import unittest

from services.cadastur import Cadastur


class CadasturTests(unittest.TestCase):
    def test_normaliza_separadores_sem_afirmar_validade_oficial(self):
        self.assertEqual(Cadastur.normalizar({'cadastur_numero': '12.345.678/0001-90'}),
                         {'cadastur_numero': '12345678000190', 'cadastur_validade': ''})

    def test_rejeita_dados_invalidos(self):
        for dados in [{'cadastur_numero': 'abc'}, {'cadastur_numero': 123},
                      {'cadastur_numero': '1' * 41},
                      {'cadastur_numero': '123', 'cadastur_validade': '2026-02-30'},
                      {'cadastur_validade': '2026-12-31'}]:
            with self.assertRaises(ValueError):
                Cadastur.normalizar(dados)

    def test_aceita_validade_passada_para_registro_de_conta_existente(self):
        self.assertEqual(Cadastur.normalizar({'cadastur_numero': '123',
                                            'cadastur_validade': '2020-01-01'})['cadastur_validade'],
                         '2020-01-01')
