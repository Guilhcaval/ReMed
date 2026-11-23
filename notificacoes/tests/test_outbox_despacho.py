"""Testes do Transactional Outbox mínimo e do comando despachar_emails (ADR 0015)."""

from contextlib import contextmanager
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from contas.models import Usuario
from notificacoes.models import OutboxEmail, StatusOutboxEmail
from notificacoes.services import MAX_TENTATIVAS_ENVIO_EMAIL, NotificacaoService
from nucleo.models import ExecucaoRotina, ResultadoRotina


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="nao-responda@remed.local",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class OutboxDespachoTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            email="maria@exemplo.com",
            cpf="52998224725",
            password="Rm3d!SenhaSegura",
            nome_completo="Maria da Silva",
            celular="11999998888",
            perfil_doador=True,
        )

    def test_enfileirar_e_despachar_email_confirmacao_com_sucesso(self):
        item = NotificacaoService.enfileirar_email_confirmacao(
            destinatario=self.usuario,
            email_destino="maria@exemplo.com",
            link_confirmacao="http://localhost:8000/contas/confirmar-email/token-teste/",
        )
        self.assertEqual(item.status, StatusOutboxEmail.PENDENTE)
        self.assertNotIn("52998224725", item.corpo_texto)
        self.assertNotIn("11999998888", item.corpo_texto)
        self.assertNotIn("Maria da Silva", item.corpo_texto)

        saida = StringIO()
        call_command("despachar_emails", stdout=saida)

        item.refresh_from_db()
        self.assertEqual(item.status, StatusOutboxEmail.ENVIADA)
        self.assertEqual(item.tentativas, 1)
        self.assertIsNotNone(item.enviado_em)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["maria@exemplo.com"])
        self.assertEqual(mail.outbox[0].from_email, "nao-responda@remed.local")

        execucao = ExecucaoRotina.objects.get(nome_rotina="despachar_emails")
        self.assertEqual(execucao.resultado, ResultadoRotina.SUCESSO)
        self.assertEqual(execucao.contadores["enviados"], 1)

    def test_falha_smtp_faz_ate_tres_novas_tentativas_antes_de_marcar_falha(self):
        item = NotificacaoService.enfileirar_email_confirmacao(
            destinatario=self.usuario,
            email_destino="maria@exemplo.com",
            link_confirmacao="http://localhost:8000/contas/confirmar-email/token-falha/",
        )

        with patch("notificacoes.services.send_mail", side_effect=OSError("SMTP indisponível")):
            for tentativa_esperada in range(1, MAX_TENTATIVAS_ENVIO_EMAIL + 1):
                OutboxEmail.objects.filter(pk=item.pk).update(proxima_tentativa_em=timezone.now())
                call_command("despachar_emails", stdout=StringIO())
                item.refresh_from_db()
                self.assertEqual(item.tentativas, tentativa_esperada)
                if tentativa_esperada < MAX_TENTATIVAS_ENVIO_EMAIL:
                    self.assertEqual(item.status, StatusOutboxEmail.PENDENTE)
                else:
                    self.assertEqual(item.status, StatusOutboxEmail.FALHA)

        self.assertIn("SMTP indisponível", item.erro_ultimo)
        ultima_execucao = ExecucaoRotina.objects.filter(nome_rotina="despachar_emails").first()
        self.assertEqual(ultima_execucao.resultado, ResultadoRotina.PARCIAL)
        self.assertEqual(ultima_execucao.contadores["falhas_definitivas"], 1)

    def test_comando_encerra_silenciosamente_quando_lock_ocupado(self):
        @contextmanager
        def _lock_ocupado(_nome):
            yield False

        NotificacaoService.enfileirar_email_confirmacao(
            destinatario=self.usuario,
            email_destino="maria@exemplo.com",
            link_confirmacao="http://localhost:8000/contas/confirmar-email/token-lock/",
        )

        with patch(
            "notificacoes.management.commands.despachar_emails.adquirir_lock_rotina",
            side_effect=_lock_ocupado,
        ):
            call_command("despachar_emails", stdout=StringIO())

        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(ExecucaoRotina.objects.count(), 0)
