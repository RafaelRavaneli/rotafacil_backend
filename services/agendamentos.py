import uuid
from datetime import date
from firebase_admin import firestore
from services.notificacoes import Notificacoes

class Agendamentos:
    STATUS_ATIVOS = {'agendado', 'pendente', 'confirmado', 'em_andamento'}

    @staticmethod
    def _status_ativo(status):
        return str(status or '').strip().lower() in Agendamentos.STATUS_ATIVOS

    @staticmethod
    def _usuario_por_identificador(db, identificador):
        if not identificador:
            return None, {}
        documento = db.collection('usuarios').document(str(identificador)).get()
        if documento.exists:
            return documento.id, documento.to_dict() or {}
        documento = next(iter(db.collection('usuarios').where(
            'email', '==', identificador).stream()), None)
        return ((documento.id, documento.to_dict() or {})
                if documento is not None and documento.exists else (None, {}))

    @staticmethod
    def _serializar(db, dados, usuarios=None, trilhas=None):
        item = dict(dados or {})
        usuarios = usuarios if usuarios is not None else {}
        trilhas = trilhas if trilhas is not None else {}
        usuario_id = item.get('id_usuario')
        trilha_id = item.get('id_trilha')
        if usuario_id and usuario_id not in usuarios:
            doc = db.collection('usuarios').document(usuario_id).get()
            usuarios[usuario_id] = (doc.to_dict() or {}) if doc.exists else {}
        if trilha_id and trilha_id not in trilhas:
            doc = db.collection('trilhas').document(trilha_id).get()
            trilhas[trilha_id] = (doc.to_dict() or {}) if doc.exists else {}
        participante = usuarios.get(usuario_id) or {}
        item['nome_usuario'] = participante.get('nome')
        item['telefone_participante'] = participante.get('telefone')
        dados_trilha = trilhas.get(trilha_id) or {}
        item['nome_trilha'] = dados_trilha.get('nome')
        guia_id, guia = Agendamentos._usuario_por_identificador(
            db, item.get('id_guia'))
        item['id_guia'] = guia_id or item.get('id_guia')
        item['nome_guia'] = guia.get('nome')
        item['telefone_guia'] = guia.get('telefone')
        agencia_id, agencia = Agendamentos._usuario_por_identificador(
            db, dados_trilha.get('criado_por'))
        if str(agencia.get('tipo') or '').strip().lower() == 'agencia':
            item['id_agencia'] = agencia_id
            item['nome_agencia'] = agencia.get('nome')
        item['avaliado'] = bool(item.get('id') and db.collection(
            'avaliacoes').document(str(item.get('id'))).get().exists)
        for campo in ('createdAt', 'cancelado_em'):
            valor = item.get(campo)
            if hasattr(valor, 'isoformat'):
                item[campo] = valor.isoformat()
        return item

    @staticmethod
    def _ordenar_para_exibicao(lista):
        """Exibe reservas ativas primeiro e as mais recentes no topo."""
        def criada_em(item):
            valor = item.get('createdAt')
            return valor.isoformat() if hasattr(valor, 'isoformat') else str(valor or '')

        ativas = [item for item in lista if Agendamentos._status_ativo(item.get('status'))]
        historico = [item for item in lista if not Agendamentos._status_ativo(item.get('status'))]
        ativas.sort(key=criada_em, reverse=True)
        historico.sort(key=criada_em, reverse=True)
        return ativas + historico

    @staticmethod
    def _usuario_pode_gerenciar_agendamento(db, dados_agendamento, usuario_atual):
        papel = (usuario_atual.get('tipo') or '').strip().lower()
        usuario_id = usuario_atual.get('id')
        eh_admin = papel == 'admin'
        eh_dono = usuario_id == dados_agendamento.get('id_usuario')
        eh_guia_responsavel = dados_agendamento.get('id_guia') in {usuario_id, usuario_atual.get('email')} - {None, ''}
        eh_agencia_proprietaria = False
        if papel == 'agencia':
            trilha = db.collection('trilhas').document(
                dados_agendamento.get('id_trilha')).get()
            aliases = {usuario_id, usuario_atual.get('email')} - {None, ''}
            eh_agencia_proprietaria = (
                trilha.exists and
                (trilha.to_dict() or {}).get('criado_por') in aliases
            )
        return (eh_admin or eh_dono or eh_guia_responsavel or
                eh_agencia_proprietaria)

    @staticmethod
    def _usuario_pode_operar_agendamento(db, dados_agendamento, usuario_atual):
        papel = (usuario_atual.get('tipo') or '').strip().lower()
        usuario_id = usuario_atual.get('id')
        if papel == 'admin':
            return True
        if papel == 'guia':
            aliases = {usuario_id, usuario_atual.get('email')} - {None, ''}
            return dados_agendamento.get('id_guia') in aliases
        if papel == 'agencia':
            trilha = db.collection('trilhas').document(
                dados_agendamento.get('id_trilha')).get()
            aliases = {usuario_id, usuario_atual.get('email')} - {None, ''}
            return (trilha.exists and
                    (trilha.to_dict() or {}).get('criado_por') in aliases)
        return False

    @staticmethod
    def agendar_trilha(db, dados):
        try:
            if not dados:
                return {"erro": "Dados não enviados"}, 400

            campos_obrigatorios = ["id_usuario", "id_trilha", "data_agendada"]
            for campo in campos_obrigatorios:
                if campo not in dados:
                    return {"erro": f"Campo obrigatório: {campo}"}, 400

            trilha_ref = db.collection('trilhas').document(dados['id_trilha']).get()
            if not trilha_ref.exists:
                return {"erro": "Roteiro não encontrado. Verifique o id_trilha informado."}, 404

            dados_trilha = trilha_ref.to_dict()
            if dados_trilha.get('ativo') is False:
                return {"erro": "Este roteiro não está disponível para agendamento."}, 409
            id_guia = dados_trilha.get("id_guia")

            data_agendada = str(dados.get('data_agendada') or '').strip()
            id_data = str(dados.get('id_data') or '').strip()
            datas = dados_trilha.get('datas') or []
            data_selecionada = None
            if datas:
                if not id_data:
                    return {"erro": "Selecione uma data disponível para este roteiro."}, 400
                data_selecionada = next(
                    (item for item in datas if str(item.get('id')) == id_data), None)
                if data_selecionada is None:
                    return {"erro": "A data selecionada não pertence mais a este roteiro."}, 409
                data_agendada = str(data_selecionada.get('data_hora_inicio') or '')[:10]
            try:
                if date.fromisoformat(data_agendada) < date.today():
                    return {"erro": "Não é possível reservar uma data passada."}, 400
            except ValueError:
                return {"erro": "data_agendada deve estar no formato AAAA-MM-DD."}, 400

            existentes = db.collection('agendamentos') \
                .where('id_usuario', '==', dados['id_usuario']) \
                .where('id_trilha', '==', dados['id_trilha']).stream()
            if any(
                Agendamentos._status_ativo(doc.to_dict().get('status')) and
                ((id_data and doc.to_dict().get('id_data') == id_data) or
                 (not id_data and doc.to_dict().get('data_agendada') == data_agendada))
                for doc in existentes
            ):
                return {"erro": "Você já possui uma reserva ativa para esta data."}, 409

            capacidade = dados_trilha.get('capacidade')
            if capacidade is not None:
                try:
                    capacidade = int(capacidade)
                except (TypeError, ValueError):
                    return {"erro": "A capacidade da atividade está inválida."}, 500
                ocupadas = sum(
                    1 for doc in db.collection('agendamentos')
                    .where('id_trilha', '==', dados['id_trilha'])
                    .where('data_agendada', '==', data_agendada).stream()
                    if Agendamentos._status_ativo(doc.to_dict().get('status'))
                )
                if capacidade > 0 and ocupadas >= capacidade:
                    return {"erro": "Não há vagas disponíveis para esta atividade."}, 409

            id_agendamento = str(uuid.uuid4())
            agendamento = {
                "id": id_agendamento,
                "id_usuario": dados.get("id_usuario"),
                "id_trilha": dados.get("id_trilha"),
                "id_guia": id_guia,
                "id_data": id_data or None,
                "data_agendada": data_agendada,
                "data_hora_inicio": (data_selecionada or {}).get('data_hora_inicio') or
                                    dados_trilha.get('data_hora_inicio'),
                "data_hora_fim": (data_selecionada or {}).get('data_hora_fim') or
                                 dados_trilha.get('data_hora_fim'),
                "valor_pago": dados_trilha.get('preco', 0),
                "status": "pendente",
                "createdAt": firestore.SERVER_TIMESTAMP
            }

            db.collection('agendamentos').document(id_agendamento).set(agendamento)

            Notificacoes.notificar_usuario(
                db, id_guia,
                "Novo agendamento recebido!",
                f"Você recebeu um novo agendamento para o roteiro '{dados_trilha.get('nome')}'.",
                dados={"tipo": "novo_agendamento", "id_agendamento": id_agendamento}
            )

            return {"mensagem": "Agendamento realizado com sucesso!", "id": id_agendamento}, 201
        except Exception as e:
            return {"erro": f"Erro interno: {str(e)}"}, 500

    @staticmethod
    def listar_agendamentos_usuario(db, id_usuario):
        try:
            ref = db.collection('agendamentos').where('id_usuario', '==', id_usuario).stream()
            usuarios, trilhas = {}, {}
            lista = [Agendamentos._serializar(db, doc.to_dict(), usuarios, trilhas) for doc in ref]
            return Agendamentos._ordenar_para_exibicao(lista), 200
        except Exception as e:
            return {"erro": f"Erro ao buscar agendamentos: {str(e)}"}, 500

    @staticmethod
    def _identificadores_guia(db, id_guia):
        """Resolve referências atuais e legadas sem depender de uma segunda chamada do cliente."""
        aliases = {id_guia}
        user = db.collection('usuarios').document(id_guia).get()
        if user.exists:
            email = (user.to_dict() or {}).get('email')
            if email:
                aliases.add(email)
        else:
            for doc in db.collection('usuarios').where('email', '==', id_guia).stream():
                aliases.add(doc.id)
        return aliases

    @staticmethod
    def listar_agendamentos_guia(db, id_guia):
        try:
            rows = {}
            for alias in Agendamentos._identificadores_guia(db, id_guia):
                for doc in db.collection('agendamentos').where('id_guia', '==', alias).stream():
                    rows[doc.id] = doc.to_dict()
            usuarios, trilhas = {}, {}
            lista = [Agendamentos._serializar(db, row, usuarios, trilhas) for row in rows.values()]
            return Agendamentos._ordenar_para_exibicao(lista), 200
        except Exception as e:
            return {"erro": f"Erro ao buscar agendamentos: {str(e)}"}, 500

    @staticmethod
    def listar_agendamentos_agencia(db, usuario_atual):
        try:
            aliases = {usuario_atual.get('id'), usuario_atual.get('email')} - {None, ''}
            agency_id = usuario_atual.get('id')
            if agency_id and not usuario_atual.get('email'):
                agency = db.collection('usuarios').document(agency_id).get()
                if agency.exists:
                    email = (agency.to_dict() or {}).get('email')
                    if email:
                        aliases.add(email)
            trilhas_ids = set()
            for alias in aliases:
                for doc in db.collection('trilhas').where('criado_por', '==', alias).stream():
                    trilhas_ids.add(doc.id)
            rows = {}
            for trilha_id in trilhas_ids:
                for doc in db.collection('agendamentos').where('id_trilha', '==', trilha_id).stream():
                    rows[doc.id] = doc.to_dict()
            usuarios, trilhas = {}, {}
            lista = [Agendamentos._serializar(db, row, usuarios, trilhas) for row in rows.values()]
            return Agendamentos._ordenar_para_exibicao(lista), 200
        except Exception as e:
            return {"erro": f"Erro ao buscar agendamentos da agência: {str(e)}"}, 500

    @staticmethod
    def cancelar_agendamento(db, id_agendamento, usuario_atual):
        try:
            doc_ref = db.collection('agendamentos').document(id_agendamento)
            doc = doc_ref.get()

            if not doc.exists:
                return {"erro": "Agendamento não encontrado"}, 404

            dados = doc.to_dict()
            if not Agendamentos._usuario_pode_gerenciar_agendamento(db, dados, usuario_atual):
                return {"erro": "Acesso negado. Você não tem permissão para cancelar este agendamento."}, 403

            status_atual = str(dados.get('status') or '').strip().lower()
            if status_atual not in {'agendado', 'pendente', 'confirmado'}:
                return {
                    "erro": "Somente reservas ainda não iniciadas podem ser canceladas."
                }, 409

            doc_ref.update({
                "status": "cancelado",
                "cancelado_em": firestore.SERVER_TIMESTAMP,
                "cancelado_por": usuario_atual.get('id'),
            })

            quem_cancelou = usuario_atual.get('id')
            id_usuario_agendamento = dados.get('id_usuario')
            id_guia_agendamento = dados.get('id_guia')

            trilha_doc = db.collection('trilhas').document(dados.get('id_trilha')).get()
            nome_trilha = trilha_doc.to_dict().get('nome') if trilha_doc.exists else 'um roteiro'

            if quem_cancelou == id_usuario_agendamento:
                Notificacoes.notificar_usuario(
                    db, id_guia_agendamento,
                    "Agendamento cancelado",
                    f"Um participante cancelou o agendamento no roteiro '{nome_trilha}'.",
                    dados={"tipo": "cancelamento", "id_agendamento": id_agendamento}
                )
            else:
                Notificacoes.notificar_usuario(
                    db, id_usuario_agendamento,
                    "Agendamento cancelado",
                    f"Seu agendamento no roteiro '{nome_trilha}' foi cancelado.",
                    dados={"tipo": "cancelamento", "id_agendamento": id_agendamento}
                )

            return {"mensagem": "agendamento cancelado com sucesso !"}, 200
        except Exception as e:
            return {"erro": f"Erro ao cancelar agendamento: {str(e)}"}, 500

    @staticmethod
    def responder_agendamento(db, id_agendamento, usuario_atual, resposta):
        try:
            resposta = str(resposta or '').strip().lower()
            if resposta not in {'confirmado', 'recusado'}:
                return {"erro": "Use status confirmado ou recusado."}, 400
            doc_ref = db.collection('agendamentos').document(id_agendamento)
            doc = doc_ref.get()
            if not doc.exists:
                return {"erro": "Agendamento não encontrado"}, 404
            dados = doc.to_dict() or {}
            if not Agendamentos._usuario_pode_operar_agendamento(
                    db, dados, usuario_atual):
                return {"erro": "Acesso negado."}, 403
            if str(dados.get('status') or '').strip().lower() != 'pendente':
                return {"erro": "Esta solicitação já foi respondida."}, 409
            doc_ref.update({
                'status': resposta,
                'respondido_em': firestore.SERVER_TIMESTAMP,
                'respondido_por': usuario_atual.get('id'),
            })
            trilha = db.collection('trilhas').document(
                dados.get('id_trilha')).get()
            nome = (trilha.to_dict() or {}).get('nome') if trilha.exists else 'roteiro'
            titulo = ('Reserva confirmada' if resposta == 'confirmado'
                      else 'Reserva recusada')
            Notificacoes.notificar_usuario(
                db, dados.get('id_usuario'), titulo,
                f"Sua solicitação para '{nome}' foi {resposta}.",
                dados={'tipo': 'resposta_agendamento',
                       'id_agendamento': id_agendamento})
            return {"mensagem": f"Agendamento {resposta} com sucesso."}, 200
        except Exception as e:
            return {"erro": f"Erro ao responder agendamento: {str(e)}"}, 500

    @staticmethod
    def finalizar_saida(db, id_trilha, id_data, data_agendada, usuario_atual):
        try:
            trilha_doc = db.collection('trilhas').document(id_trilha).get()
            if not trilha_doc.exists:
                return {"erro": "Roteiro não encontrado"}, 404
            trilha = trilha_doc.to_dict() or {}
            amostra = {'id_trilha': id_trilha, 'id_guia': trilha.get('id_guia')}
            if not Agendamentos._usuario_pode_operar_agendamento(
                    db, amostra, usuario_atual):
                return {"erro": "Acesso negado."}, 403
            id_data = str(id_data or '').strip()
            data_agendada = str(data_agendada or '').strip()
            if not id_data and not data_agendada:
                return {"erro": "Informe a data do roteiro que foi finalizada."}, 400
            reservas = []
            for doc in db.collection('agendamentos').where(
                    'id_trilha', '==', id_trilha).stream():
                dados = doc.to_dict() or {}
                mesma_saida = (dados.get('id_data') == id_data if id_data
                               else dados.get('data_agendada') == data_agendada)
                if mesma_saida and str(dados.get('status') or '').lower() in {
                        'confirmado', 'agendado', 'em_andamento'}:
                    reservas.append((doc.reference, dados))
            if not reservas:
                return {"erro": "Nenhuma reserva confirmada nesta data."}, 409
            for referencia, dados in reservas:
                referencia.update({
                    'status': 'concluido',
                    'finalizado_em': firestore.SERVER_TIMESTAMP,
                    'finalizado_por': usuario_atual.get('id'),
                })
                Notificacoes.notificar_usuario(
                    db, dados.get('id_usuario'), 'Roteiro finalizado',
                    f"O roteiro '{trilha.get('nome', 'Roteiro')}' foi finalizado. Sua avaliação já está disponível.",
                    dados={'tipo': 'roteiro_finalizado',
                           'id_agendamento': dados.get('id')})
            return {"mensagem": "Saída finalizada com sucesso.",
                    "reservas_finalizadas": len(reservas)}, 200
        except Exception as e:
            return {"erro": f"Erro ao finalizar a saída: {str(e)}"}, 500

    @staticmethod
    def fazer_checkin(db, id_agendamento, usuario_atual, latitude=None, longitude=None):
        try:
            doc_ref = db.collection('agendamentos').document(id_agendamento)
            doc = doc_ref.get()
            if not doc.exists:
                return {"erro": "Agendamento não encontrado"}, 404

            dados = doc.to_dict()
            if not Agendamentos._usuario_pode_operar_agendamento(db, dados, usuario_atual):
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
            return {"mensagem": "Check-in realizado! Bom roteiro e cuidado no percurso."}, 200
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
            if not Agendamentos._usuario_pode_operar_agendamento(db, dados, usuario_atual):
                return {"erro": "Acesso negado."}, 403

            if dados.get('status') != 'em_andamento':
                return {"erro": f"Não é possível fazer check-out: status atual é '{dados.get('status')}'. Faça check-in primeiro."}, 400

            doc_ref.update({
                "status": "concluido",
                "checkout_at": firestore.SERVER_TIMESTAMP,
            })
            return {"mensagem": "Check-out realizado! Roteiro concluído com sucesso."}, 200
        except Exception as e:
            return {"erro": f"Erro ao fazer check-out: {str(e)}"}, 500
    @staticmethod
    def dashboard_guia(db, id_guia):
        """Valores declarados nas reservas; não representam pagamentos conciliados."""
        from decimal import Decimal, InvalidOperation
        aliases = Agendamentos._identificadores_guia(db, id_guia)
        rows = {}
        user = db.collection('usuarios').document(id_guia).get()
        role = (user.to_dict() or {}).get('tipo') if user.exists else None
        if role == 'agencia':
            trail_ids = set()
            for alias in aliases:
                for trail in db.collection('trilhas').where(
                        'criado_por', '==', alias).stream():
                    trail_ids.add(trail.id)
            for trail_id in trail_ids:
                for doc in db.collection('agendamentos').where(
                        'id_trilha', '==', trail_id).stream():
                    rows[doc.id] = doc.to_dict()
        else:
            for alias in aliases:
                for doc in db.collection('agendamentos').where(
                        'id_guia', '==', alias).stream():
                    rows[doc.id] = doc.to_dict()
        counts = {key: 0 for key in (
            'pendente', 'agendado', 'confirmado', 'em_andamento',
            'concluido', 'cancelado', 'outros')}
        amount = Decimal('0')
        for item in rows.values():
            status = item.get('status')
            counts[status if status in counts else 'outros'] += 1
            if status not in Agendamentos.STATUS_ATIVOS | {'concluido'}:
                continue
            try:
                value = Decimal(str(item.get('valor_pago', 0)))
                if value.is_finite() and value >= 0:
                    amount += value
            except (InvalidOperation, ValueError):
                pass
        return {'total_agendamentos': len(rows), 'por_status': counts,
                'valor_declarado_ativo': float(amount.quantize(Decimal('0.01')))}, 200
