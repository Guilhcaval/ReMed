"""Testes de integração e matriz de permissões das views de gestão de usuários (Spec 04)."""

from datetime import date

import pyotp
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from contas.models import DispositivoTotp, EnderecoUsuario, StatusUsuario, Usuario
from nucleo.mixins import SESSAO_CHAVE_2FA_VERIFICADO


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
)
class GestaoUsuariosViewsTest(TestCase):
    def _criar_usuario(
        self,
        *,
        email: str,
        cpf: str,
        nome: str = "Usuário Teste",
        funcoes: tuple[str, ...] = (),
        is_superuser: bool = False,
        ativar_totp: bool = False,
    ) -> tuple[Usuario, str]:
        usuario = Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=nome,
            data_nascimento=date(1990, 8, 15),
            celular="11988887777",
            perfil_doador=True,
            is_superuser=is_superuser,
            is_staff=is_superuser,
            email_confirmado_em=timezone.now(),
        )
        if funcoes:
            grupos = [Group.objects.get_or_create(name=f)[0] for f in funcoes]
            usuario.groups.set(grupos)
        segredo = ""
        if ativar_totp:
            segredo = pyotp.random_base32()
            DispositivoTotp.objects.create(
                usuario=usuario,
                segredo=segredo,
                confirmado_em=timezone.now(),
            )
        return usuario, segredo

    def _logar_com_2fa(self, usuario: Usuario, *, verificado: bool = True) -> None:
        self.client.force_login(usuario)
        sessao = self.client.session
        sessao[SESSAO_CHAVE_2FA_VERIFICADO] = verificado
        sessao.save()

    def test_matriz_permissoes_e_separacao_estrita_por_rota(self):
        """CA-04-07: visitante, cidadão, is_superuser sem função, 2FA e separação de funções."""
        alvo, _ = self._criar_usuario(
            email="alvo@exemplo.com",
            cpf="52998224725",
            nome="Alvo Cidadão",
        )
        EnderecoUsuario.objects.create(
            usuario=alvo,
            cep="01310100",
            logradouro="Rua Sigilosa Confidencial",
            numero="999",
            bairro="Bela Vista",
            municipio="São Paulo",
            estado="SP",
        )

        url_lista = reverse("contas:admin_usuario_lista")
        url_detalhe = reverse("contas:admin_usuario_detalhe", kwargs={"usuario_id": alvo.pk})
        url_status = reverse("contas:admin_usuario_status", kwargs={"usuario_id": alvo.pk})
        url_funcoes = reverse("contas:admin_usuario_funcoes", kwargs={"usuario_id": alvo.pk})
        url_reset = reverse("contas:admin_usuario_resetar_2fa", kwargs={"usuario_id": alvo.pk})

        # 1. Visitante -> 302 para login
        self.assertEqual(self.client.get(url_lista).status_code, 302)

        # 2. Cidadão comum -> 403 em todas as rotas
        cidadao, _ = self._criar_usuario(email="cid@exemplo.com", cpf="11144477735")
        self.client.force_login(cidadao)
        for url in (url_lista, url_detalhe):
            self.assertEqual(self.client.get(url).status_code, 403)
        for url in (url_status, url_funcoes, url_reset):
            self.assertEqual(self.client.post(url).status_code, 403)

        # 3. is_superuser sem função administrativa explícita -> 403 (ADR 0010)
        super_sem_funcao, _ = self._criar_usuario(
            email="super@exemplo.com",
            cpf="12345678909",
            is_superuser=True,
        )
        self._logar_com_2fa(super_sem_funcao, verificado=True)
        self.assertEqual(self.client.get(url_lista).status_code, 403)
        self.assertEqual(self.client.post(url_status).status_code, 403)
        self.assertEqual(self.client.post(url_funcoes).status_code, 403)

        # 4. Admin com conferencia_doacoes apenas -> 403 em todas as rotas
        adm_conf, _ = self._criar_usuario(
            email="conf@exemplo.com",
            cpf="98765432100",
            funcoes=("conferencia_doacoes",),
            ativar_totp=True,
        )
        self._logar_com_2fa(adm_conf, verificado=True)
        self.assertEqual(self.client.get(url_lista).status_code, 403)
        self.assertEqual(self.client.get(url_detalhe).status_code, 403)

        # 5. Admin com gestao_usuarios mas SEM 2FA verificado na sessão -> 302 para 2FA
        adm_usuarios, _ = self._criar_usuario(
            email="adm-u@exemplo.com",
            cpf="71428793860",
            funcoes=("gestao_usuarios",),
            ativar_totp=True,
        )
        self._logar_com_2fa(adm_usuarios, verificado=False)
        resp_sem_2fa = self.client.get(url_lista)
        self.assertEqual(resp_sem_2fa.status_code, 302)
        self.assertIn(reverse("contas:totp_verificar"), resp_sem_2fa["Location"])

        # 6. Admin gestao_usuarios (+ 2FA): lista/detalhe/status OK, 403 em funções e reset 2FA
        self._logar_com_2fa(adm_usuarios, verificado=True)
        resp_lista = self.client.get(url_lista)
        self.assertEqual(resp_lista.status_code, 200)
        self.assertContains(resp_lista, "529.***.***-25")
        self.assertNotContains(resp_lista, "52998224725")
        self.assertNotContains(resp_lista, "529.982.247-25")
        self.assertNotContains(resp_lista, "Rua Sigilosa Confidencial")

        resp_detalhe = self.client.get(url_detalhe)
        self.assertEqual(resp_detalhe.status_code, 200)
        self.assertContains(resp_detalhe, "529.***.***-25")
        self.assertNotContains(resp_detalhe, "52998224725")
        self.assertNotContains(resp_detalhe, "Rua Sigilosa Confidencial")

        # GET nas rotas de mutação -> 405 Method Not Allowed
        self.assertEqual(self.client.get(url_status).status_code, 405)

        # POST status funciona com mensagem literal
        resp_status = self.client.post(
            url_status,
            {"novo_status": StatusUsuario.SUSPENSO, "motivo": "Revisão administrativa"},
            follow=True,
        )
        self.assertEqual(resp_status.status_code, 200)
        self.assertContains(resp_status, "Status do usuário alterado com sucesso")

        # POST funções e resetar 2FA são proibidos (403) para quem só tem gestao_usuarios
        self.assertEqual(self.client.post(url_funcoes).status_code, 403)
        self.assertEqual(self.client.post(url_reset).status_code, 403)

        # 7. Admin gestao_administradores (+ 2FA): lista/detalhe OK, 403 em status, funções OK
        adm_admins, segredo_admins = self._criar_usuario(
            email="adm-a@exemplo.com",
            cpf="39053344705",
            funcoes=("gestao_administradores",),
            ativar_totp=True,
        )
        alvo_ativo, _ = self._criar_usuario(
            email="alvo-ativo@exemplo.com",
            cpf="04224628090",
            nome="Alvo Ativo",
        )
        self._logar_com_2fa(adm_admins, verificado=True)
        self.assertEqual(self.client.get(url_lista).status_code, 200)
        self.assertEqual(self.client.get(url_detalhe).status_code, 200)
        self.assertEqual(self.client.post(url_status).status_code, 403)

        url_funcoes_ativo = reverse(
            "contas:admin_usuario_funcoes", kwargs={"usuario_id": alvo_ativo.pk}
        )
        self.assertEqual(self.client.get(url_funcoes_ativo).status_code, 405)

        codigo_valido = pyotp.TOTP(segredo_admins).now()
        resp_func = self.client.post(
            url_funcoes_ativo,
            {
                "funcoes": ["auditoria"],
                "motivo": "Acesso de leitura à auditoria",
                "codigo_step_up": codigo_valido,
            },
            follow=True,
        )
        self.assertEqual(resp_func.status_code, 200)
        self.assertContains(resp_func, "Funções administrativas atualizadas com sucesso.")
        self.assertTrue(alvo_ativo.groups.filter(name="auditoria").exists())
