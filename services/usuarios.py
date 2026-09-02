import re
import uuid
from werkzeug.security import generate_password_hash
from firebase_admin import firestore

class Usuarios:
    TIPOS_PERMITIDOS_NO_CADASTRO = {"usuario", "guia", "agencia"}  # admin NUNCA pode vir daqui
    
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
    def cadastrar_usuario(db, dados):
        try:
            if not dados:
                return {"erro": "Dados não enviados"}, 400

            campos_obrigatorios = ["nome", "email", "senha"]
            for campo in campos_obrigatorios:
                if campo not in dados:
                    return {"erro": f"Campo Obrigatório: {campo}"}, 400

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
                
                # --- NOVA TRAVA: Verifica se o documento já existe no banco ---
                documento_existente = db.collection('usuarios').where('documento', '==', documento_limpo).stream()
                if list(documento_existente):
                    return {"erro": "CPF/CNPJ já cadastrado no sistema"}, 409
                
            usuario_existente = db.collection('usuarios') \
                .where('email', '==', dados['email']) \
                .stream()
            
            if list(usuario_existente):
                return {"erro": "Email já cadastrado"}, 409
                    
            id_usuario = str(uuid.uuid4())
            usuario = {
                "id": id_usuario,
                "nome": dados.get("nome"),
                "email": dados.get("email"),
                "telefone": dados.get("telefone"),
                "cidade": dados.get("cidade"),
                "estado": dados.get("estado"),
                "senha": generate_password_hash(dados["senha"]),
                "tipo": tipo_solicitado,
                "documento": documento_limpo,
                "tipo_documento": tipo_documento,
                "verificado": False,
                "ativo": True,
                "createdAt": firestore.SERVER_TIMESTAMP
            }

            db.collection('usuarios').document(id_usuario).set(usuario)
            return {"mensagem": "Usuário cadastrado com sucesso!", "id": id_usuario}, 201
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
            return usuarios, 200
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
            
            doc_id = docs[0].id
            db.collection('usuarios').document(doc_id).delete()
            return {"mensagem": "Usuário deletado com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao deletar usuário: {str(e)}"}, 500
        
    @staticmethod
    def deletar_usuario_por_id(db, id):
        try:
            usuarios_ref = db.collection('usuarios').document(id).get()
            if not usuarios_ref.exists:
                return {"erro": "Usuário não encontrado"}, 404
            db.collection('usuarios').document(id).delete()
            return {"mensagem": "Usuário deletado com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao deletar usuário: {str(e)}"}, 500
        
    @staticmethod
    def atualizar_usuario_por_email(db, email, dados):
        try:
            if not dados:
                return {"erro": "Dados incompletos"}, 400

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
            db.collection('usuarios').document(doc_id).update(dados)
            return {"mensagem": "Usuário atualizado com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao atualizar usuário: {str(e)}"}, 500
    
    @staticmethod
    def atualizar_usuario_por_id(db, id, dados):
        try:
            if not dados:
                return {"erro": "Dados incompletos"}, 400

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
            db.collection('usuarios').document(id).update(dados)
            return {"mensagem": "Usuário atualizado com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao atualizar usuário: {str(e)}"}, 500

    @staticmethod
    def verificar_usuario(db, id_usuario, verificado):
        try:
            doc_ref = db.collection('usuarios').document(id_usuario)
            doc = doc_ref.get()
            if not doc.exists:
                return {"erro": "Usuário não encontrado"}, 404

            tipo = (doc.to_dict().get('tipo') or '').strip().lower()
            if tipo not in {"guia", "agencia"}:
                return {"erro": "Só é possível verificar usuários do tipo guia ou agencia"}, 400

            doc_ref.update({"verificado": bool(verificado)})
            acao = "verificado" if verificado else "teve a verificação removida"
            return {"mensagem": f"Usuário {acao} com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Erro ao verificar usuário: {str(e)}"}, 500