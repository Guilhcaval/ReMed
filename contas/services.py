"""Camada de services do app contas (Specs 01 e 02 — ADR 0001)."""

import hashlib
import hmac
import ipaddress
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pyotp
import segno
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Page, Paginator
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from auditoria.services import AuditoriaService
from contas.backends import buscar_usuario_por_identificador
from contas.exceptions import (
    AcumuloFuncoesProibido,
    AlteracaoCpfProibida,
    CodigoRecuperacaoInvalido,
    CodigoTotpInvalido,
    ContaAnonimizadaImutavel,
    ContaBloqueadaTemporariamente,
    ContaIndisponivel,
    CpfJaCadastrado,
    CredenciaisInvalidas,
    EmailJaCadastrado,
    EmailNaoConfirmado,
    EncerramentoContaBloqueado,
    MotivoObrigatorio,
    ResetTotpNaoPermitido,
    SenhaAtualInvalida,
    TokenConfirmacaoInvalido,
    TotpBloqueadoTemporariamente,
    TotpJaAtivado,
    TotpNaoConfigurado,
    UltimoAdministradorAtivo,
)
from contas.models import (
    FUNCOES_ADMINISTRATIVAS,
    AcaoGestaoUsuario,
    AceiteTermo,
    CodigoRecuperacaoTotp,
    DispositivoTotp,
    EnderecoUsuario,
    EtapaAcesso,
    RegistroAcesso,
    ResultadoAcesso,
    SessaoUsuario,
    StatusUsuario,
    TipoAcaoGestaoUsuario,
    TipoTokenConfirmacao,
    TokenConfirmacaoEmail,
    Usuario,
)
from notificacoes.models import TipoNotificacao
from notificacoes.services import NotificacaoService
from nucleo.exceptions import PermissaoNegada, RecursoNaoEncontrado, RegraNegocioViolada
from nucleo.services import CepService
from nucleo.validators import (
    mascarar_cpf,
    normalizar_email,
    somente_digitos,
    validar_celular,
    validar_cep,
    validar_cpf,
    validar_maioridade,
    validar_uf,
)

NOME_MIN_CARACTERES = 3
NOME_MAX_CARACTERES = 120
SENHA_MIN_CARACTERES = 8
TOTP_INTERVALO_SEGUNDOS = 30
TOTP_JANELA_TOLERANCIA = 1
ALFABETO_CODIGO_RECUPERACAO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ETAPAS_2FA: tuple[str, ...] = (
    EtapaAcesso.TOTP,
    EtapaAcesso.CODIGO_RECUPERACAO,
    EtapaAcesso.STEP_UP,
)

MENSAGENS_STATUS_INDISPONIVEL: dict[str, str] = {
    StatusUsuario.INATIVO: (
        "Sua conta está inativa no momento. Entre em contato com a equipe do ReMed "
        "para orientações sobre reativação."
    ),
    StatusUsuario.SUSPENSO: (
        "Sua conta está temporariamente suspensa pela administração. "
        "Consulte o e-mail de notificação para mais informações."
    ),
    StatusUsuario.BLOQUEADO: (
        "Sua conta está bloqueada pela administração e não pode acessar o sistema."
    ),
}


@dataclass(frozen=True)
class DadosEndereco:
    cep: str
    logradouro: str
    numero: str
    bairro: str
    municipio: str
    estado: str
    complemento: str = ""


@dataclass(frozen=True)
class DadosCadastroUsuario:
    nome_completo: str
    cpf: str
    data_nascimento: date
    email: str
    celular: str
    senha: str
    perfil_doador: bool
    perfil_solicitante: bool
    perfil_cuidador: bool
    aceite_termos: bool
    endereco: DadosEndereco


@dataclass(frozen=True)
class DadosAtualizacaoPerfil:
    nome_completo: str
    data_nascimento: date
    email: str
    celular: str
    perfil_doador: bool
    perfil_solicitante: bool
    perfil_cuidador: bool
    endereco: DadosEndereco
    cpf_enviado: str | None = None


@dataclass(frozen=True)
class PerfilUsuario:
    usuario: Usuario
    endereco: EnderecoUsuario | None
    email_pendente: str | None


@dataclass(frozen=True)
class ResultadoAtualizacaoPerfil:
    usuario: Usuario
    campos_alterados: tuple[str, ...]
    troca_email_pendente: str | None


@dataclass(frozen=True)
class ResultadoConfirmacaoEmail:
    usuario: Usuario
    tipo: str


@dataclass(frozen=True)
class ResultadoAutenticacao:
    usuario: Usuario
    exige_2fa: bool
    totp_ativo: bool


@dataclass(frozen=True)
class DadosPareamentoTotp:
    segredo_manual: str
    uri_otpauth: str
    qr_svg_data_uri: str


def _hash_token(token_claro: str) -> str:
    return hashlib.sha256(token_claro.encode("utf-8")).hexdigest()


def hash_identificador_acesso(identificador_normalizado: str) -> str:
    """Calcula HMAC-SHA256 com REMED_IDENTIFICADOR_HMAC_KEY (sem PII bruto em RegistroAcesso)."""
    valor = (identificador_normalizado or "").strip().lower()
    chave = settings.REMED_IDENTIFICADOR_HMAC_KEY.encode("utf-8")
    return hmac.new(chave, valor.encode("utf-8"), hashlib.sha256).hexdigest()


def _normalizar_ip(ip_origem: str) -> str:
    candidato = (ip_origem or "").strip()
    try:
        return str(ipaddress.ip_address(candidato))
    except ValueError:
        return "127.0.0.1"


def _validar_nome_completo(nome: str) -> str:
    limpo = (nome or "").strip()
    if len(limpo) < NOME_MIN_CARACTERES or len(limpo) > NOME_MAX_CARACTERES:
        raise RegraNegocioViolada(
            "Campo preenchido incorretamente: o nome completo deve ter entre 3 e 120 caracteres."
        )
    return limpo


def _validar_email_formato(email: str) -> str:
    normalizado = normalizar_email(email)
    try:
        validate_email(normalizado)
    except DjangoValidationError as erro:
        raise RegraNegocioViolada(
            "Campo preenchido incorretamente: informe um endereço de e-mail válido."
        ) from erro
    return normalizado


def _validar_senha_cadastro(senha: str) -> str:
    if not senha or len(senha) < SENHA_MIN_CARACTERES:
        raise RegraNegocioViolada(
            "Campo preenchido incorretamente: a senha deve ter no mínimo 8 caracteres."
        )
    # Acréscimo da especificação (aprovado): aplica os validadores nativos configurados em settings.
    try:
        validate_password(senha)
    except DjangoValidationError as erro:
        orientacao = " ".join(erro.messages)
        raise RegraNegocioViolada(f"Campo preenchido incorretamente: {orientacao}") from erro
    return senha


def _validar_perfis(doador: bool, solicitante: bool, cuidador: bool) -> list[str]:
    perfis: list[str] = []
    if doador:
        perfis.append("doador")
    if solicitante:
        perfis.append("solicitante")
    if cuidador:
        perfis.append("cuidador")
    if not perfis:
        raise RegraNegocioViolada(
            "Campo(s) obrigatório(s) não preenchido(s): selecione ao menos um perfil de uso."
        )
    return perfis


def _validar_endereco(endereco: DadosEndereco) -> DadosEndereco:
    try:
        cep = validar_cep(endereco.cep)
        estado = validar_uf(endereco.estado)
    except ValueError as erro:
        raise RegraNegocioViolada(f"Campo preenchido incorretamente: {erro}") from erro

    logradouro = (endereco.logradouro or "").strip()
    numero = (endereco.numero or "").strip()
    bairro = (endereco.bairro or "").strip()
    municipio = (endereco.municipio or "").strip()
    complemento = (endereco.complemento or "").strip()

    if not all([logradouro, numero, bairro, municipio]):
        raise RegraNegocioViolada("Campo(s) obrigatório(s) não preenchido(s)")

    return DadosEndereco(
        cep=cep,
        logradouro=logradouro[:150],
        numero=numero[:20],
        bairro=bairro[:100],
        municipio=municipio[:100],
        estado=estado,
        complemento=complemento[:100],
    )


def _verificar_agendamentos_confirmados_noop(usuario: Usuario) -> bool:
    """Gancho padrão até o app correspondencias existir.

    TODO(Etapa 7 / Spec 16 — RF018): consultar correspondencias.Agendamento para retornar True
    quando o usuário possuir agendamento confirmado em andamento, bloqueando encerrar_conta.
    """
    _ = usuario
    return False


def _cancelar_pendencias_usuario_noop(usuario: Usuario) -> None:
    """Gancho padrão até os apps medicamentos e solicitacoes existirem.

    TODO(Etapa 5 / Spec 08 — RF008 e Etapa 6 / Spec 12 — RF013): cancelar automaticamente
    doações com status "disponível" e solicitações com status "aberta" do usuário,
    notificando a outra parte vinculada via NotificacaoService.
    """
    _ = usuario


class SessaoService:
    """Gerencia o índice SessaoUsuario acoplado à tabela django_session (ADR 0009)."""

    @staticmethod
    def registrar_sessao(usuario_id: int, session_key: str) -> SessaoUsuario | None:
        if not session_key:
            return None
        sessao, _ = SessaoUsuario.objects.update_or_create(
            session_key=session_key,
            defaults={"usuario_id": usuario_id},
        )
        return sessao

    @staticmethod
    def remover_sessao(session_key: str | None) -> None:
        if not session_key:
            return
        SessaoUsuario.objects.filter(session_key=session_key).delete()

    @staticmethod
    def encerrar_todas_sessoes(usuario_id: int) -> int:
        """Remove todas as sessões ativas da conta em django_session e SessaoUsuario."""
        agora = timezone.now()
        alvo = str(usuario_id)
        with transaction.atomic():
            chaves = set(
                SessaoUsuario.objects.filter(usuario_id=usuario_id).values_list(
                    "session_key", flat=True
                )
            )
            # Complementa com sessões ainda não indexadas em SessaoUsuario (ex.: force_login).
            for sessao in (
                Session.objects.filter(expire_date__gte=agora)
                .exclude(session_key__in=chaves)
                .iterator()
            ):
                dados = sessao.get_decoded()
                if str(dados.get("_auth_user_id")) == alvo:
                    chaves.add(sessao.session_key)

            removidas = 0
            if chaves:
                removidas, _ = Session.objects.filter(session_key__in=chaves).delete()
            SessaoUsuario.objects.filter(usuario_id=usuario_id).delete()
            return removidas


class UsuarioService:
    """Regras de negócio de cadastro, confirmação de e-mail, perfil e encerramento LGPD."""

    @staticmethod
    def _gerar_e_enfileirar_token(
        *,
        usuario: Usuario,
        tipo: str,
        email_destino: str,
        construir_url_confirmacao: Callable[[str], str],
    ) -> TokenConfirmacaoEmail:
        agora = timezone.now()
        token_claro = secrets.token_urlsafe(32)
        expira_em = agora + timedelta(hours=settings.REMED_CONFIRMACAO_EMAIL_EXPIRACAO_HORAS)
        token_obj = TokenConfirmacaoEmail.objects.create(
            usuario=usuario,
            tipo=tipo,
            email_destino=email_destino,
            token_hash=_hash_token(token_claro),
            expira_em=expira_em,
        )
        link_confirmacao = construir_url_confirmacao(token_claro)
        NotificacaoService.enfileirar_email_confirmacao(
            destinatario=usuario,
            email_destino=email_destino,
            link_confirmacao=link_confirmacao,
        )
        return token_obj

    @staticmethod
    def cadastrar(
        dados: DadosCadastroUsuario,
        *,
        construir_url_confirmacao: Callable[[str], str],
    ) -> Usuario:
        if not dados.aceite_termos:
            raise RegraNegocioViolada(
                "Campo(s) obrigatório(s) não preenchido(s): aceite os Termos de Uso e a "
                "Política de Privacidade."
            )

        nome_completo = _validar_nome_completo(dados.nome_completo)
        try:
            cpf_limpo = validar_cpf(dados.cpf)
            validar_maioridade(dados.data_nascimento)
            celular_limpo = validar_celular(dados.celular)
        except ValueError as erro:
            raise RegraNegocioViolada(f"Campo preenchido incorretamente: {erro}") from erro

        email_normalizado = _validar_email_formato(dados.email)
        senha_validada = _validar_senha_cadastro(dados.senha)
        perfis_ativos = _validar_perfis(
            dados.perfil_doador,
            dados.perfil_solicitante,
            dados.perfil_cuidador,
        )
        endereco_validado = _validar_endereco(dados.endereco)

        with transaction.atomic():
            if Usuario.objects.filter(cpf=cpf_limpo).exists():
                raise CpfJaCadastrado()
            if (
                Usuario.objects.annotate(email_lower=Lower("email"))
                .filter(email_lower=email_normalizado)
                .exists()
            ):
                raise EmailJaCadastrado()

            try:
                usuario = Usuario.objects.create_user(
                    email=email_normalizado,
                    cpf=cpf_limpo,
                    password=senha_validada,
                    nome_completo=nome_completo,
                    data_nascimento=dados.data_nascimento,
                    celular=celular_limpo,
                    perfil_doador=dados.perfil_doador,
                    perfil_solicitante=dados.perfil_solicitante,
                    perfil_cuidador=dados.perfil_cuidador,
                    status=StatusUsuario.ATIVO,
                )
            except IntegrityError as erro:
                detalhe_erro = str(erro).lower()
                if "cpf" in detalhe_erro:
                    raise CpfJaCadastrado() from erro
                if "email" in detalhe_erro:
                    raise EmailJaCadastrado() from erro
                raise

            latitude_aprox, longitude_aprox = CepService.obter_coordenadas_em_cache(
                endereco_validado.cep
            )
            EnderecoUsuario.objects.create(
                usuario=usuario,
                cep=endereco_validado.cep,
                logradouro=endereco_validado.logradouro,
                numero=endereco_validado.numero,
                bairro=endereco_validado.bairro,
                municipio=endereco_validado.municipio,
                estado=endereco_validado.estado,
                complemento=endereco_validado.complemento,
                latitude_aprox=latitude_aprox,
                longitude_aprox=longitude_aprox,
            )

            versao_atual = settings.REMED_TERMOS_VERSAO_ATUAL
            AceiteTermo.objects.create(
                usuario=usuario,
                versao_termos_uso=versao_atual,
                versao_politica_privacidade=versao_atual,
                aceito_em=timezone.now(),
            )

            UsuarioService._gerar_e_enfileirar_token(
                usuario=usuario,
                tipo=TipoTokenConfirmacao.CADASTRO,
                email_destino=email_normalizado,
                construir_url_confirmacao=construir_url_confirmacao,
            )

            AuditoriaService.registrar(
                acao="usuario.cadastrado",
                entidade_tipo="usuario",
                entidade_id=usuario.pk,
                ator=usuario,
                detalhes={
                    "perfis": perfis_ativos,
                    "versao_termos_uso": versao_atual,
                    "versao_politica_privacidade": versao_atual,
                },
            )
            return usuario

    @staticmethod
    def confirmar_email(token_claro: str) -> ResultadoConfirmacaoEmail:
        valor_limpo = (token_claro or "").strip()
        if not valor_limpo:
            raise TokenConfirmacaoInvalido()

        agora = timezone.now()
        token_hash = _hash_token(valor_limpo)

        with transaction.atomic():
            token = (
                TokenConfirmacaoEmail.objects.select_for_update()
                .filter(token_hash=token_hash)
                .first()
            )
            if token is None or token.usado_em is not None or token.expira_em <= agora:
                raise TokenConfirmacaoInvalido()

            usuario = Usuario.objects.select_for_update().get(pk=token.usuario_id)
            if usuario.anonimizado_em is not None:
                raise TokenConfirmacaoInvalido()

            if token.tipo == TipoTokenConfirmacao.CADASTRO:
                if usuario.email != token.email_destino:
                    raise TokenConfirmacaoInvalido()
                usuario.email_confirmado_em = agora
                usuario.save(update_fields=["email_confirmado_em", "atualizado_em"])
            elif token.tipo == TipoTokenConfirmacao.ALTERACAO_EMAIL:
                novo_email = normalizar_email(token.email_destino)
                em_uso = (
                    Usuario.objects.annotate(email_lower=Lower("email"))
                    .filter(email_lower=novo_email)
                    .exclude(pk=usuario.pk)
                    .exists()
                )
                if em_uso:
                    raise EmailJaCadastrado()
                usuario.email = novo_email
                usuario.email_confirmado_em = agora
                try:
                    usuario.save(update_fields=["email", "email_confirmado_em", "atualizado_em"])
                except IntegrityError as erro:
                    raise EmailJaCadastrado() from erro
            else:
                raise TokenConfirmacaoInvalido()

            token.usado_em = agora
            token.save(update_fields=["usado_em"])

            TokenConfirmacaoEmail.objects.filter(
                usuario=usuario,
                tipo=token.tipo,
                usado_em__isnull=True,
            ).exclude(pk=token.pk).update(usado_em=agora)

            AuditoriaService.registrar(
                acao="usuario.email_confirmado",
                entidade_tipo="usuario",
                entidade_id=usuario.pk,
                ator=usuario,
                detalhes={"tipo_confirmacao": token.tipo},
            )
            return ResultadoConfirmacaoEmail(usuario=usuario, tipo=token.tipo)

    @staticmethod
    def reenviar_confirmacao_email(
        email: str,
        *,
        construir_url_confirmacao: Callable[[str], str],
    ) -> bool:
        email_normalizado = normalizar_email(email)
        if not email_normalizado:
            return False

        agora = timezone.now()
        with transaction.atomic():
            usuario = (
                Usuario.objects.select_for_update()
                .annotate(email_lower=Lower("email"))
                .filter(
                    email_lower=email_normalizado,
                    status=StatusUsuario.ATIVO,
                    anonimizado_em__isnull=True,
                    email_confirmado_em__isnull=True,
                )
                .first()
            )
            if usuario is None:
                return False

            TokenConfirmacaoEmail.objects.filter(
                usuario=usuario,
                tipo=TipoTokenConfirmacao.CADASTRO,
                usado_em__isnull=True,
            ).update(usado_em=agora)

            UsuarioService._gerar_e_enfileirar_token(
                usuario=usuario,
                tipo=TipoTokenConfirmacao.CADASTRO,
                email_destino=usuario.email,
                construir_url_confirmacao=construir_url_confirmacao,
            )
            return True

    @staticmethod
    def obter_perfil(usuario_id: int) -> PerfilUsuario:
        usuario = (
            Usuario.objects.select_related("endereco")
            .filter(pk=usuario_id, anonimizado_em__isnull=True)
            .first()
        )
        if usuario is None:
            raise RecursoNaoEncontrado("Usuário não encontrado.")

        try:
            endereco = usuario.endereco
        except EnderecoUsuario.DoesNotExist:
            endereco = None

        token_pendente = (
            TokenConfirmacaoEmail.objects.filter(
                usuario=usuario,
                tipo=TipoTokenConfirmacao.ALTERACAO_EMAIL,
                usado_em__isnull=True,
                expira_em__gt=timezone.now(),
            )
            .order_by("-criado_em")
            .first()
        )
        email_pendente = token_pendente.email_destino if token_pendente is not None else None
        return PerfilUsuario(usuario=usuario, endereco=endereco, email_pendente=email_pendente)

    @staticmethod
    def atualizar_perfil(
        usuario_id: int,
        dados: DadosAtualizacaoPerfil,
        *,
        construir_url_confirmacao: Callable[[str], str],
    ) -> ResultadoAtualizacaoPerfil:
        nome_completo = _validar_nome_completo(dados.nome_completo)
        try:
            validar_maioridade(dados.data_nascimento)
            celular_limpo = validar_celular(dados.celular)
        except ValueError as erro:
            raise RegraNegocioViolada(f"Campo preenchido incorretamente: {erro}") from erro

        email_normalizado = _validar_email_formato(dados.email)
        _validar_perfis(dados.perfil_doador, dados.perfil_solicitante, dados.perfil_cuidador)
        endereco_validado = _validar_endereco(dados.endereco)

        agora = timezone.now()
        with transaction.atomic():
            usuario = (
                Usuario.objects.select_for_update()
                .filter(pk=usuario_id, anonimizado_em__isnull=True)
                .first()
            )
            if usuario is None:
                raise RecursoNaoEncontrado("Usuário não encontrado.")

            if dados.cpf_enviado is not None and somente_digitos(dados.cpf_enviado) != usuario.cpf:
                raise AlteracaoCpfProibida()

            campos_alterados: list[str] = []
            campos_usuario_update: list[str] = []

            comparacoes_usuario = (
                ("nome_completo", nome_completo),
                ("data_nascimento", dados.data_nascimento),
                ("celular", celular_limpo),
                ("perfil_doador", dados.perfil_doador),
                ("perfil_solicitante", dados.perfil_solicitante),
                ("perfil_cuidador", dados.perfil_cuidador),
            )
            for nome_campo, novo_valor in comparacoes_usuario:
                if getattr(usuario, nome_campo) != novo_valor:
                    setattr(usuario, nome_campo, novo_valor)
                    campos_usuario_update.append(nome_campo)
                    campos_alterados.append(nome_campo)

            if campos_usuario_update:
                campos_usuario_update.append("atualizado_em")
                usuario.save(update_fields=campos_usuario_update)

            troca_email_pendente: str | None = None
            if email_normalizado != usuario.email:
                em_uso = (
                    Usuario.objects.annotate(email_lower=Lower("email"))
                    .filter(email_lower=email_normalizado)
                    .exclude(pk=usuario.pk)
                    .exists()
                )
                if em_uso:
                    raise EmailJaCadastrado()

                TokenConfirmacaoEmail.objects.filter(
                    usuario=usuario,
                    tipo=TipoTokenConfirmacao.ALTERACAO_EMAIL,
                    usado_em__isnull=True,
                ).update(usado_em=agora)

                UsuarioService._gerar_e_enfileirar_token(
                    usuario=usuario,
                    tipo=TipoTokenConfirmacao.ALTERACAO_EMAIL,
                    email_destino=email_normalizado,
                    construir_url_confirmacao=construir_url_confirmacao,
                )
                troca_email_pendente = email_normalizado
                campos_alterados.append("solicitacao_alteracao_email")

            endereco_atual = EnderecoUsuario.objects.filter(usuario=usuario).first()
            endereco_mudou = False
            if endereco_atual is None:
                lat, lon = CepService.obter_coordenadas_em_cache(endereco_validado.cep)
                EnderecoUsuario.objects.create(
                    usuario=usuario,
                    cep=endereco_validado.cep,
                    logradouro=endereco_validado.logradouro,
                    numero=endereco_validado.numero,
                    bairro=endereco_validado.bairro,
                    municipio=endereco_validado.municipio,
                    estado=endereco_validado.estado,
                    complemento=endereco_validado.complemento,
                    latitude_aprox=lat,
                    longitude_aprox=lon,
                )
                endereco_mudou = True
            else:
                cep_mudou = endereco_atual.cep != endereco_validado.cep
                campos_end = (
                    ("cep", endereco_validado.cep),
                    ("logradouro", endereco_validado.logradouro),
                    ("numero", endereco_validado.numero),
                    ("bairro", endereco_validado.bairro),
                    ("municipio", endereco_validado.municipio),
                    ("estado", endereco_validado.estado),
                    ("complemento", endereco_validado.complemento),
                )
                campos_end_update: list[str] = []
                for nome_campo, novo_valor in campos_end:
                    if getattr(endereco_atual, nome_campo) != novo_valor:
                        setattr(endereco_atual, nome_campo, novo_valor)
                        campos_end_update.append(nome_campo)
                if cep_mudou:
                    lat, lon = CepService.obter_coordenadas_em_cache(endereco_validado.cep)
                    endereco_atual.latitude_aprox = lat
                    endereco_atual.longitude_aprox = lon
                    campos_end_update.extend(["latitude_aprox", "longitude_aprox"])
                if campos_end_update:
                    endereco_atual.save(update_fields=campos_end_update)
                    endereco_mudou = True

            if endereco_mudou:
                campos_alterados.append("endereco")

            if campos_alterados:
                AuditoriaService.registrar(
                    acao="usuario.perfil_alterado",
                    entidade_tipo="usuario",
                    entidade_id=usuario.pk,
                    ator=usuario,
                    detalhes={"campos_alterados": sorted(campos_alterados)},
                )

            return ResultadoAtualizacaoPerfil(
                usuario=usuario,
                campos_alterados=tuple(sorted(campos_alterados)),
                troca_email_pendente=troca_email_pendente,
            )

    @staticmethod
    def encerrar_conta(
        usuario: Usuario,
        senha_atual: str,
        *,
        verificador_agendamentos_confirmados: Callable[[Usuario], bool] | None = None,
        cancelador_pendencias_usuario: Callable[[Usuario], None] | None = None,
    ) -> None:
        verificar_agendamentos = (
            verificador_agendamentos_confirmados
            if verificador_agendamentos_confirmados is not None
            else _verificar_agendamentos_confirmados_noop
        )
        cancelar_pendencias = (
            cancelador_pendencias_usuario
            if cancelador_pendencias_usuario is not None
            else _cancelar_pendencias_usuario_noop
        )

        agora = timezone.now()
        with transaction.atomic():
            conta = Usuario.objects.select_for_update().filter(pk=usuario.pk).first()
            if conta is None or conta.anonimizado_em is not None:
                raise RecursoNaoEncontrado("Usuário não encontrado.")

            if conta.status in {StatusUsuario.SUSPENSO, StatusUsuario.BLOQUEADO}:
                raise EncerramentoContaBloqueado()

            if not senha_atual or not conta.check_password(senha_atual):
                raise SenhaAtualInvalida()

            if verificar_agendamentos(conta):
                raise RegraNegocioViolada(
                    "Não é possível encerrar a conta enquanto houver agendamentos confirmados "
                    "em andamento. Conclua ou cancele os agendamentos antes de continuar."
                )

            cancelar_pendencias(conta)

            conta.email = None
            conta.cpf = None
            conta.nome_completo = ""
            conta.celular = ""
            conta.data_nascimento = None
            conta.perfil_doador = False
            conta.perfil_solicitante = False
            conta.perfil_cuidador = False
            conta.status = StatusUsuario.INATIVO
            conta.is_active = False
            conta.anonimizado_em = agora
            conta.set_unusable_password()
            conta.save(
                update_fields=[
                    "email",
                    "cpf",
                    "nome_completo",
                    "celular",
                    "data_nascimento",
                    "perfil_doador",
                    "perfil_solicitante",
                    "perfil_cuidador",
                    "status",
                    "is_active",
                    "anonimizado_em",
                    "password",
                    "atualizado_em",
                ]
            )

            EnderecoUsuario.objects.filter(usuario_id=conta.pk).delete()
            TokenConfirmacaoEmail.objects.filter(usuario_id=conta.pk).delete()
            SessaoService.encerrar_todas_sessoes(conta.pk)

            AuditoriaService.registrar(
                acao="usuario.conta_encerrada",
                entidade_tipo="usuario",
                entidade_id=conta.pk,
                ator=conta,
                detalhes={"anonimizado": True},
            )


class AutenticacaoService:
    """Autenticação por e-mail ou CPF, bloqueio de 15 min e registro append-only (Spec 02)."""

    @staticmethod
    def obter_funcoes_administrativas(usuario: Usuario) -> frozenset[str]:
        """Retorna as funções administrativas explícitas da conta (ignora is_superuser)."""
        return frozenset(
            usuario.groups.filter(name__in=FUNCOES_ADMINISTRATIVAS).values_list("name", flat=True)
        )

    @staticmethod
    def possui_funcao_administrativa(usuario: Usuario) -> bool:
        """Retorna True somente se a conta possui ao menos uma das 8 funções explícitas."""
        return usuario.groups.filter(name__in=FUNCOES_ADMINISTRATIVAS).exists()

    @staticmethod
    def possui_funcao(usuario: Usuario, nome_funcao: str) -> bool:
        """Verifica função administrativa explícita (ignora is_superuser — ADR 0010)."""
        if nome_funcao not in FUNCOES_ADMINISTRATIVAS:
            return False
        return usuario.groups.filter(name=nome_funcao).exists()

    @staticmethod
    def possui_totp_ativo(usuario: Usuario) -> bool:
        return DispositivoTotp.objects.filter(
            usuario=usuario,
            confirmado_em__isnull=False,
        ).exists()

    @staticmethod
    def _registrar_acesso(
        *,
        identificador_hash: str,
        ip_origem: str,
        resultado: str,
        etapa: str = EtapaAcesso.SENHA,
        usuario: Usuario | None = None,
        motivo_interno: str = "",
    ) -> RegistroAcesso:
        return RegistroAcesso.objects.create(
            identificador_hash=identificador_hash,
            usuario=usuario,
            ip_origem=ip_origem,
            etapa=etapa,
            resultado=resultado,
            motivo_interno=motivo_interno[:60],
        )

    @staticmethod
    def _esta_bloqueado_por_falhas(
        *,
        usuario: Usuario | None,
        identificador_hash: str,
        etapas: tuple[str, ...],
        max_tentativas: int,
        agora: datetime,
    ) -> bool:
        janela = timedelta(minutes=settings.REMED_LOGIN_JANELA_MINUTOS)
        duracao_bloqueio = timedelta(minutes=settings.REMED_LOGIN_BLOQUEIO_MINUTOS)

        filtro_alvo = (
            {"usuario": usuario}
            if usuario is not None
            else {"identificador_hash": identificador_hash}
        )

        ultimo_sucesso = (
            RegistroAcesso.objects.filter(
                **filtro_alvo,
                etapa__in=etapas,
                resultado=ResultadoAcesso.SUCESSO,
            )
            .order_by("-criado_em")
            .values_list("criado_em", flat=True)
            .first()
        )

        falhas_qs = RegistroAcesso.objects.filter(
            **filtro_alvo,
            etapa__in=etapas,
            resultado=ResultadoAcesso.FALHA,
        )
        if ultimo_sucesso is not None:
            falhas_qs = falhas_qs.filter(criado_em__gt=ultimo_sucesso)

        ultima_falha_em = (
            falhas_qs.order_by("-criado_em").values_list("criado_em", flat=True).first()
        )
        if ultima_falha_em is None:
            return False

        if ultima_falha_em + duracao_bloqueio <= agora:
            return False

        falhas_na_janela = falhas_qs.filter(
            criado_em__gte=ultima_falha_em - janela,
            criado_em__lte=ultima_falha_em,
        ).count()
        return falhas_na_janela >= max_tentativas

    @staticmethod
    def autenticar(
        identificador: str,
        senha: str,
        ip_origem: str,
        *,
        momento: datetime | None = None,
    ) -> ResultadoAutenticacao:
        agora = momento if momento is not None else timezone.now()
        ip_limpo = _normalizar_ip(ip_origem)
        identificador_norm, usuario = buscar_usuario_por_identificador(identificador)
        id_hash = hash_identificador_acesso(identificador_norm or "vazio")

        # Limite secundário por IP contra password spraying (acréscimo aprovado).
        inicio_janela = agora - timedelta(minutes=settings.REMED_LOGIN_JANELA_MINUTOS)
        falhas_ip = RegistroAcesso.objects.filter(
            ip_origem=ip_limpo,
            etapa=EtapaAcesso.SENHA,
            resultado=ResultadoAcesso.FALHA,
            criado_em__gte=inicio_janela,
        ).count()
        if falhas_ip >= settings.REMED_LOGIN_LIMITE_IP_TENTATIVAS:
            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=usuario,
                ip_origem=ip_limpo,
                resultado=ResultadoAcesso.BLOQUEADO,
                motivo_interno="limite_ip",
            )
            raise ContaBloqueadaTemporariamente()

        # Bloqueio por conta (5 falhas/15 min unificando e-mail e CPF -> bloqueio de 15 min).
        if AutenticacaoService._esta_bloqueado_por_falhas(
            usuario=usuario,
            identificador_hash=id_hash,
            etapas=(EtapaAcesso.SENHA,),
            max_tentativas=settings.REMED_LOGIN_MAX_TENTATIVAS,
            agora=agora,
        ):
            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=usuario,
                ip_origem=ip_limpo,
                resultado=ResultadoAcesso.BLOQUEADO,
                motivo_interno="limite_tentativas",
            )
            raise ContaBloqueadaTemporariamente()

        # Validação da senha primeiro (tempo constante para identificador inexistente — OWASP A07).
        if usuario is None:
            Usuario().set_password(senha or "")
            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=None,
                ip_origem=ip_limpo,
                resultado=ResultadoAcesso.FALHA,
                motivo_interno="identificador_inexistente",
            )
            raise CredenciaisInvalidas()

        if not senha or not usuario.check_password(senha):
            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=usuario,
                ip_origem=ip_limpo,
                resultado=ResultadoAcesso.FALHA,
                motivo_interno="senha_invalida",
            )
            raise CredenciaisInvalidas()

        # Orientações específicas somente após confirmar que a senha confere (RN-02-02 / FE-03).
        if usuario.email_confirmado_em is None:
            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=usuario,
                ip_origem=ip_limpo,
                resultado=ResultadoAcesso.FALHA,
                motivo_interno="email_nao_confirmado",
            )
            raise EmailNaoConfirmado()

        if usuario.status != StatusUsuario.ATIVO or not usuario.is_active:
            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=usuario,
                ip_origem=ip_limpo,
                resultado=ResultadoAcesso.FALHA,
                motivo_interno=f"conta_{usuario.status}",
            )
            mensagem = MENSAGENS_STATUS_INDISPONIVEL.get(
                usuario.status,
                "Esta conta não está disponível para acesso no momento.",
            )
            raise ContaIndisponivel(usuario.status, mensagem)

        AutenticacaoService._registrar_acesso(
            identificador_hash=id_hash,
            usuario=usuario,
            ip_origem=ip_limpo,
            resultado=ResultadoAcesso.SUCESSO,
        )

        exige_2fa = AutenticacaoService.possui_funcao_administrativa(usuario)
        totp_ativo = AutenticacaoService.possui_totp_ativo(usuario) if exige_2fa else False
        return ResultadoAutenticacao(
            usuario=usuario,
            exige_2fa=exige_2fa,
            totp_ativo=totp_ativo,
        )


def _gerar_qr_svg_data_uri(uri_otpauth: str) -> str:
    """Gera QR code SVG localmente via segno como data URI (evita |safe no template)."""
    qr = segno.make(uri_otpauth, error="m")
    return qr.svg_data_uri(scale=5, border=2, dark="#17466b", light="#ffffff")


def _normalizar_codigo_recuperacao(codigo: str) -> str:
    return "".join(ch for ch in (codigo or "").upper() if ch.isalnum())


def _gerar_codigos_recuperacao_claros(quantidade: int) -> list[str]:
    codigos: list[str] = []
    for _ in range(quantidade):
        parte_1 = "".join(secrets.choice(ALFABETO_CODIGO_RECUPERACAO) for _ in range(4))
        parte_2 = "".join(secrets.choice(ALFABETO_CODIGO_RECUPERACAO) for _ in range(4))
        codigos.append(f"{parte_1}-{parte_2}")
    return codigos


def _validar_passo_totp(segredo: str, codigo: str, agora: datetime) -> int | None:
    """Retorna o passo de tempo (counter) correspondente ao código válido ou None."""
    digitos = somente_digitos(codigo)
    if len(digitos) != 6:
        return None
    totp = pyotp.TOTP(segredo, interval=TOTP_INTERVALO_SEGUNDOS)
    passo_atual = int(agora.timestamp() // TOTP_INTERVALO_SEGUNDOS)
    for deslocamento in range(-TOTP_JANELA_TOLERANCIA, TOTP_JANELA_TOLERANCIA + 1):
        passo_candidato = passo_atual + deslocamento
        if passo_candidato < 0:
            continue
        codigo_esperado = totp.at(passo_candidato * TOTP_INTERVALO_SEGUNDOS)
        if hmac.compare_digest(digitos, codigo_esperado):
            return passo_candidato
    return None


class TotpService:
    """Serviço de 2FA TOTP (RFC 6238), códigos de recuperação, step-up e reset (ADR 0009)."""

    @staticmethod
    def _identificador_hash_usuario(usuario: Usuario) -> str:
        return hash_identificador_acesso(usuario.email or str(usuario.pk))

    @staticmethod
    def _criar_lote_codigos_recuperacao(usuario: Usuario) -> list[str]:
        qtd = settings.REMED_TOTP_CODIGOS_RECUPERACAO_QTD
        codigos_claros = _gerar_codigos_recuperacao_claros(qtd)
        objetos = [
            CodigoRecuperacaoTotp(
                usuario=usuario,
                codigo_hash=make_password(_normalizar_codigo_recuperacao(codigo)),
            )
            for codigo in codigos_claros
        ]
        CodigoRecuperacaoTotp.objects.bulk_create(objetos)
        return codigos_claros

    @staticmethod
    def iniciar_pareamento(usuario: Usuario) -> DadosPareamentoTotp:
        if not AutenticacaoService.possui_funcao_administrativa(usuario):
            raise PermissaoNegada("Apenas contas com função administrativa configuram 2FA.")

        with transaction.atomic():
            dispositivo = (
                DispositivoTotp.objects.select_for_update().filter(usuario=usuario).first()
            )
            if dispositivo is not None and dispositivo.confirmado_em is not None:
                raise TotpJaAtivado()

            if dispositivo is None:
                dispositivo = DispositivoTotp.objects.create(
                    usuario=usuario,
                    segredo=pyotp.random_base32(),
                )

            uri = pyotp.TOTP(dispositivo.segredo).provisioning_uri(
                name=usuario.email or f"admin-{usuario.pk}",
                issuer_name=settings.REMED_TOTP_ISSUER,
            )
            return DadosPareamentoTotp(
                segredo_manual=dispositivo.segredo,
                uri_otpauth=uri,
                qr_svg_data_uri=_gerar_qr_svg_data_uri(uri),
            )

    @staticmethod
    def confirmar_pareamento(
        usuario: Usuario,
        codigo: str,
        ip_origem: str,
        *,
        momento: datetime | None = None,
    ) -> list[str]:
        if not AutenticacaoService.possui_funcao_administrativa(usuario):
            raise PermissaoNegada("Apenas contas com função administrativa configuram 2FA.")

        agora = momento if momento is not None else timezone.now()
        ip_limpo = _normalizar_ip(ip_origem)
        id_hash = TotpService._identificador_hash_usuario(usuario)

        if AutenticacaoService._esta_bloqueado_por_falhas(
            usuario=usuario,
            identificador_hash=id_hash,
            etapas=ETAPAS_2FA,
            max_tentativas=settings.REMED_2FA_MAX_TENTATIVAS,
            agora=agora,
        ):
            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=usuario,
                ip_origem=ip_limpo,
                etapa=EtapaAcesso.TOTP,
                resultado=ResultadoAcesso.BLOQUEADO,
                motivo_interno="limite_2fa",
            )
            raise TotpBloqueadoTemporariamente()

        dispositivo_atual = DispositivoTotp.objects.filter(usuario=usuario).first()
        if dispositivo_atual is None:
            raise TotpNaoConfigurado()
        if dispositivo_atual.confirmado_em is not None:
            raise TotpJaAtivado()

        passo = _validar_passo_totp(dispositivo_atual.segredo, codigo, agora)
        if passo is None:
            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=usuario,
                ip_origem=ip_limpo,
                etapa=EtapaAcesso.TOTP,
                resultado=ResultadoAcesso.FALHA,
                motivo_interno="pareamento_totp_invalido",
            )
            if AutenticacaoService._esta_bloqueado_por_falhas(
                usuario=usuario,
                identificador_hash=id_hash,
                etapas=ETAPAS_2FA,
                max_tentativas=settings.REMED_2FA_MAX_TENTATIVAS,
                agora=agora,
            ):
                raise TotpBloqueadoTemporariamente()
            raise CodigoTotpInvalido()

        with transaction.atomic():
            dispositivo = DispositivoTotp.objects.select_for_update().get(usuario=usuario)
            if dispositivo.confirmado_em is not None:
                raise TotpJaAtivado()
            dispositivo.confirmado_em = agora
            dispositivo.ultimo_passo_usado = passo
            dispositivo.save(update_fields=["confirmado_em", "ultimo_passo_usado", "atualizado_em"])

            CodigoRecuperacaoTotp.objects.filter(usuario=usuario).delete()
            codigos_claros = TotpService._criar_lote_codigos_recuperacao(usuario)

            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=usuario,
                ip_origem=ip_limpo,
                etapa=EtapaAcesso.TOTP,
                resultado=ResultadoAcesso.SUCESSO,
                motivo_interno="pareamento_confirmado",
            )
            AuditoriaService.registrar(
                acao="usuario.totp_ativado",
                entidade_tipo="usuario",
                entidade_id=usuario.pk,
                ator=usuario,
                detalhes={"qtd_codigos_recuperacao": len(codigos_claros)},
            )
            return codigos_claros

    @staticmethod
    def verificar_codigo(
        usuario: Usuario,
        codigo: str,
        ip_origem: str,
        *,
        etapa: str = EtapaAcesso.TOTP,
        momento: datetime | None = None,
    ) -> None:
        agora = momento if momento is not None else timezone.now()
        ip_limpo = _normalizar_ip(ip_origem)
        id_hash = TotpService._identificador_hash_usuario(usuario)

        if AutenticacaoService._esta_bloqueado_por_falhas(
            usuario=usuario,
            identificador_hash=id_hash,
            etapas=ETAPAS_2FA,
            max_tentativas=settings.REMED_2FA_MAX_TENTATIVAS,
            agora=agora,
        ):
            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=usuario,
                ip_origem=ip_limpo,
                etapa=etapa,
                resultado=ResultadoAcesso.BLOQUEADO,
                motivo_interno="limite_2fa",
            )
            raise TotpBloqueadoTemporariamente()

        motivo_falha = ""
        with transaction.atomic():
            dispositivo = (
                DispositivoTotp.objects.select_for_update()
                .filter(usuario=usuario, confirmado_em__isnull=False)
                .first()
            )
            if dispositivo is None:
                raise TotpNaoConfigurado()

            passo = _validar_passo_totp(dispositivo.segredo, codigo, agora)
            if passo is None:
                motivo_falha = "totp_invalido"
            elif (
                dispositivo.ultimo_passo_usado is not None
                and passo <= dispositivo.ultimo_passo_usado
            ):
                motivo_falha = "totp_replay"
            else:
                dispositivo.ultimo_passo_usado = passo
                dispositivo.save(update_fields=["ultimo_passo_usado", "atualizado_em"])
                AutenticacaoService._registrar_acesso(
                    identificador_hash=id_hash,
                    usuario=usuario,
                    ip_origem=ip_limpo,
                    etapa=etapa,
                    resultado=ResultadoAcesso.SUCESSO,
                )
                return

        AutenticacaoService._registrar_acesso(
            identificador_hash=id_hash,
            usuario=usuario,
            ip_origem=ip_limpo,
            etapa=etapa,
            resultado=ResultadoAcesso.FALHA,
            motivo_interno=motivo_falha,
        )
        if AutenticacaoService._esta_bloqueado_por_falhas(
            usuario=usuario,
            identificador_hash=id_hash,
            etapas=ETAPAS_2FA,
            max_tentativas=settings.REMED_2FA_MAX_TENTATIVAS,
            agora=agora,
        ):
            raise TotpBloqueadoTemporariamente()
        raise CodigoTotpInvalido()

    @staticmethod
    def verificar_step_up(
        usuario: Usuario,
        codigo: str,
        ip_origem: str,
        *,
        momento: datetime | None = None,
    ) -> None:
        """Reconfirmação imediata de código TOTP para ações críticas (RF004 / regeneração)."""
        TotpService.verificar_codigo(
            usuario,
            codigo,
            ip_origem,
            etapa=EtapaAcesso.STEP_UP,
            momento=momento,
        )

    @staticmethod
    def consumir_codigo_recuperacao(
        usuario: Usuario,
        codigo: str,
        ip_origem: str,
        *,
        momento: datetime | None = None,
    ) -> int:
        agora = momento if momento is not None else timezone.now()
        ip_limpo = _normalizar_ip(ip_origem)
        id_hash = TotpService._identificador_hash_usuario(usuario)

        if AutenticacaoService._esta_bloqueado_por_falhas(
            usuario=usuario,
            identificador_hash=id_hash,
            etapas=ETAPAS_2FA,
            max_tentativas=settings.REMED_2FA_MAX_TENTATIVAS,
            agora=agora,
        ):
            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=usuario,
                ip_origem=ip_limpo,
                etapa=EtapaAcesso.CODIGO_RECUPERACAO,
                resultado=ResultadoAcesso.BLOQUEADO,
                motivo_interno="limite_2fa",
            )
            raise TotpBloqueadoTemporariamente()

        codigo_norm = _normalizar_codigo_recuperacao(codigo)
        if not codigo_norm:
            AutenticacaoService._registrar_acesso(
                identificador_hash=id_hash,
                usuario=usuario,
                ip_origem=ip_limpo,
                etapa=EtapaAcesso.CODIGO_RECUPERACAO,
                resultado=ResultadoAcesso.FALHA,
                motivo_interno="codigo_recuperacao_invalido",
            )
            raise CodigoRecuperacaoInvalido()

        with transaction.atomic():
            if not DispositivoTotp.objects.filter(
                usuario=usuario, confirmado_em__isnull=False
            ).exists():
                raise TotpNaoConfigurado()

            codigos_disponiveis = list(
                CodigoRecuperacaoTotp.objects.select_for_update().filter(
                    usuario=usuario,
                    usado_em__isnull=True,
                )
            )
            encontrado: CodigoRecuperacaoTotp | None = None
            for candidato in codigos_disponiveis:
                if check_password(codigo_norm, candidato.codigo_hash):
                    encontrado = candidato
                    break

            if encontrado is not None:
                encontrado.usado_em = agora
                encontrado.save(update_fields=["usado_em"])
                restantes = len(codigos_disponiveis) - 1
                AutenticacaoService._registrar_acesso(
                    identificador_hash=id_hash,
                    usuario=usuario,
                    ip_origem=ip_limpo,
                    etapa=EtapaAcesso.CODIGO_RECUPERACAO,
                    resultado=ResultadoAcesso.SUCESSO,
                )
                AuditoriaService.registrar(
                    acao="usuario.codigo_recuperacao_usado",
                    entidade_tipo="usuario",
                    entidade_id=usuario.pk,
                    ator=usuario,
                    detalhes={"codigos_restantes": restantes},
                )
                return restantes

        AutenticacaoService._registrar_acesso(
            identificador_hash=id_hash,
            usuario=usuario,
            ip_origem=ip_limpo,
            etapa=EtapaAcesso.CODIGO_RECUPERACAO,
            resultado=ResultadoAcesso.FALHA,
            motivo_interno="codigo_recuperacao_invalido",
        )
        if AutenticacaoService._esta_bloqueado_por_falhas(
            usuario=usuario,
            identificador_hash=id_hash,
            etapas=ETAPAS_2FA,
            max_tentativas=settings.REMED_2FA_MAX_TENTATIVAS,
            agora=agora,
        ):
            raise TotpBloqueadoTemporariamente()
        raise CodigoRecuperacaoInvalido()

    @staticmethod
    def regenerar_codigos_recuperacao(
        usuario: Usuario,
        codigo_step_up: str,
        ip_origem: str,
        *,
        momento: datetime | None = None,
    ) -> list[str]:
        if not AutenticacaoService.possui_funcao_administrativa(usuario):
            raise PermissaoNegada("Apenas contas administrativas possuem códigos de recuperação.")

        agora = momento if momento is not None else timezone.now()
        TotpService.verificar_step_up(usuario, codigo_step_up, ip_origem, momento=agora)

        with transaction.atomic():
            CodigoRecuperacaoTotp.objects.select_for_update().filter(
                usuario=usuario,
                usado_em__isnull=True,
            ).update(usado_em=agora)
            novos_codigos = TotpService._criar_lote_codigos_recuperacao(usuario)
            AuditoriaService.registrar(
                acao="usuario.codigos_recuperacao_regenerados",
                entidade_tipo="usuario",
                entidade_id=usuario.pk,
                ator=usuario,
                detalhes={"qtd_codigos_recuperacao": len(novos_codigos)},
            )
            return novos_codigos

    @staticmethod
    def resetar_por_administrador(
        ator: Usuario,
        usuario_alvo: Usuario,
        codigo_step_up: str,
        ip_origem: str,
        *,
        motivo: str = "Reset administrativo de 2FA",
        momento: datetime | None = None,
    ) -> None:
        if ator.pk == usuario_alvo.pk:
            raise ResetTotpNaoPermitido("Um Administrador não pode resetar o próprio 2FA.")

        if not AutenticacaoService.possui_funcao(ator, "gestao_administradores"):
            raise ResetTotpNaoPermitido(
                "Apenas Administradores com função gestão de administradores podem resetar o 2FA."
            )

        motivo_limpo = (motivo or "").strip()
        if not motivo_limpo:
            raise MotivoObrigatorio("Informe o motivo do reset de 2FA.")

        admins_ativos = (
            Usuario.objects.filter(
                groups__name="gestao_administradores",
                status=StatusUsuario.ATIVO,
                email_confirmado_em__isnull=False,
                anonimizado_em__isnull=True,
            )
            .distinct()
            .count()
        )
        if admins_ativos < 2:
            raise ResetTotpNaoPermitido(
                "O reset de 2FA exige ao menos dois Administradores ativos com "
                "gestão de administradores."
            )

        TotpService.verificar_step_up(ator, codigo_step_up, ip_origem, momento=momento)

        with transaction.atomic():
            DispositivoTotp.objects.filter(usuario=usuario_alvo).delete()
            CodigoRecuperacaoTotp.objects.filter(usuario=usuario_alvo).delete()
            SessaoService.encerrar_todas_sessoes(usuario_alvo.pk)
            AcaoGestaoUsuario.objects.create(
                usuario_alvo=usuario_alvo,
                responsavel=ator,
                acao=TipoAcaoGestaoUsuario.RESETAR_2FA,
                motivo=motivo_limpo,
            )
            AuditoriaService.registrar(
                acao="usuario.totp_resetado",
                entidade_tipo="usuario",
                entidade_id=usuario_alvo.pk,
                ator=ator,
                motivo=motivo_limpo,
                detalhes={"reset_por_administrador": True},
            )
            if usuario_alvo.anonimizado_em is None:
                NotificacaoService.registrar_evento(
                    destinatario=usuario_alvo,
                    tipo=TipoNotificacao.SEGURANCA_CONTA,
                    contexto={
                        "evento_seguranca": (
                            "Sua autenticação em dois fatores (2FA) foi resetada por um "
                            "Administrador. Configure o novo dispositivo no próximo acesso."
                        )
                    },
                )


ROTULOS_FUNCOES_ADMIN: dict[str, str] = {
    "gestao_usuarios": "Gestão de usuários",
    "aprovacao_pontos_coleta": "Aprovação de pontos de coleta",
    "conferencia_doacoes": "Conferência de doações",
    "verificacao_receitas": "Verificação de receitas",
    "moderacao_denuncias": "Moderação de denúncias",
    "metricas_e_parametros": "Métricas e parâmetros",
    "gestao_administradores": "Gestão de administradores",
    "auditoria": "Auditoria (somente leitura)",
}

USUARIOS_ADMIN_POR_PAGINA = 20
CPF_PARCIAL_MIN_DIGITOS = 3


@dataclass(frozen=True)
class FiltrosConsultaUsuarios:
    termo: str = ""
    email: str = ""
    perfil: str = ""
    status: str = ""
    data_inicio: date | None = None
    data_fim: date | None = None


@dataclass(frozen=True)
class ResumoUsuarioAdmin:
    """Projeção minimizada para o Administrador (RN-04-07 — sem CPF bruto, endereço ou receitas)."""

    id: int
    nome_completo: str
    cpf_mascarado: str
    email: str
    perfis_cidadao: tuple[str, ...]
    funcoes_admin: tuple[str, ...]
    funcoes_admin_rotulos: tuple[str, ...]
    status: str
    status_display: str
    criado_em: datetime
    email_confirmado: bool
    anonimizado: bool
    totp_ativo: bool


@dataclass(frozen=True)
class PaginaUsuariosAdmin:
    pagina: Page
    total_encontrados: int


@dataclass(frozen=True)
class DetalheUsuarioAdmin:
    resumo: ResumoUsuarioAdmin
    historico_acoes: tuple[AcaoGestaoUsuario, ...]
    pode_alterar_status: bool
    pode_gerir_funcoes: bool
    pode_resetar_2fa: bool
    eh_proprio_usuario: bool


def _cancelar_operacoes_abertas_noop(usuario_alvo: Usuario) -> None:
    """Gancho padrão até os apps medicamentos e correspondencias existirem.

    TODO(Spec 08 — RF008, Spec 15 — RF016 e Spec 16 — RF018): garantir ocultação dinâmica
    de doações disponíveis (doador.status == ativo) e cancelar transacionalmente reservas
    e agendamentos em aberto sob select_for_update() na ordem fixa da ADR 0013, notificando
    a outra parte vinculada via NotificacaoService.
    """
    _ = usuario_alvo


def _projetar_resumo_usuario(usuario: Usuario) -> ResumoUsuarioAdmin:
    perfis: list[str] = []
    if usuario.perfil_doador:
        perfis.append("Doador")
    if usuario.perfil_solicitante:
        perfis.append("Solicitante")
    if usuario.perfil_cuidador:
        perfis.append("Cuidador/Familiar")

    funcoes = tuple(
        sorted(
            grupo.name for grupo in usuario.groups.all() if grupo.name in FUNCOES_ADMINISTRATIVAS
        )
    )
    try:
        dispositivo = usuario.dispositivo_totp
        totp_ativo = dispositivo.confirmado_em is not None
    except DispositivoTotp.DoesNotExist:
        totp_ativo = False

    anonimizado = usuario.anonimizado_em is not None
    nome_exibicao = f"Usuário encerrado (#{usuario.pk})" if anonimizado else usuario.nome_completo
    email_exibicao = "—" if anonimizado or not usuario.email else usuario.email

    return ResumoUsuarioAdmin(
        id=usuario.pk,
        nome_completo=nome_exibicao,
        cpf_mascarado="—" if anonimizado else mascarar_cpf(usuario.cpf),
        email=email_exibicao,
        perfis_cidadao=tuple(perfis),
        funcoes_admin=funcoes,
        funcoes_admin_rotulos=tuple(ROTULOS_FUNCOES_ADMIN.get(f, f) for f in funcoes),
        status=usuario.status,
        status_display=usuario.get_status_display(),
        criado_em=usuario.criado_em,
        email_confirmado=usuario.email_confirmado_em is not None,
        anonimizado=anonimizado,
        totp_ativo=totp_ativo,
    )


def _travar_alvo_e_admins_ativos(usuario_alvo_id: int) -> tuple[Usuario | None, list[int]]:
    """Trava alvo e Admins ativos em ordem crescente de id (ADR 0013), evitando deadlock."""
    ids_admins = set(
        Usuario.objects.filter(
            groups__name="gestao_administradores",
            status=StatusUsuario.ATIVO,
            email_confirmado_em__isnull=False,
            anonimizado_em__isnull=True,
        ).values_list("id", flat=True)
    )
    ids_ordenados = sorted(ids_admins | {usuario_alvo_id})
    travados = list(Usuario.objects.select_for_update().filter(id__in=ids_ordenados).order_by("id"))
    alvo = next((u for u in travados if u.pk == usuario_alvo_id), None)
    return alvo, [u.pk for u in travados]


def _garantir_outro_admin_ativo_nos_travados(
    usuario_alvo_id: int,
    ids_travados: list[int],
) -> None:
    """Reavalia no banco o estado atual dos registros já travados sob FOR UPDATE."""
    existe_outro = (
        Usuario.objects.filter(
            id__in=ids_travados,
            groups__name="gestao_administradores",
            status=StatusUsuario.ATIVO,
            email_confirmado_em__isnull=False,
            anonimizado_em__isnull=True,
        )
        .exclude(pk=usuario_alvo_id)
        .exists()
    )
    if not existe_outro:
        raise UltimoAdministradorAtivo()


class GestaoUsuariosService:
    """Regras de negócio de consulta e gestão administrativa de usuários (Spec 04 / RF004)."""

    @staticmethod
    def _exigir_acesso_consulta(ator: Usuario) -> None:
        pode = AutenticacaoService.possui_funcao(
            ator, "gestao_usuarios"
        ) or AutenticacaoService.possui_funcao(ator, "gestao_administradores")
        if not pode:
            raise PermissaoNegada(
                "Apenas Administradores com gestão de usuários ou gestão de administradores "
                "podem consultar usuários."
            )

    @staticmethod
    def consultar(
        ator: Usuario,
        filtros: FiltrosConsultaUsuarios | None = None,
        *,
        pagina: int = 1,
        por_pagina: int = USUARIOS_ADMIN_POR_PAGINA,
    ) -> PaginaUsuariosAdmin:
        GestaoUsuariosService._exigir_acesso_consulta(ator)
        f = filtros if filtros is not None else FiltrosConsultaUsuarios()

        qs = (
            Usuario.objects.all()
            .select_related("dispositivo_totp")
            .prefetch_related("groups")
            .order_by("-criado_em", "-id")
        )

        termo = (f.termo or "").strip()
        if termo:
            somente_chars_cpf = all(ch.isdigit() or ch in ".- " for ch in termo)
            digitos = somente_digitos(termo)
            if somente_chars_cpf and digitos:
                if len(digitos) < CPF_PARCIAL_MIN_DIGITOS:
                    raise RegraNegocioViolada(
                        "Informe ao menos 3 dígitos para pesquisar por CPF parcial."
                    )
                qs = qs.filter(cpf__icontains=digitos)
            else:
                qs = qs.filter(nome_completo__icontains=termo)

        email_filtro = (f.email or "").strip()
        if email_filtro:
            qs = qs.filter(email__icontains=email_filtro)

        perfil_filtro = (f.perfil or "").strip()
        if perfil_filtro == "doador":
            qs = qs.filter(perfil_doador=True)
        elif perfil_filtro == "solicitante":
            qs = qs.filter(perfil_solicitante=True)
        elif perfil_filtro == "cuidador":
            qs = qs.filter(perfil_cuidador=True)
        elif perfil_filtro in FUNCOES_ADMINISTRATIVAS:
            qs = qs.filter(groups__name=perfil_filtro).distinct()

        if f.status and f.status in StatusUsuario.values:
            qs = qs.filter(status=f.status)

        if f.data_inicio is not None:
            inicio_dt = timezone.make_aware(datetime.combine(f.data_inicio, time.min))
            qs = qs.filter(criado_em__gte=inicio_dt)
        if f.data_fim is not None:
            fim_dt = timezone.make_aware(datetime.combine(f.data_fim, time.max))
            qs = qs.filter(criado_em__lte=fim_dt)

        paginador = Paginator(qs, por_pagina)
        page_obj = paginador.get_page(pagina)
        page_obj.object_list = [_projetar_resumo_usuario(u) for u in page_obj.object_list]
        return PaginaUsuariosAdmin(pagina=page_obj, total_encontrados=paginador.count)

    @staticmethod
    def obter_resumo_gestao(ator: Usuario, usuario_id: int) -> DetalheUsuarioAdmin:
        GestaoUsuariosService._exigir_acesso_consulta(ator)
        usuario = (
            Usuario.objects.select_related("dispositivo_totp")
            .prefetch_related("groups")
            .filter(pk=usuario_id)
            .first()
        )
        if usuario is None:
            raise RecursoNaoEncontrado("Usuário não encontrado.")

        resumo = _projetar_resumo_usuario(usuario)
        historico = tuple(
            AcaoGestaoUsuario.objects.filter(usuario_alvo_id=usuario.pk)
            .select_related("responsavel")
            .order_by("-criado_em")[:50]
        )

        tem_gestao_usuarios = AutenticacaoService.possui_funcao(ator, "gestao_usuarios")
        tem_gestao_admins = AutenticacaoService.possui_funcao(ator, "gestao_administradores")
        eh_proprio = ator.pk == usuario.pk

        admins_ativos = (
            Usuario.objects.filter(
                groups__name="gestao_administradores",
                status=StatusUsuario.ATIVO,
                email_confirmado_em__isnull=False,
                anonimizado_em__isnull=True,
            )
            .distinct()
            .count()
        )
        pode_gerir_funcoes = (
            tem_gestao_admins
            and not eh_proprio
            and not resumo.anonimizado
            and resumo.status == StatusUsuario.ATIVO
            and resumo.email_confirmado
        )
        pode_resetar_2fa = (
            tem_gestao_admins and not eh_proprio and resumo.totp_ativo and admins_ativos >= 2
        )

        return DetalheUsuarioAdmin(
            resumo=resumo,
            historico_acoes=historico,
            pode_alterar_status=tem_gestao_usuarios and not resumo.anonimizado,
            pode_gerir_funcoes=pode_gerir_funcoes,
            pode_resetar_2fa=pode_resetar_2fa,
            eh_proprio_usuario=eh_proprio,
        )

    @staticmethod
    def alterar_status(
        ator: Usuario,
        usuario_alvo_id: int,
        novo_status: str,
        motivo: str,
        *,
        cancelador_operacoes_abertas: Callable[[Usuario], None] | None = None,
    ) -> AcaoGestaoUsuario:
        if not AutenticacaoService.possui_funcao(ator, "gestao_usuarios"):
            raise PermissaoNegada(
                "Apenas Administradores com função gestão de usuários podem alterar status."
            )

        if novo_status not in StatusUsuario.values:
            raise RegraNegocioViolada("Status de usuário inválido.")

        motivo_limpo = (motivo or "").strip()
        if not motivo_limpo:
            if novo_status in {StatusUsuario.SUSPENSO, StatusUsuario.BLOQUEADO}:
                raise MotivoObrigatorio("Informe o motivo da suspensão ou do bloqueio")
            raise MotivoObrigatorio("Informe o motivo da alteração de status.")

        cancelar_operacoes = (
            cancelador_operacoes_abertas
            if cancelador_operacoes_abertas is not None
            else _cancelar_operacoes_abertas_noop
        )

        with transaction.atomic():
            if novo_status != StatusUsuario.ATIVO:
                alvo, ids_travados = _travar_alvo_e_admins_ativos(usuario_alvo_id)
            else:
                alvo = Usuario.objects.select_for_update().filter(pk=usuario_alvo_id).first()
                ids_travados = [alvo.pk] if alvo is not None else []
            if alvo is None:
                raise RecursoNaoEncontrado("Usuário não encontrado.")

            if alvo.anonimizado_em is not None:
                raise ContaAnonimizadaImutavel()

            if ator.pk == alvo.pk and novo_status != StatusUsuario.ATIVO:
                raise PermissaoNegada(
                    "Você não pode inativar, suspender ou bloquear a própria conta."
                )

            if alvo.status == novo_status:
                raise RegraNegocioViolada("O usuário já está com o status informado.")

            if novo_status != StatusUsuario.ATIVO and AutenticacaoService.possui_funcao(
                alvo, "gestao_administradores"
            ):
                _garantir_outro_admin_ativo_nos_travados(alvo.pk, ids_travados)

            status_anterior = alvo.status
            if novo_status == StatusUsuario.INATIVO:
                acao_tipo = TipoAcaoGestaoUsuario.INATIVAR
            elif novo_status == StatusUsuario.SUSPENSO:
                acao_tipo = TipoAcaoGestaoUsuario.SUSPENDER
            elif novo_status == StatusUsuario.BLOQUEADO:
                acao_tipo = TipoAcaoGestaoUsuario.BLOQUEAR
            elif status_anterior in {StatusUsuario.SUSPENSO, StatusUsuario.BLOQUEADO}:
                acao_tipo = TipoAcaoGestaoUsuario.DESBLOQUEAR
            else:
                acao_tipo = TipoAcaoGestaoUsuario.ATIVAR

            alvo.status = novo_status
            alvo.is_active = novo_status == StatusUsuario.ATIVO
            alvo.save(update_fields=["status", "is_active", "atualizado_em"])

            if novo_status in {
                StatusUsuario.INATIVO,
                StatusUsuario.SUSPENSO,
                StatusUsuario.BLOQUEADO,
            }:
                SessaoService.encerrar_todas_sessoes(alvo.pk)

            if novo_status in {StatusUsuario.SUSPENSO, StatusUsuario.BLOQUEADO}:
                cancelar_operacoes(alvo)

            acao_registro = AcaoGestaoUsuario.objects.create(
                usuario_alvo=alvo,
                responsavel=ator,
                acao=acao_tipo,
                status_anterior=status_anterior,
                status_novo=novo_status,
                motivo=motivo_limpo,
            )

            AuditoriaService.registrar(
                acao="usuario.status_alterado",
                entidade_tipo="usuario",
                entidade_id=alvo.pk,
                ator=ator,
                motivo=motivo_limpo,
                detalhes={
                    "acao": acao_tipo,
                    "status_anterior": status_anterior,
                    "status_novo": novo_status,
                },
            )

            if novo_status == StatusUsuario.SUSPENSO:
                msg_seguranca = f"Sua conta foi suspensa pela administração. Motivo: {motivo_limpo}"
            elif novo_status == StatusUsuario.BLOQUEADO:
                msg_seguranca = (
                    f"Sua conta foi bloqueada pela administração. Motivo: {motivo_limpo}"
                )
            elif novo_status == StatusUsuario.INATIVO:
                msg_seguranca = "Sua conta foi inativada pela administração."
            else:
                msg_seguranca = "Sua conta foi reativada pela administração e está liberada."

            NotificacaoService.registrar_evento(
                destinatario=alvo,
                tipo=TipoNotificacao.SEGURANCA_CONTA,
                contexto={"evento_seguranca": msg_seguranca},
            )
            return acao_registro

    @staticmethod
    def atualizar_funcoes_administrativas(
        ator: Usuario,
        usuario_alvo_id: int,
        funcoes: list[str] | tuple[str, ...] | set[str],
        codigo_step_up: str,
        motivo: str,
        ip_origem: str,
        *,
        momento: datetime | None = None,
    ) -> AcaoGestaoUsuario:
        if not AutenticacaoService.possui_funcao(ator, "gestao_administradores"):
            raise PermissaoNegada(
                "Apenas Administradores com função gestão de administradores podem alterar funções."
            )

        if ator.pk == usuario_alvo_id:
            raise PermissaoNegada(
                "Um Administrador não pode atribuir ou alterar as próprias funções administrativas."
            )

        motivo_limpo = (motivo or "").strip()
        if not motivo_limpo:
            raise MotivoObrigatorio("Informe o motivo da alteração de funções administrativas.")

        funcoes_limpas = {f.strip() for f in funcoes if f and f.strip()}
        invalidas = sorted(funcoes_limpas - set(FUNCOES_ADMINISTRATIVAS))
        if invalidas:
            raise RegraNegocioViolada(
                f"Função(ões) administrativa(s) inválida(s): {', '.join(invalidas)}."
            )

        if "gestao_usuarios" in funcoes_limpas and "verificacao_receitas" in funcoes_limpas:
            raise AcumuloFuncoesProibido()

        TotpService.verificar_step_up(ator, codigo_step_up, ip_origem, momento=momento)

        with transaction.atomic():
            if "gestao_administradores" not in funcoes_limpas:
                alvo, ids_travados = _travar_alvo_e_admins_ativos(usuario_alvo_id)
            else:
                alvo = Usuario.objects.select_for_update().filter(pk=usuario_alvo_id).first()
                ids_travados = [alvo.pk] if alvo is not None else []
            if alvo is None:
                raise RecursoNaoEncontrado("Usuário não encontrado.")

            if alvo.anonimizado_em is not None:
                raise ContaAnonimizadaImutavel()

            if alvo.status != StatusUsuario.ATIVO or alvo.email_confirmado_em is None:
                raise RegraNegocioViolada(
                    "Somente contas ativas com e-mail confirmado podem receber funções "
                    "administrativas."
                )

            funcoes_anteriores = sorted(
                alvo.groups.filter(name__in=FUNCOES_ADMINISTRATIVAS).values_list("name", flat=True)
            )
            funcoes_novas = sorted(funcoes_limpas)

            if (
                "gestao_administradores" in funcoes_anteriores
                and "gestao_administradores" not in funcoes_limpas
            ):
                _garantir_outro_admin_ativo_nos_travados(alvo.pk, ids_travados)

            grupos_admin_atuais = Group.objects.filter(name__in=FUNCOES_ADMINISTRATIVAS)
            alvo.groups.remove(*grupos_admin_atuais)
            if funcoes_novas:
                grupos_novos = [Group.objects.get_or_create(name=nome)[0] for nome in funcoes_novas]
                alvo.groups.add(*grupos_novos)

            recebeu_primeira_funcao_sem_2fa = (
                not funcoes_anteriores
                and bool(funcoes_novas)
                and not AutenticacaoService.possui_totp_ativo(alvo)
            )
            removeu_todas_funcoes = bool(funcoes_anteriores) and not funcoes_novas
            if recebeu_primeira_funcao_sem_2fa or removeu_todas_funcoes:
                SessaoService.encerrar_todas_sessoes(alvo.pk)

            adicionadas = sorted(set(funcoes_novas) - set(funcoes_anteriores))
            removidas = sorted(set(funcoes_anteriores) - set(funcoes_novas))

            acao_registro = AcaoGestaoUsuario.objects.create(
                usuario_alvo=alvo,
                responsavel=ator,
                acao=TipoAcaoGestaoUsuario.ALTERAR_FUNCOES_ADMIN,
                funcoes_anteriores=funcoes_anteriores,
                funcoes_novas=funcoes_novas,
                motivo=motivo_limpo,
            )

            AuditoriaService.registrar(
                acao="usuario.funcoes_admin_alteradas",
                entidade_tipo="usuario",
                entidade_id=alvo.pk,
                ator=ator,
                motivo=motivo_limpo,
                detalhes={"adicionadas": adicionadas, "removidas": removidas},
            )

            if recebeu_primeira_funcao_sem_2fa:
                msg_seguranca = (
                    "Você recebeu permissões administrativas no ReMed. Suas sessões anteriores "
                    "foram encerradas e você deverá configurar a autenticação em dois fatores "
                    "(2FA) no próximo acesso."
                )
            elif funcoes_novas:
                msg_seguranca = "Suas permissões administrativas no ReMed foram atualizadas."
            else:
                msg_seguranca = "Suas permissões administrativas no ReMed foram removidas."

            NotificacaoService.registrar_evento(
                destinatario=alvo,
                tipo=TipoNotificacao.SEGURANCA_CONTA,
                contexto={"evento_seguranca": msg_seguranca},
            )
            return acao_registro
