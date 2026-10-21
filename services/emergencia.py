"""Acesso operacional a contato de emergência, condicionado e auditado."""
import re
import uuid
from datetime import datetime, timezone, timedelta
from firebase_admin import firestore

class Emergencia:
    CAMPOS = {'contato_emergencia_nome', 'contato_emergencia_telefone',
              'contato_emergencia_relacao', 'contato_emergencia_consentimento'}

    @staticmethod
    def preparar(dados, atual):
        if not Emergencia.CAMPOS.intersection(dados):
            return
        for campo, limite in [('contato_emergencia_nome',120), ('contato_emergencia_relacao',80), ('contato_emergencia_telefone',30)]:
            if campo in dados:
                valor = dados[campo]
                if not isinstance(valor, str) or len(valor.strip()) > limite:
                    raise ValueError(f'{campo} deve ser texto com até {limite} caracteres')
                dados[campo] = valor.strip()
        campo = 'contato_emergencia_consentimento'
        if campo in dados and not isinstance(dados[campo], bool):
            raise ValueError('Consentimento deve ser verdadeiro ou falso')
        if campo not in dados:
            # Clientes antigos que alteram o contato não renovam autorização implicitamente.
            dados[campo] = False
        novo = {**atual, **dados}
        telefone = novo.get('contato_emergencia_telefone') or ''
        validar_telefone = 'contato_emergencia_telefone' in dados or novo.get(campo) is True
        if validar_telefone and telefone and not re.fullmatch(r'[+()0-9 .-]+', telefone):
            raise ValueError('Telefone de emergência inválido')
        if validar_telefone and telefone and not 10 <= len(re.sub(r'\D','',telefone)) <= 15:
            raise ValueError('Telefone de emergência deve ter de 10 a 15 dígitos')
        if novo.get(campo) is True:
            if atual.get('tipo') != 'usuario':
                raise ValueError('Consentimento de emergência é destinado ao turista')
            if not all(novo.get(key) for key in Emergencia.CAMPOS - {campo}):
                raise ValueError('Preencha nome, telefone e relação antes de autorizar o uso')
        if campo in dados:
            dados['contato_emergencia_consentimento_em'] = firestore.SERVER_TIMESTAMP

    @staticmethod
    def remover_dados(resposta):
        if isinstance(resposta, list):
            return [Emergencia.remover_dados(item) for item in resposta]
        if isinstance(resposta, dict):
            return {key: value for key,value in resposta.items() if not key.startswith('contato_emergencia_')}
        return resposta

    @staticmethod
    def _data(valor):
        try:
            result = datetime.fromisoformat(str(valor).replace('Z','+00:00'))
            # Horários legados sem offset usam o fuso brasileiro do produto.
            return result.replace(tzinfo=timezone(timedelta(hours=-3))) if result.tzinfo is None else result
        except (ValueError, TypeError):
            return None

    @staticmethod
    def consultar(db, id_usuario, solicitante, reserva_id):
        from services.agendamentos import Agendamentos
        if solicitante.get('tipo') not in {'guia', 'agencia'} or not reserva_id:
            return {'erro': 'Consulta exige responsável operacional e identificação da reserva.'}, 403
        reserva = db.collection('agendamentos').document(reserva_id).get()
        dados = (reserva.to_dict() or {}) if reserva.exists else {}
        if (dados.get('id_usuario') != id_usuario or
                str(dados.get('status') or '').lower().strip() not in {'confirmado','agendado','em_andamento'} or
                not Agendamentos._usuario_pode_operar_agendamento(db,dados,solicitante)):
            return {'erro': 'Contato indisponível para esta reserva.'}, 403
        roteiro_id = dados.get('id_trilha')
        roteiro = db.collection('trilhas').document(roteiro_id).get() if roteiro_id else None
        if roteiro is None or not roteiro.exists:
            return {'erro': 'Roteiro indisponível.'}, 403
        inicio, fim = Emergencia._data(dados.get('data_hora_inicio')), Emergencia._data(dados.get('data_hora_fim'))
        agora = datetime.now(timezone.utc)
        if not inicio or not fim or fim <= inicio or not inicio - timedelta(hours=24) <= agora <= fim:
            return {'erro': 'Consulta permitida de 24 horas antes do início até o término da saída.'}, 403
        pessoa = db.collection('usuarios').document(id_usuario).get()
        usuario = (pessoa.to_dict() or {}) if pessoa.exists else {}
        if usuario.get('contato_emergencia_consentimento') is not True:
            return {'erro': 'O turista não autorizou o uso do contato de emergência.'}, 403
        if not all(usuario.get(key) for key in Emergencia.CAMPOS - {'contato_emergencia_consentimento'}):
            return {'erro': 'Contato de emergência não cadastrado.'}, 404
        # Não devolver o contato se não for possível registrar a consulta.
        try:
            db.collection('consultas_emergencia').document(str(uuid.uuid4())).set({
                'id_usuario': id_usuario, 'id_solicitante': solicitante['id'],
                'papel_solicitante': solicitante['tipo'], 'id_agendamento': reserva_id,
                'id_trilha': roteiro_id, 'consultado_em': firestore.SERVER_TIMESTAMP,
            })
        except Exception:
            return {'erro': 'Não foi possível registrar a consulta. Tente novamente.'}, 503
        return {'nome_participante': usuario.get('nome'),
                'contato_emergencia_nome': usuario['contato_emergencia_nome'],
                'contato_emergencia_telefone': usuario['contato_emergencia_telefone'],
                'contato_emergencia_relacao': usuario['contato_emergencia_relacao']}, 200
