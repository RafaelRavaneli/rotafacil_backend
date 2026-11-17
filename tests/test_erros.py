import unittest

from services.erros import erro_interno
from services.favoritos import Favoritos


class BancoComFalha:
    """Simula o Firestore lançando um erro com detalhe interno."""

    def collection(self, _nome):
        raise RuntimeError('detalhe interno: credencial projects/segredo')


class ErroInternoTests(unittest.TestCase):
    def test_resposta_generica_sem_detalhe_da_excecao(self):
        try:
            raise RuntimeError('caminho /srv/segredo')
        except RuntimeError:
            with self.assertLogs('rotafacil', level='ERROR') as log:
                corpo, status = erro_interno('Erro ao listar favoritos')
        self.assertEqual(status, 500)
        self.assertEqual(corpo, {'erro': 'Erro ao listar favoritos. Tente novamente em instantes.'})
        self.assertIn('caminho /srv/segredo', '\n'.join(log.output))

    def test_status_personalizado(self):
        try:
            raise TimeoutError('timeout')
        except TimeoutError:
            with self.assertLogs('rotafacil', level='ERROR'):
                _, status = erro_interno('Erro ao consultar serviço', 502)
        self.assertEqual(status, 502)

    def test_servico_nao_expoe_excecao_ao_cliente(self):
        with self.assertLogs('rotafacil', level='ERROR'):
            corpo, status = Favoritos.listar_favoritos(BancoComFalha(), 'usuario-1')
        self.assertEqual(status, 500)
        self.assertNotIn('segredo', corpo['erro'])
        self.assertNotIn('credencial', corpo['erro'])


if __name__ == '__main__':
    unittest.main()
