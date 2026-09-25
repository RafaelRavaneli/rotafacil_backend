import uuid
from firebase_admin import firestore

class Agendamentos:
    @staticmethod
    def _usuario_pode_gerenciar_agendamento(dados_agendamento, usuario_atual):
        papel = (usuario_atual.get('tipo') or '').strip().lower()
        usuario_id = usuario_atual.get('id')
        eh_admin = papel == 'admin'
        eh_dono = usuario_id == dados_agendamento.get('id_usuario')
        eh_guia_responsavel = dados_agendamento.get('id_guia') in {usuario_id, usuario_atual.get('email')} - {None, ''}
        return eh_admin or eh_dono or eh_guia_responsavel

    @staticmethod
    def agendar_trilha(db, dados):
        try:
            if not dados:
                return {"erro": "Dados não enviados"}, 400

            campos_obrigatorios = ["id_usuario", "id_trilha", "data_agendada", "valor_pago"]
            for campo in campos_obrigatorios:
                if campo not in dados:
                    return {"erro": f"Campo obrigatório: {campo}"}, 400

            trilha_ref = db.collection('trilhas').document(dados['id_trilha']).get()
            if not trilha_ref.exists:
                return {"erro": "Trilha não encontrada. Verifique o id_trilha informado."}, 404

            if trilha_ref.to_dict().get('ativo') is False:
                return {"erro": "Esta trilha não está disponível para agendamento."}, 409
            id_guia = trilha_ref.to_dict().get("id_guia")

            id_agendamento = str(uuid.uuid4())
            agendamento = {
                "id": id_agendamento,
                "id_usuario": dados.get("id_usuario"),
                "id_trilha": dados.get("id_trilha"),
                "id_guia": id_guia,
                "data_agendada": dados.get("data_agendada"),
                "valor_pago": dados.get("valor_pago"),
                "status": "agendado",
                "createdAt": firestore.SERVER_TIMESTAMP
            }

            db.collection('agendamentos').document(id_agendamento).set(agendamento)
            return {"mensagem": "Agendamento realizado com sucesso!", "id": id_agendamento}, 201
        except Exception as e:
            return {"erro": f"Erro interno: {str(e)}"}, 500

    @staticmethod
    def listar_agendamentos_usuario(db, id_usuario):
        try:
            ref = db.collection('agendamentos').where('id_usuario', '==', id_usuario).stream()
            lista = [doc.to_dict() for doc in ref]
            return lista, 200
        except Exception as e:
            return {"erro": f"Erro ao buscar agendamentos: {str(e)}"}, 500

    @staticmethod
    def listar_agendamentos_guia(db, id_guia):
        try:
            ref = db.collection('agendamentos').where('id_guia', '==', id_guia).stream()
            lista = [doc.to_dict() for doc in ref]
            return lista, 200
        except Exception as e:
            return {"erro": f"Erro ao buscar agendamentos: {str(e)}"}, 500

    @staticmethod
    def cancelar_agendamento(db, id_agendamento, usuario_atual):
        try:
            doc_ref = db.collection('agendamentos').document(id_agendamento)
            doc = doc_ref.get()

            if not doc.exists:
                return {"erro": "Agendamento não encontrado"}, 404

            if not Agendamentos._usuario_pode_gerenciar_agendamento(doc.to_dict(), usuario_atual):
                return {"erro": "Acesso negado. Você não tem permissão para cancelar este agendamento."}, 403

            doc_ref.update({"status": "cancelado"})
            return {"mensagem": "agendamento cancelado com sucesso !"}, 200
        except Exception as e:
            return {"erro": f"Erro ao cancelar agendamento: {str(e)}"}, 500

    @staticmethod
    def fazer_checkin(db, id_agendamento, usuario_atual, latitude=None, longitude=None):
        try:
            doc_ref = db.collection('agendamentos').document(id_agendamento)
            doc = doc_ref.get()
            if not doc.exists:
                return {"erro": "Agendamento não encontrado"}, 404

            dados = doc.to_dict()
            if not Agendamentos._usuario_pode_gerenciar_agendamento(dados, usuario_atual):
                return {"erro": "Acesso negado."}, 403

            if dados.get('status') != 'agendado':
                return {"erro": f"Não é possível fazer check-in: status atual é '{dados.get('status')}'."}, 400

            atualizacao = {
                "status": "em_andamento",
                "checkin_at": firestore.SERVER_TIMESTAMP,
            }
            if latitude is not None and longitude is not None:
                atualizacao["checkin_latitude"] = latitude
                atualizacao["checkin_longitude"] = longitude

            doc_ref.update(atualizacao)
            return {"mensagem": "Check-in realizado! Boa trilha e cuidado no percurso."}, 200
        except Exception as e:
            return {"erro": f"Erro ao fazer check-in: {str(e)}"}, 500

    @staticmethod
    def fazer_checkout(db, id_agendamento, usuario_atual):
        try:
            doc_ref = db.collection('agendamentos').document(id_agendamento)
            doc = doc_ref.get()
            if not doc.exists:
                return {"erro": "Agendamento não encontrado"}, 404

            dados = doc.to_dict()
            if not Agendamentos._usuario_pode_gerenciar_agendamento(dados, usuario_atual):
                return {"erro": "Acesso negado."}, 403

            if dados.get('status') != 'em_andamento':
                return {"erro": f"Não é possível fazer check-out: status atual é '{dados.get('status')}'. Faça check-in primeiro."}, 400

            doc_ref.update({
                "status": "concluido",
                "checkout_at": firestore.SERVER_TIMESTAMP,
            })
            return {"mensagem": "Check-out realizado! Trilha concluída com sucesso."}, 200
        except Exception as e:
            return {"erro": f"Erro ao fazer check-out: {str(e)}"}, 500
    @staticmethod
    def dashboard_guia(db, id_guia):
        """Valores declarados nas reservas; não representam pagamentos conciliados."""
        from decimal import Decimal, InvalidOperation
        aliases = {id_guia}
        user = db.collection('usuarios').document(id_guia).get()
        if user.exists and user.to_dict().get('email'):
            aliases.add(user.to_dict()['email'])
        elif not user.exists:
            for doc in db.collection('usuarios').where('email', '==', id_guia).stream():
                aliases.add(doc.id)
        rows = {}
        for alias in aliases:
            for doc in db.collection('agendamentos').where('id_guia', '==', alias).stream():
                rows[doc.id] = doc.to_dict()
        counts = {key: 0 for key in ('agendado', 'em_andamento', 'concluido', 'cancelado', 'outros')}
        amount = Decimal('0')
        for item in rows.values():
            status = item.get('status')
            counts[status if status in counts else 'outros'] += 1
            if status not in ('agendado', 'em_andamento', 'concluido'):
                continue
            try:
                value = Decimal(str(item.get('valor_pago', 0)))
                if value.is_finite() and value >= 0:
                    amount += value
            except (InvalidOperation, ValueError):
                pass
        return {'total_agendamentos': len(rows), 'por_status': counts,
                'valor_declarado_ativo': float(amount.quantize(Decimal('0.01')))}, 200
