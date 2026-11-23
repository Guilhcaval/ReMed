"""Testes unitários dos formulários do app contas (Spec 01 / RF001)."""

from datetime import date, timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from contas.forms import (
    MSG_INCORRETO_PREFIXO,
    MSG_OBRIGATORIO_RESUMO,
    UsuarioCadastroForm,
    UsuarioPerfilEditarForm,
)


def _dados_cadastro_validos(**sobrescritas) -> dict:
    base = {
        "nome_completo": "Maria Aparecida Silva",
        "cpf": "529.982.247-25",
        "data_nascimento": "15/05/1990",
        "email": "Maria@Exemplo.com",
        "celular": "(11) 98765-4321",
        "senha": "Rm3d!9xQ",
        "perfil_doador": True,
        "perfil_solicitante": False,
        "perfil_cuidador": False,
        "cep": "01001-000",
        "logradouro": "Praça da Sé",
        "numero": "100",
        "bairro": "Sé",
        "municipio": "São Paulo",
        "estado": "SP",
        "complemento": "Apto 12",
        "aceite_termos": True,
    }
    base.update(sobrescritas)
    return base


class ContasFormsTest(SimpleTestCase):
    def test_cadastro_valido_normaliza_campos(self):
        form = UsuarioCadastroForm(data=_dados_cadastro_validos())
        self.assertTrue(form.is_valid(), form.errors)
        dados = form.para_dados()
        self.assertEqual(dados.cpf, "52998224725")
        self.assertEqual(dados.email, "maria@exemplo.com")
        self.assertEqual(dados.celular, "11987654321")
        self.assertEqual(dados.endereco.cep, "01001000")

    def test_campos_obrigatorios_vazios_exibem_mensagem_literal(self):
        """CA-01-02: campos vazios, sem perfil ou sem termos -> mensagem literal."""
        form = UsuarioCadastroForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn(MSG_OBRIGATORIO_RESUMO, form.mensagens_resumo_erros())

        form_sem_perfil = UsuarioCadastroForm(data=_dados_cadastro_validos(perfil_doador=False))
        self.assertFalse(form_sem_perfil.is_valid())
        self.assertIn(MSG_OBRIGATORIO_RESUMO, form_sem_perfil.mensagens_resumo_erros())

        form_sem_termos = UsuarioCadastroForm(data=_dados_cadastro_validos(aceite_termos=False))
        self.assertFalse(form_sem_termos.is_valid())
        self.assertIn(MSG_OBRIGATORIO_RESUMO, form_sem_termos.mensagens_resumo_erros())

    def test_limites_nome_completo(self):
        """CA-01-03: 2 e 121 rejeitados; 3 e 120 aceitos."""
        for nome_invalido in ("Ab", "A" * 121):
            form = UsuarioCadastroForm(data=_dados_cadastro_validos(nome_completo=nome_invalido))
            self.assertFalse(form.is_valid())
            self.assertIn(MSG_INCORRETO_PREFIXO, form.errors["nome_completo"][0])

        for nome_valido in ("Ana", "A" * 120):
            form = UsuarioCadastroForm(data=_dados_cadastro_validos(nome_completo=nome_valido))
            self.assertTrue(form.is_valid(), form.errors)

    def test_cpf_invalido_e_repetido_rejeitados(self):
        """CA-01-04."""
        for cpf_invalido in ("111.111.111-11", "529.982.247-00"):
            form = UsuarioCadastroForm(data=_dados_cadastro_validos(cpf=cpf_invalido))
            self.assertFalse(form.is_valid())
            self.assertIn(MSG_INCORRETO_PREFIXO, form.errors["cpf"][0])

    def test_limites_maioridade(self):
        """CA-01-06: 17 anos e 364 dias rejeitado; 18 anos completos aceito."""
        hoje = timezone.localdate()
        dezoito_exatos = date(hoje.year - 18, hoje.month, hoje.day)
        um_dia_menos = dezoito_exatos + timedelta(days=1)

        form_menor = UsuarioCadastroForm(
            data=_dados_cadastro_validos(data_nascimento=um_dia_menos.strftime("%d/%m/%Y"))
        )
        self.assertFalse(form_menor.is_valid())
        self.assertIn(MSG_INCORRETO_PREFIXO, form_menor.errors["data_nascimento"][0])

        form_maior = UsuarioCadastroForm(
            data=_dados_cadastro_validos(data_nascimento=dezoito_exatos.strftime("%d/%m/%Y"))
        )
        self.assertTrue(form_maior.is_valid(), form_maior.errors)

    def test_senha_curta_e_validadores_django(self):
        """CA-01-08 + acréscimo da especificação (validadores de senha do Django)."""
        form_curta = UsuarioCadastroForm(data=_dados_cadastro_validos(senha="Rm3d!9x"))
        self.assertFalse(form_curta.is_valid())
        self.assertIn(MSG_INCORRETO_PREFIXO, form_curta.errors["senha"][0])

        form_numerica = UsuarioCadastroForm(data=_dados_cadastro_validos(senha="12345678"))
        self.assertFalse(form_numerica.is_valid())
        self.assertIn(MSG_INCORRETO_PREFIXO, form_numerica.errors["senha"][0])

        form_valida = UsuarioCadastroForm(data=_dados_cadastro_validos(senha="Rm3d!9xQ"))
        self.assertTrue(form_valida.is_valid(), form_valida.errors)

    def test_campos_proibidos_nao_expostos_nos_formularios(self):
        proibidos = {"status", "is_staff", "is_superuser", "groups", "email_confirmado_em"}
        self.assertTrue(proibidos.isdisjoint(UsuarioCadastroForm.base_fields.keys()))
        self.assertTrue(
            (proibidos | {"cpf"}).isdisjoint(UsuarioPerfilEditarForm.base_fields.keys())
        )
