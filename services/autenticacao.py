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
    def make_token(email, usuario_id, tipo_perfil):
        key = os.getenv("KEY")
        # Inserindo o ID e o Tipo (papel) dentro do token JWT
        payload = {
            'email': email,
            'id': usuario_id,
            'tipo': tipo_perfil,
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

            usuarios_ref = db.collection('usuarios').where('email', '==', email_recebido).stream()
            docs = list(usuarios_ref)

            if not docs:
                return {"erro": "Usuário não encontrado"}, 404

            # Extrai os dados do usuário encontrado no banco
            usuario_dados = docs[0].to_dict()
            senha_salva_no_banco = usuario_dados.get('senha')

            if check_password_hash(senha_salva_no_banco, senha_recebida):
                nome_do_usuario = usuario_dados.get('nome', 'Usuário')
                
                # Pegando o ID e o TIPO do banco para mandar para o gerador de token
                usuario_id = usuario_dados.get('id')
                tipo_perfil = usuario_dados.get('tipo', 'usuario')

                # Atualizamos a chamada para passar os 3 argumentos
                token = Autenticacao.make_token(email_recebido, usuario_id, tipo_perfil)

                return {
                    "mensagem": "Autenticação bem-sucedida",
                    "nome": nome_do_usuario,
                    "tipo": tipo_perfil, # Enviar o tipo solto aqui ajuda o Flutter a montar a tela correta
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

        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
            else:
                token = parts[-1]

        if not token:
            return jsonify({"erro": "Token não informado. Acesso negado."}), 401

        try:
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

        return f(usuario_atual, *args, **kwargs)
    return decorated


def requer_papel(*papeis_permitidos):
    """
    Decorator de RBAC (Role-Based Access Control).

    IMPORTANTE: precisa ser usado JUNTO com @token_obrigatorio, e sempre
    posicionado ABAIXO dele na pilha de decorators — porque depende do
    'usuario_atual' que o token_obrigatorio já validou e injetou.

    Uso:
        @app.route(...)
        @token_obrigatorio
        @requer_papel('admin', 'guia')
        def rota_protegida(usuario_atual):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(usuario_atual, *args, **kwargs):
            papel_do_usuario = (usuario_atual.get('tipo') or '').strip().lower()
            papeis_normalizados = {p.strip().lower() for p in papeis_permitidos}

            if papel_do_usuario not in papeis_normalizados:
                return jsonify({
                    "erro": f"Acesso negado. Esta ação requer um dos perfis: {', '.join(papeis_permitidos)}."
                }), 403

            return f(usuario_atual, *args, **kwargs)
        return decorated
    return decorator


def eh_dono_ou_tem_papel(usuario_atual, identificador_alvo, *papeis_permitidos):
    """
    Helper (não é decorator) para casos de 'dono OU papel privilegiado'.
    """
    papel = (usuario_atual.get('tipo') or '').strip().lower()
    if papel in {p.strip().lower() for p in papeis_permitidos}:
        return True
    return usuario_atual.get('email') == identificador_alvo or usuario_atual.get('id') == identificador_alvo
