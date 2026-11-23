"""Testes de concorrência real no PostgreSQL para o outbox de e-mails (CA-03-06 / ADR 0015)."""

import threading
from datetime import date
from unittest.mock import patch

from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from contas.models import Usuario
from notificacoes.models import OutboxEmail, StatusOutboxEmail, TipoNotificacao
from notificacoes.services import NotificacaoService


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class OutboxConcorrenciaTest(TransactionTestCase):
    def test_dois_workers_concorrentes_nao_duplicam_envio(self):
        """CA-03-06: select_for_update(skip_locked=True) impede envio duplicado sob concorrência."""
        usuario = Usuario.objects.create_user(
            email="concorrencia@exemplo.com",
            cpf="52998224725",
            password="Rm3d!Senha1",
            nome_completo="Usuário Concorrência",
            data_nascimento=date(1990, 2, 2),
            celular="11988880000",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )
        for indice in range(6):
            NotificacaoService.registrar_evento(
                destinatario=usuario,
                tipo=TipoNotificacao.NOVA_CORRESPONDENCIA,
                contexto={"medicamento": f"Lote {indice}"},
            )

        enviados_assuntos: list[str] = []
        trava = threading.Lock()
        barreira = threading.Barrier(2)

        def _fake_send_mail(*, subject, message, from_email, recipient_list, fail_silently):
            _ = (message, from_email, recipient_list, fail_silently)
            with trava:
                enviados_assuntos.append(subject)
            return 1

        resultados = []
        erros = []

        def _executar_worker():
            try:
                barreira.wait(timeout=5)
                resultados.append(NotificacaoService.despachar_outbox_pendentes(limite_lote=50))
            except Exception as exc:  # pragma: no cover - diagnóstico de falha concorrente
                erros.append(exc)
            finally:
                connections.close_all()

        with patch("notificacoes.services.send_mail", side_effect=_fake_send_mail):
            t1 = threading.Thread(target=_executar_worker)
            t2 = threading.Thread(target=_executar_worker)
            t1.start()
            t2.start()
            t1.join(timeout=15)
            t2.join(timeout=15)

        self.assertEqual(erros, [])
        self.assertEqual(len(enviados_assuntos), 6)
        self.assertEqual(sum(r.enviados for r in resultados), 6)
        self.assertEqual(
            OutboxEmail.objects.filter(status=StatusOutboxEmail.ENVIADA).count(),
            6,
        )
