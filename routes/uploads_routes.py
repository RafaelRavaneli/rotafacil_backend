from flask import Blueprint, request, jsonify
from services.uploads import Uploads
from services.autenticacao import token_obrigatorio, requer_papel

# Inicializa o Blueprint
uploads_bp = Blueprint('uploads', __name__)

@uploads_bp.route('/imagem', methods=['POST'])
@token_obrigatorio
# @requer_papel('guia', 'agencia')
# Sem RBAC por papel de propósito: upload serve tanto para foto de perfil
# (qualquer usuário) quanto para capa de trilha (guia/agência). 
def upload_imagem(usuario_atual):
    try:
        # Verifica se a requisição contém a parte de arquivos
        if 'image' not in request.files:
            return jsonify({"erro": "Nenhuma imagem enviada. Use a chave 'image' no form-data."}), 400
            
        arquivo_imagem = request.files['image']
        
        # Verifica se o usuário enviou um arquivo vazio
        if arquivo_imagem.filename == '':
            return jsonify({"erro": "Nenhum arquivo selecionado"}), 400

        # Repassa o arquivo para a Inteligência do serviço de Uploads
        resposta, status = Uploads.enviar_para_imgbb(arquivo_imagem)
        
        return jsonify(resposta), status
        
    except Exception as e:
        return jsonify({"erro": f"Erro na rota de upload: {str(e)}"}), 500