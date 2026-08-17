import uuid
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

class Trilhas:
    @staticmethod
    def _usuario_pode_gerenciar_trilha(dados_trilha, usuario_atual):
        """
        Regra compartilhada entre atualizar e deletar trilha:
        só o criador, o guia responsável, ou um admin podem mexer.
        """
        criador = dados_trilha.get('criado_por')
        guia = dados_trilha.get('id_guia')

        papel = (usuario_atual.get('tipo') or '').strip().lower()
        email_usuario = usuario_atual.get('email')
        id_usuario = usuario_atual.get('id')

        eh_admin = papel == 'admin'
        eh_criador = email_usuario == criador or id_usuario == criador
        eh_guia_responsavel = email_usuario == guia or id_usuario == guia

        return eh_admin or eh_criador or eh_guia_responsavel
    
    @staticmethod
    def cadastrar_trilha(db, dados, usuario_atual):
        try:
            if not dados:
                return {"erro": "Dados não enviados"}, 400

            # Validações estruturais do José
            campos_obrigatorios = ["nome", "descricao", "dificuldade"]
            for campo in campos_obrigatorios:
                if campo not in dados:
                    return {"erro": f"Campo obrigatório: {campo}"}, 400
                
            id_trilha = str(uuid.uuid4())
            
            # Suas regras de negócio: Atribuição de Agência e Guia
            criado_por = usuario_atual.get("email") if isinstance(usuario_atual, dict) else usuario_atual
            guia_responsavel = dados.get("id_guia", criado_por)

            # Dicionário fechado unindo as duas arquiteturas
            trilha = {
                "id": id_trilha,
                "nome": dados.get("nome"),
                "descricao": dados.get("descricao"),
                "dificuldade": dados.get("dificuldade"),
                "modalidade": dados.get("modalidade", "Trekking"),
                "distancia_km": dados.get("distancia_km", 0.0),
                "cidade": dados.get("cidade"),
                "estado": dados.get("estado"),
                "data_atividade": dados.get("data_atividade"), # Adicionado para sua busca de datas
                "criado_por": criado_por,
                "id_guia": guia_responsavel,
                "ativo": True,
                "createdAt": firestore.SERVER_TIMESTAMP
            }

            db.collection('trilhas').document(id_trilha).set(trilha)
            return {"mensagem": "Trilha cadastrada com sucesso!", "id": id_trilha}, 201
        except Exception as e:
            return {"erro": f"Erro interno: {str(e)}"}, 500
        
    @staticmethod
    def listar_trilhas(db):
        try:
            trilhas_ref = db.collection('trilhas').stream()
            trilhas = [doc.to_dict() for doc in trilhas_ref]
            return trilhas, 200
        except Exception as e:
            return {"erro": f"Erro ao buscar trilhas: {str(e)}"}, 500
    
    @staticmethod
    def buscar_trilha_por_id(db, id_trilha):
        try:
            doc_ref = db.collection('trilhas').document(id_trilha).get()
            if doc_ref.exists:
                return doc_ref.to_dict(), 200
            return {"erro": "Trilha não encontrada"}, 404
        except Exception as e:
            return {"erro": f"Erro ao buscar trilha: {str(e)}"}, 500

    @staticmethod
    def listar_trilhas_por_data(db, data_inicio, data_fim):
        # Sua funcionalidade de busca por datas
        try:
            trilhas_ref = db.collection('trilhas')\
                .where('data_atividade', '>=', data_inicio)\
                .where('data_atividade', '<=', data_fim).stream()
            
            trilhas = [doc.to_dict() for doc in trilhas_ref]
            
            if trilhas:
                return trilhas, 200
            return {"mensagem": "Nenhuma trilha encontrada nesse período"}, 404
        except Exception as e:
            return {"erro": f"Ocorreu um erro na busca por data: {str(e)}"}, 500
        
    @staticmethod
    def atualizar_trilha(db, id_trilha, dados, usuario_atual):
        try:
            if not dados:
                return {"erro": "Dados incompletos"}, 400

            doc_ref = db.collection('trilhas').document(id_trilha)
            doc = doc_ref.get()
            if not doc.exists:
                return {"erro": "Trilha não encontrada"}, 404

            if not Trilhas._usuario_pode_gerenciar_trilha(doc.to_dict(), usuario_atual):
                return {"erro": "Acesso negado. Você não tem permissão para gerenciar esta trilha."}, 403

            doc_ref.update(dados)
            return {"mensagem": "Trilha atualizada com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Erro ao atualizar trilha: {str(e)}"}, 500
        
    @staticmethod
    def deletar_trilha(db, id_trilha, usuario_atual):
        try:
            doc_ref = db.collection('trilhas').document(id_trilha)
            doc = doc_ref.get()

            if not doc.exists:
                return {"erro": "Trilha não encontrada"}, 404

            if not Trilhas._usuario_pode_gerenciar_trilha(doc.to_dict(), usuario_atual):
                return {"erro": "Acesso negado. Você não tem permissão para gerenciar esta trilha."}, 403

            doc_ref.delete()
            return {"mensagem": "Trilha deletada com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Erro ao deletar trilha: {str(e)}"}, 500
        
#busca avançada com filtros dinâmicos  
    @staticmethod
    def buscar_trilhas_avancado(db, filtros):
        try:
            # 1. Começamos apontando para a coleção inteira
            query = db.collection('trilhas')
            
            # 2. Aplicamos os filtros dinamicamente usando FieldFilter
            if filtros.get('dificuldade'):
                query = query.where(filter=FieldFilter('dificuldade', '==', filtros.get('dificuldade')))
                
            if filtros.get('estado'):
                query = query.where(filter=FieldFilter('estado', '==', filtros.get('estado')))
                
            if filtros.get('cidade'):
                query = query.where(filter=FieldFilter('cidade', '==', filtros.get('cidade')))

            # --- FILTRO DE PERÍODO (RANGE) ---
            # Busca trilhas a partir da data de início
            if filtros.get('data_inicio'):
                query = query.where(filter=FieldFilter('data_atividade', '>=', filtros.get('data_inicio')))
                
            # Limita a busca até a data final
            if filtros.get('data_fim'):
                query = query.where(filter=FieldFilter('data_atividade', '<=', filtros.get('data_fim')))
                
            # Filtro para garantir que só traga trilhas ativas
            query = query.where(filter=FieldFilter('ativo', '==', True))

            # 3. Executamos a busca final
            resultados = query.stream()
            lista_trilhas = [doc.to_dict() for doc in resultados]
            
            if not lista_trilhas:
                return {"mensagem": "Nenhuma trilha encontrada com esses filtros."}, 404
                
            return lista_trilhas, 200
            
        except Exception as e:
            return {"erro": f"Erro na busca avançada: {str(e)}"}, 500