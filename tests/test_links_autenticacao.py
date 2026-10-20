import os
import re
import jwt
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
from werkzeug.security import generate_password_hash, check_password_hash
from test_community import FakeDB
from services.verificacao_email import VerificacaoEmail
from services.redefinicao_senha import RedefinicaoSenha
from services.links_autenticacao import link_autenticacao


@patch.dict(os.environ, {'KEY': 'link-tests-only-' * 4})
class LinksAutenticacaoTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.db.collection('usuarios').document('u1').set({
            'email': 'pessoa+teste@example.test', 'nome': 'Pessoa', 'tipo': 'usuario',
            'ativo': True, 'email_confirmado': False, 'versao_auth': 0,
            'senha': generate_password_hash('antiga123')})

    def solicitar(self, recuperacao=False):
        with patch('services.notificacoes.Notificacoes._enviar_email', return_value=({}, 200)) as send:
            service = RedefinicaoSenha.solicitar_redefinicao if recuperacao else VerificacaoEmail.solicitar
            result, status = service(self.db, {'email': 'pessoa+teste@example.test'})
            self.assertEqual(status, 200, result)
            link = re.search(r'https?://\S+', send.call_args.args[2]).group()
        parsed = urlsplit(link)
        self.assertEqual(parsed.query, '')
        params = parse_qs(urlsplit(parsed.fragment).query)
        self.assertEqual(params['email'][0], 'pessoa+teste@example.test')
        return params['token'][0]

    def test_confirmacao_emite_sessao_apenas_uma_vez(self):
        token = self.solicitar()
        result, status = VerificacaoEmail.confirmar(self.db, {
            'email': 'pessoa+teste@example.test', 'token': token, 'iniciar_sessao': True})
        self.assertEqual(status, 200, result)
        claims = jwt.decode(result['token'], os.environ['KEY'], algorithms=['HS256'])
        self.assertEqual(claims['id'], 'u1')
        self.assertEqual(result['email'], 'pessoa+teste@example.test')
        self.assertEqual(VerificacaoEmail.confirmar(self.db, {
            'email': result['email'], 'token': token, 'iniciar_sessao': True})[1], 400)

    def test_confirmacao_expirada_ou_conta_inativa_nao_emite_sessao(self):
        token = self.solicitar()
        record = self.db.data['verificacoes_email/u1']
        record['expira_em'] = datetime.now(timezone.utc) - timedelta(seconds=1)
        result, status = VerificacaoEmail.confirmar(self.db, {
            'email': record['email'], 'token': token, 'iniciar_sessao': True})
        self.assertEqual(status, 400)
        self.assertNotIn('token', result)
        record['expira_em'] = datetime.now(timezone.utc) + timedelta(minutes=5)
        self.db.data['usuarios/u1']['ativo'] = False
        self.assertEqual(VerificacaoEmail.confirmar(self.db, {
            'email': record['email'], 'token': token, 'iniciar_sessao': True})[1], 400)

    def test_recuperacao_exige_nova_senha_e_invalida_sessoes_anteriores(self):
        token = self.solicitar(True)
        self.assertEqual(RedefinicaoSenha.redefinir_senha(self.db, {
            'token': token, 'nova_senha': '123', 'iniciar_sessao': True})[1], 400)
        result, status = RedefinicaoSenha.redefinir_senha(self.db, {
            'token': token, 'nova_senha': 'nova1234', 'iniciar_sessao': True})
        self.assertEqual(status, 200, result)
        user = self.db.data['usuarios/u1']
        self.assertTrue(check_password_hash(user['senha'], 'nova1234'))
        self.assertTrue(user['email_confirmado'])
        claims = jwt.decode(result['token'], os.environ['KEY'], algorithms=['HS256'])
        self.assertEqual(claims['versao_auth'], user['versao_auth'])
        self.assertEqual(claims['versao_auth'], 1)
        self.assertEqual(RedefinicaoSenha.redefinir_senha(self.db, {
            'token': token, 'nova_senha': 'outra1234', 'iniciar_sessao': True})[1], 400)

    def test_link_de_recuperacao_nao_acessa_conta_com_email_alterado(self):
        token = self.solicitar(True)
        self.db.data['usuarios/u1']['email'] = 'novo@example.test'
        result, status = RedefinicaoSenha.redefinir_senha(self.db, {
            'token': token, 'nova_senha': 'nova1234', 'iniciar_sessao': True})
        self.assertEqual(status, 400)
        self.assertNotIn('token', result)

    def test_origem_invalida_nao_gera_link(self):
        for origin in ['javascript:alert(1)', 'http://example.test', 'https://host/?destino=outro']:
            with patch.dict(os.environ, {'APP_PUBLIC_URL': origin}):
                with self.assertRaises(ValueError):
                    link_autenticacao('confirmar-email', 'p@example.test', 'segredo')

    def test_troca_de_senha_invalida_links_emitidos_antes(self):
        confirmation = self.solicitar()
        recovery = self.solicitar(True)
        self.db.data['usuarios/u1']['versao_auth'] = 1
        self.assertEqual(VerificacaoEmail.confirmar(self.db, {
            'email': 'pessoa+teste@example.test', 'token': confirmation, 'iniciar_sessao': True})[1], 400)
        self.assertEqual(RedefinicaoSenha.redefinir_senha(self.db, {
            'token': recovery, 'nova_senha': 'nova1234', 'iniciar_sessao': True})[1], 400)
