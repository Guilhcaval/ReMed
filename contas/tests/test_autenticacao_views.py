"""Testes de integração de login, logout, 2FA, sessão e mixins de permissão (Spec 02)."""

from datetime import date, timedelta

import pyotp
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.views import View

from contas.models import DispositivoTotp, SessaoUsuario, StatusUsuario, Usuario
from contas.services import SessaoService, TotpService
from nucleo.mixins import (
    SESSAO_CHAVE_2FA_VERIFICADO,
    FuncaoAdminObrigatoriaMixin,
    PerfilObrigatorioMixin,
)


class _ViewApenasDoador(PerfilObrigatorioMixin, View):
    perfis_permitidos = ("doador",)

    def get(self, request):
        return HttpResponse("ok-doador")


class _ViewApenasReceitas(FuncaoAdminObrigatoriaMixin, View):
    funcao_admin = "verificacao_receitas"

    def get(self, request):
        return HttpResponse("ok-receitas")


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
)
class AutenticacaoViewsEMixinsTest(TestCase):
    def _criar_usuario(
        self,
        *,
        email: str = "cidadao@exemplo.com",
        cpf: str = "52998224725",
        confirmado: bool = True,
        perfil_doador: bool = True,
        perfil_solicitante: bool = False,
        is_superuser: bool = False,
        funcoes: tuple[str, ...] = (),
    ) -> Usuario:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo="Usuário Teste",
            data_nascimento=date(1992, 6, 15),
            celular="11987654321",
            perfil_doador=perfil_doador,
            perfil_solicitante=perfil_solicitante,
            is_superuser=is_superuser,
            is_staff=is_superuser,
            email_confirmado_em=timezone.now() if confirmado else None,
        )
        if funcoes:
            grupos = [Group.objects.get_or_create(name=nome)[0] for nome in funcoes]
            usuario.groups.set(grupos)
        return usuario

    def test_get_login_renderiza_email_ou_cpf_sem_cnpj_e_elementos_esperados(self):
        resposta = self.client.get(reverse("contas:login"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Entrar no ReMed")
        self.assertContains(resposta, "E-mail ou CPF")
        self.assertNotContains(resposta, "CNPJ")
        self.assertContains(resposta, "Mostrar")
        self.assertContains(resposta, "Esqueci minha senha")
        self.assertContains(resposta, "Criar conta")
        self.assertContains(resposta, "Continuar como visitante")

    def test_login_rotaciona_sessao_registra_sessao_usuario_e_bloqueia_open_redirect(self):
        """CA-02-01 e CA-02-12."""
        usuario = self._criar_usuario()
        self.client.get(reverse("contas:login"))
        chave_antes = self.client.session.session_key

        resposta = self.client.post(
            reverse("contas:login"),
            data={
                "identificador": "529.982.247-25",
                "senha": "Rm3d!Senha1",
                "next": "https://externo.exemplo/roubo",
            },
        )
        self.assertRedirects(resposta, settings.LOGIN_REDIRECT_URL)
        chave_depois = self.client.session.session_key
        self.assertNotEqual(chave_antes, chave_depois)
        self.assertTrue(
            SessaoUsuario.objects.filter(usuario=usuario, session_key=chave_depois).exists()
        )

    def test_login_bloqueio_6a_tentativa_e_nao_confirmado_mostra_reenvio(self):
        self._criar_usuario(confirmado=False)
        url = reverse("contas:login")

        r_nao_conf = self.client.post(
            url, data={"identificador": "cidadao@exemplo.com", "senha": "Rm3d!Senha1"}
        )
        self.assertEqual(r_nao_conf.status_code, 200)
        self.assertContains(r_nao_conf, reverse("contas:reenviar_confirmacao"))

        # Mais 4 falhas totalizando 5 -> 6ª retorna 429 com mensagem literal
        for _ in range(4):
            r = self.client.post(
                url, data={"identificador": "cidadao@exemplo.com", "senha": "Errada!1"}
            )
            self.assertContains(r, "E-mail/CPF ou senha incorretos")
        sexta = self.client.post(
            url, data={"identificador": "cidadao@exemplo.com", "senha": "Rm3d!Senha1"}
        )
        self.assertEqual(sexta.status_code, 429)
        self.assertContains(sexta, "Muitas tentativas. Tente novamente mais tarde", status_code=429)

    def test_logout_recusa_get_com_405_e_encerra_sessao_em_post(self):
        """CA-02-06."""
        usuario = self._criar_usuario()
        self.client.post(
            reverse("contas:login"),
            data={"identificador": "cidadao@exemplo.com", "senha": "Rm3d!Senha1"},
        )
        chave = self.client.session.session_key

        r_get = self.client.get(reverse("contas:logout"))
        self.assertEqual(r_get.status_code, 405)
        self.assertTrue(SessaoUsuario.objects.filter(usuario=usuario, session_key=chave).exists())

        r_post = self.client.post(reverse("contas:logout"))
        self.assertRedirects(r_post, reverse("contas:login"))
        self.assertFalse(SessaoUsuario.objects.filter(session_key=chave).exists())

    def test_expiracao_de_sessao_30_min_e_revogacao_por_troca_de_senha_e_suspensao(self):
        """CA-02-05 e revogação de sessão no fluxo HTTP real."""
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")

        usuario = self._criar_usuario()
        self.client.post(
            reverse("contas:login"),
            data={"identificador": "cidadao@exemplo.com", "senha": "Rm3d!Senha1"},
        )
        url_perfil = reverse("contas:perfil_editar")
        self.assertEqual(self.client.get(url_perfil).status_code, 200)

        # Expiração após > 30 minutos de inatividade
        chave = self.client.session.session_key
        Session.objects.filter(session_key=chave).update(
            expire_date=timezone.now() - timedelta(minutes=31)
        )
        r_exp = self.client.get(url_perfil)
        self.assertEqual(r_exp.status_code, 302)
        self.assertTrue(r_exp["Location"].startswith(settings.LOGIN_URL))

        # Novo login -> troca de senha revoga sessão imediatamente
        self.client.post(
            reverse("contas:login"),
            data={"identificador": "cidadao@exemplo.com", "senha": "Rm3d!Senha1"},
        )
        usuario.set_password("Rm3d!SenhaNova2")
        usuario.save(update_fields=["password"])
        SessaoService.encerrar_todas_sessoes(usuario.pk)
        self.assertEqual(self.client.get(url_perfil).status_code, 302)

        # Novo login -> suspensão revoga sessão imediatamente
        self.client.post(
            reverse("contas:login"),
            data={"identificador": "cidadao@exemplo.com", "senha": "Rm3d!SenhaNova2"},
        )
        self.assertEqual(self.client.get(url_perfil).status_code, 200)
        Usuario.objects.filter(pk=usuario.pk).update(status=StatusUsuario.SUSPENSO, is_active=False)
        SessaoService.encerrar_todas_sessoes(usuario.pk)
        self.assertEqual(self.client.get(url_perfil).status_code, 302)

    def test_fluxo_web_2fa_pareamento_verificacao_e_regeneracao(self):
        """CA-02-07, CA-02-08 e CA-02-09 nas views."""
        admin = self._criar_usuario(
            email="admin@exemplo.com",
            cpf="11144477735",
            funcoes=("verificacao_receitas",),
        )
        r_login = self.client.post(
            reverse("contas:login"),
            data={"identificador": "admin@exemplo.com", "senha": "Rm3d!Senha1"},
        )
        self.assertRedirects(r_login, reverse("contas:totp_configurar"))
        self.assertIs(self.client.session[SESSAO_CHAVE_2FA_VERIFICADO], False)

        # GET configurar gera QR local em data URI (sem CDN/URL externa)
        r_cfg = self.client.get(reverse("contas:totp_configurar"))
        self.assertEqual(r_cfg.status_code, 200)
        self.assertContains(r_cfg, "data:image/svg+xml")

        dispositivo = DispositivoTotp.objects.get(usuario=admin)
        codigo = pyotp.TOTP(dispositivo.segredo).now()
        r_ativ = self.client.post(reverse("contas:totp_configurar"), data={"codigo": codigo})
        self.assertEqual(r_ativ.status_code, 200)
        self.assertContains(r_ativ, "Guarde seus 8 códigos de recuperação agora.")
        self.assertIs(self.client.session[SESSAO_CHAVE_2FA_VERIFICADO], True)

        # Novo login direciona para totp_verificar (já possui dispositivo ativo)
        self.client.post(reverse("contas:logout"))
        r_login2 = self.client.post(
            reverse("contas:login"),
            data={"identificador": "admin@exemplo.com", "senha": "Rm3d!Senha1"},
        )
        self.assertRedirects(r_login2, reverse("contas:totp_verificar"))

    def test_matriz_permissoes_mixins_e_restricao_is_superuser(self):
        """CA-02-11: is_superuser sem função explícita recebe HTTP 403; 2FA obrigatório."""
        factory = RequestFactory()
        view_doador = _ViewApenasDoador.as_view()
        view_receitas = _ViewApenasReceitas.as_view()

        def _req(usuario, *, verificado_2fa: bool = False):
            req = factory.get("/rota-protegida/")
            req.user = usuario
            req.session = {SESSAO_CHAVE_2FA_VERIFICADO: verificado_2fa}
            return req

        # 1. Cidadão apenas solicitante -> 403 em rota de doador
        solicitante = self._criar_usuario(
            email="sol@exemplo.com",
            cpf="52998224725",
            perfil_doador=False,
            perfil_solicitante=True,
        )
        self.assertEqual(view_doador(_req(solicitante)).status_code, 403)

        # 2. Cidadão doador -> 200 em rota de doador, 403 em rota administrativa
        doador = self._criar_usuario(email="doa@exemplo.com", cpf="11144477735", perfil_doador=True)
        self.assertEqual(view_doador(_req(doador)).status_code, 200)
        self.assertEqual(view_receitas(_req(doador, verificado_2fa=True)).status_code, 403)

        # 3. Superusuário SEM função explícita verificacao_receitas -> HTTP 403 (ADR 0010!)
        superusuario = self._criar_usuario(
            email="super@exemplo.com",
            cpf="39053344705",
            is_superuser=True,
            funcoes=(),
        )
        self.assertEqual(view_receitas(_req(superusuario, verificado_2fa=True)).status_code, 403)

        # 4. Admin com gestao_usuarios tentando rota verificacao_receitas -> HTTP 403
        admin_usuarios = self._criar_usuario(
            email="gestao@exemplo.com",
            cpf="71428793860",
            funcoes=("gestao_usuarios",),
        )
        self.assertEqual(view_receitas(_req(admin_usuarios, verificado_2fa=True)).status_code, 403)

        # 5. Admin com função correta SEM 2FA -> 302 para configurar/verificar
        admin_receitas = self._criar_usuario(
            email="rec@exemplo.com",
            cpf="16899535009",
            funcoes=("verificacao_receitas",),
        )
        r_sem_2fa = view_receitas(_req(admin_receitas, verificado_2fa=False))
        self.assertEqual(r_sem_2fa.status_code, 302)
        self.assertTrue(r_sem_2fa["Location"].startswith(reverse("contas:totp_configurar")))

        # Com TOTP ativo mas sessão não verificada -> 302 para totp_verificar
        p = TotpService.iniciar_pareamento(admin_receitas)
        TotpService.confirmar_pareamento(
            admin_receitas, pyotp.TOTP(p.segredo_manual).now(), "127.0.0.1"
        )
        r_pend_2fa = view_receitas(_req(admin_receitas, verificado_2fa=False))
        self.assertEqual(r_pend_2fa.status_code, 302)
        self.assertTrue(r_pend_2fa["Location"].startswith(reverse("contas:totp_verificar")))

        # 6. Admin com função correta E 2FA concluído -> 200
        self.assertEqual(view_receitas(_req(admin_receitas, verificado_2fa=True)).status_code, 200)

    def test_recuperar_senha_em_breve_renderiza_aviso(self):
        resposta = self.client.get(reverse("contas:recuperar_senha_em_breve"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Recurso disponível em breve")

    def test_login_exibe_aviso_informativo_quando_next_eh_cadastro_ponto_coleta(self):
        url_login = reverse("contas:login")
        url_cadastrar_ponto = reverse("pontos_coleta:cadastrar")
        url_cadastro_pf = reverse("contas:cadastro")

        resposta_get = self.client.get(f"{url_login}?next={url_cadastrar_ponto}")
        self.assertEqual(resposta_get.status_code, 200)
        self.assertIs(resposta_get.context["aviso_cadastro_ponto_coleta"], True)
        self.assertContains(
            resposta_get,
            "Para cadastrar um Ponto de Coleta (Pessoa Jurídica), entre primeiro com sua conta de",
        )
        self.assertContains(resposta_get, "Crie sua conta de Pessoa Física primeiro")
        self.assertContains(resposta_get, f'href="{url_cadastro_pf}"')

        # Em POST inválido mantendo o mesmo next, o aviso continua visível
        resposta_post = self.client.post(
            url_login,
            data={
                "identificador": "inexistente@exemplo.com",
                "senha": "Errada!1",
                "next": url_cadastrar_ponto,
            },
        )
        self.assertEqual(resposta_post.status_code, 200)
        self.assertIs(resposta_post.context["aviso_cadastro_ponto_coleta"], True)
        self.assertContains(resposta_post, "Crie sua conta de Pessoa Física primeiro")

    def test_login_nao_exibe_aviso_ponto_coleta_sem_next_ou_com_outro_destino(self):
        url_login = reverse("contas:login")
        url_perfil = reverse("contas:perfil_editar")

        for url in (
            url_login,
            f"{url_login}?next={url_perfil}",
            f"{url_login}?next=https://externo.exemplo/pontos-coleta/cadastrar/",
        ):
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 200)
                self.assertIs(resposta.context["aviso_cadastro_ponto_coleta"], False)
                self.assertNotContains(resposta, "Crie sua conta de Pessoa Física primeiro")
                self.assertNotContains(
                    resposta,
                    "Para cadastrar um Ponto de Coleta (Pessoa Jurídica)",
                )
