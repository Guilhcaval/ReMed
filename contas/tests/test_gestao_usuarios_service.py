"""Testes unitários e de banco para GestaoUsuariosService e AcaoGestaoUsuario (Spec 04 / RF004)."""

import threading
from datetime import UTC, date, datetime, timedelta

import pyotp
from django.contrib.auth.models import Group
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import DatabaseError, IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from contas.exceptions import (
    AcumuloFuncoesProibido,
    ContaAnonimizadaImutavel,
    MotivoObrigatorio,
    UltimoAdministradorAtivo,
)
from contas.models import (
    AcaoGestaoUsuario,
    DispositivoTotp,
    EnderecoUsuario,
    SessaoUsuario,
    StatusUsuario,
    TipoAcaoGestaoUsuario,
    Usuario,
)
from contas.services import (
    FiltrosConsultaUsuarios,
    GestaoUsuariosService,
    SessaoService,
    TotpService,
)
from notificacoes.models import CanalNotificacao, Notificacao, TipoNotificacao
from nucleo.exceptions import PermissaoNegada, RegraNegocioViolada


def _criar_usuario_teste(
    *,
    email: str,
    cpf: str,
    nome: str = "Usuário Teste",
    status: str = StatusUsuario.ATIVO,
    confirmado: bool = True,
    anonimizado: bool = False,
    funcoes: tuple[str, ...] = (),
    ativar_totp: bool = False,
) -> tuple[Usuario, str]:
    if anonimizado:
        usuario = Usuario.objects.create(
            email=None,
            cpf=None,
            nome_completo="",
            data_nascimento=None,
            celular="",
            perfil_doador=False,
            status=StatusUsuario.INATIVO,
            is_active=False,
            email_confirmado_em=None,
            anonimizado_em=timezone.now(),
        )
        usuario.set_unusable_password()
        usuario.save(update_fields=["password"])
    else:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=nome,
            data_nascimento=date(1988, 6, 20),
            celular="11999998888",
            perfil_doador=True,
            status=status,
            is_active=status == StatusUsuario.ATIVO,
            email_confirmado_em=timezone.now() if confirmado else None,
        )
    if funcoes:
        grupos = [Group.objects.get_or_create(name=f)[0] for f in funcoes]
        usuario.groups.set(grupos)

    segredo = ""
    if ativar_totp:
        segredo = pyotp.random_base32()
        DispositivoTotp.objects.create(
            usuario=usuario,
            segredo=segredo,
            confirmado_em=timezone.now(),
        )
    return usuario, segredo


def _criar_sessao_ativa(usuario: Usuario) -> str:
    store = SessionStore()
    store["_auth_user_id"] = str(usuario.pk)
    store.create()
    SessaoService.registrar_sessao(usuario.pk, store.session_key)
    return store.session_key


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
)
class GestaoUsuariosServiceTest(TestCase):
    def test_consulta_minimizacao_lgpd_e_busca_cpf_parcial(self):
        """CA-04-01: CPF mascarado na saída, busca parcial >= 3 dígitos, sem endereço/receitas."""
        admin, _ = _criar_usuario_teste(
            email="admin@exemplo.com",
            cpf="52998224725",
            nome="Admin Gestor",
            funcoes=("gestao_usuarios",),
        )
        cidadao, _ = _criar_usuario_teste(
            email="maria@exemplo.com",
            cpf="11144477735",
            nome="Maria Oliveira",
        )
        EnderecoUsuario.objects.create(
            usuario=cidadao,
            cep="01310100",
            logradouro="Avenida Sigilosa",
            numero="999",
            bairro="Centro",
            municipio="São Paulo",
            estado="SP",
        )

        # Menos de 3 dígitos é rejeitado
        with self.assertRaises(RegraNegocioViolada):
            GestaoUsuariosService.consultar(admin, FiltrosConsultaUsuarios(termo="11"))

        # Busca por 3+ dígitos do CPF encontra e retorna projeção minimizada
        pagina = GestaoUsuariosService.consultar(admin, FiltrosConsultaUsuarios(termo="1114"))
        self.assertEqual(pagina.total_encontrados, 1)
        resumo = pagina.pagina.object_list[0]
        self.assertEqual(resumo.id, cidadao.pk)
        self.assertEqual(resumo.cpf_mascarado, "111.***.***-35")
        self.assertFalse(hasattr(resumo, "cpf"))
        self.assertFalse(hasattr(resumo, "endereco"))

    def test_alterar_status_motivo_obrigatorio_sessoes_gancho_e_notificacao(self):
        """CA-04-02/03: motivo obrigatório literal, revogação de sessão, gancho e auditoria."""
        admin, _ = _criar_usuario_teste(
            email="admin-u@exemplo.com",
            cpf="52998224725",
            funcoes=("gestao_usuarios",),
        )
        cidadao, _ = _criar_usuario_teste(
            email="cidadao@exemplo.com",
            cpf="11144477735",
            nome="João Silva",
        )
        chave_sessao = _criar_sessao_ativa(cidadao)

        # Motivo vazio ou só espaços para suspensão/bloqueio gera mensagem literal da Spec 04
        for motivo_invalido in ("", "   "):
            with self.assertRaises(MotivoObrigatorio) as ctx:
                GestaoUsuariosService.alterar_status(
                    admin, cidadao.pk, StatusUsuario.SUSPENSO, motivo_invalido
                )
            self.assertEqual(str(ctx.exception), "Informe o motivo da suspensão ou do bloqueio")

        cancelados: list[int] = []
        acao = GestaoUsuariosService.alterar_status(
            admin,
            cidadao.pk,
            StatusUsuario.SUSPENSO,
            "Descumprimento reiterado das regras sanitárias.",
            cancelador_operacoes_abertas=lambda u: cancelados.append(u.pk),
        )
        cidadao.refresh_from_db()
        self.assertEqual(cidadao.status, StatusUsuario.SUSPENSO)
        self.assertFalse(cidadao.is_active)
        self.assertEqual(cancelados, [cidadao.pk])
        self.assertFalse(Session.objects.filter(session_key=chave_sessao).exists())
        self.assertFalse(SessaoUsuario.objects.filter(usuario=cidadao).exists())
        self.assertEqual(acao.acao, TipoAcaoGestaoUsuario.SUSPENDER)
        self.assertEqual(acao.status_anterior, StatusUsuario.ATIVO)
        self.assertEqual(acao.status_novo, StatusUsuario.SUSPENSO)

        # Auditoria e notificação obrigatória seguranca_conta com motivo
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="usuario.status_alterado",
                entidade_id=str(cidadao.pk),
                ator=admin,
            ).exists()
        )
        notif = Notificacao.objects.filter(
            destinatario=cidadao,
            tipo=TipoNotificacao.SEGURANCA_CONTA,
            canal=CanalNotificacao.PLATAFORMA,
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("Descumprimento reiterado", notif.mensagem)

        # Conta anonimizada é imutável
        anon, _ = _criar_usuario_teste(
            email="anon@exemplo.com",
            cpf="12345678909",
            anonimizado=True,
        )
        with self.assertRaises(ContaAnonimizadaImutavel):
            GestaoUsuariosService.alterar_status(
                admin, anon.pk, StatusUsuario.ATIVO, "Tentativa indevida"
            )

    def test_funcoes_admin_segregacao_primeira_funcao_sem_2fa_e_trava_ultimo_admin(self):
        """CA-04-04, CA-04-05 e CA-04-06."""
        t0 = datetime(2026, 11, 23, 15, 0, 0, tzinfo=UTC)
        admin1, segredo1 = _criar_usuario_teste(
            email="admin1@exemplo.com",
            cpf="52998224725",
            funcoes=("gestao_administradores", "gestao_usuarios"),
            ativar_totp=True,
        )
        cidadao, _ = _criar_usuario_teste(
            email="futuro-admin@exemplo.com",
            cpf="11144477735",
            nome="Futura Admin",
        )
        sessao_cidadao = _criar_sessao_ativa(cidadao)

        # Proibição de autoalteração de funções
        with self.assertRaises(PermissaoNegada):
            GestaoUsuariosService.atualizar_funcoes_administrativas(
                admin1,
                admin1.pk,
                ["gestao_administradores"],
                pyotp.TOTP(segredo1).at(t0),
                "Autoalteração proibida",
                "192.0.2.10",
                momento=t0,
            )

        # Acúmulo proibido gestao_usuarios + verificacao_receitas (CA-04-05)
        with self.assertRaises(AcumuloFuncoesProibido):
            GestaoUsuariosService.atualizar_funcoes_administrativas(
                admin1,
                cidadao.pk,
                ["gestao_usuarios", "verificacao_receitas"],
                pyotp.TOTP(segredo1).at(t0),
                "Tentativa de acúmulo",
                "192.0.2.10",
                momento=t0,
            )

        # Atribuir primeira função administrativa a cidadão sem 2FA encerra sessões e notifica
        t1 = t0 + timedelta(seconds=30)
        acao = GestaoUsuariosService.atualizar_funcoes_administrativas(
            admin1,
            cidadao.pk,
            ["gestao_administradores"],
            pyotp.TOTP(segredo1).at(t1),
            "Promoção aprovada pela coordenação",
            "192.0.2.10",
            momento=t1,
        )
        self.assertEqual(acao.acao, TipoAcaoGestaoUsuario.ALTERAR_FUNCOES_ADMIN)
        self.assertEqual(acao.funcoes_anteriores, [])
        self.assertEqual(acao.funcoes_novas, ["gestao_administradores"])
        self.assertFalse(Session.objects.filter(session_key=sessao_cidadao).exists())
        self.assertFalse(SessaoUsuario.objects.filter(usuario=cidadao).exists())
        notif = Notificacao.objects.filter(
            destinatario=cidadao,
            tipo=TipoNotificacao.SEGURANCA_CONTA,
            canal=CanalNotificacao.PLATAFORMA,
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("2FA", notif.mensagem)

        # Com 2 Admins ativos, remover função de cidadao funciona; depois admin1 é o último ativo
        t2 = t1 + timedelta(seconds=30)
        GestaoUsuariosService.atualizar_funcoes_administrativas(
            admin1,
            cidadao.pk,
            [],
            pyotp.TOTP(segredo1).at(t2),
            "Retorno ao perfil cidadão",
            "192.0.2.10",
            momento=t2,
        )

        # Trava do último Administrador ativo ao tentar suspender/inativar admin1 por outro gestor
        gestor_usuarios, _ = _criar_usuario_teste(
            email="gestor-u@exemplo.com",
            cpf="12345678909",
            funcoes=("gestao_usuarios",),
        )
        with self.assertRaises(UltimoAdministradorAtivo) as ctx:
            GestaoUsuariosService.alterar_status(
                gestor_usuarios,
                admin1.pk,
                StatusUsuario.SUSPENSO,
                "Tentativa contra último admin",
            )
        self.assertEqual(str(ctx.exception), "Não é possível remover o último Administrador ativo")

    def test_reset_2fa_cria_acao_gestao_auditoria_e_notificacao(self):
        """Reset de 2FA de outro Administrador exige >= 2 Admins ativos e registra histórico."""
        t0 = datetime(2026, 11, 23, 16, 0, 0, tzinfo=UTC)
        admin1, segredo1 = _criar_usuario_teste(
            email="adm-a@exemplo.com",
            cpf="52998224725",
            funcoes=("gestao_administradores",),
            ativar_totp=True,
        )
        admin2, _ = _criar_usuario_teste(
            email="adm-b@exemplo.com",
            cpf="11144477735",
            funcoes=("gestao_administradores",),
            ativar_totp=True,
        )
        sessao_admin2 = _criar_sessao_ativa(admin2)

        TotpService.resetar_por_administrador(
            admin1,
            admin2,
            pyotp.TOTP(segredo1).at(t0),
            "192.0.2.30",
            motivo="Troca de celular corporativo confirmada",
            momento=t0,
        )
        self.assertFalse(DispositivoTotp.objects.filter(usuario=admin2).exists())
        self.assertFalse(Session.objects.filter(session_key=sessao_admin2).exists())
        self.assertTrue(
            AcaoGestaoUsuario.objects.filter(
                usuario_alvo=admin2,
                responsavel=admin1,
                acao=TipoAcaoGestaoUsuario.RESETAR_2FA,
            ).exists()
        )
        self.assertTrue(
            Notificacao.objects.filter(
                destinatario=admin2,
                tipo=TipoNotificacao.SEGURANCA_CONTA,
                canal=CanalNotificacao.PLATAFORMA,
            ).exists()
        )

    def test_check_constraint_motivo_e_trigger_imutabilidade_acao_gestao(self):
        """CheckConstraint rejeita motivo vazio/espaços e trigger 0006 bloqueia UPDATE e DELETE."""
        admin, _ = _criar_usuario_teste(
            email="admin-trig@exemplo.com",
            cpf="52998224725",
            funcoes=("gestao_usuarios",),
        )
        alvo, _ = _criar_usuario_teste(email="alvo-trig@exemplo.com", cpf="11144477735")

        for motivo_ruim in ("", "   ", "\t\n "):
            with self.assertRaises(IntegrityError), transaction.atomic():
                AcaoGestaoUsuario.objects.create(
                    usuario_alvo=alvo,
                    responsavel=admin,
                    acao=TipoAcaoGestaoUsuario.SUSPENDER,
                    status_anterior=StatusUsuario.ATIVO,
                    status_novo=StatusUsuario.SUSPENSO,
                    motivo=motivo_ruim,
                )

        acao = AcaoGestaoUsuario.objects.create(
            usuario_alvo=alvo,
            responsavel=admin,
            acao=TipoAcaoGestaoUsuario.SUSPENDER,
            status_anterior=StatusUsuario.ATIVO,
            status_novo=StatusUsuario.SUSPENSO,
            motivo="Motivo válido registrado",
        )

        # Trigger 0006 bloqueia UPDATE
        with self.assertRaises(DatabaseError), transaction.atomic():
            AcaoGestaoUsuario.objects.filter(pk=acao.pk).update(motivo="Adulterado")

        # Trigger 0006 bloqueia DELETE
        with self.assertRaises(DatabaseError), transaction.atomic():
            AcaoGestaoUsuario.objects.filter(pk=acao.pk).delete()


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
)
class UltimoAdminConcorrenciaTest(TransactionTestCase):
    def test_remocao_simultanea_de_dois_ultimos_admins_preserva_ao_menos_um(self):
        """CA-04-06 sob concorrência no PostgreSQL: nunca zera gestao_administradores ativos."""
        t0 = datetime(2026, 11, 23, 17, 0, 0, tzinfo=UTC)
        admin1, segredo1 = _criar_usuario_teste(
            email="conc-adm1@exemplo.com",
            cpf="52998224725",
            funcoes=("gestao_administradores",),
            ativar_totp=True,
        )
        admin2, segredo2 = _criar_usuario_teste(
            email="conc-adm2@exemplo.com",
            cpf="11144477735",
            funcoes=("gestao_administradores",),
            ativar_totp=True,
        )

        barreira = threading.Barrier(2)
        sucessos: list[int] = []
        bloqueios: list[Exception] = []
        outros_erros: list[Exception] = []
        trava = threading.Lock()

        def _tentar_remover(ator: Usuario, alvo: Usuario, segredo: str):
            try:
                barreira.wait(timeout=5)
                GestaoUsuariosService.atualizar_funcoes_administrativas(
                    ator,
                    alvo.pk,
                    [],
                    pyotp.TOTP(segredo).at(t0),
                    "Remoção concorrente",
                    "192.0.2.99",
                    momento=t0,
                )
                with trava:
                    sucessos.append(alvo.pk)
            except UltimoAdministradorAtivo as exc:
                with trava:
                    bloqueios.append(exc)
            except Exception as exc:  # pragma: no cover
                with trava:
                    outros_erros.append(exc)
            finally:
                connections.close_all()

        t1 = threading.Thread(target=_tentar_remover, args=(admin1, admin2, segredo1))
        t2 = threading.Thread(target=_tentar_remover, args=(admin2, admin1, segredo2))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(outros_erros, [])
        self.assertEqual(len(sucessos), 1)
        self.assertEqual(len(bloqueios), 1)
        admins_restantes = Usuario.objects.filter(
            groups__name="gestao_administradores",
            status=StatusUsuario.ATIVO,
        ).count()
        self.assertEqual(admins_restantes, 1)
