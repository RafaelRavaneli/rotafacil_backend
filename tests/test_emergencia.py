import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from services.emergencia import Emergencia
from services.usuarios import Usuarios
from services.trilhas import Trilhas
from test_community import FakeDB

class EmergencyTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.guide = {'id':'g', 'email':'g@test.local', 'tipo':'guia'}
        self.user = {'id':'u', 'tipo':'usuario', 'nome':'Pessoa', 'email':'u@test.local', 'contato_emergencia_nome':'Contato privado', 'contato_emergencia_telefone':'44999990000', 'contato_emergencia_relacao':'Irmã', 'contato_emergencia_consentimento':True}
        self.db.collection('usuarios').document('u').set(self.user)
        self.db.collection('trilhas').document('t').set({'criado_por':'g', 'id_guia':'g'})
        self.now = datetime.now(timezone.utc)
        self.res = {'id_usuario':'u','id_trilha':'t','status':'confirmado', 'data_hora_inicio':(self.now-timedelta(hours=1)).isoformat(), 'data_hora_fim':(self.now+timedelta(hours=1)).isoformat()}
        self.db.collection('agendamentos').document('b').set(self.res)
    def read(self, actor=None, id='b', user='u'):
        return Usuarios.obter_contato_emergencia(self.db,user,actor or self.guide,id)
    def test_permissao_auditoria_minima_sem_valores_pessoais(self):
        data,status=self.read()
        self.assertEqual(status,200,data)
        self.assertEqual(data['contato_emergencia_relacao'],'Irmã')
        self.assertNotIn('telefone_participante',data)
        logs=list(self.db.collection('consultas_emergencia').stream())
        self.assertEqual(len(logs),1)
        log=logs[0].to_dict()
        self.assertEqual(log['id_agendamento'],'b')
        self.assertEqual(log['id_solicitante'],'g')
        self.assertNotIn('44999990000',str(log))
        self.assertNotIn('Contato privado',str(log))
    def test_isolamento_status_e_reserva_identificada(self):
        for actor in ({'id':'u','tipo':'usuario'}, {'id':'x','tipo':'guia'}, {'id':'a','tipo':'agencia'}, {'id':'adm','tipo':'admin'}):
            self.assertEqual(self.read(actor)[1],403)
        for status in ('pendente','cancelado','recusado','concluido','desconhecido'):
            self.db.collection('agendamentos').document('b').update({'status':status})
            self.assertEqual(self.read()[1],403)
        self.assertEqual(self.read(id=None)[1],403)
        self.assertEqual(self.read(id='outra')[1],403)
        self.assertEqual(self.read(user='outro')[1],403)
        self.assertEqual(list(self.db.collection('consultas_emergencia').stream()),[])
    def test_janela_e_dados_ausentes_fecham_acesso(self):
        for start,end in ((25,30),(-4,-1)):
            self.db.collection('agendamentos').document('b').update({'data_hora_inicio':(self.now+timedelta(hours=start)).isoformat(),'data_hora_fim':(self.now+timedelta(hours=end)).isoformat()})
            self.assertEqual(self.read()[1],403)
        self.db.collection('agendamentos').document('b').set({**self.res,'data_hora_fim':None})
        self.assertEqual(self.read()[1],403)
        self.db.collection('agendamentos').document('b').set({**self.res,'data_hora_inicio':(self.now+timedelta(hours=23)).isoformat(),'data_hora_fim':(self.now+timedelta(hours=25)).isoformat()})
        self.assertEqual(self.read()[1],200)
    def test_consentimento_legado_retirada_e_remocao(self):
        for consent in (False,None,'true'):
            self.db.collection('usuarios').document('u').update({'contato_emergencia_consentimento':consent})
            self.assertEqual(self.read()[1],403)
        self.assertEqual(Usuarios.atualizar_usuario_por_id(self.db,'u',{'contato_emergencia_consentimento':True})[1],200)
        self.assertEqual(self.read()[1],200)
        self.assertEqual(Usuarios.atualizar_usuario_por_id(self.db,'u',{'contato_emergencia_consentimento':False})[1],200)
        self.assertEqual(self.read()[1],403)
        self.assertEqual(Usuarios.atualizar_usuario_por_id(self.db,'u',{'contato_emergencia_consentimento':False,'contato_emergencia_nome':'','contato_emergencia_telefone':'','contato_emergencia_relacao':''})[1],200)
        self.assertEqual(self.db.data['usuarios/u']['contato_emergencia_telefone'],'')
    def test_validacao_campos_consentimento_e_lista_sem_contatos(self):
        for value in ({'contato_emergencia_consentimento':'sim'}, {'contato_emergencia_telefone':'123'}, {'contato_emergencia_nome':[]}, {'contato_emergencia_relacao':'x'*81}, {'contato_emergencia_consentimento':True,'contato_emergencia_relacao':''}):
            self.assertEqual(Usuarios.atualizar_usuario_por_id(self.db,'u',value)[1],400)
        result,status=Usuarios.listar_usuarios(self.db)
        self.assertEqual(status,200)
        self.assertFalse(any(key.startswith('contato_emergencia_') for key in result[0]))
    def test_falha_auditoria_nao_retorna_contato(self):
        original=self.db.collection
        def collection(name):
            if name == 'consultas_emergencia': raise RuntimeError('indisponível')
            return original(name)
        with patch.object(self.db,'collection',side_effect=collection):
            result,status=self.read()
        self.assertEqual(status,503)
        self.assertNotIn('contato_emergencia_telefone',result)
    def test_emergencia_organizador_valida_e_persiste(self):
        value={'emergencia_organizador_telefone':'(44) 99999-0000','emergencia_instrucoes':'Ligue para a equipe.'}
        result,status=Trilhas.cadastrar_trilha(self.db,{'nome':'Roteiro','descricao':'Descrição','dificuldade':'Iniciante',**value},self.guide)
        self.assertEqual(status,201,result)
        doc=Trilhas.buscar_trilha_por_id(self.db,result['id'])[0]
        self.assertEqual(doc['emergencia_instrucoes'],value['emergencia_instrucoes'])
        self.assertIsNotNone(Trilhas._validar_campos_publicos({'emergencia_organizador_telefone':'abc'}))

    @patch.dict(os.environ, {'KEY': 'emergency-tests-only-' * 4})
    def test_api_reserva_cache_isolamento_e_privacidade_administrativa(self):
        from test_integration import app
        from services.autenticacao import Autenticacao
        for id, tipo in [('g','guia'), ('adm','admin'), ('x','usuario')]:
            self.db.collection('usuarios').document(id).set({'id':id, 'email':id+'@test.local','tipo':tipo,'ativo':True})
        client=app.test_client()
        def header(id,tipo):
            return {'Authorization':'Bearer '+Autenticacao.make_token(id+'@test.local',id,tipo)}
        with patch('routes.usuarios_routes.bd',self.db), patch('services.autenticacao.firestore.client',return_value=self.db):
            path='/api/usuarios/u/contato-emergencia?id_agendamento=b'
            response=client.get(path,headers=header('g','guia'))
            self.assertEqual(response.status_code,200,response.get_json())
            self.assertEqual(response.headers['Cache-Control'],'no-store, private')
            self.assertEqual(client.get(path,headers=header('x','usuario')).status_code,403)
            self.assertEqual(client.get(path,headers=header('adm','admin')).status_code,403)
            admin=header('adm','admin')
            for path in ('/api/usuarios/','/api/usuarios/u','/api/usuarios/email/u@test.local'):
                response=client.get(path,headers=admin)
                self.assertEqual(response.status_code,200,response.get_json())
                self.assertNotIn('contato_emergencia_',response.get_data(as_text=True))
            for path in ('/api/usuarios/u','/api/usuarios/email/u@test.local'):
                response=client.put(path,headers=admin,json={'contato_emergencia_consentimento':True})
                self.assertEqual(response.status_code,403,response.get_json())
            owner=header('u','usuario')
            response=client.put('/api/usuarios/u',headers=owner,json={'contato_emergencia_consentimento':False})
            self.assertEqual(response.status_code,200,response.get_json())
            self.assertEqual(client.get('/api/usuarios/u/contato-emergencia?id_agendamento=b',headers=header('g','guia')).status_code,403)

    def test_troca_de_responsavel_e_exclusao_do_roteiro_cortam_acesso(self):
        self.assertEqual(self.read()[1],200)
        self.db.collection('trilhas').document('t').update({'criado_por':'outra'})
        self.assertEqual(self.read()[1],403)
        self.db.collection('trilhas').document('t').delete()
        self.assertEqual(self.read()[1],403)
