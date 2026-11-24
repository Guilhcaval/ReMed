"""Testes de constraints PostgreSQL, PROTECT, triggers append-only e dados iniciais."""

from datetime import date

from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from contas.models import Usuario
from medicamentos.models import (
    CondicaoConservacao,
    ConferenciaDoacao,
    DadosRefrigeracaoDoacao,
    Doacao,
    ExecucaoVencimento,
    FotoDoacao,
    ParametroVencimento,
    ResultadoConferenciaDoacao,
)
from nucleo.models import ExecucaoRotina, FormaFarmaceutica, ResultadoRotina


class MedicamentosModelsConstraintsTest(TestCase):
    def _criar_usuario(self, email: str = "doador@exemplo.com", cpf: str = "52998224725"):
        return Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo="Doador Teste",
            data_nascimento=date(1990, 5, 10),
            celular="11988887777",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )

    def _criar_doacao(self, doador: Usuario) -> Doacao:
        forma = FormaFarmaceutica.objects.first()
        return Doacao.objects.create(
            doador=doador,
            nome_medicamento="Dipirona",
            principio_ativo="Dipirona sódica",
            concentracao_dosagem="500 mg",
            forma_farmaceutica=forma,
            quantidade_inicial=20,
            quantidade_disponivel=20,
            fabricante="EMS",
            lote="L2026A",
            data_validade=date(2027, 12, 31),
            embalagem_integra=True,
            condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE,
            sujeito_receita=False,
        )

    def test_migracoes_de_dados_populam_formas_farmaceuticas_e_parametro_vencimento(self):
        self.assertGreaterEqual(FormaFarmaceutica.objects.filter(ativo=True).count(), 11)
        self.assertTrue(FormaFarmaceutica.objects.filter(nome="Comprimido").exists())
        self.assertTrue(FormaFarmaceutica.objects.filter(nome="Injetável").exists())

        param = ParametroVencimento.objects.get(pk=1)
        self.assertEqual(param.validade_minima_restante_dias, 30)
        self.assertEqual(param.antecedencia_aviso_dias, 15)

    def test_constraints_doacao_foto_refrigeracao_parametro_e_protect(self):
        doador = self._criar_usuario()
        forma = FormaFarmaceutica.objects.first()

        # quantidade_inicial == 0 rejeitada
        with self.assertRaises(IntegrityError), transaction.atomic():
            Doacao.objects.create(
                doador=doador,
                nome_medicamento="A",
                principio_ativo="A",
                concentracao_dosagem="10 mg",
                forma_farmaceutica=forma,
                quantidade_inicial=0,
                quantidade_disponivel=0,
                fabricante="Lab",
                lote="L1",
                data_validade=date(2027, 12, 31),
                embalagem_integra=True,
                condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE,
            )

        # quantidade_disponivel > quantidade_inicial rejeitada
        with self.assertRaises(IntegrityError), transaction.atomic():
            Doacao.objects.create(
                doador=doador,
                nome_medicamento="B",
                principio_ativo="B",
                concentracao_dosagem="10 mg",
                forma_farmaceutica=forma,
                quantidade_inicial=10,
                quantidade_disponivel=11,
                fabricante="Lab",
                lote="L1",
                data_validade=date(2027, 12, 31),
                embalagem_integra=True,
                condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE,
            )

        # embalagem_integra = False rejeitada
        with self.assertRaises(IntegrityError), transaction.atomic():
            Doacao.objects.create(
                doador=doador,
                nome_medicamento="C",
                principio_ativo="C",
                concentracao_dosagem="10 mg",
                forma_farmaceutica=forma,
                quantidade_inicial=10,
                quantidade_disponivel=10,
                fabricante="Lab",
                lote="L1",
                data_validade=date(2027, 12, 31),
                embalagem_integra=False,
                condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE,
            )

        doacao = self._criar_doacao(doador)

        # FotoDoacao ordem inválida / MIME inválido / tamanho > 5MB
        with self.assertRaises(IntegrityError), transaction.atomic():
            FotoDoacao.objects.create(
                doacao=doacao,
                ordem=3,
                arquivo_chave="doacoes/11111111111111111111111111111111.jpg",
                mime_verificado="image/jpeg",
                tamanho_bytes=100,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            FotoDoacao.objects.create(
                doacao=doacao,
                ordem=1,
                arquivo_chave="doacoes/22222222222222222222222222222222.pdf",
                mime_verificado="application/pdf",
                tamanho_bytes=100,
            )

        FotoDoacao.objects.create(
            doacao=doacao,
            ordem=1,
            arquivo_chave="doacoes/33333333333333333333333333333333.jpg",
            mime_verificado="image/jpeg",
            tamanho_bytes=1024,
        )
        # Unicidade (doacao, ordem)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FotoDoacao.objects.create(
                doacao=doacao,
                ordem=1,
                arquivo_chave="doacoes/44444444444444444444444444444444.jpg",
                mime_verificado="image/jpeg",
                tamanho_bytes=1024,
            )

        # DadosRefrigeracaoDoacao exige declaracao=True e faixa não vazia
        with self.assertRaises(IntegrityError), transaction.atomic():
            DadosRefrigeracaoDoacao.objects.create(
                doacao=doacao,
                faixa_temperatura_bula="2 °C a 8 °C",
                declaracao_doador_conservacao=False,
                declaracao_doador_em=timezone.now(),
            )

        # ParametroVencimento singleton id=1 e antecedencia >= 1
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParametroVencimento.objects.create(
                id=2,
                validade_minima_restante_dias=30,
                antecedencia_aviso_dias=15,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParametroVencimento.objects.filter(pk=1).update(antecedencia_aviso_dias=0)

        # on_delete=PROTECT impede excluir doação com foto ou doador com doação
        with self.assertRaises(ProtectedError):
            doacao.delete()
        with self.assertRaises(ProtectedError):
            doador.delete()

    def test_triggers_append_only_em_conferencia_doacao_e_execucao_vencimento(self):
        doador = self._criar_usuario("d1@exemplo.com", "52998224725")
        resp = self._criar_usuario("r1@exemplo.com", "11144477735")
        doacao = self._criar_doacao(doador)

        # Reprovação sem motivo bloqueada por CheckConstraint
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConferenciaDoacao.objects.create(
                doacao=doacao,
                resultado=ResultadoConferenciaDoacao.REPROVADA,
                motivo="   ",
                responsavel=resp,
            )

        conf = ConferenciaDoacao.objects.create(
            doacao=doacao,
            resultado=ResultadoConferenciaDoacao.APROVADA,
            motivo="",
            responsavel=resp,
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            ConferenciaDoacao.objects.filter(pk=conf.pk).update(motivo="adulterado")
        with self.assertRaises(DatabaseError), transaction.atomic():
            ConferenciaDoacao.objects.filter(pk=conf.pk).delete()

        rotina = ExecucaoRotina.objects.create(
            nome_rotina="verificar_vencimento_doacoes",
            iniciada_em=timezone.now(),
            resultado=ResultadoRotina.SUCESSO,
        )
        exec_venc = ExecucaoVencimento.objects.create(
            execucao_rotina=rotina,
            doacoes_verificadas=5,
            doacoes_marcadas_vencidas=1,
            reservas_agendamentos_cancelados=0,
            notificacoes_enviadas=1,
            resultado=ResultadoRotina.SUCESSO,
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            ExecucaoVencimento.objects.filter(pk=exec_venc.pk).update(doacoes_verificadas=99)
        with self.assertRaises(DatabaseError), transaction.atomic():
            ExecucaoVencimento.objects.filter(pk=exec_venc.pk).delete()
