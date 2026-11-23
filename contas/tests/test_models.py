"""Testes de models e constraints PostgreSQL do app contas (ADRs 0007 e 0008)."""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from contas.models import AceiteTermo, StatusUsuario, Usuario


class UsuarioModelConstraintsTest(TestCase):
    def test_configuracao_auth_user_model_e_argon2(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "contas.Usuario")
        self.assertEqual(Usuario.USERNAME_FIELD, "email")
        nomes_campos = {campo.name for campo in Usuario._meta.get_fields()}
        self.assertNotIn("username", nomes_campos)
        self.assertEqual(
            settings.PASSWORD_HASHERS[0],
            "django.contrib.auth.hashers.Argon2PasswordHasher",
        )

    def test_unicidade_cpf_e_email_case_insensitive_no_postgresql(self):
        Usuario.objects.create_user(
            email="ana@exemplo.com",
            cpf="52998224725",
            password="Rm3d!Senha1",
            nome_completo="Ana Silva",
            perfil_doador=True,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Usuario.objects.create_user(
                    email="outra@exemplo.com",
                    cpf="52998224725",
                    password="Rm3d!Senha1",
                    nome_completo="Outra Ana",
                    perfil_doador=True,
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Usuario.objects.create(
                    email="ANA@EXEMPLO.COM",
                    cpf="11144477735",
                    nome_completo="Ana Duplicada",
                    perfil_doador=True,
                )

    def test_multiplos_usuarios_anonimizados_com_email_e_cpf_nulos(self):
        agora = timezone.now()
        u1 = Usuario.objects.create(
            email=None,
            cpf=None,
            nome_completo="",
            status=StatusUsuario.INATIVO,
            is_active=False,
            anonimizado_em=agora,
        )
        u2 = Usuario.objects.create(
            email=None,
            cpf=None,
            nome_completo="",
            status=StatusUsuario.INATIVO,
            is_active=False,
            anonimizado_em=agora,
        )
        self.assertNotEqual(u1.pk, u2.pk)

    def test_check_constraint_exige_email_e_cpf_quando_nao_anonimizado(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Usuario.objects.create(
                    email=None,
                    cpf="52998224725",
                    nome_completo="Sem Email",
                    perfil_doador=True,
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Usuario.objects.create(
                    email="semcpf@exemplo.com",
                    cpf=None,
                    nome_completo="Sem CPF",
                    perfil_doador=True,
                )

    def test_check_constraint_exige_perfil_minimo_para_cidadao(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Usuario.objects.create_user(
                    email="semperfil@exemplo.com",
                    cpf="52998224725",
                    password="Rm3d!Senha1",
                    nome_completo="Sem Perfil",
                )

    def test_on_delete_protect_impede_exclusao_fisica_com_aceite_termo(self):
        usuario = Usuario.objects.create_user(
            email="protegido@exemplo.com",
            cpf="52998224725",
            password="Rm3d!Senha1",
            nome_completo="Usuario Protegido",
            perfil_doador=True,
        )
        AceiteTermo.objects.create(
            usuario=usuario,
            versao_termos_uso="1.0-rascunho",
            versao_politica_privacidade="1.0-rascunho",
            aceito_em=timezone.now(),
        )
        with self.assertRaises(ProtectedError):
            usuario.delete()
