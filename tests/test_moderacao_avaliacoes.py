import os
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from services.avaliacoes import Avaliacoes
from test_community import FakeDB

class ReviewModerationTests(unittest.TestCase):
    def setUp(self):
        self.db=FakeDB()
        self.user={'id':'u','tipo':'usuario','nome':'Pessoa'}
        self.admin={'id':'admin','tipo':'admin'}
        for id,tipo in [('u','usuario'),('x','usuario'),('g','guia'),('a','agencia'),('admin','admin')]:
            self.db.collection('usuarios').document(id).set({'id':id,'tipo':tipo,'nome':id,'email':id+'@test.local','ativo':True})
        self.db.collection('trilhas').document('t').set({'nome':'Roteiro','id_guia':'g','criado_por':'a','ativo':True})
        for id in ('b','b2'):
            self.db.collection('agendamentos').document(id).set({'id_usuario':'u','id_trilha':'t','id_guia':'g','status':'concluido'})
    def create(self,id='b',nota=0):
        return Avaliacoes.adicionar_avaliacao(self.db,'u','t',nota,'Comentário','Pessoa',id_agendamento=id,nota_guia=4,nota_agencia=5)
    def test_uma_por_reserva_nao_por_roteiro_e_nota_zero(self):
        self.assertEqual(self.create()[1],201)
        self.assertEqual(self.create()[1],409)
        self.assertEqual(self.create('b2',4)[1],201)
        self.assertEqual(self.db.data['trilhas/t']['nota_media'],2)
        self.assertEqual(self.db.data['trilhas/t']['total_avaliacoes'],2)
        self.assertEqual(Avaliacoes.adicionar_avaliacao(self.db,'x','t',5,'','X',id_agendamento='b',nota_guia=5,nota_agencia=5)[1],404)
        self.db.collection('agendamentos').document('b2').update({'status':'cancelado'})
        self.assertEqual(Avaliacoes.adicionar_avaliacao(self.db,'u','t',5,'','U',id_agendamento='b2')[1],403)
    def test_edicao_autor_prazo_nao_renova_e_medias_recalculadas(self):
        self.create()
        old=self.db.data['avaliacoes/b']['createdAt']
        payload={'nota':2,'nota_guia':1,'nota_agencia':3,'comentario':'Editado'}
        self.assertEqual(Avaliacoes.editar(self.db,'b',self.user,payload)[1],200)
        self.assertEqual(self.db.data['avaliacoes/b']['createdAt'],old)
        self.assertEqual(self.db.data['trilhas/t']['nota_media'],2)
        self.assertEqual(self.db.data['usuarios/g']['nota_media'],1)
        self.assertEqual(self.db.data['usuarios/a']['nota_media'],3)
        self.assertEqual(Avaliacoes.editar(self.db,'b',{'id':'x','tipo':'usuario'},payload)[1],403)
        self.db.collection('avaliacoes').document('b').update({'createdAt':(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()})
        self.assertEqual(Avaliacoes.editar(self.db,'b',self.user,payload)[1],409)
    def test_denuncia_unica_com_autoria_protegida(self):
        self.create()
        payload={'motivo':'dados_pessoais','descricao':'Revisar conteúdo'}
        self.assertEqual(Avaliacoes.denunciar(self.db,'b',self.user,payload)[1],403)
        reporter={'id':'x','tipo':'usuario'}
        self.assertEqual(Avaliacoes.denunciar(self.db,'b',reporter,payload)[1],201)
        self.assertEqual(Avaliacoes.denunciar(self.db,'b',reporter,payload)[1],409)
        public,status=Avaliacoes.listar_avaliacoes_trilha(self.db,'t')
        self.assertEqual(status,200)
        self.assertNotIn('id_usuario',public[0])
        self.assertNotIn('denuncias',public[0])
        self.assertEqual(len(Avaliacoes.painel(self.db,self.admin)[0]),1)
    def test_ocultar_restaurar_retira_medias_e_historico(self):
        self.create()
        self.assertEqual(Avaliacoes.moderar(self.db,'b',self.user,{'acao':'ocultar','motivo':'Motivo'})[1],403)
        self.assertEqual(Avaliacoes.moderar(self.db,'b',self.admin,{'acao':'ocultar','motivo':'Dados pessoais'})[1],200)
        self.assertEqual(Avaliacoes.listar_avaliacoes_trilha(self.db,'t')[0],[])
        self.assertEqual(Avaliacoes.listar_profissional(self.db,'a')[0],[])
        for path in ('trilhas/t','usuarios/g','usuarios/a'):
            self.assertEqual(self.db.data[path]['total_avaliacoes'],0)
            self.assertIsNone(self.db.data[path]['nota_media'])
        self.assertFalse(Avaliacoes.minha(self.db,'b',self.user)[0]['editavel'])
        self.assertEqual(Avaliacoes.moderar(self.db,'b',self.admin,{'acao':'restaurar','motivo':'Análise revisada'})[1],200)
        self.assertEqual(self.db.data['trilhas/t']['total_avaliacoes'],1)
        self.assertEqual(len(list(self.db.collection('historico_moderacao_avaliacoes').stream())),2)
        self.assertTrue(all(doc.to_dict()['resultado']=='aplicada' for doc in self.db.collection('historico_moderacao_avaliacoes').stream()))
    def test_entrada_invalida_nao_altera_medias_ou_status(self):
        for nota in (True,2.5,'NaN',-1,6): self.assertEqual(self.create(nota=nota)[1],400)
        self.create()
        self.assertEqual(Avaliacoes.editar(self.db,'b',self.user,{'nota':5,'status_moderacao':'publicada'})[1],400)
        self.assertEqual(Avaliacoes.denunciar(self.db,'b',{'id':'x'},{'motivo':[]})[1],400)
        self.assertEqual(Avaliacoes.moderar(self.db,'b',self.admin,{'acao':[],'motivo':'texto'})[1],400)
        self.assertEqual(Avaliacoes.painel(self.db,self.user)[1],403)
    def test_auditoria_indisponivel_nao_oculta(self):
        self.create()
        original=self.db.collection
        def collection(name):
            if name=='historico_moderacao_avaliacoes': raise RuntimeError('offline')
            return original(name)
        with patch.object(self.db,'collection',side_effect=collection), self.assertRaises(RuntimeError):
            Avaliacoes.moderar(self.db,'b',self.admin,{'acao':'ocultar','motivo':'Motivo válido'})
        self.assertTrue(Avaliacoes._publicada(self.db.data['avaliacoes/b']))
    @patch.dict(os.environ,{'KEY':'review-tests-only-'*4})
    def test_api_protege_moderacao_e_ignora_contadores_do_cliente(self):
        from test_integration import app
        from services.autenticacao import Autenticacao
        client=app.test_client()
        def header(id,tipo):return {'Authorization':'Bearer '+Autenticacao.make_token(id+'@test.local',id,tipo)}
        with patch('routes.avaliacoes_routes.bd',self.db),patch('services.autenticacao.firestore.client',return_value=self.db):
            self.assertEqual(client.get('/api/avaliacoes/moderacao',headers=header('u','usuario')).status_code,403)
            self.assertEqual(client.post('/api/avaliacoes/',headers=header('g','guia'),json={}).status_code,403)
            self.assertEqual(client.post('/api/avaliacoes/',headers=header('u','usuario'),json={'id_agendamento':'b','nota_media':5}).status_code,400)
            self.create()
            response=client.get('/api/avaliacoes/profissional/a/perfil',headers=header('u','usuario'))
            self.assertEqual(response.status_code,200)
            self.assertNotIn('email',response.get_json())
            self.assertEqual(client.get('/api/avaliacoes/reserva/b',headers=header('x','usuario')).status_code,403)
            response=client.post('/api/avaliacoes/b/moderar',headers=header('admin','admin'),json={'acao':'ocultar','motivo':'Revisado'})
            self.assertEqual(response.status_code,200,response.get_json())
            self.assertEqual(client.get('/api/avaliacoes/trilha/t',headers=header('u','usuario')).get_json(),[])

    def test_leitura_publica_nao_usa_contadores_antigos_ou_ocultos(self):
        from services.trilhas import Trilhas
        from services.community import Community
        self.create()
        for path in ('trilhas/t','usuarios/g','usuarios/a'):
            self.db.data[path].update({'nota_media':5,'total_avaliacoes':99})
        self.assertEqual(Trilhas.buscar_trilha_por_id(self.db,'t')[0]['nota_media'],0)
        self.assertEqual(Community.guide(self.db,'g')['nota_media'],4)
        self.db.data['avaliacoes/b']['status_moderacao']='oculta'
        self.assertEqual(Trilhas.buscar_trilha_por_id(self.db,'t')[0]['total_avaliacoes'],0)
        self.assertEqual(Community.guide(self.db,'g')['total_avaliacoes'],0)

    def test_data_legada_do_firestore_e_serializada_em_iso(self):
        self.create()
        agora=datetime.now(timezone.utc)
        self.db.collection('avaliacoes').document('b').update({'createdAt':agora})
        data,status=Avaliacoes.listar_avaliacoes_trilha(self.db,'t')
        self.assertEqual(status,200)
        self.assertEqual(data[0]['createdAt'],agora.isoformat())
