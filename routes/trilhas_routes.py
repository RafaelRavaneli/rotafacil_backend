from flask import Blueprint, request, jsonify
from datetime import datetime
from google.cloud.firestore_v1.base_query import FieldFilter
from models.database import bd

# Inicializa o Blueprint
trilhas_bp = Blueprint('trilhas', __name__)

@trilhas_bp.route('/', methods=['POST'])
def criar_trilha():
    try:
        dados = request.get_json()
        nome = dados.get('nome')
        descricao = dados.get('descricao')
        cidade = dados.get('cidade')
        estado = dados.get('estado')
        dificuldade = dados.get('dificuldade')
        ponto_encontro = dados.get('ponto_encontro')
        data_str = dados.get('data')

        # Converte a string de data para datetime
        data = None
        if data_str:
            try:
                data = datetime.strptime(data_str, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                return jsonify({"erro": "Formato de data inválido. Use AAAA-MM-DDTHH:MM:SS"}), 400

        nova_trilha = {
            "nome": nome,
            "descricao": descricao,
            "cidade": cidade,
            "estado": estado,
            "dificuldade": dificuldade,
            "ponto_encontro": ponto_encontro,
            "data": data
        }

        # Adiciona ao Firestore
        doc_ref = bd.collection("trilhas").add(nova_trilha)
        return jsonify({"mensagem": "Trilha criada com sucesso!", "id": doc_ref[1].id}), 201
    except Exception as e:
         return jsonify({"erro": str(e)}), 500

@trilhas_bp.route('/', methods=['GET'])
def listar_trilhas():
     try:
          trilhas_ref = bd.collection("trilhas").stream()
          lista_trilhas = []
          for doc in trilhas_ref:
               trilha = doc.to_dict()
               trilha["id"] = doc.id
               lista_trilhas.append(trilha)
          return jsonify(lista_trilhas), 200
     except Exception as e:
          return jsonify({"erro": str(e)}), 500

@trilhas_bp.route('/busca', methods=['GET'])
def buscar_trilhas_avancada():
    try:
        query = bd.collection('trilhas')

        # Filtrar por Cidade
        cidade = request.args.get('cidade')
        if cidade:
             query = query.where(filter=FieldFilter('cidade', '==', cidade))

        # Filtrar por Dificuldade
        dificuldade = request.args.get('dificuldade')
        if dificuldade:
             query = query.where(filter=FieldFilter('dificuldade', '==', dificuldade))

        # Filtrar por Data (Intervalo)
        data_inicio = request.args.get('data_inicio')
        data_fim = request.args.get('data_fim')

        if data_inicio:
            try:
                dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
                query = query.where(filter=FieldFilter('data', '>=', dt_inicio))
            except ValueError:
                return jsonify({"erro": "Formato de data_inicio inválido. Use AAAA-MM-DD"}), 400

        if data_fim:
            try:
                # Modificado para incluir até o final do dia
                dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
                dt_fim = dt_fim.replace(hour=23, minute=59, second=59)
                query = query.where(filter=FieldFilter('data', '<=', dt_fim))
            except ValueError:
                 return jsonify({"erro": "Formato de data_fim inválido. Use AAAA-MM-DD"}), 400

        # Executa a query
        resultados = query.stream()
        lista_trilhas = []
        for doc in resultados:
            trilha = doc.to_dict()
            trilha['id'] = doc.id
            lista_trilhas.append(trilha)

        return jsonify(lista_trilhas), 200

    except Exception as e:
         return jsonify({"erro": str(e)}), 500