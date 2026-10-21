import os
import unittest
from unittest.mock import patch
from services.administracao import Administracao
from services.community import CommunityError, Community
from services.trilhas import Trilhas
from services.agendamentos import Agendamentos
from services.documentos_profissionais import DocumentosProfissionais
from services.autenticacao import Autenticacao
from test_community import FakeDB
from werkzeug.security import generate_password_hash

class AdministrationTests(unittest.TestCase):
    def setUp(self):
        self.db=FakeDB()
        self.admin={'id':'adm','email':'adm@test.local','tipo':'admin'}
        for id,tipo in [('adm','admin'),('adm2','admin'),('g','guia'),('a','agencia'),('u','usuario')]:
            self.db.collection('usuarios').document(id).set({'id':id,'nome':id,'email':id+'@test.local','tipo':tipo,'ativo':True,'senha':generate_password_hash('senha123')})
        self.db.collection('trilhas').document('t').set({'nome':'Roteiro','criado_por':'g','id_guia':'g','ativo':True})
        self.db.collection('agendamentos').document('b').set({'id_usuario':'u','id_guia':'g','id_trilha':'t','status':'confirmado'})
    def action(self,id,action):
        return Administracao.conta(self.db,self.admin,id,{'acao':action,'motivo':'Motivo registrado'})
    def test_bloqueio_preserva_dados_e_revoga_sessoes(self):
        self.assertEqual(self.action('g','bloquear')[1],200)
        self.assertFalse(self.db.data['usuarios/g']['ativo'])
        self.assertEqual(self.db.data['usuarios/g']['versao_auth'],1)
        self.assertEqual(self.db.data['agendamentos/b']['status'],'confirmado')
        self.assertTrue(self.db.data['trilhas/t']['ativo'])
        self.assertFalse(Trilhas.buscar_trilha_por_id(self.db,'t')[0]['ativo'])
        self.assertEqual(Agendamentos.agendar_trilha(self.db,{'id_usuario':'u','id_trilha':'t','data_agendada':'2099-01-01'})[1],409)
        self.assertEqual(self.action('g','desbloquear')[1],200)
        self.assertEqual(self.db.data['usuarios/g']['versao_auth'],2)
        self.assertTrue(Trilhas.buscar_trilha_por_id(self.db,'t')[0]['ativo'])
    def test_nao_bloqueia_admin_e_usuario_nao_executa_acoes(self):
        for id in ('adm','adm2'):
            with self.assertRaises(CommunityError): self.action(id,'bloquear')
        with self.assertRaises(CommunityError):
            Administracao.conta(self.db,{'id':'u','tipo':'usuario'},'g',{'acao':'bloquear','motivo':'Teste'})
        for value in ({'acao':'bloquear'}, {'acao':'bloquear','motivo':'ab'}, {'acao':'bloquear','motivo':'Motivo','id_admin':'forjado'}, {'acao':[],'motivo':'Motivo'}):
            with self.assertRaises(CommunityError): Administracao.conta(self.db,self.admin,'g',value)
    def test_selo_e_remocao_auditados_sem_reaprovacao_automatica(self):
        self.action('g','verificar')
        self.assertTrue(Community.guide(self.db,'g')['verificado'])
        self.action('g','remover_verificacao')
        self.db.collection('documentos_profissionais').document('d').set({'id_usuario':'g','status':'pendente'})
        self.assertEqual(DocumentosProfissionais.analisar(self.db,self.admin,'d',{'status':'aprovado'})[1],200)
        self.assertFalse(Community.guide(self.db,'g')['verificado'])
        self.action('g','verificar')
        self.assertTrue(Community.guide(self.db,'g')['verificado'])
        audit=Administracao.historico(self.db,self.admin,{'tipo':'conta'})[0]
        self.assertEqual(len(audit),3)
        self.assertNotIn('senha',str(audit))
        self.assertEqual(len(Administracao.historico(self.db,self.admin,{'tipo':'documento'})[0]),1)
    def test_roteiro_suspenso_nao_recebe_reserva_e_organizador_nao_remove_restricao(self):
        self.assertEqual(Administracao.roteiro(self.db,self.admin,'t',{'acao':'suspender','motivo':'Análise de segurança'})[1],200)
        self.assertTrue(self.db.data['trilhas/t']['ativo'])
        self.assertFalse(Trilhas.buscar_trilha_por_id(self.db,'t')[0]['ativo'])
        self.assertEqual(Agendamentos.agendar_trilha(self.db,{'id_usuario':'u','id_trilha':'t','data_agendada':'2099-01-01'})[1],409)
        result,status=Trilhas.atualizar_trilha(self.db,'t',{'bloqueado_moderacao':False},{'id':'g','tipo':'guia'})
        self.assertEqual(status,400,result)
        self.assertEqual(Administracao.roteiro(self.db,self.admin,'t',{'acao':'liberar','motivo':'Correções conferidas'})[1],200)
        self.assertTrue(Trilhas.buscar_trilha_por_id(self.db,'t')[0]['ativo'])
        self.assertEqual(self.db.data['agendamentos/b']['status'],'confirmado')
    def test_listas_filtram_sem_senha_documentos_ou_emergencia(self):
        self.db.data['usuarios/g'].update({'documento':'privado','contato_emergencia_nome':'Privado','email_confirmado':True})
        self.action('g','bloquear')
        rows,status=Administracao.contas(self.db,self.admin,{'tipo':'guia','estado':'bloqueadas','q':'g@test'})
        self.assertEqual(status,200); self.assertEqual(len(rows),1)
        for field in ('senha','documento','contato_emergencia_nome'): self.assertNotIn(field,rows[0])
        self.assertEqual(len(Administracao.historico(self.db,self.admin,{'id_alvo':'g'})[0]),1)
        with self.assertRaises(CommunityError): Administracao.contas(self.db,self.admin,{'tipo':'super_admin'})
    def test_falha_auditoria_impede_acao(self):
        original=self.db.collection
        def collection(name):
            if name=='historico_admin': raise RuntimeError('offline')
            return original(name)
        with patch.object(self.db,'collection',side_effect=collection), self.assertRaises(RuntimeError): self.action('g','bloquear')
        self.assertTrue(self.db.data['usuarios/g']['ativo'])
    @patch.dict(os.environ,{'KEY':'administration-tests-'*4})
    def test_api_sessao_aberta_bloqueada_e_papeis_protegidos(self):
        from test_integration import app
        client=app.test_client()
        def header(id,tipo):return {'Authorization':'Bearer '+Autenticacao.make_token(id+'@test.local',id,tipo)}
        admin=header('adm','admin'); guia=header('g','guia'); turista=header('u','usuario')
        with patch('routes.admin_routes.bd',self.db),patch('routes.usuarios_routes.bd',self.db),patch('routes.trilhas_routes.bd',self.db),patch('services.autenticacao.firestore.client',return_value=self.db):
            self.assertEqual(client.get('/api/admin/contas',headers=turista).status_code,403)
            self.assertEqual(client.get('/api/admin/contas',headers=header('u','admin')).status_code,403)
            self.assertEqual(client.get('/api/admin/historico',headers=guia).status_code,403)
            self.assertEqual(client.get('/api/admin/contas').status_code,401)
            self.assertEqual(client.delete('/api/usuarios/adm',headers=admin).status_code,403)
            self.assertEqual(client.put('/api/usuarios/adm/tipo',headers=admin,json={'tipo':'usuario'}).status_code,403)
            result=client.post('/api/admin/contas/g/acao',headers=admin,json={'acao':'bloquear','motivo':'Teste de bloqueio'})
            self.assertEqual(result.status_code,200,result.get_json())
            self.assertEqual(result.headers['Cache-Control'],'no-store, private')
            response=client.get('/api/trilhas/',headers=guia)
            self.assertEqual(response.status_code,403,response.get_json())
            self.assertEqual(response.get_json()['codigo'],'CONTA_BLOQUEADA')
            client.post('/api/admin/contas/g/acao',headers=admin,json={'acao':'desbloquear','motivo':'Teste concluído'})
            self.assertEqual(client.get('/api/trilhas/',headers=guia).status_code,401)
            fresh={'Authorization':'Bearer '+Autenticacao.make_token('g@test.local','g','guia',versao_auth=2)}
            self.assertEqual(client.get('/api/trilhas/',headers=fresh).status_code,200)
            self.assertEqual(client.put('/api/usuarios/g',headers=admin,json={'ativo':True}).status_code,403)
            self.assertEqual(client.put('/api/usuarios/g/verificar',headers=admin,json={'verificado':True,'motivo':'Certificado conferido'}).status_code,200)
            self.assertEqual(client.post('/api/usuarios/',json={'nome':'Intruso','email':'i@test.local','senha':'senha123','tipo':'admin'}).status_code,400)

    def test_liberar_suspensao_nao_reativa_roteiro_inativo_e_filtros_distinguem_responsavel(self):
        self.action('g','bloquear')
        self.assertEqual(len(Administracao.roteiros(self.db,self.admin,{'estado':'restritos'})[0]),1)
        self.assertEqual(Administracao.roteiros(self.db,self.admin,{'estado':'ativos'})[0],[])
        self.action('g','desbloquear')
        self.db.data['trilhas/t']['ativo']=False
        Administracao.roteiro(self.db,self.admin,'t',{'acao':'suspender','motivo':'Revisão'})
        Administracao.roteiro(self.db,self.admin,'t',{'acao':'liberar','motivo':'Conferido'})
        self.assertFalse(self.db.data['trilhas/t']['ativo'])
        self.assertFalse(Trilhas.buscar_trilha_por_id(self.db,'t')[0]['ativo'])

    def test_admin_nao_assume_operacao_de_reservas_por_rotas_genericas(self):
        self.assertFalse(Agendamentos._usuario_pode_operar_agendamento(self.db,self.db.data['agendamentos/b'],self.admin))
        self.assertEqual(Agendamentos.cancelar_agendamento(self.db,'b',self.admin)[1],403)
        self.assertEqual(Trilhas.deletar_trilha(self.db,'t',self.admin)[1],403)
