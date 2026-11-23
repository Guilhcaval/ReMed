from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

FUNCOES_ADMINISTRATIVAS: tuple[str, ...] = (
    "gestao_usuarios",
    "aprovacao_pontos_coleta",
    "conferencia_doacoes",
    "verificacao_receitas",
    "moderacao_denuncias",
    "metricas_e_parametros",
    "gestao_administradores",
    "auditoria",
)


class StatusUsuario(models.TextChoices):
    ATIVO = "ativo", "Ativo"
    INATIVO = "inativo", "Inativo"
    SUSPENSO = "suspenso", "Suspenso"
    BLOQUEADO = "bloqueado", "Bloqueado"


class TipoTokenConfirmacao(models.TextChoices):
    CADASTRO = "cadastro", "Confirmação de cadastro"
    ALTERACAO_EMAIL = "alteracao_email", "Confirmação de alteração de e-mail"


class EtapaAcesso(models.TextChoices):
    SENHA = "senha", "Senha"
    TOTP = "totp", "Código TOTP"
    CODIGO_RECUPERACAO = "codigo_recuperacao", "Código de recuperação"
    STEP_UP = "step_up", "Reconfirmação 2FA (step-up)"


class ResultadoAcesso(models.TextChoices):
    SUCESSO = "sucesso", "Sucesso"
    FALHA = "falha", "Falha"
    BLOQUEADO = "bloqueado", "Bloqueado"


class TipoAcaoGestaoUsuario(models.TextChoices):
    ATIVAR = "ativar", "Ativar"
    INATIVAR = "inativar", "Inativar"
    SUSPENDER = "suspender", "Suspender"
    BLOQUEAR = "bloquear", "Bloquear"
    DESBLOQUEAR = "desbloquear", "Desbloquear"
    ALTERAR_FUNCOES_ADMIN = "alterar_funcoes_admin", "Alterar funções administrativas"
    RESETAR_2FA = "resetar_2fa", "Resetar 2FA"


class UsuarioManager(BaseUserManager):
    def create_user(
        self,
        email: str,
        cpf: str,
        password: str | None = None,
        **extra_fields,
    ):
        if not email:
            raise ValueError("E-mail é obrigatório.")
        if not cpf:
            raise ValueError("CPF é obrigatório.")

        email_normalizado = self.normalize_email(email).strip().lower()
        cpf_digitos = "".join(ch for ch in cpf if ch.isdigit())

        extra_fields.setdefault("status", StatusUsuario.ATIVO)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields["is_active"] = (
            extra_fields["status"] == StatusUsuario.ATIVO
            and extra_fields.get("anonimizado_em") is None
        )

        usuario = self.model(
            email=email_normalizado,
            cpf=cpf_digitos,
            **extra_fields,
        )
        if password:
            usuario.set_password(password)
        else:
            usuario.set_unusable_password()
        usuario.save(using=self._db)
        return usuario

    def create_superuser(
        self,
        email: str,
        cpf: str,
        password: str | None = None,
        **extra_fields,
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("status", StatusUsuario.ATIVO)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusuário deve ter is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusuário deve ter is_superuser=True.")

        return self.create_user(email=email, cpf=cpf, password=password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    nome_completo = models.CharField(max_length=120, blank=True)
    cpf = models.CharField(  # noqa: DJ001  # ADR 0007: NULL na anonimização LGPD
        max_length=11,
        null=True,
        blank=True,
    )
    data_nascimento = models.DateField(null=True, blank=True)
    email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    email_confirmado_em = models.DateTimeField(null=True, blank=True)
    celular = models.CharField(max_length=11, blank=True)

    perfil_doador = models.BooleanField(default=False)
    perfil_solicitante = models.BooleanField(default=False)
    perfil_cuidador = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20,
        choices=StatusUsuario.choices,
        default=StatusUsuario.ATIVO,
        db_index=True,
    )
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    anonimizado_em = models.DateTimeField(null=True, blank=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["cpf", "nome_completo"]

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"
        constraints = [
            models.UniqueConstraint(
                fields=["cpf"],
                condition=Q(cpf__isnull=False),
                name="uq_usuario_cpf_nao_nulo",
            ),
            models.UniqueConstraint(
                Lower("email"),
                condition=Q(email__isnull=False),
                name="uq_usuario_email_lower_nao_nulo",
            ),
            models.CheckConstraint(
                condition=Q(cpf__isnull=True) | Q(cpf__regex=r"^[0-9]{11}$"),
                name="ck_usuario_cpf_onze_digitos",
            ),
            models.CheckConstraint(
                condition=(
                    Q(anonimizado_em__isnull=True, email__isnull=False, cpf__isnull=False)
                    | Q(anonimizado_em__isnull=False, email__isnull=True, cpf__isnull=True)
                ),
                name="ck_usuario_anonimizacao_consistente",
            ),
            models.CheckConstraint(
                condition=(
                    Q(anonimizado_em__isnull=False)
                    | Q(is_superuser=True)
                    | Q(perfil_doador=True)
                    | Q(perfil_solicitante=True)
                    | Q(perfil_cuidador=True)
                ),
                name="ck_usuario_perfil_minimo",
            ),
        ]

    def __str__(self) -> str:
        return f"Usuário #{self.pk}"


class EnderecoUsuario(models.Model):
    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        related_name="endereco",
    )
    cep = models.CharField(max_length=8)
    logradouro = models.CharField(max_length=150)
    numero = models.CharField(max_length=20)
    bairro = models.CharField(max_length=100)
    municipio = models.CharField(max_length=100)
    estado = models.CharField(max_length=2)
    complemento = models.CharField(max_length=100, blank=True)
    latitude_aprox = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude_aprox = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        verbose_name = "Endereço de usuário"
        verbose_name_plural = "Endereços de usuários"
        constraints = [
            models.CheckConstraint(
                condition=Q(cep__regex=r"^[0-9]{8}$"),
                name="ck_endereco_usuario_cep_oito_digitos",
            ),
        ]

    def __str__(self) -> str:
        return f"Endereço do Usuário #{self.usuario_id}"


class AceiteTermo(models.Model):
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="aceites_termos",
    )
    versao_termos_uso = models.CharField(max_length=30)
    versao_politica_privacidade = models.CharField(max_length=30)
    aceito_em = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = "Aceite de termo"
        verbose_name_plural = "Aceites de termos"
        ordering = ["-aceito_em"]

    def __str__(self) -> str:
        return f"Aceite Usuário #{self.usuario_id} ({self.versao_termos_uso})"


class TokenConfirmacaoEmail(models.Model):
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="tokens_confirmacao_email",
    )
    tipo = models.CharField(max_length=20, choices=TipoTokenConfirmacao.choices)
    email_destino = models.EmailField(max_length=254)
    token_hash = models.CharField(max_length=64, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField(db_index=True)
    usado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Token de confirmação de e-mail"
        verbose_name_plural = "Tokens de confirmação de e-mail"

    def __str__(self) -> str:
        return f"Token #{self.pk} ({self.tipo})"


class RegistroAcesso(models.Model):
    """Registro append-only de tentativas de autenticação e 2FA (ADR 0009 / ADR 0011)."""

    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    # Acréscimo aprovado: HMAC-SHA256 com REMED_IDENTIFICADOR_HMAC_KEY (sem PII bruto).
    identificador_hash = models.CharField(max_length=64, db_index=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="registros_acesso",
    )
    ip_origem = models.GenericIPAddressField(db_index=True)
    etapa = models.CharField(
        max_length=25,
        choices=EtapaAcesso.choices,
        default=EtapaAcesso.SENHA,
    )
    resultado = models.CharField(
        max_length=20,
        choices=ResultadoAcesso.choices,
        db_index=True,
    )
    motivo_interno = models.CharField(max_length=60, blank=True)

    class Meta:
        verbose_name = "Registro de acesso"
        verbose_name_plural = "Registros de acesso"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["usuario", "criado_em"], name="idx_acesso_usuario_dt"),
            models.Index(fields=["ip_origem", "criado_em"], name="idx_acesso_ip_dt"),
            models.Index(fields=["identificador_hash", "criado_em"], name="idx_acesso_idhash_dt"),
        ]

    def __str__(self) -> str:
        return f"Acesso #{self.pk} ({self.etapa} - {self.resultado})"


class DispositivoTotp(models.Model):
    """Dispositivo autenticador TOTP (RFC 6238) para contas administrativas (ADR 0009)."""

    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        related_name="dispositivo_totp",
    )
    segredo = models.CharField(max_length=64)
    confirmado_em = models.DateTimeField(null=True, blank=True)
    ultimo_passo_usado = models.BigIntegerField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dispositivo TOTP"
        verbose_name_plural = "Dispositivos TOTP"

    def __str__(self) -> str:
        return f"Dispositivo TOTP Usuário #{self.usuario_id}"


class CodigoRecuperacaoTotp(models.Model):
    """Código de recuperação alfanumérico de uso único (salvo apenas como hash — ADR 0009)."""

    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="codigos_recuperacao_totp",
    )
    codigo_hash = models.CharField(max_length=128)
    criado_em = models.DateTimeField(auto_now_add=True)
    usado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Código de recuperação TOTP"
        verbose_name_plural = "Códigos de recuperação TOTP"
        indexes = [
            models.Index(fields=["usuario", "usado_em"], name="idx_cod_rec_usuario_usado"),
        ]

    def __str__(self) -> str:
        return f"Código recuperação #{self.pk} (Usuário #{self.usuario_id})"


class SessaoUsuario(models.Model):
    """Índice auxiliar ligando o usuário à session_key em django_session para revogação rápida."""

    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="sessoes_ativas",
    )
    session_key = models.CharField(max_length=40, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Sessão de usuário"
        verbose_name_plural = "Sessões de usuários"
        indexes = [
            models.Index(fields=["usuario", "criado_em"], name="idx_sessao_usuario_dt"),
        ]

    def __str__(self) -> str:
        return f"Sessão Usuário #{self.usuario_id}"


class AcaoGestaoUsuario(models.Model):
    """Histórico estruturado append-only das ações administrativas do RF004 (Spec 04)."""

    usuario_alvo = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="acoes_gestao_recebidas",
    )
    responsavel = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="acoes_gestao_executadas",
    )
    acao = models.CharField(
        max_length=30,
        choices=TipoAcaoGestaoUsuario.choices,
        db_index=True,
    )
    status_anterior = models.CharField(
        max_length=20,
        choices=StatusUsuario.choices,
        blank=True,
    )
    status_novo = models.CharField(
        max_length=20,
        choices=StatusUsuario.choices,
        blank=True,
    )
    funcoes_anteriores = models.JSONField(null=True, blank=True)
    funcoes_novas = models.JSONField(null=True, blank=True)
    motivo = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Ação de gestão de usuário"
        verbose_name_plural = "Ações de gestão de usuários"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["usuario_alvo", "criado_em"], name="idx_acao_gestao_alvo_dt"),
            models.Index(fields=["responsavel", "criado_em"], name="idx_acao_gestao_resp_dt"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(motivo__regex=r"[^[:space:]]"),
                name="ck_acao_gestao_motivo_nao_vazio",
            ),
        ]

    def __str__(self) -> str:
        return f"Ação #{self.pk} ({self.acao} -> Usuário #{self.usuario_alvo_id})"
