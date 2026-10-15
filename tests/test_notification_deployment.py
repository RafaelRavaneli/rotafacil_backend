"""Verifica notificacoes e publicacao sem acessar Firebase ou SMTP reais."""
import datetime as dt
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import MagicMock, patch

from test_community import FakeDB
from test_integration import app
from services.agendamentos import Agendamentos
from services.agendador import enviar_lembretes_diarios
from services.autenticacao import Autenticacao
from services.community import PushDevices
from services.notificacoes import Notificacoes

BACKEND = Path(__file__).resolve().parents[1]


class NotificationDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.user = {'id': 'u1', 'email': 'ana@example.test', 'tipo': 'usuario'}
        self.db.collection('usuarios').document('u1').set(self.user)

    def test_eventos_usam_dispositivos_e_preservam_dados(self):
        for token, device in [('web-token', 'web'), ('phone-token', 'phone')]:
            PushDevices.register(self.db, self.user, {'token': token, 'dispositivo_id': device})
        self.db.collection('usuarios').document('u1').update({'fcm_tokens': ['legacy-token']})
        with patch('services.community.messaging.send', return_value='fake') as send:
            result = Notificacoes.notificar_usuario(
                self.db, 'u1', 'Reserva', 'Confirmada', {'tipo': 'reserva', 'numero': 123})
        self.assertEqual(result, {'enviados': 2, 'falhas': 0})
        self.assertEqual({call.args[0].token for call in send.call_args_list},
                         {'web-token', 'phone-token'})
        for call in send.call_args_list:
            self.assertEqual(call.args[0].data, {'tipo': 'reserva', 'numero': '123'})
        notifications = list(self.db.collection('notificacoes').stream())
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].to_dict()['titulo'], 'Reserva')

    def test_preferencias_controlam_eventos_e_central_persistida(self):
        result,status=Notificacoes.atualizar_preferencias(
            self.db,self.user,{'agendamentos':False,'push':False})
        self.assertEqual(status,200,result)
        with patch('services.notificacoes.PushDevices.send') as send:
            self.assertEqual(Notificacoes.notificar_usuario(
                self.db,'u1','Reserva','Confirmada',{'tipo':'reserva'}),
                {'enviados':0,'falhas':0})
            send.assert_not_called()
        self.assertEqual(len(self.db.collection('notificacoes').stream()),0)

        Notificacoes.notificar_usuario(
            self.db,'u1','Sistema','Atualização',{'tipo':'sistema'})
        items,status=Notificacoes.listar(self.db,self.user)
        self.assertEqual(status,200,items)
        self.assertEqual(len(items),1)
        self.assertFalse(items[0]['lida'])
        self.assertEqual(Notificacoes.marcar_lida(
            self.db,self.user,items[0]['id'])[1],200)
        self.assertTrue(self.db.collection('notificacoes')
                        .document(items[0]['id']).get().to_dict()['lida'])

    def test_token_invalido_e_removido_sem_afetar_outro_dispositivo(self):
        from firebase_admin import messaging
        for token, device in [('expired', 'web'), ('valid', 'phone')]:
            PushDevices.register(self.db, self.user, {'token': token, 'dispositivo_id': device})
        with patch('services.community.messaging.send',
                   side_effect=[messaging.UnregisteredError('Expired token'), 'fake']):
            result = PushDevices.send(self.db, 'u1', 'Teste', 'Texto')
        self.assertEqual(result, {'enviados': 1, 'falhas': 1})
        devices = list(self.db.collection('dispositivos_fcm').stream())
        self.assertEqual([doc.to_dict()['token'] for doc in devices], ['valid'])

    def test_falha_de_push_nao_impede_criacao_da_reserva(self):
        self.db.collection('trilhas').document('t1').set({'id_guia': 'g1', 'ativo': True})
        with patch('services.notificacoes.PushDevices.send', side_effect=RuntimeError('Offline')):
            result, status = Agendamentos.agendar_trilha(self.db, {
                'id_usuario': 'u1', 'id_trilha': 't1',
                'data_agendada': '2026-10-20', 'valor_pago': 50})
        self.assertEqual(status, 201)
        self.assertTrue(self.db.collection('agendamentos').document(result['id']).get().exists)

    @patch.dict(os.environ, {'KEY': 'test-key-only-' * 4})
    def test_registro_e_logout_usam_unica_rota_por_metodo(self):
        rules = list(app.url_map.iter_rules())
        for method in ('POST', 'DELETE'):
            matches = [rule for rule in rules
                       if rule.rule == '/api/usuarios/fcm-token' and method in rule.methods]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].endpoint, 'community.devices')
        token = Autenticacao.make_token(self.user['email'], 'u1', 'usuario')
        headers = {'Authorization': 'Bearer ' + token}
        client = app.test_client()
        with patch('services.autenticacao.firestore.client', return_value=self.db), patch(
                'routes.community_routes.bd', self.db):
            self.assertEqual(client.post('/api/usuarios/fcm-token', headers=headers,
                json={'token': 'old', 'dispositivo_id': 'web'}).status_code, 200)
            self.assertEqual(client.post('/api/usuarios/fcm-token', headers=headers,
                json={'token': 'new', 'dispositivo_id': 'web'}).status_code, 200)
            self.assertEqual(client.post('/api/usuarios/fcm-token', headers=headers,
                json={'token': 'phone', 'dispositivo_id': 'phone'}).status_code, 200)
            self.assertEqual(client.post('/api/usuarios/fcm-token', headers=headers,
                json={'token': 'missing-device'}).status_code, 400)
            self.assertEqual(client.delete('/api/usuarios/fcm-token?dispositivo_id=web',
                headers=headers).status_code, 200)
        with patch('services.community.messaging.send', return_value='fake') as send:
            self.assertEqual(Notificacoes.notificar_usuario(self.db, 'u1', 'Teste', 'Texto'),
                             {'enviados': 1, 'falhas': 0})
            self.assertEqual(send.call_args.args[0].token, 'phone')

    def test_lembrete_considera_data_de_sao_paulo_na_virada_utc(self):
        class FrozenDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                instant = cls(2026, 10, 14, 1, tzinfo=dt.timezone.utc)
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
        self.db.collection('trilhas').document('t1').set({'nome': 'Mirante'})
        for key, date in [('tomorrow', '2026-10-14'), ('later', '2026-10-15')]:
            self.db.collection('agendamentos').document(key).set({
                'status': 'agendado', 'data_agendada': date,
                'id_trilha': 't1', 'id_usuario': 'u1'})
        with patch('models.database.bd', self.db), patch(
                'services.agendador.dt.datetime', FrozenDateTime), patch(
                'services.notificacoes.Notificacoes.notificar_usuario') as notify:
            enviar_lembretes_diarios()
        self.assertEqual(notify.call_count, 1)
        self.assertEqual(notify.call_args.kwargs['dados']['id_agendamento'], 'tomorrow')

    def test_cron_propaga_falha_de_consulta(self):
        database = MagicMock()
        database.collection.side_effect = RuntimeError('Offline')
        with patch('models.database.bd', database):
            with self.assertRaises(RuntimeError):
                enviar_lembretes_diarios(raise_errors=True)

    def test_comando_cron_executa_uma_rodada(self):
        with patch('services.agendador.enviar_lembretes_diarios') as execute:
            runpy.run_path(str(BACKEND / 'enviar_lembretes.py'), run_name='__main__')
        execute.assert_called_once_with(raise_errors=True)

    def test_firebase_le_arquivo_configurado_e_nao_oculta_credencial_invalida(self):
        with patch('dotenv.load_dotenv'), patch.dict(os.environ, {
                'FIREBASE_CREDENTIALS_PATH': '/etc/secrets/firebase-key.json'}), patch(
                'firebase_admin.get_app', side_effect=ValueError('No app')), patch(
                'firebase_admin.credentials.Certificate') as certificate, patch(
                'firebase_admin.initialize_app') as initialize, patch('firebase_admin.firestore.client'):
            runpy.run_path(str(BACKEND / 'models/database.py'))
            certificate.assert_called_once_with('/etc/secrets/firebase-key.json')
            initialize.assert_called_once_with(certificate.return_value)
            certificate.side_effect = ValueError('Invalid credential')
            with self.assertRaises(ValueError):
                runpy.run_path(str(BACKEND / 'models/database.py'))

    def test_firebase_existente_nao_reinicializa(self):
        with patch('dotenv.load_dotenv'), patch('firebase_admin.get_app'), patch(
                'firebase_admin.credentials.Certificate') as certificate, patch(
                'firebase_admin.initialize_app') as initialize, patch('firebase_admin.firestore.client'):
            runpy.run_path(str(BACKEND / 'models/database.py'))
        certificate.assert_not_called()
        initialize.assert_not_called()

    def test_agendador_embutido_exige_opt_in_e_respeita_reloader(self):
        for enabled, debug, reloader, expected in [
                ('false', 'false', '', 0), ('true', 'false', '', 1),
                ('true', 'true', '', 0), ('true', 'true', 'true', 1)]:
            with self.subTest(enabled=enabled, debug=debug, reloader=reloader), patch.dict(
                    os.environ, {'ENABLE_SCHEDULER': enabled, 'FLASK_DEBUG': debug,
                                 'WERKZEUG_RUN_MAIN': reloader}), patch(
                    'services.agendador.iniciar_agendador') as start, patch('flask.Flask.run') as run:
                runpy.run_path(str(BACKEND / 'app.py'), run_name='__main__')
                self.assertEqual(start.call_count, expected)
                run.assert_called_once_with(debug=(debug == 'true'))
