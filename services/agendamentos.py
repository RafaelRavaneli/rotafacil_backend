import uuid
from firebase_admin import firestore

class Agendamentos:
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

            dados_agendamento = doc.to_dict()
            id_usuario_dono = dados_agendamento.get('id_usuario')
            id_guia_responsavel = dados_agendamento.get('id_guia')

            papel = (usuario_atual.get('tipo') or '').strip().lower()
            usuario_id = usuario_atual.get('id')

            eh_admin = papel == 'admin'
            eh_dono_do_agendamento = usuario_id == id_usuario_dono
            eh_guia_responsavel = usuario_id == id_guia_responsavel

            if not (eh_admin or eh_dono_do_agendamento or eh_guia_responsavel):
                return {"erro": "Acesso negado. Você não tem permissão para cancelar este agendamento."}, 403

            doc_ref.update({"status": "cancelado"})
            return {"mensagem": "agendamento cancelado com sucesso !"}, 200
        except Exception as e:
            return {"erro": f"Erro ao cancelar agendamento: {str(e)}"}, 500

    @staticmethod
    def dashboard_guia(db, id_guia):
        try:
            guia_doc = db.collection('usuarios').document(id_guia).get()
            identificadores = [id_guia]
            if guia_doc.exists:
                email_guia = guia_doc.to_dict().get('email')
                if email_guia:
                    identificadores.append(email_guia)

            agendamentos_ref = db.collection('agendamentos').where('id_guia', 'in', identificadores).stream()
            agendamentos = [doc.to_dict() for doc in agendamentos_ref]

            cancelados = [a for a in agendamentos if a.get('status') == 'cancelado']
            confirmados = [a for a in agendamentos if a.get('status') != 'cancelado']
            receita_total = sum(float(a.get('valor_pago') or 0) for a in confirmados)

            contagem_por_trilha = {}
            for a in confirmados:
                id_trilha = a.get('id_trilha')
                if id_trilha:
                    contagem_por_trilha[id_trilha] = contagem_por_trilha.get(id_trilha, 0) + 1

            trilha_mais_agendada = None
            if contagem_por_trilha:
                id_trilha_top = max(contagem_por_trilha, key=contagem_por_trilha.get)
                trilha_doc = db.collection('trilhas').document(id_trilha_top).get()
                if trilha_doc.exists:
                    trilha_mais_agendada = {
                        "id": id_trilha_top,
                        "nome": trilha_doc.to_dict().get('nome'),
                        "total_agendamentos": contagem_por_trilha[id_trilha_top]
                    }

            trilhas_ref = db.collection('trilhas').where('id_guia', 'in', identificadores).stream()
            total_trilhas_criadas = sum(1 for _ in trilhas_ref)

            return {
                "total_trilhas_criadas": total_trilhas_criadas,
                "total_agendamentos": len(agendamentos),
                "agendamentos_confirmados": len(confirmados),
                "agendamentos_cancelados": len(cancelados),
                "receita_total": round(receita_total, 2),
                "trilha_mais_agendada": trilha_mais_agendada
            }, 200
        except Exception as e:
            return {"erro": f"Erro ao gerar dashboard: {str(e)}"}, 500