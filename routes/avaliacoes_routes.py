from flask import Blueprint, request, jsonify
from models.database import bd
from services.avaliacoes import Avaliacoes
from services.autenticacao import token_obrigatorio, requer_papel

avaliacoes_bp = Blueprint('avaliacoes', __name__)


@avaliacoes_bp.after_request
def nao_armazenar_respostas(response):
    response.headers['Cache-Control'] = 'no-store, private'
    return response

# --- Avaliar uma trilha concluída ---
@avaliacoes_bp.route('/', methods=['POST'])
@token_obrigatorio
@requer_papel('usuario')
def adicionar_avaliacao(usuario_atual):
    dados = request.get_json(silent=True) or {}
    if not isinstance(dados,dict) or set(dados)-{'id_trilha','id_agendamento','nota','nota_guia','nota_agencia','comentario'}:
        return jsonify({'erro':'Campos de avaliação inválidos.'}),400
    resposta, status = Avaliacoes.adicionar_avaliacao(
        bd,
        usuario_atual.get('id'),
        dados.get('id_trilha'),
        dados.get('nota'),
        dados.get('comentario'),
        usuario_atual.get('nome'),
        id_agendamento=dados.get('id_agendamento'),
        nota_guia=dados.get('nota_guia'),
        nota_agencia=dados.get('nota_agencia'),
    )
    return jsonify(resposta), status

# --- Listar avaliações de uma trilha ---
@avaliacoes_bp.route('/trilha/<id_trilha>', methods=['GET'])
@token_obrigatorio
def listar_avaliacoes_trilha(usuario_atual, id_trilha):
    resposta, status = Avaliacoes.listar_avaliacoes_trilha(bd, id_trilha)
    return jsonify(resposta), status


# Erros internos nunca devolvem conteúdo da avaliação ou da denúncia.
def executar(funcao, *args):
    try:
        resposta, status = funcao(bd, *args)
    except Exception:
        resposta, status = {'erro':'Não foi possível concluir esta operação. Atualize e tente novamente.'}, 503
    return jsonify(resposta), status

@avaliacoes_bp.route('/profissional/<id>', methods=['GET'])
@token_obrigatorio
def listar_profissional(usuario_atual,id):
    return executar(Avaliacoes.listar_profissional,id)

@avaliacoes_bp.route('/reserva/<id>', methods=['GET'])
@token_obrigatorio
def minha(usuario_atual,id):
    return executar(Avaliacoes.minha,id,usuario_atual)

@avaliacoes_bp.route('/<id>', methods=['PATCH'])
@token_obrigatorio
@requer_papel('usuario')
def editar(usuario_atual,id):
    return executar(Avaliacoes.editar,id,usuario_atual,request.get_json(silent=True))

@avaliacoes_bp.route('/<id>/denunciar', methods=['POST'])
@token_obrigatorio
def denunciar(usuario_atual,id):
    return executar(Avaliacoes.denunciar,id,usuario_atual,request.get_json(silent=True))

@avaliacoes_bp.route('/moderacao', methods=['GET'])
@token_obrigatorio
@requer_papel('admin')
def painel(usuario_atual):
    return executar(Avaliacoes.painel,usuario_atual,request.args.get('status','denunciadas'))

@avaliacoes_bp.route('/<id>/moderar', methods=['POST'])
@token_obrigatorio
@requer_papel('admin')
def moderar(usuario_atual,id):
    return executar(Avaliacoes.moderar,id,usuario_atual,request.get_json(silent=True))


@avaliacoes_bp.route('/profissional/<id>/perfil', methods=['GET'])
@token_obrigatorio
def perfil_profissional(usuario_atual,id):
    ref,pessoa = Avaliacoes._usuario_por_identificador(bd,id)
    if ref is None or pessoa.get('tipo') not in {'guia','agencia'} or pessoa.get('ativo') is False:
        return jsonify({'erro':'Profissional não encontrado.'}),404
    campos=('nome','tipo','cidade','estado','descricao_profissional','verificado','nota_media','total_avaliacoes')
    estatisticas=Avaliacoes.estatisticas(bd,ref.id,'id_'+pessoa['tipo'],'nota_'+pessoa['tipo'])
    return jsonify({'id':ref.id,**{campo:pessoa.get(campo) for campo in campos},**estatisticas}),200
