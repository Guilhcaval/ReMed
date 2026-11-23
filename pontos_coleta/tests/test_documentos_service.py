"""Testes unitários de DocumentoPontoService e rotina verificar_documentos_pontos (Spec 06)."""

import tempfile
from datetime import date, time, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from contas.models import Usuario
from notificacoes.models import CanalNotificacao, Notificacao, TipoNotificacao
from nucleo.exceptions import PermissaoNegada, RecursoNaoEncontrado
from nucleo.models import ExecucaoRotina, ResultadoRotina, TipoDocumentoPonto, TipoEstabelecimento
from pontos_coleta.exceptions import DocumentoVencido
from pontos_coleta.models import (
    DocumentoPontoColeta,
    PontoColeta,
    StatusDocumentoPonto,
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
    REMED_PONTO_DOC_AVISO_VENCIMENTO_DIAS=30,
)
class DocumentoPontoServiceTest(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta_privada = Path(self._tmp.name)
        self._override = override_settings(PRIVATE_STORAGE_ROOT=self.pasta_privada)
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        self._tmp.cleanup()

    def _criar_usuario(self, email: str, cpf: str, funcoes: tuple[str, ...] = ()) -> Usuario:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=f"Nome {email}",
            data_nascimento=date(1990, 5, 5),
            celular="11988887777",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )
        if funcoes:
            grupos = [Group.objects.get_or_create(name=f)[0] for f in funcoes]
            usuario.groups.set(grupos)
        return usuario

    @patch("nucleo.services.CepService.obter_coordenadas_em_cache", return_value=(None, None))
    def _criar_ponto(self, usuario: Usuario, _mock_geo) -> PontoColeta:
        tipo = TipoEstabelecimento.objects.first()
        return PontoColetaService.cadastrar(
            usuario,
            DadosPontoColeta(
                cnpj="11222333000181",
                razao_social="Clínica Vida LTDA",
                nome_fantasia="Clínica Vida",
                tipo_estabelecimento_id=tipo.pk,
                email="clinica@vida.org",
                telefone="1133334444",
                possui_refrigeracao=False,
                observacoes="",
                cep="01001000",
                logradouro="Praça da Sé",
                numero="50",
                bairro="Sé",
                municipio="São Paulo",
                estado="SP",
            ),
            [ItemHorario(0, time(8, 0), time(17, 0))],
        )

    def test_envio_versionamento_limpeza_em_rollback_e_acesso_auditado(self):
        """CA-06-01, CA-06-02, CA-06-03 e CA-06-04."""
        resp = self._criar_usuario("resp@exemplo.com", "52998224725")
        outro = self._criar_usuario("outro@exemplo.com", "11144477735")
        adm_sem = self._criar_usuario(
            "adm-u@exemplo.com", "12345678909", funcoes=("gestao_usuarios",)
        )
        adm_ok = self._criar_usuario(
            "adm-p@exemplo.com", "71428793860", funcoes=("aprovacao_pontos_coleta",)
        )
        ponto = self._criar_ponto(resp)
        tipos = list(TipoDocumentoPonto.objects.filter(obrigatorio=True).order_by("id"))

        # Validade anterior a hoje -> mensagem literal RF006
        with self.assertRaises(DocumentoVencido) as ctx:
            DocumentoPontoService.enviar(
                ponto.pk,
                resp,
                tipo_documento_id=tipos[0].pk,
                numero_documento="LIC-1",
                data_validade=date(2026, 11, 22),
                conteudo=_pdf_valido(),
                nome_original="licenca.pdf",
                referencia=date(2026, 11, 23),
            )
        self.assertEqual(str(ctx.exception), "Documento vencido. Envie um documento válido")

        # Envio dos 2 obrigatórios passa ambos para em_analise
        doc1 = DocumentoPontoService.enviar(
            ponto.pk,
            resp,
            tipo_documento_id=tipos[0].pk,
            numero_documento="LIC-1",
            data_validade=date(2027, 6, 1),
            conteudo=_pdf_valido(),
            nome_original="licenca.pdf",
            referencia=date(2026, 11, 23),
        )
        self.assertEqual(doc1.versao, 1)
        self.assertEqual(doc1.status, StatusDocumentoPonto.ENVIADO)

        doc2 = DocumentoPontoService.enviar(
            ponto.pk,
            resp,
            tipo_documento_id=tipos[1].pk,
            numero_documento="ALV-1",
            data_validade=date(2027, 6, 1),
            conteudo=_pdf_valido(),
            nome_original="alvara.pdf",
            referencia=date(2026, 11, 23),
        )
        doc1.refresh_from_db()
        self.assertEqual(doc1.status, StatusDocumentoPonto.EM_ANALISE)
        self.assertEqual(doc2.status, StatusDocumentoPonto.EM_ANALISE)

        # Nova versão preserva v1 intacta (CA-06-03)
        doc1_v2 = DocumentoPontoService.enviar(
            ponto.pk,
            resp,
            tipo_documento_id=tipos[0].pk,
            numero_documento="LIC-2",
            data_validade=date(2027, 12, 1),
            conteudo=_pdf_valido(),
            nome_original="licenca_v2.pdf",
            referencia=date(2026, 11, 23),
        )
        self.assertEqual(doc1_v2.versao, 2)
        self.assertEqual(
            DocumentoPontoColeta.objects.filter(
                ponto_coleta=ponto, tipo_documento=tipos[0]
            ).count(),
            2,
        )

        # Limpeza do arquivo físico em caso de falha na transação do banco
        arquivos_antes = set(self.pasta_privada.rglob("*.pdf"))
        with patch("auditoria.services.AuditoriaService.registrar", side_effect=RuntimeError("DB")):
            with self.assertRaises(RuntimeError):
                DocumentoPontoService.enviar(
                    ponto.pk,
                    resp,
                    tipo_documento_id=tipos[0].pk,
                    numero_documento="LIC-3",
                    data_validade=date(2028, 1, 1),
                    conteudo=_pdf_valido(),
                    nome_original="licenca_v3.pdf",
                    referencia=date(2026, 11, 23),
                )
        self.assertEqual(set(self.pasta_privada.rglob("*.pdf")), arquivos_antes)

        # Controle de acesso e auditoria de leitura (CA-06-04)
        with self.assertRaises(RecursoNaoEncontrado):
            DocumentoPontoService.gerar_acesso_temporario(doc1.pk, outro)
        with self.assertRaises(PermissaoNegada):
            DocumentoPontoService.gerar_acesso_temporario(doc1.pk, adm_sem)

        url = DocumentoPontoService.gerar_acesso_temporario(doc1.pk, adm_ok)
        self.assertIn("/arquivos/privados/", url)
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="arquivo.acessado", entidade_id=str(doc1.pk), ator=adm_ok
            ).exists()
        )

    def test_rotina_diaria_aviso_idempotente_e_vencimento_devolve_ponto(self):
        """CA-06-05: aviso 30 dias antes idempotente e vencimento devolve ponto ativo."""
        resp = self._criar_usuario("resp@exemplo.com", "52998224725")
        ponto = self._criar_ponto(resp)
        tipos = list(TipoDocumentoPonto.objects.filter(obrigatorio=True).order_by("id"))

        hoje = date(2026, 11, 23)
        doc_aviso = DocumentoPontoService.enviar(
            ponto.pk,
            resp,
            tipo_documento_id=tipos[0].pk,
            numero_documento="LIC-AV",
            data_validade=hoje + timedelta(days=15),
            conteudo=_pdf_valido(),
            nome_original="licenca.pdf",
            referencia=hoje,
        )
        doc_venc = DocumentoPontoService.enviar(
            ponto.pk,
            resp,
            tipo_documento_id=tipos[1].pk,
            numero_documento="ALV-VC",
            data_validade=hoje + timedelta(days=1),
            conteudo=_pdf_valido(),
            nome_original="alvara.pdf",
            referencia=hoje,
        )
        DocumentoPontoColeta.objects.filter(pk__in=[doc_aviso.pk, doc_venc.pk]).update(
            status=StatusDocumentoPonto.APROVADO
        )
        PontoColeta.objects.filter(pk=ponto.pk).update(status=StatusPontoColeta.ATIVO)

        # 1ª execução em hoje: avisa sobre doc_aviso (15 dias) e não duplica na 2ª execução
        r1 = DocumentoPontoService.processar_vencimentos_diarios(referencia=hoje)
        self.assertEqual(r1.avisos_enviados, 2)  # ambos vencem em <= 30 dias
        self.assertEqual(r1.documentos_vencidos, 0)

        r2 = DocumentoPontoService.processar_vencimentos_diarios(referencia=hoje)
        self.assertEqual(r2.avisos_enviados, 0)  # idempotente
        self.assertEqual(
            Notificacao.objects.filter(
                destinatario=resp,
                tipo=TipoNotificacao.DOCUMENTO_PRESTES_VENCER,
                canal=CanalNotificacao.PLATAFORMA,
            ).count(),
            2,
        )

        # Avança relógio 2 dias: doc_venc expirou -> marca vencido e devolve ponto para pendente
        cancelados: list[int] = []
        r3 = DocumentoPontoService.processar_vencimentos_diarios(
            referencia=hoje + timedelta(days=2),
            cancelador_agendamentos_futuros=lambda p: cancelados.append(p.pk),
        )
        self.assertEqual(r3.documentos_vencidos, 1)
        self.assertEqual(r3.pontos_remetidos_reaprovacao, 1)
        self.assertEqual(cancelados, [ponto.pk])

        doc_venc.refresh_from_db()
        ponto.refresh_from_db()
        self.assertEqual(doc_venc.status, StatusDocumentoPonto.VENCIDO)
        self.assertEqual(ponto.status, StatusPontoColeta.PENDENTE_APROVACAO)

        # Comando manage.py registra ExecucaoRotina
        call_command("verificar_documentos_pontos", stdout=StringIO())
        execucao = ExecucaoRotina.objects.filter(nome_rotina="verificar_documentos_pontos").first()
        self.assertIsNotNone(execucao)
        self.assertEqual(execucao.resultado, ResultadoRotina.SUCESSO)
