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
from werkzeug.security import generate_password_hash, check_password_hash
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
    def test_somente_turista_cria_reserva(self):
        doc = MagicMock()
        doc.exists = True
        doc.id = 'u1'
        with patch('services.autenticacao.firestore.client', return_value=self.db), patch(
                'routes.agendamentos_routes.Agendamentos.agendar_trilha',
                return_value=({'mensagem':'ok'},201)) as agendar:
            self.db.collection.return_value.document.return_value.get.return_value = doc
            for role in ('guia','agencia'):
                doc.to_dict.return_value = {
                    'id':'u1','email':f'{role}@example.test','tipo':role}
                token = Autenticacao.make_token(
                    f'{role}@example.test','u1',role)
                response = self.client.post('/api/agendamentos/', json={
                    'id_trilha':'t1','data_agendada':'2026-12-01'},
                    headers={'Authorization':f'Bearer {token}'})
                self.assertEqual(response.status_code,403)
            doc.to_dict.return_value = {
                'id':'u1','email':'turista@example.test','tipo':'usuario'}
            token = Autenticacao.make_token(
                'turista@example.test','u1','usuario')
            response = self.client.post('/api/agendamentos/', json={
                'id_trilha':'t1','data_agendada':'2026-12-01'},
                headers={'Authorization':f'Bearer {token}'})
            self.assertEqual(response.status_code,201)
            agendar.assert_called_once()

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

    def test_alteracao_de_senha_confere_senha_atual(self):
        ref = self.db.collection.return_value.document.return_value
        ref.get.return_value.exists = True
        ref.get.return_value.to_dict.return_value = {
            'senha': generate_password_hash('senha123')}

        self.assertEqual(Autenticacao.alterar_senha(
            self.db,{'id':'u1'},
            {'senha_atual':'incorreta','nova_senha':'nova123'})[1],401)
        ref.update.assert_not_called()

        result,status=Autenticacao.alterar_senha(
            self.db,{'id':'u1'},
            {'senha_atual':'senha123','nova_senha':'nova123'})
        self.assertEqual(status,200,result)
        nova_hash=ref.update.call_args.args[0]['senha']
        self.assertTrue(check_password_hash(nova_hash,'nova123'))

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
            'tipo':'guia','documento':'52998224725', 'cadastur_numero':'12.345.678/0001-90'})
        self.assertEqual(status, 201, result)
        saved = self.db.collection.return_value.document.return_value.set.call_args.args[0]
        self.assertEqual(saved['documento'], '52998224725')
        self.assertEqual(saved['cadastur_numero'], '12345678000190')
        self.assertFalse(saved['verificado'])

    def test_cadastur_obrigatorio_para_ambos_perfis_sem_exigir_do_turista(self):
        self.db.collection.return_value.where.return_value.stream.return_value = []
        base = {'nome':'Pessoa', 'email':'pessoa@example.test', 'senha':'senha123'}
        for tipo, documento in [('guia','52998224725'), ('agencia','11222333000181')]:
            result, status = Usuarios.cadastrar_usuario(self.db, {**base, 'tipo':tipo, 'documento':documento})
            self.assertEqual(status,400,result)
            self.assertIn('Cadastur',result['erro'])
            result, status = Usuarios.cadastrar_usuario(self.db, {**base, 'tipo':tipo, 'documento':documento, 'cadastur_numero':'123456789', 'cadastur_validade':'2099-12-31'})
            self.assertEqual(status,201,result)
        self.assertEqual(Usuarios.cadastrar_usuario(self.db,base)[1],201)

    def test_cadastro_valida_email_senha_e_documento_do_perfil(self):
        base = {'nome':'Pessoa','senha':'senha123','tipo':'usuario'}
        self.assertEqual(Usuarios.cadastrar_usuario(
            self.db,{**base,'email':'invalido'})[1],400)
        self.assertEqual(Usuarios.cadastrar_usuario(
            self.db,{**base,'email':'pessoa@example.test','senha':'123'})[1],400)
        self.assertEqual(Usuarios.cadastrar_usuario(self.db,{
            **base,'email':'guia@example.test','tipo':'guia',
            'documento':'11222333000181'})[1],400)
        self.assertEqual(Usuarios.cadastrar_usuario(self.db,{
            **base,'email':'agencia@example.test','tipo':'agencia',
            'documento':'52998224725'})[1],400)

    def test_login_nao_revela_conta_ausente_ou_inativa(self):
        query = self.db.collection.return_value.where.return_value
        query.stream.return_value = []
        result,status=Autenticacao.login(
            self.db,{'email':'ausente@example.test','senha':'senha123'})
        self.assertEqual((result,status),({'erro':'Credenciais inválidas'},401))

        doc=MagicMock()
        doc.to_dict.return_value={'ativo':False,
            'senha':generate_password_hash('senha123')}
        query.stream.return_value=[doc]
        result,status=Autenticacao.login(
            self.db,{'email':'inativa@example.test','senha':'senha123'})
        self.assertEqual((result,status),({'erro':'Credenciais inválidas'},401))

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

    @patch.dict(os.environ, {'KEY': 'email-version-key-only-' * 3})
    def test_senha_redefinida_rejeita_jwt_anterior(self):
        doc = MagicMock()
        doc.exists = True
        doc.id = 'u1'
        doc.to_dict.return_value = {'id': 'u1', 'email': 'u@example.test', 'tipo': 'usuario', 'versao_auth': 1}
        self.db.collection.return_value.document.return_value.get.return_value = doc
        token_antigo = Autenticacao.make_token('u@example.test', 'u1', 'usuario', 0)
        token_novo = Autenticacao.make_token('u@example.test', 'u1', 'usuario', 1)
        with patch('services.autenticacao.firestore.client', return_value=self.db), patch('routes.usuarios_routes.bd', self.db):
            response = self.client.get('/api/usuarios/u1', headers={'Authorization': f'Bearer {token_antigo}'})
            self.assertEqual(response.status_code, 401)
            response = self.client.get('/api/usuarios/u1', headers={'Authorization': f'Bearer {token_novo}'})
            self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
