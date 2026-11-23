"""Testes unitários de PontoColetaService (Spec 05 / RF005 — CA-05-01 a CA-05-08)."""

from datetime import date, time
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from contas.models import StatusUsuario, Usuario
from notificacoes.models import CanalNotificacao, Notificacao, TipoNotificacao
from nucleo.exceptions import PermissaoNegada, RecursoNaoEncontrado
from nucleo.models import TipoEstabelecimento
from pontos_coleta.exceptions import CnpjJaCadastrado, HorarioInvalido, UltimoResponsavelAtivo
from pontos_coleta.models import (
    PontoColeta,
    PontoColetaResponsavel,
    StatusPontoColeta,
    StatusResponsavelPonto,
)
from pontos_coleta.services import (
    DadosAtualizacaoPonto,
    DadosPontoColeta,
    FiltrosPontoColeta,
    ItemHorario,
    PontoColetaService,
)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PontoColetaServiceTest(TestCase):
    def _criar_usuario(
        self,
        *,
        email: str,
        cpf: str,
        status: str = StatusUsuario.ATIVO,
        confirmado: bool = True,
        funcoes: tuple[str, ...] = (),
    ) -> Usuario:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=f"Nome {email}",
            data_nascimento=date(1990, 3, 15),
            celular="11988887777",
            perfil_doador=True,
            status=status,
            is_active=status == StatusUsuario.ATIVO,
            email_confirmado_em=timezone.now() if confirmado else None,
        )
        if funcoes:
            grupos = [Group.objects.get_or_create(name=f)[0] for f in funcoes]
            usuario.groups.set(grupos)
        return usuario

    def _dados_ponto(self, cnpj: str = "11.222.333/0001-81") -> DadosPontoColeta:
        tipo = TipoEstabelecimento.objects.first()
        return DadosPontoColeta(
            cnpj=cnpj,
            razao_social="Farmácia Central LTDA",
            nome_fantasia="Farmácia Central",
            tipo_estabelecimento_id=tipo.pk,
            email="contato@farmaciacentral.org",
            telefone="(11) 3333-4444",
            possui_refrigeracao=True,
            observacoes="Entrada pela portaria principal.",
            cep="01001-000",
            logradouro="Praça da Sé",
            numero="100",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
        )

    def _horarios_validos(self) -> list[ItemHorario]:
        return [
            ItemHorario(dia_semana=0, hora_abertura=time(8, 0), hora_fechamento=time(12, 0)),
            ItemHorario(dia_semana=0, hora_abertura=time(13, 0), hora_fechamento=time(18, 0)),
        ]

    @patch(
        "nucleo.services.CepService.obter_coordenadas_em_cache",
        return_value=(Decimal("-23.55"), Decimal("-46.63")),
    )
    def test_cadastro_nasce_pendente_grava_auditoria_coordenadas_e_bloqueia_cnpj_duplicado(
        self, _mock_geo
    ):
        """CA-05-01 e CA-05-02."""
        usuario = self._criar_usuario(email="resp@exemplo.com", cpf="52998224725")
        ponto = PontoColetaService.cadastrar(
            usuario,
            self._dados_ponto(),
            self._horarios_validos(),
        )
        self.assertEqual(ponto.status, StatusPontoColeta.PENDENTE_APROVACAO)
        self.assertEqual(ponto.cnpj, "11222333000181")
        self.assertEqual(ponto.latitude_aprox, Decimal("-23.55"))
        self.assertEqual(ponto.longitude_aprox, Decimal("-46.63"))
        self.assertTrue(
            PontoColetaResponsavel.objects.filter(
                ponto_coleta=ponto, usuario=usuario, status=StatusResponsavelPonto.ATIVO
            ).exists()
        )
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="ponto_coleta.cadastrado", entidade_id=str(ponto.pk)
            ).exists()
        )

        # Não aparece na pesquisa pública
        pub = PontoColetaService.pesquisar(None, FiltrosPontoColeta(), apenas_ativos=True)
        self.assertEqual(pub.total_encontrados, 0)

        # CNPJ duplicado rejeitado
        with self.assertRaises(CnpjJaCadastrado):
            PontoColetaService.cadastrar(usuario, self._dados_ponto(), self._horarios_validos())

        # Horário sobreposto rejeitado
        with self.assertRaises(HorarioInvalido):
            PontoColetaService.cadastrar(
                usuario,
                self._dados_ponto(cnpj="27.865.757/0001-02"),
                [
                    ItemHorario(0, time(8, 0), time(14, 0)),
                    ItemHorario(0, time(13, 0), time(18, 0)),
                ],
            )

    @patch(
        "nucleo.services.CepService.obter_coordenadas_em_cache",
        return_value=(Decimal("-23.55"), Decimal("-46.63")),
    )
    def test_editar_endereco_de_ponto_ativo_remete_reaprovacao_e_chama_gancho(self, _mock_geo):
        """CA-05-04: alteração de endereço de ponto ativo devolve a pendente_aprovacao."""
        usuario = self._criar_usuario(email="resp@exemplo.com", cpf="52998224725")
        outro = self._criar_usuario(email="outro@exemplo.com", cpf="11144477735")
        ponto = PontoColetaService.cadastrar(usuario, self._dados_ponto(), self._horarios_validos())
        PontoColeta.objects.filter(pk=ponto.pk).update(status=StatusPontoColeta.ATIVO)

        tipo = TipoEstabelecimento.objects.first()
        dados_edicao = DadosAtualizacaoPonto(
            razao_social="Farmácia Central LTDA",
            nome_fantasia="Farmácia Central Nova",
            tipo_estabelecimento_id=tipo.pk,
            email="novo@farmacia.org",
            telefone="1133334444",
            possui_refrigeracao=True,
            observacoes="",
            cep="01310100",
            logradouro="Avenida Paulista",
            numero="200",
            bairro="Bela Vista",
            municipio="São Paulo",
            estado="SP",
        )

        # Outro usuário sem vínculo ativo -> 404 (RecursoNaoEncontrado)
        with self.assertRaises(RecursoNaoEncontrado):
            PontoColetaService.atualizar(ponto.pk, outro, dados_edicao, self._horarios_validos())

        acionados: list[int] = []
        resultado = PontoColetaService.atualizar(
            ponto.pk,
            usuario,
            dados_edicao,
            self._horarios_validos(),
            cancelador_agendamentos_futuros=lambda p: acionados.append(p.pk),
        )
        self.assertTrue(resultado.remetido_reaprovacao)
        self.assertEqual(resultado.ponto.status, StatusPontoColeta.PENDENTE_APROVACAO)
        self.assertEqual(resultado.ponto.cnpj, "11222333000181")
        self.assertEqual(acionados, [ponto.pk])
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="ponto_coleta.remetido_reaprovacao", entidade_id=str(ponto.pk)
            ).exists()
        )

    @patch("nucleo.services.CepService.obter_coordenadas_em_cache", return_value=(None, None))
    def test_convite_anti_enumeracao_aceite_desvinculo_e_inativacao_voluntaria(self, _mock_geo):
        """CA-05-06 e CA-05-08."""
        resp1 = self._criar_usuario(email="resp1@exemplo.com", cpf="52998224725")
        resp2 = self._criar_usuario(email="resp2@exemplo.com", cpf="11144477735")
        ponto = PontoColetaService.cadastrar(resp1, self._dados_ponto(), self._horarios_validos())

        # Anti-enumeração: identificador inexistente retorna False sem lançar erro revelador
        self.assertFalse(
            PontoColetaService.convidar_responsavel(ponto.pk, resp1, "naoexiste@exemplo.com")
        )

        # Convite válido nasce convite_pendente (sem acesso ainda) e notifica seguranca_conta
        self.assertTrue(
            PontoColetaService.convidar_responsavel(ponto.pk, resp1, "resp2@exemplo.com")
        )
        with self.assertRaises(RecursoNaoEncontrado):
            PontoColetaService.obter_para_responsavel(ponto.pk, resp2)
        self.assertTrue(
            Notificacao.objects.filter(
                destinatario=resp2,
                tipo=TipoNotificacao.SEGURANCA_CONTA,
                canal=CanalNotificacao.PLATAFORMA,
            ).exists()
        )

        # Não pode desvincular único responsável ativo
        vinculo_resp1 = PontoColetaResponsavel.objects.get(ponto_coleta=ponto, usuario=resp1)
        with self.assertRaises(UltimoResponsavelAtivo):
            PontoColetaService.desvincular_responsavel(ponto.pk, resp1, vinculo_resp1.pk)

        # Após aceite, resp2 acessa normalmente e resp1 pode ser desvinculado
        convite = PontoColetaResponsavel.objects.get(ponto_coleta=ponto, usuario=resp2)
        PontoColetaService.responder_convite(convite.pk, resp2, aceitar=True)
        self.assertEqual(PontoColetaService.obter_para_responsavel(ponto.pk, resp2).pk, ponto.pk)
        PontoColetaService.desvincular_responsavel(ponto.pk, resp2, vinculo_resp1.pk)
        with self.assertRaises(RecursoNaoEncontrado):
            PontoColetaService.obter_para_responsavel(ponto.pk, resp1)

        # Inativação voluntária pelo responsável ativo com gancho
        PontoColeta.objects.filter(pk=ponto.pk).update(status=StatusPontoColeta.ATIVO)
        acionados: list[int] = []
        inativado = PontoColetaService.inativar_pelo_responsavel(
            ponto.pk,
            resp2,
            cancelador_agendamentos_futuros=lambda p: acionados.append(p.pk),
        )
        self.assertEqual(inativado.status, StatusPontoColeta.INATIVO)
        self.assertEqual(acionados, [ponto.pk])

    @patch("nucleo.services.CepService.obter_coordenadas_em_cache", return_value=(None, None))
    def test_alterar_cnpj_exclusivo_aprovacao_pontos_coleta(self, _mock_geo):
        """CA-05-05."""
        resp = self._criar_usuario(email="resp@exemplo.com", cpf="52998224725")
        admin_outro = self._criar_usuario(
            email="adm-u@exemplo.com", cpf="11144477735", funcoes=("gestao_usuarios",)
        )
        admin_pontos = self._criar_usuario(
            email="adm-p@exemplo.com", cpf="12345678909", funcoes=("aprovacao_pontos_coleta",)
        )
        ponto = PontoColetaService.cadastrar(resp, self._dados_ponto(), self._horarios_validos())

        with self.assertRaises(PermissaoNegada):
            PontoColetaService.alterar_cnpj(
                admin_outro, ponto.pk, "27.865.757/0001-02", "Correção de digitação"
            )

        atualizado = PontoColetaService.alterar_cnpj(
            admin_pontos, ponto.pk, "27.865.757/0001-02", "Correção conforme cartão CNPJ"
        )
        self.assertEqual(atualizado.cnpj, "27865757000102")
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao="ponto_coleta.cnpj_alterado", entidade_id=str(ponto.pk), ator=admin_pontos
            ).exists()
        )
