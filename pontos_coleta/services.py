"""Camada de services do app pontos_coleta (Specs 05, 06 e 07 — RF005, RF006 e RF007)."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.paginator import Page, Paginator
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from auditoria.services import AuditoriaService
from contas.models import StatusUsuario, Usuario
from contas.services import AutenticacaoService, buscar_usuario_por_identificador
from notificacoes.models import TipoNotificacao
from notificacoes.services import NotificacaoService
from nucleo.arquivos import (
    AntimalwareScanner,
    ArquivoService,
    BackendArmazenamentoPrivado,
)
from nucleo.exceptions import PermissaoNegada, RecursoNaoEncontrado, RegraNegocioViolada
from nucleo.models import TipoDocumentoPonto, TipoEstabelecimento
from nucleo.services import CepService
from nucleo.validators import (
    formatar_cnpj,
    mascarar_cpf,
    normalizar_email,
    somente_digitos,
    validar_cep,
    validar_cnpj,
    validar_telefone,
    validar_uf,
)
from pontos_coleta.exceptions import (
    CnpjJaCadastrado,
    DocumentosObrigatoriosPendentes,
    DocumentoVencido,
    HorarioInvalido,
    MotivoAnaliseObrigatorio,
    UltimoResponsavelAtivo,
)
from pontos_coleta.models import (
    AnalisePontoColeta,
    DocumentoPontoColeta,
    HorarioFuncionamentoPonto,
    PontoColeta,
    PontoColetaResponsavel,
    ResultadoAnalisePonto,
    StatusDocumentoPonto,
    StatusPontoColeta,
    StatusResponsavelPonto,
    TipoAcaoAnalisePonto,
)

PONTOS_POR_PAGINA = 20

# Checklist orientativo não bloqueante (Spec 07 / RN-07-02 — Questão 10 do PRD em aberto).
CHECKLIST_ORIENTATIVO_APROVACAO: tuple[str, ...] = (
    "Conferir se o CNPJ está ativo e compatível com a razão social e o nome fantasia informados.",
    "Verificar se licença de funcionamento e alvará sanitário estão legíveis e válidos.",
    "Conferir se o endereço público e os horários de retirada estão coerentes com o local.",
)


@dataclass(frozen=True)
class ItemHorario:
    dia_semana: int
    hora_abertura: time
    hora_fechamento: time


@dataclass(frozen=True)
class DadosPontoColeta:
    cnpj: str
    razao_social: str
    nome_fantasia: str
    tipo_estabelecimento_id: int
    email: str
    telefone: str
    possui_refrigeracao: bool
    observacoes: str
    cep: str
    logradouro: str
    numero: str
    bairro: str
    municipio: str
    estado: str
    complemento: str = ""


@dataclass(frozen=True)
class DadosAtualizacaoPonto:
    razao_social: str
    nome_fantasia: str
    tipo_estabelecimento_id: int
    email: str
    telefone: str
    possui_refrigeracao: bool
    observacoes: str
    cep: str
    logradouro: str
    numero: str
    bairro: str
    municipio: str
    estado: str
    complemento: str = ""


@dataclass(frozen=True)
class ResultadoAtualizacaoPonto:
    ponto: PontoColeta
    campos_alterados: tuple[str, ...]
    remetido_reaprovacao: bool


@dataclass(frozen=True)
class FiltrosPontoColeta:
    termo: str = ""
    cnpj: str = ""
    tipo_estabelecimento_id: int | None = None
    municipio: str = ""
    status: str = ""
    revisao_vencida: bool = False


@dataclass(frozen=True)
class PaginaPontosColeta:
    pagina: Page
    total_encontrados: int


@dataclass(frozen=True)
class ResumoResponsavelPonto:
    id: int
    usuario_id: int
    nome_completo: str
    cpf_mascarado: str
    email: str
    status: str
    status_display: str
    vinculado_em: datetime


@dataclass(frozen=True)
class ItemDocumentoObrigatorio:
    tipo: TipoDocumentoPonto
    ultima_versao: DocumentoPontoColeta | None
    enviado_e_valido: bool
    aprovado_e_valido: bool


@dataclass(frozen=True)
class SituacaoDocumentosObrigatorios:
    itens: tuple[ItemDocumentoObrigatorio, ...]
    todos_enviados_validos: bool
    todos_aprovados_validos: bool


@dataclass(frozen=True)
class ResumoMeusPontos:
    pontos: tuple[
        tuple[PontoColeta, SituacaoDocumentosObrigatorios, AnalisePontoColeta | None], ...
    ]
    convites_pendentes: tuple[PontoColetaResponsavel, ...]


@dataclass(frozen=True)
class FiltrosDocumentosAdmin:
    ponto_coleta_id: int | None = None
    tipo_documento_id: int | None = None
    status: str = ""
    validade_ate: date | None = None


@dataclass(frozen=True)
class PaginaDocumentosAdmin:
    pagina: Page
    total_encontrados: int


@dataclass(frozen=True)
class ResultadoVencimentoDocumentos:
    avisos_enviados: int
    documentos_vencidos: int
    pontos_remetidos_reaprovacao: int


@dataclass(frozen=True)
class DetalhePontoAdmin:
    ponto: PontoColeta
    cnpj_formatado: str
    horarios: tuple[HorarioFuncionamentoPonto, ...]
    responsaveis: tuple[ResumoResponsavelPonto, ...]
    documentos: tuple[DocumentoPontoColeta, ...]
    situacao_docs: SituacaoDocumentosObrigatorios
    analises: tuple[AnalisePontoColeta, ...]
    revisao_vencida: bool
    checklist_orientativo: tuple[str, ...]


def _cancelar_agendamentos_futuros_noop(ponto: PontoColeta, *, motivo: str) -> None:
    """Gancho padrão até o app correspondencias existir.

    TODO(Spec 16 — RF018): cancelar transacionalmente agendamentos futuros confirmados ou
    propostos vinculados a `ponto` sob select_for_update() na ordem fixa da ADR 0013,
    mantendo a correspondência aceita/reservada, reiniciando o prazo de expiração da
    reserva (REMED_RESERVA_EXPIRACAO_HORAS) a partir do cancelamento automático e
    notificando ambas as partes via NotificacaoService.
    """
    _ = (ponto, motivo)


def _validar_horarios(horarios: list[ItemHorario] | tuple[ItemHorario, ...]) -> list[ItemHorario]:
    if not horarios:
        raise HorarioInvalido("Informe ao menos um dia e horário de funcionamento para retirada.")

    por_dia: dict[int, list[ItemHorario]] = defaultdict(list)
    for item in horarios:
        if item.dia_semana < 0 or item.dia_semana > 6:
            raise HorarioInvalido("Dia da semana inválido.")
        if item.hora_abertura >= item.hora_fechamento:
            raise HorarioInvalido(
                "O horário de abertura deve ser anterior ao horário de fechamento."
            )
        por_dia[item.dia_semana].append(item)

    ordenados: list[ItemHorario] = []
    for dia in sorted(por_dia):
        faixas = sorted(por_dia[dia], key=lambda h: (h.hora_abertura, h.hora_fechamento))
        for indice in range(1, len(faixas)):
            if faixas[indice].hora_abertura < faixas[indice - 1].hora_fechamento:
                raise HorarioInvalido("Existem faixas de horário sobrepostas no mesmo dia.")
        ordenados.extend(faixas)
    return ordenados


def _responsaveis_ativos_do_ponto(ponto_id: int) -> list[Usuario]:
    return list(
        Usuario.objects.filter(
            vinculos_pontos_coleta__ponto_coleta_id=ponto_id,
            vinculos_pontos_coleta__status=StatusResponsavelPonto.ATIVO,
            status=StatusUsuario.ATIVO,
            anonimizado_em__isnull=True,
        ).distinct()
    )


def _projetar_responsaveis(ponto_id: int) -> tuple[ResumoResponsavelPonto, ...]:
    vinculos = (
        PontoColetaResponsavel.objects.filter(
            ponto_coleta_id=ponto_id,
            status__in=[
                StatusResponsavelPonto.ATIVO,
                StatusResponsavelPonto.CONVITE_PENDENTE,
            ],
        )
        .select_related("usuario")
        .order_by("status", "vinculado_em", "id")
    )
    return tuple(
        ResumoResponsavelPonto(
            id=v.pk,
            usuario_id=v.usuario_id,
            nome_completo=v.usuario.nome_completo or f"Usuário #{v.usuario_id}",
            cpf_mascarado=mascarar_cpf(v.usuario.cpf),
            email=v.usuario.email or "—",
            status=v.status,
            status_display=v.get_status_display(),
            vinculado_em=v.vinculado_em,
        )
        for v in vinculos
    )


def _ponto_com_revisao_vencida(ponto: PontoColeta, *, referencia: datetime | None = None) -> bool:
    if ponto.status != StatusPontoColeta.ATIVO:
        return False
    agora = referencia if referencia is not None else timezone.now()
    if ponto.ultima_revisao_em is None:
        return True
    limite = agora - timedelta(days=settings.REMED_PONTO_REVISAO_PERIODICA_DIAS)
    return ponto.ultima_revisao_em <= limite


class PontoColetaService:
    """Regras de negócio do cadastro, edição, responsáveis e pesquisa de pontos (Spec 05)."""

    @staticmethod
    def listar_tipos_estabelecimento_ativos() -> list[TipoEstabelecimento]:
        return list(TipoEstabelecimento.objects.filter(ativo=True).order_by("id"))

    @staticmethod
    def usuario_possui_vinculo_ou_convite(usuario: Usuario) -> bool:
        if getattr(usuario, "pk", None) is None:
            return False
        return PontoColetaResponsavel.objects.filter(
            usuario_id=usuario.pk,
            status__in=(
                StatusResponsavelPonto.ATIVO,
                StatusResponsavelPonto.CONVITE_PENDENTE,
            ),
        ).exists()

    @staticmethod
    def _convidar_responsavel_interno(
        ponto: PontoColeta,
        ator: Usuario,
        identificador: str,
    ) -> bool:
        """Cria convite sem vazar existência de conta (anti-enumeração — RS005)."""
        _, convidado = buscar_usuario_por_identificador(identificador)
        if convidado is None:
            return False
        if (
            convidado.pk == ator.pk
            or convidado.status != StatusUsuario.ATIVO
            or convidado.email_confirmado_em is None
            or convidado.anonimizado_em is not None
        ):
            return False

        ja_vinculado = PontoColetaResponsavel.objects.filter(
            ponto_coleta=ponto,
            usuario=convidado,
            status__in=[
                StatusResponsavelPonto.ATIVO,
                StatusResponsavelPonto.CONVITE_PENDENTE,
            ],
        ).exists()
        if ja_vinculado:
            return False

        vinculo = PontoColetaResponsavel.objects.create(
            ponto_coleta=ponto,
            usuario=convidado,
            status=StatusResponsavelPonto.CONVITE_PENDENTE,
            convidado_por=ator,
        )
        AuditoriaService.registrar(
            acao="ponto_coleta.responsavel_convidado",
            entidade_tipo="ponto_coleta",
            entidade_id=ponto.pk,
            ator=ator,
            detalhes={"vinculo_id": vinculo.pk, "convidado_usuario_id": convidado.pk},
        )
        # Acréscimo da especificação (aprovado): notificação via seguranca_conta sem PII.
        NotificacaoService.registrar_evento(
            destinatario=convidado,
            tipo=TipoNotificacao.SEGURANCA_CONTA,
            contexto={
                "evento_seguranca": (
                    f"Você recebeu um convite para atuar como responsável do ponto de coleta "
                    f"{ponto.nome_fantasia}. Acesse Meus pontos para aceitar ou recusar."
                )
            },
            url_destino="/pontos-coleta/meus/",
        )
        return True

    @staticmethod
    def cadastrar(
        usuario: Usuario,
        dados: DadosPontoColeta,
        horarios: list[ItemHorario] | tuple[ItemHorario, ...],
        *,
        responsaveis_adicionais: list[str] | tuple[str, ...] = (),
    ) -> PontoColeta:
        if (
            usuario.status != StatusUsuario.ATIVO
            or usuario.email_confirmado_em is None
            or usuario.anonimizado_em is not None
        ):
            raise PermissaoNegada("Somente usuários ativos com e-mail confirmado podem cadastrar.")

        try:
            cnpj_limpo = validar_cnpj(dados.cnpj)
            telefone_limpo = validar_telefone(dados.telefone)
            cep_limpo = validar_cep(dados.cep)
            estado_limpo = validar_uf(dados.estado)
        except ValueError as erro:
            raise RegraNegocioViolada(str(erro)) from erro

        email_limpo = normalizar_email(dados.email)
        razao_limpa = (dados.razao_social or "").strip()
        fantasia_limpa = (dados.nome_fantasia or "").strip()
        if not razao_limpa or not fantasia_limpa or not email_limpo:
            raise RegraNegocioViolada("Campo(s) obrigatório(s) não preenchido(s)")

        horarios_validos = _validar_horarios(horarios)

        tipo_estab = TipoEstabelecimento.objects.filter(
            pk=dados.tipo_estabelecimento_id, ativo=True
        ).first()
        if tipo_estab is None:
            raise RegraNegocioViolada("Selecione um tipo de estabelecimento válido.")

        if PontoColeta.objects.filter(cnpj=cnpj_limpo).exists():
            raise CnpjJaCadastrado()

        lat_aprox, lon_aprox = CepService.obter_coordenadas_em_cache(cep_limpo)

        try:
            with transaction.atomic():
                ponto = PontoColeta.objects.create(
                    cnpj=cnpj_limpo,
                    razao_social=razao_limpa[:150],
                    nome_fantasia=fantasia_limpa[:150],
                    tipo_estabelecimento=tipo_estab,
                    email=email_limpo,
                    telefone=telefone_limpo,
                    possui_refrigeracao=bool(dados.possui_refrigeracao),
                    observacoes=(dados.observacoes or "").strip(),
                    cep=cep_limpo,
                    logradouro=(dados.logradouro or "").strip()[:150],
                    numero=(dados.numero or "").strip()[:20],
                    bairro=(dados.bairro or "").strip()[:100],
                    municipio=(dados.municipio or "").strip()[:100],
                    estado=estado_limpo,
                    complemento=(dados.complemento or "").strip()[:100],
                    latitude_aprox=lat_aprox,
                    longitude_aprox=lon_aprox,
                    status=StatusPontoColeta.PENDENTE_APROVACAO,
                )
                HorarioFuncionamentoPonto.objects.bulk_create(
                    [
                        HorarioFuncionamentoPonto(
                            ponto_coleta=ponto,
                            dia_semana=h.dia_semana,
                            hora_abertura=h.hora_abertura,
                            hora_fechamento=h.hora_fechamento,
                        )
                        for h in horarios_validos
                    ]
                )
                PontoColetaResponsavel.objects.create(
                    ponto_coleta=ponto,
                    usuario=usuario,
                    status=StatusResponsavelPonto.ATIVO,
                )
                AuditoriaService.registrar(
                    acao="ponto_coleta.cadastrado",
                    entidade_tipo="ponto_coleta",
                    entidade_id=ponto.pk,
                    ator=usuario,
                    detalhes={
                        "tipo_estabelecimento_id": tipo_estab.pk,
                        "possui_refrigeracao": ponto.possui_refrigeracao,
                        "status": ponto.status,
                    },
                )
                for ident in responsaveis_adicionais:
                    if (ident or "").strip():
                        PontoColetaService._convidar_responsavel_interno(ponto, usuario, ident)
                return ponto
        except IntegrityError as erro:
            if PontoColeta.objects.filter(cnpj=cnpj_limpo).exists():
                raise CnpjJaCadastrado() from erro
            raise

    @staticmethod
    def obter_para_responsavel(ponto_id: int, usuario: Usuario) -> PontoColeta:
        ponto = (
            PontoColeta.objects.select_related("tipo_estabelecimento")
            .prefetch_related("horarios")
            .filter(
                pk=ponto_id,
                responsaveis__usuario=usuario,
                responsaveis__status=StatusResponsavelPonto.ATIVO,
            )
            .first()
        )
        if ponto is None:
            raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")
        return ponto

    @staticmethod
    def listar_responsaveis_para_gestao(
        ponto_id: int,
        usuario: Usuario,
    ) -> tuple[PontoColeta, tuple[ResumoResponsavelPonto, ...]]:
        ponto = PontoColetaService.obter_para_responsavel(ponto_id, usuario)
        return ponto, _projetar_responsaveis(ponto.pk)

    @staticmethod
    def listar_meus_pontos(usuario: Usuario) -> ResumoMeusPontos:
        pontos = list(
            PontoColeta.objects.select_related("tipo_estabelecimento")
            .filter(
                responsaveis__usuario=usuario,
                responsaveis__status=StatusResponsavelPonto.ATIVO,
            )
            .distinct()
            .order_by("-criado_em", "-id")
        )
        itens = []
        for ponto in pontos:
            situacao = DocumentoPontoService.situacao_documentos_obrigatorios(ponto.pk)
            ultima_analise = (
                AnalisePontoColeta.objects.filter(ponto_coleta_id=ponto.pk)
                .order_by("-criado_em")
                .first()
            )
            itens.append((ponto, situacao, ultima_analise))

        convites = tuple(
            PontoColetaResponsavel.objects.select_related(
                "ponto_coleta", "ponto_coleta__tipo_estabelecimento", "convidado_por"
            )
            .filter(usuario=usuario, status=StatusResponsavelPonto.CONVITE_PENDENTE)
            .order_by("-vinculado_em")
        )
        return ResumoMeusPontos(pontos=tuple(itens), convites_pendentes=convites)

    @staticmethod
    def atualizar(
        ponto_id: int,
        usuario: Usuario,
        dados: DadosAtualizacaoPonto,
        horarios: list[ItemHorario] | tuple[ItemHorario, ...],
        *,
        cancelador_agendamentos_futuros: Callable[[PontoColeta], None] | None = None,
    ) -> ResultadoAtualizacaoPonto:
        try:
            telefone_limpo = validar_telefone(dados.telefone)
            cep_limpo = validar_cep(dados.cep)
            estado_limpo = validar_uf(dados.estado)
        except ValueError as erro:
            raise RegraNegocioViolada(str(erro)) from erro

        email_limpo = normalizar_email(dados.email)
        razao_limpa = (dados.razao_social or "").strip()
        fantasia_limpa = (dados.nome_fantasia or "").strip()
        if not razao_limpa or not fantasia_limpa or not email_limpo:
            raise RegraNegocioViolada("Campo(s) obrigatório(s) não preenchido(s)")

        horarios_validos = _validar_horarios(horarios)
        tipo_estab = TipoEstabelecimento.objects.filter(
            pk=dados.tipo_estabelecimento_id, ativo=True
        ).first()
        if tipo_estab is None:
            raise RegraNegocioViolada("Selecione um tipo de estabelecimento válido.")

        with transaction.atomic():
            ponto = PontoColeta.objects.select_for_update().filter(pk=ponto_id).first()
            if ponto is None:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            eh_responsavel_ativo = PontoColetaResponsavel.objects.filter(
                ponto_coleta=ponto,
                usuario=usuario,
                status=StatusResponsavelPonto.ATIVO,
            ).exists()
            if not eh_responsavel_ativo:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            novos_valores = {
                "razao_social": razao_limpa[:150],
                "nome_fantasia": fantasia_limpa[:150],
                "tipo_estabelecimento_id": tipo_estab.pk,
                "email": email_limpo,
                "telefone": telefone_limpo,
                "possui_refrigeracao": bool(dados.possui_refrigeracao),
                "observacoes": (dados.observacoes or "").strip(),
                "cep": cep_limpo,
                "logradouro": (dados.logradouro or "").strip()[:150],
                "numero": (dados.numero or "").strip()[:20],
                "bairro": (dados.bairro or "").strip()[:100],
                "municipio": (dados.municipio or "").strip()[:100],
                "estado": estado_limpo,
                "complemento": (dados.complemento or "").strip()[:100],
            }
            campos_endereco = {
                "cep",
                "logradouro",
                "numero",
                "bairro",
                "municipio",
                "estado",
                "complemento",
            }
            campos_alterados: list[str] = []
            for campo, novo_val in novos_valores.items():
                if getattr(ponto, campo) != novo_val:
                    setattr(ponto, campo, novo_val)
                    campos_alterados.append(campo)

            endereco_mudou = bool(campos_endereco.intersection(campos_alterados))
            if endereco_mudou:
                lat_aprox, lon_aprox = CepService.obter_coordenadas_em_cache(cep_limpo)
                ponto.latitude_aprox = lat_aprox
                ponto.longitude_aprox = lon_aprox

            horarios_anteriores = list(
                HorarioFuncionamentoPonto.objects.filter(ponto_coleta=ponto)
                .order_by("dia_semana", "hora_abertura")
                .values_list("dia_semana", "hora_abertura", "hora_fechamento")
            )
            horarios_novos_tuplas = [
                (h.dia_semana, h.hora_abertura, h.hora_fechamento) for h in horarios_validos
            ]
            if horarios_anteriores != horarios_novos_tuplas:
                HorarioFuncionamentoPonto.objects.filter(ponto_coleta=ponto).delete()
                HorarioFuncionamentoPonto.objects.bulk_create(
                    [
                        HorarioFuncionamentoPonto(
                            ponto_coleta=ponto,
                            dia_semana=h.dia_semana,
                            hora_abertura=h.hora_abertura,
                            hora_fechamento=h.hora_fechamento,
                        )
                        for h in horarios_validos
                    ]
                )
                campos_alterados.append("horarios")

            remetido_reaprovacao = False
            if ponto.status == StatusPontoColeta.ATIVO and endereco_mudou:
                ponto.status = StatusPontoColeta.PENDENTE_APROVACAO
                remetido_reaprovacao = True

            ponto.save()

            if remetido_reaprovacao:
                if cancelador_agendamentos_futuros is not None:
                    cancelador_agendamentos_futuros(ponto)
                else:
                    _cancelar_agendamentos_futuros_noop(
                        ponto, motivo="Alteração de endereço de ponto ativo"
                    )
                AuditoriaService.registrar(
                    acao="ponto_coleta.remetido_reaprovacao",
                    entidade_tipo="ponto_coleta",
                    entidade_id=ponto.pk,
                    ator=usuario,
                    detalhes={"motivo_tecnico": "alteracao_endereco"},
                )

            AuditoriaService.registrar(
                acao="ponto_coleta.alterado",
                entidade_tipo="ponto_coleta",
                entidade_id=ponto.pk,
                ator=usuario,
                detalhes={"campos_alterados": sorted(set(campos_alterados))},
            )
            return ResultadoAtualizacaoPonto(
                ponto=ponto,
                campos_alterados=tuple(sorted(set(campos_alterados))),
                remetido_reaprovacao=remetido_reaprovacao,
            )

    @staticmethod
    def inativar_pelo_responsavel(
        ponto_id: int,
        usuario: Usuario,
        *,
        cancelador_agendamentos_futuros: Callable[[PontoColeta], None] | None = None,
    ) -> PontoColeta:
        """Inativação voluntária pelo representante (acréscimo aprovado na Spec 05)."""
        with transaction.atomic():
            ponto = PontoColeta.objects.select_for_update().filter(pk=ponto_id).first()
            if ponto is None:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            eh_responsavel_ativo = PontoColetaResponsavel.objects.filter(
                ponto_coleta=ponto,
                usuario=usuario,
                status=StatusResponsavelPonto.ATIVO,
            ).exists()
            if not eh_responsavel_ativo:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            if ponto.status == StatusPontoColeta.INATIVO:
                raise RegraNegocioViolada("Este ponto de coleta já está inativo.")

            status_anterior = ponto.status
            ponto.status = StatusPontoColeta.INATIVO
            ponto.save(update_fields=["status", "atualizado_em"])

            if status_anterior == StatusPontoColeta.ATIVO:
                if cancelador_agendamentos_futuros is not None:
                    cancelador_agendamentos_futuros(ponto)
                else:
                    _cancelar_agendamentos_futuros_noop(
                        ponto, motivo="Inativação voluntária pelo responsável"
                    )

            AuditoriaService.registrar(
                acao="ponto_coleta.inativado_responsavel",
                entidade_tipo="ponto_coleta",
                entidade_id=ponto.pk,
                ator=usuario,
                detalhes={"status_anterior": status_anterior, "status_novo": ponto.status},
            )
            return ponto

    @staticmethod
    def alterar_cnpj(
        ator: Usuario,
        ponto_id: int,
        novo_cnpj: str,
        motivo: str,
    ) -> PontoColeta:
        if not AutenticacaoService.possui_funcao(ator, "aprovacao_pontos_coleta"):
            raise PermissaoNegada(
                "Apenas Administradores com função aprovação de pontos podem alterar CNPJ."
            )

        motivo_limpo = (motivo or "").strip()
        if not motivo_limpo:
            raise RegraNegocioViolada("Informe o motivo da alteração do CNPJ.")

        try:
            cnpj_limpo = validar_cnpj(novo_cnpj)
        except ValueError as erro:
            raise RegraNegocioViolada(str(erro)) from erro

        with transaction.atomic():
            ponto = PontoColeta.objects.select_for_update().filter(pk=ponto_id).first()
            if ponto is None:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            if ponto.cnpj == cnpj_limpo:
                raise RegraNegocioViolada("O ponto de coleta já possui o CNPJ informado.")

            if PontoColeta.objects.filter(cnpj=cnpj_limpo).exclude(pk=ponto.pk).exists():
                raise CnpjJaCadastrado()

            cnpj_anterior = ponto.cnpj
            ponto.cnpj = cnpj_limpo
            ponto.save(update_fields=["cnpj", "atualizado_em"])

            AuditoriaService.registrar(
                acao="ponto_coleta.cnpj_alterado",
                entidade_tipo="ponto_coleta",
                entidade_id=ponto.pk,
                ator=ator,
                motivo=motivo_limpo,
                detalhes={"cnpj_anterior": cnpj_anterior, "cnpj_novo": cnpj_limpo},
            )
            return ponto

    @staticmethod
    def convidar_responsavel(
        ponto_id: int,
        ator: Usuario,
        identificador_usuario: str,
    ) -> bool:
        """Envia convite de responsabilidade sem vazar se o e-mail/CPF existe (RS005)."""
        if not (identificador_usuario or "").strip():
            raise RegraNegocioViolada("Informe o e-mail ou CPF do usuário a convidar.")

        with transaction.atomic():
            ponto = PontoColeta.objects.select_for_update().filter(pk=ponto_id).first()
            if ponto is None:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            eh_responsavel_ativo = PontoColetaResponsavel.objects.filter(
                ponto_coleta=ponto,
                usuario=ator,
                status=StatusResponsavelPonto.ATIVO,
            ).exists()
            if not eh_responsavel_ativo:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            return PontoColetaService._convidar_responsavel_interno(
                ponto, ator, identificador_usuario
            )

    @staticmethod
    def responder_convite(
        convite_id: int,
        usuario: Usuario,
        *,
        aceitar: bool,
    ) -> PontoColetaResponsavel:
        with transaction.atomic():
            vinculo = (
                PontoColetaResponsavel.objects.select_for_update()
                .select_related("ponto_coleta")
                .filter(
                    pk=convite_id,
                    usuario=usuario,
                    status=StatusResponsavelPonto.CONVITE_PENDENTE,
                )
                .first()
            )
            if vinculo is None:
                raise RecursoNaoEncontrado("Convite não encontrado.")

            if aceitar:
                vinculo.status = StatusResponsavelPonto.ATIVO
                vinculo.save(update_fields=["status"])
                acao = "ponto_coleta.responsavel_convite_aceito"
            else:
                vinculo.status = StatusResponsavelPonto.RECUSADO
                vinculo.desvinculado_em = timezone.now()
                vinculo.save(update_fields=["status", "desvinculado_em"])
                acao = "ponto_coleta.responsavel_convite_recusado"

            AuditoriaService.registrar(
                acao=acao,
                entidade_tipo="ponto_coleta",
                entidade_id=vinculo.ponto_coleta_id,
                ator=usuario,
                detalhes={"vinculo_id": vinculo.pk},
            )
            return vinculo

    @staticmethod
    def desvincular_responsavel(
        ponto_id: int,
        ator: Usuario,
        responsavel_id: int,
    ) -> PontoColetaResponsavel:
        with transaction.atomic():
            ponto = PontoColeta.objects.select_for_update().filter(pk=ponto_id).first()
            if ponto is None:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            vinculos = list(
                PontoColetaResponsavel.objects.select_for_update()
                .filter(
                    ponto_coleta=ponto,
                    status__in=[
                        StatusResponsavelPonto.ATIVO,
                        StatusResponsavelPonto.CONVITE_PENDENTE,
                    ],
                )
                .order_by("id")
            )
            ator_ativo = any(
                v.usuario_id == ator.pk and v.status == StatusResponsavelPonto.ATIVO
                for v in vinculos
            )
            if not ator_ativo:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            alvo = next((v for v in vinculos if v.pk == responsavel_id), None)
            if alvo is None:
                raise RecursoNaoEncontrado("Vínculo de responsável não encontrado.")

            ativos = [v for v in vinculos if v.status == StatusResponsavelPonto.ATIVO]
            if alvo.status == StatusResponsavelPonto.ATIVO and len(ativos) <= 1:
                raise UltimoResponsavelAtivo()

            alvo.status = StatusResponsavelPonto.INATIVO
            alvo.desvinculado_em = timezone.now()
            alvo.save(update_fields=["status", "desvinculado_em"])

            AuditoriaService.registrar(
                acao="ponto_coleta.responsavel_desvinculado",
                entidade_tipo="ponto_coleta",
                entidade_id=ponto.pk,
                ator=ator,
                detalhes={"vinculo_id": alvo.pk, "usuario_desvinculado_id": alvo.usuario_id},
            )
            return alvo

    @staticmethod
    def pesquisar(
        ator: Usuario | None,
        filtros: FiltrosPontoColeta | None = None,
        *,
        apenas_ativos: bool = True,
        pagina: int = 1,
        por_pagina: int = PONTOS_POR_PAGINA,
    ) -> PaginaPontosColeta:
        if not apenas_ativos:
            if ator is None or not AutenticacaoService.possui_funcao(
                ator, "aprovacao_pontos_coleta"
            ):
                raise PermissaoNegada(
                    "Apenas Administradores com aprovação de pontos podem ver todos os status."
                )

        f = filtros if filtros is not None else FiltrosPontoColeta()
        qs = (
            PontoColeta.objects.select_related("tipo_estabelecimento")
            .prefetch_related("horarios")
            .order_by("nome_fantasia", "id")
        )
        if apenas_ativos:
            qs = qs.filter(status=StatusPontoColeta.ATIVO)
        elif f.status and f.status in StatusPontoColeta.values:
            qs = qs.filter(status=f.status)

        termo = (f.termo or "").strip()
        if termo:
            if apenas_ativos:
                qs = qs.filter(nome_fantasia__icontains=termo)
            else:
                qs = qs.filter(Q(nome_fantasia__icontains=termo) | Q(razao_social__icontains=termo))

        cnpj_digitos = somente_digitos(f.cnpj)
        if not apenas_ativos and cnpj_digitos:
            qs = qs.filter(cnpj__icontains=cnpj_digitos)

        if f.tipo_estabelecimento_id:
            qs = qs.filter(tipo_estabelecimento_id=f.tipo_estabelecimento_id)

        municipio = (f.municipio or "").strip()
        if municipio:
            qs = qs.filter(municipio__icontains=municipio)

        if not apenas_ativos and f.revisao_vencida:
            limite = timezone.now() - timedelta(days=settings.REMED_PONTO_REVISAO_PERIODICA_DIAS)
            qs = qs.filter(status=StatusPontoColeta.ATIVO).filter(
                Q(ultima_revisao_em__isnull=True) | Q(ultima_revisao_em__lte=limite)
            )

        paginador = Paginator(qs, por_pagina)
        page_obj = paginador.get_page(pagina)
        return PaginaPontosColeta(pagina=page_obj, total_encontrados=paginador.count)


class DocumentoPontoService:
    """Envio, versionamento, acesso auditado e rotina de vencimentos de documentos (Spec 06)."""

    @staticmethod
    def listar_tipos_documento_ativos() -> list[TipoDocumentoPonto]:
        return list(TipoDocumentoPonto.objects.filter(ativo=True).order_by("id"))

    @staticmethod
    def situacao_documentos_obrigatorios(
        ponto_id: int,
        *,
        referencia: date | None = None,
    ) -> SituacaoDocumentosObrigatorios:
        hoje = referencia if referencia is not None else timezone.localdate()
        tipos = list(TipoDocumentoPonto.objects.filter(ativo=True, obrigatorio=True).order_by("id"))
        docs = list(
            DocumentoPontoColeta.objects.filter(
                ponto_coleta_id=ponto_id,
                tipo_documento__in=tipos,
            )
            .select_related("tipo_documento")
            .order_by("tipo_documento_id", "-versao")
        )
        ultimo_por_tipo: dict[int, DocumentoPontoColeta] = {}
        for doc in docs:
            if doc.tipo_documento_id not in ultimo_por_tipo:
                ultimo_por_tipo[doc.tipo_documento_id] = doc

        itens: list[ItemDocumentoObrigatorio] = []
        for tipo in tipos:
            ultimo = ultimo_por_tipo.get(tipo.pk)
            enviado_valido = (
                ultimo is not None
                and ultimo.status
                in {
                    StatusDocumentoPonto.ENVIADO,
                    StatusDocumentoPonto.EM_ANALISE,
                    StatusDocumentoPonto.APROVADO,
                }
                and ultimo.data_validade >= hoje
            )
            aprovado_valido = (
                ultimo is not None
                and ultimo.status == StatusDocumentoPonto.APROVADO
                and ultimo.data_validade >= hoje
            )
            itens.append(
                ItemDocumentoObrigatorio(
                    tipo=tipo,
                    ultima_versao=ultimo,
                    enviado_e_valido=enviado_valido,
                    aprovado_e_valido=aprovado_valido,
                )
            )
        return SituacaoDocumentosObrigatorios(
            itens=tuple(itens),
            todos_enviados_validos=bool(itens) and all(i.enviado_e_valido for i in itens),
            todos_aprovados_validos=bool(itens) and all(i.aprovado_e_valido for i in itens),
        )

    @staticmethod
    def listar_do_ponto(
        ponto_id: int,
        usuario: Usuario,
    ) -> tuple[PontoColeta, SituacaoDocumentosObrigatorios, list[DocumentoPontoColeta]]:
        ponto = PontoColetaService.obter_para_responsavel(ponto_id, usuario)
        situacao = DocumentoPontoService.situacao_documentos_obrigatorios(ponto.pk)
        documentos = list(
            DocumentoPontoColeta.objects.filter(ponto_coleta=ponto)
            .select_related("tipo_documento", "enviado_por")
            .order_by("-enviado_em", "-versao")
        )
        return ponto, situacao, documentos

    @staticmethod
    def enviar(
        ponto_id: int,
        usuario: Usuario,
        *,
        tipo_documento_id: int,
        numero_documento: str,
        data_validade: date,
        conteudo: bytes,
        nome_original: str,
        referencia: date | None = None,
        scanner: AntimalwareScanner | None = None,
        backend: BackendArmazenamentoPrivado | None = None,
    ) -> DocumentoPontoColeta:
        hoje = referencia if referencia is not None else timezone.localdate()
        if data_validade < hoje:
            raise DocumentoVencido()

        numero_limpo = (numero_documento or "").strip()
        if not numero_limpo:
            raise RegraNegocioViolada("Informe o número do documento.")

        tipo = TipoDocumentoPonto.objects.filter(pk=tipo_documento_id, ativo=True).first()
        if tipo is None:
            raise RegraNegocioViolada("Selecione um tipo de documento válido.")

        with transaction.atomic():
            # select_for_update no PontoColeta evita colisão concorrente ao calcular próxima versão.
            ponto = PontoColeta.objects.select_for_update().filter(pk=ponto_id).first()
            if ponto is None:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            eh_responsavel_ativo = PontoColetaResponsavel.objects.filter(
                ponto_coleta=ponto,
                usuario=usuario,
                status=StatusResponsavelPonto.ATIVO,
            ).exists()
            if not eh_responsavel_ativo:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            armazenado = ArquivoService.armazenar_privado(
                conteudo=conteudo,
                nome_original=nome_original,
                categoria="pontos_coleta",
                scanner=scanner,
                backend=backend,
            )
            try:
                maior_versao = (
                    DocumentoPontoColeta.objects.filter(
                        ponto_coleta=ponto,
                        tipo_documento=tipo,
                    ).aggregate(maior=Max("versao"))["maior"]
                    or 0
                )
                doc = DocumentoPontoColeta.objects.create(
                    ponto_coleta=ponto,
                    tipo_documento=tipo,
                    versao=maior_versao + 1,
                    arquivo_chave=armazenado.chave,
                    mime_verificado=armazenado.mime_verificado,
                    tamanho_bytes=armazenado.tamanho_bytes,
                    numero_documento=numero_limpo[:80],
                    data_validade=data_validade,
                    status=StatusDocumentoPonto.ENVIADO,
                    enviado_por=usuario,
                )

                situacao = DocumentoPontoService.situacao_documentos_obrigatorios(
                    ponto.pk, referencia=hoje
                )
                if situacao.todos_enviados_validos:
                    ids_para_analise = [
                        item.ultima_versao.pk
                        for item in situacao.itens
                        if item.ultima_versao is not None
                        and item.ultima_versao.status == StatusDocumentoPonto.ENVIADO
                    ]
                    if ids_para_analise:
                        DocumentoPontoColeta.objects.filter(pk__in=ids_para_analise).update(
                            status=StatusDocumentoPonto.EM_ANALISE
                        )
                        if doc.pk in ids_para_analise:
                            doc.status = StatusDocumentoPonto.EM_ANALISE

                AuditoriaService.registrar(
                    acao="documento_ponto.enviado",
                    entidade_tipo="documento_ponto",
                    entidade_id=doc.pk,
                    ator=usuario,
                    detalhes={
                        "ponto_coleta_id": ponto.pk,
                        "tipo_documento_id": tipo.pk,
                        "versao": doc.versao,
                        "status": doc.status,
                    },
                )
                AuditoriaService.registrar(
                    acao="arquivo.enviado",
                    entidade_tipo="documento_ponto",
                    entidade_id=doc.pk,
                    ator=usuario,
                    detalhes={
                        "categoria": "pontos_coleta",
                        "mime_verificado": armazenado.mime_verificado,
                        "tamanho_bytes": armazenado.tamanho_bytes,
                    },
                )
                return doc
            except Exception:
                ArquivoService.remover_silencioso(armazenado.chave, backend=backend)
                raise

    @staticmethod
    def gerar_acesso_temporario(
        documento_id: int,
        ator: Usuario,
        *,
        backend: BackendArmazenamentoPrivado | None = None,
    ) -> str:
        documento = (
            DocumentoPontoColeta.objects.select_related("ponto_coleta", "tipo_documento")
            .filter(pk=documento_id)
            .first()
        )
        if documento is None:
            raise RecursoNaoEncontrado("Documento não encontrado.")

        eh_responsavel_ativo = PontoColetaResponsavel.objects.filter(
            ponto_coleta_id=documento.ponto_coleta_id,
            usuario=ator,
            status=StatusResponsavelPonto.ATIVO,
        ).exists()
        if not eh_responsavel_ativo:
            if AutenticacaoService.possui_funcao(ator, "aprovacao_pontos_coleta"):
                pass
            elif AutenticacaoService.possui_funcao_administrativa(ator) or ator.is_superuser:
                raise PermissaoNegada(
                    "Apenas o responsável ativo ou Administrador com aprovação de pontos "
                    "pode visualizar este documento."
                )
            else:
                raise RecursoNaoEncontrado("Documento não encontrado.")

        AuditoriaService.registrar(
            acao="arquivo.acessado",
            entidade_tipo="documento_ponto",
            entidade_id=documento.pk,
            ator=ator,
            detalhes={
                "ponto_coleta_id": documento.ponto_coleta_id,
                "versao": documento.versao,
            },
        )
        return ArquivoService.gerar_url_temporaria(
            documento.arquivo_chave,
            usuario_id=ator.pk,
            mime_verificado=documento.mime_verificado,
            nome_download=f"ponto_{documento.ponto_coleta_id}_doc_{documento.pk}_v{documento.versao}",
            backend=backend,
        )

    @staticmethod
    def pesquisar_admin(
        ator: Usuario,
        filtros: FiltrosDocumentosAdmin | None = None,
        *,
        pagina: int = 1,
        por_pagina: int = PONTOS_POR_PAGINA,
    ) -> PaginaDocumentosAdmin:
        if not AutenticacaoService.possui_funcao(ator, "aprovacao_pontos_coleta"):
            raise PermissaoNegada(
                "Apenas Administradores com função aprovação de pontos podem pesquisar documentos."
            )

        f = filtros if filtros is not None else FiltrosDocumentosAdmin()
        qs = DocumentoPontoColeta.objects.select_related(
            "ponto_coleta", "tipo_documento", "enviado_por"
        ).order_by("data_validade", "-enviado_em")
        if f.ponto_coleta_id:
            qs = qs.filter(ponto_coleta_id=f.ponto_coleta_id)
        if f.tipo_documento_id:
            qs = qs.filter(tipo_documento_id=f.tipo_documento_id)
        if f.status and f.status in StatusDocumentoPonto.values:
            qs = qs.filter(status=f.status)
        if f.validade_ate is not None:
            qs = qs.filter(data_validade__lte=f.validade_ate)

        paginador = Paginator(qs, por_pagina)
        return PaginaDocumentosAdmin(
            pagina=paginador.get_page(pagina),
            total_encontrados=paginador.count,
        )

    @staticmethod
    def processar_vencimentos_diarios(
        *,
        referencia: date | None = None,
        cancelador_agendamentos_futuros: Callable[[PontoColeta], None] | None = None,
    ) -> ResultadoVencimentoDocumentos:
        """Rotina diária idempotente de aviso e expiração de documentos (Spec 06 / ADR 0014)."""
        hoje = referencia if referencia is not None else timezone.localdate()
        agora = timezone.now()
        limite_aviso = hoje + timedelta(days=settings.REMED_PONTO_DOC_AVISO_VENCIMENTO_DIAS)

        avisos_enviados = 0
        documentos_vencidos = 0
        pontos_remetidos = 0

        # 1. Aviso prévio (30 dias antes, idempotente via aviso_vencimento_enviado_em)
        candidatos_aviso = list(
            DocumentoPontoColeta.objects.filter(
                status=StatusDocumentoPonto.APROVADO,
                data_validade__gte=hoje,
                data_validade__lte=limite_aviso,
                aviso_vencimento_enviado_em__isnull=True,
                ponto_coleta__status=StatusPontoColeta.ATIVO,
            )
            .values_list("id", flat=True)
            .order_by("id")
        )
        for doc_id in candidatos_aviso:
            with transaction.atomic():
                doc = (
                    DocumentoPontoColeta.objects.select_for_update(of=("self",))
                    .select_related("ponto_coleta")
                    .filter(
                        pk=doc_id,
                        status=StatusDocumentoPonto.APROVADO,
                        aviso_vencimento_enviado_em__isnull=True,
                    )
                    .first()
                )
                if doc is None:
                    continue
                tem_versao_mais_nova = DocumentoPontoColeta.objects.filter(
                    ponto_coleta_id=doc.ponto_coleta_id,
                    tipo_documento_id=doc.tipo_documento_id,
                    status=StatusDocumentoPonto.APROVADO,
                    versao__gt=doc.versao,
                ).exists()
                if tem_versao_mais_nova:
                    continue

                doc.aviso_vencimento_enviado_em = agora
                doc.save(update_fields=["aviso_vencimento_enviado_em"])
                for responsavel in _responsaveis_ativos_do_ponto(doc.ponto_coleta_id):
                    NotificacaoService.registrar_evento(
                        destinatario=responsavel,
                        tipo=TipoNotificacao.DOCUMENTO_PRESTES_VENCER,
                        contexto={"ponto_nome": doc.ponto_coleta.nome_fantasia},
                        url_destino=f"/pontos-coleta/{doc.ponto_coleta_id}/documentos/",
                    )
                avisos_enviados += 1

        # 2. Vencimento efetivo (data_validade < hoje)
        candidatos_vencidos = list(
            DocumentoPontoColeta.objects.filter(
                status=StatusDocumentoPonto.APROVADO,
                data_validade__lt=hoje,
            )
            .values_list("id", "ponto_coleta_id")
            .order_by("ponto_coleta_id", "id")
        )
        for doc_id, ponto_id in candidatos_vencidos:
            with transaction.atomic():
                ponto = PontoColeta.objects.select_for_update().filter(pk=ponto_id).first()
                if ponto is None:
                    continue
                doc = (
                    DocumentoPontoColeta.objects.select_for_update()
                    .filter(pk=doc_id, status=StatusDocumentoPonto.APROVADO)
                    .first()
                )
                if doc is None or doc.data_validade >= hoje:
                    continue

                doc.status = StatusDocumentoPonto.VENCIDO
                doc.save(update_fields=["status"])
                documentos_vencidos += 1

                AuditoriaService.registrar(
                    acao="documento_ponto.vencido",
                    entidade_tipo="documento_ponto",
                    entidade_id=doc.pk,
                    ator=None,
                    detalhes={"ponto_coleta_id": ponto.pk, "versao": doc.versao},
                )

                tem_nova_valida = DocumentoPontoColeta.objects.filter(
                    ponto_coleta_id=ponto.pk,
                    tipo_documento_id=doc.tipo_documento_id,
                    status=StatusDocumentoPonto.APROVADO,
                    data_validade__gte=hoje,
                    versao__gt=doc.versao,
                ).exists()
                if ponto.status == StatusPontoColeta.ATIVO and not tem_nova_valida:
                    ponto.status = StatusPontoColeta.PENDENTE_APROVACAO
                    ponto.save(update_fields=["status", "atualizado_em"])
                    pontos_remetidos += 1
                    if cancelador_agendamentos_futuros is not None:
                        cancelador_agendamentos_futuros(ponto)
                    else:
                        _cancelar_agendamentos_futuros_noop(
                            ponto, motivo="Documento obrigatório vencido"
                        )
                    AuditoriaService.registrar(
                        acao="ponto_coleta.remetido_reaprovacao",
                        entidade_tipo="ponto_coleta",
                        entidade_id=ponto.pk,
                        ator=None,
                        detalhes={"motivo_tecnico": "documento_vencido", "documento_id": doc.pk},
                    )
                    for responsavel in _responsaveis_ativos_do_ponto(ponto.pk):
                        NotificacaoService.registrar_evento(
                            destinatario=responsavel,
                            tipo=TipoNotificacao.PONTO_ANALISADO,
                            contexto={
                                "ponto_nome": ponto.nome_fantasia,
                                "resultado": "pendente de aprovação por documento vencido",
                            },
                            url_destino=f"/pontos-coleta/{ponto.pk}/documentos/",
                        )

        return ResultadoVencimentoDocumentos(
            avisos_enviados=avisos_enviados,
            documentos_vencidos=documentos_vencidos,
            pontos_remetidos_reaprovacao=pontos_remetidos,
        )


class AprovacaoPontoService:
    """Análise, aprovação, mudança de situação e revisão periódica de pontos (Spec 07)."""

    @staticmethod
    def _exigir_funcao_aprovacao(ator: Usuario) -> None:
        if not AutenticacaoService.possui_funcao(ator, "aprovacao_pontos_coleta"):
            raise PermissaoNegada(
                "Apenas Administradores com função aprovação de pontos podem executar esta ação."
            )

    @staticmethod
    def obter_detalhe_admin(
        ator: Usuario,
        ponto_id: int,
        *,
        referencia: date | None = None,
    ) -> DetalhePontoAdmin:
        AprovacaoPontoService._exigir_funcao_aprovacao(ator)
        ponto = (
            PontoColeta.objects.select_related("tipo_estabelecimento")
            .prefetch_related("horarios")
            .filter(pk=ponto_id)
            .first()
        )
        if ponto is None:
            raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

        documentos = tuple(
            DocumentoPontoColeta.objects.filter(ponto_coleta=ponto)
            .select_related("tipo_documento", "enviado_por")
            .order_by("-enviado_em", "-versao")
        )
        situacao = DocumentoPontoService.situacao_documentos_obrigatorios(
            ponto.pk, referencia=referencia
        )
        analises = tuple(
            AnalisePontoColeta.objects.filter(ponto_coleta=ponto)
            .select_related("responsavel")
            .order_by("-criado_em")[:50]
        )
        return DetalhePontoAdmin(
            ponto=ponto,
            cnpj_formatado=formatar_cnpj(ponto.cnpj),
            horarios=tuple(ponto.horarios.all()),
            responsaveis=_projetar_responsaveis(ponto.pk),
            documentos=documentos,
            situacao_docs=situacao,
            analises=analises,
            revisao_vencida=_ponto_com_revisao_vencida(ponto),
            checklist_orientativo=CHECKLIST_ORIENTATIVO_APROVACAO,
        )

    @staticmethod
    def analisar_cadastro(
        ator: Usuario,
        ponto_id: int,
        resultado: str,
        motivo: str = "",
        *,
        referencia: date | None = None,
    ) -> AnalisePontoColeta:
        AprovacaoPontoService._exigir_funcao_aprovacao(ator)
        if resultado not in ResultadoAnalisePonto.values:
            raise RegraNegocioViolada("Resultado de análise inválido.")

        motivo_limpo = (motivo or "").strip()
        if (
            resultado
            in {
                ResultadoAnalisePonto.REPROVADO,
                ResultadoAnalisePonto.PENDENTE_DOCUMENTACAO,
            }
            and not motivo_limpo
        ):
            raise MotivoAnaliseObrigatorio()

        hoje = referencia if referencia is not None else timezone.localdate()
        agora = timezone.now()

        with transaction.atomic():
            ponto = PontoColeta.objects.select_for_update().filter(pk=ponto_id).first()
            if ponto is None:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            if ponto.status != StatusPontoColeta.PENDENTE_APROVACAO:
                raise RegraNegocioViolada(
                    "Somente pontos com status Pendente de aprovação passam por análise inicial."
                )

            status_anterior = ponto.status
            situacao = DocumentoPontoService.situacao_documentos_obrigatorios(
                ponto.pk, referencia=hoje
            )

            if resultado == ResultadoAnalisePonto.APROVADO:
                if not situacao.todos_enviados_validos:
                    raise DocumentosObrigatoriosPendentes(
                        "Não é possível aprovar o ponto de coleta sem licença de funcionamento "
                        "e alvará sanitário enviados e dentro da validade."
                    )
                ids_aprovar = [
                    item.ultima_versao.pk
                    for item in situacao.itens
                    if item.ultima_versao is not None
                ]
                if ids_aprovar:
                    DocumentoPontoColeta.objects.filter(pk__in=ids_aprovar).update(
                        status=StatusDocumentoPonto.APROVADO
                    )
                ponto.status = StatusPontoColeta.ATIVO
                ponto.ultima_revisao_em = agora
                ponto.save(update_fields=["status", "ultima_revisao_em", "atualizado_em"])
                acao_auditoria = "ponto_coleta.aprovado"
                texto_resultado = "aprovado e ativo na plataforma"
            else:
                if resultado == ResultadoAnalisePonto.REPROVADO:
                    ids_reprovar = [
                        item.ultima_versao.pk
                        for item in situacao.itens
                        if item.ultima_versao is not None
                        and item.ultima_versao.status
                        in {StatusDocumentoPonto.ENVIADO, StatusDocumentoPonto.EM_ANALISE}
                    ]
                    if ids_reprovar:
                        DocumentoPontoColeta.objects.filter(pk__in=ids_reprovar).update(
                            status=StatusDocumentoPonto.REPROVADO
                        )
                    acao_auditoria = "ponto_coleta.reprovado"
                    texto_resultado = f"reprovado — motivo: {motivo_limpo}"
                else:
                    acao_auditoria = "ponto_coleta.pendente_documentacao"
                    texto_resultado = f"pendente de documentação — motivo: {motivo_limpo}"

            analise = AnalisePontoColeta.objects.create(
                ponto_coleta=ponto,
                tipo_acao=TipoAcaoAnalisePonto.ANALISE_CADASTRO,
                resultado=resultado,
                status_anterior=status_anterior,
                status_novo=ponto.status,
                motivo=motivo_limpo,
                responsavel=ator,
            )
            AuditoriaService.registrar(
                acao=acao_auditoria,
                entidade_tipo="ponto_coleta",
                entidade_id=ponto.pk,
                ator=ator,
                motivo=motivo_limpo,
                detalhes={
                    "resultado": resultado,
                    "status_anterior": status_anterior,
                    "status_novo": ponto.status,
                },
            )
            for responsavel in _responsaveis_ativos_do_ponto(ponto.pk):
                NotificacaoService.registrar_evento(
                    destinatario=responsavel,
                    tipo=TipoNotificacao.PONTO_ANALISADO,
                    contexto={
                        "ponto_nome": ponto.nome_fantasia,
                        "resultado": texto_resultado,
                    },
                    url_destino=f"/pontos-coleta/{ponto.pk}/documentos/",
                )
            return analise

    @staticmethod
    def alterar_situacao(
        ator: Usuario,
        ponto_id: int,
        novo_status: str,
        motivo: str,
        *,
        referencia: date | None = None,
        cancelador_agendamentos_futuros: Callable[[PontoColeta], None] | None = None,
    ) -> AnalisePontoColeta:
        AprovacaoPontoService._exigir_funcao_aprovacao(ator)
        if novo_status not in {
            StatusPontoColeta.ATIVO,
            StatusPontoColeta.SUSPENSO,
            StatusPontoColeta.INATIVO,
        }:
            raise RegraNegocioViolada("Situação de destino inválida para o ponto de coleta.")

        motivo_limpo = (motivo or "").strip()
        if not motivo_limpo:
            raise MotivoAnaliseObrigatorio()

        hoje = referencia if referencia is not None else timezone.localdate()
        agora = timezone.now()

        with transaction.atomic():
            ponto = PontoColeta.objects.select_for_update().filter(pk=ponto_id).first()
            if ponto is None:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")

            if ponto.status == novo_status:
                raise RegraNegocioViolada("O ponto de coleta já está com a situação informada.")

            status_anterior = ponto.status
            if novo_status == StatusPontoColeta.ATIVO:
                situacao = DocumentoPontoService.situacao_documentos_obrigatorios(
                    ponto.pk, referencia=hoje
                )
                if not situacao.todos_enviados_validos:
                    raise DocumentosObrigatoriosPendentes(
                        "Para reativar o ponto, licença de funcionamento e alvará sanitário "
                        "devem estar válidos. Solicite o envio de nova versão antes de reativar."
                    )
                ids_aprovar = [
                    item.ultima_versao.pk
                    for item in situacao.itens
                    if item.ultima_versao is not None
                    and item.ultima_versao.status
                    in {StatusDocumentoPonto.ENVIADO, StatusDocumentoPonto.EM_ANALISE}
                ]
                if ids_aprovar:
                    DocumentoPontoColeta.objects.filter(pk__in=ids_aprovar).update(
                        status=StatusDocumentoPonto.APROVADO
                    )
                ponto.ultima_revisao_em = agora

            ponto.status = novo_status
            ponto.save(update_fields=["status", "ultima_revisao_em", "atualizado_em"])

            if status_anterior == StatusPontoColeta.ATIVO and novo_status in {
                StatusPontoColeta.SUSPENSO,
                StatusPontoColeta.INATIVO,
            }:
                if cancelador_agendamentos_futuros is not None:
                    cancelador_agendamentos_futuros(ponto)
                else:
                    _cancelar_agendamentos_futuros_noop(ponto, motivo=motivo_limpo)

            analise = AnalisePontoColeta.objects.create(
                ponto_coleta=ponto,
                tipo_acao=TipoAcaoAnalisePonto.ALTERACAO_SITUACAO,
                resultado="",
                status_anterior=status_anterior,
                status_novo=novo_status,
                motivo=motivo_limpo,
                responsavel=ator,
            )
            AuditoriaService.registrar(
                acao="ponto_coleta.situacao_alterada",
                entidade_tipo="ponto_coleta",
                entidade_id=ponto.pk,
                ator=ator,
                motivo=motivo_limpo,
                detalhes={"status_anterior": status_anterior, "status_novo": novo_status},
            )
            for responsavel in _responsaveis_ativos_do_ponto(ponto.pk):
                texto_situacao = (
                    f"situação alterada para {ponto.get_status_display()} — {motivo_limpo}"
                )
                NotificacaoService.registrar_evento(
                    destinatario=responsavel,
                    tipo=TipoNotificacao.PONTO_ANALISADO,
                    contexto={
                        "ponto_nome": ponto.nome_fantasia,
                        "resultado": texto_situacao,
                    },
                    url_destino=f"/pontos-coleta/{ponto.pk}/documentos/",
                )
            return analise

    @staticmethod
    def registrar_revisao_periodica(
        ator: Usuario,
        ponto_id: int,
        motivo: str = "",
        *,
        referencia: date | None = None,
    ) -> AnalisePontoColeta:
        AprovacaoPontoService._exigir_funcao_aprovacao(ator)
        hoje = referencia if referencia is not None else timezone.localdate()
        agora = timezone.now()
        motivo_limpo = (
            motivo or ""
        ).strip() or "Revisão periódica concluída com documentação regular."

        with transaction.atomic():
            ponto = PontoColeta.objects.select_for_update().filter(pk=ponto_id).first()
            if ponto is None:
                raise RecursoNaoEncontrado("Ponto de coleta não encontrado.")
            if ponto.status != StatusPontoColeta.ATIVO:
                raise RegraNegocioViolada(
                    "A revisão periódica se aplica apenas a pontos de coleta ativos."
                )

            situacao = DocumentoPontoService.situacao_documentos_obrigatorios(
                ponto.pk, referencia=hoje
            )
            if not situacao.todos_aprovados_validos:
                raise DocumentosObrigatoriosPendentes(
                    "Não é possível confirmar revisão periódica com documento obrigatório vencido "
                    "ou pendente."
                )

            ponto.ultima_revisao_em = agora
            ponto.save(update_fields=["ultima_revisao_em", "atualizado_em"])

            analise = AnalisePontoColeta.objects.create(
                ponto_coleta=ponto,
                tipo_acao=TipoAcaoAnalisePonto.REVISAO_PERIODICA,
                resultado=ResultadoAnalisePonto.APROVADO,
                status_anterior=StatusPontoColeta.ATIVO,
                status_novo=StatusPontoColeta.ATIVO,
                motivo=motivo_limpo,
                responsavel=ator,
            )
            AuditoriaService.registrar(
                acao="ponto_coleta.revisao_periodica",
                entidade_tipo="ponto_coleta",
                entidade_id=ponto.pk,
                ator=ator,
                motivo=motivo_limpo,
                detalhes={"ultima_revisao_em": agora.isoformat()},
            )
            return analise
