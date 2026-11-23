"""Testes da barra de navegação global única e do context processor (ADRs 0005, 0006 e 0010)."""

from datetime import date
from html.parser import HTMLParser

import pyotp
from django.contrib.auth.models import AnonymousUser, Group
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from contas.models import DispositivoTotp, StatusUsuario, Usuario
from notificacoes.models import TipoNotificacao
from notificacoes.services import NotificacaoService
from nucleo.context_processors import navegacao_global
from nucleo.mixins import SESSAO_CHAVE_2FA_VERIFICADO


class _ExtratorNavbar(HTMLParser):
    """Extrai links, botões e aria-current dentro de <nav aria-label='Navegação principal'>."""

    def __init__(self):
        super().__init__()
        self._em_nav = False
        self._profundidade_nav = 0
        self._tag_atual: str | None = None
        self._attrs_atual: dict[str, str] = {}
        self._texto_atual: list[str] = []
        self.links: list[dict[str, str]] = []
        self.botoes: list[dict[str, str]] = []
        self.brand_href: str | None = None

    def handle_starttag(self, tag, attrs):
        mapa = {k: (v or "") for k, v in attrs}
        if tag == "nav" and mapa.get("aria-label") == "Navegação principal":
            self._em_nav = True
            self._profundidade_nav = 1
            return
        if not self._em_nav:
            return
        if tag == "nav":
            self._profundidade_nav += 1
        elif tag == "a":
            classes = mapa.get("class", "").split()
            if "navbar-brand" in classes:
                self.brand_href = mapa.get("href", "")
            elif "nav-link" in classes or "dropdown-item" in classes:
                self._tag_atual = "a"
                self._attrs_atual = mapa
                self._texto_atual = []
        elif tag == "button":
            self._tag_atual = "button"
            self._attrs_atual = mapa
            self._texto_atual = []

    def handle_data(self, data):
        if self._tag_atual is not None:
            self._texto_atual.append(data)

    def handle_endtag(self, tag):
        if not self._em_nav:
            return
        if tag == "nav":
            self._profundidade_nav -= 1
            if self._profundidade_nav == 0:
                self._em_nav = False
            return
        if self._tag_atual == tag:
            texto = " ".join(" ".join(self._texto_atual).split())
            item = {
                "texto": texto,
                "href": self._attrs_atual.get("href", ""),
                "aria_current": self._attrs_atual.get("aria-current", ""),
                "class": self._attrs_atual.get("class", ""),
            }
            if tag == "a":
                self.links.append(item)
            else:
                self.botoes.append(item)
            self._tag_atual = None
            self._attrs_atual = {}
            self._texto_atual = []


def _extrair_navbar(resposta) -> _ExtratorNavbar:
    extrator = _ExtratorNavbar()
    extrator.feed(resposta.content.decode("utf-8"))
    return extrator


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
)
class NavegacaoGlobalTest(TestCase):
    def _criar_usuario(
        self,
        *,
        email: str,
        cpf: str,
        status: str = StatusUsuario.ATIVO,
        confirmado: bool = True,
        anonimizado: bool = False,
        is_superuser: bool = False,
        funcoes: tuple[str, ...] = (),
        ativar_totp: bool = False,
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
            return usuario

        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=f"Usuário {email}",
            data_nascimento=date(1990, 5, 10),
            celular="11988887777",
            perfil_doador=True,
            status=status,
            is_active=status == StatusUsuario.ATIVO,
            is_superuser=is_superuser,
            is_staff=is_superuser,
            email_confirmado_em=timezone.now() if confirmado else None,
        )
        if funcoes:
            grupos = [Group.objects.get_or_create(name=nome)[0] for nome in funcoes]
            usuario.groups.set(grupos)
        if ativar_totp:
            DispositivoTotp.objects.create(
                usuario=usuario,
                segredo=pyotp.random_base32(),
                confirmado_em=timezone.now(),
            )
        return usuario

    def _logar(self, usuario: Usuario, *, verificado_2fa: bool | None = None) -> None:
        self.client.force_login(usuario)
        if verificado_2fa is not None:
            sessao = self.client.session
            sessao[SESSAO_CHAVE_2FA_VERIFICADO] = verificado_2fa
            sessao.save()

    def test_context_processor_zero_queries_para_anonimos_inativos_e_pendentes_2fa(self):
        rf = RequestFactory()

        # 1. Visitante anônimo -> 0 queries
        req_anon = rf.get("/pontos-coleta/")
        req_anon.user = AnonymousUser()
        req_anon.session = {}
        with self.assertNumQueries(0):
            ctx_anon = navegacao_global(req_anon)
        self.assertFalse(ctx_anon["nav_autenticado"])
        self.assertEqual(ctx_anon["notificacoes_nao_lidas"], 0)
        self.assertEqual(ctx_anon["nav_admin_itens"], ())

        # 2. Conta inativa -> 0 queries
        inativo = self._criar_usuario(
            email="inativo@exemplo.com",
            cpf="52998224725",
            status=StatusUsuario.INATIVO,
        )
        req_inativo = rf.get("/pontos-coleta/")
        req_inativo.user = inativo
        req_inativo.session = {}
        with self.assertNumQueries(0):
            ctx_inativo = navegacao_global(req_inativo)
        self.assertFalse(ctx_inativo["nav_autenticado"])
        self.assertEqual(ctx_inativo["notificacoes_nao_lidas"], 0)

        # 3. Conta com e-mail não confirmado -> 0 queries
        nao_conf = self._criar_usuario(
            email="pendente@exemplo.com",
            cpf="11144477735",
            confirmado=False,
        )
        req_nao_conf = rf.get("/pontos-coleta/")
        req_nao_conf.user = nao_conf
        req_nao_conf.session = {}
        with self.assertNumQueries(0):
            ctx_nao_conf = navegacao_global(req_nao_conf)
        self.assertFalse(ctx_nao_conf["nav_autenticado"])

        # 4. Conta anonimizada -> 0 queries
        anon = self._criar_usuario(email="", cpf="", anonimizado=True)
        req_anonim = rf.get("/pontos-coleta/")
        req_anonim.user = anon
        req_anonim.session = {}
        with self.assertNumQueries(0):
            ctx_anonim = navegacao_global(req_anonim)
        self.assertFalse(ctx_anonim["nav_autenticado"])

        # 5. Conta administrativa pendente de 2FA -> 0 queries
        admin_pend = self._criar_usuario(
            email="admpend@exemplo.com",
            cpf="12345678909",
            funcoes=("gestao_usuarios",),
            ativar_totp=True,
        )
        req_pend_2fa = rf.get("/contas/2fa/verificar/")
        req_pend_2fa.user = admin_pend
        req_pend_2fa.session = {SESSAO_CHAVE_2FA_VERIFICADO: False}
        with self.assertNumQueries(0):
            ctx_pend = navegacao_global(req_pend_2fa)
        self.assertTrue(ctx_pend["nav_autenticado"])
        self.assertTrue(ctx_pend["nav_pendente_2fa"])
        self.assertEqual(ctx_pend["notificacoes_nao_lidas"], 0)
        self.assertEqual(ctx_pend["nav_admin_itens"], ())

    def test_barra_visitante_identica_entre_rotas_e_estado_ativo(self):
        rotas_esperadas = [
            (reverse("pontos_coleta:lista_publica"), "Pontos de coleta"),
            (reverse("contas:login"), "Entrar"),
            (reverse("contas:cadastro"), "Criar conta"),
        ]
        ordem_esperada = ["Pontos de coleta", "Entrar", "Criar conta"]

        for url, ativo_esperado in rotas_esperadas:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                nav = _extrair_navbar(resp)
                self.assertEqual(nav.brand_href, reverse("pontos_coleta:lista_publica"))
                self.assertEqual([item["texto"] for item in nav.links], ordem_esperada)
                ativos = [item["texto"] for item in nav.links if item["aria_current"] == "page"]
                self.assertEqual(ativos, [ativo_esperado])
                self.assertNotIn("Administração", [b["texto"] for b in nav.botoes])

    def test_barra_cidadao_identica_entre_rotas_sem_administracao_e_com_badge(self):
        cidadao = self._criar_usuario(email="cid@exemplo.com", cpf="52998224725")
        NotificacaoService.registrar_evento(
            destinatario=cidadao,
            tipo=TipoNotificacao.NOVA_MENSAGEM,
            enviar_email=False,
        )
        self._logar(cidadao)

        rotas_esperadas = [
            (reverse("pontos_coleta:lista_publica"), reverse("pontos_coleta:lista_publica")),
            (reverse("pontos_coleta:cadastrar"), reverse("pontos_coleta:meus_pontos")),
            (reverse("notificacoes:lista"), reverse("notificacoes:lista")),
            (reverse("contas:perfil_editar"), reverse("contas:perfil_editar")),
        ]
        hrefs_esperados = [
            reverse("pontos_coleta:lista_publica"),
            reverse("pontos_coleta:meus_pontos"),
            reverse("notificacoes:lista"),
            reverse("contas:perfil_editar"),
        ]
        textos_esperados = [
            "Pontos de coleta",
            "Meus pontos",
            "Notificações 1 não lidas",
            "Meu perfil",
        ]

        for url, href_ativo_esperado in rotas_esperadas:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                nav = _extrair_navbar(resp)
                self.assertEqual(nav.brand_href, reverse("contas:perfil_editar"))
                self.assertEqual([item["href"] for item in nav.links], hrefs_esperados)
                self.assertEqual([item["texto"] for item in nav.links], textos_esperados)
                ativos = [item["href"] for item in nav.links if item["aria_current"] == "page"]
                self.assertEqual(ativos, [href_ativo_esperado])
                self.assertNotIn("Administração", [b["texto"] for b in nav.botoes])
                self.assertIn("Sair", [b["texto"] for b in nav.botoes])

    def test_barra_admin_com_2fa_identica_em_todas_as_rotas_e_dropdown_filtrado(self):
        admin_completo = self._criar_usuario(
            email="adm-full@exemplo.com",
            cpf="52998224725",
            funcoes=("gestao_usuarios", "aprovacao_pontos_coleta"),
            ativar_totp=True,
        )
        self._logar(admin_completo, verificado_2fa=True)

        rotas_esperadas = [
            (reverse("pontos_coleta:lista_publica"), reverse("pontos_coleta:lista_publica"), False),
            (reverse("pontos_coleta:cadastrar"), reverse("pontos_coleta:meus_pontos"), False),
            (reverse("notificacoes:lista"), reverse("notificacoes:lista"), False),
            (reverse("contas:perfil_editar"), reverse("contas:perfil_editar"), False),
            (reverse("contas:admin_usuario_lista"), reverse("contas:admin_usuario_lista"), True),
            (reverse("pontos_coleta:admin_lista"), reverse("pontos_coleta:admin_lista"), True),
            (
                reverse("pontos_coleta:admin_documentos"),
                reverse("pontos_coleta:admin_documentos"),
                True,
            ),
        ]
        ordem_esperada = [
            "Pontos de coleta",
            "Meus pontos",
            "Notificações",
            "Gestão de usuários",
            "Aprovação de pontos",
            "Documentos de pontos",
            "Meu perfil",
        ]

        for url, href_ativo_esperado, dropdown_ativo in rotas_esperadas:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                nav = _extrair_navbar(resp)
                self.assertEqual([item["texto"] for item in nav.links], ordem_esperada)
                ativos = [item["href"] for item in nav.links if item["aria_current"] == "page"]
                self.assertEqual(ativos, [href_ativo_esperado])
                botoes_admin = [b for b in nav.botoes if b["texto"] == "Administração"]
                self.assertEqual(len(botoes_admin), 1)
                tem_classe_active = "active" in botoes_admin[0]["class"].split()
                self.assertEqual(tem_classe_active, dropdown_ativo)

        # Admin somente com gestao_usuarios vê apenas Gestão de usuários no dropdown
        admin_so_usuarios = self._criar_usuario(
            email="adm-u@exemplo.com",
            cpf="11144477735",
            funcoes=("gestao_usuarios",),
            ativar_totp=True,
        )
        self._logar(admin_so_usuarios, verificado_2fa=True)
        nav_u = _extrair_navbar(self.client.get(reverse("contas:perfil_editar")))
        textos_u = [item["texto"] for item in nav_u.links]
        self.assertIn("Gestão de usuários", textos_u)
        self.assertNotIn("Aprovação de pontos", textos_u)
        self.assertNotIn("Documentos de pontos", textos_u)

    def test_is_superuser_sem_funcao_e_admin_pendente_2fa_nao_veem_dropdown_administracao(self):
        # 1. is_superuser sem função explícita + 2FA -> sem dropdown Administração (ADR 0010)
        super_sem_funcao = self._criar_usuario(
            email="super@exemplo.com",
            cpf="52998224725",
            is_superuser=True,
        )
        self._logar(super_sem_funcao, verificado_2fa=True)
        resp_super = self.client.get(reverse("contas:perfil_editar"))
        self.assertEqual(resp_super.status_code, 200)
        nav_super = _extrair_navbar(resp_super)
        self.assertNotIn("Administração", [b["texto"] for b in nav_super.botoes])
        self.assertNotIn("Gestão de usuários", [i["texto"] for i in nav_super.links])
        self.assertNotIn("Aprovação de pontos", [i["texto"] for i in nav_super.links])

        # 2. Admin com função explícita, porém pendente de 2FA -> barra mínima (só logo + Sair)
        admin_sem_2fa = self._criar_usuario(
            email="adm-sem-2fa@exemplo.com",
            cpf="11144477735",
            funcoes=("gestao_usuarios", "aprovacao_pontos_coleta"),
            ativar_totp=True,
        )
        self._logar(admin_sem_2fa, verificado_2fa=False)
        resp_2fa = self.client.get(reverse("contas:totp_verificar"))
        self.assertEqual(resp_2fa.status_code, 200)
        nav_2fa = _extrair_navbar(resp_2fa)
        self.assertIsNone(nav_2fa.brand_href)
        self.assertEqual(nav_2fa.links, [])
        self.assertEqual([b["texto"] for b in nav_2fa.botoes], ["Sair"])
