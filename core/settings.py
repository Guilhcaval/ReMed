"""Configurações base do projeto Django ReMed.

Consolida as ADRs 0001 a 0020. Segredos e credenciais vêm exclusivamente
de variáveis de ambiente (carregadas de `.env` em desenvolvimento via
python-dotenv com override=False, conforme ADR 0020).
"""

import hashlib
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env", override=False)


def _obter_env(nome: str, padrao: str | None = None, *, obrigatorio: bool = False) -> str:
    valor = os.environ.get(nome)
    if valor is None or valor == "":
        if obrigatorio and padrao is None:
            raise ImproperlyConfigured(
                f"Variável de ambiente obrigatória ausente: {nome}. "
                "Consulte .env.example para configurar o ambiente."
            )
        return padrao or ""
    return valor


def _obter_bool(nome: str, padrao: bool = False) -> bool:
    valor = os.environ.get(nome)
    if valor is None or valor == "":
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


def _obter_int(nome: str, padrao: int) -> int:
    valor = os.environ.get(nome)
    if valor is None or valor == "":
        return padrao
    try:
        return int(valor)
    except ValueError as erro:
        raise ImproperlyConfigured(
            f"Variável de ambiente {nome} deve ser um número inteiro."
        ) from erro


def _obter_lista(nome: str, padrao: list[str] | None = None) -> list[str]:
    valor = os.environ.get(nome)
    if valor is None or not valor.strip():
        return list(padrao or [])
    return [item.strip() for item in valor.split(",") if item.strip()]


# Segurança básica
DEBUG = _obter_bool("DJANGO_DEBUG", False)
SECRET_KEY = _obter_env("DJANGO_SECRET_KEY", obrigatorio=True)
ALLOWED_HOSTS = _obter_lista("DJANGO_ALLOWED_HOSTS", ["127.0.0.1", "localhost"] if DEBUG else [])
CSRF_TRUSTED_ORIGINS = _obter_lista("DJANGO_CSRF_TRUSTED_ORIGINS", [])

# Aplicações instaladas (apps de domínio entram conforme cada etapa do plano)
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "nucleo",
    "contas",
    "auditoria",
    "notificacoes",
    "pontos_coleta",
    "medicamentos",
]

AUTH_USER_MODEL = "contas.Usuario"
AUTHENTICATION_BACKENDS = ["contas.backends.EmailOuCpfBackend"]
LOGIN_URL = "/contas/entrar/"
LOGIN_REDIRECT_URL = "/contas/meu-perfil/"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "nucleo.context_processors.navegacao_global",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

# Banco de dados PostgreSQL (ADR 0002)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _obter_env("POSTGRES_DB", "remed"),
        "USER": _obter_env("POSTGRES_USER", "postgres"),
        "PASSWORD": _obter_env("POSTGRES_PASSWORD", ""),
        "HOST": _obter_env("POSTGRES_HOST", "127.0.0.1"),
        "PORT": _obter_env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": _obter_int("POSTGRES_CONN_MAX_AGE", 60),
    }
}

# Hash de senha Argon2id com parâmetros padrão do Django 6.1.3 (ADR 0008 / RS005)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# Validação de senhas (RF001 / RS005)
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internacionalização e fuso horário (USE_TZ = True — ADR 0011)
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# Arquivos estáticos hospedados no próprio projeto (ADR 0005)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Armazenamento privado local para dev e testes (fora de static/, sem URL pública — ADR 0016)
PRIVATE_STORAGE_ROOT = Path(
    _obter_env("REMED_PRIVATE_STORAGE_ROOT", str(BASE_DIR / "private_media"))
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sessão no PostgreSQL com expiração por inatividade de 30 minutos (ADR 0009)
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = _obter_int("REMED_SESSION_COOKIE_AGE", 1800)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Cabeçalhos e endurecimento de segurança (OWASP Top 10:2025 / RS005)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = _obter_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = _obter_int("DJANGO_SECURE_HSTS_SECONDS", 31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# E-mail (SMTP nativo em produção/homologação; console legível em desenvolvimento — ADR 0015)
EMAIL_BACKEND = _obter_env(
    "DJANGO_EMAIL_BACKEND",
    "notificacoes.backends.ConsoleEmailBackend"
    if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = _obter_env("EMAIL_HOST", "localhost")
EMAIL_PORT = _obter_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = _obter_env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = _obter_env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _obter_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = _obter_env("DEFAULT_FROM_EMAIL", "nao-responda@remed.local")

# Parâmetros configuráveis de negócio (consolidados das Specs 01 a 19)
REMED_CONFIRMACAO_EMAIL_EXPIRACAO_HORAS = _obter_int("REMED_CONFIRMACAO_EMAIL_EXPIRACAO_HORAS", 24)
REMED_CONFIRMACAO_EMAIL_REENVIO_LIMITE_HORA = _obter_int(
    "REMED_CONFIRMACAO_EMAIL_REENVIO_LIMITE_HORA", 5
)
REMED_TERMOS_VERSAO_ATUAL = _obter_env("REMED_TERMOS_VERSAO_ATUAL", "1.0-rascunho")
REMED_LOGIN_MAX_TENTATIVAS = _obter_int("REMED_LOGIN_MAX_TENTATIVAS", 5)
REMED_LOGIN_JANELA_MINUTOS = _obter_int("REMED_LOGIN_JANELA_MINUTOS", 15)
REMED_LOGIN_BLOQUEIO_MINUTOS = _obter_int("REMED_LOGIN_BLOQUEIO_MINUTOS", 15)
# Acréscimo da especificação (Spec 02 / ADR 0009): limite secundário por IP e limite de falhas 2FA
REMED_LOGIN_LIMITE_IP_TENTATIVAS = _obter_int("REMED_LOGIN_LIMITE_IP_TENTATIVAS", 20)
REMED_2FA_MAX_TENTATIVAS = _obter_int("REMED_2FA_MAX_TENTATIVAS", 5)
REMED_TOTP_ISSUER = _obter_env("REMED_TOTP_ISSUER", "ReMed")
REMED_TOTP_CODIGOS_RECUPERACAO_QTD = _obter_int("REMED_TOTP_CODIGOS_RECUPERACAO_QTD", 8)


def resolver_identificador_hmac_key(
    valor_env: str,
    secret_key: str,
    *,
    debug: bool,
    em_teste: bool,
) -> str:
    """Resolve a chave dedicada de HMAC para RegistroAcesso.identificador_hash.

    Em produção (DEBUG=False fora de testes), recusa iniciar sem REMED_IDENTIFICADOR_HMAC_KEY.
    """
    chave = (valor_env or "").strip()
    if chave:
        return chave
    if debug or em_teste:
        return hashlib.sha256(f"remed-dev-identificador-hmac:{secret_key}".encode()).hexdigest()
    raise ImproperlyConfigured(
        "Variável de ambiente obrigatória ausente em produção: REMED_IDENTIFICADOR_HMAC_KEY. "
        "Defina uma chave dedicada independente de DJANGO_SECRET_KEY (consulte .env.example)."
    )


REMED_IDENTIFICADOR_HMAC_KEY = resolver_identificador_hmac_key(
    _obter_env("REMED_IDENTIFICADOR_HMAC_KEY", ""),
    SECRET_KEY,
    debug=DEBUG,
    em_teste="test" in sys.argv,
)
REMED_NOTIFICACAO_EMAIL_LIMITE_HORA = _obter_int("REMED_NOTIFICACAO_EMAIL_LIMITE_HORA", 20)
# Acréscimo da especificação (Spec 03 / RN-03-05): limiar de falhas definitivas no lote SMTP
# para disparo de alerta operacional (gravado apenas na plataforma para evitar loop de SMTP).
REMED_NOTIFICACAO_ALERTA_FALHAS_LOTE = _obter_int("REMED_NOTIFICACAO_ALERTA_FALHAS_LOTE", 3)
REMED_PONTO_DOC_AVISO_VENCIMENTO_DIAS = _obter_int("REMED_PONTO_DOC_AVISO_VENCIMENTO_DIAS", 30)
REMED_PONTO_REVISAO_PERIODICA_DIAS = _obter_int("REMED_PONTO_REVISAO_PERIODICA_DIAS", 180)
REMED_REFRIGERADO_JANELA_MAX_MINUTOS = _obter_int("REMED_REFRIGERADO_JANELA_MAX_MINUTOS", 120)
REMED_VENCIMENTO_MAX_RETENTATIVAS = _obter_int("REMED_VENCIMENTO_MAX_RETENTATIVAS", 3)
REMED_VENCIMENTO_RETRY_INTERVALO_SEGUNDOS = _obter_int(
    "REMED_VENCIMENTO_RETRY_INTERVALO_SEGUNDOS", 900
)
REMED_NOMINATIM_INTERVALO_SEGUNDOS = _obter_int("REMED_NOMINATIM_INTERVALO_SEGUNDOS", 1)
REMED_SOLICITACOES_ABERTAS_MAX_POR_USUARIO = _obter_int(
    "REMED_SOLICITACOES_ABERTAS_MAX_POR_USUARIO", 5
)
REMED_SOLICITACAO_EXPIRACAO_DIAS = _obter_int("REMED_SOLICITACAO_EXPIRACAO_DIAS", 30)
REMED_CORRESPONDENCIA_ACEITE_HORAS = _obter_int("REMED_CORRESPONDENCIA_ACEITE_HORAS", 48)
REMED_RESERVA_EXPIRACAO_HORAS = _obter_int("REMED_RESERVA_EXPIRACAO_HORAS", 48)
REMED_AGENDAMENTO_LIMITE_ALTERACAO_HORAS = _obter_int("REMED_AGENDAMENTO_LIMITE_ALTERACAO_HORAS", 2)
REMED_ARQUIVO_TAMANHO_MAX_BYTES = _obter_int("REMED_ARQUIVO_TAMANHO_MAX_BYTES", 5 * 1024 * 1024)
REMED_ARQUIVO_URL_TEMPORARIA_SEGUNDOS = _obter_int("REMED_ARQUIVO_URL_TEMPORARIA_SEGUNDOS", 60)
REMED_CEP_CACHE_TTL_DIAS = _obter_int("REMED_CEP_CACHE_TTL_DIAS", 30)
# Acréscimo da especificação (Spec 01 / ADR 0018): limites configuráveis de taxa e timeout do CEP
REMED_CADASTRO_LIMITE_IP_HORA = _obter_int("REMED_CADASTRO_LIMITE_IP_HORA", 5)
REMED_CEP_RATE_LIMIT_IP_MINUTO = _obter_int("REMED_CEP_RATE_LIMIT_IP_MINUTO", 30)
REMED_CEP_TIMEOUT_SEGUNDOS = _obter_int("REMED_CEP_TIMEOUT_SEGUNDOS", 3)
REMED_CEP_USER_AGENT = _obter_env("REMED_CEP_USER_AGENT", "ReMed/1.0 (+https://remed.local)")

# Logging estruturado sem exposição de segredos ou dados pessoais
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "padrao": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "padrao",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": _obter_env("DJANGO_LOG_LEVEL", "INFO"),
    },
}
