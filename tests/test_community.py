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
    def test_chat_participantes_autoria_e_idempotencia(self):
        chat=Community.start_chat(self.db,self.t,{'id_guia':'g'})
        self.assertEqual(chat['id'],Community.start_chat(self.db,self.t,{'id_guia':'g'})['id'])
        self.assertEqual(Community.chats(self.db,self.x),[])
        self.denied(403,Community.messages,self.db,self.x,'conversas',chat['id'])
        self.denied(403,Community.send,self.db,self.x,'conversas',chat['id'],{'texto':'oi'})
        msg=Community.send(self.db,self.t,'conversas',chat['id'],{'texto':'Olá','id_autor':'g','atendente':True})
        self.assertEqual(msg['id_autor'],'t'); self.assertFalse(msg['atendente'])
        self.assertEqual(Community.messages(self.db,self.g,'conversas',chat['id'])[0]['texto'],'Olá')
        self.denied(403,Community.start_chat,self.db,self.g,{'id_guia':'g'})
    def test_catalogo_nao_expoe_dados_privados(self):
        guide=Community.guides(self.db)[0]
        self.assertEqual(guide['id'],'g')
        for key in ('senha','email','documento'): self.assertNotIn(key,guide)
        self.denied(400,Community.start_chat,self.db,self.t,{'id_guia':'g/x'})
    def test_suporte_owner_e_admin_sem_falsificar_atendente(self):
        ticket=Community.open_ticket(self.db,self.t,{'assunto':'Reserva','texto':'Ajuda'})
        self.assertEqual(Community.tickets(self.db,self.x),[])
        self.denied(403,Community.send,self.db,self.x,'suporte',ticket['id'],{'texto':'x'})
        own=Community.send(self.db,self.t,'suporte',ticket['id'],{'texto':'Resposta','atendente':True})
        admin=Community.send(self.db,self.users['admin'],'suporte',ticket['id'],{'texto':'Atendimento'})
        self.assertFalse(own['atendente']);self.assertTrue(admin['atendente'])
        self.assertEqual(len(Community.messages(self.db,self.t,'suporte',ticket['id'])),3)
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
        for path in ['/api/guias','/api/conversas','/api/suporte','/api/convites-guias','/api/agendamentos/dashboard/g']:
            self.assertEqual(client.get(path).status_code,401)
        def headers(id):
            user=self.users[id]
            return {'Authorization':'Bearer '+Autenticacao.make_token(user['email'],id,user['tipo'])}
        with patch('services.autenticacao.firestore.client',return_value=self.db), patch('routes.community_routes.bd',self.db), patch('routes.agendamentos_routes.bd',self.db):
            self.assertEqual(client.post('/api/conversas',json=[],headers=headers('t')).status_code,400)
            self.assertEqual(client.post('/api/conversas',json={'id_guia':'g'},headers=headers('t')).status_code,200)
            self.assertEqual(client.get('/api/agendamentos/dashboard/g',headers=headers('a')).status_code,403)
            self.assertEqual(client.get('/api/agendamentos/dashboard/g',headers=headers('g')).status_code,200)
            with patch('services.community.PushDevices.send',return_value={'enviados':0,'falhas':0}) as send:
                client.post('/api/usuarios/fcm-token/teste',json={'id_usuario':'x'},headers=headers('t'))
                self.assertEqual(send.call_args.args[1],'t')
