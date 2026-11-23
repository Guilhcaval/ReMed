"""Testes unitários de AutenticacaoService, EmailOuCpfBackend e RegistroAcesso (Spec 02)."""

from datetime import date, timedelta

from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from contas.backends import EmailOuCpfBackend
from contas.exceptions import (
    ContaBloqueadaTemporariamente,
    ContaIndisponivel,
    CredenciaisInvalidas,
    EmailNaoConfirmado,
)
from contas.models import EtapaAcesso, RegistroAcesso, ResultadoAcesso, StatusUsuario, Usuario
from contas.services import AutenticacaoService, hash_identificador_acesso
from core.settings import resolver_identificador_hmac_key


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
)
class AutenticacaoServiceTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            email="ana@exemplo.com",
            cpf="52998224725",
            password="Rm3d!Senha1",
            nome_completo="Ana Carolina",
            data_nascimento=date(1990, 5, 10),
            celular="11987654321",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )

    def test_chave_hmac_dedicada_recusa_iniciar_em_producao_sem_env(self):
        with self.assertRaises(ImproperlyConfigured):
            resolver_identificador_hmac_key("", "secret-key", debug=False, em_teste=False)

        self.assertEqual(
            resolver_identificador_hmac_key(
                "minha-chave", "secret-key", debug=False, em_teste=False
            ),
            "minha-chave",
        )
        fallback_dev = resolver_identificador_hmac_key("", "secret-key", debug=True, em_teste=False)
        self.assertEqual(len(fallback_dev), 64)
        self.assertNotEqual(fallback_dev, "secret-key")

    def test_login_por_email_e_cpf_com_e_sem_mascara_sem_pii_em_registro_acesso(self):
        """CA-02-01."""
        for identificador in ("ANA@Exemplo.com", "529.982.247-25", "52998224725"):
            with self.subTest(identificador=identificador):
                resultado = AutenticacaoService.autenticar(
                    identificador,
                    "Rm3d!Senha1",
                    "192.0.2.10",
                )
                self.assertEqual(resultado.usuario.pk, self.usuario.pk)
                self.assertFalse(resultado.exige_2fa)

        registro = RegistroAcesso.objects.first()
        self.assertEqual(registro.resultado, ResultadoAcesso.SUCESSO)
        self.assertEqual(registro.etapa, EtapaAcesso.SENHA)
        self.assertEqual(registro.identificador_hash, hash_identificador_acesso("52998224725"))
        self.assertNotIn("52998224725", registro.identificador_hash)
        self.assertNotIn("ana@exemplo.com", registro.identificador_hash)

    def test_recusa_cnpj_e_credenciais_invalidas(self):
        """CA-02-02 e CA-02-03."""
        for identificador, senha in (
            ("12.345.678/0001-95", "Rm3d!Senha1"),
            ("naoexiste@exemplo.com", "Rm3d!Senha1"),
            ("ana@exemplo.com", "SenhaErrada!9"),
        ):
            with self.subTest(identificador=identificador):
                with self.assertRaises(CredenciaisInvalidas) as ctx:
                    AutenticacaoService.autenticar(identificador, senha, "192.0.2.11")
                self.assertEqual(str(ctx.exception), "E-mail/CPF ou senha incorretos")

        self.assertEqual(
            RegistroAcesso.objects.filter(resultado=ResultadoAcesso.FALHA).count(),
            3,
        )

    def test_ordem_de_mensagens_para_nao_confirmado_inativo_suspenso_e_bloqueado(self):
        """CA-02-02 / RN-02-02: orientações específicas só após senha correta."""
        agora = timezone.now()
        Usuario.objects.filter(pk=self.usuario.pk).update(email_confirmado_em=None)
        with self.assertRaises(CredenciaisInvalidas):
            AutenticacaoService.autenticar(
                "ana@exemplo.com", "Errada!1", "192.0.2.12", momento=agora
            )
        with self.assertRaises(EmailNaoConfirmado):
            AutenticacaoService.autenticar(
                "ana@exemplo.com", "Rm3d!Senha1", "192.0.2.12", momento=agora
            )

        Usuario.objects.filter(pk=self.usuario.pk).update(email_confirmado_em=agora)
        for indice, status_bloqueio in enumerate(
            (StatusUsuario.INATIVO, StatusUsuario.SUSPENSO, StatusUsuario.BLOQUEADO),
            start=1,
        ):
            momento_subteste = agora + timedelta(minutes=20 * indice)
            with self.subTest(status=status_bloqueio):
                Usuario.objects.filter(pk=self.usuario.pk).update(
                    status=status_bloqueio,
                    is_active=False,
                )
                with self.assertRaises(CredenciaisInvalidas):
                    AutenticacaoService.autenticar(
                        "ana@exemplo.com",
                        "Errada!1",
                        "192.0.2.13",
                        momento=momento_subteste,
                    )
                with self.assertRaises(ContaIndisponivel) as ctx:
                    AutenticacaoService.autenticar(
                        "ana@exemplo.com",
                        "Rm3d!Senha1",
                        "192.0.2.13",
                        momento=momento_subteste,
                    )
                self.assertEqual(ctx.exception.status, status_bloqueio)

    def test_bloqueio_15_min_apos_5_falhas_unificando_email_e_cpf(self):
        """CA-02-04: 3 falhas por e-mail + 2 por CPF bloqueiam a 6ª e liberam após 15 min."""
        agora = timezone.now()
        for indice in range(3):
            with self.assertRaises(CredenciaisInvalidas):
                AutenticacaoService.autenticar(
                    "ana@exemplo.com",
                    f"Errada!{indice}",
                    "192.0.2.20",
                    momento=agora,
                )
        for indice in range(2):
            with self.assertRaises(CredenciaisInvalidas):
                AutenticacaoService.autenticar(
                    "529.982.247-25",
                    f"ErradaCpf!{indice}",
                    "192.0.2.20",
                    momento=agora,
                )

        # 6ª tentativa dentro dos 15 minutos falha mesmo com senha correta
        with self.assertRaises(ContaBloqueadaTemporariamente) as ctx:
            AutenticacaoService.autenticar(
                "ana@exemplo.com",
                "Rm3d!Senha1",
                "192.0.2.20",
                momento=agora + timedelta(minutes=5),
            )
        self.assertEqual(str(ctx.exception), "Muitas tentativas. Tente novamente mais tarde")
        self.assertTrue(
            RegistroAcesso.objects.filter(
                usuario=self.usuario,
                resultado=ResultadoAcesso.BLOQUEADO,
            ).exists()
        )

        # Após expirar 15 minutos, login válido volta a funcionar
        resultado = AutenticacaoService.autenticar(
            "ana@exemplo.com",
            "Rm3d!Senha1",
            "192.0.2.20",
            momento=agora + timedelta(minutes=16),
        )
        self.assertEqual(resultado.usuario.pk, self.usuario.pk)

    @override_settings(REMED_LOGIN_LIMITE_IP_TENTATIVAS=3)
    def test_limite_secundario_por_ip_bloqueia_password_spraying(self):
        for indice in range(3):
            with self.assertRaises(CredenciaisInvalidas):
                AutenticacaoService.autenticar(f"u{indice}@exemplo.com", "Errada!1", "192.0.2.30")
        with self.assertRaises(ContaBloqueadaTemporariamente):
            AutenticacaoService.autenticar("ana@exemplo.com", "Rm3d!Senha1", "192.0.2.30")

    def test_backend_customizado_aceita_email_ou_cpf_e_recusa_cnpj_e_inativos(self):
        backend = EmailOuCpfBackend()
        self.assertEqual(
            backend.authenticate(None, username="ANA@exemplo.com", password="Rm3d!Senha1"),
            self.usuario,
        )
        self.assertEqual(
            backend.authenticate(None, username="529.982.247-25", password="Rm3d!Senha1"),
            self.usuario,
        )
        self.assertIsNone(
            backend.authenticate(None, username="12345678000195", password="Rm3d!Senha1")
        )
        Usuario.objects.filter(pk=self.usuario.pk).update(
            status=StatusUsuario.SUSPENSO, is_active=False
        )
        self.assertIsNone(backend.get_user(self.usuario.pk))

    def test_trigger_postgresql_bloqueia_update_e_delete_em_registro_acesso(self):
        """CA-02-12: RegistroAcesso é append-only no PostgreSQL."""
        AutenticacaoService.autenticar("ana@exemplo.com", "Rm3d!Senha1", "192.0.2.40")
        registro = RegistroAcesso.objects.first()

        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                RegistroAcesso.objects.filter(pk=registro.pk).update(
                    resultado=ResultadoAcesso.FALHA
                )

        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                RegistroAcesso.objects.filter(pk=registro.pk).delete()

        self.assertTrue(RegistroAcesso.objects.filter(pk=registro.pk).exists())
