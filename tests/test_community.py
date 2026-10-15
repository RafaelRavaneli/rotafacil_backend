"""Fluxos multiusuário com armazenamento isolado; nunca usa Firebase real."""
import os
import unittest
from copy import deepcopy
from unittest.mock import patch
from google.api_core.exceptions import AlreadyExists, FailedPrecondition
from test_integration import app
from services.autenticacao import Autenticacao
from services.community import Community, CommunityError, PushDevices
from services.agendamentos import Agendamentos
from services.trilhas import Trilhas


class Snapshot:
    def __init__(self, ref):
        self.reference, self.id = ref, ref.id
        self.data = deepcopy(ref.db.data.get(ref.path))
        self.exists = self.data is not None
        self.update_time = ref.db.versions.get(ref.path, 0)
    def to_dict(self):
        return deepcopy(self.data)


class Ref:
    def __init__(self, db, path):
        self.db, self.path, self.id = db, path, path.split('/')[-1]
    def get(self): return Snapshot(self)
    def collection(self, name): return Query(self.db, self.path+'/'+name)
    def set(self, data):
        self.db.data[self.path] = deepcopy(data)
        self.db.versions[self.path] = self.db.versions.get(self.path, 0)+1
    def create(self, data):
        if self.path in self.db.data: raise AlreadyExists('exists')
        self.set(data)
    def check(self, option):
        if option and option._last_update_time != self.db.versions.get(self.path):
            raise FailedPrecondition('changed')
    def update(self, data, option=None):
        self.check(option)
        self.set({**self.db.data[self.path], **data})
    def delete(self, option=None):
        self.check(option)
        self.db.data.pop(self.path, None)


class Query:
    def __init__(self, db, path, filters=(), order=None, count=None):
        self.db, self.path, self.filters, self.order, self.count = db, path, filters, order, count
    def document(self, id): return Ref(self.db, self.path+'/'+id)
    def where(self, field, op, value):
        return Query(self.db, self.path, (*self.filters, (field, op, value)), self.order, self.count)
    def order_by(self, field, direction=None):
        return Query(self.db, self.path, self.filters, (field, direction), self.count)
    def limit(self, count): return Query(self.db, self.path, self.filters, self.order, count)
    def stream(self):
        rows = [Ref(self.db, path).get() for path in self.db.data if path.rsplit('/', 1)[0] == self.path]
        for field, op, value in self.filters:
            rows = [row for row in rows if (value in row.data.get(field, []) if op == 'array_contains' else row.data.get(field) == value)]
        if self.order: rows.sort(key=lambda row: row.data[self.order[0]], reverse=self.order[1]=='DESCENDING')
        return rows[:self.count] if self.count is not None else rows


class FakeDB:
    def __init__(self): self.data, self.versions = {}, {}
    def collection(self, name): return Query(self, name)
    def batch(self): return Batch()


class Batch:
    def __init__(self): self.items=[]
    def create(self, ref, data): self.items.append((ref,data))
    def commit(self):
        if any(ref.get().exists for ref, _ in self.items): raise AlreadyExists('exists')
        for ref,data in self.items: ref.create(data)


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.users = {id: {'id':id, 'tipo':role, 'nome':id, 'email':id+'@example.test', 'senha':'secret', 'documento':'private'}
                      for id,role in [('t','usuario'),('x','usuario'),('g','guia'),('a','agencia'),('admin','admin')]}
        for id,user in self.users.items(): self.db.collection('usuarios').document(id).set(user)
        self.t,self.g,self.a,self.x = [self.users[id] for id in ('t','g','a','x')]
    def denied(self, status, fn, *args):
        with self.assertRaises(CommunityError) as ctx: fn(*args)
        self.assertEqual(ctx.exception.status,status)
    def test_catalogo_nao_expoe_dados_privados(self):
        guide=Community.guides(self.db)[0]
        self.assertEqual(guide['id'],'g')
        for key in ('senha','email','documento'): self.assertNotIn(key,guide)
        self.denied(400,Community.invite,self.db,self.a,{'id_guia':'g/x'})
    def test_convite_aceite_e_vinculo_da_trilha(self):
        self.denied(403,Community.invite,self.db,self.t,{'id_guia':'g'})
        invite=Community.invite(self.db,self.a,{'id_guia':'g'})
        self.assertFalse(Community.can_assign(self.db,self.a,'g'))
        data={'nome':'Trilha','descricao':'Caminho','dificuldade':'Fácil','id_guia':'g'}
        self.assertEqual(Trilhas.cadastrar_trilha(self.db,data,self.a)[1],403)
        self.denied(403,Community.answer_invitation,self.db,self.a,invite['id'],{'status':'aceito'})
        Community.answer_invitation(self.db,self.g,invite['id'],{'status':'aceito'})
        self.assertTrue(Community.can_assign(self.db,self.a,'g'))
        self.assertEqual(Trilhas.cadastrar_trilha(self.db,data,self.a)[1],201)
        self.denied(409,Community.answer_invitation,self.db,self.g,invite['id'],{'status':'recusado'})
        self.denied(409,Community.invite,self.db,self.a,{'id_guia':'g'})
    def test_push_rotacao_multiplos_dispositivos_e_logout(self):
        for token,device in [('old','web'),('phone','phone'),('new','web')]:
            PushDevices.register(self.db,self.t,{'token':token,'dispositivo_id':device})
        PushDevices.register(self.db,self.x,{'token':'other','dispositivo_id':'web'})
        PushDevices.remove(self.db,self.t,{'dispositivo_id':'web'})
        with patch('services.community.messaging.send',return_value='fake') as send:
            result=PushDevices.send(self.db,'t','Teste','Texto')
            self.assertEqual(result,{'enviados':1,'falhas':0})
            self.assertEqual(send.call_args.args[0].token,'phone')
        self.assertEqual(len(self.db.collection('dispositivos_fcm').stream()),2)
    def test_dashboard_vazio_cancelamentos_e_email_legado(self):
        self.assertEqual(Agendamentos.dashboard_guia(self.db,'g')[0]['total_agendamentos'],0)
        for id,guide,status,value in [('1','g','agendado','10.25'),('2','g@example.test','concluido',20),('3','g','cancelado',90),('4','g','agendado','NaN')]:
            self.db.collection('agendamentos').document(id).set({'id_guia':guide,'status':status,'valor_pago':value})
        result,status=Agendamentos.dashboard_guia(self.db,'g')
        self.assertEqual(status,200);self.assertEqual(result['total_agendamentos'],4)
        self.assertEqual(result['valor_declarado_ativo'],30.25)
        self.assertEqual(result['por_status']['cancelado'],1)
    @patch.dict(os.environ, {'KEY':'test-key-only-'*4})
    def test_rotas_autenticadas_e_push_apenas_propria_conta(self):
        client=app.test_client()
        for path in ['/api/guias','/api/convites-guias','/api/agendamentos/dashboard/g']:
            self.assertEqual(client.get(path).status_code,401)
        def headers(id):
            user=self.users[id]
            return {'Authorization':'Bearer '+Autenticacao.make_token(user['email'],id,user['tipo'])}
        with patch('services.autenticacao.firestore.client',return_value=self.db), patch('routes.community_routes.bd',self.db), patch('routes.agendamentos_routes.bd',self.db):
            self.assertEqual(client.post('/api/convites-guias',json=[],headers=headers('a')).status_code,400)
            self.assertEqual(client.get('/api/agendamentos/dashboard/g',headers=headers('a')).status_code,403)
            self.assertEqual(client.get('/api/agendamentos/dashboard/g',headers=headers('g')).status_code,200)
            with patch('services.community.PushDevices.send',return_value={'enviados':0,'falhas':0}) as send:
                client.post('/api/usuarios/fcm-token/teste',json={'id_usuario':'x'},headers=headers('t'))
                self.assertEqual(send.call_args.args[1],'t')

    def test_agenda_por_id_inclui_email_legado_sem_outro_guia(self):
        for booking_id, guide_id in [('nova','g'),('antiga','g@example.test'),('outra','outro')]:
            self.db.collection('agendamentos').document(booking_id).set(
                {'id':booking_id,'id_guia':guide_id,'status':'agendado'})
        for identifier in ('g','g@example.test'):
            result,status=Agendamentos.listar_agendamentos_guia(self.db,identifier)
            self.assertEqual(status,200)
            self.assertEqual({row['id'] for row in result},{'nova','antiga'})

    @patch.dict(os.environ, {'KEY':'test-key-only-'*4})
    def test_agenda_autorizada_somente_para_guia_dono(self):
        self.db.collection('agendamentos').document('antiga').set(
            {'id':'antiga','id_guia':'g@example.test','status':'agendado'})
        client=app.test_client()
        def headers(user):
            return {'Authorization':'Bearer '+Autenticacao.make_token(user['email'],user['id'],user['tipo'])}
        with patch('services.autenticacao.firestore.client',return_value=self.db), patch('routes.agendamentos_routes.bd',self.db):
            for identifier in ('g','g@example.test'):
                response=client.get('/api/agendamentos/guia/'+identifier,headers=headers(self.g))
                self.assertEqual(response.status_code,200)
                self.assertEqual([row['id'] for row in response.json],['antiga'])
            for identifier in ('outro','outro@example.test'):
                self.assertEqual(client.get('/api/agendamentos/guia/'+identifier,headers=headers(self.g)).status_code,403)
            self.assertEqual(client.get('/api/agendamentos/guia/g',headers=headers(self.t)).status_code,403)
            self.assertEqual(client.get('/api/agendamentos/guia/g').status_code,401)

    def test_reservas_ativas_bloqueiam_delete_e_desativacao_por_edicao(self):
        for status in ('agendado','pendente','em_andamento','Confirmado',''):
            with self.subTest(status=status):
                self.db.collection('trilhas').document('t1').set({'ativo':True,'id_guia':'g'})
                self.db.collection('agendamentos').document('b1').set({'id':'b1','id_trilha':'t1','status':status})
                self.assertEqual(Trilhas.deletar_trilha(self.db,'t1',self.g)[1],409)
                self.assertEqual(Trilhas.atualizar_trilha(self.db,'t1',{'ativo':False},self.g)[1],409)
                self.assertTrue(self.db.collection('trilhas').document('t1').get().to_dict()['ativo'])
                self.assertTrue(self.db.collection('agendamentos').document('b1').get().exists)

    def test_desativacao_preserva_historico_e_ignora_reservas_de_outra_trilha(self):
        self.db.collection('trilhas').document('t1').set({'ativo':True,'id_guia':'g'})
        for booking,status,trail in [('b1','cancelado','t1'),('b2','concluido','t1'),('b3','agendado','t2')]:
            self.db.collection('agendamentos').document(booking).set({'id':booking,'id_trilha':trail,'status':status})
        self.assertEqual(Trilhas.deletar_trilha(self.db,'t1',self.x)[1],403)
        self.assertEqual(Trilhas.deletar_trilha(self.db,'t1',self.g)[1],200)
        self.assertFalse(self.db.collection('trilhas').document('t1').get().to_dict()['ativo'])
        self.assertEqual(len(self.db.collection('agendamentos').stream()),3)

    def test_falha_ao_conferir_reservas_nao_desativa_trilha(self):
        self.db.collection('trilhas').document('t1').set({'ativo':True,'id_guia':'g'})
        with patch.object(Trilhas,'_tem_agendamentos_ativos',side_effect=RuntimeError('Offline')):
            self.assertEqual(Trilhas.deletar_trilha(self.db,'t1',self.g)[1],500)
        self.assertTrue(self.db.collection('trilhas').document('t1').get().to_dict()['ativo'])

    def test_rotas_de_chat_removidas(self):
        client = app.test_client()
        paths = ('/api/conversas', '/api/conversas/exemplo/mensagens',
                 '/api/suporte', '/api/suporte/exemplo/mensagens')
        for path in paths:
            for method in ('GET', 'POST'):
                with self.subTest(path=path, method=method):
                    self.assertEqual(client.open(path, method=method).status_code, 404)
        for name in ('start_chat', 'chats', 'thread', 'messages', 'send', 'tickets', 'open_ticket'):
            self.assertFalse(hasattr(Community, name))
