"""Testes da Página Inicial pública na rota raiz `/` (HomeView e HomeService)."""

from datetime import date, timedelta

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from contas.models import StatusUsuario, Usuario
from medicamentos.models import CondicaoConservacao, Doacao, StatusDoacao
from nucleo.context_processors import navegacao_global
from nucleo.models import FormaFarmaceutica, TipoEstabelecimento
from nucleo.services import HomeService
from pontos_coleta.models import PontoColeta, StatusPontoColeta


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
)
class HomeViewEServiceTest(TestCase):
    def _criar_usuario(
        self,
        *,
        email: str,
        cpf: str,
        perfil_doador: bool = True,
        perfil_solicitante: bool = False,
    ) -> Usuario:
        return Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo="Maria Confidencial Silva",
            data_nascimento=date(1990, 5, 10),
            celular="11988887777",
            perfil_doador=perfil_doador,
            perfil_solicitante=perfil_solicitante,
            status=StatusUsuario.ATIVO,
            is_active=True,
            email_confirmado_em=timezone.now(),
        )

    def _criar_ponto(self, *, cnpj: str, status: str) -> PontoColeta:
        tipo = TipoEstabelecimento.objects.first()
        return PontoColeta.objects.create(
            cnpj=cnpj,
            razao_social=f"Instituição {cnpj} LTDA",
            nome_fantasia=f"Farmácia {cnpj}",
            tipo_estabelecimento=tipo,
            email=f"contato-{cnpj}@exemplo.org",
            telefone="1133334444",
            possui_refrigeracao=True,
            cep="01001000",
            logradouro="Praça da Sé",
            numero="100",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            status=status,
        )

    def _criar_doacao(
        self,
        *,
        doador: Usuario,
        status: str,
        validade_delta_dias: int = 90,
        qtd_disp: int = 10,
    ) -> Doacao:
        forma = FormaFarmaceutica.objects.first()
        return Doacao.objects.create(
            doador=doador,
            nome_medicamento="Losartana Potássica",
            principio_ativo="Losartana",
            concentracao_dosagem="50 mg",
            forma_farmaceutica=forma,
            quantidade_inicial=10,
            quantidade_disponivel=qtd_disp,
            fabricante="EMS",
            lote="L2026A",
            data_validade=timezone.localdate() + timedelta(days=validade_delta_dias),
            embalagem_integra=True,
            condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE,
            sujeito_receita=False,
            status=status,
        )

    def test_home_service_conta_apenas_doacoes_disponiveis_validas_e_pontos_ativos(self):
        doador = self._criar_usuario(email="doador@exemplo.com", cpf="52998224725")
        self._criar_doacao(doador=doador, status=StatusDoacao.DISPONIVEL, validade_delta_dias=60)
        self._criar_doacao(doador=doador, status=StatusDoacao.DISPONIVEL, validade_delta_dias=120)
        # Não devem entrar no contador público
        self._criar_doacao(doador=doador, status=StatusDoacao.EM_ANALISE, validade_delta_dias=60)
        self._criar_doacao(doador=doador, status=StatusDoacao.VENCIDO, validade_delta_dias=-5)
        self._criar_doacao(
            doador=doador, status=StatusDoacao.DISPONIVEL, validade_delta_dias=60, qtd_disp=0
        )

        self._criar_ponto(cnpj="11222333000181", status=StatusPontoColeta.ATIVO)
        self._criar_ponto(cnpj="11444777000161", status=StatusPontoColeta.PENDENTE_APROVACAO)
        self._criar_ponto(cnpj="27865757000102", status=StatusPontoColeta.SUSPENSO)

        resumo = HomeService.obter_resumo_publico()
        self.assertEqual(resumo.doacoes_disponiveis, 2)
        self.assertEqual(resumo.pontos_coleta_ativos, 1)

    def test_get_home_visitante_renderiza_busca_fluxo_rnf13_ctas_e_sem_pii(self):
        doador = self._criar_usuario(email="privado@exemplo.com", cpf="52998224725")
        self._criar_doacao(doador=doador, status=StatusDoacao.DISPONIVEL)
        self._criar_ponto(cnpj="11222333000181", status=StatusPontoColeta.ATIVO)

        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'action="{reverse("medicamentos:busca")}"')
        self.assertContains(resp, 'name="termo"')
        self.assertContains(resp, "O ReMed não substitui avaliação médica ou farmacêutica.")
        self.assertContains(resp, "Como funciona o ReMed")
        self.assertContains(resp, reverse("contas:cadastro"))
        self.assertContains(resp, reverse("contas:login"))
        self.assertContains(resp, reverse("pontos_coleta:cadastrar"))
        self.assertContains(resp, "Doações disponíveis")
        self.assertContains(resp, "Pontos de coleta ativos")
        # Nenhum dado pessoal do doador pode vazar na página inicial
        self.assertNotContains(resp, "Maria Confidencial Silva")
        self.assertNotContains(resp, "privado@exemplo.com")
        self.assertNotContains(resp, "52998224725")

    def test_get_home_autenticado_adapta_ctas_por_perfil(self):
        doador = self._criar_usuario(
            email="doador@exemplo.com",
            cpf="52998224725",
            perfil_doador=True,
        )
        self.client.force_login(doador)
        resp_doador = self.client.get(reverse("nucleo:home"))
        self.assertEqual(resp_doador.status_code, 200)
        self.assertContains(resp_doador, reverse("medicamentos:doacao_criar"))
        self.assertContains(resp_doador, "Cadastrar doação")
        self.assertNotContains(resp_doador, "Criar conta gratuita")

        solicitante = self._criar_usuario(
            email="sol@exemplo.com",
            cpf="11144477735",
            perfil_doador=False,
            perfil_solicitante=True,
        )
        self.client.force_login(solicitante)
        resp_sol = self.client.get(reverse("nucleo:home"))
        self.assertEqual(resp_sol.status_code, 200)
        self.assertNotContains(resp_sol, reverse("medicamentos:doacao_criar"))
        self.assertContains(resp_sol, reverse("medicamentos:busca"))

    def test_navegacao_global_zero_queries_na_raiz_para_visitante(self):
        rf = RequestFactory()
        req = rf.get("/")
        req.user = AnonymousUser()
        req.session = {}
        with self.assertNumQueries(0):
            ctx = navegacao_global(req)
        self.assertFalse(ctx["nav_autenticado"])
        self.assertEqual(ctx["notificacoes_nao_lidas"], 0)
