import io
import os

from firebase_admin import storage
from flask import Blueprint, jsonify, request, send_file

from models.database import bd
from services.autenticacao import token_obrigatorio, requer_papel
from services.documentos_profissionais import DocumentosProfissionais


documentos_profissionais_bp = Blueprint('documentos_profissionais', __name__)


@documentos_profissionais_bp.errorhandler(RuntimeError)
def armazenamento_indisponivel(error):
    return jsonify({'erro': str(error)}), 503


def _bucket():
    nome = os.getenv('FIREBASE_STORAGE_BUCKET')
    if not nome:
        raise RuntimeError('FIREBASE_STORAGE_BUCKET não configurado no servidor.')
    return storage.bucket(nome)


@documentos_profissionais_bp.route('/', methods=['GET'])
@token_obrigatorio
@requer_papel('guia', 'agencia', 'admin')
def listar_documentos(usuario_atual):
    resposta, status = DocumentosProfissionais.listar(
        bd, usuario_atual, request.args.get('status'))
    return jsonify(resposta), status


@documentos_profissionais_bp.route('/', methods=['POST'])
@token_obrigatorio
@requer_papel('guia', 'agencia')
def enviar_documento(usuario_atual):
    resposta, status = DocumentosProfissionais.enviar(
        bd, _bucket(), usuario_atual, request.files.get('arquivo'),
        request.form.get('tipo_documento'))
    return jsonify(resposta), status


@documentos_profissionais_bp.route('/<identificador>/arquivo', methods=['GET'])
@token_obrigatorio
@requer_papel('guia', 'agencia', 'admin')
def abrir_documento(usuario_atual, identificador):
    resposta, status = DocumentosProfissionais.obter_arquivo(
        bd, _bucket(), usuario_atual, identificador)
    if status != 200:
        return jsonify(resposta), status
    return send_file(
        io.BytesIO(resposta['conteudo']),
        mimetype=resposta['content_type'],
        download_name=resposta['nome_arquivo'],
        as_attachment=False,
    )


@documentos_profissionais_bp.route('/<identificador>', methods=['DELETE'])
@token_obrigatorio
@requer_papel('guia', 'agencia', 'admin')
def excluir_documento(usuario_atual, identificador):
    resposta, status = DocumentosProfissionais.excluir(
        bd, _bucket(), usuario_atual, identificador)
    return jsonify(resposta), status


@documentos_profissionais_bp.route('/<identificador>/analise', methods=['PUT'])
@token_obrigatorio
@requer_papel('admin')
def analisar_documento(usuario_atual, identificador):
    resposta, status = DocumentosProfissionais.analisar(
        bd, usuario_atual, identificador, request.get_json(silent=True) or {})
    return jsonify(resposta), status
