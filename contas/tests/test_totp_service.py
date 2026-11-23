"""Testes unitários de TotpService, SessaoService e bootstrap_admin (Spec 02)."""

import os
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from unittest.mock import patch

import pyotp
from django.contrib.auth.models import Group
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from auditoria.models import OrigemAuditoria, RegistroAuditoria
from contas.exceptions import (
    CodigoRecuperacaoInvalido,
    CodigoTotpInvalido,
    ResetTotpNaoPermitido,
    TotpBloqueadoTemporariamente,
)
from contas.models import (
    CodigoRecuperacaoTotp,
    DispositivoTotp,
    SessaoUsuario,
    StatusUsuario,
    Usuario,
)
from contas.services import SessaoService, TotpService


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
)
class TotpESessaoServiceTest(TestCase):
    def _criar_admin(self, email: str, cpf: str, funcoes: tuple[str, ...]) -> Usuario:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!SenhaAdmin1",
            nome_completo=f"Admin {email}",
            data_nascimento=date(1985, 3, 15),
            celular="11988887777",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )
        grupos = [Group.objects.get_or_create(name=nome)[0] for nome in funcoes]
        usuario.groups.set(grupos)
        return usuario

    def test_pareamento_totp_segno_anti_replay_e_limite_2fa(self):
        """CA-02-08 e RN-02-07."""
        admin = self._criar_admin("admin1@exemplo.com", "52998224725", ("gestao_administradores",))
        pareamento = TotpService.iniciar_pareamento(admin)
        self.assertTrue(pareamento.qr_svg_data_uri.startswith("data:image/svg+xml"))
        self.assertNotIn("http://", pareamento.qr_svg_data_uri)
        self.assertNotIn("https://", pareamento.qr_svg_data_uri)

        t0 = datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC)
        codigo_t0 = pyotp.TOTP(pareamento.segredo_manual).at(t0)

        codigos = TotpService.confirmar_pareamento(admin, codigo_t0, "192.0.2.50", momento=t0)
        self.assertEqual(len(codigos), 8)
        self.assertEqual(CodigoRecuperacaoTotp.objects.filter(usuario=admin).count(), 8)
        for codigo in codigos:
            self.assertFalse(
                CodigoRecuperacaoTotp.objects.filter(usuario=admin, codigo_hash=codigo).exists()
            )
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="usuario.totp_ativado",
                entidade_id=str(admin.pk),
            ).exists()
        )

        # Reuso do mesmo código na mesma janela de 30 s é recusado (anti-replay)
        with self.assertRaises(CodigoTotpInvalido):
            TotpService.verificar_codigo(
                admin, codigo_t0, "192.0.2.50", momento=t0 + timedelta(seconds=5)
            )

        # Código da janela seguinte (+30 s) é aceito
        t1 = t0 + timedelta(seconds=30)
        codigo_t1 = pyotp.TOTP(pareamento.segredo_manual).at(t1)
        TotpService.verificar_codigo(admin, codigo_t1, "192.0.2.50", momento=t1)

        # 5 falhas consecutivas de 2FA em 15 min acionam bloqueio temporário
        for indice in range(4):
            with self.assertRaises(CodigoTotpInvalido):
                TotpService.verificar_codigo(
                    admin,
                    "000000",
                    "192.0.2.50",
                    momento=t1 + timedelta(seconds=indice + 1),
                )
        with self.assertRaises(TotpBloqueadoTemporariamente):
            TotpService.verificar_codigo(
                admin,
                "000000",
                "192.0.2.50",
                momento=t1 + timedelta(seconds=10),
            )

    def test_codigos_recuperacao_uso_unico_e_regeneracao_com_step_up(self):
        """CA-02-09."""
        admin = self._criar_admin("admin2@exemplo.com", "11144477735", ("gestao_administradores",))
        pareamento = TotpService.iniciar_pareamento(admin)
        t0 = datetime(2026, 11, 23, 13, 0, 0, tzinfo=UTC)
        codigos = TotpService.confirmar_pareamento(
            admin,
            pyotp.TOTP(pareamento.segredo_manual).at(t0),
            "192.0.2.51",
            momento=t0,
        )

        restantes = TotpService.consumir_codigo_recuperacao(
            admin, codigos[0], "192.0.2.51", momento=t0 + timedelta(seconds=10)
        )
        self.assertEqual(restantes, 7)
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="usuario.codigo_recuperacao_usado",
                entidade_id=str(admin.pk),
            ).exists()
        )
        # Reuso do mesmo código de recuperação falha
        with self.assertRaises(CodigoRecuperacaoInvalido):
            TotpService.consumir_codigo_recuperacao(
                admin, codigos[0], "192.0.2.51", momento=t0 + timedelta(seconds=15)
            )

        # Regeneração exige step-up válido (código TOTP novo) e invalida códigos anteriores
        t1 = t0 + timedelta(seconds=60)
        novos = TotpService.regenerar_codigos_recuperacao(
            admin,
            pyotp.TOTP(pareamento.segredo_manual).at(t1),
            "192.0.2.51",
            momento=t1,
        )
        self.assertEqual(len(novos), 8)
        with self.assertRaises(CodigoRecuperacaoInvalido):
            TotpService.consumir_codigo_recuperacao(
                admin, codigos[1], "192.0.2.51", momento=t1 + timedelta(seconds=5)
            )
        self.assertEqual(
            TotpService.consumir_codigo_recuperacao(
                admin, novos[0], "192.0.2.51", momento=t1 + timedelta(seconds=10)
            ),
            7,
        )
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="usuario.codigos_recuperacao_regenerados",
                entidade_id=str(admin.pk),
            ).exists()
        )

    def test_reset_2fa_exige_dois_admins_ativos_e_revoga_sessoes_do_alvo(self):
        """CA-02-10."""
        admin1 = self._criar_admin("a1@exemplo.com", "52998224725", ("gestao_administradores",))
        p1 = TotpService.iniciar_pareamento(admin1)
        t0 = datetime(2026, 11, 23, 14, 0, 0, tzinfo=UTC)
        TotpService.confirmar_pareamento(
            admin1, pyotp.TOTP(p1.segredo_manual).at(t0), "192.0.2.52", momento=t0
        )

        # Auto-reset proibido
        with self.assertRaises(ResetTotpNaoPermitido):
            TotpService.resetar_por_administrador(
                admin1,
                admin1,
                pyotp.TOTP(p1.segredo_manual).at(t0 + timedelta(seconds=30)),
                "192.0.2.52",
                momento=t0 + timedelta(seconds=30),
            )

        # Com apenas 1 Admin ativo com gestao_administradores, não pode resetar outro usuário
        outro = self._criar_admin("mod@exemplo.com", "11144477735", ("moderacao_denuncias",))
        p_outro = TotpService.iniciar_pareamento(outro)
        TotpService.confirmar_pareamento(
            outro, pyotp.TOTP(p_outro.segredo_manual).at(t0), "192.0.2.52", momento=t0
        )
        with self.assertRaises(ResetTotpNaoPermitido):
            TotpService.resetar_por_administrador(
                admin1,
                outro,
                pyotp.TOTP(p1.segredo_manual).at(t0 + timedelta(seconds=60)),
                "192.0.2.52",
                momento=t0 + timedelta(seconds=60),
            )

        # Adicionando um 2º Admin ativo com gestao_administradores, reset é autorizado
        admin2 = self._criar_admin("a2@exemplo.com", "39053344705", ("gestao_administradores",))
        p2 = TotpService.iniciar_pareamento(admin2)
        TotpService.confirmar_pareamento(
            admin2, pyotp.TOTP(p2.segredo_manual).at(t0), "192.0.2.52", momento=t0
        )
        sessao_alvo = SessionStore()
        sessao_alvo["_auth_user_id"] = str(admin2.pk)
        sessao_alvo.create()
        SessaoService.registrar_sessao(admin2.pk, sessao_alvo.session_key)

        t2 = t0 + timedelta(seconds=90)
        TotpService.resetar_por_administrador(
            admin1,
            admin2,
            pyotp.TOTP(p1.segredo_manual).at(t2),
            "192.0.2.52",
            momento=t2,
        )
        self.assertFalse(DispositivoTotp.objects.filter(usuario=admin2).exists())
        self.assertFalse(CodigoRecuperacaoTotp.objects.filter(usuario=admin2).exists())
        self.assertFalse(SessaoUsuario.objects.filter(usuario=admin2).exists())
        self.assertFalse(Session.objects.filter(session_key=sessao_alvo.session_key).exists())
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="usuario.totp_resetado",
                entidade_id=str(admin2.pk),
                ator=admin1,
            ).exists()
        )

    def test_revogacao_de_sessoes_em_troca_de_senha_e_suspensao_bloqueio(self):
        """Revogação via SessaoUsuario + django_session (RF003 / RF004 / ADR 0009)."""
        usuario = self._criar_admin("revoga@exemplo.com", "52998224725", ("auditoria",))
        s1 = SessionStore()
        s1["_auth_user_id"] = str(usuario.pk)
        s1.create()
        SessaoService.registrar_sessao(usuario.pk, s1.session_key)

        s2 = SessionStore()
        s2["_auth_user_id"] = str(usuario.pk)
        s2.create()
        SessaoService.registrar_sessao(usuario.pk, s2.session_key)
        self.assertEqual(SessaoUsuario.objects.filter(usuario=usuario).count(), 2)

        # Simula troca de senha + encerramento de todas as sessões
        usuario.set_password("Rm3d!NovaSenha2")
        usuario.save(update_fields=["password"])
        removidas = SessaoService.encerrar_todas_sessoes(usuario.pk)
        self.assertEqual(removidas, 2)
        self.assertEqual(SessaoUsuario.objects.filter(usuario=usuario).count(), 0)
        self.assertFalse(
            Session.objects.filter(session_key__in=[s1.session_key, s2.session_key]).exists()
        )

        # Simula nova sessão seguida de suspensão/bloqueio
        s3 = SessionStore()
        s3["_auth_user_id"] = str(usuario.pk)
        s3.create()
        SessaoService.registrar_sessao(usuario.pk, s3.session_key)

        Usuario.objects.filter(pk=usuario.pk).update(status=StatusUsuario.SUSPENSO, is_active=False)
        SessaoService.encerrar_todas_sessoes(usuario.pk)
        self.assertFalse(SessaoUsuario.objects.filter(usuario=usuario).exists())
        self.assertFalse(Session.objects.filter(session_key=s3.session_key).exists())

    def test_comando_bootstrap_admin_cria_primeiro_admin_e_bloqueia_acumulo_proibido(self):
        saida = StringIO()
        with patch.dict(os.environ, {"REMED_BOOTSTRAP_ADMIN_PASSWORD": "Rm3d!BootAdmin9"}):
            call_command(
                "bootstrap_admin",
                email="root.admin@exemplo.com",
                cpf="529.982.247-25",
                nome_completo="Administrador Inicial",
                data_nascimento="10/01/1985",
                celular="(11) 99876-5432",
                stdout=saida,
            )

        admin = Usuario.objects.get(email="root.admin@exemplo.com")
        self.assertEqual(admin.cpf, "52998224725")
        self.assertTrue(admin.is_superuser)
        self.assertIsNotNone(admin.email_confirmado_em)
        self.assertTrue(admin.groups.filter(name="gestao_administradores").exists())
        self.assertFalse(DispositivoTotp.objects.filter(usuario=admin).exists())
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="usuario.admin_bootstrap",
                entidade_id=str(admin.pk),
                origem=OrigemAuditoria.TERMINAL,
            ).exists()
        )

        # Segunda execução sem --permitir-adicional é bloqueada
        with patch.dict(os.environ, {"REMED_BOOTSTRAP_ADMIN_PASSWORD": "Rm3d!BootAdmin9"}):
            with self.assertRaises(CommandError):
                call_command(
                    "bootstrap_admin",
                    email="outro.admin@exemplo.com",
                    cpf="111.444.777-35",
                    nome_completo="Outro Admin",
                    data_nascimento="10/01/1985",
                    celular="(11) 99876-5432",
                )

        # Acúmulo proibido gestao_usuarios + verificacao_receitas é bloqueado (ADR 0010)
        with patch.dict(os.environ, {"REMED_BOOTSTRAP_ADMIN_PASSWORD": "Rm3d!BootAdmin9"}):
            with self.assertRaises(CommandError):
                call_command(
                    "bootstrap_admin",
                    email="acumulo@exemplo.com",
                    cpf="111.444.777-35",
                    nome_completo="Admin Acumulo",
                    data_nascimento="10/01/1985",
                    celular="(11) 99876-5432",
                    funcoes="gestao_usuarios,verificacao_receitas",
                    permitir_adicional=True,
                )
