from services.emergencia import Emergencia
from flask import Blueprint, request, jsonify
from models.database import bd
from services.usuarios import Usuarios
from services.autenticacao import token_obrigatorio, requer_papel, eh_dono_ou_tem_papel

usuarios_bp = Blueprint('usuarios', __name__)


@usuarios_bp.after_request
def proteger_cache_de_perfis(response):
    if request.endpoint != 'usuarios.documentos_legais':
        response.headers['Cache-Control'] = 'no-store, private'
    return response


@usuarios_bp.route('/documentos-legais', methods=['GET'])
def documentos_legais():
    from services.documentos_legais import DocumentosLegais
    return jsonify(DocumentosLegais.documentos()), 200


@usuarios_bp.route('/aceite-legal', methods=['POST'])
@token_obrigatorio
def registrar_aceite_legal(usuario_atual):
    from services.documentos_legais import DocumentosLegais
    resposta, status = DocumentosLegais.registrar(
        bd, usuario_atual, request.get_json(silent=True) or {})
    return jsonify(resposta), status

# --- Cadastro: público, sem RBAC (ninguém tem token ainda) ---
@usuarios_bp.route('/', methods=['POST'])
def cadastrar_usuario():
    resposta, status = Usuarios.cadastrar_usuario(bd, request.get_json())
    return jsonify(resposta), status

# --- Listar TODOS os usuários: só admin ---
@usuarios_bp.route('/', methods=['GET'])
@token_obrigatorio
@requer_papel('admin')
def listar_usuarios(usuario_atual):
    resposta, status = Usuarios.listar_usuarios(bd)
    return jsonify(resposta), status

# --- Buscar por e-mail: dono ou admin ---
@usuarios_bp.route('/email/<email>', methods=['GET'])
@token_obrigatorio
def listar_usuario_por_email(usuario_atual, email):
    if not eh_dono_ou_tem_papel(usuario_atual, email, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode ver o próprio perfil."}), 403
    resposta, status = Usuarios.listar_usuario_por_email(bd, email)
    if email not in {usuario_atual.get('id'), usuario_atual.get('email')}:
        resposta = Emergencia.remover_dados(resposta)
    return jsonify(resposta), status

# --- Buscar por ID: dono ou admin ---
@usuarios_bp.route('/<id>', methods=['GET'])
@token_obrigatorio
def listar_usuario_por_id(usuario_atual, id):
    if not eh_dono_ou_tem_papel(usuario_atual, id, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode ver o próprio perfil."}), 403
    resposta, status = Usuarios.listar_usuario_por_id(bd, id)
    if id not in {usuario_atual.get('id'), usuario_atual.get('email')}:
        resposta = Emergencia.remover_dados(resposta)
    return jsonify(resposta), status

# --- Atualizar por e-mail: dono ou admin ---
@usuarios_bp.route('/email/<email>', methods=['PUT'])
@token_obrigatorio
def atualizar_usuario_por_email(usuario_atual, email):
    if usuario_atual.get('tipo') == 'admin' and email not in {usuario_atual.get('id'),usuario_atual.get('email')}:
        return jsonify({'erro':'Use as ações administrativas específicas, com motivo e histórico.'}),403
    if not eh_dono_ou_tem_papel(usuario_atual, email, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode editar o próprio perfil."}), 403
    dados = request.get_json(silent=True) or {}
    if Emergencia.CAMPOS.intersection(dados) and email not in {usuario_atual.get('id'), usuario_atual.get('email')}:
        return jsonify({'erro': 'Somente o dono pode alterar o contato de emergência.'}), 403
    resposta, status = Usuarios.atualizar_usuario_por_email(bd, email, dados)
    return jsonify(resposta), status

# --- Atualizar por ID: dono ou admin ---
@usuarios_bp.route('/<id>', methods=['PUT'])
@token_obrigatorio
def atualizar_usuario_por_id(usuario_atual, id):
    if usuario_atual.get('tipo') == 'admin' and id not in {usuario_atual.get('id'),usuario_atual.get('email')}:
        return jsonify({'erro':'Use as ações administrativas específicas, com motivo e histórico.'}),403
    if not eh_dono_ou_tem_papel(usuario_atual, id, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode editar o próprio perfil."}), 403
    dados = request.get_json(silent=True) or {}
    if Emergencia.CAMPOS.intersection(dados) and id not in {usuario_atual.get('id'), usuario_atual.get('email')}:
        return jsonify({'erro': 'Somente o dono pode alterar o contato de emergência.'}), 403
    resposta, status = Usuarios.atualizar_usuario_por_id(bd, id, dados)
    return jsonify(resposta), status

# --- Deletar por e-mail: dono ou admin ---
@usuarios_bp.route('/email/<email>', methods=['DELETE'])
@token_obrigatorio
def deletar_usuario_por_email(usuario_atual, email):
    if usuario_atual.get('tipo') == 'admin':
        return jsonify({'erro':'Exclusão e mudança de papel administrativo não são permitidas por esta rota.'}),403
    if usuario_atual.get('tipo') == 'admin' and email not in {usuario_atual.get('id'),usuario_atual.get('email')}:
        return jsonify({'erro':'Use as ações administrativas específicas, com motivo e histórico.'}),403
    if not eh_dono_ou_tem_papel(usuario_atual, email, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode deletar o próprio perfil."}), 403
    resposta, status = Usuarios.deletar_usuario_por_email(bd, email)
    return jsonify(resposta), status

# --- Deletar por ID: dono ou admin ---
@usuarios_bp.route('/<id>', methods=['DELETE'])
@token_obrigatorio
def deletar_usuario_por_id(usuario_atual, id):
    if usuario_atual.get('tipo') == 'admin':
        return jsonify({'erro':'Exclusão e mudança de papel administrativo não são permitidas por esta rota.'}),403
    if usuario_atual.get('tipo') == 'admin' and id not in {usuario_atual.get('id'),usuario_atual.get('email')}:
        return jsonify({'erro':'Use as ações administrativas específicas, com motivo e histórico.'}),403
    if not eh_dono_ou_tem_papel(usuario_atual, id, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode deletar o próprio perfil."}), 403
    resposta, status = Usuarios.deletar_usuario_por_id(bd, id)
    return jsonify(resposta), status

# --- Verificar/desverificar guia ou agência: exclusivo admin ---
@usuarios_bp.route('/<id>/verificar', methods=['PUT'])
@token_obrigatorio
@requer_papel('admin')
def verificar_usuario(usuario_atual, id):
    dados = request.get_json(silent=True) or {}
    from services.community import CommunityError
    from services.administracao import Administracao
    verificado=dados.get('verificado')
    if not isinstance(verificado,bool):
        return jsonify({'erro':'Informe verificado como verdadeiro ou falso e motivo.'}),400
    try:
        resposta,status=Administracao.conta(bd,usuario_atual,id,{'acao':'verificar' if verificado else 'remover_verificacao','motivo':dados.get('motivo')})
    except CommunityError as error:
        resposta,status={'erro':str(error)},error.status
    except Exception:
        resposta,status={'erro':'Não foi possível confirmar a verificação. Recarregue antes de tentar novamente.'},503
    return jsonify(resposta),status

# --- Mudar tipo de usuário (com validação de documento se virar guia/agencia): dono ou admin ---
@usuarios_bp.route('/<id>/tipo', methods=['PUT'])
@token_obrigatorio
def mudar_tipo_usuario(usuario_atual, id):
    if usuario_atual.get('tipo') == 'admin':
        return jsonify({'erro':'Exclusão e mudança de papel administrativo não são permitidas por esta rota.'}),403
    if usuario_atual.get('tipo') == 'admin' and id not in {usuario_atual.get('id'),usuario_atual.get('email')}:
        return jsonify({'erro':'Use as ações administrativas específicas, com motivo e histórico.'}),403
    if not eh_dono_ou_tem_papel(usuario_atual, id, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode alterar o próprio tipo."}), 403
    dados = request.get_json(silent=True) or {}
    resposta, status = Usuarios.mudar_tipo_usuario(
        bd, id, dados.get('tipo'), dados.get('documento'), cadastur=dados)
    return jsonify(resposta), status

# --- Contato de emergência: responsável operacional, reserva e período autorizados ---
@usuarios_bp.route('/<id>/contato-emergencia', methods=['GET'])
@token_obrigatorio
@requer_papel('guia', 'agencia')
def obter_contato_emergencia(usuario_atual, id):
    resposta, status = Usuarios.obter_contato_emergencia(bd, id, usuario_atual, request.args.get('id_agendamento'))
    response = jsonify(resposta)
    response.headers['Cache-Control'] = 'no-store, private'
    return response, status
