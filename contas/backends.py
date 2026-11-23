"""Backend de autenticação customizado: e-mail ou CPF, sem CNPJ (ADR 0007 / Spec 02)."""

from django.contrib.auth.backends import BaseBackend
from django.db.models.functions import Lower

from contas.models import StatusUsuario, Usuario
from nucleo.validators import normalizar_email, somente_digitos


def buscar_usuario_por_identificador(identificador: str) -> tuple[str, Usuario | None]:
    """Normaliza e-mail ou CPF (rejeitando CNPJ) e retorna (identificador_normalizado, usuario)."""
    bruto = (identificador or "").strip()
    if not bruto:
        return "", None

    if "@" in bruto:
        email_norm = normalizar_email(bruto)
        usuario = (
            Usuario.objects.annotate(email_lower=Lower("email"))
            .filter(email_lower=email_norm, anonimizado_em__isnull=True)
            .first()
        )
        return email_norm, usuario

    digitos = somente_digitos(bruto)
    # Rejeita CNPJ (14 dígitos) ou comprimentos inválidos (ADR 0007 / RN-02-01).
    if len(digitos) != 11:
        return bruto.lower(), None

    usuario = Usuario.objects.filter(cpf=digitos, anonimizado_em__isnull=True).first()
    return digitos, usuario


def usuario_pode_autenticar(usuario: Usuario) -> bool:
    return (
        usuario.status == StatusUsuario.ATIVO
        and usuario.email_confirmado_em is not None
        and usuario.anonimizado_em is None
        and usuario.is_active
    )


class EmailOuCpfBackend(BaseBackend):
    """Autentica somente por e-mail (case-insensitive) ou CPF (11 dígitos), nunca CNPJ."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identificador = username if username is not None else kwargs.get("email")
        if not identificador or not password:
            return None

        _, usuario = buscar_usuario_por_identificador(str(identificador))
        if usuario is None:
            # Executa hash fictício com o mesmo hasher Argon2id (mitigação de timing — OWASP A07).
            Usuario().set_password(password)
            return None

        if not usuario.check_password(password):
            return None

        if not usuario_pode_autenticar(usuario):
            return None

        return usuario

    def get_user(self, user_id):
        usuario = Usuario.objects.filter(pk=user_id, anonimizado_em__isnull=True).first()
        if usuario is None or not usuario_pode_autenticar(usuario):
            return None
        return usuario
