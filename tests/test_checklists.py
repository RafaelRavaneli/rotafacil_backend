import unittest
import os
from copy import deepcopy
from unittest.mock import patch
from test_community import FakeDB, Query, Ref
from test_integration import app
from services.checklists import Checklists
from services.trilhas import Trilhas
from services.autenticacao import Autenticacao
from services.usuarios import Usuarios


class MergeRef(Ref):
    def set(self, data, merge=False):
        if merge:
            previous = deepcopy(self.db.data.get(self.path, {}))
            data = {**previous, **data, 'marcados': {**previous.get('marcados', {}), **data.get('marcados', {})}}
        super().set(data)


class MergeQuery(Query):
    def document(self, id):
        return MergeRef(self.db, self.path+'/'+id)


class ChecklistDB(FakeDB):
    def collection(self, name):
        return MergeQuery(self, name)


class ChecklistTests(unittest.TestCase):
    def setUp(self):
        self.db = ChecklistDB()
        self.user = {'id': 'u1', 'tipo': 'usuario'}
        self.db.collection('trilhas').document('t1').set({
            'itens_obrigatorios': ['Lanterna', ' Água '],
            'itens_recomendados': ['água', 'Boné']})
        for id in ['b1', 'b2']:
            self.db.collection('agendamentos').document(id).set({
                'id_usuario': 'u1', 'id_trilha': 't1', 'status': 'confirmado'})

    def mark(self, label, checked=True, booking='b1', user=None):
        return Checklists.atualizar(self.db, booking, user or self.user,
            {'id_item': Checklists.chave(label), 'marcado': checked})

    def test_itens_obrigatorios_e_legados_recomendados_sem_duplicatas(self):
        data, status = Checklists.obter(self.db, 'b1', self.user)
        self.assertEqual(status, 200)
        self.assertEqual([item['nome'] for item in data['itens']], ['Lanterna', 'Água', 'Boné'])
        self.assertEqual([item['obrigatorio'] for item in data['itens']], [True, True, False])
        self.db.data['trilhas/t1'].pop('itens_obrigatorios')
        self.assertEqual(Checklists.obter(self.db, 'b1', self.user)[0]['total'], 2)

    def test_gravacao_persiste_sem_alterar_roteiro_ou_outra_saida(self):
        before = deepcopy(self.db.data['trilhas/t1'])
        self.assertEqual(self.mark('Lanterna')[1], 200)
        self.assertEqual(self.mark('Boné')[1], 200)
        reloaded = Checklists.obter(self.db, 'b1', self.user)[0]
        self.assertEqual(reloaded['preparados'], 2)
        self.assertEqual(Checklists.obter(self.db, 'b2', self.user)[0]['preparados'], 0)
        self.assertEqual(self.db.data['trilhas/t1'], before)
        self.assertEqual(self.mark('Lanterna', False)[0]['preparados'], 1)
        self.assertNotIn('marcados', self.db.data['agendamentos/b1'])

    def test_outros_turistas_guias_agencias_e_admin_nao_acessam_checklist(self):
        for user in [{'id': 'u2', 'tipo': 'usuario'}, {'id': 'u1', 'tipo': 'guia'},
                     {'id': 'a', 'tipo': 'agencia'}, {'id': 'admin', 'tipo': 'admin'}]:
            self.assertEqual(Checklists.obter(self.db, 'b1', user)[1], 403)
            self.assertEqual(self.mark('Lanterna', user=user)[1], 403)
        self.assertFalse(any(key.startswith('checklists_pessoais/') for key in self.db.data))

    def test_item_inexistente_payload_adulterado_e_marcacao_invalida_rejeitados(self):
        for body in [None, [], {}, {'id_item': 'outro', 'marcado': True}, {'id_item': [], 'marcado': True},
                     {'id_item': Checklists.chave('Lanterna'), 'marcado': 'true'},
                     {'id_item': Checklists.chave('Lanterna'), 'marcado': True, 'id_usuario': 'u2'}]:
            self.assertEqual(Checklists.atualizar(self.db, 'b1', self.user, body)[1], 400)

    def test_reserva_encerrada_apenas_consulta_e_roteiro_ausente_nao_quebra(self):
        self.mark('Lanterna')
        for status in ['cancelado', 'recusado', 'concluido']:
            self.db.data['agendamentos/b1']['status'] = status
            response, code = Checklists.obter(self.db, 'b1', self.user)
            self.assertEqual(code, 200)
            self.assertFalse(response['editavel'])
            self.assertEqual(self.mark('Boné')[1], 409)
        self.db.data.pop('trilhas/t1')
        self.assertEqual(Checklists.obter(self.db, 'b1', self.user)[1], 404)
        self.assertEqual(Checklists.obter(self.db, 'inexistente', self.user)[1], 404)

    def test_alterar_lista_nao_transfere_marcacao_para_item_novo(self):
        self.mark('Lanterna')
        self.db.data['trilhas/t1']['itens_obrigatorios'] = ['Botas', 'lanterna']
        items = Checklists.obter(self.db, 'b1', self.user)[0]['itens']
        self.assertFalse(items[0]['marcado'])
        self.assertTrue(items[1]['marcado'])
        self.db.data['trilhas/t1']['itens_obrigatorios'] = ['Botas']
        self.assertEqual(self.mark('Lanterna')[1], 400)

    def test_roteiro_valida_e_normaliza_listas(self):
        data = {'itens_obrigatorios': [' Água ', 'água'], 'itens_recomendados': [' Boné ' ]}
        self.assertIsNone(Trilhas._validar_campos_publicos(data))
        self.assertEqual(data['itens_obrigatorios'], ['Água'])
        for invalid in ['texto', [1], [''], ['x'*121], ['x']*51]:
            self.assertIsNotNone(Trilhas._validar_campos_publicos({'itens_obrigatorios': invalid}))

    def test_rotas_exigem_sessao(self):
        client = app.test_client()
        for method in [client.get, client.patch]:
            self.assertEqual(method('/api/agendamentos/b1/checklist').status_code, 401)

    def test_falha_de_persistencia_nao_e_reportada_como_sucesso(self):
        with patch.object(MergeRef, 'set', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                self.mark('Lanterna')
        self.assertEqual(Checklists.obter(self.db, 'b1', self.user)[0]['preparados'], 0)

    def test_exclusao_da_conta_remove_somente_seus_checklists(self):
        self.mark('Lanterna')
        self.db.collection('usuarios').document('u1').set({
            'id': 'u1', 'email': 'u1@example.test', 'tipo': 'usuario'})
        for id in ['b1', 'b2']:
            self.db.data['agendamentos/'+id]['status'] = 'concluido'
        self.db.collection('checklists_pessoais').document('outra').set({'id_usuario': 'u2'})
        result, status = Usuarios._excluir_conta(self.db, self.db.collection('usuarios').document('u1').get())
        self.assertEqual(status, 200, result)
        self.assertNotIn('checklists_pessoais/b1', self.db.data)
        self.assertIn('checklists_pessoais/outra', self.db.data)

    @patch.dict(os.environ, {'KEY': 'checklist-tests-only-' * 4})
    def test_api_persiste_recarrega_e_rejeita_outro_usuario(self):
        for id in ['u1', 'u2']:
            self.db.collection('usuarios').document(id).set({
                'id': id, 'email': id+'@example.test', 'tipo': 'usuario', 'ativo': True})
        client = app.test_client()
        with patch('routes.agendamentos_routes.bd', self.db), patch(
                'services.autenticacao.firestore.client', return_value=self.db):
            header = {'Authorization': 'Bearer '+Autenticacao.make_token('u1@example.test', 'u1', 'usuario')}
            response = client.patch('/api/agendamentos/b1/checklist', headers=header,
                json={'id_item': Checklists.chave('Lanterna'), 'marcado': True})
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(client.get('/api/agendamentos/b1/checklist', headers=header).get_json()['preparados'], 1)
            other = {'Authorization': 'Bearer '+Autenticacao.make_token('u2@example.test', 'u2', 'usuario')}
            self.assertEqual(client.get('/api/agendamentos/b1/checklist', headers=other).status_code, 403)
            with patch.object(MergeRef, 'set', side_effect=RuntimeError('offline')):
                response = client.patch('/api/agendamentos/b1/checklist', headers=header,
                    json={'id_item': Checklists.chave('Boné'), 'marcado': True})
                self.assertEqual(response.status_code, 503)
                self.assertIn('Tente novamente', response.get_json()['erro'])
