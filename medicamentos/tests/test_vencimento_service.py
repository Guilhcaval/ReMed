"""Testes unitários e de rotina agendada de VencimentoService (Spec 11 / RF012 / ADR 0014)."""

from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from contas.models import Usuario
from medicamentos.exceptions import DoacaoIndisponivel, DoacaoVencidaIrreversivel
from medicamentos.models import (
    CondicaoConservacao,
    Doacao,
    ExecucaoVencimento,
    ParametroVencimento,
    StatusDoacao,
)
from medicamentos.services import (
    ResultadoCancelamentoCorrespondencia,
    VencimentoService,
)
from notificacoes.models import Notificacao, TipoNotificacao
from nucleo.exceptions import PermissaoNegada
from nucleo.models import ExecucaoRotina, FormaFarmaceutica, ResultadoRotina


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class VencimentoServiceTest(TestCase):
    def setUp(self):
        self.hoje = date(2026, 11, 24)
        self.forma = FormaFarmaceutica.objects.first()
        self.doador = self._criar_usuario("doador@exemplo.com", "52998224725")
        self.solicitante = self._criar_usuario("sol@exemplo.com", "11144477735")
        self.admin_param = self._criar_usuario(
            "param@exemplo.com", "12345678909", funcoes=("metricas_e_parametros",)
        )
        self.admin_gestao = self._criar_usuario(
            "gest@exemplo.com", "71428793860", funcoes=("gestao_administradores",)
        )

    def _criar_usuario(self, email: str, cpf: str, *, funcoes: tuple[str, ...] = ()) -> Usuario:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=f"Usuário {email}",
            data_nascimento=date(1990, 5, 10),
            celular="11988887777",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )
        if funcoes:
            grupos = [Group.objects.get_or_create(name=f)[0] for f in funcoes]
            usuario.groups.set(grupos)
        return usuario

    def _criar_doacao(self, *, status: str, dias_validade: int, nome: str = "Med") -> Doacao:
        return Doacao.objects.create(
            doador=self.doador,
            nome_medicamento=nome,
            principio_ativo=nome,
            concentracao_dosagem="500 mg",
            forma_farmaceutica=self.forma,
            quantidade_inicial=10,
            quantidade_disponivel=10,
            fabricante="EMS",
            lote="LV1",
            data_validade=self.hoje + timedelta(days=dias_validade),
            embalagem_integra=True,
            condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE,
            status=status,
        )

    def test_rotina_diaria_vence_abaixo_do_minimo_avisa_previamente_e_eh_idempotente(self):
        """CA-11-01 e CA-11-02."""
        # Corte padrão = hoje + 30 dias; aviso = corte + 15 dias (hoje + 30..45)
        d_reservada_vencer = self._criar_doacao(
            status=StatusDoacao.RESERVADO, dias_validade=20, nome="Reservado Curto"
        )
        d_prestes_vencer = self._criar_doacao(
            status=StatusDoacao.DISPONIVEL, dias_validade=40, nome="Quase Vencendo"
        )
        d_entregue_antiga = self._criar_doacao(
            status=StatusDoacao.ENTREGUE, dias_validade=-10, nome="Já Entregue"
        )

        def fake_cancelador(doacao: Doacao, *, motivo: str):
            _ = motivo
            if doacao.pk == d_reservada_vencer.pk:
                return ResultadoCancelamentoCorrespondencia(
                    cancelados=1, solicitantes_notificar=(self.solicitante,)
                )
            return ResultadoCancelamentoCorrespondencia()

        res1 = VencimentoService.executar_rotina_diaria(
            referencia=self.hoje, cancelador_correspondencias=fake_cancelador
        )
        self.assertEqual(res1.resultado, ResultadoRotina.SUCESSO)
        self.assertEqual(res1.doacoes_marcadas_vencidas, 1)
        self.assertEqual(res1.reservas_agendamentos_cancelados, 1)
        self.assertEqual(res1.avisos_enviados, 1)

        d_reservada_vencer.refresh_from_db()
        d_prestes_vencer.refresh_from_db()
        d_entregue_antiga.refresh_from_db()
        self.assertEqual(d_reservada_vencer.status, StatusDoacao.VENCIDO)
        self.assertEqual(d_prestes_vencer.status, StatusDoacao.DISPONIVEL)
        self.assertIsNotNone(d_prestes_vencer.aviso_vencimento_enviado_em)
        self.assertEqual(d_entregue_antiga.status, StatusDoacao.ENTREGUE)

        # Notificação de vencimento contém orientação de descarte sanitário (RNF11)
        notif_doador = Notificacao.objects.filter(
            destinatario=self.doador, tipo=TipoNotificacao.DOACAO_VENCIDA
        ).first()
        self.assertIsNotNone(notif_doador)
        self.assertIn("legislação sanitária", notif_doador.mensagem)
        self.assertTrue(
            Notificacao.objects.filter(
                destinatario=self.solicitante, tipo=TipoNotificacao.DOACAO_VENCIDA
            ).exists()
        )

        # Segunda execução no mesmo dia é idempotente (não reenvia aviso nem vence de novo)
        res2 = VencimentoService.executar_rotina_diaria(
            referencia=self.hoje, cancelador_correspondencias=fake_cancelador
        )
        self.assertEqual(res2.doacoes_marcadas_vencidas, 0)
        self.assertEqual(res2.avisos_enviados, 0)

    def test_validacao_tempo_real_e_irreversibilidade_de_vencido(self):
        """CA-11-03 e CA-11-04 (irreversibilidade)."""
        d_hoje_curta = self._criar_doacao(status=StatusDoacao.DISPONIVEL, dias_validade=5)
        with self.assertRaises(DoacaoIndisponivel):
            VencimentoService.verificar_ou_vencer_doacao(d_hoje_curta.pk, referencia=self.hoje)
        d_hoje_curta.refresh_from_db()
        self.assertEqual(d_hoje_curta.status, StatusDoacao.VENCIDO)

        with self.assertRaises(DoacaoVencidaIrreversivel):
            VencimentoService.impedir_reativacao_vencida(d_hoje_curta)

    def test_parcial_e_falha_geram_alerta_operacional_e_ate_3_retentativas_de_15_min(self):
        """CA-11-04 (alerta + retries ADR 0014 / Spec 11)."""
        d1 = self._criar_doacao(status=StatusDoacao.DISPONIVEL, dias_validade=5, nome="Med 1")
        d2 = self._criar_doacao(status=StatusDoacao.DISPONIVEL, dias_validade=5, nome="Med 2")

        def falhar_no_primeiro(doacao: Doacao):
            if doacao.pk == d1.pk:
                raise RuntimeError("Erro pontual simulado")

        res_parcial = VencimentoService.executar_rotina_diaria(
            referencia=self.hoje, processador_item_vencido=falhar_no_primeiro
        )
        self.assertEqual(res_parcial.resultado, ResultadoRotina.PARCIAL)
        d2.refresh_from_db()
        self.assertEqual(d2.status, StatusDoacao.VENCIDO)
        self.assertTrue(
            Notificacao.objects.filter(
                destinatario=self.admin_gestao, tipo=TipoNotificacao.ALERTA_OPERACIONAL
            ).exists()
        )

        # Política de 1 + 3 retentativas com intervalo de 900 s (15 min)
        esperas: list[float] = []
        tentativas_vistas: list[int] = []

        def executor_sempre_falha(*, referencia, cancelador_correspondencias, tentativa):
            _ = (referencia, cancelador_correspondencias)
            tentativas_vistas.append(tentativa)
            rot = ExecucaoRotina.objects.create(
                nome_rotina="verificar_vencimento_doacoes",
                iniciada_em=timezone.now(),
                finalizada_em=timezone.now(),
                tentativa=tentativa,
                resultado=ResultadoRotina.FALHA,
            )
            ev = ExecucaoVencimento.objects.create(
                execucao_rotina=rot,
                resultado=ResultadoRotina.FALHA,
            )
            from medicamentos.services import ResultadoExecucaoVencimento

            return ResultadoExecucaoVencimento(rot, ev, 0, 0, 0, 0, 0, ResultadoRotina.FALHA)

        resultados = VencimentoService.executar_com_retentativas(
            max_retentativas=3,
            intervalo_segundos=900,
            sleep_fn=esperas.append,
            executor=executor_sempre_falha,
        )
        self.assertEqual(len(resultados), 4)
        self.assertEqual(tentativas_vistas, [1, 2, 3, 4])
        self.assertEqual(esperas, [900, 900, 900])

    def test_parametros_restritos_a_metricas_e_parametros_e_comando_respeita_lock(self):
        """CA-11-05 e lock pg_try_advisory_lock no comando."""
        with self.assertRaises(PermissaoNegada):
            VencimentoService.atualizar_parametros(
                self.admin_gestao, validade_minima_restante_dias=45, antecedencia_aviso_dias=20
            )

        param = VencimentoService.atualizar_parametros(
            self.admin_param, validade_minima_restante_dias=45, antecedencia_aviso_dias=20
        )
        self.assertEqual(param.validade_minima_restante_dias, 45)
        self.assertEqual(param.antecedencia_aviso_dias, 20)
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="parametro_vencimento.atualizado", ator=self.admin_param
            ).exists()
        )
        ParametroVencimento.objects.filter(pk=1).update(
            validade_minima_restante_dias=30, antecedencia_aviso_dias=15
        )

        saida = StringIO()
        call_command("verificar_vencimento_doacoes", "--max-retentativas=0", stdout=saida)
        self.assertIn("Rotina concluída", saida.getvalue())

        # Lock ocupado encerra sem duplicar
        saida_lock = StringIO()
        with patch(
            "medicamentos.management.commands.verificar_vencimento_doacoes.adquirir_lock_rotina"
        ) as m_lock:
            m_lock.return_value.__enter__.return_value = False
            call_command("verificar_vencimento_doacoes", stdout=saida_lock)
        self.assertIn("já está em execução", saida_lock.getvalue())
