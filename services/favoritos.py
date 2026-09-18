from firebase_admin import firestore


class Favoritos:
    @staticmethod
    def _gerar_id_favorito(id_usuario, id_trilha):
        return f"{id_usuario}__{id_trilha}"

    @staticmethod
    def adicionar_favorito(db, id_usuario, id_trilha):
        try:
            if not id_trilha:
                return {"erro": "id_trilha é obrigatório"}, 400

            trilha_ref = db.collection('trilhas').document(id_trilha).get()
            if not trilha_ref.exists:
                return {"erro": "Trilha não encontrada"}, 404

            id_favorito = Favoritos._gerar_id_favorito(id_usuario, id_trilha)
            doc_ref = db.collection('favoritos').document(id_favorito)

            if doc_ref.get().exists:
                return {"mensagem": "Essa trilha já está nos seus favoritos"}, 200

            doc_ref.set({
                "id_usuario": id_usuario,
                "id_trilha": id_trilha,
                "createdAt": firestore.SERVER_TIMESTAMP
            })
            return {"mensagem": "Trilha adicionada aos favoritos!"}, 201
        except Exception as e:
            return {"erro": f"Erro ao adicionar favorito: {str(e)}"}, 500

    @staticmethod
    def remover_favorito(db, id_usuario, id_trilha):
        try:
            id_favorito = Favoritos._gerar_id_favorito(id_usuario, id_trilha)
            doc_ref = db.collection('favoritos').document(id_favorito)

            if not doc_ref.get().exists:
                return {"erro": "Essa trilha não está nos seus favoritos"}, 404

            doc_ref.delete()
            return {"mensagem": "Trilha removida dos favoritos"}, 200
        except Exception as e:
            return {"erro": f"Erro ao remover favorito: {str(e)}"}, 500

    @staticmethod
    def listar_favoritos(db, id_usuario):
        try:
            favoritos_ref = db.collection('favoritos').where('id_usuario', '==', id_usuario).stream()

            trilhas = []
            for doc in favoritos_ref:
                id_trilha = doc.to_dict().get('id_trilha')
                trilha_doc = db.collection('trilhas').document(id_trilha).get()
                if trilha_doc.exists:
                    trilhas.append(trilha_doc.to_dict())

            return trilhas, 200
        except Exception as e:
            return {"erro": f"Erro ao listar favoritos: {str(e)}"}, 500