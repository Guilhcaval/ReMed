"""Testes unitários de AprovacaoPontoService (Spec 07 / RF007 — CA-07-01 a CA-07-05)."""

import tempfile
from datetime import date, time
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from contas.models import Usuario
from notificacoes.models import CanalNotificacao, Notificacao, TipoNotificacao
from nucleo.exceptions import PermissaoNegada
from nucleo.models import TipoDocumentoPonto, TipoEstabelecimento
from pontos_coleta.exceptions import (
    DocumentosObrigatoriosPendentes,
    MotivoAnaliseObrigatorio,
)
from pontos_coleta.models import (
    AnalisePontoColeta,
    DocumentoPontoColeta,
    PontoColeta,
    ResultadoAnalisePonto,
    StatusDocumentoPonto,
    StatusPontoColeta,
    TipoAcaoAnalisePonto,
)
from pontos_coleta.services import (
    AprovacaoPontoService,
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
)
class AprovacaoPontoServiceTest(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta_privada = Path(self._tmp.name)
        self._override = override_settings(PRIVATE_STORAGE_ROOT=self.pasta_privada)
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        self._tmp.cleanup()

    def _criar_usuario(
        self, email: str, cpf: str, funcoes: tuple[str, ...] = (), is_superuser: bool = False
    ) -> Usuario:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=f"Nome {email}",
            data_nascimento=date(1989, 2, 10),
            celular="11988887777",
            perfil_doador=True,
            is_superuser=is_superuser,
            is_staff=is_superuser,
            email_confirmado_em=timezone.now(),
        )
        if funcoes:
            grupos = [Group.objects.get_or_create(name=f)[0] for f in funcoes]
            usuario.groups.set(grupos)
        return usuario

    @patch("nucleo.services.CepService.obter_coordenadas_em_cache", return_value=(None, None))
    def _criar_ponto(self, resp: Usuario, _mock_geo) -> PontoColeta:
        tipo = TipoEstabelecimento.objects.first()
        return PontoColetaService.cadastrar(
            resp,
            DadosPontoColeta(
                cnpj="11222333000181",
                razao_social="Farmácia Esperança LTDA",
                nome_fantasia="Farmácia Esperança",
                tipo_estabelecimento_id=tipo.pk,
                email="esperanca@farmacia.org",
                telefone="1133334444",
                possui_refrigeracao=True,
                observacoes="",
                cep="01001000",
                logradouro="Praça da Sé",
                numero="10",
                bairro="Sé",
                municipio="São Paulo",
                estado="SP",
            ),
            [ItemHorario(0, time(9, 0), time(18, 0))],
        )

    def _enviar_docs_validos(self, ponto: PontoColeta, resp: Usuario, validade: date):
        tipos = list(TipoDocumentoPonto.objects.filter(obrigatorio=True).order_by("id"))
        docs = []
        for idx, tipo in enumerate(tipos, start=1):
            docs.append(
                DocumentoPontoService.enviar(
                    ponto.pk,
                    resp,
                    tipo_documento_id=tipo.pk,
                    numero_documento=f"DOC-{idx}",
                    data_validade=validade,
                    conteudo=_pdf_valido(),
                    nome_original=f"doc_{idx}.pdf",
                    referencia=date(2026, 11, 23),
                )
            )
        return docs

    def test_aprovacao_bloqueio_sem_docs_motivo_suspensao_reativacao_e_revisao(self):
        """CA-07-01, CA-07-02, CA-07-03, CA-07-04 e CA-07-05."""
        resp = self._criar_usuario("resp@exemplo.com", "52998224725")
        admin = self._criar_usuario(
            "adm@exemplo.com", "11144477735", funcoes=("aprovacao_pontos_coleta",)
        )
        super_sem_funcao = self._criar_usuario(
            "super@exemplo.com", "12345678909", is_superuser=True
        )
        ponto = self._criar_ponto(resp)

        # is_superuser sem função explícita -> PermissaoNegada (CA-07-05)
        with self.assertRaises(PermissaoNegada):
            AprovacaoPontoService.analisar_cadastro(
                super_sem_funcao, ponto.pk, ResultadoAnalisePonto.APROVADO
            )

        # Sem documentos obrigatórios -> aprovação bloqueada (CA-07-02)
        with self.assertRaises(DocumentosObrigatoriosPendentes):
            AprovacaoPontoService.analisar_cadastro(admin, ponto.pk, ResultadoAnalisePonto.APROVADO)

        # Reprovação sem motivo -> mensagem literal RF007 (CA-07-02)
        with self.assertRaises(MotivoAnaliseObrigatorio) as ctx:
            AprovacaoPontoService.analisar_cadastro(
                admin, ponto.pk, ResultadoAnalisePonto.REPROVADO, "   "
            )
        self.assertEqual(str(ctx.exception), "Informe o motivo da reprovação ou da suspensão")

        # Envia os 2 documentos válidos e aprova (CA-07-01)
        docs = self._enviar_docs_validos(ponto, resp, validade=date(2027, 8, 1))
        analise_ok = AprovacaoPontoService.analisar_cadastro(
            admin,
            ponto.pk,
            ResultadoAnalisePonto.APROVADO,
            "Documentação regular.",
            referencia=date(2026, 11, 23),
        )
        ponto.refresh_from_db()
        self.assertEqual(ponto.status, StatusPontoColeta.ATIVO)
        self.assertIsNotNone(ponto.ultima_revisao_em)
        self.assertEqual(analise_ok.resultado, ResultadoAnalisePonto.APROVADO)
        for doc in docs:
            doc.refresh_from_db()
            self.assertEqual(doc.status, StatusDocumentoPonto.APROVADO)
        self.assertTrue(
            Notificacao.objects.filter(
                destinatario=resp,
                tipo=TipoNotificacao.PONTO_ANALISADO,
                canal=CanalNotificacao.PLATAFORMA,
            ).exists()
        )

        # Revisão periódica atualiza ultima_revisao_em e grava histórico
        rev = AprovacaoPontoService.registrar_revisao_periodica(
            admin, ponto.pk, "Revisão semestral OK", referencia=date(2026, 11, 23)
        )
        self.assertEqual(rev.tipo_acao, TipoAcaoAnalisePonto.REVISAO_PERIODICA)

        # Suspensão aciona gancho cancelador_agendamentos_futuros (CA-07-03)
        cancelados: list[int] = []
        AprovacaoPontoService.alterar_situacao(
            admin,
            ponto.pk,
            StatusPontoColeta.SUSPENSO,
            "Reforma temporária no local.",
            referencia=date(2026, 11, 23),
            cancelador_agendamentos_futuros=lambda p: cancelados.append(p.pk),
        )
        ponto.refresh_from_db()
        self.assertEqual(ponto.status, StatusPontoColeta.SUSPENSO)
        self.assertEqual(cancelados, [ponto.pk])

        # Reativação bloqueada se um documento venceu (CA-07-04)
        DocumentoPontoColeta.objects.filter(pk=docs[0].pk).update(
            data_validade=date(2026, 10, 1), status=StatusDocumentoPonto.VENCIDO
        )
        with self.assertRaises(DocumentosObrigatoriosPendentes):
            AprovacaoPontoService.alterar_situacao(
                admin,
                ponto.pk,
                StatusPontoColeta.ATIVO,
                "Tentativa sem alvará válido",
                referencia=date(2026, 11, 23),
            )

        self.assertTrue(AnalisePontoColeta.objects.filter(ponto_coleta=ponto).count() >= 3)
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="ponto_coleta.aprovado", entidade_id=str(ponto.pk)
            ).exists()
        )
