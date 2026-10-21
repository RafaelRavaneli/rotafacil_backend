import hashlib
import math
import uuid
from datetime import datetime, timezone, timedelta
from google.api_core.exceptions import AlreadyExists
from services.community import update_checked, CommunityError


class Avaliacoes:
    @staticmethod
    def estatisticas(db, id, campo='id_trilha', campo_nota='nota_roteiro'):
        notas=[]
        for doc in db.collection('avaliacoes').where(campo,'==',id).stream():
            data=doc.to_dict() or {}
            nota=data.get(campo_nota,data.get('nota') if campo_nota=='nota_roteiro' else None)
            if Avaliacoes._publicada(data) and type(nota) in (int,float) and math.isfinite(nota) and 0<=nota<=5:
                notas.append(nota)
        return {'nota_media':round(sum(notas)/len(notas),1) if notas else None,'total_avaliacoes':len(notas)}

    @staticmethod
    def _recalcular_media_trilha(db, id_trilha):
        avaliacoes_ref = db.collection('avaliacoes').where('id_trilha', '==', id_trilha).stream()
        notas = [
            (doc.to_dict() or {}).get(
                'nota_roteiro', (doc.to_dict() or {}).get('nota', 0))
            for doc in avaliacoes_ref if Avaliacoes._publicada(doc.to_dict() or {})
        ]

        notas = [n for n in notas if type(n) in (int,float) and math.isfinite(n) and 0 <= n <= 5]
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
            if not Avaliacoes._publicada(doc.to_dict() or {}):
                continue
            nota = (doc.to_dict() or {}).get(campo_nota)
            if type(nota) in (int,float) and math.isfinite(nota) and 0 <= nota <= 5:
                notas.append(nota)
        referencia.update({
            'nota_media': round(sum(notas) / len(notas), 1) if notas else None,
            'total_avaliacoes': len(notas),
        })

    @staticmethod
    def _normalizar_nota(valor, campo):
        if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
            raise ValueError(f'{campo} deve ser um número inteiro')
        try:
            if not math.isfinite(float(valor)) or float(valor) != int(float(valor)):
                raise ValueError()
            nota = int(float(valor))
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
            if not isinstance(id_trilha,str) or not id_trilha or len(id_trilha)>128 or '/' in id_trilha:
                return {'erro':'id_trilha deve identificar um roteiro válido.'},400
            if id_agendamento is not None and (not isinstance(id_agendamento,str) or not id_agendamento or len(id_agendamento)>128 or '/' in id_agendamento):
                return {'erro':'Identificação de reserva inválida.'},400

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
            else:
                candidatas = [doc for doc in db.collection('agendamentos').where('id_usuario','==',id_usuario).where('id_trilha','==',id_trilha).stream() if str((doc.to_dict() or {}).get('status') or '').lower() == 'concluido']
                if not candidatas:
                    return {'erro': 'A avaliação será liberada quando o responsável finalizar o roteiro.'}, 403
                if len(candidatas) != 1:
                    return {'erro': 'Informe a reserva concluída que deseja avaliar.'}, 400
                id_agendamento = candidatas[0].id
                reserva = candidatas[0].to_dict() or {}

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

            if not guia_id: nota_guia = None
            if not agencia_id: nota_agencia = None
            id_avaliacao = id_agendamento
            doc_ref = db.collection('avaliacoes').document(id_avaliacao)

            if doc_ref.get().exists or any(True for _ in db.collection('avaliacoes').where('id_agendamento','==',id_agendamento).stream()):
                return {"erro": "Você já avaliou este roteiro"}, 409

            doc_ref.create({
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
                "status_moderacao": "publicada",
                "createdAt": datetime.now(timezone.utc).isoformat()
            })

            Avaliacoes._recalcular_media_trilha(db, id_trilha)
            if guia_id:
                Avaliacoes._recalcular_media_responsavel(
                    db, guia_id, 'nota_guia')
            if agencia_id:
                Avaliacoes._recalcular_media_responsavel(
                    db, agencia_id, 'nota_agencia')

            return {"mensagem": "Avaliação registrada com sucesso!"}, 201
        except AlreadyExists:
            return {"erro": "Esta reserva já foi avaliada."}, 409
        except Exception as e:
            return {"erro": f"Erro ao registrar avaliação: {str(e)}"}, 500

    @staticmethod
    def _publicada(dados):
        return dados.get('status_moderacao', 'publicada') == 'publicada'

    @staticmethod
    def _publico(doc):
        dados = doc.to_dict() or {}
        campos = ('nome_usuario', 'nota', 'nota_roteiro', 'nota_guia', 'nota_agencia', 'comentario', 'createdAt', 'editado_em')
        resposta = {'id': doc.id, **{campo: dados.get(campo) for campo in campos}}
        for campo in ('createdAt','editado_em'):
            if isinstance(resposta.get(campo),datetime): resposta[campo]=resposta[campo].isoformat()
        return resposta

    @staticmethod
    def _recalcular(db, dados):
        if db.collection('trilhas').document(dados['id_trilha']).get().exists:
            Avaliacoes._recalcular_media_trilha(db, dados['id_trilha'])
        for tipo in ('guia','agencia'):
            if dados.get('id_'+tipo):
                Avaliacoes._recalcular_media_responsavel(db,dados['id_'+tipo],'nota_'+tipo)

    @staticmethod
    def listar_avaliacoes_trilha(db, id_trilha):
        try:
            docs = db.collection('avaliacoes').where('id_trilha','==',id_trilha).stream()
            return [Avaliacoes._publico(doc) for doc in docs if Avaliacoes._publicada(doc.to_dict() or {})], 200
        except Exception:
            return {'erro':'Não foi possível carregar as avaliações.'}, 503

    @staticmethod
    def listar_profissional(db, id_profissional):
        ref, pessoa = Avaliacoes._usuario_por_identificador(db,id_profissional)
        if ref is None or pessoa.get('tipo') not in {'guia','agencia'}:
            return {'erro':'Profissional não encontrado.'},404
        docs = db.collection('avaliacoes').where('id_'+pessoa['tipo'],'==',ref.id).stream()
        return [Avaliacoes._publico(doc) for doc in docs if Avaliacoes._publicada(doc.to_dict() or {})],200

    @staticmethod
    def minha(db, reserva_id, usuario):
        reserva = db.collection('agendamentos').document(reserva_id).get()
        if not reserva.exists or (reserva.to_dict() or {}).get('id_usuario') != usuario.get('id'):
            return {'erro':'Reserva não disponível.'},403
        doc = db.collection('avaliacoes').document(reserva_id).get()
        if not doc.exists:
            return {'erro':'Avaliação não encontrada.'},404
        dados = doc.to_dict() or {}
        if dados.get('id_usuario') != usuario.get('id'): return {'erro':'Avaliação indisponível.'},403
        return {**Avaliacoes._publico(doc), 'status_moderacao':dados.get('status_moderacao','publicada'), 'editavel':Avaliacoes._editavel(dados) and (reserva.to_dict() or {}).get('status') == 'concluido' and dados.get('id_agendamento') == reserva_id},200

    @staticmethod
    def _editavel(dados):
        try:
            valor = dados.get('createdAt')
            criada = valor if isinstance(valor,datetime) else datetime.fromisoformat(str(valor).replace('Z','+00:00'))
            if criada.tzinfo is None: criada=criada.replace(tzinfo=timezone.utc)
            return Avaliacoes._publicada(dados) and criada <= datetime.now(timezone.utc) <= criada+timedelta(days=7)
        except (TypeError,ValueError):
            return False

    @staticmethod
    def editar(db, id_avaliacao, usuario, payload):
        doc = db.collection('avaliacoes').document(id_avaliacao).get()
        dados = (doc.to_dict() or {}) if doc.exists else {}
        if usuario.get('tipo') != 'usuario' or dados.get('id_usuario') != usuario.get('id'):
            return {'erro':'Somente o autor pode editar sua avaliação.'},403
        reserva_id=dados.get('id_agendamento')
        reserva=db.collection('agendamentos').document(reserva_id).get() if reserva_id else None
        if reserva is None or not reserva.exists or (reserva.to_dict() or {}).get('status') != 'concluido' or (reserva.to_dict() or {}).get('id_usuario') != usuario.get('id') or (reserva.to_dict() or {}).get('id_trilha') != dados.get('id_trilha'):
            return {'erro':'A avaliação exige reserva concluída.'},403
        if not Avaliacoes._editavel(dados):
            return {'erro':'Edição disponível por 7 dias após envio, somente enquanto publicada.'},409
        if not isinstance(payload,dict) or set(payload)-{'nota','nota_guia','nota_agencia','comentario'}:
            return {'erro':'Campos de avaliação inválidos.'},400
        try:
            atualizacao={'nota':Avaliacoes._normalizar_nota(payload.get('nota'),'nota_roteiro')}
            atualizacao['nota_roteiro']=atualizacao['nota']
            for tipo in ('guia','agencia'):
                if dados.get('id_'+tipo): atualizacao['nota_'+tipo]=Avaliacoes._normalizar_nota(payload.get('nota_'+tipo),'nota_'+tipo)
            comentario=payload.get('comentario','')
            if not isinstance(comentario,str) or len(comentario.strip())>500: raise ValueError('Comentário deve ter até 500 caracteres.')
            atualizacao.update({'comentario':comentario.strip(),'editado_em':datetime.now(timezone.utc).isoformat()})
            update_checked(doc.reference,doc,atualizacao)
            Avaliacoes._recalcular(db,dados)
            return {'mensagem':'Avaliação atualizada.'},200
        except ValueError as error:
            return {'erro':str(error)},400
        except CommunityError as error:
            return {'erro':str(error)},error.status

    @staticmethod
    def denunciar(db, id_avaliacao, usuario, payload):
        doc=db.collection('avaliacoes').document(id_avaliacao).get()
        dados=(doc.to_dict() or {}) if doc.exists else {}
        if not doc.exists or not Avaliacoes._publicada(dados): return {'erro':'Avaliação indisponível.'},404
        if dados.get('id_usuario') == usuario.get('id'): return {'erro':'Não é possível denunciar a própria avaliação.'},403
        if not isinstance(payload,dict) or set(payload)-{'motivo','descricao'}: return {'erro':'Denúncia inválida.'},400
        motivo=payload.get('motivo')
        descricao=payload.get('descricao','')
        if not isinstance(motivo,str) or motivo not in {'conteudo_ofensivo','dados_pessoais','spam','outro'} or not isinstance(descricao,str) or len(descricao.strip())>500:
            return {'erro':'Informe motivo válido e descrição de até 500 caracteres.'},400
        id=hashlib.sha256((id_avaliacao+'|'+usuario['id']).encode()).hexdigest()
        try:
            db.collection('denuncias_avaliacoes').document(id).create({'id_avaliacao':id_avaliacao,'id_denunciante':usuario['id'],'motivo':motivo,'descricao':descricao.strip(),'status':'pendente','criado_em':datetime.now(timezone.utc).isoformat()})
        except AlreadyExists:
            return {'erro':'Sua denúncia já foi registrada.'},409
        return {'mensagem':'Denúncia registrada para análise.'},201

    @staticmethod
    def painel(db, usuario, status='denunciadas'):
        if usuario.get('tipo') != 'admin': return {'erro':'Acesso administrativo obrigatório.'},403
        if status not in {'denunciadas','todas','publicadas','ocultas'}: return {'erro':'Filtro inválido.'},400
        denuncias={}
        for doc in db.collection('denuncias_avaliacoes').stream():
            dados=doc.to_dict() or {}
            denuncias.setdefault(dados.get('id_avaliacao'),[]).append({'id':doc.id,**dados})
        result=[]
        for doc in db.collection('avaliacoes').stream():
            dados=doc.to_dict() or {}
            reports=denuncias.get(doc.id,[])
            visible=Avaliacoes._publicada(dados)
            if status == 'denunciadas' and not any(r.get('status')=='pendente' for r in reports): continue
            if status == 'publicadas' and not visible or status == 'ocultas' and visible: continue
            historico=[{**(item.to_dict() or {}),'id':item.id} for item in db.collection('historico_moderacao_avaliacoes').where('id_avaliacao','==',doc.id).stream()]
            result.append({**Avaliacoes._publico(doc),'status_moderacao':dados.get('status_moderacao','publicada'),'denuncias':reports,'historico':historico})
        return result,200

    @staticmethod
    def moderar(db,id_avaliacao,usuario,payload):
        if usuario.get('tipo') != 'admin': return {'erro':'Acesso administrativo obrigatório.'},403
        if not isinstance(payload,dict) or set(payload)-{'acao','motivo'}: return {'erro':'Ação inválida.'},400
        acao=payload.get('acao'); motivo=payload.get('motivo')
        if not isinstance(acao,str) or acao not in {'ocultar','restaurar','manter'} or not isinstance(motivo,str) or not 3<=len(motivo.strip())<=500:
            return {'erro':'Informe uma ação válida e motivo de 3 a 500 caracteres.'},400
        doc=db.collection('avaliacoes').document(id_avaliacao).get()
        if not doc.exists: return {'erro':'Avaliação não encontrada.'},404
        dados=doc.to_dict() or {}
        reports=list(db.collection('denuncias_avaliacoes').where('id_avaliacao','==',id_avaliacao).stream())
        audit=db.collection('historico_moderacao_avaliacoes').document(str(uuid.uuid4()))
        audit.create({'id_avaliacao':id_avaliacao,'id_admin':usuario['id'],'acao':acao,'motivo':motivo.strip(),'criado_em':datetime.now(timezone.utc).isoformat(),'resultado':'solicitada'})
        try:
            novo = 'oculta' if acao=='ocultar' else ('publicada' if acao=='restaurar' else dados.get('status_moderacao','publicada'))
            update_checked(doc.reference,doc,{'status_moderacao':novo,'moderado_em':datetime.now(timezone.utc).isoformat()})
        except CommunityError as error:
            audit.update({'resultado':'conflito'})
            return {'erro':str(error)},error.status
        for report in reports:
            report.reference.update({'status':'analisada'})
        Avaliacoes._recalcular(db,dados)
        audit.update({'resultado':'aplicada'})
        return {'mensagem':'Moderação aplicada.'},200
