import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Importa a aplicação sem carregar credenciais ou acessar serviços externos.
database = types.ModuleType('models.database')
database.bd = MagicMock()
sys.modules['models.database'] = database
from app import app
from services.autenticacao import Autenticacao
from services.trilhas import Trilhas
from services.agendamentos import Agendamentos
from services.usuarios import Usuarios
from werkzeug.security import generate_password_hash
import jwt


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.db = MagicMock()

    def test_cors_permite_flutter_local(self):
        response = self.client.options('/api/auth/login', headers={
            'Origin': 'http://localhost:8080',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'authorization,content-type',
        })
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'http://localhost:8080')
        self.assertIn('authorization', response.headers['Access-Control-Allow-Headers'].lower())

    def test_cors_nao_libera_origem_arbitraria(self):
        response = self.client.options('/api/auth/login', headers={
            'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'POST'})
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)

    def test_rotas_protegidas_sem_token(self):
        for path in ['/api/trilhas/', '/api/favoritos/', '/api/agendamentos/usuario/u1']:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.get('/api/trilhas/', headers={'Authorization':'   '}).status_code, 401)

    @patch.dict(os.environ, {'KEY': 'test-key-only-' * 4})
    def test_login_usa_id_real_do_documento(self):
        doc = MagicMock()
        doc.id = 'u1'
        doc.to_dict.return_value = {'nome':'Ana','tipo':'usuario',
            'senha':generate_password_hash('senha123')}
        self.db.collection.return_value.where.return_value.stream.return_value = [doc]
        result, status = Autenticacao.login(self.db, {'email':'ana@example.test','senha':'senha123'})
        self.assertEqual(status, 200)
        self.assertEqual(result['id'], 'u1')
        payload = jwt.decode(result['token'], os.environ['KEY'], algorithms=['HS256'])
        self.assertEqual(payload['id'], 'u1')

    @patch.dict(os.environ, {'KEY': 'test-key-only-' * 4})
    def test_token_continua_valido_apos_troca_de_email(self):
        doc = MagicMock()
        doc.exists = True
        doc.id = 'u1'
        doc.to_dict.return_value = {'email':'novo@example.test','tipo':'usuario'}
        token = Autenticacao.make_token('antigo@example.test', 'u1', 'usuario')
        with patch('services.autenticacao.firestore.client', return_value=self.db), patch(
            'routes.trilhas_routes.Trilhas.listar_trilhas', return_value=([], 200)):
            self.db.collection.return_value.document.return_value.get.return_value = doc
            response = self.client.get('/api/trilhas/', headers={'Authorization':f'Bearer {token}'})
        self.assertEqual(response.status_code, 200)

    def test_cadastro_recebe_documento_frontend(self):
        self.db.collection.return_value.where.return_value.stream.return_value = []
        result, status = Usuarios.cadastrar_usuario(self.db, {
            'nome':'Guia','email':'guia@example.test','senha':'senha123',
            'tipo':'guia','documento':'52998224725'})
        self.assertEqual(status, 201, result)
        saved = self.db.collection.return_value.document.return_value.set.call_args.args[0]
        self.assertEqual(saved['documento'], '52998224725')

    def test_trilha_preserva_preco_e_id_do_guia(self):
        result, status = Trilhas.cadastrar_trilha(self.db, {
            'nome':'Trilha','descricao':'Caminho','dificuldade':'Fácil','preco':35},
            {'id':'u1','email':'guia@example.test'})
        self.assertEqual(status, 201, result)
        saved = self.db.collection.return_value.document.return_value.set.call_args.args[0]
        self.assertEqual(saved['id_guia'], 'u1')
        self.assertEqual(saved['preco'], 35)

    def test_exclusao_preserva_documento_e_exige_dono(self):
        ref = self.db.collection.return_value.document.return_value
        ref.get.return_value.exists = True
        ref.get.return_value.to_dict.return_value = {'id_guia':'u1','criado_por':'u1'}
        self.assertEqual(Trilhas.deletar_trilha(self.db, 't1', {'id':'u2'})[1], 403)
        ref.update.assert_not_called()
        self.assertEqual(Trilhas.deletar_trilha(self.db, 't1', {'id':'u1'})[1], 200)
        ref.update.assert_called_once_with({'ativo':False})
        ref.delete.assert_not_called()

    def test_nao_agenda_trilha_desativada(self):
        self.db.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {'ativo':False}
        result, status = Agendamentos.agendar_trilha(self.db, {
            'id_usuario':'u1','id_trilha':'t1','data_agendada':'2026-09-25','valor_pago':35})
        self.assertEqual(status, 409)
        self.db.collection.return_value.document.return_value.set.assert_not_called()

if __name__ == '__main__':
    unittest.main()
