"""Camada de services do app contas (Spec 01 / RF001 — ADR 0001)."""

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from auditoria.services import AuditoriaService
from contas.exceptions import (
    AlteracaoCpfProibida,
    CpfJaCadastrado,
    EmailJaCadastrado,
    EncerramentoContaBloqueado,
    SenhaAtualInvalida,
    TokenConfirmacaoInvalido,
)
from contas.models import (
    AceiteTermo,
    EnderecoUsuario,
    StatusUsuario,
    TipoTokenConfirmacao,
    TokenConfirmacaoEmail,
    Usuario,
)
from notificacoes.services import NotificacaoService
from nucleo.exceptions import RecursoNaoEncontrado, RegraNegocioViolada
from nucleo.services import CepService
from nucleo.validators import (
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


def _hash_token(token_claro: str) -> str:
    return hashlib.sha256(token_claro.encode("utf-8")).hexdigest()


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


def _invalidar_sessoes_usuario(usuario_id: int) -> int:
    """Remove sessões ativas do usuário na tabela django_session (PostgreSQL)."""
    agora = timezone.now()
    alvo = str(usuario_id)
    chaves_para_remover: list[str] = []
    for sessao in Session.objects.filter(expire_date__gte=agora).iterator():
        dados = sessao.get_decoded()
        if str(dados.get("_auth_user_id")) == alvo:
            chaves_para_remover.append(sessao.session_key)
    if not chaves_para_remover:
        return 0
    removidas, _ = Session.objects.filter(session_key__in=chaves_para_remover).delete()
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
            _invalidar_sessoes_usuario(conta.pk)

            AuditoriaService.registrar(
                acao="usuario.conta_encerrada",
                entidade_tipo="usuario",
                entidade_id=conta.pk,
                ator=conta,
                detalhes={"anonimizado": True},
            )
