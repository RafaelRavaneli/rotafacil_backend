from firebase_admin import firestore


class Avaliacoes:
    @staticmethod
    def _gerar_id_avaliacao(id_usuario, id_trilha):
        return f"{id_usuario}__{id_trilha}"

    @staticmethod
    def _usuario_completou_trilha(db, id_usuario, id_trilha):
        agendamentos_ref = db.collection('agendamentos') \
            .where('id_usuario', '==', id_usuario) \
            .where('id_trilha', '==', id_trilha) \
            .where('status', '==', 'concluido').stream()
        return any(True for _ in agendamentos_ref)

    @staticmethod
    def _recalcular_media_trilha(db, id_trilha):
        avaliacoes_ref = db.collection('avaliacoes').where('id_trilha', '==', id_trilha).stream()
        notas = [doc.to_dict().get('nota', 0) for doc in avaliacoes_ref]

        if notas:
            media = round(sum(notas) / len(notas), 1)
            total = len(notas)
        else:
            media = None
            total = 0

        db.collection('trilhas').document(id_trilha).update({
            "nota_media": media,
            "total_avaliacoes": total
        })

    @staticmethod
    def adicionar_avaliacao(db, id_usuario, id_trilha, nota, comentario, nome_usuario):
        try:
            if not id_trilha:
                return {"erro": "id_trilha é obrigatório"}, 400

            try:
                nota = int(nota)
            except (TypeError, ValueError):
                return {"erro": "nota deve ser um número inteiro"}, 400

            if nota < 1 or nota > 5:
                return {"erro": "nota deve estar entre 1 e 5"}, 400

            trilha_ref = db.collection('trilhas').document(id_trilha).get()
            if not trilha_ref.exists:
                return {"erro": "Trilha não encontrada"}, 404

            if not Avaliacoes._usuario_completou_trilha(db, id_usuario, id_trilha):
                return {"erro": "Só é possível avaliar trilhas que você já concluiu (com check-out registrado)."}, 403

            id_avaliacao = Avaliacoes._gerar_id_avaliacao(id_usuario, id_trilha)
            doc_ref = db.collection('avaliacoes').document(id_avaliacao)

            if doc_ref.get().exists:
                return {"erro": "Você já avaliou esta trilha"}, 409

            doc_ref.set({
                "id_usuario": id_usuario,
                "id_trilha": id_trilha,
                "nome_usuario": nome_usuario,
                "nota": nota,
                "comentario": comentario,
                "createdAt": firestore.SERVER_TIMESTAMP
            })

            Avaliacoes._recalcular_media_trilha(db, id_trilha)

            return {"mensagem": "Avaliação registrada com sucesso!"}, 201
        except Exception as e:
            return {"erro": f"Erro ao registrar avaliação: {str(e)}"}, 500

    @staticmethod
    def listar_avaliacoes_trilha(db, id_trilha):
        try:
            avaliacoes_ref = db.collection('avaliacoes').where('id_trilha', '==', id_trilha).stream()
            avaliacoes = [doc.to_dict() for doc in avaliacoes_ref]
            return avaliacoes, 200
        except Exception as e:
            return {"erro": f"Erro ao buscar avaliações: {str(e)}"}, 500