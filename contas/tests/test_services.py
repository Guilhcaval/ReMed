"""Testes unitários do UsuarioService (Spec 01 / RF001 — sem request)."""

import logging
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from contas.exceptions import (
    AlteracaoCpfProibida,
    CpfJaCadastrado,
    EmailJaCadastrado,
    EncerramentoContaBloqueado,
    SenhaAtualInvalida,
    TokenConfirmacaoInvalido,
)
from contas.models import (
    AceiteTermo,
    EnderecoUsuario,
    StatusUsuario,
    TipoTokenConfirmacao,
    TokenConfirmacaoEmail,
    Usuario,
)
from contas.services import (
    DadosAtualizacaoPerfil,
    DadosCadastroUsuario,
    DadosEndereco,
    UsuarioService,
)
from notificacoes.models import OutboxEmail, StatusOutboxEmail
from nucleo.exceptions import RegraNegocioViolada
from nucleo.models import CacheCep, FonteCep


def _endereco_padrao(**sobrescritas) -> DadosEndereco:
    base = {
        "cep": "01001000",
        "logradouro": "Praça da Sé",
        "numero": "100",
        "bairro": "Sé",
        "municipio": "São Paulo",
        "estado": "SP",
        "complemento": "Apto 4",
    }
    base.update(sobrescritas)
    return DadosEndereco(**base)


def _dados_cadastro(**sobrescritas) -> DadosCadastroUsuario:
    base = {
        "nome_completo": "Maria Aparecida Silva",
        "cpf": "52998224725",
        "data_nascimento": date(1990, 5, 15),
        "email": "Maria@Exemplo.com",
        "celular": "11987654321",
        "senha": "Rm3d!9xQ",
        "perfil_doador": True,
        "perfil_solicitante": False,
        "perfil_cuidador": True,
        "aceite_termos": True,
        "endereco": _endereco_padrao(),
    }
    base.update(sobrescritas)
    return DadosCadastroUsuario(**base)


class UsuarioServiceTest(TestCase):
    def _capturar_tokens(self):
        tokens: list[str] = []

        def _construir(token: str) -> str:
            tokens.append(token)
            return f"http://localhost:8000/contas/confirmar-email/{token}/"

        return tokens, _construir

    def test_cadastro_valido_com_argon2id_outbox_auditoria_e_sem_token_em_log(self):
        """CA-01-01 e CA-01-08: cadastro completo na mesma transação + hash Argon2id."""
        CacheCep.objects.create(
            cep="01001000",
            logradouro="Praça da Sé",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            latitude_aprox=Decimal("-23.55"),
            longitude_aprox=Decimal("-46.63"),
            fonte=FonteCep.BRASILAPI,
        )
        tokens, construtor = self._capturar_tokens()

        registros_log: list[str] = []

        class _CapturadorLog(logging.Handler):
            def emit(self, record):
                registros_log.append(self.format(record))

        handler = _CapturadorLog()
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        try:
            usuario = UsuarioService.cadastrar(
                _dados_cadastro(),
                construir_url_confirmacao=construtor,
            )
        finally:
            root_logger.removeHandler(handler)

        self.assertEqual(usuario.status, StatusUsuario.ATIVO)
        self.assertIsNone(usuario.email_confirmado_em)
        self.assertEqual(usuario.email, "maria@exemplo.com")
        self.assertTrue(usuario.password.startswith("argon2$argon2id$"))
        self.assertTrue(usuario.check_password("Rm3d!9xQ"))

        endereco = EnderecoUsuario.objects.get(usuario=usuario)
        self.assertEqual(endereco.latitude_aprox, Decimal("-23.55"))
        self.assertEqual(endereco.longitude_aprox, Decimal("-46.63"))

        aceite = AceiteTermo.objects.get(usuario=usuario)
        self.assertEqual(aceite.versao_termos_uso, "1.0-rascunho")

        self.assertEqual(len(tokens), 1)
        token_claro = tokens[0]
        token_db = TokenConfirmacaoEmail.objects.get(usuario=usuario)
        self.assertNotEqual(token_db.token_hash, token_claro)
        self.assertEqual(len(token_db.token_hash), 64)

        outbox = OutboxEmail.objects.get(destinatario=usuario)
        self.assertEqual(outbox.status, StatusOutboxEmail.PENDENTE)
        self.assertIn(token_claro, outbox.corpo_texto)

        auditoria = RegistroAuditoria.objects.get(
            acao="usuario.cadastrado", entidade_id=str(usuario.pk)
        )
        self.assertEqual(auditoria.detalhes["perfis"], ["doador", "cuidador"])
        self.assertNotIn("cpf", auditoria.detalhes)
        self.assertNotIn("email", auditoria.detalhes)
        self.assertNotIn(token_claro, str(auditoria.detalhes))

        for mensagem_log in registros_log:
            self.assertNotIn(token_claro, mensagem_log)

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
    def test_rollback_completo_em_falha_durante_cadastro(self):
        _, construtor = self._capturar_tokens()
        with patch(
            "contas.services.AuditoriaService.registrar",
            side_effect=RuntimeError("Falha induzida na auditoria"),
        ):
            with self.assertRaises(RuntimeError):
                UsuarioService.cadastrar(_dados_cadastro(), construir_url_confirmacao=construtor)

        self.assertEqual(Usuario.objects.count(), 0)
        self.assertEqual(EnderecoUsuario.objects.count(), 0)
        self.assertEqual(AceiteTermo.objects.count(), 0)
        self.assertEqual(OutboxEmail.objects.count(), 0)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
    def test_cpf_e_email_duplicados_rejeitados_com_mensagens_literais(self):
        """CA-01-05 e CA-01-07."""
        _, construtor = self._capturar_tokens()
        UsuarioService.cadastrar(_dados_cadastro(), construir_url_confirmacao=construtor)

        with self.assertRaises(CpfJaCadastrado) as ctx_cpf:
            UsuarioService.cadastrar(
                _dados_cadastro(email="outro@exemplo.com"),
                construir_url_confirmacao=construtor,
            )
        self.assertEqual(str(ctx_cpf.exception), "CPF já cadastrado")

        with self.assertRaises(EmailJaCadastrado) as ctx_email:
            UsuarioService.cadastrar(
                _dados_cadastro(cpf="11144477735", email="MARIA@EXEMPLO.COM"),
                construir_url_confirmacao=construtor,
            )
        self.assertEqual(str(ctx_email.exception), "E-mail já cadastrado")

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
    def test_confirmar_email_uso_unico_expiracao_e_reenvio(self):
        """CA-01-09."""
        tokens, construtor = self._capturar_tokens()
        usuario = UsuarioService.cadastrar(
            _dados_cadastro(),
            construir_url_confirmacao=construtor,
        )
        token_inicial = tokens[0]

        # Reenvio invalida o token anterior e gera um novo
        enviado = UsuarioService.reenviar_confirmacao_email(
            "MARIA@exemplo.com",
            construir_url_confirmacao=construtor,
        )
        self.assertTrue(enviado)
        self.assertEqual(len(tokens), 2)
        with self.assertRaises(TokenConfirmacaoInvalido):
            UsuarioService.confirmar_email(token_inicial)

        # Novo token confirma e não pode ser reutilizado
        token_novo = tokens[1]
        resultado = UsuarioService.confirmar_email(token_novo)
        self.assertEqual(resultado.usuario.pk, usuario.pk)
        usuario.refresh_from_db()
        self.assertIsNotNone(usuario.email_confirmado_em)
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="usuario.email_confirmado",
                entidade_id=str(usuario.pk),
            ).exists()
        )
        with self.assertRaises(TokenConfirmacaoInvalido):
            UsuarioService.confirmar_email(token_novo)

        # Reenvio para conta já confirmada ou e-mail inexistente é silencioso
        self.assertFalse(
            UsuarioService.reenviar_confirmacao_email(
                "maria@exemplo.com",
                construir_url_confirmacao=construtor,
            )
        )
        self.assertFalse(
            UsuarioService.reenviar_confirmacao_email(
                "naoexiste@exemplo.com",
                construir_url_confirmacao=construtor,
            )
        )

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
    def test_token_expirado_e_rejeitado(self):
        tokens, construtor = self._capturar_tokens()
        usuario = UsuarioService.cadastrar(
            _dados_cadastro(),
            construir_url_confirmacao=construtor,
        )
        TokenConfirmacaoEmail.objects.filter(usuario=usuario).update(
            expira_em=timezone.now() - timedelta(minutes=1)
        )
        with self.assertRaises(TokenConfirmacaoInvalido):
            UsuarioService.confirmar_email(tokens[0])

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
    def test_atualizar_perfil_bloqueia_cpf_registra_auditoria_e_troca_email_pendente(self):
        """CA-01-11 e CA-01-15."""
        tokens, construtor = self._capturar_tokens()
        usuario = UsuarioService.cadastrar(
            _dados_cadastro(),
            construir_url_confirmacao=construtor,
        )
        UsuarioService.confirmar_email(tokens[0])

        # Tentativa de alterar CPF é rejeitada pelo service
        with self.assertRaises(AlteracaoCpfProibida):
            UsuarioService.atualizar_perfil(
                usuario.pk,
                DadosAtualizacaoPerfil(
                    nome_completo="Maria Atualizada",
                    data_nascimento=date(1990, 5, 15),
                    email="maria@exemplo.com",
                    celular="11911112222",
                    perfil_doador=True,
                    perfil_solicitante=True,
                    perfil_cuidador=False,
                    endereco=_endereco_padrao(numero="200"),
                    cpf_enviado="11144477735",
                ),
                construir_url_confirmacao=construtor,
            )

        # Atualização com troca de e-mail mantém e-mail atual ativo até confirmar
        resultado = UsuarioService.atualizar_perfil(
            usuario.pk,
            DadosAtualizacaoPerfil(
                nome_completo="Maria Atualizada",
                data_nascimento=date(1990, 5, 15),
                email="novo.email@exemplo.com",
                celular="11911112222",
                perfil_doador=True,
                perfil_solicitante=True,
                perfil_cuidador=False,
                endereco=_endereco_padrao(numero="200"),
            ),
            construir_url_confirmacao=construtor,
        )
        usuario.refresh_from_db()
        self.assertEqual(usuario.email, "maria@exemplo.com")
        self.assertEqual(resultado.troca_email_pendente, "novo.email@exemplo.com")
        self.assertEqual(usuario.celular, "11911112222")

        auditoria = RegistroAuditoria.objects.filter(
            acao="usuario.perfil_alterado",
            entidade_id=str(usuario.pk),
        ).first()
        self.assertIsNotNone(auditoria)
        campos = auditoria.detalhes["campos_alterados"]
        self.assertIn("celular", campos)
        self.assertIn("endereco", campos)
        self.assertIn("solicitacao_alteracao_email", campos)
        self.assertNotIn("11911112222", str(auditoria.detalhes))
        self.assertNotIn("novo.email@exemplo.com", str(auditoria.detalhes))

        # Confirmar link efetiva o novo e-mail
        token_troca = tokens[-1]
        self.assertTrue(
            TokenConfirmacaoEmail.objects.filter(
                usuario=usuario,
                tipo=TipoTokenConfirmacao.ALTERACAO_EMAIL,
                email_destino="novo.email@exemplo.com",
            ).exists()
        )
        UsuarioService.confirmar_email(token_troca)
        usuario.refresh_from_db()
        self.assertEqual(usuario.email, "novo.email@exemplo.com")

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
    def test_encerrar_conta_anonimiza_encerra_sessoes_e_permite_recadastro(self):
        """CA-01-13."""
        tokens, construtor = self._capturar_tokens()
        usuario = UsuarioService.cadastrar(
            _dados_cadastro(),
            construir_url_confirmacao=construtor,
        )
        UsuarioService.confirmar_email(tokens[0])

        sessao = SessionStore()
        sessao["_auth_user_id"] = str(usuario.pk)
        sessao.create()
        chave_sessao = sessao.session_key
        self.assertTrue(Session.objects.filter(session_key=chave_sessao).exists())

        with self.assertRaises(SenhaAtualInvalida):
            UsuarioService.encerrar_conta(usuario, "SenhaErrada!1")

        cancelador_chamado = False

        def _cancelador_fake(conta):
            nonlocal cancelador_chamado
            cancelador_chamado = conta.pk == usuario.pk

        UsuarioService.encerrar_conta(
            usuario,
            "Rm3d!9xQ",
            cancelador_pendencias_usuario=_cancelador_fake,
        )
        self.assertTrue(cancelador_chamado)

        usuario.refresh_from_db()
        self.assertIsNone(usuario.email)
        self.assertIsNone(usuario.cpf)
        self.assertEqual(usuario.nome_completo, "")
        self.assertEqual(usuario.celular, "")
        self.assertIsNone(usuario.data_nascimento)
        self.assertIsNotNone(usuario.anonimizado_em)
        self.assertEqual(usuario.status, StatusUsuario.INATIVO)
        self.assertFalse(usuario.is_active)
        self.assertFalse(usuario.has_usable_password())
        self.assertFalse(EnderecoUsuario.objects.filter(usuario=usuario).exists())
        self.assertFalse(TokenConfirmacaoEmail.objects.filter(usuario=usuario).exists())
        self.assertFalse(Session.objects.filter(session_key=chave_sessao).exists())
        self.assertTrue(AceiteTermo.objects.filter(usuario=usuario).exists())
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="usuario.conta_encerrada",
                entidade_id=str(usuario.pk),
            ).exists()
        )

        # Recadastro posterior com o mesmo CPF e e-mail é aceito
        novo_usuario = UsuarioService.cadastrar(
            _dados_cadastro(),
            construir_url_confirmacao=construtor,
        )
        self.assertNotEqual(novo_usuario.pk, usuario.pk)

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
    def test_encerrar_conta_bloqueado_para_suspenso_bloqueado_e_agendamento_confirmado(self):
        """CA-01-14."""
        _, construtor = self._capturar_tokens()
        usuario = UsuarioService.cadastrar(
            _dados_cadastro(),
            construir_url_confirmacao=construtor,
        )

        for status_punido in (StatusUsuario.SUSPENSO, StatusUsuario.BLOQUEADO):
            Usuario.objects.filter(pk=usuario.pk).update(status=status_punido)
            usuario.refresh_from_db()
            with self.assertRaises(EncerramentoContaBloqueado):
                UsuarioService.encerrar_conta(usuario, "Rm3d!9xQ")

        Usuario.objects.filter(pk=usuario.pk).update(status=StatusUsuario.ATIVO)
        usuario.refresh_from_db()
        with self.assertRaises(RegraNegocioViolada) as ctx:
            UsuarioService.encerrar_conta(
                usuario,
                "Rm3d!9xQ",
                verificador_agendamentos_confirmados=lambda _u: True,
            )
        self.assertIn("agendamentos confirmados", str(ctx.exception))
