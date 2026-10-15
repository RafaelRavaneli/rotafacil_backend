import datetime
import mimetypes
import uuid


class DocumentosProfissionais:
    TIPOS_PERMITIDOS = {
        'cadastur', 'certificacao', 'identificacao_profissional', 'outro'
    }
    CONTENT_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
    TAMANHO_MAXIMO = 5 * 1024 * 1024

    @staticmethod
    def _publico(doc):
        dados = doc.to_dict() or {}
        dados['id'] = doc.id
        dados.pop('caminho_storage', None)
        return dados

    @staticmethod
    def enviar(db, bucket, usuario, arquivo, tipo_documento):
        try:
            if (usuario.get('tipo') or '').strip().lower() not in {'guia', 'agencia'}:
                return {'erro': 'Apenas guias e agências podem enviar documentos profissionais.'}, 403
            tipo_documento = (tipo_documento or '').strip().lower()
            if tipo_documento not in DocumentosProfissionais.TIPOS_PERMITIDOS:
                return {'erro': 'Tipo de documento profissional inválido.'}, 400
            if arquivo is None or not arquivo.filename:
                return {'erro': 'Selecione um arquivo.'}, 400
            content_type = (arquivo.content_type or '').lower()
            if content_type == 'application/octet-stream':
                content_type = (mimetypes.guess_type(arquivo.filename)[0] or '').lower()
            if content_type not in DocumentosProfissionais.CONTENT_TYPES:
                return {'erro': 'Envie uma imagem JPG, PNG ou WEBP.'}, 400
            conteudo = arquivo.read()
            if not conteudo:
                return {'erro': 'O arquivo está vazio.'}, 400
            if len(conteudo) > DocumentosProfissionais.TAMANHO_MAXIMO:
                return {'erro': 'O arquivo deve ter no máximo 5 MB.'}, 400

            identificador = str(uuid.uuid4())
            extensao = {'image/jpeg': 'jpg', 'image/png': 'png',
                        'image/webp': 'webp'}[content_type]
            caminho = f'documentos-profissionais/{usuario["id"]}/{identificador}.{extensao}'
            bucket.blob(caminho).upload_from_string(
                conteudo, content_type=content_type)
            agora = datetime.datetime.now(datetime.timezone.utc).isoformat()
            dados = {
                'id': identificador,
                'id_usuario': usuario['id'],
                'tipo_usuario': usuario.get('tipo'),
                'tipo_documento': tipo_documento,
                'nome_arquivo': arquivo.filename,
                'content_type': content_type,
                'tamanho': len(conteudo),
                'caminho_storage': caminho,
                'status': 'pendente',
                'observacao_analise': '',
                'criado_em': agora,
                'analisado_em': None,
                'analisado_por': None,
            }
            db.collection('documentos_profissionais').document(
                identificador).set(dados)
            db.collection('usuarios').document(usuario['id']).update(
                {'verificado': False})
            return {key: value for key, value in dados.items()
                    if key != 'caminho_storage'}, 201
        except Exception as error:
            return {'erro': f'Erro ao enviar documento profissional: {error}'}, 500

    @staticmethod
    def listar(db, usuario, status=None):
        try:
            papel = (usuario.get('tipo') or '').strip().lower()
            if papel == 'admin':
                docs = db.collection('documentos_profissionais').stream()
            elif papel in {'guia', 'agencia'}:
                docs = db.collection('documentos_profissionais').where(
                    'id_usuario', '==', usuario.get('id')).stream()
            else:
                return {'erro': 'Acesso negado.'}, 403
            status = (status or '').strip().lower()
            itens = [DocumentosProfissionais._publico(doc) for doc in docs]
            if status:
                itens = [item for item in itens if item.get('status') == status]
            for item in itens:
                dono = db.collection('usuarios').document(
                    item.get('id_usuario')).get()
                if dono.exists:
                    dados_dono = dono.to_dict() or {}
                    item['nome_usuario'] = dados_dono.get('nome')
                    if papel == 'admin':
                        item['email_usuario'] = dados_dono.get('email')
            itens.sort(key=lambda item: item.get('criado_em') or '', reverse=True)
            return itens, 200
        except Exception as error:
            return {'erro': f'Erro ao listar documentos profissionais: {error}'}, 500

    @staticmethod
    def obter_arquivo(db, bucket, usuario, identificador):
        try:
            doc = db.collection('documentos_profissionais').document(
                identificador).get()
            if not doc.exists:
                return {'erro': 'Documento não encontrado.'}, 404
            dados = doc.to_dict() or {}
            papel = (usuario.get('tipo') or '').strip().lower()
            if papel != 'admin' and dados.get('id_usuario') != usuario.get('id'):
                return {'erro': 'Acesso negado.'}, 403
            conteudo = bucket.blob(dados['caminho_storage']).download_as_bytes()
            return {
                'conteudo': conteudo,
                'content_type': dados.get('content_type') or 'application/octet-stream',
                'nome_arquivo': dados.get('nome_arquivo') or 'documento',
            }, 200
        except Exception as error:
            return {'erro': f'Erro ao abrir documento profissional: {error}'}, 500

    @staticmethod
    def excluir(db, bucket, usuario, identificador):
        try:
            ref = db.collection('documentos_profissionais').document(identificador)
            doc = ref.get()
            if not doc.exists:
                return {'erro': 'Documento não encontrado.'}, 404
            dados = doc.to_dict() or {}
            papel = (usuario.get('tipo') or '').strip().lower()
            if papel != 'admin' and dados.get('id_usuario') != usuario.get('id'):
                return {'erro': 'Acesso negado.'}, 403
            if papel != 'admin' and dados.get('status') == 'aprovado':
                return {'erro': 'Documento aprovado não pode ser excluído.'}, 409
            bucket.blob(dados['caminho_storage']).delete()
            ref.delete()
            return {'mensagem': 'Documento excluído com sucesso.'}, 200
        except Exception as error:
            return {'erro': f'Erro ao excluir documento profissional: {error}'}, 500

    @staticmethod
    def analisar(db, usuario, identificador, dados_analise):
        try:
            if (usuario.get('tipo') or '').strip().lower() != 'admin':
                return {'erro': 'Acesso negado.'}, 403
            status = str((dados_analise or {}).get('status') or '').strip().lower()
            observacao = str((dados_analise or {}).get('observacao') or '').strip()
            if status not in {'aprovado', 'rejeitado'}:
                return {'erro': 'Use status aprovado ou rejeitado.'}, 400
            if status == 'rejeitado' and not observacao:
                return {'erro': 'Informe o motivo da rejeição.'}, 400
            ref = db.collection('documentos_profissionais').document(identificador)
            doc = ref.get()
            if not doc.exists:
                return {'erro': 'Documento não encontrado.'}, 404
            dados_doc = doc.to_dict() or {}
            agora = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ref.update({
                'status': status,
                'observacao_analise': observacao,
                'analisado_em': agora,
                'analisado_por': usuario.get('id'),
            })

            id_usuario = dados_doc.get('id_usuario')
            existe_aprovado = status == 'aprovado'
            if not existe_aprovado:
                for outro in db.collection('documentos_profissionais').where(
                        'id_usuario', '==', id_usuario).stream():
                    if outro.id != identificador and (
                            outro.to_dict() or {}).get('status') == 'aprovado':
                        existe_aprovado = True
                        break
            db.collection('usuarios').document(id_usuario).update(
                {'verificado': existe_aprovado})
            return {'mensagem': f'Documento {status} com sucesso.'}, 200
        except Exception as error:
            return {'erro': f'Erro ao analisar documento profissional: {error}'}, 500
