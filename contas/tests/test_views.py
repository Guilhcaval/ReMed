"""Testes de integração das views e rotas do app contas (Spec 01 / RF001)."""

import logging
import re
from datetime import date

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from contas.models import StatusUsuario, Usuario
from contas.services import DadosCadastroUsuario, DadosEndereco, UsuarioService
from notificacoes.models import OutboxEmail


def _post_cadastro(**sobrescritas) -> dict:
    base = {
        "nome_completo": "João Pedro Santos",
        "cpf": "529.982.247-25",
        "data_nascimento": "10/03/1992",
        "email": "joao@exemplo.com",
        "celular": "(11) 98765-4321",
        "senha": "Rm3d!9xQ",
        "perfil_doador": "on",
        "cep": "01001-000",
        "logradouro": "Praça da Sé",
        "numero": "50",
        "bairro": "Sé",
        "municipio": "São Paulo",
        "estado": "SP",
        "complemento": "Bloco B",
        "aceite_termos": "on",
    }
    base.update(sobrescritas)
    return base


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ContasViewsTest(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _criar_usuario_confirmado(
        self,
        *,
        email: str = "ativo@exemplo.com",
        cpf: str = "11144477735",
        nome: str = "Usuária Ativa",
        complemento: str = "Sala 1",
    ) -> Usuario:
        tokens: list[str] = []
        usuario = UsuarioService.cadastrar(
            DadosCadastroUsuario(
                nome_completo=nome,
                cpf=cpf,
                data_nascimento=date(1988, 7, 20),
                email=email,
                celular="11988887777",
                senha="Rm3d!9xQ",
                perfil_doador=True,
                perfil_solicitante=False,
                perfil_cuidador=False,
                aceite_termos=True,
                endereco=DadosEndereco(
                    cep="01001000",
                    logradouro="Praça da Sé",
                    numero="10",
                    bairro="Sé",
                    municipio="São Paulo",
                    estado="SP",
                    complemento=complemento,
                ),
            ),
            construir_url_confirmacao=lambda t: tokens.append(t) or f"http://testserver/c/{t}/",
        )
        UsuarioService.confirmar_email(tokens[0])
        usuario.refresh_from_db()
        return usuario

    def test_get_cadastro_renderiza_elementos_essenciais_e_modais_rascunho(self):
        resposta = self.client.get(reverse("contas:cadastro"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Criar conta · ReMed")
        self.assertContains(resposta, "Cadastro de pessoa física")
        self.assertNotContains(resposta, 'role="tablist"')
        self.assertNotContains(resposta, "Pessoa Jurídica")
        self.assertNotContains(resposta, "Pessoa Física · Doador / Solicitante")
        self.assertContains(
            resposta,
            "Representa um Ponto de Coleta (farmácia, UBS ou ONG)?",
        )
        self.assertContains(resposta, "Entrar para cadastrar ponto")
        self.assertContains(
            resposta,
            f"{reverse('contas:login')}?next={reverse('pontos_coleta:cadastrar')}",
        )
        self.assertContains(resposta, "Não sei meu CEP")
        self.assertContains(resposta, 'rel="noopener noreferrer"')
        self.assertContains(resposta, "csrfmiddlewaretoken")
        self.assertContains(resposta, "1.0-rascunho")
        self.assertContains(resposta, "Questão 8 do PRD")

    def test_post_cadastro_valido_faz_prg_e_ignora_mass_assignment(self):
        """CA-01-01 e CA-01-12."""
        payload = _post_cadastro(
            status=StatusUsuario.SUSPENSO,
            is_superuser="true",
            is_staff="true",
        )
        resposta = self.client.post(reverse("contas:cadastro"), data=payload, follow=True)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Cadastro realizado com sucesso")

        usuario = Usuario.objects.get(email="joao@exemplo.com")
        self.assertEqual(usuario.status, StatusUsuario.ATIVO)
        self.assertFalse(usuario.is_superuser)
        self.assertFalse(usuario.is_staff)
        self.assertEqual(OutboxEmail.objects.filter(destinatario=usuario).count(), 1)

    def test_post_cadastro_invalido_preserva_campos_e_nao_reexibe_senha(self):
        payload = _post_cadastro(cpf="111.111.111-11", nome_completo="Maria Preservada")
        resposta = self.client.post(reverse("contas:cadastro"), data=payload)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Campo preenchido incorretamente")
        self.assertContains(resposta, "Maria Preservada")
        self.assertNotContains(resposta, "Rm3d!9xQ")

    def test_post_cadastro_campos_vazios_exibe_mensagem_literal(self):
        resposta = self.client.post(reverse("contas:cadastro"), data={})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Campo(s) obrigatório(s) não preenchido(s)")

    def test_post_cadastro_cpf_e_email_duplicados(self):
        self._criar_usuario_confirmado(email="joao@exemplo.com", cpf="52998224725")

        r_cpf = self.client.post(
            reverse("contas:cadastro"),
            data=_post_cadastro(email="outro@exemplo.com"),
        )
        self.assertContains(r_cpf, "CPF já cadastrado")

        r_email = self.client.post(
            reverse("contas:cadastro"),
            data=_post_cadastro(cpf="111.444.777-35", email="JOAO@EXEMPLO.COM"),
        )
        self.assertContains(r_email, "E-mail já cadastrado")

    @override_settings(REMED_CADASTRO_LIMITE_IP_HORA=2)
    def test_cadastro_aplica_rate_limit_por_ip(self):
        url = reverse("contas:cadastro")
        self.assertEqual(self.client.post(url, data={}).status_code, 200)
        self.assertEqual(self.client.post(url, data={}).status_code, 200)
        terceira = self.client.post(url, data={})
        self.assertEqual(terceira.status_code, 429)

    def test_confirmar_email_view_sucesso_e_reuso(self):
        tokens: list[str] = []
        UsuarioService.cadastrar(
            DadosCadastroUsuario(
                nome_completo="Pedro Confirmacao",
                cpf="52998224725",
                data_nascimento=date(1991, 4, 12),
                email="pedro@exemplo.com",
                celular="11977776666",
                senha="Rm3d!9xQ",
                perfil_doador=True,
                perfil_solicitante=False,
                perfil_cuidador=False,
                aceite_termos=True,
                endereco=DadosEndereco(
                    cep="01001000",
                    logradouro="Praça da Sé",
                    numero="1",
                    bairro="Sé",
                    municipio="São Paulo",
                    estado="SP",
                ),
            ),
            construir_url_confirmacao=lambda t: tokens.append(t) or f"http://testserver/c/{t}/",
        )
        url = reverse("contas:confirmar_email", kwargs={"token": tokens[0]})
        registros_log: list[str] = []

        class _CapturadorLog(logging.Handler):
            def emit(self, record):
                registros_log.append(self.format(record))

        handler = _CapturadorLog()
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        try:
            primeira = self.client.get(url)
            segunda = self.client.get(url)
        finally:
            root_logger.removeHandler(handler)

        self.assertEqual(primeira.status_code, 200)
        self.assertContains(primeira, "E-mail confirmado com sucesso")
        self.assertEqual(segunda.status_code, 200)
        self.assertContains(segunda, "Não foi possível confirmar o e-mail")
        for linha_log in registros_log:
            self.assertNotIn(tokens[0], linha_log)

    def test_reenviar_confirmacao_resposta_identica_e_limite_5_por_hora(self):
        """CA-01-18: resposta igual para e-mail existente ou inexistente e 6ª tentativa -> 429."""
        UsuarioService.cadastrar(
            DadosCadastroUsuario(
                nome_completo="Lucas Pendente",
                cpf="52998224725",
                data_nascimento=date(1991, 4, 12),
                email="pendente@exemplo.com",
                celular="11977776666",
                senha="Rm3d!9xQ",
                perfil_doador=True,
                perfil_solicitante=False,
                perfil_cuidador=False,
                aceite_termos=True,
                endereco=DadosEndereco(
                    cep="01001000",
                    logradouro="Praça da Sé",
                    numero="1",
                    bairro="Sé",
                    municipio="São Paulo",
                    estado="SP",
                ),
            ),
            construir_url_confirmacao=lambda t: f"http://testserver/c/{t}/",
        )
        url = reverse("contas:reenviar_confirmacao")

        r_existente = self.client.post(
            url,
            data={"email": "pendente@exemplo.com"},
            follow=True,
            REMOTE_ADDR="10.0.0.1",
        )
        r_inexistente = self.client.post(
            url,
            data={"email": "desconhecido@exemplo.com"},
            follow=True,
            REMOTE_ADDR="10.0.0.2",
        )
        self.assertEqual(r_existente.status_code, 200)
        self.assertEqual(r_inexistente.status_code, 200)

        def _normalizar_csrf(html: bytes) -> str:
            return re.sub(
                r'name="csrfmiddlewaretoken" value="[^"]+"',
                'name="csrfmiddlewaretoken" value="CSRF"',
                html.decode("utf-8"),
            )

        self.assertEqual(
            _normalizar_csrf(r_existente.content),
            _normalizar_csrf(r_inexistente.content),
        )

        # Limite por IP (5/hora -> 6ª retorna 429)
        cache.clear()
        for indice in range(settings.REMED_CONFIRMACAO_EMAIL_REENVIO_LIMITE_HORA):
            r = self.client.post(
                url,
                data={"email": f"user{indice}@exemplo.com"},
                REMOTE_ADDR="10.0.0.9",
            )
            self.assertEqual(r.status_code, 302)
        sexta_ip = self.client.post(
            url,
            data={"email": "outro@exemplo.com"},
            REMOTE_ADDR="10.0.0.9",
        )
        self.assertEqual(sexta_ip.status_code, 429)

        # Limite por e-mail mesmo variando IP (5/hora -> 6ª retorna 429)
        cache.clear()
        for indice in range(settings.REMED_CONFIRMACAO_EMAIL_REENVIO_LIMITE_HORA):
            r = self.client.post(
                url,
                data={"email": "pendente@exemplo.com"},
                REMOTE_ADDR=f"10.0.1.{indice}",
            )
            self.assertEqual(r.status_code, 302)
        sexta_email = self.client.post(
            url,
            data={"email": "PENDENTE@EXEMPLO.COM"},
            REMOTE_ADDR="10.0.1.99",
        )
        self.assertEqual(sexta_email.status_code, 429)

    def test_perfil_visitante_redirecionado_e_xss_escapado(self):
        """CA-01-17 e controle de acesso a contas:perfil_editar."""
        url_perfil = reverse("contas:perfil_editar")
        r_visitante = self.client.get(url_perfil)
        self.assertEqual(r_visitante.status_code, 302)
        self.assertTrue(r_visitante["Location"].startswith(settings.LOGIN_URL))

        payload_xss = "<script>alert(1)</script>"
        usuario = self._criar_usuario_confirmado(
            nome=payload_xss,
            complemento=payload_xss,
        )
        self.client.force_login(usuario)

        # Autenticado visitando cadastro é redirecionado para o perfil
        r_cad = self.client.get(reverse("contas:cadastro"))
        self.assertRedirects(r_cad, url_perfil)

        r_perfil = self.client.get(url_perfil)
        self.assertEqual(r_perfil.status_code, 200)
        self.assertNotContains(r_perfil, "<script>alert(1)</script>")
        self.assertContains(r_perfil, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_perfil_edicao_ignora_cpf_adulterado_no_post(self):
        """CA-01-11."""
        usuario = self._criar_usuario_confirmado(cpf="11144477735")
        self.client.force_login(usuario)

        resposta = self.client.post(
            reverse("contas:perfil_editar"),
            data={
                "nome_completo": "Nome Novo",
                "cpf": "529.982.247-25",
                "data_nascimento": "20/07/1988",
                "email": "ativo@exemplo.com",
                "celular": "(11) 91234-5678",
                "perfil_doador": "on",
                "perfil_solicitante": "on",
                "cep": "01001-000",
                "logradouro": "Praça da Sé",
                "numero": "99",
                "bairro": "Sé",
                "municipio": "São Paulo",
                "estado": "SP",
                "complemento": "Conjunto 3",
            },
            follow=True,
        )
        self.assertEqual(resposta.status_code, 200)
        usuario.refresh_from_db()
        self.assertEqual(usuario.nome_completo, "Nome Novo")
        self.assertEqual(usuario.cpf, "11144477735")
        self.assertEqual(usuario.celular, "11912345678")

    def test_encerrar_conta_view_faz_logout_e_bloqueia_visitante(self):
        url_encerrar = reverse("contas:encerrar_conta")
        r_visitante = self.client.get(url_encerrar)
        self.assertEqual(r_visitante.status_code, 302)
        self.assertTrue(r_visitante["Location"].startswith(settings.LOGIN_URL))

        usuario = self._criar_usuario_confirmado()
        self.client.force_login(usuario)

        r_senha_errada = self.client.post(
            url_encerrar,
            data={"senha_atual": "Errada!123", "confirmar_encerramento": "on"},
        )
        self.assertEqual(r_senha_errada.status_code, 200)
        self.assertContains(r_senha_errada, "Senha atual incorreta.")

        r_ok = self.client.post(
            url_encerrar,
            data={"senha_atual": "Rm3d!9xQ", "confirmar_encerramento": "on"},
            follow=True,
        )
        self.assertEqual(r_ok.status_code, 200)
        usuario.refresh_from_db()
        self.assertIsNotNone(usuario.anonimizado_em)
        self.assertNotIn("_auth_user_id", self.client.session)
