from services.community import Community
from services.disponibilidades import Disponibilidades
import uuid
import math
from datetime import date, datetime
import pygeohash as pgh
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

class Trilhas:
    CAMPOS_EDITAVEIS = {
        'nome', 'descricao', 'dificuldade', 'modalidade', 'distancia_km',
        'cidade', 'estado', 'data_atividade', 'latitude', 'longitude',
        'imagem_url', 'acessivel', 'itens_recomendados', 'trajeto',
        'id_guia', 'ativo', 'preco', 'capacidade', 'horario_inicio',
        'horario_fim', 'data_fim', 'data_hora_inicio', 'data_hora_fim',
        'atividades', 'arquivado', 'ponto_encontro', 'datas',
    }

    @staticmethod
    def _validar_campos_publicos(dados, criacao=False):
        proibidos = sorted(set(dados) - Trilhas.CAMPOS_EDITAVEIS)
        if proibidos:
            return f"Campos não permitidos: {', '.join(proibidos)}"
        limites = {'nome': 160, 'descricao': 4000, 'dificuldade': 40,
                   'modalidade': 80, 'cidade': 120, 'estado': 2,
                   'ponto_encontro': 250}
        for campo, limite in limites.items():
            if campo not in dados:
                continue
            valor = dados.get(campo)
            if not isinstance(valor, str) or not valor.strip() or len(valor.strip()) > limite:
                return f"{campo} deve ser um texto de 1 a {limite} caracteres"
            dados[campo] = valor.strip()
        if criacao:
            for campo in ('nome', 'descricao', 'dificuldade'):
                if campo not in dados:
                    return f"Campo obrigatório: {campo}"
        if 'preco' in dados:
            try:
                preco = float(str(dados['preco']).strip().replace(',', '.'))
            except (TypeError, ValueError):
                return 'Preço deve ser um número válido'
            if not math.isfinite(preco) or preco < 0:
                return 'Preço deve ser um número maior ou igual a zero'
            dados['preco'] = round(preco, 2)
        for campo in ('ativo', 'acessivel', 'arquivado'):
            if campo in dados and not isinstance(dados[campo], bool):
                return f"{campo} deve ser verdadeiro ou falso"
        if dados.get('data_atividade'):
            try:
                data_atividade = date.fromisoformat(str(dados['data_atividade']))
            except ValueError:
                return 'data_atividade deve estar no formato AAAA-MM-DD'
            if data_atividade < date.today():
                return 'A data da atividade não pode estar no passado'
        if 'dificuldade' in dados:
            dificuldades = {
                'fácil': 'Iniciante', 'facil': 'Iniciante',
                'iniciante': 'Iniciante', 'moderada': 'Intermediário',
                'moderado': 'Intermediário', 'intermediário': 'Intermediário',
                'intermediario': 'Intermediário', 'difícil': 'Avançado',
                'dificil': 'Avançado', 'avançado': 'Avançado',
                'avancado': 'Avançado',
            }
            dificuldade = dificuldades.get(dados['dificuldade'].lower())
            if dificuldade is None:
                return 'dificuldade deve ser Iniciante, Intermediário ou Avançado'
            dados['dificuldade'] = dificuldade
        if 'atividades' in dados:
            atividades = dados['atividades']
            if (not isinstance(atividades, list) or not atividades or len(atividades) > 50 or
                    not all(isinstance(item, str) and 0 < len(item.strip()) <= 80 for item in atividades)):
                return 'atividades deve ser uma lista não vazia de textos'
            dados['atividades'] = list(dict.fromkeys(item.strip() for item in atividades))
        if 'datas' in dados and not isinstance(dados['datas'], list):
            return 'datas deve ser uma lista de saídas do roteiro'
        return None

    @staticmethod
    def _normalizar_datas(dados, atual=None, validar_futuro=True):
        combinado = {**(atual or {}), **dados}
        capacidade = combinado.get('capacidade', 12)
        try:
            capacidade = int(capacidade)
        except (TypeError, ValueError) as exc:
            raise ValueError('Capacidade deve ser um número inteiro.') from exc
        if capacidade <= 0:
            raise ValueError('Capacidade deve ser maior que zero.')

        entradas = combinado.get('datas')
        if entradas is None:
            inicio = combinado.get('data_hora_inicio')
            fim = combinado.get('data_hora_fim')
            if inicio or fim:
                entradas = [{'id': combinado.get('id_data'), 'data_hora_inicio': inicio,
                             'data_hora_fim': fim}]
            else:
                data_inicio = combinado.get('data_atividade')
                data_fim = combinado.get('data_fim') or data_inicio
                hora_inicio = combinado.get('horario_inicio')
                hora_fim = combinado.get('horario_fim')
                entradas = [] if not any((data_inicio, hora_inicio, hora_fim)) else [{
                    'data_hora_inicio': f'{data_inicio}T{hora_inicio}' if data_inicio and hora_inicio else None,
                    'data_hora_fim': f'{data_fim}T{hora_fim}' if data_fim and hora_fim else None,
                }]
        if not entradas:
            return capacidade, []
        if len(entradas) > 100:
            raise ValueError('O roteiro permite no máximo 100 datas.')

        normalizadas = []
        intervalos = []
        for entrada in entradas:
            if not isinstance(entrada, dict):
                raise ValueError('Cada data do roteiro deve possuir início e fim.')
            inicio_iso = entrada.get('data_hora_inicio') or entrada.get('startDateTime')
            fim_iso = entrada.get('data_hora_fim') or entrada.get('endDateTime')
            if not inicio_iso or not fim_iso:
                raise ValueError('Informe data e hora de início e fim de cada saída.')
            try:
                inicio = datetime.fromisoformat(str(inicio_iso).replace('Z', '+00:00'))
                fim = datetime.fromisoformat(str(fim_iso).replace('Z', '+00:00'))
            except ValueError as exc:
                raise ValueError('Datas do roteiro devem estar no formato ISO 8601.') from exc
            if inicio.tzinfo is not None:
                inicio = inicio.replace(tzinfo=None)
            if fim.tzinfo is not None:
                fim = fim.replace(tzinfo=None)
            if fim <= inicio:
                raise ValueError('O fim de cada saída deve ser posterior ao início.')
            if validar_futuro and inicio.date() < date.today():
                raise ValueError('A data da atividade não pode estar no passado')
            if any(inicio < outro_fim and fim > outro_inicio
                   for outro_inicio, outro_fim in intervalos):
                raise ValueError('As datas do mesmo roteiro não podem se sobrepor.')
            intervalos.append((inicio, fim))
            normalizadas.append({
                'id': str(entrada.get('id') or uuid.uuid4()),
                'data_hora_inicio': inicio.isoformat(timespec='minutes'),
                'data_hora_fim': fim.isoformat(timespec='minutes'),
            })
        normalizadas.sort(key=lambda item: item['data_hora_inicio'])
        return capacidade, normalizadas

    @staticmethod
    def _campos_data_legados(datas):
        if not datas:
            return {
                'data_atividade': None, 'data_fim': None,
                'horario_inicio': None, 'horario_fim': None,
                'data_hora_inicio': None, 'data_hora_fim': None,
            }
        primeira = datas[0]
        inicio = datetime.fromisoformat(primeira['data_hora_inicio'])
        fim = datetime.fromisoformat(primeira['data_hora_fim'])
        return {
            'data_atividade': inicio.date().isoformat(),
            'data_fim': fim.date().isoformat(),
            'horario_inicio': inicio.strftime('%H:%M'),
            'horario_fim': fim.strftime('%H:%M'),
            'data_hora_inicio': primeira['data_hora_inicio'],
            'data_hora_fim': primeira['data_hora_fim'],
        }

    @staticmethod
    def _planejamento(dados, atual=None):
        combinado = {**(atual or {}), **dados}
        capacidade = combinado.get('capacidade', 12)
        try:
            capacidade = int(capacidade)
        except (TypeError, ValueError) as exc:
            raise ValueError('Capacidade deve ser um número inteiro.') from exc
        if capacidade <= 0:
            raise ValueError('Capacidade deve ser maior que zero.')
        inicio_iso = combinado.get('data_hora_inicio')
        fim_iso = combinado.get('data_hora_fim')
        if bool(inicio_iso) != bool(fim_iso):
            raise ValueError('Informe data e hora de início e fim do roteiro.')
        if inicio_iso and fim_iso:
            try:
                inicio_dt = datetime.fromisoformat(str(inicio_iso).replace('Z', '+00:00'))
                fim_dt = datetime.fromisoformat(str(fim_iso).replace('Z', '+00:00'))
            except ValueError as exc:
                raise ValueError('Data e hora do roteiro devem estar no formato ISO 8601.') from exc
            if inicio_dt.tzinfo is not None:
                inicio_dt = inicio_dt.replace(tzinfo=None)
            if fim_dt.tzinfo is not None:
                fim_dt = fim_dt.replace(tzinfo=None)
        else:
            data_inicio = combinado.get('data_atividade')
            data_fim = combinado.get('data_fim') or data_inicio
            inicio = combinado.get('horario_inicio')
            fim = combinado.get('horario_fim')
            if not any((data_inicio, inicio, fim)):
                return capacidade, None, None, None, None
            if not data_inicio or not inicio or not fim:
                raise ValueError('Informe data e hora de início e fim do roteiro.')
            try:
                inicio_dt = datetime.fromisoformat(
                    f"{data_inicio}T{Disponibilidades._hora(inicio, 'horario_inicio').strftime('%H:%M')}"
                )
                fim_dt = datetime.fromisoformat(
                    f"{data_fim}T{Disponibilidades._hora(fim, 'horario_fim').strftime('%H:%M')}"
                )
            except ValueError as exc:
                raise ValueError('Data e hora do roteiro são inválidas.') from exc
        if fim_dt <= inicio_dt:
            raise ValueError('O fim do roteiro deve ser posterior ao início.')
        inicio_iso = inicio_dt.isoformat(timespec='minutes')
        fim_iso = fim_dt.isoformat(timespec='minutes')
        return (
            capacidade,
            inicio_dt.strftime('%H:%M'),
            fim_dt.strftime('%H:%M'),
            inicio_iso,
            fim_iso,
        )

    @staticmethod
    def _conflito_agenda(db, guia_id, inicio_iso, fim_iso, ignorar=None):
        if not guia_id or not inicio_iso or not fim_iso:
            return False
        inicio_dt = datetime.fromisoformat(inicio_iso)
        fim_dt = datetime.fromisoformat(fim_iso)
        dia = inicio_dt.date()
        while dia <= fim_dt.date():
            inicio_dia = inicio_dt.strftime('%H:%M') if dia == inicio_dt.date() else '00:00'
            fim_dia = fim_dt.strftime('%H:%M') if dia == fim_dt.date() else '23:59'
            if Disponibilidades.conflito_bloqueio(
                    db, guia_id, dia.isoformat(), inicio_dia, fim_dia):
                return True
            dia = date.fromordinal(dia.toordinal() + 1)
        for doc in db.collection('trilhas').where('id_guia', '==', guia_id).stream():
            if doc.id == ignorar:
                continue
            item = doc.to_dict() or {}
            if item.get('ativo') is False:
                continue
            outras_datas = item.get('datas') or [{
                'data_hora_inicio': item.get('data_hora_inicio'),
                'data_hora_fim': item.get('data_hora_fim'),
            }]
            for outra in outras_datas:
                try:
                    outro_inicio = datetime.fromisoformat(outra.get('data_hora_inicio'))
                    outro_fim = datetime.fromisoformat(outra.get('data_hora_fim'))
                except (AttributeError, TypeError, ValueError):
                    outra_data = item.get('data_atividade')
                    if not outra_data:
                        continue
                    outro_inicio = datetime.fromisoformat(
                        f"{outra_data}T{item.get('horario_inicio', '00:00')}"
                    )
                    outro_fim = datetime.fromisoformat(
                        f"{item.get('data_fim') or outra_data}T{item.get('horario_fim', '23:59')}"
                    )
                if inicio_dt < outro_fim and fim_dt > outro_inicio:
                    return True
        return False

    @staticmethod
    def _usuario_pode_gerenciar_trilha(dados_trilha, usuario_atual):
        """
        Regra compartilhada entre atualizar e deletar trilha:
        só o criador ou um admin podem mexer. O guia responsável executa o
        roteiro, mas não recebe propriedade sobre um roteiro da agência.
        Registros legados sem criador continuam sob gestão do guia indicado.
        """
        criador = dados_trilha.get('criado_por')
        guia = dados_trilha.get('id_guia')

        papel = (usuario_atual.get('tipo') or '').strip().lower()
        email_usuario = usuario_atual.get('email')
        id_usuario = usuario_atual.get('id')

        eh_admin = papel == 'admin'
        eh_criador = email_usuario == criador or id_usuario == criador
        eh_guia_responsavel = email_usuario == guia or id_usuario == guia

        eh_responsavel_legado = not criador and eh_guia_responsavel

        return eh_admin or eh_criador or eh_responsavel_legado

    @staticmethod
    def _distancia_valida(value):
        if isinstance(value, bool):
            raise ValueError('Distância inválida')
        number = float(str(value).strip().replace(',', '.'))
        if not math.isfinite(number) or number <= 0:
            raise ValueError('Distância inválida')
        return number

    @staticmethod
    def _serializar_trilha(db, doc, responsaveis=None):
        data = {**(doc.to_dict() or {}), 'id': doc.id}
        if not data.get('datas') and data.get('data_hora_inicio') and data.get('data_hora_fim'):
            data['datas'] = [{
                'id': f'legacy-{doc.id}',
                'data_hora_inicio': data['data_hora_inicio'],
                'data_hora_fim': data['data_hora_fim'],
            }]
        cache = responsaveis if responsaveis is not None else {}
        identifier = data.get('id_guia')
        if isinstance(identifier, str) and identifier and '/' not in identifier:
            if identifier not in cache:
                user = db.collection('usuarios').document(identifier).get()
                if not user.exists:
                    user = next(iter(db.collection('usuarios').where('email', '==', identifier).stream()), None)
                user_data = (user.to_dict() or {}) if user is not None and user.exists else {}
                public_name = user_data.get('nome')
                cache[identifier] = {
                    'nome': public_name if isinstance(public_name, str) and public_name.strip() else None,
                    'tipo': user_data.get('tipo'),
                }
            responsible = cache[identifier]
            data['nome_guia'] = responsible.get('nome')
            data['tipo_responsavel'] = responsible.get('tipo')
        return data

    @staticmethod
    def _ocorre_no_periodo(trilha, data_inicio=None, data_fim=None):
        if not data_inicio and not data_fim:
            return True
        datas = trilha.get('datas') or [{
            'data_hora_inicio': trilha.get('data_hora_inicio') or trilha.get('data_atividade'),
            'data_hora_fim': trilha.get('data_hora_fim') or trilha.get('data_fim') or
                             trilha.get('data_atividade'),
        }]
        for item in datas:
            inicio = str(item.get('data_hora_inicio') or '')[:10]
            fim = str(item.get('data_hora_fim') or inicio)[:10]
            if inicio and (not data_fim or inicio <= data_fim) and (not data_inicio or fim >= data_inicio):
                return True
        return False

    @staticmethod
    def _tem_agendamentos_ativos(db, id_trilha):
        finais = {'cancelado', 'cancelada', 'cancelled', 'canceled', 'concluido', 'concluído', 'completed'}
        for doc in db.collection('agendamentos').where('id_trilha', '==', id_trilha).stream():
            status = str((doc.to_dict() or {}).get('status') or '').strip().lower()
            if status not in finais:
                return True
        return False

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
            
            erro_campos = Trilhas._validar_campos_publicos(dados, criacao=True)
            if erro_campos:
                return {"erro": erro_campos}, 400

            if 'distancia_km' in dados:
                try:
                    dados['distancia_km'] = Trilhas._distancia_valida(dados['distancia_km'])
                except (TypeError, ValueError):
                    return {'erro': 'Informe uma distância do percurso válida, maior que zero, em quilômetros.'}, 400

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

            try:
                capacidade, datas = Trilhas._normalizar_datas(dados)
            except ValueError as error:
                return {'erro': str(error)}, 400
            campos_data = Trilhas._campos_data_legados(datas)

            id_trilha = str(uuid.uuid4())
            criado_por = usuario_atual.get("email") if isinstance(usuario_atual, dict) else usuario_atual 
            guia_responsavel = dados.get("id_guia") or usuario_atual.get("id")
            if not Community.can_assign(db, usuario_atual, guia_responsavel):
                return {"erro": "O guia precisa aceitar o convite da agência antes de ser vinculado."}, 403
            if any(Trilhas._conflito_agenda(
                    db, guia_responsavel, item['data_hora_inicio'],
                    item['data_hora_fim']) for item in datas):
                return {"erro": "O responsável já possui atividade ou bloqueio neste horário."}, 409
            trilha = {
                "id": id_trilha,
                "nome": dados.get("nome"),
                "descricao": dados.get("descricao"),
                "dificuldade": dados.get("dificuldade"),
                "modalidade": dados.get("modalidade", "Trekking"),
                "atividades": dados.get("atividades") or [dados.get("modalidade", "Trilha")],
                "distancia_km": dados.get("distancia_km", 0.0),
                "cidade": dados.get("cidade"),
                "estado": dados.get("estado"),
                **campos_data,
                "datas": datas,
                "latitude": latitude,
                "longitude": longitude,
                "ponto_encontro": dados.get("ponto_encontro"),
                "geohash": geohash,
                "imagem_url": dados.get("imagem_url"),
                "acessivel": bool(dados.get("acessivel", False)),
                "itens_recomendados": itens_recomendados,
                "trajeto": trajeto,
                "criado_por": criado_por,
                "id_guia": guia_responsavel,
                "ativo": bool(dados.get("ativo", True)),
                "arquivado": False,
                "preco": dados.get("preco", 0),
                "capacidade": capacidade,
                "createdAt": firestore.SERVER_TIMESTAMP
            }

            db.collection('trilhas').document(id_trilha).set(trilha)
            return {"mensagem": "Roteiro cadastrado com sucesso!", "id": id_trilha}, 201
        except Exception as e:
            return {"erro": f"Erro interno: {str(e)}"}, 500
        
    @staticmethod
    def listar_trilhas(db):
        try:
            trilhas_ref = db.collection('trilhas').stream()
            responsaveis = {}
            trilhas = [Trilhas._serializar_trilha(db, doc, responsaveis) for doc in trilhas_ref]
            return trilhas, 200
        except Exception as e:
            return {"erro": f"Erro ao buscar roteiros: {str(e)}"}, 500
    
    @staticmethod
    def buscar_trilha_por_id(db, id_trilha):
        try:
            doc_ref = db.collection('trilhas').document(id_trilha).get()
            if doc_ref.exists:
                return Trilhas._serializar_trilha(db, doc_ref), 200
            return {"erro": "Roteiro não encontrado"}, 404
        except Exception as e:
            return {"erro": f"Erro ao buscar roteiro: {str(e)}"}, 500

    @staticmethod
    def listar_trilhas_por_data(db, data_inicio, data_fim):
        try:
            responsaveis = {}
            trilhas = [
                Trilhas._serializar_trilha(db, doc, responsaveis)
                for doc in db.collection('trilhas').stream()
            ]
            trilhas = [item for item in trilhas if Trilhas._ocorre_no_periodo(
                item, data_inicio, data_fim)]
            
            if trilhas:
                return trilhas, 200
            return {"mensagem": "Nenhum roteiro encontrado nesse período"}, 404
        except Exception as e:
            return {"erro": f"Ocorreu um erro na busca por data: {str(e)}"}, 500
        
    @staticmethod
    def atualizar_trilha(db, id_trilha, dados, usuario_atual):
        try:
            if not dados:
                return {"erro": "Dados incompletos"}, 400

            erro_campos = Trilhas._validar_campos_publicos(dados)
            if erro_campos:
                return {"erro": erro_campos}, 400

            if 'distancia_km' in dados:
                try:
                    dados['distancia_km'] = Trilhas._distancia_valida(dados['distancia_km'])
                except (TypeError, ValueError):
                    return {'erro': 'Informe uma distância do percurso válida, maior que zero, em quilômetros.'}, 400

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
                return {"erro": "Roteiro não encontrado"}, 404

            if not Trilhas._usuario_pode_gerenciar_trilha(doc.to_dict(), usuario_atual):
                return {"erro": "Acesso negado. Você não tem permissão para gerenciar este roteiro."}, 403

            try:
                altera_datas = any(campo in dados for campo in {
                    'datas', 'data_atividade', 'data_fim', 'horario_inicio',
                    'horario_fim', 'data_hora_inicio', 'data_hora_fim',
                })
                capacidade, datas = Trilhas._normalizar_datas(
                    dados, doc.to_dict(), validar_futuro=altera_datas)
            except ValueError as error:
                return {'erro': str(error)}, 400
            dados['capacidade'] = capacidade
            dados['datas'] = datas
            dados.update(Trilhas._campos_data_legados(datas))

            if dados.get('ativo') is False and Trilhas._tem_agendamentos_ativos(db, id_trilha):
                return {'erro': 'Este roteiro possui reservas ativas. Cancele ou conclua essas reservas antes de desativá-lo.'}, 409

            atual = doc.to_dict()
            if dados.get('arquivado') is True and atual.get('ativo') is not False:
                return {'erro': 'Desative o roteiro antes de arquivá-lo.'}, 409
            if dados.get('ativo') is True:
                dados['arquivado'] = False

            if 'id_guia' in dados and dados['id_guia'] != doc.to_dict().get('id_guia'):
                if not isinstance(dados['id_guia'], str) or not Community.can_assign(db, usuario_atual, dados['id_guia']):
                    return {"erro": "Guia não vinculado à sua conta."}, 403
            combinado = {**doc.to_dict(), **dados}
            if any(Trilhas._conflito_agenda(
                    db, combinado.get('id_guia'), item['data_hora_inicio'],
                    item['data_hora_fim'], ignorar=id_trilha) for item in datas):
                return {"erro": "O responsável já possui atividade ou bloqueio neste horário."}, 409
            doc_ref.update(dados)
            return {"mensagem": "Roteiro atualizado com sucesso!"}, 200
        except Exception as e:
            return {"erro": f"Erro ao atualizar roteiro: {str(e)}"}, 500
             
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
            resultados = query.stream()
            responsaveis = {}
            lista_trilhas = [Trilhas._serializar_trilha(db, doc, responsaveis) for doc in resultados]

            data_inicio = filtros.get('data_inicio')
            data_fim = filtros.get('data_fim')
            if data_inicio or data_fim:
                lista_trilhas = [t for t in lista_trilhas if Trilhas._ocorre_no_periodo(
                    t, data_inicio, data_fim)]

            if busca_geografica:
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
                return {"mensagem": "Nenhum roteiro encontrado com esses filtros."}, 404

            return lista_trilhas, 200

        except Exception as e:
            return {"erro": f"Erro na busca avançada: {str(e)}"}, 500
    @staticmethod
    def deletar_trilha(db, id_trilha, usuario_atual):
        doc_ref = db.collection('trilhas').document(id_trilha)
        doc = doc_ref.get()
        if not doc.exists:
            return {"erro": "Roteiro não encontrado"}, 404
        if not Trilhas._usuario_pode_gerenciar_trilha(doc.to_dict(), usuario_atual):
            return {"erro": "Você não tem permissão para excluir este roteiro."}, 403
        try:
            tem_reservas = Trilhas._tem_agendamentos_ativos(db, id_trilha)
        except Exception:
            return {'erro': 'Não foi possível verificar as reservas do roteiro. Tente novamente.'}, 500
        if tem_reservas:
            return {'erro': 'Este roteiro possui reservas ativas. Cancele ou conclua essas reservas antes de desativá-lo.'}, 409
        # Mantém referências de agendamentos já existentes.
        doc_ref.update({"ativo": False})
        return {"mensagem": "Roteiro desativado com sucesso."}, 200
