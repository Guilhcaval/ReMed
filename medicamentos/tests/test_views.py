"""Testes de integração HTTP, matriz de permissões, privacidade e XSS (Specs 08–11 e 14)."""

import io
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pyotp
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from auditoria.models import RegistroAuditoria
from contas.models import DispositivoTotp, EnderecoUsuario, Usuario
from medicamentos.models import (
    CondicaoConservacao,
    Doacao,
    FotoDoacao,
    ParametroVencimento,
    ResultadoConferenciaDoacao,
    StatusDoacao,
)
from medicamentos.views import SESSAO_CHAVE_BUSCA_LOCALIZACAO
from nucleo.mixins import SESSAO_CHAVE_2FA_VERIFICADO
from nucleo.models import FormaFarmaceutica, TipoEstabelecimento
from nucleo.services import DadosLocalizacaoCep
from pontos_coleta.models import PontoColeta, StatusPontoColeta


def _png_bytes() -> bytes:
    img = Image.new("RGB", (32, 32), color=(23, 70, 107))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
)
class MedicamentosViewsTest(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta_privada = Path(self._tmp.name)
        self._override = override_settings(PRIVATE_STORAGE_ROOT=self.pasta_privada)
        self._override.enable()
        self.forma = FormaFarmaceutica.objects.first()

    def tearDown(self):
        self._override.disable()
        self._tmp.cleanup()

    def _criar_usuario(
        self,
        email: str,
        cpf: str,
        *,
        nome: str = "Maria Secreta da Silva",
        perfil_doador: bool = True,
        perfil_solicitante: bool = False,
        is_superuser: bool = False,
        funcoes: tuple[str, ...] = (),
        ativar_totp: bool = False,
    ) -> Usuario:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=nome,
            data_nascimento=date(1990, 5, 10),
            celular="11999887766",
            perfil_doador=perfil_doador,
            perfil_solicitante=perfil_solicitante,
            is_superuser=is_superuser,
            is_staff=is_superuser,
            email_confirmado_em=timezone.now(),
        )
        EnderecoUsuario.objects.create(
            usuario=usuario,
            cep="01001000",
            logradouro="Rua Particular Secreta 999",
            numero="999",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            latitude_aprox=Decimal("-23.55"),
            longitude_aprox=Decimal("-46.63"),
        )
        if funcoes:
            grupos = [Group.objects.get_or_create(name=f)[0] for f in funcoes]
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

    def test_fluxo_completo_doacao_conferencia_foto_busca_privacidade_e_xss(self):
        """CA-08-01, CA-10-01, CA-14-02 e proteção XSS."""
        doador = self._criar_usuario("maria-doadora@exemplo.com", "52998224725")
        tipo = TipoEstabelecimento.objects.first()
        ponto = PontoColeta.objects.create(
            cnpj="11222333000181",
            razao_social="Farmácia Privada Ponto LTDA",
            nome_fantasia="Farmácia Secreta Retirada",
            tipo_estabelecimento=tipo,
            email="farmacia@secreta.org",
            telefone="1133334444",
            possui_refrigeracao=True,
            cep="01001000",
            logradouro="Av Ponto Secreto",
            numero="77",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            latitude_aprox=Decimal("-23.55"),
            longitude_aprox=Decimal("-46.63"),
            status=StatusPontoColeta.ATIVO,
        )

        self._logar(doador)
        validade = (timezone.localdate() + timedelta(days=90)).isoformat()
        resp_criar = self.client.post(
            reverse("medicamentos:doacao_criar"),
            data={
                "nome_medicamento": "<script>alert(1)</script>Losartana",
                "principio_ativo": "Losartana potássica",
                "concentracao_dosagem": "50 mg",
                "forma_farmaceutica": str(self.forma.pk),
                "quantidade": "30",
                "fabricante": "EMS",
                "lote": "L2026Z",
                "data_validade": validade,
                "embalagem_integra": "sim",
                "controle_especial": "nao",
                "condicao_conservacao": CondicaoConservacao.REFRIGERADO,
                "faixa_temperatura_bula": "2 °C a 8 °C",
                "declaracao_doador_conservacao": "on",
                "sujeito_receita": "sim",
                "ponto_coleta": str(ponto.pk),
                "observacoes": "<b>obs</b>",
                "foto_1": SimpleUploadedFile("f1.png", _png_bytes(), content_type="image/png"),
            },
            follow=True,
        )
        self.assertEqual(resp_criar.status_code, 200)
        self.assertContains(resp_criar, "O ReMed não substitui avaliação médica ou farmacêutica")
        self.assertNotContains(resp_criar, "<script>alert(1)</script>")

        doacao = Doacao.objects.get()
        foto = FotoDoacao.objects.get(doacao=doacao, ordem=1)

        # Ainda em análise -> não aparece na busca pública
        resp_busca_antes = self.client.get(reverse("medicamentos:busca"))
        self.assertContains(resp_busca_antes, "Nenhum medicamento encontrado")

        # Conferente (+ 2FA) acessa foto (60 s + auditoria) e aprova
        conferente = self._criar_usuario(
            "conf@exemplo.com",
            "11144477735",
            funcoes=("conferencia_doacoes",),
            ativar_totp=True,
        )
        self._logar(conferente, verificado_2fa=True)

        resp_foto = self.client.get(
            reverse("medicamentos:doacao_foto_acessar", kwargs={"foto_id": foto.pk})
        )
        self.assertEqual(resp_foto.status_code, 302)
        self.assertIn("/arquivos/privados/", resp_foto["Location"])
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="arquivo.acessado", entidade_id=str(foto.pk), ator=conferente
            ).exists()
        )

        resp_conf = self.client.post(
            reverse("medicamentos:admin_conferencia_registrar", kwargs={"doacao_id": doacao.pk}),
            data={"resultado": ResultadoConferenciaDoacao.APROVADA, "motivo": ""},
            follow=True,
        )
        self.assertEqual(resp_conf.status_code, 200)
        self.assertContains(resp_conf, "Conferência registrada com sucesso")

        # Visitante busca -> vê resumo escapado e NENHUM dado do doador, ponto ou coordenadas
        self.client.logout()
        resp_busca = self.client.get(reverse("medicamentos:busca"))
        self.assertEqual(resp_busca.status_code, 200)
        self.assertContains(resp_busca, "&lt;script&gt;alert(1)&lt;/script&gt;Losartana")
        self.assertContains(resp_busca, "Refrigerado")
        self.assertContains(resp_busca, "Exige receita")
        self.assertContains(
            resp_busca, f"{reverse('contas:login')}?next={reverse('medicamentos:busca')}"
        )
        for dado_privado in (
            "Maria Secreta da Silva",
            "maria-doadora@exemplo.com",
            "11999887766",
            "Rua Particular Secreta",
            "Farmácia Secreta Retirada",
            "Av Ponto Secreto",
            "-23.55",
            "-46.63",
        ):
            self.assertNotContains(resp_busca, dado_privado)

    def test_sessao_localizacao_cep_gps_e_limpeza(self):
        """CA-14-05."""
        fake_loc = DadosLocalizacaoCep(
            cep="01001000",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            latitude_aprox=Decimal("-23.55"),
            longitude_aprox=Decimal("-46.63"),
            fonte="brasilapi",
            do_cache=True,
        )
        with patch(
            "medicamentos.views.GeolocalizacaoService.obter_coordenadas_por_cep",
            return_value=fake_loc,
        ):
            r_cep = self.client.post(
                reverse("medicamentos:definir_localizacao"),
                data={"cep": "01001-000"},
            )
        self.assertRedirects(r_cep, reverse("medicamentos:busca"))
        self.assertIn(SESSAO_CHAVE_BUSCA_LOCALIZACAO, self.client.session)

        r_limpar = self.client.post(reverse("medicamentos:limpar_localizacao"))
        self.assertRedirects(r_limpar, reverse("medicamentos:busca"))
        self.assertNotIn(SESSAO_CHAVE_BUSCA_LOCALIZACAO, self.client.session)

    def test_matriz_permissoes_e_isolamento_de_perfis(self):
        """CA-08-05, CA-10-04 e CA-11-05."""
        doador = self._criar_usuario("d@exemplo.com", "52998224725", perfil_doador=True)
        so_solicitante = self._criar_usuario(
            "s@exemplo.com", "11144477735", perfil_doador=False, perfil_solicitante=True
        )
        outro_doador = self._criar_usuario("d2@exemplo.com", "12345678909", perfil_doador=True)
        super_sem = self._criar_usuario("sup@exemplo.com", "71428793860", is_superuser=True)
        adm_usuarios = self._criar_usuario(
            "au@exemplo.com", "39053344705", funcoes=("gestao_usuarios",), ativar_totp=True
        )
        adm_conf_sem_2fa = self._criar_usuario(
            "ac@exemplo.com", "16899535009", funcoes=("conferencia_doacoes",), ativar_totp=True
        )
        adm_param = self._criar_usuario(
            "ap@exemplo.com", "98765432100", funcoes=("metricas_e_parametros",), ativar_totp=True
        )

        doacao = Doacao.objects.create(
            doador=doador,
            nome_medicamento="Dipirona",
            principio_ativo="Dipirona",
            concentracao_dosagem="500 mg",
            forma_farmaceutica=self.forma,
            quantidade_inicial=10,
            quantidade_disponivel=10,
            fabricante="EMS",
            lote="LM1",
            data_validade=timezone.localdate() + timedelta(days=90),
            embalagem_integra=True,
            condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE,
            status=StatusDoacao.EM_ANALISE,
        )
        foto = FotoDoacao.objects.create(
            doacao=doacao,
            ordem=1,
            arquivo_chave="doacoes/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png",
            mime_verificado="image/png",
            tamanho_bytes=123,
        )

        # Sem perfil Doador -> 403 em /doacoes/nova/
        self._logar(so_solicitante)
        self.assertEqual(self.client.get(reverse("medicamentos:doacao_criar")).status_code, 403)

        # Outro Doador -> 404 na edição, cancelamento e foto da doação alheia
        self._logar(outro_doador)
        self.assertEqual(
            self.client.get(
                reverse("medicamentos:doacao_editar", kwargs={"doacao_id": doacao.pk})
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("medicamentos:doacao_cancelar", kwargs={"doacao_id": doacao.pk})
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("medicamentos:doacao_foto_acessar", kwargs={"foto_id": foto.pk})
            ).status_code,
            404,
        )

        # is_superuser sem função explícita -> 403 nas rotas admin
        self._logar(super_sem, verificado_2fa=True)
        self.assertEqual(
            self.client.get(reverse("medicamentos:admin_conferencia_lista")).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("medicamentos:admin_vencimento_parametros")).status_code, 403
        )

        # Admin com função incorreta -> 403
        self._logar(adm_usuarios, verificado_2fa=True)
        self.assertEqual(
            self.client.get(reverse("medicamentos:admin_conferencia_lista")).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("medicamentos:admin_vencimento_parametros")).status_code, 403
        )

        # Admin com conferencia_doacoes sem 2FA -> 302 para verificar 2FA
        self._logar(adm_conf_sem_2fa, verificado_2fa=False)
        r_2fa = self.client.get(reverse("medicamentos:admin_conferencia_lista"))
        self.assertEqual(r_2fa.status_code, 302)
        self.assertIn(reverse("contas:totp_verificar"), r_2fa["Location"])

        # Admin com metricas_e_parametros + 2FA -> atualiza parâmetros com sucesso
        self._logar(adm_param, verificado_2fa=True)
        r_param = self.client.post(
            reverse("medicamentos:admin_vencimento_parametros"),
            data={"validade_minima_restante_dias": "45", "antecedencia_aviso_dias": "20"},
            follow=True,
        )
        self.assertEqual(r_param.status_code, 200)
        self.assertContains(r_param, "Parâmetros de vencimento atualizados com sucesso")
        self.assertEqual(ParametroVencimento.objects.get(pk=1).validade_minima_restante_dias, 45)
