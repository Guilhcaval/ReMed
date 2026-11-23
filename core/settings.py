"""Configurações base do projeto Django ReMed.

Consolida as ADRs 0001 a 0020. Segredos e credenciais vêm exclusivamente
de variáveis de ambiente (carregadas de `.env` em desenvolvimento via
python-dotenv com override=False, conforme ADR 0020).
"""

import os
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
]

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

# Validação de senhas (Argon2PasswordHasher entra na Etapa 1 com argon2-cffi — ADR 0008)
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

# E-mail (SMTP nativo em produção/homologação; console em desenvolvimento — ADR 0015)
EMAIL_BACKEND = _obter_env(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend"
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
REMED_NOTIFICACAO_EMAIL_LIMITE_HORA = _obter_int("REMED_NOTIFICACAO_EMAIL_LIMITE_HORA", 20)
REMED_PONTO_DOC_AVISO_VENCIMENTO_DIAS = _obter_int("REMED_PONTO_DOC_AVISO_VENCIMENTO_DIAS", 30)
REMED_PONTO_REVISAO_PERIODICA_DIAS = _obter_int("REMED_PONTO_REVISAO_PERIODICA_DIAS", 180)
REMED_REFRIGERADO_JANELA_MAX_MINUTOS = _obter_int("REMED_REFRIGERADO_JANELA_MAX_MINUTOS", 120)
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
