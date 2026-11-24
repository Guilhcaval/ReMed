"""Testes unitários de DoacaoService e RefrigeracaoService (Specs 08 e 09)."""

import io
import tempfile
from datetime import date, time, timedelta
from pathlib import Path

from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image

from auditoria.models import RegistroAuditoria
from contas.models import EnderecoUsuario, Usuario
from contas.services import UsuarioService
from medicamentos.exceptions import (
    CienciaRefrigeradoObrigatoria,
    DadosRefrigeracaoObrigatorios,
    EmbalagemNaoIntegra,
    FotoDoacaoFormatoInvalido,
    JanelaRefrigeradoInvalida,
    MedicamentoControleEspecialBloqueado,
    ValidadeDoacaoInvalida,
)
from medicamentos.models import (
    CondicaoConservacao,
    DadosRefrigeracaoDoacao,
    Doacao,
    FotoDoacao,
    StatusDoacao,
)
from medicamentos.services import (
    ArquivoFotoEntrada,
    DadosDoacao,
    DoacaoService,
    RefrigeracaoService,
)
from nucleo.exceptions import PermissaoNegada, RecursoNaoEncontrado, RegraNegocioViolada
from nucleo.models import FormaFarmaceutica, TipoEstabelecimento
from pontos_coleta.models import PontoColeta, StatusPontoColeta


def _jpeg_com_exif() -> bytes:
    img = Image.new("RGB", (60, 40), color=(23, 70, 107))
    exif = img.getexif()
    exif[0x010F] = "CameraSecreta"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _png_valido() -> bytes:
    img = Image.new("RGB", (40, 40), color=(30, 122, 82))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class DoacaoERefrigeracaoServiceTest(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta_privada = Path(self._tmp.name)
        self._override = override_settings(PRIVATE_STORAGE_ROOT=self.pasta_privada)
        self._override.enable()
        self.hoje = date(2026, 11, 24)
        self.forma = FormaFarmaceutica.objects.first()

    def tearDown(self):
        self._override.disable()
        self._tmp.cleanup()

    def _criar_usuario(
        self,
        email: str = "doador@exemplo.com",
        cpf: str = "52998224725",
        *,
        perfil_doador: bool = True,
    ) -> Usuario:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo="Doador Teste",
            data_nascimento=date(1990, 5, 10),
            celular="11988887777",
            perfil_doador=perfil_doador,
            perfil_solicitante=not perfil_doador,
            email_confirmado_em=timezone.now(),
        )
        EnderecoUsuario.objects.create(
            usuario=usuario,
            cep="01001000",
            logradouro="Praça da Sé",
            numero="10",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            latitude_aprox="-23.550520",
            longitude_aprox="-46.633308",
        )
        return usuario

    def _dados_padrao(self, **sobrescritas) -> DadosDoacao:
        base = dict(
            nome_medicamento="Losartana potássica",
            principio_ativo="Losartana potássica",
            concentracao_dosagem="50 mg",
            forma_farmaceutica_id=self.forma.pk,
            quantidade=30,
            fabricante="EMS",
            lote="L2026X",
            data_validade=self.hoje + timedelta(days=90),
            embalagem_integra=True,
            controle_especial=False,
            condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE,
            sujeito_receita=False,
            ponto_coleta_id=None,
            observacoes="Caixa fechada",
            faixa_temperatura_bula="",
            declaracao_doador_conservacao=False,
        )
        base.update(sobrescritas)
        return DadosDoacao(**base)

    def test_cadastro_valido_nasce_em_analise_remove_exif_e_grava_auditoria(self):
        """CA-08-01."""
        doador = self._criar_usuario()
        doacao = DoacaoService.cadastrar(
            doador,
            self._dados_padrao(),
            [ArquivoFotoEntrada(conteudo=_jpeg_com_exif(), nome_original="caixa.jpg")],
            referencia=self.hoje,
        )
        self.assertEqual(doacao.status, StatusDoacao.EM_ANALISE)
        self.assertEqual(doacao.quantidade_disponivel, 30)
        self.assertEqual(doacao.regiao_bairro, "Sé")
        self.assertEqual(str(doacao.latitude_aprox), "-23.55")

        foto = FotoDoacao.objects.get(doacao=doacao, ordem=1)
        caminho = self.pasta_privada / foto.arquivo_chave
        self.assertTrue(caminho.is_file())
        with Image.open(caminho) as img_salva:
            self.assertEqual(len(img_salva.getexif()), 0)

        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="doacao.cadastrada", entidade_id=str(doacao.pk), ator=doador
            ).exists()
        )
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="arquivo.enviado", entidade_id=str(foto.pk), ator=doador
            ).exists()
        )

    def test_bloqueios_de_seguranca_embalagem_validade_controle_especial_e_foto(self):
        """CA-08-02 e CA-09-01."""
        doador = self._criar_usuario()
        foto_ok = [ArquivoFotoEntrada(conteudo=_png_valido(), nome_original="f.png")]

        with self.assertRaises(EmbalagemNaoIntegra):
            DoacaoService.cadastrar(
                doador, self._dados_padrao(embalagem_integra=False), foto_ok, referencia=self.hoje
            )
        with self.assertRaises(MedicamentoControleEspecialBloqueado):
            DoacaoService.cadastrar(
                doador, self._dados_padrao(controle_especial=True), foto_ok, referencia=self.hoje
            )
        with self.assertRaises(ValidadeDoacaoInvalida):
            DoacaoService.cadastrar(
                doador,
                self._dados_padrao(data_validade=self.hoje - timedelta(days=1)),
                foto_ok,
                referencia=self.hoje,
            )
        with self.assertRaises(ValidadeDoacaoInvalida):
            DoacaoService.cadastrar(
                doador,
                self._dados_padrao(data_validade=self.hoje + timedelta(days=10)),
                foto_ok,
                referencia=self.hoje,
            )
        with self.assertRaises(FotoDoacaoFormatoInvalido):
            DoacaoService.cadastrar(
                doador,
                self._dados_padrao(),
                [ArquivoFotoEntrada(conteudo=b"%PDF-1.4\n%%EOF", nome_original="doc.pdf")],
                referencia=self.hoje,
            )
        with self.assertRaises(DadosRefrigeracaoObrigatorios):
            DoacaoService.cadastrar(
                doador,
                self._dados_padrao(
                    condicao_conservacao=CondicaoConservacao.REFRIGERADO,
                    faixa_temperatura_bula="",
                    declaracao_doador_conservacao=False,
                ),
                foto_ok,
                referencia=self.hoje,
            )

        sem_perfil_doador = self._criar_usuario(
            email="so-sol@exemplo.com", cpf="11144477735", perfil_doador=False
        )
        with self.assertRaises(PermissaoNegada):
            DoacaoService.cadastrar(
                sem_perfil_doador, self._dados_padrao(), foto_ok, referencia=self.hoje
            )

    def test_regras_puras_refrigeracao_janela_ciencia_e_priorizacao_pontos(self):
        """CA-09-02, CA-09-03 e CA-09-04."""
        self.assertEqual(
            RefrigeracaoService.validar_janela_curta(time(9, 0), time(11, 0), limite_minutos=120),
            120,
        )
        with self.assertRaises(JanelaRefrigeradoInvalida):
            RefrigeracaoService.validar_janela_curta(time(9, 0), time(11, 1), limite_minutos=120)
        with self.assertRaises(JanelaRefrigeradoInvalida):
            RefrigeracaoService.validar_janela_curta(time(11, 0), time(11, 0), limite_minutos=120)
        with self.assertRaises(CienciaRefrigeradoObrigatoria):
            RefrigeracaoService.validar_ciencia_solicitante(False)
        RefrigeracaoService.validar_ciencia_solicitante(True)

        tipo = TipoEstabelecimento.objects.first()
        p_sem = PontoColeta.objects.create(
            cnpj="11222333000181",
            razao_social="A LTDA",
            nome_fantasia="AAA Sem Frio",
            tipo_estabelecimento=tipo,
            email="a@a.org",
            telefone="1133334444",
            possui_refrigeracao=False,
            cep="01001000",
            logradouro="Rua A",
            numero="1",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            status=StatusPontoColeta.ATIVO,
        )
        p_com = PontoColeta.objects.create(
            cnpj="11444777000161",
            razao_social="Z LTDA",
            nome_fantasia="ZZZ Com Frio",
            tipo_estabelecimento=tipo,
            email="z@z.org",
            telefone="1133335555",
            possui_refrigeracao=True,
            cep="01001000",
            logradouro="Rua Z",
            numero="2",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            status=StatusPontoColeta.ATIVO,
        )
        ordenados = RefrigeracaoService.priorizar_pontos_refrigerados([p_sem, p_com])
        self.assertEqual([p.pk for p in ordenados], [p_com.pk, p_sem.pk])

    def test_edicao_devolve_disponivel_a_em_analise_e_trata_transicoes_de_refrigeracao(self):
        """CA-08-03 e refinamento ambiente <-> refrigerado."""
        doador = self._criar_usuario()
        doacao = DoacaoService.cadastrar(
            doador,
            self._dados_padrao(),
            [ArquivoFotoEntrada(conteudo=_png_valido(), nome_original="f1.png")],
            referencia=self.hoje,
        )
        Doacao.objects.filter(pk=doacao.pk).update(status=StatusDoacao.DISPONIVEL)

        # Editar apenas observações mantém disponivel
        res_obs = DoacaoService.atualizar(
            doacao.pk,
            doador,
            self._dados_padrao(observacoes="Nova obs"),
            referencia=self.hoje,
        )
        self.assertFalse(res_obs.remetida_reanalise)
        self.assertEqual(res_obs.doacao.status, StatusDoacao.DISPONIVEL)

        # Transição ambiente -> refrigerado cria DadosRefrigeracaoDoacao e volta a em_analise
        res_refrig = DoacaoService.atualizar(
            doacao.pk,
            doador,
            self._dados_padrao(
                condicao_conservacao=CondicaoConservacao.REFRIGERADO,
                faixa_temperatura_bula="2 °C a 8 °C",
                declaracao_doador_conservacao=True,
            ),
            referencia=self.hoje,
        )
        self.assertTrue(res_refrig.remetida_reanalise)
        self.assertEqual(res_refrig.doacao.status, StatusDoacao.EM_ANALISE)
        self.assertTrue(DadosRefrigeracaoDoacao.objects.filter(doacao=doacao).exists())

        # Transição refrigerado -> ambiente remove DadosRefrigeracaoDoacao e devolve a em_analise
        Doacao.objects.filter(pk=doacao.pk).update(status=StatusDoacao.DISPONIVEL)
        res_amb = DoacaoService.atualizar(
            doacao.pk,
            doador,
            self._dados_padrao(condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE),
            referencia=self.hoje,
        )
        self.assertTrue(res_amb.remetida_reanalise)
        self.assertEqual(res_amb.doacao.status, StatusDoacao.EM_ANALISE)
        self.assertFalse(DadosRefrigeracaoDoacao.objects.filter(doacao=doacao).exists())

    def test_cancelamento_sem_exclusao_e_encerramento_lgpd_cancela_doacoes_abertas(self):
        """CA-08-04, CA-08-05 e integração contas.UsuarioService.encerrar_conta."""
        doador = self._criar_usuario()
        outro = self._criar_usuario(email="outro@exemplo.com", cpf="11144477735")
        doacao1 = DoacaoService.cadastrar(
            doador,
            self._dados_padrao(),
            [ArquivoFotoEntrada(conteudo=_png_valido(), nome_original="f1.png")],
            referencia=self.hoje,
        )
        doacao2 = DoacaoService.cadastrar(
            doador,
            self._dados_padrao(nome_medicamento="Dipirona"),
            [ArquivoFotoEntrada(conteudo=_png_valido(), nome_original="f2.png")],
            referencia=self.hoje,
        )
        Doacao.objects.filter(pk=doacao2.pk).update(status=StatusDoacao.DISPONIVEL)

        with self.assertRaises(RecursoNaoEncontrado):
            DoacaoService.cancelar(doacao1.pk, outro)

        DoacaoService.cancelar(doacao1.pk, doador)
        doacao1.refresh_from_db()
        self.assertEqual(doacao1.status, StatusDoacao.CANCELADO)

        # Doação entregue não pode ser cancelada
        Doacao.objects.filter(pk=doacao1.pk).update(status=StatusDoacao.ENTREGUE)
        with self.assertRaises(RegraNegocioViolada):
            DoacaoService.cancelar(doacao1.pk, doador)

        # Encerramento LGPD da conta cancela doação disponível restante
        UsuarioService.encerrar_conta(doador, "Rm3d!Senha1")
        doacao2.refresh_from_db()
        self.assertEqual(doacao2.status, StatusDoacao.CANCELADO)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class SubstituicaoFotoOnCommitTest(TransactionTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta_privada = Path(self._tmp.name)
        self._override = override_settings(PRIVATE_STORAGE_ROOT=self.pasta_privada)
        self._override.enable()
        self.hoje = date(2026, 11, 24)
        self.forma, _ = FormaFarmaceutica.objects.get_or_create(nome="Comprimido")

    def tearDown(self):
        self._override.disable()
        self._tmp.cleanup()

    def test_substituicao_foto_remove_arquivo_antigo_em_on_commit_e_devolve_em_analise(self):
        doador = Usuario.objects.create_user(
            email="foto-commit@exemplo.com",
            cpf="52998224725",
            password="Rm3d!Senha1",
            nome_completo="Doador Foto",
            data_nascimento=date(1990, 5, 10),
            celular="11988887777",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )
        dados = DadosDoacao(
            nome_medicamento="Paracetamol",
            principio_ativo="Paracetamol",
            concentracao_dosagem="750 mg",
            forma_farmaceutica_id=self.forma.pk,
            quantidade=10,
            fabricante="EMS",
            lote="L1",
            data_validade=self.hoje + timedelta(days=90),
            embalagem_integra=True,
            controle_especial=False,
            condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE,
            sujeito_receita=False,
        )
        doacao = DoacaoService.cadastrar(
            doador,
            dados,
            [ArquivoFotoEntrada(conteudo=_png_valido(), nome_original="orig.png")],
            referencia=self.hoje,
        )
        foto_orig = FotoDoacao.objects.get(doacao=doacao, ordem=1)
        chave_antiga = foto_orig.arquivo_chave
        self.assertTrue((self.pasta_privada / chave_antiga).is_file())

        Doacao.objects.filter(pk=doacao.pk).update(status=StatusDoacao.DISPONIVEL)
        res = DoacaoService.atualizar(
            doacao.pk,
            doador,
            dados,
            fotos_novas={
                1: ArquivoFotoEntrada(conteudo=_jpeg_com_exif(), nome_original="nova.jpg")
            },
            referencia=self.hoje,
        )
        self.assertTrue(res.remetida_reanalise)
        self.assertEqual(res.doacao.status, StatusDoacao.EM_ANALISE)

        foto_orig.refresh_from_db()
        self.assertNotEqual(foto_orig.arquivo_chave, chave_antiga)
        self.assertTrue((self.pasta_privada / foto_orig.arquivo_chave).is_file())
        self.assertFalse((self.pasta_privada / chave_antiga).is_file())
