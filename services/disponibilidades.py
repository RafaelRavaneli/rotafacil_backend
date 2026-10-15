import uuid
from datetime import date, datetime
from firebase_admin import firestore
from services.community import Community


class Disponibilidades:
    TIPOS = {'disponivel', 'bloqueio'}

    @staticmethod
    def _hora(valor, campo):
        try:
            return datetime.strptime(str(valor or ''), '%H:%M').time()
        except ValueError as exc:
            raise ValueError(f'{campo} deve estar no formato HH:MM.') from exc

    @staticmethod
    def _validar(dados):
        data_texto = str(dados.get('data') or '').strip()
        try:
            data_valor = date.fromisoformat(data_texto)
        except ValueError as exc:
            raise ValueError('data deve estar no formato AAAA-MM-DD.') from exc
        if data_valor < date.today():
            raise ValueError('Não é possível cadastrar disponibilidade em data passada.')
        inicio = Disponibilidades._hora(dados.get('horario_inicio'), 'horario_inicio')
        fim = Disponibilidades._hora(dados.get('horario_fim'), 'horario_fim')
        if inicio >= fim:
            raise ValueError('O horário final deve ser posterior ao inicial.')
        tipo = str(dados.get('tipo') or '').strip().lower()
        if tipo not in Disponibilidades.TIPOS:
            raise ValueError('tipo deve ser disponivel ou bloqueio.')
        capacidade = dados.get('capacidade')
        if capacidade is not None:
            try:
                capacidade = int(capacidade)
            except (TypeError, ValueError) as exc:
                raise ValueError('capacidade deve ser um número inteiro.') from exc
            if capacidade <= 0:
                raise ValueError('capacidade deve ser maior que zero.')
        return data_texto, inicio.strftime('%H:%M'), fim.strftime('%H:%M'), tipo, capacidade

    @staticmethod
    def _sobrepoe(inicio_a, fim_a, inicio_b, fim_b):
        return inicio_a < fim_b and inicio_b < fim_a

    @staticmethod
    def _pode_consultar(db, usuario, alvo):
        if alvo in {usuario.get('id'), usuario.get('email')}:
            return True
        if usuario.get('tipo') == 'admin':
            return True
        if usuario.get('tipo') != 'agencia':
            return False
        return any(item.get('id_guia') == alvo for item in Community.linked(db, usuario.get('id')))

    @staticmethod
    def listar(db, usuario, guia_id=None):
        alvo = guia_id or usuario.get('id')
        if not Disponibilidades._pode_consultar(db, usuario, alvo):
            return {'erro': 'Você não possui vínculo para consultar este calendário.'}, 403
        docs = db.collection('disponibilidades').where('id_usuario', '==', alvo).stream()
        items = [{**(doc.to_dict() or {}), 'id': doc.id} for doc in docs]
        items.sort(key=lambda item: (item.get('data', ''), item.get('horario_inicio', '')))
        return items, 200

    @staticmethod
    def criar(db, usuario, dados):
        if usuario.get('tipo') not in {'guia', 'agencia', 'admin'}:
            return {'erro': 'Somente guias e agências gerenciam disponibilidade.'}, 403
        try:
            data_texto, inicio, fim, tipo, capacidade = Disponibilidades._validar(dados or {})
        except ValueError as error:
            return {'erro': str(error)}, 400
        usuario_id = usuario.get('id')
        existentes = db.collection('disponibilidades') \
            .where('id_usuario', '==', usuario_id) \
            .where('data', '==', data_texto).stream()
        if any(Disponibilidades._sobrepoe(
            inicio, fim,
            (doc.to_dict() or {}).get('horario_inicio', ''),
            (doc.to_dict() or {}).get('horario_fim', ''),
        ) for doc in existentes):
            return {'erro': 'Já existe disponibilidade ou bloqueio neste horário.'}, 409
        identificador = str(uuid.uuid4())
        item = {
            'id': identificador,
            'id_usuario': usuario_id,
            'data': data_texto,
            'horario_inicio': inicio,
            'horario_fim': fim,
            'tipo': tipo,
            'capacidade': capacidade,
            'observacao': str(dados.get('observacao') or '').strip()[:500],
            'createdAt': firestore.SERVER_TIMESTAMP,
        }
        db.collection('disponibilidades').document(identificador).set(item)
        return item, 201

    @staticmethod
    def excluir(db, usuario, identificador):
        ref = db.collection('disponibilidades').document(identificador)
        doc = ref.get()
        if not doc.exists:
            return {'erro': 'Disponibilidade não encontrada.'}, 404
        if usuario.get('tipo') != 'admin' and (doc.to_dict() or {}).get('id_usuario') != usuario.get('id'):
            return {'erro': 'Você não pode alterar este calendário.'}, 403
        ref.delete()
        return {'mensagem': 'Registro removido.'}, 200

    @staticmethod
    def conflito_bloqueio(db, guia_id, data_texto, inicio, fim):
        if not guia_id or not data_texto or not inicio or not fim:
            return False
        docs = db.collection('disponibilidades') \
            .where('id_usuario', '==', guia_id) \
            .where('data', '==', data_texto).stream()
        return any(
            (doc.to_dict() or {}).get('tipo') == 'bloqueio' and
            Disponibilidades._sobrepoe(
                inicio, fim,
                (doc.to_dict() or {}).get('horario_inicio', ''),
                (doc.to_dict() or {}).get('horario_fim', ''),
            ) for doc in docs
        )
