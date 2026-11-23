"""Testes de models, constraints, migração de dados e trigger SQL (Specs 05, 06 e 07)."""

from datetime import date, time

from django.db import DatabaseError, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.utils import timezone

from contas.models import Usuario
from nucleo.models import TipoDocumentoPonto, TipoEstabelecimento
from pontos_coleta.models import (
    AnalisePontoColeta,
    DocumentoPontoColeta,
    HorarioFuncionamentoPonto,
    PontoColeta,
    PontoColetaResponsavel,
    ResultadoAnalisePonto,
    StatusDocumentoPonto,
    StatusPontoColeta,
    StatusResponsavelPonto,
    TipoAcaoAnalisePonto,
)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PontosColetaModelsConstraintsTest(TestCase):
    def _criar_usuario(self, email: str, cpf: str) -> Usuario:
        return Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=f"Usuário {email}",
            data_nascimento=date(1990, 5, 10),
            celular="11988887777",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )

    def _criar_ponto(self, cnpj: str = "11222333000181") -> PontoColeta:
        tipo = TipoEstabelecimento.objects.first()
        return PontoColeta.objects.create(
            cnpj=cnpj,
            razao_social="Farmácia Solidária LTDA",
            nome_fantasia="Farmácia Solidária",
            tipo_estabelecimento=tipo,
            email="contato@farmacia.org",
            telefone="1133334444",
            possui_refrigeracao=True,
            cep="01001000",
            logradouro="Praça da Sé",
            numero="100",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
        )

    def test_migracao_dados_popula_tipos_estabelecimento_e_documento(self):
        """RN-05-02 e RN-06-01: 6 tipos de estabelecimento e 2 documentos obrigatórios."""
        nomes_estab = set(TipoEstabelecimento.objects.values_list("nome", flat=True))
        self.assertTrue(
            {
                "Farmácia",
                "Posto/Unidade de Saúde",
                "Hospital",
                "Clínica",
                "ONG/Instituição Social",
                "Outros",
            }.issubset(nomes_estab)
        )
        nomes_doc = set(
            TipoDocumentoPonto.objects.filter(obrigatorio=True).values_list("nome", flat=True)
        )
        self.assertEqual(nomes_doc, {"Licença de funcionamento", "Alvará sanitário"})

    def test_constraints_ponto_horario_responsavel_documento_e_protect(self):
        """Constraints PostgreSQL e on_delete=PROTECT."""
        usuario = self._criar_usuario("resp@exemplo.com", "52998224725")
        ponto = self._criar_ponto()

        # CNPJ único
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._criar_ponto(cnpj="11222333000181")

        # Horário com dia fora de 0..6 ou abertura >= fechamento
        with self.assertRaises(IntegrityError), transaction.atomic():
            HorarioFuncionamentoPonto.objects.create(
                ponto_coleta=ponto,
                dia_semana=7,
                hora_abertura=time(8, 0),
                hora_fechamento=time(17, 0),
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            HorarioFuncionamentoPonto.objects.create(
                ponto_coleta=ponto,
                dia_semana=0,
                hora_abertura=time(17, 0),
                hora_fechamento=time(8, 0),
            )

        # UniqueConstraint parcial em PontoColetaResponsavel (ativo/convite_pendente)
        PontoColetaResponsavel.objects.create(
            ponto_coleta=ponto, usuario=usuario, status=StatusResponsavelPonto.ATIVO
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PontoColetaResponsavel.objects.create(
                ponto_coleta=ponto, usuario=usuario, status=StatusResponsavelPonto.CONVITE_PENDENTE
            )

        # Documento acima de 5 MB bloqueado pela CheckConstraint
        tipo_doc = TipoDocumentoPonto.objects.first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentoPontoColeta.objects.create(
                ponto_coleta=ponto,
                tipo_documento=tipo_doc,
                versao=1,
                arquivo_chave="pontos_coleta/00000000000000000000000000000001.pdf",
                mime_verificado="application/pdf",
                tamanho_bytes=(5 * 1024 * 1024) + 1,
                numero_documento="DOC-1",
                data_validade=date(2027, 1, 1),
                status=StatusDocumentoPonto.ENVIADO,
                enviado_por=usuario,
            )

        # on_delete=PROTECT impede exclusão física do ponto
        with self.assertRaises(ProtectedError), transaction.atomic():
            ponto.delete()

    def test_analise_check_constraint_motivo_e_trigger_append_only(self):
        """Spec 07 / RN-07-05: CheckConstraint de motivo e trigger 0002 bloqueiam mutação."""
        admin = self._criar_usuario("adm@exemplo.com", "11144477735")
        ponto = self._criar_ponto()

        # Reprovação ou suspensão sem motivo (vazio ou só espaços) -> IntegrityError
        for motivo_ruim in ("", "   "):
            with self.assertRaises(IntegrityError), transaction.atomic():
                AnalisePontoColeta.objects.create(
                    ponto_coleta=ponto,
                    tipo_acao=TipoAcaoAnalisePonto.ANALISE_CADASTRO,
                    resultado=ResultadoAnalisePonto.REPROVADO,
                    status_anterior=StatusPontoColeta.PENDENTE_APROVACAO,
                    status_novo=StatusPontoColeta.PENDENTE_APROVACAO,
                    motivo=motivo_ruim,
                    responsavel=admin,
                )

        analise = AnalisePontoColeta.objects.create(
            ponto_coleta=ponto,
            tipo_acao=TipoAcaoAnalisePonto.ANALISE_CADASTRO,
            resultado=ResultadoAnalisePonto.REPROVADO,
            status_anterior=StatusPontoColeta.PENDENTE_APROVACAO,
            status_novo=StatusPontoColeta.PENDENTE_APROVACAO,
            motivo="Alvará ilegível.",
            responsavel=admin,
        )

        # Trigger 0002 bloqueia UPDATE
        with self.assertRaises(DatabaseError), transaction.atomic():
            AnalisePontoColeta.objects.filter(pk=analise.pk).update(motivo="Adulterado")

        # Trigger 0002 bloqueia DELETE
        with self.assertRaises(DatabaseError), transaction.atomic():
            AnalisePontoColeta.objects.filter(pk=analise.pk).delete()
