import os
import unittest
from unittest.mock import Mock, patch

from services.geocodificacao import Geocodificacao


class GeocodificacaoTests(unittest.TestCase):
    def test_exige_consulta_e_configuracao(self):
        self.assertEqual(Geocodificacao.buscar('x')[1], 400)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Geocodificacao.buscar('Praça da Sé')[1], 503)

    @patch('services.geocodificacao.requests.get')
    def test_busca_retorna_coordenadas_normalizadas(self, get):
        resposta = Mock()
        resposta.json.return_value = {
            'features': [{
                'geometry': {'coordinates': [-46.6333, -23.5505]},
                'properties': {
                    'label': 'Praça da Sé, São Paulo, SP',
                    'locality': 'São Paulo',
                    'region_a': 'SP',
                },
            }],
        }
        get.return_value = resposta
        with patch.dict(os.environ, {'ORS_API_KEY': 'teste'}):
            dados, status = Geocodificacao.buscar('Praça da Sé')
        self.assertEqual(status, 200)
        self.assertEqual(dados[0]['latitude'], -23.5505)
        self.assertEqual(dados[0]['longitude'], -46.6333)
        get.assert_called_once()


if __name__ == '__main__':
    unittest.main()
