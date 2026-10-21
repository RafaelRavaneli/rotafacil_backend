from services.emergencia import Emergencia
from services.documentos_legais import DocumentosLegais
from services.verificacao_email import VerificacaoEmail
import re
import os
import uuid
from werkzeug.security import generate_password_hash
from firebase_admin import firestore, storage
from services.cadastur import Cadastur

class Usuarios:
    @staticmethod
    def _atualizar_cadastur(dados, atual):
        if not {'cadastur_numero', 'cadastur_validade'} & set(dados):
            return None
        if atual.get('tipo') not in {'guia', 'agencia'}:
            return {'erro': 'Cadastur é destinado a guias e agências.'}, 400
        try:
            dados.update(Cadastur.normalizar({**atual, **dados}, obrigatorio=True))
        except ValueError as error:
            return {'erro': str(error)}, 400
        return None

    TIPOS_PERMITIDOS_NO_CADASTRO = {"usuario", "guia", "agencia"}  # admin NUNCA pode vir daqui
    STATUS_COMPROMISSO_ATIVO = {
        'agendado', 'pendente', 'confirmado', 'em_andamento'
    }
    CAMPOS_EDITAVEIS = {
        'nome', 'email', 'telefone', 'cidade', 'estado', 'documento',
        'foto_url', 'contato_emergencia_nome', 'contato_emergencia_telefone',
        'contato_emergencia_relacao', 'contato_emergencia_consentimento',
        'descricao_profissional', 'especialidades', 'nome_fantasia',
        'razao_social', 'cadastur_numero', 'cadastur_validade',
    }

    @staticmethod
    def _validar_campos_edicao(dados):
        proibidos = sorted(set(dados) - Usuarios.CAMPOS_EDITAVEIS)
        if proibidos:
            return {"erro": f"Campos não permitidos na atualização: {', '.join(proibidos)}"}, 400
        descricao = dados.get('descricao_profissional')
        if descricao is not None and (
                not isinstance(descricao, str) or len(descricao.strip()) > 600):
            return {"erro": "A apresentação profissional deve ter até 600 caracteres"}, 400
        especialidades = dados.get('especialidades')
        if especialidades is not None:
            if (not isinstance(especialidades, list) or
                    len(especialidades) > 10 or
                    any(not isinstance(item, str) or not item.strip() or
                        len(item.strip()) > 80 for item in especialidades)):
                return {"erro": "Informe até 10 especialidades de até 80 caracteres"}, 400
            dados['especialidades'] = list(dict.fromkeys(
                item.strip() for item in especialidades))
        if isinstance(descricao, str):
            dados['descricao_profissional'] = descricao.strip()
        if 'nome' in dados:
            nome = str(dados.get('nome') or '').strip()
            if not nome or len(nome) > 120:
                return {"erro": "Nome deve ter entre 1 e 120 caracteres"}, 400
            dados['nome'] = nome
        if 'email' in dados:
            email = str(dados.get('email') or '').strip().lower()
            if (len(email) > 254 or
                    not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)):
                return {"erro": "E-mail inválido"}, 400
            dados['email'] = email
        return None

    @staticmethod
    def _aliases_usuario(usuario):
        return {
            valor for valor in (usuario.get('id'), usuario.get('email'))
            if valor
        }

    @staticmethod
    def _agendamentos_ativos_da_conta(db, usuario):
        aliases = Usuarios._aliases_usuario(usuario)
        trilhas_da_agencia = set()
        if (usuario.get('tipo') or '').strip().lower() == 'agencia':
            for trilha in db.collection('trilhas').stream():
                dados_trilha = trilha.to_dict() or {}
                if dados_trilha.get('criado_por') in aliases:
                    trilhas_da_agencia.add(trilha.id)

        ativos = []
        for agendamento in db.collection('agendamentos').stream():
            dados = agendamento.to_dict() or {}
            status = str(dados.get('status') or '').strip().lower()
            if status not in Usuarios.STATUS_COMPROMISSO_ATIVO:
                continue
            participa = dados.get('id_usuario') in aliases
            responsavel = dados.get('id_guia') in aliases
            atividade_da_agencia = dados.get('id_trilha') in trilhas_da_agencia
            if participa or responsavel or atividade_da_agencia:
                ativos.append(agendamento.id)
        return ativos

    @staticmethod
    def _excluir_documentos_por_campo(db, colecao, campo, valores):
        removidos = set()
        for valor in valores:
            for doc in db.collection(colecao).where(campo, '==', valor).stream():
                if doc.id not in removidos:
                    doc.reference.delete()
                    removidos.add(doc.id)

    @staticmethod
    def _excluir_conta(db, doc):
        usuario = doc.to_dict() or {}
        usuario.setdefault('id', doc.id)
        ativos = Usuarios._agendamentos_ativos_da_conta(db, usuario)
        if ativos:
            return {
                "erro": "Não é possível excluir a conta enquanto houver reservas ativas. Cancele ou conclua as reservas primeiro."
            }, 409

        aliases = Usuarios._aliases_usuario(usuario)

        documentos = []
        for alias in aliases:
            documentos.extend(db.collection('documentos_profissionais').where(
                'id_usuario', '==', alias).stream())
        if documentos:
            nome_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
            if not nome_bucket:
                return {
                    'erro': 'Armazenamento de documentos não configurado; a conta não foi excluída.'
                }, 503
            bucket = storage.bucket(nome_bucket)
            processados = set()
            for documento in documentos:
                if documento.id in processados:
                    continue
                dados_documento = documento.to_dict() or {}
                caminho = dados_documento.get('caminho_storage')
                if caminho:
                    bucket.blob(caminho).delete()
                documento.reference.delete()
                processados.add(documento.id)

        # Retira atividades futuras do catálogo e remove a atribuição do guia.
        for trilha in db.collection('trilhas').stream():
            dados = trilha.to_dict() or {}
            atualizacao = {}
            if dados.get('criado_por') in aliases:
                atualizacao['ativo'] = False
            if dados.get('id_guia') in aliases:
                atualizacao['id_guia'] = None
            if atualizacao:
                trilha.reference.update(atualizacao)

        for colecao, campo in (
            ('favoritos', 'id_usuario'),
            ('checklists_pessoais', 'id_usuario'),
            ('consultas_emergencia', 'id_usuario'),
            ('dispositivos_fcm', 'id_usuario'),
            ('notificacoes', 'id_usuario'),
            ('disponibilidades', 'id_usuario'),
            ('redefinicoes_senha', 'id_usuario'),
            ('verificacoes_email', 'id_usuario'),
            ('convites_guias', 'id_guia'),
            ('convites_guias', 'id_agencia'),
        ):
            Usuarios._excluir_documentos_por_campo(
                db, colecao, campo, aliases
            )

        doc.reference.delete()
        return {"mensagem": "Conta excluída com sucesso."}, 200
    
    @staticmethod
    def _validar_cpf(cpf):
        cpf = re.sub(r'\D', '', cpf or '')
        if len(cpf) != 11 or cpf == cpf[0] * 11:
            return False

        def calcular_digito(base, pesos):
            soma = sum(int(d) * p for d, p in zip(base, pesos))
            resto = soma % 11
            return '0' if resto < 2 else str(11 - resto)

        dv1 = calcular_digito(cpf[:9], range(10, 1, -1))
        dv2 = calcular_digito(cpf[:9] + dv1, range(11, 1, -1))
        return cpf[-2:] == dv1 + dv2

    @staticmethod
    def _validar_cnpj(cnpj):
        cnpj = re.sub(r'\D', '', cnpj or '')
        if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
            return False

        def calcular_digito(base, pesos):
            soma = sum(int(d) * p for d, p in zip(base, pesos))
            resto = soma % 11
            return '0' if resto < 2 else str(11 - resto)

        pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        dv1 = calcular_digito(cnpj[:12], pesos1)
        dv2 = calcular_digito(cnpj[:12] + dv1, pesos2)
        return cnpj[-2:] == dv1 + dv2

    @staticmethod
    def _validar_documento(documento):
        """Aceita CPF (11 dígitos) ou CNPJ (14 dígitos), detectando qual é pelo tamanho.
        Retorna (valido: bool, tipo: 'cpf' | 'cnpj' | None)."""
        apenas_digitos = re.sub(r'\D', '', documento or '')
        if len(apenas_digitos) == 11:
            return Usuarios._validar_cpf(apenas_digitos), 'cpf'
        elif len(apenas_digitos) == 14:
            return Usuarios._validar_cnpj(apenas_digitos), 'cnpj'
        return False, None

    @staticmethod
    def _documento_compativel_com_perfil(tipo_usuario, tipo_documento):
        if tipo_usuario == 'guia':
            return tipo_documento == 'cpf'
        if tipo_usuario == 'agencia':
            return tipo_documento == 'cnpj'
        return True

    @staticmethod
    def _email_disponivel(db, email, ignorar_id):
        return not any(
            doc.id != ignorar_id
            for doc in db.collection('usuarios').where(
                'email', '==', email).stream()
        )
    
    @staticmethod
    def cadastrar_usuario(db, dados):
        try:
            if not dados:
                return {"erro": "Dados não enviados"}, 400

            campos_obrigatorios = ["nome", "email", "senha"]
            for campo in campos_obrigatorios:
                if campo not in dados or not str(dados.get(campo) or '').strip():
                    return {"erro": f"Campo Obrigatório: {campo}"}, 400

            nome = str(dados['nome']).strip()
            email = str(dados['email']).strip().lower()
            senha = str(dados['senha'])
            if len(nome) > 120:
                return {"erro": "Nome deve ter até 120 caracteres"}, 400
            if (len(email) > 254 or
                    not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)):
                return {"erro": "E-mail inválido"}, 400
            if len(senha) < 6 or len(senha) > 128:
                return {"erro": "A senha deve ter entre 6 e 128 caracteres"}, 400

            tipo_solicitado = (dados.get("tipo") or "usuario").strip().lower()
            if tipo_solicitado not in Usuarios.TIPOS_PERMITIDOS_NO_CADASTRO:
                return {"erro": f"Tipo de usuário inválido. Use um de: {', '.join(Usuarios.TIPOS_PERMITIDOS_NO_CADASTRO)}"}, 400

            documento = dados.get("documento")
            documento_limpo = re.sub(r'\D', '', documento) if documento else None
            tipo_documento = None

            if tipo_solicitado in {"guia", "agencia"} and not documento_limpo:
                return {"erro": "Documento (CPF ou CNPJ) é obrigatório para guias e agências"}, 400

            if documento_limpo:
                valido, tipo_documento = Usuarios._validar_documento(documento_limpo)
                if not valido:
                    return {"erro": "CPF/CNPJ inválido"}, 400
                tipo_esperado = 'cpf' if tipo_solicitado == 'guia' else 'cnpj'
                if tipo_solicitado in {'guia', 'agencia'} and tipo_documento != tipo_esperado:
                    rotulo = 'CPF' if tipo_esperado == 'cpf' else 'CNPJ'
                    return {"erro": f"{rotulo} inválido para este perfil"}, 400
                
                # --- NOVA TRAVA: Verifica se o documento já existe no banco ---
                documento_existente = db.collection('usuarios').where('documento', '==', documento_limpo).stream()
                if list(documento_existente):
                    return {"erro": "CPF/CNPJ já cadastrado no sistema"}, 409
                
            usuario_existente = db.collection('usuarios') \
                .where('email', '==', email) \
                .stream()
            
            if list(usuario_existente):
                return {"erro": "Email já cadastrado"}, 409

            cadastur = {}
            if tipo_solicitado in {'guia', 'agencia'}:
                try:
                    cadastur = Cadastur.normalizar(dados, obrigatorio=True)
                except ValueError as error:
                    return {'erro': str(error)}, 400
                    
            try:
                aceite = DocumentosLegais.validar_aceite(dados)
            except ValueError as error:
                return {'erro': str(error), 'codigo': 'ACEITE_LEGAL_NECESSARIO'}, 400

            id_usuario = str(uuid.uuid4())
            usuario = {
                "id": id_usuario,
                "nome": nome,
                "email": email,
                "telefone": dados.get("telefone"),
                "cidade": dados.get("cidade"),
                "estado": dados.get("estado"),
                "senha": generate_password_hash(senha),
                "tipo": tipo_solicitado,
                "documento": documento_limpo,
                "tipo_documento": tipo_documento,
                **cadastur,
                "contato_emergencia_nome": "",
                "contato_emergencia_telefone": "",
                "contato_emergencia_relacao": "",
                "contato_emergencia_consentimento": False,
                "aceite_legal": aceite,
                "historico_aceites_legais": [aceite],
                "verificado": False,
                "email_confirmado": False,
                "exigir_confirmacao_email": VerificacaoEmail.habilitada(),
                "ativo": True,
                "createdAt": firestore.SERVER_TIMESTAMP
            }

            db.collection('usuarios').document(id_usuario).set(usuario)
            enviada = False
            if usuario['exigir_confirmacao_email']:
                try:
                    _, envio_status = VerificacaoEmail.solicitar(db, {'email': email})
                    enviada = envio_status == 200
                except Exception:
                    # Conta criada: falha no envio deve permitir reenvio, sem novo cadastro.
                    enviada = False
            return {"mensagem": "Usuário cadastrado com sucesso!", "id": id_usuario,
                    "confirmacao_email_necessaria": usuario['exigir_confirmacao_email'],
                    "confirmacao_email_enviada": enviada}, 201
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao salvar: {str(e)}"}, 500

    @staticmethod
    def listar_usuarios(db):
        try:
            usuarios_ref = db.collection('usuarios').stream()
            usuarios = []
            for doc in usuarios_ref:
                usuario = doc.to_dict()
                usuario.pop("senha", None)  
                usuarios.append(usuario)
            return Emergencia.remover_dados(usuarios), 200
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao buscar usuários: {str(e)}"}, 500
        
    @staticmethod
    def listar_usuario_por_email(db, email):
        try:
            usuarios_ref = db.collection('usuarios').where('email', '==', email).stream()
            usuarios = []
            for doc in usuarios_ref:
                usuario = doc.to_dict()
                usuario.pop("senha", None) 
                usuarios.append(usuario)
            if usuarios:
                return usuarios, 200
            return {"erro": "Usuário não encontrado"}, 404
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao buscar usuário: {str(e)}"}, 500
    
    @staticmethod
    def listar_usuario_por_id(db, id):
        try:
            usuario_ref = db.collection('usuarios').document(id).get()
            if usuario_ref.exists:
                usuario = usuario_ref.to_dict()
                usuario.pop("senha", None) 
                return usuario, 200
            return {"erro": "Usuário não encontrado"}, 404
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao buscar usuário: {str(e)}"}, 500

    @staticmethod
    def deletar_usuario_por_email(db, email):
        try:
            usuarios_ref = db.collection('usuarios').where('email', '==', email).stream()
            docs = list(usuarios_ref)
            if not docs:
                return {"erro": "Usuário não encontrado"}, 404
            
            return Usuarios._excluir_conta(db, docs[0])
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao deletar usuário: {str(e)}"}, 500
        
    @staticmethod
    def deletar_usuario_por_id(db, id):
        try:
            usuarios_ref = db.collection('usuarios').document(id).get()
            if not usuarios_ref.exists:
                return {"erro": "Usuário não encontrado"}, 404
            return Usuarios._excluir_conta(db, usuarios_ref)
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao deletar usuário: {str(e)}"}, 500
        
    @staticmethod
    def atualizar_usuario_por_email(db, email, dados):
        try:
            if not dados:
                return {"erro": "Dados incompletos"}, 400

            erro_campos = Usuarios._validar_campos_edicao(dados)
            if erro_campos:
                return erro_campos

            if "tipo" in dados:
                return {"erro": "Este campo só pode ser alterado via PUT /api/usuarios/<id>/tipo"}, 403

            if "verificado" in dados:
                return {"erro": "Este campo só pode ser alterado por um admin"}, 403

            if "documento" in dados:
                valido, tipo_documento = Usuarios._validar_documento(dados["documento"])
                if not valido:
                    return {"erro": "CPF/CNPJ inválido"}, 400
                
                documento_limpo = re.sub(r'\D', '', dados["documento"])
                
                # --- NOVA TRAVA: Evita que um usuário pegue o documento de outro ---
                doc_existente = db.collection('usuarios').where('documento', '==', documento_limpo).stream()
                for doc in doc_existente:
                    if doc.to_dict().get('email') != email:
                        return {"erro": "CPF/CNPJ já cadastrado por outro usuário"}, 409

                dados["documento"] = documento_limpo
                dados["tipo_documento"] = tipo_documento

            usuarios_ref = db.collection('usuarios').where('email', '==', email).stream()
            docs = list(usuarios_ref)
            if not docs:
                return {"erro": "Usuário não encontrado"}, 404
            doc_id = docs[0].id
            atual = docs[0].to_dict() or {}
            try:
                Emergencia.preparar(dados, atual)
            except ValueError as error:
                return {'erro': str(error)}, 400
            erro_cadastur = Usuarios._atualizar_cadastur(dados, atual)
            if erro_cadastur:
                return erro_cadastur
            if ("documento" in dados and
                    not Usuarios._documento_compativel_com_perfil(
                        atual.get('tipo'), dados.get('tipo_documento'))):
                return {"erro": "Documento incompatível com o tipo da conta"}, 400
            if ("email" in dados and
                    not Usuarios._email_disponivel(db, dados['email'], doc_id)):
                return {"erro": "Email já cadastrado"}, 409
            if 'email' in dados and dados['email'] != atual.get('email'):
                dados.update({'email_confirmado': False, 'email_confirmado_em': None})
            db.collection('usuarios').document(doc_id).update(dados)
            return {"mensagem": "Usuário atualizado com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao atualizar usuário: {str(e)}"}, 500
    
    @staticmethod
    def atualizar_usuario_por_id(db, id, dados):
        try:
            if not dados:
                return {"erro": "Dados incompletos"}, 400

            erro_campos = Usuarios._validar_campos_edicao(dados)
            if erro_campos:
                return erro_campos

            if "tipo" in dados:
                return {"erro": "Este campo só pode ser alterado via PUT /api/usuarios/<id>/tipo"}, 403

            if "verificado" in dados:
                return {"erro": "Este campo só pode ser alterado por um admin"}, 403

            if "documento" in dados:
                valido, tipo_documento = Usuarios._validar_documento(dados["documento"])
                if not valido:
                    return {"erro": "CPF/CNPJ inválido"}, 400
                
                documento_limpo = re.sub(r'\D', '', dados["documento"])

                # --- NOVA TRAVA: Evita que um usuário pegue o documento de outro ---
                doc_existente = db.collection('usuarios').where('documento', '==', documento_limpo).stream()
                for doc in doc_existente:
                    if doc.id != id:
                        return {"erro": "CPF/CNPJ já cadastrado por outro usuário"}, 409
                
                dados["documento"] = documento_limpo
                dados["tipo_documento"] = tipo_documento

            usuarios_ref = db.collection('usuarios').document(id).get()
            if not usuarios_ref.exists:
                return {"erro": "Usuário não encontrado"}, 404
            atual = usuarios_ref.to_dict() or {}
            try:
                Emergencia.preparar(dados, atual)
            except ValueError as error:
                return {'erro': str(error)}, 400
            erro_cadastur = Usuarios._atualizar_cadastur(dados, atual)
            if erro_cadastur:
                return erro_cadastur
            if ("documento" in dados and
                    not Usuarios._documento_compativel_com_perfil(
                        atual.get('tipo'), dados.get('tipo_documento'))):
                return {"erro": "Documento incompatível com o tipo da conta"}, 400
            if ("email" in dados and
                    not Usuarios._email_disponivel(db, dados['email'], id)):
                return {"erro": "Email já cadastrado"}, 409
            if 'email' in dados and dados['email'] != atual.get('email'):
                dados.update({'email_confirmado': False, 'email_confirmado_em': None})
            db.collection('usuarios').document(id).update(dados)
            return {"mensagem": "Usuário atualizado com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao atualizar usuário: {str(e)}"}, 500

    @staticmethod
    def mudar_tipo_usuario(db, id_usuario, novo_tipo, documento_novo=None, cadastur=None):
        try:
            novo_tipo = (novo_tipo or "").strip().lower()
            if novo_tipo not in Usuarios.TIPOS_PERMITIDOS_NO_CADASTRO:
                return {"erro": f"Tipo inválido. Use um de: {', '.join(Usuarios.TIPOS_PERMITIDOS_NO_CADASTRO)}"}, 400

            doc_ref = db.collection('usuarios').document(id_usuario)
            doc = doc_ref.get()
            if not doc.exists:
                return {"erro": "Usuário não encontrado"}, 404

            dados_atuais = doc.to_dict()
            dados_atuais.setdefault('id', id_usuario)
            tipo_atual = (dados_atuais.get('tipo') or '').strip().lower()
            if tipo_atual == novo_tipo:
                return {"mensagem": "A conta já possui este tipo."}, 200

            if Usuarios._agendamentos_ativos_da_conta(db, dados_atuais):
                return {
                    "erro": "Não é possível alterar o tipo da conta enquanto houver reservas ativas. Cancele ou conclua as reservas primeiro."
                }, 409

            documento_atual = dados_atuais.get('documento')
            atualizacao = {"tipo": novo_tipo, "verificado": False}

            if novo_tipo in {"guia", "agencia"}:
                # Precisa de documento válido: usa o que já está salvo, ou o novo enviado agora
                documento_para_validar = documento_novo or documento_atual
                if not documento_para_validar:
                    return {"erro": "Documento (CPF ou CNPJ) é obrigatório para guias e agências"}, 400

                valido, tipo_documento = Usuarios._validar_documento(documento_para_validar)
                if not valido:
                    return {"erro": "CPF/CNPJ inválido"}, 400

                esperado = 'cpf' if novo_tipo == 'guia' else 'cnpj'
                if tipo_documento != esperado:
                    rotulo = 'CPF' if novo_tipo == 'guia' else 'CNPJ'
                    return {"erro": f"{rotulo} válido é obrigatório para este tipo de conta"}, 400

                documento_limpo = re.sub(r'\D', '', documento_para_validar)

                # Mesma trava de duplicidade do cadastro
                doc_existente = db.collection('usuarios').where('documento', '==', documento_limpo).stream()
                for outro in doc_existente:
                    if outro.id != id_usuario:
                        return {"erro": "CPF/CNPJ já cadastrado por outro usuário"}, 409

                atualizacao["documento"] = documento_limpo
                atualizacao["tipo_documento"] = tipo_documento
                try:
                    atualizacao.update(Cadastur.normalizar(cadastur or {}, obrigatorio=True))
                except ValueError as error:
                    return {'erro': str(error)}, 400

            if novo_tipo == 'usuario':
                atualizacao.update({
                    'documento': None,
                    'tipo_documento': None,
                    'descricao_profissional': None,
                    'especialidades': [],
                    'nome_fantasia': None,
                    'razao_social': None,
                    'cadastur_numero': '',
                    'cadastur_validade': '',
                })
            elif novo_tipo == 'guia':
                atualizacao.update({'nome_fantasia': None, 'razao_social': None})
            else:
                atualizacao.update({
                    'descricao_profissional': None,
                    'especialidades': [],
                })

            aliases = Usuarios._aliases_usuario(dados_atuais)
            if tipo_atual in {'guia', 'agencia'}:
                for trilha in db.collection('trilhas').stream():
                    dados_trilha = trilha.to_dict() or {}
                    mudancas_trilha = {}
                    if dados_trilha.get('criado_por') in aliases:
                        mudancas_trilha['ativo'] = False
                    if (tipo_atual == 'guia' and
                            dados_trilha.get('id_guia') in aliases):
                        mudancas_trilha['id_guia'] = None
                    if mudancas_trilha:
                        trilha.reference.update(mudancas_trilha)

            if tipo_atual == 'guia':
                Usuarios._excluir_documentos_por_campo(
                    db, 'disponibilidades', 'id_usuario', aliases)
                Usuarios._excluir_documentos_por_campo(
                    db, 'convites_guias', 'id_guia', aliases)
            if tipo_atual == 'agencia':
                Usuarios._excluir_documentos_por_campo(
                    db, 'convites_guias', 'id_agencia', aliases)

            doc_ref.update(atualizacao)
            return {"mensagem": f"Tipo de usuário alterado para '{novo_tipo}' com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Erro ao alterar tipo de usuário: {str(e)}"}, 500

    @staticmethod
    def obter_contato_emergencia(db, id_usuario, usuario_solicitante, reserva_id=None):
        try:
            return Emergencia.consultar(db, id_usuario, usuario_solicitante, reserva_id)
        except Exception:
            return {'erro': 'Não foi possível consultar o contato de emergência.'}, 503
