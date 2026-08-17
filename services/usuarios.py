import uuid
from werkzeug.security import generate_password_hash
from firebase_admin import firestore

class Usuarios:
    TIPOS_PERMITIDOS_NO_CADASTRO = {"usuario", "guia", "agencia"}  # admin NUNCA pode vir daqui
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

            usuario_existente = db.collection('usuarios') \
                .where('email', '==', dados['email']) \
                .stream()
            
            if list(usuario_existente):
                return {"erro": "Email já cadastrado"}, 409
                    
            id_usuario = str(uuid.uuid4())
            # Dicionário fechado para evitar inserção de lixo no banco
            usuario = {
                "id": id_usuario,
                "nome": dados.get("nome"),
                "email": dados.get("email"),
                "telefone": dados.get("telefone"),
                "cidade": dados.get("cidade"),
                "estado": dados.get("estado"),
                "senha": generate_password_hash(dados["senha"]),
                "tipo": tipo_solicitado,   # ← ESSA É A ÚNICA LINHA QUE MUDA
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
                usuario.pop("senha", None)  # Remove a senha por segurança
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
                usuario.pop("senha", None) # Remove a senha por segurança
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
                usuario.pop("senha", None) # Remove a senha por segurança
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
            usuarios_ref = db.collection('usuarios').document(id).get()
            if not usuarios_ref.exists:
                return {"erro": "Usuário não encontrado"}, 404
            db.collection('usuarios').document(id).update(dados)
            return {"mensagem": "Usuário atualizado com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Ocorreu um erro ao atualizar usuário: {str(e)}"}, 500 