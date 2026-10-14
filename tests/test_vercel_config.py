"""Configuração de hospedagem sem usar credenciais ou Firebase reais."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from models.firebase_config import firebase_credential_source


class VercelConfigTests(unittest.TestCase):
    def test_json_tem_precedencia_e_preserva_quebras_de_linha(self):
        fixture = {'project_id': 'teste', 'private_key': 'valor fictício\nsegunda linha'}
        with patch.dict(os.environ, {
            'FIREBASE_CREDENTIALS_JSON': json.dumps(fixture),
            'FIREBASE_CREDENTIALS_PATH': 'nao-usar.json',
        }):
            self.assertEqual(firebase_credential_source(), fixture)

    def test_erros_nao_expoem_conteudo_da_variavel(self):
        for value in ['segredo-invalido', '[]', 'null', '42']:
            with self.subTest(value=value), patch.dict(os.environ, {'FIREBASE_CREDENTIALS_JSON': value}):
                with self.assertRaisesRegex(ValueError, 'objeto JSON válido') as error:
                    firebase_credential_source()
                self.assertNotIn(value, str(error.exception))

    def test_caminho_local_explicito_continua_funcionando(self):
        with patch.dict(os.environ, {'FIREBASE_CREDENTIALS_JSON': '', 'FIREBASE_CREDENTIALS_PATH': 'arquivo-local.json'}):
            self.assertEqual(firebase_credential_source(), 'arquivo-local.json')

    def test_caminho_padrao_independe_do_diretorio_de_execucao(self):
        with patch.dict(os.environ, {}, clear=True):
            path = Path(firebase_credential_source())
            self.assertTrue(path.is_absolute())
            self.assertEqual(path.name, 'firebase-key.json')


if __name__ == '__main__':
    unittest.main()
