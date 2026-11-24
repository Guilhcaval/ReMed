"""Camada de services do app medicamentos (Specs 08, 09, 10, 11 e 14)."""

import logging
import time as time_module
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.paginator import Page, Paginator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from auditoria.models import OrigemAuditoria
from auditoria.services import AuditoriaService
from contas.models import EnderecoUsuario, StatusUsuario, Usuario
from contas.services import AutenticacaoService
from medicamentos.exceptions import (
    CienciaRefrigeradoObrigatoria,
    DadosRefrigeracaoObrigatorios,
    DoacaoIndisponivel,
    DoacaoVencidaIrreversivel,
    EmbalagemNaoIntegra,
    FotoDoacaoFormatoInvalido,
    FotoDoacaoObrigatoria,
    JanelaRefrigeradoInvalida,
    MedicamentoControleEspecialBloqueado,
    MotivoReprovacaoObrigatorio,
    ValidadeDoacaoInvalida,
)
from medicamentos.models import (
    CondicaoConservacao,
    ConferenciaDoacao,
    DadosRefrigeracaoDoacao,
    Doacao,
    ExecucaoVencimento,
    FotoDoacao,
    ParametroVencimento,
    ResultadoConferenciaDoacao,
    StatusDoacao,
)
from notificacoes.models import TipoNotificacao
from notificacoes.services import NotificacaoService
from nucleo.arquivos import (
    AntimalwareScanner,
    ArquivoArmazenado,
    ArquivoService,
    BackendArmazenamentoPrivado,
)
from nucleo.exceptions import (
    ArquivoFormatoInvalido,
    ConflitoConcorrencia,
    PermissaoNegada,
    RecursoNaoEncontrado,
    RegraNegocioViolada,
)
from nucleo.models import ExecucaoRotina, FormaFarmaceutica, ResultadoRotina
from nucleo.services import CepService, GeolocalizacaoService
from pontos_coleta.models import PontoColeta, StatusPontoColeta

logger = logging.getLogger(__name__)

NOME_ROTINA_VENCIMENTO = "verificar_vencimento_doacoes"
EXTENSOES_FOTO_DOACAO: frozenset[str] = frozenset({"jpg", "jpeg", "png"})
DOACOES_POR_PAGINA = 15
CONFERENCIAS_POR_PAGINA = 20
EXECUCOES_POR_PAGINA = 20
BUSCA_POR_PAGINA = 10  # Literal do RF015 (regra 5)

# Checklist orientativo não bloqueante (Spec 10 / RN-10-03 — Questão 4 do PRD em aberto).
CHECKLIST_ORIENTATIVO_CONFERENCIA: tuple[str, ...] = (
    "Conferir se o nome, concentração, lote e data de validade na foto conferem com o cadastro.",
    "Verificar indícios de integridade aparente da embalagem (lacrada, sem avarias ou violação).",
    (
        "Confirmar que o medicamento não pertence à lista de controle especial "
        "(Portaria SVS/MS nº 344/1998)."
    ),
    (
        "Em medicamentos refrigerados, conferir se a faixa de temperatura da bula "
        "e a declaração estão completas."
    ),
)

# Motivos orientativos para reprovação na conferência (Spec 10 — acréscimo aprovado).
MOTIVOS_ORIENTATIVOS_REPROVACAO: tuple[str, ...] = (
    "Foto ilegível ou sem visualização clara da validade/lote",
    "Divergência entre os dados cadastrados e a foto da embalagem",
    "Indício de medicamento de controle especial (Portaria SVS/MS nº 344/1998)",
    "Embalagem aparentando violação, avaria ou uso parcial",
    "Informações insuficientes de conservação para medicamento refrigerado",
)


@dataclass(frozen=True)
class ArquivoFotoEntrada:
    conteudo: bytes
    nome_original: str


@dataclass(frozen=True)
class DadosDoacao:
    nome_medicamento: str
    principio_ativo: str
    concentracao_dosagem: str
    forma_farmaceutica_id: int
    quantidade: int
    fabricante: str
    lote: str
    data_validade: date
    embalagem_integra: bool
    controle_especial: bool
    condicao_conservacao: str
    sujeito_receita: bool
    ponto_coleta_id: int | None = None
    observacoes: str = ""
    faixa_temperatura_bula: str = ""
    declaracao_doador_conservacao: bool = False


@dataclass(frozen=True)
class ResultadoAtualizacaoDoacao:
    doacao: Doacao
    campos_alterados: tuple[str, ...]
    remetida_reanalise: bool


@dataclass(frozen=True)
class FiltrosMinhasDoacoes:
    termo: str = ""
    status: str = ""
    data_inicio: date | None = None
    data_fim: date | None = None


@dataclass(frozen=True)
class PaginaDoacoes:
    pagina: Page
    total_encontrados: int


@dataclass(frozen=True)
class FiltrosConferenciaAdmin:
    termo: str = ""
    condicao_conservacao: str = ""
    sujeito_receita: str = ""
    data_inicio: date | None = None
    data_fim: date | None = None


@dataclass(frozen=True)
class DetalheConferenciaDoacao:
    doacao: Doacao
    fotos: tuple[FotoDoacao, ...]
    dados_refrigeracao: DadosRefrigeracaoDoacao | None
    conferencias: tuple[ConferenciaDoacao, ...]
    dentro_validade_minima: bool
    validade_minima_dias: int
    checklist_orientativo: tuple[str, ...]
    motivos_orientativos: tuple[str, ...]


@dataclass(frozen=True)
class ResultadoCancelamentoCorrespondencia:
    cancelados: int = 0
    solicitantes_notificar: tuple[Usuario, ...] = ()


@dataclass(frozen=True)
class ResultadoExecucaoVencimento:
    execucao_rotina: ExecucaoRotina
    execucao_vencimento: ExecucaoVencimento
    doacoes_verificadas: int
    doacoes_marcadas_vencidas: int
    avisos_enviados: int
    reservas_agendamentos_cancelados: int
    notificacoes_enviadas: int
    resultado: str


@dataclass(frozen=True)
class LocalizacaoBuscaSessao:
    origem: str
    rotulo_aproximado: str
    latitude_aprox: Decimal
    longitude_aprox: Decimal
    cep: str = ""


@dataclass(frozen=True)
class FiltrosBuscaMedicamento:
    termo: str = ""
    forma_farmaceutica_id: int | None = None
    concentracao: str = ""
    distancia_max_km: int | None = None
    validade_minima: date | None = None
    condicao_conservacao: str = ""


@dataclass(frozen=True)
class ItemBuscaMedicamento:
    """Projeção estrita dos campos públicos do RF015 (sem PII, endereço ou ponto de retirada)."""

    id: int
    nome_medicamento: str
    principio_ativo: str
    concentracao_dosagem: str
    forma_farmaceutica_nome: str
    quantidade_disponivel: int
    data_validade: date
    condicao_conservacao: str
    condicao_conservacao_display: str
    sujeito_receita: bool
    regiao_aproximada: str
    faixa_distancia: str


@dataclass(frozen=True)
class PaginaBuscaMedicamentos:
    pagina: Page
    total_encontrados: int
    ordenado_por_proximidade: bool


def _cancelar_correspondencias_noop(
    doacao: Doacao,
    *,
    motivo: str,
) -> ResultadoCancelamentoCorrespondencia:
    """Gancho padrão até o app correspondencias existir (Etapa 8).

    TODO(Etapa 8 / Specs 15 e 16 — RF016/RF018): sob select_for_update() na ordem fixa
    (Doacao -> Solicitacao -> Correspondencia -> Agendamento), cancelar correspondência/reserva
    e agendamento em aberto vinculados à doação, devolver a solicitação para `aberta` e retornar
    a contagem de cancelamentos + solicitantes a notificar.
    """
    _ = (doacao, motivo)
    return ResultadoCancelamentoCorrespondencia()


def _acionar_correspondencia_noop(doacao: Doacao) -> None:
    """Gancho padrão até o app correspondencias existir (Etapa 8 — Spec 15 / RF016)."""
    _ = doacao


def _verificar_solicitante_vinculado_noop(doacao: Doacao, usuario: Usuario) -> bool:
    """Gancho padrão até o app correspondencias existir (Etapa 8 — Spec 15/16/18)."""
    _ = (doacao, usuario)
    return False


def _rotulo_medicamento_notificacao(doacao: Doacao) -> str:
    return f"{doacao.nome_medicamento} ({doacao.concentracao_dosagem})"[:120]


def _formatar_regiao_aproximada(bairro: str, municipio: str, uf: str) -> str:
    bairro_limpo = (bairro or "").strip()
    municipio_limpo = (municipio or "").strip()
    uf_limpa = (uf or "").strip().upper()
    local_cidade = (
        f"{municipio_limpo}/{uf_limpa}" if municipio_limpo and uf_limpa else municipio_limpo
    )
    if bairro_limpo and local_cidade:
        return f"{bairro_limpo} · {local_cidade}"
    return bairro_limpo or local_cidade or "Região não informada"


def _validar_usuario_doador_ativo(usuario: Usuario) -> None:
    if (
        usuario is None
        or not getattr(usuario, "is_authenticated", False)
        or usuario.status != StatusUsuario.ATIVO
        or usuario.email_confirmado_em is None
        or usuario.anonimizado_em is not None
    ):
        raise PermissaoNegada("Somente usuários ativos com e-mail confirmado podem doar.")
    if not usuario.perfil_doador:
        raise PermissaoNegada("Apenas usuários com perfil Doador podem gerenciar doações.")


class RefrigeracaoService:
    """Regras puras de conservação e transporte para medicamentos refrigerados (Spec 09 / RF010)."""

    @staticmethod
    def validar_dados_doador(faixa_temperatura: str, declaracao: bool) -> str:
        faixa_limpa = (faixa_temperatura or "").strip()
        if not faixa_limpa or not declaracao:
            raise DadosRefrigeracaoObrigatorios()
        return faixa_limpa[:80]

    @staticmethod
    def validar_janela_curta(
        hora_inicio: time,
        hora_fim: time,
        *,
        limite_minutos: int | None = None,
    ) -> int:
        if hora_inicio is None or hora_fim is None or hora_inicio >= hora_fim:
            raise JanelaRefrigeradoInvalida()
        limite = (
            limite_minutos
            if limite_minutos is not None
            else settings.REMED_REFRIGERADO_JANELA_MAX_MINUTOS
        )
        minutos_inicio = hora_inicio.hour * 60 + hora_inicio.minute
        minutos_fim = hora_fim.hour * 60 + hora_fim.minute
        duracao = minutos_fim - minutos_inicio
        if duracao <= 0 or duracao > limite:
            raise JanelaRefrigeradoInvalida()
        return duracao

    @staticmethod
    def validar_ciencia_solicitante(ciencia_confirmada: bool) -> None:
        if not ciencia_confirmada:
            raise CienciaRefrigeradoObrigatoria()

    @staticmethod
    def priorizar_pontos_refrigerados(pontos: Iterable[PontoColeta]) -> list[PontoColeta]:
        return sorted(
            pontos,
            key=lambda p: (not p.possui_refrigeracao, (p.nome_fantasia or "").lower(), p.pk or 0),
        )


class VencimentoService:
    """Parâmetros, validação em tempo real e rotina diária de vencimento (Spec 11 / RF012)."""

    @staticmethod
    def obter_parametros() -> ParametroVencimento:
        param, _ = ParametroVencimento.objects.get_or_create(
            id=1,
            defaults={
                "validade_minima_restante_dias": 30,
                "antecedencia_aviso_dias": 15,
            },
        )
        return param

    @staticmethod
    def atualizar_parametros(
        ator: Usuario,
        *,
        validade_minima_restante_dias: int,
        antecedencia_aviso_dias: int,
    ) -> ParametroVencimento:
        if not AutenticacaoService.possui_funcao(ator, "metricas_e_parametros"):
            raise PermissaoNegada(
                "Apenas Administradores com função métricas e parâmetros podem alterar "
                "os parâmetros de vencimento."
            )
        if validade_minima_restante_dias < 0:
            raise RegraNegocioViolada("A validade mínima restante deve ser maior ou igual a zero.")
        if antecedencia_aviso_dias < 1:
            raise RegraNegocioViolada(
                "A antecedência do aviso de vencimento deve ser de pelo menos 1 dia."
            )

        with transaction.atomic():
            param, _ = ParametroVencimento.objects.select_for_update().get_or_create(
                id=1,
                defaults={
                    "validade_minima_restante_dias": 30,
                    "antecedencia_aviso_dias": 15,
                },
            )
            anterior = {
                "validade_minima_restante_dias": param.validade_minima_restante_dias,
                "antecedencia_aviso_dias": param.antecedencia_aviso_dias,
            }
            param.validade_minima_restante_dias = int(validade_minima_restante_dias)
            param.antecedencia_aviso_dias = int(antecedencia_aviso_dias)
            param.atualizado_por = ator
            param.save(
                update_fields=[
                    "validade_minima_restante_dias",
                    "antecedencia_aviso_dias",
                    "atualizado_por",
                    "atualizado_em",
                ]
            )
            AuditoriaService.registrar(
                acao="parametro_vencimento.atualizado",
                entidade_tipo="parametro_vencimento",
                entidade_id=param.pk,
                ator=ator,
                detalhes={
                    "anterior": anterior,
                    "novo": {
                        "validade_minima_restante_dias": param.validade_minima_restante_dias,
                        "antecedencia_aviso_dias": param.antecedencia_aviso_dias,
                    },
                },
            )
            return param

    @staticmethod
    def calcular_data_corte(
        referencia: date | None = None,
        *,
        parametros: ParametroVencimento | None = None,
    ) -> date:
        hoje = referencia if referencia is not None else timezone.localdate()
        params = parametros if parametros is not None else VencimentoService.obter_parametros()
        return hoje + timedelta(days=params.validade_minima_restante_dias)

    @staticmethod
    def doacao_dentro_da_validade(
        doacao_ou_data: Doacao | date,
        *,
        referencia: date | None = None,
        parametros: ParametroVencimento | None = None,
    ) -> bool:
        data_validade = (
            doacao_ou_data.data_validade if isinstance(doacao_ou_data, Doacao) else doacao_ou_data
        )
        hoje = referencia if referencia is not None else timezone.localdate()
        data_corte = VencimentoService.calcular_data_corte(hoje, parametros=parametros)
        return data_validade >= hoje and data_validade >= data_corte

    @staticmethod
    def impedir_reativacao_vencida(doacao: Doacao) -> None:
        if doacao.status == StatusDoacao.VENCIDO:
            raise DoacaoVencidaIrreversivel()

    @staticmethod
    def verificar_ou_vencer_doacao(
        doacao_id: int,
        *,
        referencia: date | None = None,
        cancelador_correspondencias: Callable[..., ResultadoCancelamentoCorrespondencia]
        | None = None,
    ) -> Doacao:
        """Validação em tempo real de validade sob select_for_update() (RF012 / ADR 0013)."""
        hoje = referencia if referencia is not None else timezone.localdate()
        parametros = VencimentoService.obter_parametros()
        cancelador = (
            cancelador_correspondencias
            if cancelador_correspondencias is not None
            else _cancelar_correspondencias_noop
        )

        venceu_ou_indisponivel = False
        with transaction.atomic():
            doacao = (
                Doacao.objects.select_for_update()
                .select_related("doador")
                .filter(pk=doacao_id)
                .first()
            )
            if doacao is None:
                raise RecursoNaoEncontrado("Doação não encontrada.")
            if doacao.status == StatusDoacao.VENCIDO:
                venceu_ou_indisponivel = True
            elif VencimentoService.doacao_dentro_da_validade(
                doacao, referencia=hoje, parametros=parametros
            ):
                return doacao
            else:
                if doacao.status in {
                    StatusDoacao.EM_ANALISE,
                    StatusDoacao.DISPONIVEL,
                    StatusDoacao.RESERVADO,
                }:
                    status_anterior = doacao.status
                    doacao.status = StatusDoacao.VENCIDO
                    doacao.save(update_fields=["status", "atualizado_em"])
                    cancelamento = cancelador(
                        doacao, motivo="Doação venceu ou ficou abaixo da validade mínima."
                    )
                    rotulo = _rotulo_medicamento_notificacao(doacao)
                    if doacao.doador.anonimizado_em is None:
                        NotificacaoService.registrar_evento(
                            destinatario=doacao.doador,
                            tipo=TipoNotificacao.DOACAO_VENCIDA,
                            contexto={"medicamento": rotulo},
                            url_destino="/doacoes/minhas/",
                        )
                    for solicitante in cancelamento.solicitantes_notificar:
                        if solicitante.anonimizado_em is None:
                            NotificacaoService.registrar_evento(
                                destinatario=solicitante,
                                tipo=TipoNotificacao.DOACAO_VENCIDA,
                                contexto={"medicamento": rotulo},
                                url_destino="/notificacoes/",
                            )
                    AuditoriaService.registrar(
                        acao="doacao.vencida_tempo_real",
                        entidade_tipo="doacao",
                        entidade_id=doacao.pk,
                        detalhes={
                            "status_anterior": status_anterior,
                            "status_novo": StatusDoacao.VENCIDO,
                            "cancelamentos": cancelamento.cancelados,
                        },
                    )
                venceu_ou_indisponivel = True

        if venceu_ou_indisponivel:
            raise DoacaoIndisponivel()
        return doacao

    @staticmethod
    def executar_rotina_diaria(
        *,
        referencia: date | None = None,
        cancelador_correspondencias: Callable[..., ResultadoCancelamentoCorrespondencia]
        | None = None,
        tentativa: int = 1,
        processador_item_vencido: Callable[[Doacao], None] | None = None,
    ) -> ResultadoExecucaoVencimento:
        """Executa a rotina diária de vencimento e aviso prévio de forma idempotente (RF012)."""
        iniciada_em = timezone.now()
        execucao_rotina = ExecucaoRotina.objects.create(
            nome_rotina=NOME_ROTINA_VENCIMENTO,
            iniciada_em=iniciada_em,
            tentativa=max(1, int(tentativa)),
            resultado=ResultadoRotina.EM_ANDAMENTO,
        )

        hoje = referencia if referencia is not None else timezone.localdate()
        cancelador = (
            cancelador_correspondencias
            if cancelador_correspondencias is not None
            else _cancelar_correspondencias_noop
        )

        doacoes_verificadas = 0
        doacoes_marcadas_vencidas = 0
        avisos_enviados = 0
        reservas_canceladas = 0
        notificacoes_enviadas = 0
        erros_itens: list[str] = []

        try:
            parametros = VencimentoService.obter_parametros()
            data_corte = VencimentoService.calcular_data_corte(hoje, parametros=parametros)
            limite_aviso = data_corte + timedelta(days=parametros.antecedencia_aviso_dias)

            status_monitorados = (
                StatusDoacao.EM_ANALISE,
                StatusDoacao.DISPONIVEL,
                StatusDoacao.RESERVADO,
            )
            doacoes_verificadas = Doacao.objects.filter(status__in=status_monitorados).count()

            # Etapa A — Vencimento efetivo (transação isolada por item para suportar `parcial`)
            ids_para_vencer = list(
                Doacao.objects.filter(
                    status__in=status_monitorados,
                    data_validade__lt=data_corte,
                )
                .order_by("id")
                .values_list("id", flat=True)
            )
            for doacao_id in ids_para_vencer:
                try:
                    with transaction.atomic():
                        doacao = (
                            Doacao.objects.select_for_update()
                            .select_related("doador")
                            .filter(pk=doacao_id, status__in=status_monitorados)
                            .first()
                        )
                        if doacao is None or doacao.data_validade >= data_corte:
                            continue

                        if processador_item_vencido is not None:
                            processador_item_vencido(doacao)

                        status_anterior = doacao.status
                        doacao.status = StatusDoacao.VENCIDO
                        doacao.save(update_fields=["status", "atualizado_em"])

                        cancelamento = cancelador(
                            doacao, motivo="Vencimento automático pela rotina diária (RF012)."
                        )
                        rotulo = _rotulo_medicamento_notificacao(doacao)

                        notifs_item = 0
                        if doacao.doador.anonimizado_em is None:
                            NotificacaoService.registrar_evento(
                                destinatario=doacao.doador,
                                tipo=TipoNotificacao.DOACAO_VENCIDA,
                                contexto={"medicamento": rotulo},
                                url_destino="/doacoes/minhas/",
                            )
                            notifs_item += 1

                        for solicitante in cancelamento.solicitantes_notificar:
                            if solicitante.anonimizado_em is None:
                                NotificacaoService.registrar_evento(
                                    destinatario=solicitante,
                                    tipo=TipoNotificacao.DOACAO_VENCIDA,
                                    contexto={"medicamento": rotulo},
                                    url_destino="/notificacoes/",
                                )
                                notifs_item += 1

                        AuditoriaService.registrar(
                            acao="doacao.vencida_rotina",
                            entidade_tipo="doacao",
                            entidade_id=doacao.pk,
                            origem=OrigemAuditoria.ROTINA_AUTOMATICA,
                            detalhes={
                                "status_anterior": status_anterior,
                                "status_novo": StatusDoacao.VENCIDO,
                                "reservas_agendamentos_cancelados": cancelamento.cancelados,
                            },
                        )

                    doacoes_marcadas_vencidas += 1
                    reservas_canceladas += cancelamento.cancelados
                    notificacoes_enviadas += notifs_item
                except Exception as erro_item:
                    logger.exception("Erro ao vencer doação #%s na rotina diária.", doacao_id)
                    erros_itens.append(f"doacao#{doacao_id}: {erro_item.__class__.__name__}")

            # Etapa B — Aviso prévio de vencimento (idempotente via aviso_vencimento_enviado_em)
            ids_para_avisar = list(
                Doacao.objects.filter(
                    status__in=(StatusDoacao.EM_ANALISE, StatusDoacao.DISPONIVEL),
                    aviso_vencimento_enviado_em__isnull=True,
                    data_validade__gte=data_corte,
                    data_validade__lte=limite_aviso,
                )
                .order_by("id")
                .values_list("id", flat=True)
            )
            for doacao_id in ids_para_avisar:
                try:
                    with transaction.atomic():
                        doacao = (
                            Doacao.objects.select_for_update()
                            .select_related("doador")
                            .filter(
                                pk=doacao_id,
                                status__in=(StatusDoacao.EM_ANALISE, StatusDoacao.DISPONIVEL),
                                aviso_vencimento_enviado_em__isnull=True,
                            )
                            .first()
                        )
                        if doacao is None:
                            continue

                        doacao.aviso_vencimento_enviado_em = timezone.now()
                        doacao.save(update_fields=["aviso_vencimento_enviado_em", "atualizado_em"])
                        if doacao.doador.anonimizado_em is None:
                            NotificacaoService.registrar_evento(
                                destinatario=doacao.doador,
                                tipo=TipoNotificacao.DOACAO_PRESTES_VENCER,
                                contexto={"medicamento": _rotulo_medicamento_notificacao(doacao)},
                                url_destino="/doacoes/minhas/",
                            )
                            avisos_enviados += 1
                            notificacoes_enviadas += 1
                except Exception as erro_aviso:
                    logger.exception("Erro ao avisar vencimento da doação #%s.", doacao_id)
                    erros_itens.append(f"aviso#{doacao_id}: {erro_aviso.__class__.__name__}")

            resultado_final = ResultadoRotina.PARCIAL if erros_itens else ResultadoRotina.SUCESSO
            resumo_erro = "; ".join(erros_itens)[:500]
        except Exception as erro_fatal:
            logger.exception("Falha sistêmica na rotina %s.", NOME_ROTINA_VENCIMENTO)
            resultado_final = ResultadoRotina.FALHA
            resumo_erro = f"{erro_fatal.__class__.__name__}: {str(erro_fatal)[:400]}"

        execucao_rotina.finalizada_em = timezone.now()
        execucao_rotina.resultado = resultado_final
        execucao_rotina.contadores = {
            "doacoes_verificadas": doacoes_verificadas,
            "doacoes_marcadas_vencidas": doacoes_marcadas_vencidas,
            "avisos_enviados": avisos_enviados,
            "reservas_agendamentos_cancelados": reservas_canceladas,
            "notificacoes_enviadas": notificacoes_enviadas,
        }
        execucao_rotina.resumo_erro = resumo_erro
        execucao_rotina.save(
            update_fields=["finalizada_em", "resultado", "contadores", "resumo_erro"]
        )

        execucao_vencimento = ExecucaoVencimento.objects.create(
            execucao_rotina=execucao_rotina,
            doacoes_verificadas=doacoes_verificadas,
            doacoes_marcadas_vencidas=doacoes_marcadas_vencidas,
            reservas_agendamentos_cancelados=reservas_canceladas,
            notificacoes_enviadas=notificacoes_enviadas,
            resultado=resultado_final,
            resumo_erro=resumo_erro,
        )

        if resultado_final in {ResultadoRotina.PARCIAL, ResultadoRotina.FALHA}:
            NotificacaoService.alertar_administradores_operacional(
                nome_rotina=NOME_ROTINA_VENCIMENTO,
                resumo_tecnico=(
                    f"Tentativa {execucao_rotina.tentativa} encerrada com status "
                    f"{resultado_final}: {resumo_erro[:120]}"
                ),
                enviar_email=False,
            )

        return ResultadoExecucaoVencimento(
            execucao_rotina=execucao_rotina,
            execucao_vencimento=execucao_vencimento,
            doacoes_verificadas=doacoes_verificadas,
            doacoes_marcadas_vencidas=doacoes_marcadas_vencidas,
            avisos_enviados=avisos_enviados,
            reservas_agendamentos_cancelados=reservas_canceladas,
            notificacoes_enviadas=notificacoes_enviadas,
            resultado=resultado_final,
        )

    @staticmethod
    def executar_com_retentativas(
        *,
        referencia: date | None = None,
        cancelador_correspondencias: Callable[..., ResultadoCancelamentoCorrespondencia]
        | None = None,
        max_retentativas: int | None = None,
        intervalo_segundos: int | None = None,
        sleep_fn: Callable[[float], None] = time_module.sleep,
        executor: Callable[..., ResultadoExecucaoVencimento] | None = None,
    ) -> tuple[ResultadoExecucaoVencimento, ...]:
        """Executa a rotina diária e realiza até 3 novas tentativas (15 min) em falha/parcial."""
        limite_retries = (
            settings.REMED_VENCIMENTO_MAX_RETENTATIVAS
            if max_retentativas is None
            else max(0, int(max_retentativas))
        )
        intervalo = (
            settings.REMED_VENCIMENTO_RETRY_INTERVALO_SEGUNDOS
            if intervalo_segundos is None
            else max(0, int(intervalo_segundos))
        )
        fn_executar = executor if executor is not None else VencimentoService.executar_rotina_diaria

        resultados: list[ResultadoExecucaoVencimento] = []
        for tentativa in range(1, limite_retries + 2):
            resultado = fn_executar(
                referencia=referencia,
                cancelador_correspondencias=cancelador_correspondencias,
                tentativa=tentativa,
            )
            resultados.append(resultado)
            if resultado.resultado == ResultadoRotina.SUCESSO:
                break
            if tentativa <= limite_retries:
                sleep_fn(intervalo)
        return tuple(resultados)

    @staticmethod
    def listar_execucoes(
        ator: Usuario,
        *,
        pagina: int = 1,
        por_pagina: int = EXECUCOES_POR_PAGINA,
    ) -> PaginaDoacoes:
        if not AutenticacaoService.possui_funcao(ator, "metricas_e_parametros"):
            raise PermissaoNegada(
                "Apenas Administradores com função métricas e parâmetros podem consultar "
                "execuções da rotina de vencimento."
            )
        qs = ExecucaoVencimento.objects.select_related("execucao_rotina").order_by(
            "-executado_em", "-id"
        )
        paginador = Paginator(qs, por_pagina)
        return PaginaDoacoes(pagina=paginador.get_page(pagina), total_encontrados=paginador.count)


class DoacaoService:
    """Regras de negócio do cadastro, edição, cancelamento e fotos de doação (Specs 08 e 09)."""

    @staticmethod
    def listar_formas_farmaceuticas_ativas() -> list[FormaFarmaceutica]:
        return list(FormaFarmaceutica.objects.filter(ativo=True).order_by("id"))

    @staticmethod
    def listar_pontos_coleta_ativos(*, priorizar_refrigeracao: bool = False) -> list[PontoColeta]:
        pontos = list(
            PontoColeta.objects.filter(status=StatusPontoColeta.ATIVO)
            .select_related("tipo_estabelecimento")
            .order_by("nome_fantasia", "id")
        )
        if priorizar_refrigeracao:
            return RefrigeracaoService.priorizar_pontos_refrigerados(pontos)
        return pontos

    @staticmethod
    def _resolver_localizacao_aproximada(
        doador: Usuario,
        ponto_coleta: PontoColeta | None,
    ) -> tuple[str, str, str, Decimal | None, Decimal | None]:
        if ponto_coleta is not None:
            lat = ponto_coleta.latitude_aprox
            lon = ponto_coleta.longitude_aprox
            if lat is None or lon is None:
                lat, lon = CepService.obter_coordenadas_em_cache(ponto_coleta.cep)
            return (
                ponto_coleta.bairro[:100],
                ponto_coleta.municipio[:100],
                ponto_coleta.estado[:2],
                GeolocalizacaoService.arredondar_coordenada(lat),
                GeolocalizacaoService.arredondar_coordenada(lon),
            )

        endereco = EnderecoUsuario.objects.filter(usuario=doador).first()
        if endereco is None:
            return "", "", "", None, None
        lat = endereco.latitude_aprox
        lon = endereco.longitude_aprox
        if lat is None or lon is None:
            lat, lon = CepService.obter_coordenadas_em_cache(endereco.cep)
        return (
            endereco.bairro[:100],
            endereco.municipio[:100],
            endereco.estado[:2],
            GeolocalizacaoService.arredondar_coordenada(lat),
            GeolocalizacaoService.arredondar_coordenada(lon),
        )

    @staticmethod
    def _validar_dados_comuns(
        dados: DadosDoacao,
        *,
        referencia: date | None = None,
    ) -> tuple[FormaFarmaceutica, PontoColeta | None, str]:
        if not dados.embalagem_integra:
            raise EmbalagemNaoIntegra()
        if dados.controle_especial:
            raise MedicamentoControleEspecialBloqueado()

        nome = (dados.nome_medicamento or "").strip()
        principio = (dados.principio_ativo or "").strip()
        concentracao = (dados.concentracao_dosagem or "").strip()
        fabricante = (dados.fabricante or "").strip()
        lote = (dados.lote or "").strip()
        if not all([nome, principio, concentracao, fabricante, lote]):
            raise RegraNegocioViolada("Campo(s) obrigatório(s) não preenchido(s)")
        if len(nome) > 150:
            raise RegraNegocioViolada("O nome do medicamento deve ter no máximo 150 caracteres.")
        if dados.quantidade is None or int(dados.quantidade) <= 0:
            raise RegraNegocioViolada("A quantidade deve ser um número inteiro maior que zero.")

        if dados.condicao_conservacao not in CondicaoConservacao.values:
            raise RegraNegocioViolada("Selecione uma condição de conservação válida.")

        faixa_temp = ""
        if dados.condicao_conservacao == CondicaoConservacao.REFRIGERADO:
            faixa_temp = RefrigeracaoService.validar_dados_doador(
                dados.faixa_temperatura_bula,
                dados.declaracao_doador_conservacao,
            )

        hoje = referencia if referencia is not None else timezone.localdate()
        if dados.data_validade is None or dados.data_validade < hoje:
            raise ValidadeDoacaoInvalida()
        parametros = VencimentoService.obter_parametros()
        if not VencimentoService.doacao_dentro_da_validade(
            dados.data_validade, referencia=hoje, parametros=parametros
        ):
            raise ValidadeDoacaoInvalida(
                "Não é permitido cadastrar medicamento com validade inferior ao prazo mínimo "
                f"configurado ({parametros.validade_minima_restante_dias} dias). "
                "Faça o descarte conforme a legislação sanitária"
            )

        forma = FormaFarmaceutica.objects.filter(pk=dados.forma_farmaceutica_id, ativo=True).first()
        if forma is None:
            raise RegraNegocioViolada("Selecione uma forma farmacêutica válida.")

        ponto: PontoColeta | None = None
        if dados.ponto_coleta_id is not None:
            ponto = PontoColeta.objects.filter(
                pk=dados.ponto_coleta_id,
                status=StatusPontoColeta.ATIVO,
            ).first()
            if ponto is None:
                raise RegraNegocioViolada("Selecione um ponto de coleta ativo.")

        return forma, ponto, faixa_temp

    @staticmethod
    def _armazenar_foto_privada(
        foto: ArquivoFotoEntrada,
        *,
        scanner: AntimalwareScanner | None = None,
        backend: BackendArmazenamentoPrivado | None = None,
    ) -> ArquivoArmazenado:
        try:
            return ArquivoService.armazenar_privado(
                conteudo=foto.conteudo,
                nome_original=foto.nome_original,
                categoria="doacoes",
                extensoes_permitidas=EXTENSOES_FOTO_DOACAO,
                scanner=scanner,
                backend=backend,
            )
        except ArquivoFormatoInvalido as erro:
            raise FotoDoacaoFormatoInvalido() from erro

    @staticmethod
    def cadastrar(
        usuario: Usuario,
        dados: DadosDoacao,
        fotos: Sequence[ArquivoFotoEntrada],
        *,
        scanner: AntimalwareScanner | None = None,
        backend: BackendArmazenamentoPrivado | None = None,
        referencia: date | None = None,
    ) -> Doacao:
        _validar_usuario_doador_ativo(usuario)
        forma, ponto, faixa_temp = DoacaoService._validar_dados_comuns(dados, referencia=referencia)

        lista_fotos = list(fotos or [])
        if not lista_fotos:
            raise FotoDoacaoObrigatoria()
        if len(lista_fotos) > 2:
            raise RegraNegocioViolada("Envie no máximo 2 fotos da embalagem.")

        armazenadas: list[ArquivoArmazenado] = []
        try:
            for item_foto in lista_fotos:
                armazenadas.append(
                    DoacaoService._armazenar_foto_privada(
                        item_foto, scanner=scanner, backend=backend
                    )
                )

            bairro, municipio, uf, lat, lon = DoacaoService._resolver_localizacao_aproximada(
                usuario, ponto
            )
            agora = timezone.now()

            with transaction.atomic():
                doacao = Doacao.objects.create(
                    doador=usuario,
                    nome_medicamento=dados.nome_medicamento.strip()[:150],
                    principio_ativo=dados.principio_ativo.strip()[:150],
                    concentracao_dosagem=dados.concentracao_dosagem.strip()[:80],
                    forma_farmaceutica=forma,
                    quantidade_inicial=int(dados.quantidade),
                    quantidade_disponivel=int(dados.quantidade),
                    fabricante=dados.fabricante.strip()[:120],
                    lote=dados.lote.strip()[:60],
                    data_validade=dados.data_validade,
                    embalagem_integra=True,
                    condicao_conservacao=dados.condicao_conservacao,
                    sujeito_receita=bool(dados.sujeito_receita),
                    ponto_coleta=ponto,
                    observacoes=(dados.observacoes or "").strip(),
                    status=StatusDoacao.EM_ANALISE,
                    regiao_bairro=bairro,
                    regiao_municipio=municipio,
                    regiao_uf=uf,
                    latitude_aprox=lat,
                    longitude_aprox=lon,
                )

                if doacao.condicao_conservacao == CondicaoConservacao.REFRIGERADO:
                    DadosRefrigeracaoDoacao.objects.create(
                        doacao=doacao,
                        faixa_temperatura_bula=faixa_temp,
                        declaracao_doador_conservacao=True,
                        declaracao_doador_em=agora,
                    )

                for ordem, arq in enumerate(armazenadas, start=1):
                    foto_obj = FotoDoacao.objects.create(
                        doacao=doacao,
                        ordem=ordem,
                        arquivo_chave=arq.chave,
                        mime_verificado=arq.mime_verificado,
                        tamanho_bytes=arq.tamanho_bytes,
                    )
                    AuditoriaService.registrar(
                        acao="arquivo.enviado",
                        entidade_tipo="foto_doacao",
                        entidade_id=foto_obj.pk,
                        ator=usuario,
                        detalhes={
                            "doacao_id": doacao.pk,
                            "ordem": ordem,
                            "mime_verificado": arq.mime_verificado,
                            "tamanho_bytes": arq.tamanho_bytes,
                        },
                    )

                AuditoriaService.registrar(
                    acao="doacao.cadastrada",
                    entidade_tipo="doacao",
                    entidade_id=doacao.pk,
                    ator=usuario,
                    detalhes={
                        "forma_farmaceutica_id": forma.pk,
                        "quantidade": doacao.quantidade_inicial,
                        "refrigerado": (
                            doacao.condicao_conservacao == CondicaoConservacao.REFRIGERADO
                        ),
                        "sujeito_receita": doacao.sujeito_receita,
                        "qtd_fotos": len(armazenadas),
                        "status": doacao.status,
                    },
                )
                return doacao
        except Exception:
            for arq in armazenadas:
                ArquivoService.remover_silencioso(arq.chave, backend=backend)
            raise

    @staticmethod
    def obter_para_doador(doacao_id: int, usuario: Usuario) -> Doacao:
        _validar_usuario_doador_ativo(usuario)
        doacao = (
            Doacao.objects.select_related(
                "forma_farmaceutica", "ponto_coleta", "dados_refrigeracao"
            )
            .prefetch_related("fotos")
            .filter(pk=doacao_id, doador=usuario)
            .first()
        )
        if doacao is None:
            raise RecursoNaoEncontrado("Doação não encontrada.")
        return doacao

    @staticmethod
    def listar_do_doador(
        usuario: Usuario,
        filtros: FiltrosMinhasDoacoes | None = None,
        *,
        pagina: int = 1,
        por_pagina: int = DOACOES_POR_PAGINA,
    ) -> PaginaDoacoes:
        _validar_usuario_doador_ativo(usuario)
        f = filtros if filtros is not None else FiltrosMinhasDoacoes()
        qs = (
            Doacao.objects.filter(doador=usuario)
            .select_related("forma_farmaceutica", "ponto_coleta", "dados_refrigeracao")
            .prefetch_related("fotos", "conferencias")
            .order_by("-criado_em", "-id")
        )
        termo = (f.termo or "").strip()
        if termo:
            qs = qs.filter(
                Q(nome_medicamento__icontains=termo) | Q(principio_ativo__icontains=termo)
            )
        if f.status and f.status in StatusDoacao.values:
            qs = qs.filter(status=f.status)
        if f.data_inicio is not None:
            inicio_dt = timezone.make_aware(datetime.combine(f.data_inicio, time.min))
            qs = qs.filter(criado_em__gte=inicio_dt)
        if f.data_fim is not None:
            fim_dt = timezone.make_aware(datetime.combine(f.data_fim, time.max))
            qs = qs.filter(criado_em__lte=fim_dt)

        paginador = Paginator(qs, por_pagina)
        return PaginaDoacoes(pagina=paginador.get_page(pagina), total_encontrados=paginador.count)

    @staticmethod
    def atualizar(
        doacao_id: int,
        usuario: Usuario,
        dados: DadosDoacao,
        *,
        fotos_novas: Mapping[int, ArquivoFotoEntrada] | None = None,
        scanner: AntimalwareScanner | None = None,
        backend: BackendArmazenamentoPrivado | None = None,
        referencia: date | None = None,
    ) -> ResultadoAtualizacaoDoacao:
        _validar_usuario_doador_ativo(usuario)
        forma, ponto, faixa_temp = DoacaoService._validar_dados_comuns(dados, referencia=referencia)

        mapa_fotos_entrada = dict(fotos_novas or {})
        for ordem in mapa_fotos_entrada:
            if ordem not in {1, 2}:
                raise RegraNegocioViolada("Posição de foto inválida.")

        fotos_armazenadas: dict[int, ArquivoArmazenado] = {}
        try:
            for ordem, item_foto in sorted(mapa_fotos_entrada.items()):
                fotos_armazenadas[ordem] = DoacaoService._armazenar_foto_privada(
                    item_foto, scanner=scanner, backend=backend
                )

            with transaction.atomic():
                doacao = (
                    Doacao.objects.select_for_update().filter(pk=doacao_id, doador=usuario).first()
                )
                if doacao is None:
                    raise RecursoNaoEncontrado("Doação não encontrada.")

                if doacao.status == StatusDoacao.VENCIDO:
                    raise DoacaoVencidaIrreversivel()
                if doacao.status not in {StatusDoacao.EM_ANALISE, StatusDoacao.DISPONIVEL}:
                    raise RegraNegocioViolada(
                        "Apenas doações em análise ou disponíveis podem ser alteradas."
                    )

                ponto_novo_id = ponto.pk if ponto is not None else None
                novos_valores = {
                    "nome_medicamento": dados.nome_medicamento.strip()[:150],
                    "principio_ativo": dados.principio_ativo.strip()[:150],
                    "concentracao_dosagem": dados.concentracao_dosagem.strip()[:80],
                    "forma_farmaceutica_id": forma.pk,
                    "quantidade_inicial": int(dados.quantidade),
                    "fabricante": dados.fabricante.strip()[:120],
                    "lote": dados.lote.strip()[:60],
                    "data_validade": dados.data_validade,
                    "condicao_conservacao": dados.condicao_conservacao,
                    "sujeito_receita": bool(dados.sujeito_receita),
                    "ponto_coleta_id": ponto_novo_id,
                    "observacoes": (dados.observacoes or "").strip(),
                }
                campos_criticos = {
                    "nome_medicamento",
                    "principio_ativo",
                    "concentracao_dosagem",
                    "forma_farmaceutica_id",
                    "quantidade_inicial",
                    "fabricante",
                    "lote",
                    "data_validade",
                    "condicao_conservacao",
                    "sujeito_receita",
                }

                conservacao_anterior = doacao.condicao_conservacao
                campos_alterados: list[str] = []
                for campo, novo_valor in novos_valores.items():
                    if getattr(doacao, campo) != novo_valor:
                        setattr(doacao, campo, novo_valor)
                        campos_alterados.append(campo)

                if "quantidade_inicial" in campos_alterados:
                    doacao.quantidade_disponivel = doacao.quantidade_inicial
                if "data_validade" in campos_alterados:
                    doacao.aviso_vencimento_enviado_em = None
                if "ponto_coleta_id" in campos_alterados:
                    bairro, municipio, uf, lat, lon = (
                        DoacaoService._resolver_localizacao_aproximada(usuario, ponto)
                    )
                    doacao.regiao_bairro = bairro
                    doacao.regiao_municipio = municipio
                    doacao.regiao_uf = uf
                    doacao.latitude_aprox = lat
                    doacao.longitude_aprox = lon

                # Gestão da transição de refrigeração na mesma transação (Spec 09).
                mudanca_critica = bool(campos_criticos.intersection(campos_alterados))
                refrig_existente = DadosRefrigeracaoDoacao.objects.filter(doacao=doacao).first()
                if doacao.condicao_conservacao == CondicaoConservacao.REFRIGERADO:
                    agora = timezone.now()
                    if refrig_existente is None:
                        DadosRefrigeracaoDoacao.objects.create(
                            doacao=doacao,
                            faixa_temperatura_bula=faixa_temp,
                            declaracao_doador_conservacao=True,
                            declaracao_doador_em=agora,
                        )
                        campos_alterados.append("dados_refrigeracao")
                        mudanca_critica = True
                    elif refrig_existente.faixa_temperatura_bula != faixa_temp:
                        refrig_existente.faixa_temperatura_bula = faixa_temp
                        refrig_existente.declaracao_doador_em = agora
                        refrig_existente.save(
                            update_fields=["faixa_temperatura_bula", "declaracao_doador_em"]
                        )
                        campos_alterados.append("faixa_temperatura_bula")
                        mudanca_critica = True
                elif (
                    conservacao_anterior == CondicaoConservacao.REFRIGERADO
                    or refrig_existente is not None
                ):
                    DadosRefrigeracaoDoacao.objects.filter(doacao=doacao).delete()
                    if "dados_refrigeracao" not in campos_alterados:
                        campos_alterados.append("dados_refrigeracao")
                    mudanca_critica = True

                # Substituição ou adição de fotos (1 ou 2); remove arquivo antigo em on_commit.
                chaves_antigas_remover: list[str] = []
                for ordem, arq in sorted(fotos_armazenadas.items()):
                    foto_atual = FotoDoacao.objects.filter(doacao=doacao, ordem=ordem).first()
                    if foto_atual is not None:
                        chaves_antigas_remover.append(foto_atual.arquivo_chave)
                        foto_atual.arquivo_chave = arq.chave
                        foto_atual.mime_verificado = arq.mime_verificado
                        foto_atual.tamanho_bytes = arq.tamanho_bytes
                        foto_atual.save(
                            update_fields=["arquivo_chave", "mime_verificado", "tamanho_bytes"]
                        )
                        foto_obj = foto_atual
                    else:
                        foto_obj = FotoDoacao.objects.create(
                            doacao=doacao,
                            ordem=ordem,
                            arquivo_chave=arq.chave,
                            mime_verificado=arq.mime_verificado,
                            tamanho_bytes=arq.tamanho_bytes,
                        )
                    campos_alterados.append(f"foto_{ordem}")
                    mudanca_critica = True
                    AuditoriaService.registrar(
                        acao="arquivo.enviado",
                        entidade_tipo="foto_doacao",
                        entidade_id=foto_obj.pk,
                        ator=usuario,
                        detalhes={
                            "doacao_id": doacao.pk,
                            "ordem": ordem,
                            "mime_verificado": arq.mime_verificado,
                            "tamanho_bytes": arq.tamanho_bytes,
                        },
                    )

                remetida_reanalise = False
                if doacao.status == StatusDoacao.DISPONIVEL and mudanca_critica:
                    doacao.status = StatusDoacao.EM_ANALISE
                    remetida_reanalise = True

                doacao.save()

                AuditoriaService.registrar(
                    acao="doacao.alterada",
                    entidade_tipo="doacao",
                    entidade_id=doacao.pk,
                    ator=usuario,
                    detalhes={
                        "campos_alterados": sorted(set(campos_alterados)),
                        "remetida_reanalise": remetida_reanalise,
                        "status": doacao.status,
                    },
                )

                for chave_antiga in chaves_antigas_remover:
                    transaction.on_commit(
                        lambda c=chave_antiga: ArquivoService.remover_silencioso(c, backend=backend)
                    )

                return ResultadoAtualizacaoDoacao(
                    doacao=doacao,
                    campos_alterados=tuple(sorted(set(campos_alterados))),
                    remetida_reanalise=remetida_reanalise,
                )
        except Exception:
            for arq in fotos_armazenadas.values():
                ArquivoService.remover_silencioso(arq.chave, backend=backend)
            raise

    @staticmethod
    def cancelar(
        doacao_id: int,
        usuario: Usuario,
        *,
        cancelador_correspondencias: Callable[..., ResultadoCancelamentoCorrespondencia]
        | None = None,
    ) -> Doacao:
        _validar_usuario_doador_ativo(usuario)
        cancelador = (
            cancelador_correspondencias
            if cancelador_correspondencias is not None
            else _cancelar_correspondencias_noop
        )
        with transaction.atomic():
            doacao = Doacao.objects.select_for_update().filter(pk=doacao_id, doador=usuario).first()
            if doacao is None:
                raise RecursoNaoEncontrado("Doação não encontrada.")

            if doacao.status in {
                StatusDoacao.ENTREGUE,
                StatusDoacao.VENCIDO,
                StatusDoacao.CANCELADO,
            }:
                raise RegraNegocioViolada("Esta doação não pode ser cancelada no status atual.")

            status_anterior = doacao.status
            doacao.status = StatusDoacao.CANCELADO
            doacao.save(update_fields=["status", "atualizado_em"])

            cancelamento = cancelador(doacao, motivo="Cancelamento voluntário pelo doador.")
            rotulo = _rotulo_medicamento_notificacao(doacao)
            for solicitante in cancelamento.solicitantes_notificar:
                if solicitante.anonimizado_em is None:
                    NotificacaoService.registrar_evento(
                        destinatario=solicitante,
                        tipo=TipoNotificacao.AGENDAMENTO_CANCELADO,
                        contexto={"medicamento": rotulo},
                        url_destino="/notificacoes/",
                    )

            AuditoriaService.registrar(
                acao="doacao.cancelada",
                entidade_tipo="doacao",
                entidade_id=doacao.pk,
                ator=usuario,
                detalhes={
                    "status_anterior": status_anterior,
                    "status_novo": doacao.status,
                    "cancelamentos_vinculados": cancelamento.cancelados,
                },
            )
            return doacao

    @staticmethod
    def cancelar_doacoes_abertas_no_encerramento(usuario: Usuario) -> int:
        """Cancela doações abertas (em_analise/disponivel) no encerramento LGPD da conta."""
        doacoes = list(
            Doacao.objects.select_for_update()
            .filter(
                doador=usuario,
                status__in=(StatusDoacao.EM_ANALISE, StatusDoacao.DISPONIVEL),
            )
            .order_by("id")
        )
        for doacao in doacoes:
            status_anterior = doacao.status
            doacao.status = StatusDoacao.CANCELADO
            doacao.save(update_fields=["status", "atualizado_em"])
            AuditoriaService.registrar(
                acao="doacao.cancelada",
                entidade_tipo="doacao",
                entidade_id=doacao.pk,
                ator=usuario,
                motivo="Encerramento de conta pelo usuário",
                detalhes={
                    "status_anterior": status_anterior,
                    "status_novo": StatusDoacao.CANCELADO,
                },
            )
        return len(doacoes)

    @staticmethod
    def gerar_acesso_foto(
        foto_id: int,
        ator: Usuario,
        *,
        sessao_2fa_verificado: bool = False,
        verificador_solicitante_vinculado: Callable[[Doacao, Usuario], bool] | None = None,
        backend: BackendArmazenamentoPrivado | None = None,
    ) -> str:
        foto = FotoDoacao.objects.select_related("doacao").filter(pk=foto_id).first()
        if foto is None:
            raise RecursoNaoEncontrado("Foto da doação não encontrada.")

        eh_dono = foto.doacao.doador_id == ator.pk
        eh_conferente = (
            AutenticacaoService.possui_funcao(ator, "conferencia_doacoes") and sessao_2fa_verificado
        )
        verificar_solicitante = (
            verificador_solicitante_vinculado
            if verificador_solicitante_vinculado is not None
            else _verificar_solicitante_vinculado_noop
        )
        eh_solicitante_vinculado = (
            not eh_dono and not eh_conferente and verificar_solicitante(foto.doacao, ator)
        )

        if not (eh_dono or eh_conferente or eh_solicitante_vinculado):
            raise RecursoNaoEncontrado("Foto da doação não encontrada.")

        ext = foto.arquivo_chave.rsplit(".", 1)[-1].lower()
        url = ArquivoService.gerar_url_temporaria(
            foto.arquivo_chave,
            usuario_id=ator.pk,
            mime_verificado=foto.mime_verificado,
            nome_download=f"doacao_{foto.doacao_id}_foto_{foto.ordem}.{ext}",
            backend=backend,
        )
        AuditoriaService.registrar(
            acao="arquivo.acessado",
            entidade_tipo="foto_doacao",
            entidade_id=foto.pk,
            ator=ator,
            detalhes={"doacao_id": foto.doacao_id, "ordem": foto.ordem},
        )
        return url


class ConferenciaDoacaoService:
    """Fila e registro de conferência de validade/integridade pelo Administrador (Spec 10)."""

    @staticmethod
    def _exigir_conferencia(ator: Usuario) -> None:
        if not AutenticacaoService.possui_funcao(ator, "conferencia_doacoes"):
            raise PermissaoNegada(
                "Apenas Administradores com função conferência de doações podem acessar "
                "este recurso."
            )

    @staticmethod
    def listar_pendentes(
        ator: Usuario,
        filtros: FiltrosConferenciaAdmin | None = None,
        *,
        pagina: int = 1,
        por_pagina: int = CONFERENCIAS_POR_PAGINA,
    ) -> PaginaDoacoes:
        ConferenciaDoacaoService._exigir_conferencia(ator)
        f = filtros if filtros is not None else FiltrosConferenciaAdmin()
        qs = (
            Doacao.objects.filter(status=StatusDoacao.EM_ANALISE)
            .select_related("forma_farmaceutica", "dados_refrigeracao")
            .order_by("data_validade", "criado_em", "id")
        )
        termo = (f.termo or "").strip()
        if termo:
            qs = qs.filter(
                Q(nome_medicamento__icontains=termo) | Q(principio_ativo__icontains=termo)
            )
        if f.condicao_conservacao in CondicaoConservacao.values:
            qs = qs.filter(condicao_conservacao=f.condicao_conservacao)
        if f.sujeito_receita == "sim":
            qs = qs.filter(sujeito_receita=True)
        elif f.sujeito_receita == "nao":
            qs = qs.filter(sujeito_receita=False)
        if f.data_inicio is not None:
            inicio_dt = timezone.make_aware(datetime.combine(f.data_inicio, time.min))
            qs = qs.filter(criado_em__gte=inicio_dt)
        if f.data_fim is not None:
            fim_dt = timezone.make_aware(datetime.combine(f.data_fim, time.max))
            qs = qs.filter(criado_em__lte=fim_dt)

        paginador = Paginator(qs, por_pagina)
        return PaginaDoacoes(pagina=paginador.get_page(pagina), total_encontrados=paginador.count)

    @staticmethod
    def obter_detalhe(
        ator: Usuario,
        doacao_id: int,
        *,
        referencia: date | None = None,
    ) -> DetalheConferenciaDoacao:
        ConferenciaDoacaoService._exigir_conferencia(ator)
        doacao = (
            Doacao.objects.select_related(
                "forma_farmaceutica",
                "ponto_coleta",
                "dados_refrigeracao",
            )
            .prefetch_related("fotos")
            .filter(pk=doacao_id)
            .first()
        )
        if doacao is None:
            raise RecursoNaoEncontrado("Doação não encontrada.")

        parametros = VencimentoService.obter_parametros()
        dentro_validade = VencimentoService.doacao_dentro_da_validade(
            doacao, referencia=referencia, parametros=parametros
        )
        conferencias = tuple(
            ConferenciaDoacao.objects.filter(doacao=doacao)
            .select_related("responsavel")
            .order_by("-conferido_em", "-id")
        )
        try:
            dados_refrig = doacao.dados_refrigeracao
        except DadosRefrigeracaoDoacao.DoesNotExist:
            dados_refrig = None

        return DetalheConferenciaDoacao(
            doacao=doacao,
            fotos=tuple(doacao.fotos.all()),
            dados_refrigeracao=dados_refrig,
            conferencias=conferencias,
            dentro_validade_minima=dentro_validade,
            validade_minima_dias=parametros.validade_minima_restante_dias,
            checklist_orientativo=CHECKLIST_ORIENTATIVO_CONFERENCIA,
            motivos_orientativos=MOTIVOS_ORIENTATIVOS_REPROVACAO,
        )

    @staticmethod
    def registrar_conferencia(
        ator: Usuario,
        doacao_id: int,
        resultado: str,
        motivo: str = "",
        *,
        referencia: date | None = None,
        acionador_correspondencia: Callable[[Doacao], None] | None = None,
    ) -> ConferenciaDoacao:
        ConferenciaDoacaoService._exigir_conferencia(ator)
        if resultado not in ResultadoConferenciaDoacao.values:
            raise RegraNegocioViolada("Resultado de conferência inválido.")

        motivo_limpo = (motivo or "").strip()
        if resultado == ResultadoConferenciaDoacao.REPROVADA and not motivo_limpo:
            raise MotivoReprovacaoObrigatorio()

        parametros = VencimentoService.obter_parametros()
        acionar_corr = (
            acionador_correspondencia
            if acionador_correspondencia is not None
            else _acionar_correspondencia_noop
        )

        with transaction.atomic():
            doacao = (
                Doacao.objects.select_for_update()
                .select_related("doador")
                .filter(pk=doacao_id)
                .first()
            )
            if doacao is None:
                raise RecursoNaoEncontrado("Doação não encontrada.")

            if doacao.status == StatusDoacao.VENCIDO:
                raise DoacaoVencidaIrreversivel()
            if doacao.status != StatusDoacao.EM_ANALISE:
                raise ConflitoConcorrencia(
                    "Esta doação não está mais em análise e já foi processada."
                )

            if resultado == ResultadoConferenciaDoacao.APROVADA:
                if not VencimentoService.doacao_dentro_da_validade(
                    doacao, referencia=referencia, parametros=parametros
                ):
                    raise ValidadeDoacaoInvalida(
                        "A doação está vencida ou abaixo da validade mínima restante configurada "
                        "e não pode ser aprovada"
                    )
                doacao.status = StatusDoacao.DISPONIVEL
                acao_auditoria = "doacao.aprovada"
                texto_resultado = "aprovada e disponível na plataforma"
            else:
                doacao.status = StatusDoacao.REPROVADO
                acao_auditoria = "doacao.reprovada"
                texto_resultado = f"reprovada. Motivo: {motivo_limpo}"

            doacao.save(update_fields=["status", "atualizado_em"])

            conferencia = ConferenciaDoacao.objects.create(
                doacao=doacao,
                resultado=resultado,
                motivo=motivo_limpo,
                responsavel=ator,
            )

            AuditoriaService.registrar(
                acao=acao_auditoria,
                entidade_tipo="doacao",
                entidade_id=doacao.pk,
                ator=ator,
                motivo=motivo_limpo,
                detalhes={
                    "conferencia_id": conferencia.pk,
                    "resultado": resultado,
                    "status_novo": doacao.status,
                },
            )

            if doacao.doador.anonimizado_em is None:
                NotificacaoService.registrar_evento(
                    destinatario=doacao.doador,
                    tipo=TipoNotificacao.DOACAO_CONFERIDA,
                    contexto={
                        "medicamento": _rotulo_medicamento_notificacao(doacao),
                        "resultado": texto_resultado,
                    },
                    url_destino="/doacoes/minhas/",
                )

            if resultado == ResultadoConferenciaDoacao.APROVADA:
                acionar_corr(doacao)

            return conferencia

    @staticmethod
    def marcar_vencida_na_conferencia(
        ator: Usuario,
        doacao_id: int,
        *,
        referencia: date | None = None,
    ) -> Doacao:
        """Transição direta para vencido na fila quando abaixo da validade mínima (RN-10-03)."""
        ConferenciaDoacaoService._exigir_conferencia(ator)
        parametros = VencimentoService.obter_parametros()

        with transaction.atomic():
            doacao = (
                Doacao.objects.select_for_update()
                .select_related("doador")
                .filter(pk=doacao_id)
                .first()
            )
            if doacao is None:
                raise RecursoNaoEncontrado("Doação não encontrada.")
            if doacao.status != StatusDoacao.EM_ANALISE:
                raise ConflitoConcorrencia(
                    "Esta doação não está mais em análise e já foi processada."
                )
            if VencimentoService.doacao_dentro_da_validade(
                doacao, referencia=referencia, parametros=parametros
            ):
                raise RegraNegocioViolada(
                    "A doação ainda está dentro da validade mínima restante configurada."
                )

            doacao.status = StatusDoacao.VENCIDO
            doacao.save(update_fields=["status", "atualizado_em"])

            AuditoriaService.registrar(
                acao="doacao.vencida_conferencia",
                entidade_tipo="doacao",
                entidade_id=doacao.pk,
                ator=ator,
                detalhes={"status_anterior": StatusDoacao.EM_ANALISE, "status_novo": doacao.status},
            )

            if doacao.doador.anonimizado_em is None:
                NotificacaoService.registrar_evento(
                    destinatario=doacao.doador,
                    tipo=TipoNotificacao.DOACAO_VENCIDA,
                    contexto={"medicamento": _rotulo_medicamento_notificacao(doacao)},
                    url_destino="/doacoes/minhas/",
                )
            return doacao


class BuscaMedicamentoService:
    """Busca pública/autenticada de medicamentos disponíveis por proximidade (Spec 14 / RF015)."""

    @staticmethod
    def buscar(
        filtros: FiltrosBuscaMedicamento | None = None,
        localizacao: LocalizacaoBuscaSessao | None = None,
        *,
        pagina: int = 1,
        por_pagina: int = BUSCA_POR_PAGINA,
        referencia: date | None = None,
    ) -> PaginaBuscaMedicamentos:
        f = filtros if filtros is not None else FiltrosBuscaMedicamento()
        hoje = referencia if referencia is not None else timezone.localdate()
        data_corte = VencimentoService.calcular_data_corte(hoje)

        qs = (
            Doacao.objects.select_related("forma_farmaceutica")
            .only(
                "id",
                "nome_medicamento",
                "principio_ativo",
                "concentracao_dosagem",
                "forma_farmaceutica__nome",
                "quantidade_disponivel",
                "data_validade",
                "condicao_conservacao",
                "sujeito_receita",
                "regiao_bairro",
                "regiao_municipio",
                "regiao_uf",
                "latitude_aprox",
                "longitude_aprox",
                "criado_em",
            )
            .filter(
                status=StatusDoacao.DISPONIVEL,
                quantidade_disponivel__gt=0,
                doador__status=StatusUsuario.ATIVO,
                data_validade__gte=data_corte,
            )
        )

        termo = (f.termo or "").strip()
        if termo:
            qs = qs.filter(
                Q(nome_medicamento__icontains=termo) | Q(principio_ativo__icontains=termo)
            )
        if f.forma_farmaceutica_id is not None:
            qs = qs.filter(forma_farmaceutica_id=f.forma_farmaceutica_id)
        concentracao = (f.concentracao or "").strip()
        if concentracao:
            qs = qs.filter(concentracao_dosagem__icontains=concentracao)
        if f.validade_minima is not None:
            qs = qs.filter(data_validade__gte=f.validade_minima)
        if f.condicao_conservacao in CondicaoConservacao.values:
            qs = qs.filter(condicao_conservacao=f.condicao_conservacao)

        if localizacao is not None:
            if f.distancia_max_km is not None and f.distancia_max_km > 0:
                bbox = GeolocalizacaoService.calcular_bounding_box(
                    localizacao.latitude_aprox,
                    localizacao.longitude_aprox,
                    float(f.distancia_max_km),
                )
                qs = qs.filter(
                    latitude_aprox__isnull=False,
                    longitude_aprox__isnull=False,
                    latitude_aprox__gte=bbox.lat_min,
                    latitude_aprox__lte=bbox.lat_max,
                    longitude_aprox__gte=bbox.lon_min,
                    longitude_aprox__lte=bbox.lon_max,
                )

            candidatos: list[tuple[bool, float, float, int, ItemBuscaMedicamento]] = []
            for doacao in qs:
                dist_km: float | None = None
                faixa = ""
                if doacao.latitude_aprox is not None and doacao.longitude_aprox is not None:
                    dist_km = GeolocalizacaoService.calcular_distancia_haversine_km(
                        localizacao.latitude_aprox,
                        localizacao.longitude_aprox,
                        doacao.latitude_aprox,
                        doacao.longitude_aprox,
                    )
                    if (
                        f.distancia_max_km is not None
                        and f.distancia_max_km > 0
                        and dist_km > float(f.distancia_max_km)
                    ):
                        continue
                    faixa = GeolocalizacaoService.formatar_faixa_distancia(dist_km)
                elif f.distancia_max_km is not None and f.distancia_max_km > 0:
                    continue

                item = ItemBuscaMedicamento(
                    id=doacao.pk,
                    nome_medicamento=doacao.nome_medicamento,
                    principio_ativo=doacao.principio_ativo,
                    concentracao_dosagem=doacao.concentracao_dosagem,
                    forma_farmaceutica_nome=doacao.forma_farmaceutica.nome,
                    quantidade_disponivel=doacao.quantidade_disponivel,
                    data_validade=doacao.data_validade,
                    condicao_conservacao=doacao.condicao_conservacao,
                    condicao_conservacao_display=doacao.get_condicao_conservacao_display(),
                    sujeito_receita=doacao.sujeito_receita,
                    regiao_aproximada=_formatar_regiao_aproximada(
                        doacao.regiao_bairro, doacao.regiao_municipio, doacao.regiao_uf
                    ),
                    faixa_distancia=faixa,
                )
                candidatos.append(
                    (
                        dist_km is None,
                        dist_km if dist_km is not None else float("inf"),
                        -doacao.criado_em.timestamp(),
                        -doacao.pk,
                        item,
                    )
                )

            candidatos.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
            itens_ordenados = [c[4] for c in candidatos]
            paginador = Paginator(itens_ordenados, por_pagina)
            return PaginaBuscaMedicamentos(
                pagina=paginador.get_page(pagina),
                total_encontrados=paginador.count,
                ordenado_por_proximidade=True,
            )

        qs_ordenado = qs.order_by("-criado_em", "-id")
        paginador = Paginator(qs_ordenado, por_pagina)
        page_obj = paginador.get_page(pagina)
        page_obj.object_list = [
            ItemBuscaMedicamento(
                id=doacao.pk,
                nome_medicamento=doacao.nome_medicamento,
                principio_ativo=doacao.principio_ativo,
                concentracao_dosagem=doacao.concentracao_dosagem,
                forma_farmaceutica_nome=doacao.forma_farmaceutica.nome,
                quantidade_disponivel=doacao.quantidade_disponivel,
                data_validade=doacao.data_validade,
                condicao_conservacao=doacao.condicao_conservacao,
                condicao_conservacao_display=doacao.get_condicao_conservacao_display(),
                sujeito_receita=doacao.sujeito_receita,
                regiao_aproximada=_formatar_regiao_aproximada(
                    doacao.regiao_bairro, doacao.regiao_municipio, doacao.regiao_uf
                ),
                faixa_distancia="",
            )
            for doacao in page_obj.object_list
        ]
        return PaginaBuscaMedicamentos(
            pagina=page_obj,
            total_encontrados=paginador.count,
            ordenado_por_proximidade=False,
        )
