"""Bootstrap seguro pelo terminal do primeiro Administrador (ADR 0007 / ADR 0010 / Spec 02)."""

import getpass
import os
import sys
from datetime import date, datetime

from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models.functions import Lower
from django.utils import timezone

from auditoria.models import OrigemAuditoria
from auditoria.services import AuditoriaService
from contas.models import FUNCOES_ADMINISTRATIVAS, StatusUsuario, Usuario
from nucleo.validators import (
    normalizar_email,
    validar_celular,
    validar_cpf,
    validar_maioridade,
)


def _parse_data_nascimento(valor: str) -> date:
    texto = (valor or "").strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError("Informe a data de nascimento no formato dd/mm/aaaa ou aaaa-mm-dd.")


class Command(BaseCommand):
    help = (
        "Cria o primeiro Administrador do ReMed via terminal com CPF válido, senha oculta "
        "(getpass) e função explícita gestao_administradores (exige pareamento 2FA no 1º login)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", type=str, help="E-mail do Administrador.")
        parser.add_argument("--cpf", type=str, help="CPF válido (com ou sem máscara).")
        parser.add_argument("--nome-completo", type=str, help="Nome completo (3 a 120 caracteres).")
        parser.add_argument(
            "--data-nascimento",
            type=str,
            help="Data de nascimento (dd/mm/aaaa ou aaaa-mm-dd; maior de 18 anos).",
        )
        parser.add_argument("--celular", type=str, help="Celular com DDD (10 ou 11 dígitos).")
        parser.add_argument(
            "--funcoes",
            type=str,
            default="gestao_administradores",
            help=(
                "Lista separada por vírgula de funções administrativas "
                "(padrão: gestao_administradores)."
            ),
        )
        parser.add_argument(
            "--permitir-adicional",
            action="store_true",
            help="Permite criar novo Administrador mesmo se já existir um ativo no sistema.",
        )
        parser.add_argument(
            "--password-stdin",
            action="store_true",
            help="Lê a senha da entrada padrão (stdin) para automação/testes, sem expor em argv.",
        )

    def _ler_campo(self, valor: str | None, prompt: str) -> str:
        if valor is not None and valor.strip():
            return valor.strip()
        return input(prompt).strip()

    def _obter_senha(self, *, usar_stdin: bool) -> str:
        if usar_stdin:
            senha = sys.stdin.readline().rstrip("\r\n")
            if not senha:
                raise CommandError("Nenhuma senha recebida pela entrada padrão (stdin).")
            return senha

        senha_env = os.environ.get("REMED_BOOTSTRAP_ADMIN_PASSWORD", "")
        if senha_env:
            return senha_env

        senha_1 = getpass.getpass("Senha do Administrador (mínimo 8 caracteres): ")
        senha_2 = getpass.getpass("Confirme a senha: ")
        if senha_1 != senha_2:
            raise CommandError("As senhas digitadas não coincidem.")
        return senha_1

    def handle(self, *args, **options):
        ja_existe_admin = Usuario.objects.filter(
            groups__name="gestao_administradores",
            status=StatusUsuario.ATIVO,
            anonimizado_em__isnull=True,
        ).exists()
        if ja_existe_admin and not options["permitir_adicional"]:
            raise CommandError(
                "Já existe um Administrador ativo com gestao_administradores. "
                "Use a gestão de administradores pela interface ou passe --permitir-adicional."
            )

        funcoes = [
            f.strip()
            for f in (options["funcoes"] or "gestao_administradores").split(",")
            if f.strip()
        ]
        if "gestao_administradores" not in funcoes:
            funcoes.append("gestao_administradores")

        invalidas = [f for f in funcoes if f not in FUNCOES_ADMINISTRATIVAS]
        if invalidas:
            raise CommandError(
                f"Função(ões) administrativa(s) inválida(s): {', '.join(invalidas)}."
            )

        if "gestao_usuarios" in funcoes and "verificacao_receitas" in funcoes:
            raise CommandError(
                "Acúmulo proibido pela ADR 0010: uma mesma conta não pode acumular "
                "gestao_usuarios e verificacao_receitas."
            )

        email_bruto = self._ler_campo(options.get("email"), "E-mail do Administrador: ")
        cpf_bruto = self._ler_campo(options.get("cpf"), "CPF do Administrador (11 dígitos): ")
        nome = self._ler_campo(options.get("nome_completo"), "Nome completo: ")
        nasc_bruto = self._ler_campo(
            options.get("data_nascimento"), "Data de nascimento (dd/mm/aaaa): "
        )
        celular_bruto = self._ler_campo(options.get("celular"), "Celular com DDD: ")

        try:
            email = normalizar_email(email_bruto)
            validate_email(email)
            cpf = validar_cpf(cpf_bruto)
            if len(nome) < 3 or len(nome) > 120:
                raise ValueError("Nome completo deve ter entre 3 e 120 caracteres.")
            data_nasc = validar_maioridade(_parse_data_nascimento(nasc_bruto))
            celular = validar_celular(celular_bruto)
        except (ValueError, DjangoValidationError) as erro:
            raise CommandError(str(erro)) from erro

        senha = self._obter_senha(usar_stdin=bool(options["password_stdin"]))
        try:
            validate_password(senha)
        except DjangoValidationError as erro:
            raise CommandError("Senha inválida: " + " ".join(erro.messages)) from erro

        with transaction.atomic():
            if Usuario.objects.filter(cpf=cpf).exists():
                raise CommandError("CPF já cadastrado em outra conta.")
            if (
                Usuario.objects.annotate(email_lower=Lower("email"))
                .filter(email_lower=email)
                .exists()
            ):
                raise CommandError("E-mail já cadastrado em outra conta.")

            agora = timezone.now()
            usuario = Usuario.objects.create_superuser(
                email=email,
                cpf=cpf,
                password=senha,
                nome_completo=nome,
                data_nascimento=data_nasc,
                celular=celular,
                email_confirmado_em=agora,
                perfil_doador=True,
                status=StatusUsuario.ATIVO,
            )

            grupos = []
            for nome_funcao in sorted(set(funcoes)):
                grupo, _ = Group.objects.get_or_create(name=nome_funcao)
                grupos.append(grupo)
            usuario.groups.set(grupos)

            AuditoriaService.registrar(
                acao="usuario.admin_bootstrap",
                entidade_tipo="usuario",
                entidade_id=usuario.pk,
                ator=None,
                detalhes={"funcoes": sorted(set(funcoes))},
                origem=OrigemAuditoria.TERMINAL,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Administrador #{usuario.pk} criado com sucesso com funções "
                f"{', '.join(sorted(set(funcoes)))}. "
                "O pareamento do 2FA (TOTP) será exigido no primeiro login."
            )
        )
