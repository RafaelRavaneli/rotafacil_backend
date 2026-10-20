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
        notas = [
            (doc.to_dict() or {}).get(
                'nota_roteiro', (doc.to_dict() or {}).get('nota', 0))
            for doc in avaliacoes_ref
        ]

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
    def _usuario_por_identificador(db, identificador):
        if not identificador:
            return None, {}
        documento = db.collection('usuarios').document(str(identificador)).get()
        if documento.exists:
            return documento.reference, documento.to_dict() or {}
        documento = next(iter(db.collection('usuarios').where(
            'email', '==', identificador).stream()), None)
        return ((documento.reference, documento.to_dict() or {})
                if documento is not None and documento.exists else (None, {}))

    @staticmethod
    def _recalcular_media_responsavel(db, id_responsavel, campo_nota):
        referencia, _ = Avaliacoes._usuario_por_identificador(
            db, id_responsavel)
        if referencia is None:
            return
        notas = []
        for doc in db.collection('avaliacoes').where(
                f'id_{"guia" if campo_nota == "nota_guia" else "agencia"}',
                '==', referencia.id).stream():
            nota = (doc.to_dict() or {}).get(campo_nota)
            if isinstance(nota, (int, float)):
                notas.append(nota)
        referencia.update({
            'nota_media': round(sum(notas) / len(notas), 1) if notas else None,
            'total_avaliacoes': len(notas),
        })

    @staticmethod
    def _normalizar_nota(valor, campo):
        try:
            nota = int(valor)
        except (TypeError, ValueError):
            raise ValueError(f'{campo} deve ser um número inteiro')
        if nota < 0 or nota > 5:
            raise ValueError(f'{campo} deve estar entre 0 e 5')
        return nota

    @staticmethod
    def adicionar_avaliacao(db, id_usuario, id_trilha, nota, comentario,
                            nome_usuario, id_agendamento=None,
                            nota_guia=None, nota_agencia=None):
        try:
            if not id_trilha:
                return {"erro": "id_trilha é obrigatório"}, 400

            try:
                nota = Avaliacoes._normalizar_nota(nota, 'nota_roteiro')
            except ValueError as error:
                return {"erro": str(error)}, 400

            if comentario is None:
                comentario = ''
            if not isinstance(comentario, str) or len(comentario.strip()) > 500:
                return {"erro": "comentario deve ser um texto de até 500 caracteres"}, 400
            comentario = comentario.strip()

            trilha_ref = db.collection('trilhas').document(id_trilha).get()
            if not trilha_ref.exists:
                return {"erro": "Roteiro não encontrado"}, 404

            dados_trilha = trilha_ref.to_dict() or {}
            reserva = None
            if id_agendamento:
                reserva_doc = db.collection('agendamentos').document(
                    str(id_agendamento)).get()
                if reserva_doc.exists:
                    candidato = reserva_doc.to_dict() or {}
                    if (candidato.get('id_usuario') == id_usuario and
                            candidato.get('id_trilha') == id_trilha):
                        reserva = candidato
                if reserva is None:
                    return {"erro": "Reserva não encontrada para esta avaliação."}, 404
                if str(reserva.get('status') or '').lower() != 'concluido':
                    return {"erro": "A avaliação será liberada quando o responsável finalizar o roteiro."}, 403
            elif not Avaliacoes._usuario_completou_trilha(
                    db, id_usuario, id_trilha):
                return {"erro": "A avaliação será liberada quando o responsável finalizar o roteiro."}, 403

            guia_id = (reserva or {}).get('id_guia') or dados_trilha.get('id_guia')
            guia_ref, _ = Avaliacoes._usuario_por_identificador(db, guia_id)
            guia_id = guia_ref.id if guia_ref is not None else None
            criador_ref, criador = Avaliacoes._usuario_por_identificador(
                db, dados_trilha.get('criado_por'))
            agencia_id = (criador_ref.id if criador_ref is not None and
                           str(criador.get('tipo') or '').lower() == 'agencia'
                           else None)
            if guia_id:
                try:
                    nota_guia = Avaliacoes._normalizar_nota(
                        nota_guia, 'nota_guia')
                except ValueError as error:
                    return {"erro": str(error)}, 400
            if agencia_id:
                try:
                    nota_agencia = Avaliacoes._normalizar_nota(
                        nota_agencia, 'nota_agencia')
                except ValueError as error:
                    return {"erro": str(error)}, 400

            id_avaliacao = (str(id_agendamento) if id_agendamento else
                            Avaliacoes._gerar_id_avaliacao(id_usuario, id_trilha))
            doc_ref = db.collection('avaliacoes').document(id_avaliacao)

            if doc_ref.get().exists:
                return {"erro": "Você já avaliou este roteiro"}, 409

            doc_ref.set({
                "id_usuario": id_usuario,
                "id_trilha": id_trilha,
                "id_agendamento": id_agendamento,
                "id_guia": guia_id,
                "id_agencia": agencia_id,
                "nome_usuario": nome_usuario,
                "nota": nota,
                "nota_roteiro": nota,
                "nota_guia": nota_guia,
                "nota_agencia": nota_agencia,
                "comentario": comentario,
                "createdAt": firestore.SERVER_TIMESTAMP
            })

            Avaliacoes._recalcular_media_trilha(db, id_trilha)
            if guia_id:
                Avaliacoes._recalcular_media_responsavel(
                    db, guia_id, 'nota_guia')
            if agencia_id:
                Avaliacoes._recalcular_media_responsavel(
                    db, agencia_id, 'nota_agencia')

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
