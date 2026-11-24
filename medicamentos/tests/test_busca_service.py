"""Testes unitários de BuscaMedicamentoService (Spec 14 / RF015 / RS002 / RS010)."""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from contas.models import StatusUsuario, Usuario
from medicamentos.models import CondicaoConservacao, Doacao, StatusDoacao
from medicamentos.services import (
    BuscaMedicamentoService,
    FiltrosBuscaMedicamento,
    LocalizacaoBuscaSessao,
)
from nucleo.models import FormaFarmaceutica


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BuscaMedicamentoServiceTest(TestCase):
    def setUp(self):
        self.hoje = date(2026, 11, 24)
        self.forma_comp = FormaFarmaceutica.objects.get(nome="Comprimido")
        self.forma_inj = FormaFarmaceutica.objects.get(nome="Injetável")
        self.doador_ativo = self._criar_usuario("ativo@exemplo.com", "52998224725")
        self.doador_suspenso = self._criar_usuario(
            "suspenso@exemplo.com", "11144477735", status=StatusUsuario.SUSPENSO
        )

    def _criar_usuario(self, email: str, cpf: str, *, status: str = StatusUsuario.ATIVO) -> Usuario:
        return Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=f"Nome Privado {email}",
            data_nascimento=date(1990, 5, 10),
            celular="11988887777",
            perfil_doador=True,
            status=status,
            is_active=status == StatusUsuario.ATIVO,
            email_confirmado_em=timezone.now(),
        )

    def _criar_doacao(
        self,
        *,
        doador: Usuario | None = None,
        nome: str = "Dipirona",
        principio: str = "Dipirona sódica",
        concentracao: str = "500 mg",
        forma=None,
        status: str = StatusDoacao.DISPONIVEL,
        conservacao: str = CondicaoConservacao.TEMPERATURA_AMBIENTE,
        dias_validade: int = 90,
        bairro: str = "Sé",
        lat: Decimal | None = Decimal("-23.55"),
        lon: Decimal | None = Decimal("-46.63"),
    ) -> Doacao:
        return Doacao.objects.create(
            doador=doador or self.doador_ativo,
            nome_medicamento=nome,
            principio_ativo=principio,
            concentracao_dosagem=concentracao,
            forma_farmaceutica=forma or self.forma_comp,
            quantidade_inicial=10,
            quantidade_disponivel=10,
            fabricante="EMS",
            lote="LB1",
            data_validade=self.hoje + timedelta(days=dias_validade),
            embalagem_integra=True,
            condicao_conservacao=conservacao,
            status=status,
            regiao_bairro=bairro,
            regiao_municipio="São Paulo",
            regiao_uf="SP",
            latitude_aprox=lat,
            longitude_aprox=lon,
        )

    def test_ordenacao_por_proximidade_e_filtro_distancia_maxima(self):
        """CA-14-01."""
        d_perto = self._criar_doacao(nome="Perto", lat=Decimal("-23.55"), lon=Decimal("-46.63"))
        d_medio = self._criar_doacao(nome="Medio", lat=Decimal("-23.58"), lon=Decimal("-46.66"))
        self._criar_doacao(nome="Longe", lat=Decimal("-22.90"), lon=Decimal("-43.17"))

        loc = LocalizacaoBuscaSessao(
            origem="cep",
            rotulo_aproximado="Sé · São Paulo/SP",
            latitude_aprox=Decimal("-23.55"),
            longitude_aprox=Decimal("-46.63"),
            cep="01001000",
        )
        res = BuscaMedicamentoService.buscar(
            FiltrosBuscaMedicamento(distancia_max_km=10),
            localizacao=loc,
            referencia=self.hoje,
        )
        self.assertTrue(res.ordenado_por_proximidade)
        self.assertEqual([item.id for item in res.pagina.object_list], [d_perto.pk, d_medio.pk])
        self.assertEqual(res.pagina.object_list[0].faixa_distancia, "menos de 1 km")

    def test_visibilidade_estrita_e_filtros_combinados(self):
        """CA-14-03."""
        visivel = self._criar_doacao(
            nome="Insulina NPH",
            principio="Insulina humana",
            concentracao="100 UI/mL",
            forma=self.forma_inj,
            conservacao=CondicaoConservacao.REFRIGERADO,
            dias_validade=120,
        )
        # Não devem aparecer:
        self._criar_doacao(nome="Insulina Em Analise", status=StatusDoacao.EM_ANALISE)
        self._criar_doacao(nome="Insulina Reservada", status=StatusDoacao.RESERVADO)
        self._criar_doacao(nome="Insulina Curta", dias_validade=10)
        self._criar_doacao(nome="Insulina Suspenso", doador=self.doador_suspenso)

        res = BuscaMedicamentoService.buscar(
            FiltrosBuscaMedicamento(
                termo="insulina",
                forma_farmaceutica_id=self.forma_inj.pk,
                concentracao="100",
                validade_minima=self.hoje + timedelta(days=90),
                condicao_conservacao=CondicaoConservacao.REFRIGERADO,
            ),
            referencia=self.hoje,
        )
        self.assertEqual([item.id for item in res.pagina.object_list], [visivel.pk])

    def test_paginacao_fixa_de_10_itens_por_pagina(self):
        """CA-14-04 (parte paginação)."""
        for i in range(15):
            self._criar_doacao(nome=f"Medicamento {i:02d}")

        p1 = BuscaMedicamentoService.buscar(pagina=1, referencia=self.hoje)
        p2 = BuscaMedicamentoService.buscar(pagina=2, referencia=self.hoje)
        self.assertEqual(p1.total_encontrados, 15)
        self.assertEqual(len(p1.pagina.object_list), 10)
        self.assertEqual(len(p2.pagina.object_list), 5)
