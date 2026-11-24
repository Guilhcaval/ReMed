"""Camada de services do app notificacoes (Spec 03 / RF017 — ADR 0015)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.paginator import Page, Paginator
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from contas.models import StatusUsuario, Usuario
from notificacoes.models import (
    CanalNotificacao,
    Notificacao,
    OutboxEmail,
    StatusNotificacao,
    StatusOutboxEmail,
    TipoNotificacao,
)
from nucleo.exceptions import RecursoNaoEncontrado, RegraNegocioViolada

MAX_TENTATIVAS_ENVIO_EMAIL = 4  # 1 tentativa inicial + 3 novas tentativas (Spec 03 / RNF15)
INTERVALO_RETENTATIVA_MINUTOS = 1  # Backoff fixo de 1 min cabendo nos 5 min do RNF15
NOTIFICACOES_POR_PAGINA = 20  # Acréscimo da especificação (Spec 03 / RN-03-07)
_REGEX_URL_CONFIRMACAO = re.compile(r"https?://[^\s]+/contas/confirmar-email/[^\s]+")

TIPOS_CRITICOS_SEGURANCA: frozenset[str] = frozenset(
    {
        TipoNotificacao.SEGURANCA_CONTA,
        TipoNotificacao.CONFIRMACAO_EMAIL,
        TipoNotificacao.ALERTA_OPERACIONAL,
    }
)

TIPOS_PERMITIDO_LOCAL_RETIRADA: frozenset[str] = frozenset(
    {
        TipoNotificacao.AGENDAMENTO_CONFIRMADO,
        TipoNotificacao.AGENDAMENTO_ALTERADO,
        TipoNotificacao.LEMBRETE_RETIRADA_24H,
    }
)

CHAVES_PROIBIDAS_CONTEXTO: frozenset[str] = frozenset(
    {
        "cpf",
        "nome_terceiro",
        "nome_completo",
        "telefone",
        "celular",
        "email",
        "email_terceiro",
        "endereco",
        "endereco_usuario",
        "motivo_saude",
        "diagnostico",
        "receita",
        "texto_mensagem",
        "conteudo_mensagem",
        "senha",
        "password",
        "token",
        "segredo",
        "codigo_recuperacao",
    }
)


@dataclass(frozen=True)
class _DefinicaoTemplate:
    titulo: str
    assunto: str
    mensagem: str
    chaves_permitidas: frozenset[str] = frozenset()


# Catálogo fechado de templates seguros (RN-03-01 / RN-03-03 / RS002 / RS014).
CATALOGO_NOTIFICACOES: dict[str, _DefinicaoTemplate] = {
    TipoNotificacao.CONFIRMACAO_EMAIL: _DefinicaoTemplate(
        titulo="Confirme seu e-mail",
        assunto="ReMed — Confirme seu e-mail",
        mensagem="Use o link enviado para confirmar seu e-mail no ReMed.",
        chaves_permitidas=frozenset({"link_confirmacao"}),
    ),
    TipoNotificacao.SEGURANCA_CONTA: _DefinicaoTemplate(
        titulo="Aviso de segurança da conta",
        assunto="ReMed — Aviso de segurança da sua conta",
        mensagem="{evento_seguranca}",
        chaves_permitidas=frozenset({"evento_seguranca"}),
    ),
    TipoNotificacao.NOVA_CORRESPONDENCIA: _DefinicaoTemplate(
        titulo="Nova correspondência disponível",
        assunto="ReMed — Nova correspondência disponível",
        mensagem=(
            "Encontramos uma correspondência compatível para o medicamento {medicamento}. "
            "Acesse a plataforma para avaliar e responder dentro do prazo."
        ),
        chaves_permitidas=frozenset({"medicamento"}),
    ),
    TipoNotificacao.CORRESPONDENCIA_ACEITA: _DefinicaoTemplate(
        titulo="Correspondência aceita",
        assunto="ReMed — Correspondência aceita",
        mensagem=(
            "A correspondência para {medicamento} foi aceita pelas partes. "
            "Acesse a plataforma para combinar o agendamento da retirada."
        ),
        chaves_permitidas=frozenset({"medicamento"}),
    ),
    TipoNotificacao.AGENDAMENTO_PROPOSTO: _DefinicaoTemplate(
        titulo="Nova proposta de agendamento",
        assunto="ReMed — Nova proposta de agendamento",
        mensagem=(
            "Há uma proposta de agendamento para retirada de {medicamento}. "
            "Acesse a plataforma para confirmar ou sugerir outro horário."
        ),
        chaves_permitidas=frozenset({"medicamento"}),
    ),
    TipoNotificacao.AGENDAMENTO_CONFIRMADO: _DefinicaoTemplate(
        titulo="Agendamento confirmado",
        assunto="ReMed — Agendamento de retirada confirmado",
        mensagem=(
            "Seu agendamento para retirada de {medicamento} foi confirmado para {data_hora}. "
            "Local de retirada: {local_retirada}."
        ),
        chaves_permitidas=frozenset({"medicamento", "data_hora", "local_retirada"}),
    ),
    TipoNotificacao.AGENDAMENTO_ALTERADO: _DefinicaoTemplate(
        titulo="Agendamento alterado",
        assunto="ReMed — Agendamento de retirada alterado",
        mensagem=(
            "O agendamento de retirada de {medicamento} foi atualizado para {data_hora}. "
            "Local de retirada: {local_retirada}."
        ),
        chaves_permitidas=frozenset({"medicamento", "data_hora", "local_retirada"}),
    ),
    TipoNotificacao.AGENDAMENTO_CANCELADO: _DefinicaoTemplate(
        titulo="Agendamento cancelado",
        assunto="ReMed — Agendamento cancelado",
        mensagem=(
            "O agendamento relacionado a {medicamento} foi cancelado. "
            "Acesse a plataforma para acompanhar o novo status."
        ),
        chaves_permitidas=frozenset({"medicamento"}),
    ),
    TipoNotificacao.LEMBRETE_RETIRADA_24H: _DefinicaoTemplate(
        titulo="Lembrete de retirada em 24 horas",
        assunto="ReMed — Lembrete de retirada agendada",
        mensagem=(
            "Lembrete: sua retirada de {medicamento} está agendada para {data_hora}. "
            "Local de retirada: {local_retirada}."
        ),
        chaves_permitidas=frozenset({"medicamento", "data_hora", "local_retirada"}),
    ),
    TipoNotificacao.ENTREGA_CONFIRMADA: _DefinicaoTemplate(
        titulo="Entrega confirmada",
        assunto="ReMed — Entrega confirmada",
        mensagem="A retirada de {medicamento} foi confirmada com sucesso na plataforma.",
        chaves_permitidas=frozenset({"medicamento"}),
    ),
    TipoNotificacao.DOACAO_CONFERIDA: _DefinicaoTemplate(
        titulo="Resultado da conferência da doação",
        assunto="ReMed — Resultado da conferência da doação",
        mensagem=(
            "A conferência da sua doação de {medicamento} foi concluída com status: {resultado}."
        ),
        chaves_permitidas=frozenset({"medicamento", "resultado"}),
    ),
    TipoNotificacao.DOACAO_PRESTES_VENCER: _DefinicaoTemplate(
        titulo="Doação próxima do vencimento",
        assunto="ReMed — Doação próxima do vencimento",
        mensagem=(
            "Sua doação de {medicamento} está próxima da data de validade. "
            "Acesse a plataforma para conferir o status."
        ),
        chaves_permitidas=frozenset({"medicamento"}),
    ),
    TipoNotificacao.DOACAO_VENCIDA: _DefinicaoTemplate(
        titulo="Doação marcada como vencida",
        assunto="ReMed — Doação vencida removida da busca",
        mensagem=(
            "A doação de {medicamento} atingiu o limite de validade e foi retirada "
            "automaticamente da busca por segurança sanitária. "
            "Descarte medicamentos vencidos em pontos de coleta de descarte farmacêutico, "
            "conforme a legislação sanitária."
        ),
        chaves_permitidas=frozenset({"medicamento"}),
    ),
    TipoNotificacao.NOVA_MENSAGEM: _DefinicaoTemplate(
        titulo="Nova mensagem na plataforma",
        assunto="ReMed — Você recebeu uma nova mensagem",
        mensagem=(
            "Você recebeu uma nova mensagem sobre uma correspondência em andamento. "
            "Acesse a plataforma para ler e responder."
        ),
        chaves_permitidas=frozenset(),
    ),
    TipoNotificacao.PONTO_ANALISADO: _DefinicaoTemplate(
        titulo="Resultado da análise do ponto de coleta",
        assunto="ReMed — Resultado da análise do ponto de coleta",
        mensagem="A análise do ponto de coleta {ponto_nome} foi concluída: {resultado}.",
        chaves_permitidas=frozenset({"ponto_nome", "resultado"}),
    ),
    TipoNotificacao.DOCUMENTO_PRESTES_VENCER: _DefinicaoTemplate(
        titulo="Documento do ponto de coleta próximo do vencimento",
        assunto="ReMed — Documento próximo do vencimento",
        mensagem=(
            "Um documento do ponto de coleta {ponto_nome} vencerá em breve. "
            "Envie uma versão atualizada na plataforma."
        ),
        chaves_permitidas=frozenset({"ponto_nome"}),
    ),
    TipoNotificacao.SOLICITACAO_PRESTES_EXPIRAR: _DefinicaoTemplate(
        titulo="Solicitação próxima da expiração",
        assunto="ReMed — Sua solicitação expira em breve",
        mensagem=(
            "Sua solicitação para {medicamento} expirará em breve caso não haja correspondência. "
            "Acesse a plataforma para acompanhar."
        ),
        chaves_permitidas=frozenset({"medicamento"}),
    ),
    TipoNotificacao.SOLICITACAO_EXPIRADA: _DefinicaoTemplate(
        titulo="Solicitação expirada",
        assunto="ReMed — Solicitação expirada",
        mensagem=(
            "Sua solicitação para {medicamento} expirou automaticamente. "
            "Você pode registrar uma nova solicitação quando desejar."
        ),
        chaves_permitidas=frozenset({"medicamento"}),
    ),
    TipoNotificacao.RECEITA_VERIFICADA: _DefinicaoTemplate(
        titulo="Resultado da verificação da receita",
        assunto="ReMed — Resultado da verificação de receita",
        mensagem=(
            "A verificação da documentação vinculada à sua solicitação foi concluída: {resultado}."
        ),
        chaves_permitidas=frozenset({"resultado"}),
    ),
    TipoNotificacao.DENUNCIA_RESULTADO: _DefinicaoTemplate(
        titulo="Atualização sobre denúncia registrada",
        assunto="ReMed — Atualização sobre denúncia",
        mensagem="A análise da denúncia registrada na plataforma foi concluída: {resultado}.",
        chaves_permitidas=frozenset({"resultado"}),
    ),
    TipoNotificacao.ALERTA_OPERACIONAL: _DefinicaoTemplate(
        titulo="Alerta operacional: {nome_rotina}",
        assunto="ReMed — Alerta operacional ({nome_rotina})",
        mensagem="Falha operacional detectada na rotina {nome_rotina}: {resumo_tecnico}",
        chaves_permitidas=frozenset({"nome_rotina", "resumo_tecnico"}),
    ),
}


@dataclass(frozen=True)
class ResultadoDespachoOutbox:
    processados: int
    enviados: int
    reagendados: int
    falhas_definitivas: int
    links_confirmacao_dev: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultadoRegistroNotificacao:
    notificacao_plataforma: Notificacao | None
    outbox_email: OutboxEmail | None
    email_suprimido: bool = False


@dataclass(frozen=True)
class FiltrosNotificacao:
    tipo: str = ""
    status: str = ""
    data_inicio: date | None = None
    data_fim: date | None = None


@dataclass(frozen=True)
class PaginaNotificacoes:
    pagina: Page
    total_nao_lidas: int
    total_filtradas: int


def _validar_url_destino_interna(url_destino: str) -> str:
    url = (url_destino or "").strip()
    if not url:
        return ""
    if not url.startswith("/") or url.startswith("//") or "://" in url:
        raise RegraNegocioViolada("A URL de destino da notificação deve ser uma rota interna.")
    return url[:255]


def _renderizar_conteudo_seguro(
    tipo: str,
    contexto: Mapping[str, str] | None,
) -> tuple[str, str, str]:
    definicao = CATALOGO_NOTIFICACOES.get(tipo)
    if definicao is None:
        raise RegraNegocioViolada(f"Tipo de notificação não suportado: {tipo}")

    dados = dict(contexto) if contexto is not None else {}
    for chave in dados:
        chave_norm = str(chave).strip().lower()
        if chave_norm in CHAVES_PROIBIDAS_CONTEXTO:
            raise RegraNegocioViolada(
                f"Dado sensível ou proibido não permitido em notificação: {chave}"
            )
        if chave_norm == "local_retirada" and tipo not in TIPOS_PERMITIDO_LOCAL_RETIRADA:
            raise RegraNegocioViolada(
                "Endereço/local de retirada só pode constar após confirmação do agendamento."
            )
        if chave_norm not in definicao.chaves_permitidas:
            raise RegraNegocioViolada(f"Parâmetro de template não autorizado para {tipo}: {chave}")

    faltantes = definicao.chaves_permitidas - set(dados.keys())
    if faltantes:
        lista_faltantes = ", ".join(sorted(faltantes))
        raise RegraNegocioViolada(
            f"Parâmetros obrigatórios ausentes para notificação {tipo}: {lista_faltantes}"
        )

    dados_limpos = {k: str(v).strip() for k, v in dados.items()}
    titulo = definicao.titulo.format(**dados_limpos)[:140]
    assunto = definicao.assunto.format(**dados_limpos)[:160]
    mensagem = definicao.mensagem.format(**dados_limpos)
    return titulo, assunto, mensagem


class NotificacaoService:
    @staticmethod
    def enfileirar_email_confirmacao(
        *,
        destinatario,
        email_destino: str,
        link_confirmacao: str,
    ) -> OutboxEmail:
        agora = timezone.now()
        assunto = "ReMed — Confirme seu e-mail"
        corpo_texto = render_to_string(
            "notificacoes/email/confirmacao_email.txt",
            {"link_confirmacao": link_confirmacao},
        )
        return OutboxEmail.objects.create(
            destinatario=destinatario,
            email_destino=email_destino,
            tipo=TipoNotificacao.CONFIRMACAO_EMAIL,
            critico_seguranca=True,
            assunto=assunto,
            corpo_texto=corpo_texto,
            status=StatusOutboxEmail.PENDENTE,
            tentativas=0,
            proxima_tentativa_em=agora,
        )

    @staticmethod
    def suprimir_emails_confirmacao_pendentes(destinatario) -> int:
        """Suprime e-mails de confirmação pendentes substituídos por novo token."""
        return OutboxEmail.objects.filter(
            destinatario=destinatario,
            tipo=TipoNotificacao.CONFIRMACAO_EMAIL,
            status=StatusOutboxEmail.PENDENTE,
        ).update(
            status=StatusOutboxEmail.SUPRIMIDA,
            erro_ultimo="Substituído por novo link de confirmação.",
        )

    @staticmethod
    def registrar_evento(
        *,
        destinatario: Usuario,
        tipo: str,
        contexto: Mapping[str, str] | None = None,
        url_destino: str = "",
        enviar_plataforma: bool = True,
        enviar_email: bool = True,
    ) -> ResultadoRegistroNotificacao:
        if destinatario is None or destinatario.anonimizado_em is not None:
            raise RegraNegocioViolada("Destinatário inválido ou anonimizado para notificação.")

        url_segura = _validar_url_destino_interna(url_destino)
        titulo, assunto, mensagem = _renderizar_conteudo_seguro(tipo, contexto)
        critico = tipo in TIPOS_CRITICOS_SEGURANCA
        agora = timezone.now()

        notificacao_plataforma: Notificacao | None = None
        if enviar_plataforma:
            notificacao_plataforma = Notificacao.objects.create(
                destinatario=destinatario,
                tipo=tipo,
                canal=CanalNotificacao.PLATAFORMA,
                obrigatoria=critico,
                titulo=titulo,
                mensagem=mensagem,
                url_destino=url_segura,
                status=StatusNotificacao.ENVIADA,
                enviada_em=agora,
            )

        outbox_email: OutboxEmail | None = None
        email_suprimido = False
        if enviar_email and destinatario.email:
            limite_hora = settings.REMED_NOTIFICACAO_EMAIL_LIMITE_HORA
            excedeu_limite = False
            if not critico:
                janela_inicio = agora - timedelta(hours=1)
                enviados_ultima_hora = OutboxEmail.objects.filter(
                    destinatario=destinatario,
                    critico_seguranca=False,
                    criado_em__gte=janela_inicio,
                    status__in=[StatusOutboxEmail.PENDENTE, StatusOutboxEmail.ENVIADA],
                ).count()
                excedeu_limite = enviados_ultima_hora >= limite_hora

            corpo_texto = render_to_string(
                "notificacoes/email/notificacao_padrao.txt",
                {"titulo": titulo, "mensagem": mensagem},
            )
            if excedeu_limite:
                email_suprimido = True
                outbox_email = OutboxEmail.objects.create(
                    notificacao=None,
                    destinatario=destinatario,
                    email_destino=destinatario.email,
                    tipo=tipo,
                    critico_seguranca=False,
                    assunto=assunto,
                    corpo_texto=corpo_texto,
                    status=StatusOutboxEmail.SUPRIMIDA,
                    tentativas=0,
                    proxima_tentativa_em=agora,
                    erro_ultimo="Limite horario de e-mails nao criticos atingido.",
                )
            else:
                notificacao_email = Notificacao.objects.create(
                    destinatario=destinatario,
                    tipo=tipo,
                    canal=CanalNotificacao.EMAIL,
                    obrigatoria=critico,
                    titulo=titulo,
                    mensagem=mensagem,
                    url_destino=url_segura,
                    status=StatusNotificacao.PENDENTE,
                )
                outbox_email = OutboxEmail.objects.create(
                    notificacao=notificacao_email,
                    destinatario=destinatario,
                    email_destino=destinatario.email,
                    tipo=tipo,
                    critico_seguranca=critico,
                    assunto=assunto,
                    corpo_texto=corpo_texto,
                    status=StatusOutboxEmail.PENDENTE,
                    tentativas=0,
                    proxima_tentativa_em=agora,
                )

        return ResultadoRegistroNotificacao(
            notificacao_plataforma=notificacao_plataforma,
            outbox_email=outbox_email,
            email_suprimido=email_suprimido,
        )

    @staticmethod
    def alertar_administradores_operacional(
        *,
        nome_rotina: str,
        resumo_tecnico: str,
        enviar_email: bool = False,
    ) -> int:
        """Registra alerta operacional exclusivamente para contas ativas com gestao_administradores.

        Quando chamado a partir de falhas SMTP (despachar_emails), `enviar_email=False` garante
        que o alerta fique registrado na plataforma sem criar cascata/loop de falhas no outbox.
        """
        admins = list(
            Usuario.objects.filter(
                groups__name="gestao_administradores",
                status=StatusUsuario.ATIVO,
                email_confirmado_em__isnull=False,
                anonimizado_em__isnull=True,
            ).distinct()
        )
        resumo_limpo = (resumo_tecnico or "Falha operacional detectada.").strip()[:200]
        total = 0
        for admin in admins:
            NotificacaoService.registrar_evento(
                destinatario=admin,
                tipo=TipoNotificacao.ALERTA_OPERACIONAL,
                contexto={"nome_rotina": nome_rotina[:60], "resumo_tecnico": resumo_limpo},
                enviar_plataforma=True,
                enviar_email=enviar_email,
            )
            total += 1
        return total

    @staticmethod
    def despachar_outbox_pendentes(*, limite_lote: int = 50) -> ResultadoDespachoOutbox:
        agora = timezone.now()
        with transaction.atomic():
            ids_lote = list(
                OutboxEmail.objects.select_for_update(skip_locked=True)
                .filter(
                    status=StatusOutboxEmail.PENDENTE,
                    proxima_tentativa_em__lte=agora,
                )
                .order_by("proxima_tentativa_em", "id")
                .values_list("id", flat=True)[:limite_lote]
            )

        enviados = 0
        reagendados = 0
        falhas_definitivas = 0
        links_confirmacao_dev: list[str] = []

        for item_id in ids_lote:
            with transaction.atomic():
                item = (
                    OutboxEmail.objects.select_for_update(skip_locked=True, of=("self",))
                    .select_related("notificacao")
                    .filter(
                        id=item_id,
                        status=StatusOutboxEmail.PENDENTE,
                    )
                    .first()
                )
                if item is None:
                    continue

                item.tentativas += 1
                try:
                    send_mail(
                        subject=item.assunto,
                        message=item.corpo_texto,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[item.email_destino],
                        fail_silently=False,
                    )
                except Exception as erro:
                    item.erro_ultimo = str(erro)[:255]
                    if item.tentativas >= MAX_TENTATIVAS_ENVIO_EMAIL:
                        item.status = StatusOutboxEmail.FALHA
                        falhas_definitivas += 1
                        if item.notificacao_id is not None:
                            item.notificacao.status = StatusNotificacao.FALHA
                            item.notificacao.save(update_fields=["status"])
                    else:
                        item.proxima_tentativa_em = timezone.now() + timedelta(
                            minutes=INTERVALO_RETENTATIVA_MINUTOS
                        )
                        reagendados += 1
                    item.save(
                        update_fields=[
                            "tentativas",
                            "status",
                            "proxima_tentativa_em",
                            "erro_ultimo",
                        ]
                    )
                else:
                    momento_envio = timezone.now()
                    item.status = StatusOutboxEmail.ENVIADA
                    item.enviado_em = momento_envio
                    item.erro_ultimo = ""
                    item.save(update_fields=["tentativas", "status", "enviado_em", "erro_ultimo"])
                    if item.notificacao_id is not None:
                        item.notificacao.status = StatusNotificacao.ENVIADA
                        item.notificacao.enviada_em = momento_envio
                        item.notificacao.save(update_fields=["status", "enviada_em"])
                    if settings.DEBUG and item.tipo == TipoNotificacao.CONFIRMACAO_EMAIL:
                        links_confirmacao_dev.extend(
                            _REGEX_URL_CONFIRMACAO.findall(item.corpo_texto or "")
                        )
                    enviados += 1

        return ResultadoDespachoOutbox(
            processados=len(ids_lote),
            enviados=enviados,
            reagendados=reagendados,
            falhas_definitivas=falhas_definitivas,
            links_confirmacao_dev=tuple(links_confirmacao_dev),
        )

    @staticmethod
    def contar_nao_lidas(usuario_id: int) -> int:
        return Notificacao.objects.filter(
            destinatario_id=usuario_id,
            canal=CanalNotificacao.PLATAFORMA,
            status=StatusNotificacao.ENVIADA,
        ).count()

    @staticmethod
    def listar_do_usuario(
        usuario_id: int,
        filtros: FiltrosNotificacao | None = None,
        *,
        pagina: int = 1,
        por_pagina: int = NOTIFICACOES_POR_PAGINA,
    ) -> PaginaNotificacoes:
        f = filtros if filtros is not None else FiltrosNotificacao()
        qs = Notificacao.objects.filter(
            destinatario_id=usuario_id,
            canal=CanalNotificacao.PLATAFORMA,
        )
        if f.tipo:
            qs = qs.filter(tipo=f.tipo)
        if f.status == "nao_lida":
            qs = qs.filter(status=StatusNotificacao.ENVIADA)
        elif f.status == "lida":
            qs = qs.filter(status=StatusNotificacao.LIDA)
        if f.data_inicio is not None:
            inicio_dt = timezone.make_aware(datetime.combine(f.data_inicio, time.min))
            qs = qs.filter(criada_em__gte=inicio_dt)
        if f.data_fim is not None:
            fim_dt = timezone.make_aware(datetime.combine(f.data_fim, time.max))
            qs = qs.filter(criada_em__lte=fim_dt)

        qs = qs.order_by("-criada_em", "-id")
        paginador = Paginator(qs, por_pagina)
        page_obj = paginador.get_page(pagina)
        return PaginaNotificacoes(
            pagina=page_obj,
            total_nao_lidas=NotificacaoService.contar_nao_lidas(usuario_id),
            total_filtradas=paginador.count,
        )

    @staticmethod
    def marcar_como_lida(notificacao_id: int, usuario_id: int) -> Notificacao:
        with transaction.atomic():
            notificacao = (
                Notificacao.objects.select_for_update()
                .filter(
                    pk=notificacao_id,
                    destinatario_id=usuario_id,
                    canal=CanalNotificacao.PLATAFORMA,
                )
                .first()
            )
            if notificacao is None:
                raise RecursoNaoEncontrado("Notificação não encontrada.")
            if notificacao.status != StatusNotificacao.LIDA:
                notificacao.status = StatusNotificacao.LIDA
                notificacao.lida_em = timezone.now()
                notificacao.save(update_fields=["status", "lida_em"])
            return notificacao

    @staticmethod
    def marcar_todas_como_lidas(usuario_id: int) -> int:
        agora = timezone.now()
        with transaction.atomic():
            return Notificacao.objects.filter(
                destinatario_id=usuario_id,
                canal=CanalNotificacao.PLATAFORMA,
                status=StatusNotificacao.ENVIADA,
            ).update(status=StatusNotificacao.LIDA, lida_em=agora)
