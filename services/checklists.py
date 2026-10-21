"""Itens do roteiro e preparação particular de cada reserva."""
import hashlib
from firebase_admin import firestore


class Checklists:
    STATUS_EDITAVEIS = {'pendente', 'agendado', 'confirmado', 'em_andamento'}

    @staticmethod
    def chave(nome):
        return hashlib.sha256(' '.join(nome.split()).lower().encode('utf-8')).hexdigest()

    @staticmethod
    def normalizar_itens(valores, campo):
        if not isinstance(valores, list) or len(valores) > 50:
            raise ValueError(f'{campo} deve conter até 50 itens.')
        resultado, vistos = [], set()
        for valor in valores:
            if not isinstance(valor, str) or not 1 <= len(valor.strip()) <= 120:
                raise ValueError(f'Cada item de {campo} deve ter de 1 a 120 caracteres.')
            nome = ' '.join(valor.split())
            chave = Checklists.chave(nome)
            if chave not in vistos:
                resultado.append(nome)
                vistos.add(chave)
        return resultado

    @staticmethod
    def itens(roteiro, marcados=None):
        marcados = marcados if isinstance(marcados, dict) else {}
        itens, vistos = [], set()
        for campo, obrigatorio in [('itens_obrigatorios', True), ('itens_recomendados', False)]:
            valores = roteiro.get(campo) or []
            if not isinstance(valores, list):
                continue
            for nome in valores:
                if not isinstance(nome, str) or not nome.strip():
                    continue
                nome = ' '.join(nome.split())
                chave = Checklists.chave(nome)
                if chave in vistos:
                    continue
                vistos.add(chave)
                itens.append({'id': chave, 'nome': nome, 'obrigatorio': obrigatorio,
                              'marcado': marcados.get(chave) is True})
        return itens

    @staticmethod
    def _carregar(db, reserva_id, usuario):
        reserva = db.collection('agendamentos').document(reserva_id).get()
        if not reserva.exists:
            return None, ({'erro': 'Reserva não encontrada.'}, 404)
        dados = reserva.to_dict() or {}
        if usuario.get('tipo') != 'usuario' or dados.get('id_usuario') != usuario.get('id'):
            return None, ({'erro': 'O checklist pessoal pertence somente ao turista da reserva.'}, 403)
        roteiro_id = dados.get('id_trilha')
        roteiro = db.collection('trilhas').document(roteiro_id).get() if roteiro_id else None
        if roteiro is None or not roteiro.exists:
            return None, ({'erro': 'O roteiro desta reserva não está disponível.'}, 404)
        return (dados, roteiro.to_dict() or {}), None

    @staticmethod
    def obter(db, reserva_id, usuario):
        carregado, erro = Checklists._carregar(db, reserva_id, usuario)
        if erro:
            return erro
        reserva, roteiro = carregado
        snapshot = db.collection('checklists_pessoais').document(reserva_id).get()
        registro = (snapshot.to_dict() or {}) if snapshot.exists else {}
        itens = Checklists.itens(roteiro, registro.get('marcados'))
        return {'id_agendamento': reserva_id, 'itens': itens,
                'editavel': str(reserva.get('status') or '').strip().lower() in Checklists.STATUS_EDITAVEIS,
                'total': len(itens), 'preparados': sum(item['marcado'] for item in itens)}, 200

    @staticmethod
    def atualizar(db, reserva_id, usuario, dados):
        carregado, erro = Checklists._carregar(db, reserva_id, usuario)
        if erro:
            return erro
        reserva, roteiro = carregado
        if str(reserva.get('status') or '').strip().lower() not in Checklists.STATUS_EDITAVEIS:
            return {'erro': 'O checklist desta reserva está disponível apenas para consulta.'}, 409
        if (not isinstance(dados, dict) or set(dados) != {'id_item', 'marcado'} or
                not isinstance(dados.get('id_item'), str) or
                not isinstance(dados.get('marcado'), bool) or
                dados.get('id_item') not in {item['id'] for item in Checklists.itens(roteiro)}):
            return {'erro': 'Informe um item atual do roteiro e uma marcação válida.'}, 400
        # Merge em uma única folha do mapa preserva marcações concorrentes de outros itens.
        db.collection('checklists_pessoais').document(reserva_id).set({
            'id_usuario': usuario['id'], 'id_agendamento': reserva_id,
            'id_trilha': reserva['id_trilha'],
            'marcados': {dados['id_item']: dados['marcado']},
            'atualizado_em': firestore.SERVER_TIMESTAMP,
        }, merge=True)
        return Checklists.obter(db, reserva_id, usuario)
