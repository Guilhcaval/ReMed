"""Testes do app auditoria (ADR 0011 / CA-01-16)."""

from django.db import DatabaseError, transaction
from django.test import TestCase

from auditoria.models import RegistroAuditoria
from auditoria.services import AuditoriaService
from nucleo.exceptions import RegraNegocioViolada


class AuditoriaServiceTest(TestCase):
    def test_registrar_cria_evento_imutavel(self):
        registro = AuditoriaService.registrar(
            acao="usuario.cadastrado",
            entidade_tipo="usuario",
            entidade_id=42,
            detalhes={"perfis": ["doador"], "versao_termos_uso": "1.0-rascunho"},
        )
        self.assertEqual(registro.acao, "usuario.cadastrado")
        self.assertEqual(registro.entidade_id, "42")
        self.assertEqual(registro.detalhes["perfis"], ["doador"])

    def test_rejeita_chaves_sensiveis_em_detalhes(self):
        for chave in ("cpf", "email", "senha", "token", "endereco"):
            with self.subTest(chave=chave):
                with self.assertRaises(RegraNegocioViolada):
                    AuditoriaService.registrar(
                        acao="usuario.teste",
                        entidade_tipo="usuario",
                        entidade_id=1,
                        detalhes={chave: "valor-proibido"},
                    )

    def test_rejeita_chave_sensivel_aninhada(self):
        with self.assertRaises(RegraNegocioViolada):
            AuditoriaService.registrar(
                acao="usuario.teste",
                entidade_tipo="usuario",
                entidade_id=1,
                detalhes={"dados": [{"token": "segredo"}]},
            )

    def test_trigger_postgresql_bloqueia_update_e_delete(self):
        """CA-01-16: trigger append-only impede UPDATE e DELETE em RegistroAuditoria."""
        registro = AuditoriaService.registrar(
            acao="usuario.cadastrado",
            entidade_tipo="usuario",
            entidade_id=99,
        )

        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                RegistroAuditoria.objects.filter(pk=registro.pk).update(acao="adulterada")

        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                RegistroAuditoria.objects.filter(pk=registro.pk).delete()

        self.assertTrue(RegistroAuditoria.objects.filter(pk=registro.pk).exists())
