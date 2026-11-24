"""Testes unitários e de concorrência de ConferenciaDoacaoService (Spec 10 / RF011)."""

import threading
from datetime import date, timedelta

from django.contrib.auth.models import Group
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from contas.models import Usuario
from medicamentos.exceptions import MotivoReprovacaoObrigatorio, ValidadeDoacaoInvalida
from medicamentos.models import (
    CondicaoConservacao,
    ConferenciaDoacao,
    Doacao,
    ResultadoConferenciaDoacao,
    StatusDoacao,
)
from medicamentos.services import ConferenciaDoacaoService
from notificacoes.models import Notificacao, TipoNotificacao
from nucleo.exceptions import ConflitoConcorrencia, PermissaoNegada
from nucleo.models import FormaFarmaceutica


def _criar_usuario_com_funcoes(email: str, cpf: str, funcoes: tuple[str, ...] = ()) -> Usuario:
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


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class ConferenciaDoacaoServiceTest(TestCase):
    def setUp(self):
        self.hoje = date(2026, 11, 24)
        self.forma = FormaFarmaceutica.objects.first()
        self.doador = _criar_usuario_com_funcoes("doador@exemplo.com", "52998224725")
        self.conferente = _criar_usuario_com_funcoes(
            "conf@exemplo.com", "11144477735", ("conferencia_doacoes",)
        )
        self.outro_admin = _criar_usuario_com_funcoes(
            "adm@exemplo.com", "12345678909", ("gestao_usuarios",)
        )

    def _criar_doacao(self, *, dias_validade: int = 90) -> Doacao:
        return Doacao.objects.create(
            doador=self.doador,
            nome_medicamento="Amoxicilina",
            principio_ativo="Amoxicilina",
            concentracao_dosagem="500 mg",
            forma_farmaceutica=self.forma,
            quantidade_inicial=21,
            quantidade_disponivel=21,
            fabricante="Medley",
            lote="L99",
            data_validade=self.hoje + timedelta(days=dias_validade),
            embalagem_integra=True,
            condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE,
            status=StatusDoacao.EM_ANALISE,
        )

    def test_aprovacao_disponibiliza_notifica_audita_e_dispara_gancho(self):
        """CA-10-01."""
        doacao = self._criar_doacao(dias_validade=60)
        acionadas: list[int] = []

        conf = ConferenciaDoacaoService.registrar_conferencia(
            self.conferente,
            doacao.pk,
            ResultadoConferenciaDoacao.APROVADA,
            referencia=self.hoje,
            acionador_correspondencia=lambda d: acionadas.append(d.pk),
        )
        doacao.refresh_from_db()
        self.assertEqual(doacao.status, StatusDoacao.DISPONIVEL)
        self.assertEqual(conf.resultado, ResultadoConferenciaDoacao.APROVADA)
        self.assertEqual(acionadas, [doacao.pk])
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="doacao.aprovada", entidade_id=str(doacao.pk), ator=self.conferente
            ).exists()
        )
        self.assertTrue(
            Notificacao.objects.filter(
                destinatario=self.doador, tipo=TipoNotificacao.DOACAO_CONFERIDA
            ).exists()
        )

    def test_reprovacao_exige_motivo_e_notifica_doador(self):
        """CA-10-02."""
        doacao = self._criar_doacao(dias_validade=60)
        with self.assertRaises(MotivoReprovacaoObrigatorio):
            ConferenciaDoacaoService.registrar_conferencia(
                self.conferente,
                doacao.pk,
                ResultadoConferenciaDoacao.REPROVADA,
                motivo="   ",
                referencia=self.hoje,
            )

        ConferenciaDoacaoService.registrar_conferencia(
            self.conferente,
            doacao.pk,
            ResultadoConferenciaDoacao.REPROVADA,
            motivo="Foto ilegível da data de validade.",
            referencia=self.hoje,
        )
        doacao.refresh_from_db()
        self.assertEqual(doacao.status, StatusDoacao.REPROVADO)
        notif = Notificacao.objects.filter(
            destinatario=self.doador, tipo=TipoNotificacao.DOACAO_CONFERIDA
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("Foto ilegível", notif.mensagem)

    def test_bloqueio_validade_abaixo_do_minimo_transicao_vencida_e_permissao(self):
        """CA-10-03 e CA-10-04 (permissão)."""
        doacao_curta = self._criar_doacao(dias_validade=10)
        with self.assertRaises(ValidadeDoacaoInvalida):
            ConferenciaDoacaoService.registrar_conferencia(
                self.conferente,
                doacao_curta.pk,
                ResultadoConferenciaDoacao.APROVADA,
                referencia=self.hoje,
            )

        ConferenciaDoacaoService.marcar_vencida_na_conferencia(
            self.conferente, doacao_curta.pk, referencia=self.hoje
        )
        doacao_curta.refresh_from_db()
        self.assertEqual(doacao_curta.status, StatusDoacao.VENCIDO)
        self.assertTrue(
            Notificacao.objects.filter(
                destinatario=self.doador, tipo=TipoNotificacao.DOACAO_VENCIDA
            ).exists()
        )

        outra = self._criar_doacao(dias_validade=60)
        with self.assertRaises(PermissaoNegada):
            ConferenciaDoacaoService.registrar_conferencia(
                self.outro_admin,
                outra.pk,
                ResultadoConferenciaDoacao.APROVADA,
                referencia=self.hoje,
            )


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class ConferenciaConcorrenciaTest(TransactionTestCase):
    def test_dois_conferentes_simultaneos_nao_gravam_duas_conferencias_conflitantes(self):
        """CA-10-04 sob concorrência real no PostgreSQL (select_for_update)."""
        hoje = date(2026, 11, 24)
        forma, _ = FormaFarmaceutica.objects.get_or_create(nome="Comprimido")
        doador = _criar_usuario_com_funcoes("dc@exemplo.com", "52998224725")
        c1 = _criar_usuario_com_funcoes("c1@exemplo.com", "11144477735", ("conferencia_doacoes",))
        c2 = _criar_usuario_com_funcoes("c2@exemplo.com", "12345678909", ("conferencia_doacoes",))

        doacao = Doacao.objects.create(
            doador=doador,
            nome_medicamento="Dipirona",
            principio_ativo="Dipirona",
            concentracao_dosagem="500 mg",
            forma_farmaceutica=forma,
            quantidade_inicial=10,
            quantidade_disponivel=10,
            fabricante="EMS",
            lote="LC1",
            data_validade=hoje + timedelta(days=90),
            embalagem_integra=True,
            condicao_conservacao=CondicaoConservacao.TEMPERATURA_AMBIENTE,
            status=StatusDoacao.EM_ANALISE,
        )

        barreira = threading.Barrier(2)
        sucessos: list[int] = []
        conflitos: list[str] = []

        def _worker(ator: Usuario, resultado: str, motivo: str):
            connections.close_all()
            try:
                barreira.wait(timeout=5)
                ConferenciaDoacaoService.registrar_conferencia(
                    ator, doacao.pk, resultado, motivo=motivo, referencia=hoje
                )
                sucessos.append(ator.pk)
            except ConflitoConcorrencia as erro:
                conflitos.append(str(erro))
            finally:
                connections.close_all()

        t1 = threading.Thread(target=_worker, args=(c1, ResultadoConferenciaDoacao.APROVADA, ""))
        t2 = threading.Thread(
            target=_worker,
            args=(c2, ResultadoConferenciaDoacao.REPROVADA, "Motivo simultâneo"),
        )
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        self.assertEqual(len(sucessos), 1)
        self.assertEqual(len(conflitos), 1)
        self.assertEqual(ConferenciaDoacao.objects.filter(doacao=doacao).count(), 1)
