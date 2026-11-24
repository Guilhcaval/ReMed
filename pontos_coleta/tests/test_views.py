"""Testes de integração HTTP e matriz de permissões do app pontos_coleta (Specs 05, 06 e 07)."""

import tempfile
from datetime import date, time
from pathlib import Path
from unittest.mock import patch

import pyotp
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from contas.models import DispositivoTotp, Usuario
from nucleo.mixins import SESSAO_CHAVE_2FA_VERIFICADO
from nucleo.models import TipoDocumentoPonto, TipoEstabelecimento
from pontos_coleta.models import (
    DocumentoPontoColeta,
    PontoColeta,
    ResultadoAnalisePonto,
    StatusPontoColeta,
)
from pontos_coleta.services import (
    DadosPontoColeta,
    DocumentoPontoService,
    ItemHorario,
    PontoColetaService,
)


def _pdf_valido() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
)
class PontosColetaViewsTest(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta_privada = Path(self._tmp.name)
        self._override = override_settings(PRIVATE_STORAGE_ROOT=self.pasta_privada)
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        self._tmp.cleanup()

    def _criar_usuario(
        self,
        email: str,
        cpf: str,
        *,
        funcoes: tuple[str, ...] = (),
        is_superuser: bool = False,
        ativar_totp: bool = False,
    ) -> Usuario:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=f"Usuário {email}",
            data_nascimento=date(1990, 5, 10),
            celular="11988887777",
            perfil_doador=True,
            is_superuser=is_superuser,
            is_staff=is_superuser,
            email_confirmado_em=timezone.now(),
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

    def _logar_com_2fa(self, usuario: Usuario, *, verificado: bool = True) -> None:
        self.client.force_login(usuario)
        sessao = self.client.session
        sessao[SESSAO_CHAVE_2FA_VERIFICADO] = verificado
        sessao.save()

    @patch("nucleo.services.CepService.obter_coordenadas_em_cache", return_value=(None, None))
    def test_fluxo_completo_cadastro_documentos_aprovacao_e_visibilidade_publica(self, _mock_geo):
        """CA-05-01, CA-05-03, CA-05-07, CA-06-01, CA-06-04 e CA-07-01."""
        # Visitante em cadastrar -> redireciona para login (CA-05-03)
        resp_visit = self.client.get(reverse("pontos_coleta:cadastrar"))
        self.assertEqual(resp_visit.status_code, 302)
        self.assertIn(reverse("contas:login"), resp_visit["Location"])

        resp_user = self._criar_usuario("resp@exemplo.com", "52998224725")
        self.client.force_login(resp_user)

        tipo_estab = TipoEstabelecimento.objects.first()
        post_data = {
            "cnpj": "11.222.333/0001-81",
            "razao_social": "Farmácia do Bem LTDA",
            "nome_fantasia": "Farmácia do Bem",
            "tipo_estabelecimento": str(tipo_estab.pk),
            "email": "contato@farmaciadobem.org",
            "telefone": "(11) 3333-4444",
            "cep": "01001-000",
            "logradouro": "Praça da Sé",
            "numero": "100",
            "bairro": "Sé",
            "municipio": "São Paulo",
            "estado": "SP",
            "complemento": "",
            "possui_refrigeracao": "sim",
            "observacoes": "Retirada no balcão 2",
            "horarios-TOTAL_FORMS": "1",
            "horarios-INITIAL_FORMS": "0",
            "horarios-MIN_NUM_FORMS": "0",
            "horarios-MAX_NUM_FORMS": "14",
            "horarios-0-dias": ["0", "1", "2"],
            "horarios-0-hora_abertura": "08:00",
            "horarios-0-hora_fechamento": "17:00",
        }
        resp_cad = self.client.post(reverse("pontos_coleta:cadastrar"), data=post_data)
        ponto = PontoColeta.objects.get(cnpj="11222333000181")
        self.assertRedirects(
            resp_cad, reverse("pontos_coleta:documentos", kwargs={"ponto_id": ponto.pk})
        )

        # Ainda pendente: não aparece na lista pública
        resp_pub_antes = self.client.get(reverse("pontos_coleta:lista_publica"))
        self.assertNotContains(resp_pub_antes, "Farmácia do Bem")

        # Envia os 2 documentos obrigatórios (RF006)
        tipos_doc = list(TipoDocumentoPonto.objects.filter(obrigatorio=True).order_by("id"))
        url_docs = reverse("pontos_coleta:documentos", kwargs={"ponto_id": ponto.pk})
        for idx, tipo_doc in enumerate(tipos_doc, start=1):
            arquivo = SimpleUploadedFile(
                f"doc_{idx}.pdf", _pdf_valido(), content_type="application/pdf"
            )
            resp_up = self.client.post(
                url_docs,
                data={
                    "tipo_documento": str(tipo_doc.pk),
                    "numero_documento": f"NUM-{idx}",
                    "data_validade": "2027-12-31",
                    "arquivo": arquivo,
                },
                follow=True,
            )
            self.assertEqual(resp_up.status_code, 200)
            self.assertContains(
                resp_up, "Documento enviado com sucesso. O cadastro está em análise"
            )

        # Admin com aprovacao_pontos_coleta (+ 2FA) visualiza documento (60 s) e aprova
        admin = self._criar_usuario(
            "adm@exemplo.com",
            "11144477735",
            funcoes=("aprovacao_pontos_coleta",),
            ativar_totp=True,
        )
        self._logar_com_2fa(admin, verificado=True)

        doc = DocumentoPontoColeta.objects.filter(ponto_coleta=ponto).first()
        resp_acesso = self.client.get(
            reverse("pontos_coleta:documento_acessar", kwargs={"doc_id": doc.pk})
        )
        self.assertEqual(resp_acesso.status_code, 302)
        self.assertIn("/arquivos/privados/", resp_acesso["Location"])
        resp_dl = self.client.get(resp_acesso["Location"])
        self.assertEqual(resp_dl.status_code, 200)
        self.assertEqual(resp_dl["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp_dl["Cache-Control"], "no-store")
        self.assertTrue(b"".join(resp_dl.streaming_content).startswith(b"%PDF-"))
        for closer in resp_dl._resource_closers:
            closer()
        resp_dl._resource_closers.clear()
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="arquivo.acessado", entidade_id=str(doc.pk), ator=admin
            ).exists()
        )

        # Aprovação (RF007)
        resp_apr = self.client.post(
            reverse("pontos_coleta:admin_analisar", kwargs={"ponto_id": ponto.pk}),
            data={"resultado": ResultadoAnalisePonto.APROVADO, "motivo": "Tudo conferido."},
            follow=True,
        )
        self.assertEqual(resp_apr.status_code, 200)
        self.assertContains(resp_apr, "Situação do ponto de coleta atualizada com sucesso")

        # Agora ativo: aparece na lista pública
        ponto.refresh_from_db()
        self.assertEqual(ponto.status, StatusPontoColeta.ATIVO)
        resp_pub_depois = self.client.get(reverse("pontos_coleta:lista_publica"))
        self.assertContains(resp_pub_depois, "Farmácia do Bem")

    @patch("nucleo.services.CepService.obter_coordenadas_em_cache", return_value=(None, None))
    def test_matriz_permissoes_e_isolamento_entre_perfis(self, _mock_geo):
        """CA-05-04, CA-05-05, CA-06-04 e CA-07-05."""
        resp = self._criar_usuario("resp@exemplo.com", "52998224725")
        outro = self._criar_usuario("outro@exemplo.com", "11144477735")
        adm_usuarios = self._criar_usuario(
            "adm-u@exemplo.com", "12345678909", funcoes=("gestao_usuarios",), ativar_totp=True
        )
        super_sem = self._criar_usuario("super@exemplo.com", "71428793860", is_superuser=True)
        adm_sem_2fa = self._criar_usuario(
            "adm-p@exemplo.com",
            "39053344705",
            funcoes=("aprovacao_pontos_coleta",),
            ativar_totp=True,
        )

        tipo = TipoEstabelecimento.objects.first()
        ponto = PontoColetaService.cadastrar(
            resp,
            DadosPontoColeta(
                cnpj="11222333000181",
                razao_social="ONG Saúde LTDA",
                nome_fantasia="ONG Saúde",
                tipo_estabelecimento_id=tipo.pk,
                email="ong@saude.org",
                telefone="1133334444",
                possui_refrigeracao=False,
                observacoes="",
                cep="01001000",
                logradouro="Praça da Sé",
                numero="1",
                bairro="Sé",
                municipio="São Paulo",
                estado="SP",
            ),
            [ItemHorario(0, time(8, 0), time(12, 0))],
        )
        tipo_doc = TipoDocumentoPonto.objects.first()
        doc = DocumentoPontoService.enviar(
            ponto.pk,
            resp,
            tipo_documento_id=tipo_doc.pk,
            numero_documento="DOC-1",
            data_validade=date(2027, 12, 1),
            conteudo=_pdf_valido(),
            nome_original="doc.pdf",
            referencia=date(2026, 11, 23),
        )

        # Outro cidadão recebe 404 nas rotas de gestão e documento do ponto
        self.client.force_login(outro)
        self.assertEqual(
            self.client.get(
                reverse("pontos_coleta:editar", kwargs={"ponto_id": ponto.pk})
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("pontos_coleta:documentos", kwargs={"ponto_id": ponto.pk})
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("pontos_coleta:documento_acessar", kwargs={"doc_id": doc.pk})
            ).status_code,
            404,
        )

        # Admin com gestao_usuarios (sem aprovacao_pontos_coleta) -> 403 nas rotas admin e doc
        self._logar_com_2fa(adm_usuarios, verificado=True)
        for url in (
            reverse("pontos_coleta:admin_lista"),
            reverse("pontos_coleta:admin_detalhe", kwargs={"ponto_id": ponto.pk}),
            reverse("pontos_coleta:admin_documentos"),
            reverse("pontos_coleta:documento_acessar", kwargs={"doc_id": doc.pk}),
        ):
            self.assertEqual(self.client.get(url).status_code, 403)

        # is_superuser sem função explícita -> 403
        self._logar_com_2fa(super_sem, verificado=True)
        self.assertEqual(self.client.get(reverse("pontos_coleta:admin_lista")).status_code, 403)

        # Admin com aprovacao_pontos_coleta sem 2FA verificado -> redireciona para totp_verificar
        self._logar_com_2fa(adm_sem_2fa, verificado=False)
        r_2fa = self.client.get(reverse("pontos_coleta:admin_lista"))
        self.assertEqual(r_2fa.status_code, 302)
        self.assertIn(reverse("contas:totp_verificar"), r_2fa["Location"])

    def test_get_cadastrar_ponto_nao_exibe_barra_de_abas_nem_link_cadastro_pf(self):
        usuario = self._criar_usuario("resp-tela@exemplo.com", "52998224725")
        self.client.force_login(usuario)

        resposta = self.client.get(reverse("pontos_coleta:cadastrar"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Parceria ReMed")
        self.assertContains(resposta, "Cadastro de instituição / ponto de coleta")
        self.assertContains(resposta, "Cadastro com responsável autenticado")
        self.assertNotContains(resposta, 'role="tablist"')
        self.assertNotContains(resposta, "Pessoa Física · Doador / Solicitante")
        self.assertNotContains(resposta, f'href="{reverse("contas:cadastro")}"')

    def test_lista_publica_exibe_chamada_cadastrar_ponto_para_visitante_e_autenticado(self):
        url_lista = reverse("pontos_coleta:lista_publica")
        url_cadastrar = reverse("pontos_coleta:cadastrar")

        resp_visitante = self.client.get(url_lista)
        self.assertEqual(resp_visitante.status_code, 200)
        self.assertContains(resp_visitante, "Representa uma instituição?")
        self.assertContains(resp_visitante, "Cadastrar ponto de coleta")
        self.assertContains(resp_visitante, f'href="{url_cadastrar}"')

        usuario = self._criar_usuario("visitante-auth@exemplo.com", "52998224725")
        self.client.force_login(usuario)
        resp_autenticado = self.client.get(url_lista)
        self.assertEqual(resp_autenticado.status_code, 200)
        self.assertContains(resp_autenticado, "Representa uma instituição?")
        self.assertContains(resp_autenticado, "Cadastrar ponto de coleta")
        self.assertContains(resp_autenticado, f'href="{url_cadastrar}"')
