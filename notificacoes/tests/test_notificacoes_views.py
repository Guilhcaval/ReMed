"""Testes de integração das views da central de notificações (Spec 03 / RF017)."""

from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from contas.models import Usuario
from notificacoes.models import StatusNotificacao, TipoNotificacao
from notificacoes.services import NotificacaoService


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class NotificacoesViewsTest(TestCase):
    def _criar_e_logar(self, email: str, cpf: str) -> Usuario:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=f"Usuário {email}",
            data_nascimento=date(1991, 4, 12),
            celular="11988881111",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )
        self.client.force_login(usuario)
        return usuario

    def test_visitante_redirecionado_para_login(self):
        resposta = self.client.get(reverse("notificacoes:lista"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("contas:login"), resposta["Location"])

    def test_lista_filtros_datas_invertidas_e_paginacao(self):
        """CA-03-05: lista paginada, filtros e validação de período invertido."""
        usuario = self._criar_e_logar("cidadao@exemplo.com", "52998224725")
        for indice in range(22):
            NotificacaoService.registrar_evento(
                destinatario=usuario,
                tipo=TipoNotificacao.NOVA_CORRESPONDENCIA,
                contexto={"medicamento": f"Remédio {indice}"},
                enviar_email=False,
            )

        resp = self.client.get(reverse("notificacoes:lista"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Notificações")
        self.assertEqual(len(resp.context["pagina"].object_list), 20)
        self.assertEqual(resp.context["total_nao_lidas"], 22)

        resp_p2 = self.client.get(reverse("notificacoes:lista"), {"page": 2})
        self.assertEqual(resp_p2.status_code, 200)
        self.assertEqual(len(resp_p2.context["pagina"].object_list), 2)

        # Datas invertidas exibem erro de validação
        resp_inv = self.client.get(
            reverse("notificacoes:lista"),
            {"data_inicio": "2026-11-25", "data_fim": "2026-11-20"},
        )
        self.assertEqual(resp_inv.status_code, 200)
        self.assertContains(resp_inv, "A data inicial não pode ser posterior à data final")

    def test_marcar_lida_post_exclusivo_protecao_open_redirect_e_isolamento(self):
        """POST exclusivo (405 em GET), sem open redirect e 404 para notificação de terceiros."""
        outro = Usuario.objects.create_user(
            email="outro@exemplo.com",
            cpf="11144477735",
            password="Rm3d!Senha1",
            nome_completo="Outro Usuário",
            data_nascimento=date(1990, 1, 1),
            celular="11977771111",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )
        notif_outro = NotificacaoService.registrar_evento(
            destinatario=outro,
            tipo=TipoNotificacao.NOVA_MENSAGEM,
            enviar_email=False,
        ).notificacao_plataforma

        usuario = self._criar_e_logar("dona@exemplo.com", "52998224725")
        notif = NotificacaoService.registrar_evento(
            destinatario=usuario,
            tipo=TipoNotificacao.NOVA_MENSAGEM,
            url_destino="/contas/perfil/",
            enviar_email=False,
        ).notificacao_plataforma

        url_ler = reverse("notificacoes:marcar_lida", kwargs={"notificacao_id": notif.pk})
        self.assertEqual(self.client.get(url_ler).status_code, 405)
        self.assertEqual(
            self.client.get(reverse("notificacoes:marcar_todas_lidas")).status_code, 405
        )

        # Tentativa de marcar notificação de outro usuário -> 404
        url_outro = reverse("notificacoes:marcar_lida", kwargs={"notificacao_id": notif_outro.pk})
        self.assertEqual(self.client.post(url_outro).status_code, 404)

        # POST com next externo não redireciona para domínio externo
        resp = self.client.post(url_ler, {"next": "https://malicioso.exemplo/steal"})
        self.assertRedirects(resp, reverse("notificacoes:lista"))
        notif.refresh_from_db()
        self.assertEqual(notif.status, StatusNotificacao.LIDA)

    def test_marcar_todas_lidas_atualiza_apenas_usuario_logado(self):
        outro = Usuario.objects.create_user(
            email="outro2@exemplo.com",
            cpf="11144477735",
            password="Rm3d!Senha1",
            nome_completo="Outro Dois",
            data_nascimento=date(1990, 1, 1),
            celular="11977772222",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )
        NotificacaoService.registrar_evento(
            destinatario=outro, tipo=TipoNotificacao.NOVA_MENSAGEM, enviar_email=False
        )

        usuario = self._criar_e_logar("principal@exemplo.com", "52998224725")
        for _ in range(3):
            NotificacaoService.registrar_evento(
                destinatario=usuario, tipo=TipoNotificacao.NOVA_MENSAGEM, enviar_email=False
            )

        resp = self.client.post(reverse("notificacoes:marcar_todas_lidas"))
        self.assertRedirects(resp, reverse("notificacoes:lista"))
        self.assertEqual(NotificacaoService.contar_nao_lidas(usuario.pk), 0)
        self.assertEqual(NotificacaoService.contar_nao_lidas(outro.pk), 1)
