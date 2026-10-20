import hashlib
import json
import unittest
from unittest.mock import MagicMock
from datetime import datetime
from services.documentos_legais import DocumentosLegais
from services.usuarios import Usuarios
from test_integration import app


class DocumentosLegaisTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.db.collection.return_value.where.return_value.stream.return_value = []
        self.acceptance = {'aceite_termos': True, 'ciencia_privacidade': True,
                           'termos_versao': '2026-10-20', 'privacidade_versao': '2026-10-20'}

    def test_cadastro_sem_aceite_nao_grava_conta(self):
        for extra in [{}, {**self.acceptance, 'aceite_termos': 'true'},
                      {**self.acceptance, 'ciencia_privacidade': False},
                      {**self.acceptance, 'termos_versao': 'antiga'}]:
            result, status = Usuarios.cadastrar_usuario(self.db, {
                'nome': 'Pessoa', 'email': 'pessoa@example.test', 'senha': 'senha123', **extra})
            self.assertEqual(status, 400, result)
            self.assertEqual(result['codigo'], 'ACEITE_LEGAL_NECESSARIO')
        self.db.collection.return_value.document.return_value.set.assert_not_called()

    def test_registro_usa_horario_e_hash_do_servidor(self):
        result, status = Usuarios.cadastrar_usuario(self.db, {
            'nome': 'Pessoa', 'email': 'pessoa@example.test', 'senha': 'senha123',
            **self.acceptance, 'registrado_em': 'falso', 'termos_sha256': 'falso'})
        self.assertEqual(status, 201, result)
        saved = self.db.collection.return_value.document.return_value.set.call_args.args[0]
        record = saved['aceite_legal']
        self.assertEqual(saved['historico_aceites_legais'], [record])
        self.assertIsNotNone(datetime.fromisoformat(record['registrado_em']).tzinfo)
        self.assertEqual(record['termos_sha256'], DocumentosLegais.documentos()['termos']['sha256'])

    def test_hash_representa_documento_publicado(self):
        for document in DocumentosLegais.documentos().values():
            content = dict(document)
            digest = content.pop('sha256')
            self.assertEqual(digest, hashlib.sha256(json.dumps(
                content, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest())

    def test_documentos_publicos_e_aceite_exige_autenticacao(self):
        client = app.test_client()
        response = client.get('/api/usuarios/documentos-legais')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), DocumentosLegais.documentos())
        self.assertEqual(client.post('/api/usuarios/aceite-legal', json=self.acceptance).status_code, 401)

    def test_perfil_nao_permite_alterar_prova_do_aceite(self):
        for field in ['aceite_legal', 'historico_aceites_legais']:
            self.assertEqual(Usuarios._validar_campos_edicao({field: {}})[1], 400)

    def test_repetir_aceite_nao_cria_historico_duplicado(self):
        record = DocumentosLegais.validar_aceite(self.acceptance)
        ref = self.db.collection.return_value.document.return_value
        ref.get.return_value.to_dict.return_value = {'aceite_legal': record}
        result, status = DocumentosLegais.registrar(self.db, {'id': 'u1'}, self.acceptance)
        self.assertEqual(status, 200)
        self.assertEqual(result['aceite_legal'], record)
        ref.update.assert_not_called()

    def test_formato_invalido_e_conta_ausente_nao_gravam(self):
        for value in [None, [], 'true', True]:
            self.assertEqual(DocumentosLegais.registrar(self.db, {'id': 'u1'}, value)[1], 400)
        ref = self.db.collection.return_value.document.return_value
        ref.get.return_value.exists = False
        self.assertEqual(DocumentosLegais.registrar(self.db, {'id': 'u1'}, self.acceptance)[1], 404)
        ref.update.assert_not_called()

    def test_aceite_existente_so_altera_propria_conta_e_preserva_historico(self):
        result, status = DocumentosLegais.registrar(self.db, {'id': 'u1'}, self.acceptance)
        self.assertEqual(status, 200, result)
        self.db.collection.return_value.document.assert_called_with('u1')
        update = self.db.collection.return_value.document.return_value.update.call_args.args[0]
        self.assertIn('historico_aceites_legais', update)
        self.assertEqual(set(update), {'aceite_legal', 'historico_aceites_legais'})
