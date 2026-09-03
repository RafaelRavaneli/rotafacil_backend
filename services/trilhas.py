import uuid
import math
import pygeohash as pgh
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
    def _calcular_distancia_km(lat1, lon1, lat2, lon2):
        """Distância em linha reta (Haversine) entre duas coordenadas, em km."""
        R = 6371
        lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    @staticmethod
    def _precisao_geohash_para_raio(raio_km):
        """
        Escolhe quantos caracteres de geohash usar na busca, com base no raio
        pedido. Referência de tamanho de célula por precisão: geohash.org / Wikipedia.
        Escolhe a maior precisão (célula mais específica) que ainda cobre o raio inteiro.
        """
        tabela = [
            (1, 5000), (2, 1250), (3, 156), (4, 39),
            (5, 4.9), (6, 1.2), (7, 0.153), (8, 0.038), (9, 0.0048),
        ]
        precisao_escolhida = 1
        for precisao, tamanho_celula_km in tabela:
            if tamanho_celula_km >= raio_km:
                precisao_escolhida = precisao
            else:
                break
        return precisao_escolhida

    @staticmethod
    def _validar_lista_coordenadas(lista):
        """Valida uma lista de pontos [{'latitude':.., 'longitude':..}, ...], usada tanto
        pro trajeto da trilha quanto (futuramente) por outras features baseadas em rota."""
        if not isinstance(lista, list):
            return False, "deve ser uma lista de pontos"
        pontos_validados = []
        for ponto in lista:
            if not isinstance(ponto, dict) or "latitude" not in ponto or "longitude" not in ponto:
                return False, "cada ponto precisa ter 'latitude' e 'longitude'"
            try:
                lat = float(ponto["latitude"])
                lon = float(ponto["longitude"])
            except (TypeError, ValueError):
                return False, "latitude e longitude devem ser números válidos"
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                return False, "coordenada fora do intervalo válido"
            pontos_validados.append({"latitude": lat, "longitude": lon})
        return True, pontos_validados

    @staticmethod
    def cadastrar_trilha(db, dados, usuario_atual):
        try:
            if not dados:
                return {"erro": "Dados não enviados"}, 400
            
            campos_obrigatorios = ["nome", "descricao", "dificuldade"]
            for campo in campos_obrigatorios:
                if campo not in dados:
                    return {"erro": f"Campo obrigatório: {campo}"}, 400

            latitude = dados.get("latitude")
            longitude = dados.get("longitude")
            geohash = None
            if latitude is not None or longitude is not None:
                try:
                    latitude = float(latitude)
                    longitude = float(longitude)
                except (TypeError, ValueError):
                    return {"erro": "latitude e longitude devem ser números válidos"}, 400
                if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                    return {"erro": "Coordenadas fora do intervalo válido"}, 400
                geohash = pgh.encode(latitude, longitude, precision=9)

            itens_recomendados = dados.get("itens_recomendados", [])
            if not isinstance(itens_recomendados, list) or not all(isinstance(i, str) for i in itens_recomendados):
                return {"erro": "itens_recomendados deve ser uma lista de textos"}, 400

            trajeto = dados.get("trajeto", [])
            valido, resultado = Trilhas._validar_lista_coordenadas(trajeto)
            if not valido:
                return {"erro": f"Campo 'trajeto' inválido: {resultado}"}, 400
            trajeto = resultado

            id_trilha = str(uuid.uuid4())
            criado_por = usuario_atual.get("email") if isinstance(usuario_atual, dict) else usuario_atual 
            guia_responsavel = dados.get("id_guia", criado_por)     
            trilha = {
                "id": id_trilha,
                "nome": dados.get("nome"),
                "descricao": dados.get("descricao"),
                "dificuldade": dados.get("dificuldade"),
                "modalidade": dados.get("modalidade", "Trekking"),
                "distancia_km": dados.get("distancia_km", 0.0),
                "cidade": dados.get("cidade"),
                "estado": dados.get("estado"),
                "data_atividade": dados.get("data_atividade"),
                "latitude": latitude,
                "longitude": longitude,
                "geohash": geohash,
                "imagem_url": dados.get("imagem_url"),
                "acessivel": bool(dados.get("acessivel", False)),
                "itens_recomendados": itens_recomendados,
                "trajeto": trajeto,
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

            if "latitude" in dados and "longitude" in dados:
                try:
                    dados["latitude"] = float(dados["latitude"])
                    dados["longitude"] = float(dados["longitude"])
                except (TypeError, ValueError):
                    return {"erro": "latitude e longitude devem ser números válidos"}, 400
                dados["geohash"] = pgh.encode(dados["latitude"], dados["longitude"], precision=9)

            if "trajeto" in dados:
                valido, resultado = Trilhas._validar_lista_coordenadas(dados["trajeto"])
                if not valido:
                    return {"erro": f"Campo 'trajeto' inválido: {resultado}"}, 400
                dados["trajeto"] = resultado

            if "itens_recomendados" in dados:
                if not isinstance(dados["itens_recomendados"], list) or not all(isinstance(i, str) for i in dados["itens_recomendados"]):
                    return {"erro": "itens_recomendados deve ser uma lista de textos"}, 400

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
             
    #busca avançada com filtros dinâmicos  
    @staticmethod
    def buscar_trilhas_avancado(db, filtros):
        try:
            lat_usuario = filtros.get('latitude')
            lon_usuario = filtros.get('longitude')
            raio_km = filtros.get('raio_km')
            busca_geografica = bool(lat_usuario and lon_usuario and raio_km)

            query = db.collection('trilhas')

            # Filtros de igualdade: sempre podem ser combinados, geo ou não
            if filtros.get('dificuldade'):
                query = query.where(filter=FieldFilter('dificuldade', '==', filtros.get('dificuldade')))
                
            if filtros.get('estado'):
                query = query.where(filter=FieldFilter('estado', '==', filtros.get('estado')))

            if filtros.get('cidade'):
                query = query.where(filter=FieldFilter('cidade', '==', filtros.get('cidade')))
            query = query.where(filter=FieldFilter('ativo', '==', True))

            if filtros.get('acessivel') is not None:
                valor_acessivel = str(filtros.get('acessivel')).strip().lower() == 'true'
                query = query.where(filter=FieldFilter('acessivel', '==', valor_acessivel))
            query = query.where(filter=FieldFilter('ativo', '==', True))

            if busca_geografica:
                try:
                    lat_usuario = float(lat_usuario)
                    lon_usuario = float(lon_usuario)
                    raio_km = float(raio_km)
                except ValueError:
                    return {"erro": "latitude, longitude e raio_km devem ser números válidos"}, 400

                # O Firestore só permite UM campo com filtro de intervalo por consulta.
                # Como o geohash já ocupa esse papel aqui, o filtro de data (se enviado
                # junto) é aplicado depois, em Python, e não como where() do Firestore.
                precisao = max(1, Trilhas._precisao_geohash_para_raio(raio_km) - 1)
                prefixo = pgh.encode(lat_usuario, lon_usuario, precision=precisao)
                query = query.where(filter=FieldFilter('geohash', '>=', prefixo)) \
                             .where(filter=FieldFilter('geohash', '<=', prefixo + '\uf8ff'))
            else:
                # Sem busca geográfica: filtro de data por intervalo funciona normalmente
                if filtros.get('data_inicio'):
                    query = query.where(filter=FieldFilter('data_atividade', '>=', filtros.get('data_inicio')))
                if filtros.get('data_fim'):
                    query = query.where(filter=FieldFilter('data_atividade', '<=', filtros.get('data_fim')))

            resultados = query.stream()
            lista_trilhas = [doc.to_dict() for doc in resultados]

            if busca_geografica:
                # Filtro de data em Python, já que não pôde ir no Firestore junto do geohash
                data_inicio = filtros.get('data_inicio')
                data_fim = filtros.get('data_fim')
                if data_inicio:
                    lista_trilhas = [t for t in lista_trilhas if (t.get('data_atividade') or '') >= data_inicio]
                if data_fim:
                    lista_trilhas = [t for t in lista_trilhas if (t.get('data_atividade') or '') <= data_fim]

                # Refino final: distância exata (Haversine) + descarta falsos positivos do geohash
                trilhas_no_raio = []
                for trilha in lista_trilhas:
                    lat_trilha = trilha.get('latitude')
                    lon_trilha = trilha.get('longitude')
                    if lat_trilha is None or lon_trilha is None:
                        continue
                    distancia = Trilhas._calcular_distancia_km(lat_usuario, lon_usuario, lat_trilha, lon_trilha)
                    if distancia <= raio_km:
                        trilha['distancia_usuario_km'] = round(distancia, 2)
                        trilhas_no_raio.append(trilha)

                trilhas_no_raio.sort(key=lambda t: t['distancia_usuario_km'])
                lista_trilhas = trilhas_no_raio

            if not lista_trilhas:
                return {"mensagem": "Nenhuma trilha encontrada com esses filtros."}, 404

            return lista_trilhas, 200

        except Exception as e:
            return {"erro": f"Erro na busca avançada: {str(e)}"}, 500