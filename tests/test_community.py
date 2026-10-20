"""Fluxos multiusuário com armazenamento isolado; nunca usa Firebase real."""
import os
import io
import unittest
from copy import deepcopy
from unittest.mock import patch
from google.api_core.exceptions import AlreadyExists, FailedPrecondition
from test_integration import app
from services.autenticacao import Autenticacao
from services.community import Community, CommunityError, PushDevices
from services.agendamentos import Agendamentos
from services.trilhas import Trilhas
from services.usuarios import Usuarios
from services.disponibilidades import Disponibilidades
from services.documentos_profissionais import DocumentosProfissionais
from services.avaliacoes import Avaliacoes
from services.uploads import Uploads
from werkzeug.datastructures import FileStorage


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


class FakeBlob:
    def __init__(self, bucket, path):
        self.bucket, self.path = bucket, path
    def upload_from_string(self, data, content_type=None):
        self.bucket.files[self.path] = (bytes(data), content_type)
    def download_as_bytes(self):
        return self.bucket.files[self.path][0]
    def delete(self):
        self.bucket.files.pop(self.path, None)


class FakeBucket:
    def __init__(self): self.files = {}
    def blob(self, path): return FakeBlob(self, path)


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
        self.db.collection('usuarios').document('g').update({
            'descricao_profissional': 'Condutor de ecoturismo',
            'especialidades': ['Trekking', 'Cachoeiras'],
            'verificado': True,
        })
        guide=Community.guides(self.db)[0]
        self.assertEqual(guide['id'],'g')
        for key in ('senha','email','documento'): self.assertNotIn(key,guide)
        detail=Community.guide(self.db,'g')
        self.assertEqual(detail['descricao_profissional'],
                         'Condutor de ecoturismo')
        self.assertEqual(detail['especialidades'],
                         ['Trekking','Cachoeiras'])
        for key in ('senha','email','documento'): self.assertNotIn(key,detail)
        self.denied(404,Community.guide,self.db,'a')
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
        result,status=Trilhas.cadastrar_trilha(self.db,data,self.a)
        self.assertEqual(status,201)
        self.assertEqual(
            Trilhas.atualizar_trilha(
                self.db,result['id'],{'descricao':'Sem autorização'},self.g
            )[1],403)
        self.assertEqual(
            Trilhas.deletar_trilha(self.db,result['id'],self.g)[1],403)
        self.assertEqual(
            Trilhas.atualizar_trilha(
                self.db,result['id'],{'descricao':'Atualizado pela agência'},self.a
            )[1],200)
        self.denied(409,Community.answer_invitation,self.db,self.g,invite['id'],{'status':'recusado'})
        self.denied(409,Community.invite,self.db,self.a,{'id_guia':'g'})

    def test_agencia_revoga_reenvia_e_partes_encerram_vinculo(self):
        invite=Community.invite(self.db,self.a,{'id_guia':'g'})
        self.denied(403,Community.manage_invitation,self.db,self.g,
                    invite['id'],'revogar')
        revoked=Community.manage_invitation(
            self.db,self.a,invite['id'],'revogar')
        self.assertEqual(revoked['status'],'revogado')
        resent=Community.manage_invitation(
            self.db,self.a,invite['id'],'reenviar')
        self.assertEqual(resent['status'],'pendente')
        Community.answer_invitation(
            self.db,self.g,invite['id'],{'status':'aceito'})
        self.db.collection('trilhas').document('t1').set({
            'criado_por':'a','id_guia':'g','ativo':True})
        self.db.collection('agendamentos').document('b1').set({
            'id_trilha':'t1','status':'confirmado'})
        self.denied(409,Community.manage_invitation,self.db,self.a,
                    invite['id'],'desligar')
        self.db.collection('agendamentos').document('b1').update(
            {'status':'concluido'})
        disconnected=Community.manage_invitation(
            self.db,self.g,invite['id'],'desligar')
        self.assertEqual(disconnected['status'],'desligado')
        self.assertEqual(self.db.collection('trilhas').document('t1')
                         .get().to_dict()['id_guia'],'a')
        self.assertEqual(Community.manage_invitation(
            self.db,self.a,invite['id'],'reenviar')['status'],'pendente')
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
        for id,guide,status,value in [('1','g','agendado','10.25'),('2','g@example.test','concluido',20),('3','g','cancelado',90),('4','g','agendado','NaN'),('5','g','pendente',5),('6','g','confirmado',7)]:
            self.db.collection('agendamentos').document(id).set({'id_guia':guide,'status':status,'valor_pago':value})
        result,status=Agendamentos.dashboard_guia(self.db,'g')
        self.assertEqual(status,200);self.assertEqual(result['total_agendamentos'],6)
        self.assertEqual(result['valor_declarado_ativo'],42.25)
        self.assertEqual(result['por_status']['cancelado'],1)
        self.assertEqual(result['por_status']['pendente'],1)
        self.assertEqual(result['por_status']['confirmado'],1)
        self.db.collection('trilhas').document('agency-trail').set({
            'criado_por':'a@example.test'})
        self.db.collection('agendamentos').document('agency-booking').set({
            'id_trilha':'agency-trail','id_guia':'g','status':'agendado',
            'valor_pago':45})
        agency_result,agency_status=Agendamentos.dashboard_guia(self.db,'a')
        self.assertEqual(agency_status,200)
        self.assertEqual(agency_result['total_agendamentos'],1)
        self.assertEqual(agency_result['valor_declarado_ativo'],45)

    def test_cancelamento_respeita_transicao_de_estado(self):
        for booking_id,status in (
                ('agendada','agendado'),('andamento','em_andamento'),
                ('concluida','concluido'),('cancelada','cancelado')):
            self.db.collection('agendamentos').document(booking_id).set({
                'id_usuario':'t','id_guia':'g','id_trilha':'t1',
                'status':status})
        self.db.collection('trilhas').document('t1').set({'nome':'Trilha'})
        result,status=Agendamentos.cancelar_agendamento(
            self.db,'agendada',self.t)
        self.assertEqual(status,200,result)
        for booking_id in ('agendada','andamento','concluida','cancelada'):
            with self.subTest(booking_id=booking_id):
                result,status=Agendamentos.cancelar_agendamento(
                    self.db,booking_id,self.t)
                self.assertEqual(status,409,result)

    def test_checkin_e_checkout_exigem_operador_responsavel(self):
        self.db.collection('trilhas').document('t1').set({
            'nome':'Trilha','criado_por':'a'})
        self.db.collection('agendamentos').document('b1').set({
            'id_usuario':'t','id_guia':'g','id_trilha':'t1',
            'status':'agendado'})
        result,status=Agendamentos.fazer_checkin(self.db,'b1',self.t)
        self.assertEqual(status,403,result)
        result,status=Agendamentos.fazer_checkin(self.db,'b1',self.g)
        self.assertEqual(status,200,result)
        result,status=Agendamentos.fazer_checkout(self.db,'b1',self.t)
        self.assertEqual(status,403,result)
        result,status=Agendamentos.fazer_checkout(self.db,'b1',self.a)
        self.assertEqual(status,200,result)
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
            self.assertEqual(client.get('/api/agendamentos/guia/g',headers=headers('a')).status_code,403)
            self.assertEqual(client.get('/api/agendamentos/dashboard/g',headers=headers('g')).status_code,200)
            self.assertEqual(client.put('/api/agendamentos/b1/checkin',headers=headers('g')).status_code,503)
            self.assertEqual(client.put('/api/agendamentos/b1/checkout',headers=headers('g')).status_code,503)
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

    def test_trilha_mostra_nome_publico_do_responsavel_por_id_e_email(self):
        self.db.collection('usuarios').document('g').update({'nome':'Mateus Guia'})
        for trail_id,owner in [('t1','g'),('t2','g@example.test'),('t3','nao-existe')]:
            self.db.collection('trilhas').document(trail_id).set({'nome':trail_id,'id_guia':owner,'distancia_km':'15,5'})
        rows,status=Trilhas.listar_trilhas(self.db)
        self.assertEqual(status,200)
        by_id={row['id']:row for row in rows}
        for trail_id in ('t1','t2'):
            self.assertEqual(by_id[trail_id]['nome_guia'],'Mateus Guia')
            self.assertEqual(by_id[trail_id]['tipo_responsavel'],'guia')
            for private in ('senha','documento','telefone','email'):
                self.assertNotIn(private,by_id[trail_id])
        self.assertIsNone(by_id['t3']['nome_guia'])
        detail,status=Trilhas.buscar_trilha_por_id(self.db,'t1')
        self.assertEqual(status,200)
        self.assertEqual(detail['nome_guia'],'Mateus Guia')

    def test_distancia_invalida_nao_salva_e_decimal_persiste(self):
        base={'nome':'Trilha','descricao':'Percurso','dificuldade':'Fácil'}
        for value in ('',0,-2,'NaN','Infinity',None,True):
            result,status=Trilhas.cadastrar_trilha(self.db,{**base,'distancia_km':value},self.g)
            self.assertEqual(status,400,result)
        self.assertEqual(len(self.db.collection('trilhas').stream()),0)
        result,status=Trilhas.cadastrar_trilha(self.db,{**base,'distancia_km':'15,5'},self.g)
        self.assertEqual(status,201,result)
        ref=self.db.collection('trilhas').document(result['id'])
        self.assertEqual(ref.get().to_dict()['distancia_km'],15.5)
        self.assertEqual(Trilhas.atualizar_trilha(self.db,result['id'],{'distancia_km':-1},self.g)[1],400)
        self.assertEqual(ref.get().to_dict()['distancia_km'],15.5)
        self.assertEqual(Trilhas.atualizar_trilha(self.db,result['id'],{'distancia_km':'12,75'},self.g)[1],200)
        self.assertEqual(ref.get().to_dict()['distancia_km'],12.75)

    def test_trilha_rejeita_campos_internos_preco_e_data_invalidos(self):
        base={'nome':'Trilha','descricao':'Percurso','dificuldade':'Fácil'}
        for dados in (
                {**base,'criado_por':'outro'},
                {**base,'preco':-1},
                {**base,'preco':'NaN'},
                {**base,'data_atividade':'2020-01-01'},
                {**base,'ativo':'sim'}):
            with self.subTest(dados=dados):
                self.assertEqual(Trilhas.cadastrar_trilha(
                    self.db,dados,self.g)[1],400)
        result,status=Trilhas.cadastrar_trilha(self.db,base,self.g)
        self.assertEqual(status,201,result)
        self.assertEqual(Trilhas.atualizar_trilha(
            self.db,result['id'],{'criado_por':'outro'},self.g)[1],400)

    def test_roteiro_aceita_varias_atividades_e_intervalo_em_dias_diferentes(self):
        dados={
            'nome':'Expedição','descricao':'Percurso completo',
            'dificuldade':'Avançado','atividades':['Trilha','Rapel','Acampamento'],
            'data_atividade':'2099-06-10','data_fim':'2099-06-11',
            'data_hora_inicio':'2099-06-10T23:00:00',
            'data_hora_fim':'2099-06-11T15:00:00',
        }
        result,status=Trilhas.cadastrar_trilha(self.db,dados,self.g)
        self.assertEqual(status,201,result)
        roteiro=self.db.collection('trilhas').document(result['id']).get().to_dict()
        self.assertEqual(roteiro['atividades'],['Trilha','Rapel','Acampamento'])
        self.assertEqual(roteiro['data_atividade'],'2099-06-10')
        self.assertEqual(roteiro['data_fim'],'2099-06-11')
        self.assertEqual(roteiro['horario_inicio'],'23:00')
        self.assertEqual(roteiro['horario_fim'],'15:00')
        invalido={**dados,'data_hora_fim':'2099-06-10T22:00:00'}
        self.assertEqual(Trilhas.cadastrar_trilha(self.db,invalido,self.g)[1],400)
        Disponibilidades.criar(self.db,self.g,{
            'data':'2099-07-11','horario_inicio':'10:00',
            'horario_fim':'16:00','tipo':'bloqueio'})
        conflito={
            **dados,'data_atividade':'2099-07-10','data_fim':'2099-07-11',
            'data_hora_inicio':'2099-07-10T23:00:00',
            'data_hora_fim':'2099-07-11T15:00:00'}
        self.assertEqual(Trilhas.cadastrar_trilha(self.db,conflito,self.g)[1],409)

    def test_reserva_usa_preco_do_servidor_bloqueia_duplicidade_e_lotacao(self):
        self.db.collection('trilhas').document('t1').set({
            'nome':'Trilha final','ativo':True,'id_guia':'g',
            'preco':80,'capacidade':1})
        dados={'id_usuario':'t','id_trilha':'t1','data_agendada':'2099-01-01','valor_pago':1}
        with patch('services.agendamentos.Notificacoes.notificar_usuario'):
            result,status=Agendamentos.agendar_trilha(self.db,dados)
            self.assertEqual(status,201,result)
            reserva=self.db.collection('agendamentos').document(result['id']).get().to_dict()
            self.assertEqual(reserva['valor_pago'],80)
            self.assertEqual(Agendamentos.agendar_trilha(self.db,dados)[1],409)
            self.assertEqual(Agendamentos.agendar_trilha(
                self.db,{**dados,'id_usuario':'x'})[1],409)

    def test_agencia_lista_somente_reservas_das_proprias_trilhas(self):
        self.db.collection('trilhas').document('t1').set(
            {'nome':'Própria','criado_por':'a@example.test','id_guia':'g'})
        self.db.collection('trilhas').document('t2').set(
            {'nome':'Outra','criado_por':'outra@example.test','id_guia':'g'})
        self.db.collection('agendamentos').document('b1').set(
            {'id':'b1','id_trilha':'t1','id_usuario':'t','status':'agendado'})
        self.db.collection('agendamentos').document('b2').set(
            {'id':'b2','id_trilha':'t2','id_usuario':'x','status':'agendado'})
        rows,status=Agendamentos.listar_agendamentos_agencia(self.db,self.a)
        self.assertEqual(status,200)
        self.assertEqual([row['id'] for row in rows],['b1'])
        self.assertEqual(rows[0]['nome_usuario'],'t')
        self.assertEqual(rows[0]['nome_trilha'],'Própria')
        self.assertEqual(Agendamentos.cancelar_agendamento(
            self.db,'b1',self.a)[1],200)
        self.assertEqual(Agendamentos.cancelar_agendamento(
            self.db,'b2',self.a)[1],403)

    def test_emergencia_exige_reserva_ativa_e_responsabilidade(self):
        self.db.collection('usuarios').document('t').update({
            'telefone':'1111','contato_emergencia_nome':'Maria',
            'contato_emergencia_telefone':'2222'})
        self.db.collection('trilhas').document('t1').set(
            {'criado_por':'a@example.test','id_guia':'g'})
        self.db.collection('agendamentos').document('b1').set({
            'id_usuario':'t','id_trilha':'t1','id_guia':'g','status':'concluido'})
        self.assertEqual(Usuarios.obter_contato_emergencia(self.db,'t',self.g)[1],403)
        self.db.collection('agendamentos').document('b1').update({'status':'em_andamento'})
        for solicitante in (self.g,self.a):
            result,status=Usuarios.obter_contato_emergencia(self.db,'t',solicitante)
            self.assertEqual(status,200,result)
            self.assertEqual(result['contato_emergencia_nome'],'Maria')
        self.assertEqual(Usuarios.obter_contato_emergencia(self.db,'t',
            {**self.a,'id':'outra','email':'outra@example.test'})[1],403)

    def test_atualizacao_de_usuario_rejeita_campos_protegidos(self):
        result,status=Usuarios.atualizar_usuario_por_id(
            self.db,'t',{'nome':'Novo','admin':True})
        self.assertEqual(status,400)
        self.assertNotIn('admin',self.db.collection('usuarios').document('t').get().to_dict())
        self.assertEqual(Usuarios.atualizar_usuario_por_id(
            self.db,'t',{'contato_emergencia_nome':'Maria'})[1],200)

    def test_exclusao_de_conta_bloqueia_compromisso_ativo(self):
        self.db.collection('agendamentos').document('b1').set({
            'id_usuario':'t','id_guia':'g','status':'confirmado'})
        for identificador in ('t','g'):
            with self.subTest(identificador=identificador):
                result,status=Usuarios.deletar_usuario_por_id(
                    self.db,identificador)
                self.assertEqual(status,409,result)
                self.assertTrue(self.db.collection('usuarios')
                                .document(identificador).get().exists)

    def test_exclusao_de_agencia_considera_reservas_das_suas_trilhas(self):
        self.db.collection('trilhas').document('t1').set({
            'criado_por':'a@example.test','ativo':True})
        self.db.collection('agendamentos').document('b1').set({
            'id_trilha':'t1','id_usuario':'t','status':'agendado'})
        result,status=Usuarios.deletar_usuario_por_id(self.db,'a')
        self.assertEqual(status,409,result)
        self.assertTrue(self.db.collection('usuarios').document('a').get().exists)

    def test_exclusao_de_conta_limpa_dados_privados_e_preserva_historico(self):
        self.db.collection('trilhas').document('propria').set({
            'criado_por':'g@example.test','id_guia':'g','ativo':True})
        self.db.collection('trilhas').document('atribuida').set({
            'criado_por':'a','id_guia':'g@example.test','ativo':True})
        self.db.collection('agendamentos').document('historico').set({
            'id_usuario':'t','id_guia':'g','id_trilha':'propria',
            'status':'concluido'})
        for colecao, identificador, dados in (
            ('favoritos','fav',{'id_usuario':'g'}),
            ('dispositivos_fcm','device',{'id_usuario':'g'}),
            ('disponibilidades','disp',{'id_usuario':'g'}),
            ('redefinicoes_senha','reset',{'id_usuario':'g'}),
            ('convites_guias','invite',{'id_guia':'g','id_agencia':'a'}),
        ):
            self.db.collection(colecao).document(identificador).set(dados)

        result,status=Usuarios.deletar_usuario_por_id(self.db,'g')
        self.assertEqual(status,200,result)
        self.assertFalse(self.db.collection('usuarios').document('g').get().exists)
        self.assertTrue(self.db.collection('agendamentos')
                        .document('historico').get().exists)
        self.assertFalse(self.db.collection('trilhas')
                         .document('propria').get().to_dict()['ativo'])
        self.assertIsNone(self.db.collection('trilhas')
                          .document('atribuida').get().to_dict()['id_guia'])
        for colecao in ('favoritos','dispositivos_fcm','disponibilidades',
                        'redefinicoes_senha','convites_guias'):
            self.assertEqual(len(self.db.collection(colecao).stream()),0)

    def test_mudanca_de_tipo_bloqueia_reserva_ativa(self):
        self.db.collection('agendamentos').document('b1').set({
            'id_usuario':'t','status':'pendente'})
        result,status=Usuarios.mudar_tipo_usuario(
            self.db,'t','guia','52998224725')
        self.assertEqual(status,409,result)
        self.assertEqual(self.db.collection('usuarios').document('t')
                         .get().to_dict()['tipo'],'usuario')

    def test_mudanca_de_tipo_exige_documento_do_perfil_correto(self):
        self.assertEqual(Usuarios.mudar_tipo_usuario(
            self.db,'t','guia','11222333000181')[1],400)
        self.assertEqual(Usuarios.mudar_tipo_usuario(
            self.db,'t','agencia','52998224725')[1],400)
        result,status=Usuarios.mudar_tipo_usuario(
            self.db,'t','guia','52998224725')
        self.assertEqual(status,200,result)
        usuario=self.db.collection('usuarios').document('t').get().to_dict()
        self.assertEqual(usuario['tipo'],'guia')
        self.assertEqual(usuario['tipo_documento'],'cpf')
        self.assertFalse(usuario['verificado'])

    def test_mudanca_de_operador_limpa_vinculos_sem_apagar_historico(self):
        self.db.collection('trilhas').document('propria').set({
            'criado_por':'g@example.test','id_guia':'g','ativo':True})
        self.db.collection('trilhas').document('atribuida').set({
            'criado_por':'a','id_guia':'g@example.test','ativo':True})
        self.db.collection('agendamentos').document('historico').set({
            'id_guia':'g','status':'concluido'})
        self.db.collection('disponibilidades').document('d1').set(
            {'id_usuario':'g'})
        self.db.collection('convites_guias').document('c1').set(
            {'id_guia':'g','id_agencia':'a'})

        result,status=Usuarios.mudar_tipo_usuario(self.db,'g','usuario')
        self.assertEqual(status,200,result)
        guia=self.db.collection('usuarios').document('g').get().to_dict()
        self.assertEqual(guia['tipo'],'usuario')
        self.assertIsNone(guia['documento'])
        self.assertFalse(self.db.collection('trilhas').document('propria')
                         .get().to_dict()['ativo'])
        self.assertIsNone(self.db.collection('trilhas').document('atribuida')
                          .get().to_dict()['id_guia'])
        self.assertTrue(self.db.collection('agendamentos')
                        .document('historico').get().exists)
        self.assertEqual(len(self.db.collection('disponibilidades').stream()),0)
        self.assertEqual(len(self.db.collection('convites_guias').stream()),0)

    def test_disponibilidade_valida_conflito_e_remocao(self):
        dados={'data':'2099-02-10','horario_inicio':'08:00',
               'horario_fim':'12:00','tipo':'disponivel','capacidade':8}
        item,status=Disponibilidades.criar(self.db,self.g,dados)
        self.assertEqual(status,201,item)
        self.assertEqual(Disponibilidades.criar(
            self.db,self.g,{**dados,'horario_inicio':'10:00','horario_fim':'13:00'})[1],409)
        rows,status=Disponibilidades.listar(self.db,self.g)
        self.assertEqual(status,200);self.assertEqual([row['id'] for row in rows],[item['id']])
        self.assertEqual(Disponibilidades.excluir(self.db,self.x,item['id'])[1],403)
        self.assertEqual(Disponibilidades.excluir(self.db,self.g,item['id'])[1],200)

    def test_bloqueio_impede_atividade_no_mesmo_horario(self):
        bloqueio={'data':'2099-02-10','horario_inicio':'08:00',
                  'horario_fim':'12:00','tipo':'bloqueio'}
        self.assertEqual(Disponibilidades.criar(self.db,self.g,bloqueio)[1],201)
        trilha={'nome':'Trilha','descricao':'Percurso','dificuldade':'Fácil',
                'data_atividade':'2099-02-10','horario_inicio':'09:00',
                'horario_fim':'11:00','capacidade':10}
        result,status=Trilhas.cadastrar_trilha(self.db,trilha,self.g)
        self.assertEqual(status,409,result)

    def test_avaliacao_valida_comentario_e_exige_conclusao(self):
        self.db.collection('trilhas').document('t1').set({'nome':'Trilha'})
        self.assertEqual(Avaliacoes.adicionar_avaliacao(
            self.db,'t','t1',5,['inválido'],'t')[1],400)
        self.assertEqual(Avaliacoes.adicionar_avaliacao(
            self.db,'t','t1',5,'x'*501,'t')[1],400)
        self.assertEqual(Avaliacoes.adicionar_avaliacao(
            self.db,'t','t1',5,'Ótima','t')[1],403)
        self.db.collection('agendamentos').document('b1').set({
            'id_usuario':'t','id_trilha':'t1','status':'concluido'})
        result,status=Avaliacoes.adicionar_avaliacao(
            self.db,'t','t1',5,'  Ótima  ','t')
        self.assertEqual(status,201,result)
        avaliacao=self.db.collection('avaliacoes').document(
            't__t1').get().to_dict()
        self.assertEqual(avaliacao['comentario'],'Ótima')
        self.assertEqual(Avaliacoes.adicionar_avaliacao(
            self.db,'t','t1',4,'Outra','t')[1],409)

    @patch.dict(os.environ, {'IMGBB_API_KEY':'test','URL_IMGBB':'https://example.test'})
    def test_upload_rejeita_tipo_e_tamanho_invalidos(self):
        arquivo=FileStorage(stream=io.BytesIO(b'conteudo'),
                            filename='arquivo.txt',content_type='text/plain')
        self.assertEqual(Uploads.enviar_para_imgbb(arquivo)[1],400)
        grande=FileStorage(
            stream=io.BytesIO(b'x'*(Uploads.TAMANHO_MAXIMO+1)),
            filename='foto.png',content_type='image/png')
        with patch('services.uploads.requests.post') as enviar:
            self.assertEqual(Uploads.enviar_para_imgbb(grande)[1],400)
            enviar.assert_not_called()

    def test_documento_profissional_e_privado_e_exige_analise_admin(self):
        bucket=FakeBucket()
        arquivo=FileStorage(stream=io.BytesIO(b'imagem'),
                            filename='cadastur.png',content_type='image/png')
        result,status=DocumentosProfissionais.enviar(
            self.db,bucket,self.g,arquivo,'cadastur')
        self.assertEqual(status,201,result)
        identificador=result['id']
        self.assertEqual(result['status'],'pendente')
        self.assertNotIn('caminho_storage',result)
        self.assertEqual(DocumentosProfissionais.obter_arquivo(
            self.db,bucket,self.x,identificador)[1],403)
        conteudo,status=DocumentosProfissionais.obter_arquivo(
            self.db,bucket,self.g,identificador)
        self.assertEqual(status,200,conteudo)
        self.assertEqual(conteudo['conteudo'],b'imagem')
        self.assertEqual(DocumentosProfissionais.analisar(
            self.db,self.g,identificador,{'status':'aprovado'})[1],403)
        self.assertEqual(DocumentosProfissionais.analisar(
            self.db,self.users['admin'],identificador,
            {'status':'aprovado'})[1],200)
        self.assertTrue(self.db.collection('usuarios').document('g')
                        .get().to_dict()['verificado'])
        self.assertEqual(DocumentosProfissionais.excluir(
            self.db,bucket,self.g,identificador)[1],409)
        self.assertEqual(DocumentosProfissionais.excluir(
            self.db,bucket,self.users['admin'],identificador)[1],200)
        self.assertEqual(bucket.files,{})

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
