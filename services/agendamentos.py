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
                
            id_agendamento = str(uuid.uuid4())
            agendamento = {
                "id": id_agendamento,
                "id_usuario": dados.get("id_usuario"),
                "id_trilha": dados.get("id_trilha"),
                "id_guia": dados.get("id_guia"),
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
    def cancelar_agendamento(db, id_agendamento):
        try:
            doc_ref = db.collection('agendamentos').document(id_agendamento)
            if not doc_ref.get().exists:
                return {"erro": "Agendamento não encontrado"}, 404
                
            doc_ref.update({"status": "cancelado"})
            return {"mensagem": "agendamento cancelado com sucesso !"}, 200
        except Exception as e:
            return {"erro": f"Erro ao cancelar agendamento: {str(e)}"}, 500