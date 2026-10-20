"""Documentos versionados e prova de aceite sem consentimento genérico."""
import json
from pathlib import Path
from datetime import datetime, timezone
from firebase_admin import firestore


class DocumentosLegais:
    @staticmethod
    def documentos():
        path = Path(__file__).resolve().parent.parent / 'legal' / 'legal_documents.json'
        return json.loads(path.read_text(encoding='utf-8'))

    @staticmethod
    def validar_aceite(dados):
        if not isinstance(dados, dict):
            raise ValueError('Envie os dados de aceite em um objeto JSON.')
        docs = DocumentosLegais.documentos()
        if (dados.get('aceite_termos') is not True or
                dados.get('ciencia_privacidade') is not True):
            raise ValueError('É necessário aceitar os Termos de Uso e declarar ciência da Política de Privacidade.')
        if any(dados.get(f'{key}_versao') != doc['version'] for key, doc in docs.items()):
            raise ValueError('Os documentos foram atualizados. Leia as versões atuais antes de continuar.')
        return {
            'termos_versao': docs['termos']['version'],
            'privacidade_versao': docs['privacidade']['version'],
            'termos_sha256': docs['termos']['sha256'],
            'privacidade_sha256': docs['privacidade']['sha256'],
            'aceite_termos': True,
            'ciencia_privacidade': True,
            'registrado_em': datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def registrar(db, usuario, dados):
        try:
            aceite = DocumentosLegais.validar_aceite(dados)
        except ValueError as error:
            return {'erro': str(error), 'codigo': 'ACEITE_LEGAL_NECESSARIO'}, 400
        ref = db.collection('usuarios').document(usuario['id'])
        snapshot = ref.get()
        if not snapshot.exists:
            return {'erro': 'Usuário não encontrado'}, 404
        anterior = (snapshot.to_dict() or {}).get('aceite_legal') or {}
        if isinstance(anterior, dict) and all(
                anterior.get(key) == aceite[key] for key in (
                    'termos_versao', 'privacidade_versao', 'termos_sha256',
                    'privacidade_sha256', 'aceite_termos', 'ciencia_privacidade')):
            return {'mensagem': 'Aceite já registrado', 'aceite_legal': anterior}, 200
        ref.update({'aceite_legal': aceite,
                    'historico_aceites_legais': firestore.ArrayUnion([aceite])})
        return {'mensagem': 'Aceite registrado', 'aceite_legal': aceite}, 200
