import jwt
import datetime
import os
from dotenv import load_dotenv
from werkzeug.security import check_password_hash
from flask import request, jsonify
from functools import wraps
from firebase_admin import firestore

load_dotenv()

class Autenticacao:
    @staticmethod
    def make_token(email):
        key = os.getenv("KEY")
        payload = {
            'email': email,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)
        }
        token = jwt.encode(payload, key, algorithm='HS256')
        return token

    @staticmethod
    def login(db, dados):
        try:
            if not dados:
                return {"erro": "Dados incompletos"}, 400
            
            email_recebido = dados.get('email')
            senha_recebida = dados.get('senha')

            if not email_recebido or not senha_recebida:
                return {"erro": "E-mail e senha são obrigatórios"}, 400

            # 1. Bater a ref de e-mail no Firebase
            usuarios_ref = db.collection('usuarios').where('email', '==', email_recebido).stream()
            docs = list(usuarios_ref)

            if not docs:
                return {"erro": "Usuário não encontrado"}, 404

            usuario_dados = docs[0].to_dict()
            senha_salva_no_banco = usuario_dados.get('senha')

            # 2. Conferir a senha criptografada
            # check_password_hash pega o hash do banco e compara com a senha digitada
            if check_password_hash(senha_salva_no_banco, senha_recebida):
                nome_do_usuario = usuario_dados.get('nome', 'Usuário')
                token = Autenticacao.make_token(email_recebido)

                return {
                    "mensagem": "Autenticação bem-sucedida",
                    "nome": nome_do_usuario,
                    "token": token
                }, 200
            else:
                return {"erro": "Credenciais inválidas"}, 401
                
        except Exception as e:
            return {"erro": f"Ocorreu um erro no login: {str(e)}"}, 500

def token_obrigatorio(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Verifica se o token foi enviado no cabeçalho da requisição
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
            else:
                token = parts[-1]

        if not token:
            return jsonify({"erro": "Token não informado. Acesso negado."}), 401

        try:
            # Tenta ler o token usando a chave secreta
            key = os.getenv("KEY")
            dados_token = jwt.decode(token, key, algorithms=["HS256"])
            usuario_email = dados_token['email']

            db = firestore.client()
            usuarios_ref = db.collection('usuarios').where('email', '==', usuario_email).stream()
            docs = list(usuarios_ref)

            if not docs:
                return jsonify({"erro": "Usuário não encontrado."}), 401

            usuario_atual = docs[0].to_dict()
            usuario_atual.pop("senha", None)
        except jwt.ExpiredSignatureError:
            return jsonify({"erro": "O token expirou. Faça login novamente."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"erro": "Token inválido."}), 401
        except Exception as e:
            return jsonify({"erro": f"Erro ao validar token: {str(e)}"}), 401

        # Se deu tudo certo, deixa a rota continuar o trabalho dela
        return f(usuario_atual, *args, **kwargs)

    return decorated        