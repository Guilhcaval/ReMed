"""Testes unitários dos validadores puros em nucleo/validators.py."""

from datetime import date

from django.test import SimpleTestCase

from nucleo.validators import (
    formatar_celular,
    formatar_cep,
    formatar_cnpj,
    formatar_cpf,
    validar_celular,
    validar_cep,
    validar_cnpj,
    validar_cpf,
    validar_maioridade,
    validar_telefone,
    validar_uf,
)


class ValidatorsTest(SimpleTestCase):
    def test_validar_cpf_valido_com_e_sem_mascara(self):
        self.assertEqual(validar_cpf("529.982.247-25"), "52998224725")
        self.assertEqual(validar_cpf("52998224725"), "52998224725")
        self.assertEqual(formatar_cpf("52998224725"), "529.982.247-25")

    def test_validar_cpf_invalido_e_repetido(self):
        for invalido in ("111.111.111-11", "00000000000", "529.982.247-26", "12345"):
            with self.subTest(cpf=invalido):
                with self.assertRaises(ValueError):
                    validar_cpf(invalido)

    def test_validar_maioridade_limites_exatos(self):
        """CA-01-06: 17 anos e 364 dias rejeitado; 18 anos completos aceito."""
        referencia = date(2026, 11, 23)
        self.assertEqual(
            validar_maioridade(date(2008, 11, 23), referencia=referencia),
            date(2008, 11, 23),
        )
        with self.assertRaises(ValueError):
            validar_maioridade(date(2008, 11, 24), referencia=referencia)
        with self.assertRaises(ValueError):
            validar_maioridade(date(2027, 1, 1), referencia=referencia)

    def test_validar_cep_celular_e_uf(self):
        self.assertEqual(validar_cep("01001-000"), "01001000")
        self.assertEqual(formatar_cep("01001000"), "01001-000")
        with self.assertRaises(ValueError):
            validar_cep("01001")

        self.assertEqual(validar_celular("(11) 98765-4321"), "11987654321")
        self.assertEqual(formatar_celular("11987654321"), "(11) 98765-4321")
        with self.assertRaises(ValueError):
            validar_celular("00999999999")

        self.assertEqual(validar_uf("sp"), "SP")
        with self.assertRaises(ValueError):
            validar_uf("XX")

    def test_validar_cnpj_e_telefone(self):
        self.assertEqual(validar_cnpj("11.222.333/0001-81"), "11222333000181")
        self.assertEqual(formatar_cnpj("11222333000181"), "11.222.333/0001-81")
        for invalido in ("00.000.000/0000-00", "11.222.333/0001-82", "12345"):
            with self.subTest(cnpj=invalido):
                with self.assertRaises(ValueError):
                    validar_cnpj(invalido)

        self.assertEqual(validar_telefone("(11) 3333-4444"), "1133334444")
        with self.assertRaises(ValueError):
            validar_telefone("0033334444")
