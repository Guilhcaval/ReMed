"""Testes unitários de NotificacaoService, context processor e despachar_emails (Spec 03)."""

from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Group
from django.core import mail
from django.core.management import call_command
from django.db import transaction
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from contas.models import StatusUsuario, Usuario
from notificacoes.context_processors import contador_notificacoes
from notificacoes.models import (
    CanalNotificacao,
    Notificacao,
    OutboxEmail,
    StatusNotificacao,
    StatusOutboxEmail,
    TipoNotificacao,
)
from notificacoes.services import (
    CATALOGO_NOTIFICACOES,
    FiltrosNotificacao,
    NotificacaoService,
)
from nucleo.exceptions import RecursoNaoEncontrado, RegraNegocioViolada
from nucleo.models import ExecucaoRotina, ResultadoRotina


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REMED_NOTIFICACAO_EMAIL_LIMITE_HORA=20,
    REMED_NOTIFICACAO_ALERTA_FALHAS_LOTE=3,
)
class NotificacaoServiceTest(TestCase):
    def _criar_usuario(
        self,
        *,
        email: str = "usuario@exemplo.com",
        cpf: str = "52998224725",
        status: str = StatusUsuario.ATIVO,
        confirmado: bool = True,
        anonimizado: bool = False,
        funcoes: tuple[str, ...] = (),
    ) -> Usuario:
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
                nome_completo=f"Nome {email}",
                data_nascimento=date(1990, 5, 10),
                celular="11999990000",
                perfil_doador=True,
                status=status,
                is_active=status == StatusUsuario.ATIVO,
                email_confirmado_em=timezone.now() if confirmado else None,
            )
        if funcoes:
            grupos = [Group.objects.get_or_create(name=nome)[0] for nome in funcoes]
            usuario.groups.set(grupos)
        return usuario

    def test_criacao_atomica_e_rollback_em_falha_de_transacao(self):
        """CA-03-01: notificação na plataforma e outbox são atômicos com a operação de origem."""
        usuario = self._criar_usuario()

        resultado = NotificacaoService.registrar_evento(
            destinatario=usuario,
            tipo=TipoNotificacao.NOVA_CORRESPONDENCIA,
            contexto={"medicamento": "Dipirona 500mg"},
            url_destino="/notificacoes/",
        )
        self.assertIsNotNone(resultado.notificacao_plataforma)
        self.assertIsNotNone(resultado.outbox_email)
        self.assertFalse(resultado.email_suprimido)
        self.assertEqual(
            Notificacao.objects.filter(
                destinatario=usuario, canal=CanalNotificacao.PLATAFORMA
            ).count(),
            1,
        )
        self.assertEqual(
            OutboxEmail.objects.filter(
                destinatario=usuario, status=StatusOutboxEmail.PENDENTE
            ).count(),
            1,
        )

        # Rollback transacional desfaz notificação e outbox junto com a operação chamadora
        with self.assertRaises(RuntimeError), transaction.atomic():
            NotificacaoService.registrar_evento(
                destinatario=usuario,
                tipo=TipoNotificacao.ENTREGA_CONFIRMADA,
                contexto={"medicamento": "Amoxicilina 500mg"},
            )
            raise RuntimeError("Falha simulada na transação chamadora")

        self.assertEqual(
            Notificacao.objects.filter(
                destinatario=usuario, tipo=TipoNotificacao.ENTREGA_CONFIRMADA
            ).count(),
            0,
        )
        self.assertEqual(
            OutboxEmail.objects.filter(
                destinatario=usuario, tipo=TipoNotificacao.ENTREGA_CONFIRMADA
            ).count(),
            0,
        )

    def test_catalogo_cobre_todos_os_21_tipos_e_bloqueia_pii_e_local_indevido(self):
        """CA-03-03/RN-03-03: 21 tipos cobertos, bloqueio de PII e local_retirada restrito."""
        self.assertEqual(set(CATALOGO_NOTIFICACOES.keys()), set(TipoNotificacao.values))
        self.assertEqual(len(CATALOGO_NOTIFICACOES), 21)

        usuario = self._criar_usuario()

        # Chaves proibidas (PII / saúde / conteúdo livre / segredos) são bloqueadas
        for chave_proibida in (
            "cpf",
            "nome_terceiro",
            "telefone",
            "endereco",
            "motivo_saude",
            "receita",
            "texto_mensagem",
            "token",
        ):
            with self.subTest(chave_proibida=chave_proibida):
                with self.assertRaises(RegraNegocioViolada):
                    NotificacaoService.registrar_evento(
                        destinatario=usuario,
                        tipo=TipoNotificacao.NOVA_CORRESPONDENCIA,
                        contexto={"medicamento": "Paracetamol", chave_proibida: "dado-sensivel"},
                    )

        # local_retirada bloqueado antes de confirmação do agendamento
        with self.assertRaises(RegraNegocioViolada):
            NotificacaoService.registrar_evento(
                destinatario=usuario,
                tipo=TipoNotificacao.AGENDAMENTO_PROPOSTO,
                contexto={"medicamento": "Dipirona", "local_retirada": "UBS Centro"},
            )

        # local_retirada permitido após confirmação de agendamento
        res_agendado = NotificacaoService.registrar_evento(
            destinatario=usuario,
            tipo=TipoNotificacao.AGENDAMENTO_CONFIRMADO,
            contexto={
                "medicamento": "Dipirona 500mg",
                "data_hora": "25/11/2026 14:00",
                "local_retirada": "UBS Central - Sala 2",
            },
        )
        self.assertIn("UBS Central", res_agendado.notificacao_plataforma.mensagem)

        # URL externa proibida (evita open redirect em url_destino)
        for url_invalida in ("https://externo.exemplo/phish", "//externo.exemplo/x", "http://a"):
            with self.assertRaises(RegraNegocioViolada):
                NotificacaoService.registrar_evento(
                    destinatario=usuario,
                    tipo=TipoNotificacao.NOVA_MENSAGEM,
                    url_destino=url_invalida,
                )

        # Destinatário anonimizado rejeitado
        anon = self._criar_usuario(anonimizado=True)
        with self.assertRaises(RegraNegocioViolada):
            NotificacaoService.registrar_evento(
                destinatario=anon,
                tipo=TipoNotificacao.NOVA_MENSAGEM,
            )

    def test_limite_horario_suprime_nao_criticos_mas_preserva_plataforma_e_seguranca_conta(self):
        """CA-03-04: 20 e-mails não críticos/h; 21º suprimido; seguranca_conta sempre enfileira."""
        usuario = self._criar_usuario()

        for indice in range(20):
            res = NotificacaoService.registrar_evento(
                destinatario=usuario,
                tipo=TipoNotificacao.NOVA_CORRESPONDENCIA,
                contexto={"medicamento": f"Medicamento {indice}"},
            )
            self.assertFalse(res.email_suprimido)
            self.assertEqual(res.outbox_email.status, StatusOutboxEmail.PENDENTE)

        # 21ª notificação não crítica: plataforma criada, e-mail suprimido
        res_21 = NotificacaoService.registrar_evento(
            destinatario=usuario,
            tipo=TipoNotificacao.NOVA_CORRESPONDENCIA,
            contexto={"medicamento": "Medicamento 21"},
        )
        self.assertTrue(res_21.email_suprimido)
        self.assertIsNotNone(res_21.notificacao_plataforma)
        self.assertEqual(res_21.outbox_email.status, StatusOutboxEmail.SUPRIMIDA)

        # Notificação crítica seguranca_conta NÃO é suprimida
        res_seg = NotificacaoService.registrar_evento(
            destinatario=usuario,
            tipo=TipoNotificacao.SEGURANCA_CONTA,
            contexto={"evento_seguranca": "Alteração crítica na conta."},
        )
        self.assertFalse(res_seg.email_suprimido)
        self.assertTrue(res_seg.notificacao_plataforma.obrigatoria)
        self.assertEqual(res_seg.outbox_email.status, StatusOutboxEmail.PENDENTE)
        self.assertTrue(res_seg.outbox_email.critico_seguranca)

    def test_alerta_operacional_smtp_sem_loop_no_outbox(self):
        """RN-03-05: falhas SMTP >= limiar alertam gestao_administradores só na plataforma."""
        admin_gestor = self._criar_usuario(
            email="admin-gestor@exemplo.com",
            cpf="52998224725",
            funcoes=("gestao_administradores",),
        )
        admin_outro = self._criar_usuario(
            email="admin-usuarios@exemplo.com",
            cpf="11144477735",
            funcoes=("gestao_usuarios",),
        )
        cidadao = self._criar_usuario(email="cidadao@exemplo.com", cpf="12345678909")

        # 3 itens já na 3ª tentativa (próxima falha será a 4ª -> falha definitiva)
        for indice in range(3):
            OutboxEmail.objects.create(
                destinatario=cidadao,
                email_destino=cidadao.email,
                tipo=TipoNotificacao.NOVA_CORRESPONDENCIA,
                critico_seguranca=False,
                assunto=f"Teste {indice}",
                corpo_texto="Corpo",
                status=StatusOutboxEmail.PENDENTE,
                tentativas=3,
                proxima_tentativa_em=timezone.now() - timedelta(minutes=1),
            )

        outbox_antes = OutboxEmail.objects.count()
        with patch("notificacoes.services.send_mail", side_effect=OSError("SMTP fora do ar")):
            saida = StringIO()
            call_command("despachar_emails", stdout=saida)

        # Alerta operacional gravado na plataforma apenas para gestao_administradores
        alertas_gestor = Notificacao.objects.filter(
            destinatario=admin_gestor,
            tipo=TipoNotificacao.ALERTA_OPERACIONAL,
            canal=CanalNotificacao.PLATAFORMA,
        )
        self.assertEqual(alertas_gestor.count(), 1)
        self.assertEqual(
            Notificacao.objects.filter(
                destinatario=admin_outro, tipo=TipoNotificacao.ALERTA_OPERACIONAL
            ).count(),
            0,
        )
        # Anti-loop: nenhum novo OutboxEmail criado pelo alerta de falha SMTP!
        self.assertEqual(OutboxEmail.objects.count(), outbox_antes)
        self.assertEqual(
            OutboxEmail.objects.filter(status=StatusOutboxEmail.FALHA).count(),
            3,
        )
        execucao = ExecucaoRotina.objects.order_by("-id").first()
        self.assertIsNotNone(execucao)
        self.assertEqual(execucao.resultado, ResultadoRotina.PARCIAL)

    def test_listar_filtrar_e_marcar_como_lida_com_isolamento_por_usuario(self):
        """CA-03-05: filtros, marcação individual, em lote e isolamento entre usuários."""
        u1 = self._criar_usuario(email="u1@exemplo.com", cpf="52998224725")
        u2 = self._criar_usuario(email="u2@exemplo.com", cpf="11144477735")

        r1 = NotificacaoService.registrar_evento(
            destinatario=u1,
            tipo=TipoNotificacao.NOVA_CORRESPONDENCIA,
            contexto={"medicamento": "Dipirona"},
            enviar_email=False,
        )
        r2 = NotificacaoService.registrar_evento(
            destinatario=u1,
            tipo=TipoNotificacao.SEGURANCA_CONTA,
            contexto={"evento_seguranca": "Teste segurança"},
            enviar_email=False,
        )
        r_u2 = NotificacaoService.registrar_evento(
            destinatario=u2,
            tipo=TipoNotificacao.NOVA_MENSAGEM,
            enviar_email=False,
        )

        # Isolamento: u1 não pode marcar notificação de u2
        with self.assertRaises(RecursoNaoEncontrado):
            NotificacaoService.marcar_como_lida(r_u2.notificacao_plataforma.pk, u1.pk)

        # Marca 1 notificação de u1 como lida
        lida = NotificacaoService.marcar_como_lida(r1.notificacao_plataforma.pk, u1.pk)
        self.assertEqual(lida.status, StatusNotificacao.LIDA)
        self.assertIsNotNone(lida.lida_em)

        # Filtros por status e tipo
        so_nao_lidas = NotificacaoService.listar_do_usuario(
            u1.pk, FiltrosNotificacao(status="nao_lida")
        )
        self.assertEqual(so_nao_lidas.total_nao_lidas, 1)
        self.assertEqual(so_nao_lidas.total_filtradas, 1)
        self.assertEqual(so_nao_lidas.pagina.object_list[0].pk, r2.notificacao_plataforma.pk)

        so_tipo = NotificacaoService.listar_do_usuario(
            u1.pk, FiltrosNotificacao(tipo=TipoNotificacao.NOVA_CORRESPONDENCIA)
        )
        self.assertEqual(so_tipo.total_filtradas, 1)

        # Marcar todas de u1 não afeta u2
        qtd = NotificacaoService.marcar_todas_como_lidas(u1.pk)
        self.assertEqual(qtd, 1)
        self.assertEqual(NotificacaoService.contar_nao_lidas(u1.pk), 0)
        self.assertEqual(NotificacaoService.contar_nao_lidas(u2.pk), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_context_processor_zero_queries_para_anonimos_e_inativos(self):
        """Context processor não consulta o banco para usuários anônimos, inativos ou pendentes."""
        rf = RequestFactory()

        req_anon = rf.get("/")
        req_anon.user = AnonymousUser()
        with self.assertNumQueries(0):
            self.assertEqual(contador_notificacoes(req_anon), {"notificacoes_nao_lidas": 0})

        inativo = self._criar_usuario(
            email="inativo@exemplo.com",
            cpf="52998224725",
            status=StatusUsuario.INATIVO,
        )
        req_inativo = rf.get("/")
        req_inativo.user = inativo
        with self.assertNumQueries(0):
            self.assertEqual(contador_notificacoes(req_inativo), {"notificacoes_nao_lidas": 0})

        pendente = self._criar_usuario(
            email="pendente@exemplo.com",
            cpf="11144477735",
            confirmado=False,
        )
        req_pendente = rf.get("/")
        req_pendente.user = pendente
        with self.assertNumQueries(0):
            self.assertEqual(contador_notificacoes(req_pendente), {"notificacoes_nao_lidas": 0})

        ativo = self._criar_usuario(email="ativo@exemplo.com", cpf="12345678909")
        NotificacaoService.registrar_evento(
            destinatario=ativo,
            tipo=TipoNotificacao.NOVA_MENSAGEM,
            enviar_email=False,
        )
        req_ativo = rf.get("/")
        req_ativo.user = ativo
        with self.assertNumQueries(1):
            self.assertEqual(contador_notificacoes(req_ativo), {"notificacoes_nao_lidas": 1})
