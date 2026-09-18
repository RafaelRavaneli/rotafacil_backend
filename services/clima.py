import requests


class Clima:
    CODIGOS_TEMPO = {
        0: "Céu limpo", 1: "Principalmente limpo", 2: "Parcialmente nublado", 3: "Nublado",
        45: "Neblina", 48: "Neblina com geada",
        51: "Garoa leve", 53: "Garoa moderada", 55: "Garoa intensa",
        61: "Chuva leve", 63: "Chuva moderada", 65: "Chuva forte",
        71: "Neve leve", 73: "Neve moderada", 75: "Neve forte",
        80: "Pancadas de chuva leves", 81: "Pancadas de chuva moderadas", 82: "Pancadas de chuva fortes",
        95: "Tempestade", 96: "Tempestade com granizo leve", 99: "Tempestade com granizo forte",
    }

    @staticmethod
    def obter_previsao_trilha(db, id_trilha):
        try:
            trilha_doc = db.collection('trilhas').document(id_trilha).get()
            if not trilha_doc.exists:
                return {"erro": "Trilha não encontrada"}, 404

            dados_trilha = trilha_doc.to_dict()
            latitude = dados_trilha.get('latitude')
            longitude = dados_trilha.get('longitude')

            if latitude is None or longitude is None:
                return {"erro": "Esta trilha não possui coordenadas cadastradas. Não é possível obter previsão do tempo."}, 400

            resposta = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                    "timezone": "auto",
                    "forecast_days": 16,
                },
                timeout=10
            )
            resposta.raise_for_status()
            dados_clima = resposta.json()

            dias = dados_clima.get("daily", {})
            datas = dias.get("time", [])

            previsao = []
            for i, data in enumerate(datas):
                codigo = dias.get("weathercode", [None] * len(datas))[i]
                previsao.append({
                    "data": data,
                    "temperatura_maxima": dias.get("temperature_2m_max", [None] * len(datas))[i],
                    "temperatura_minima": dias.get("temperature_2m_min", [None] * len(datas))[i],
                    "probabilidade_chuva": dias.get("precipitation_probability_max", [None] * len(datas))[i],
                    "condicao": Clima.CODIGOS_TEMPO.get(codigo, "Desconhecido"),
                })

            data_atividade = dados_trilha.get('data_atividade')
            previsao_do_dia = next((p for p in previsao if p['data'] == data_atividade), None)

            return {
                "trilha": dados_trilha.get('nome'),
                "data_atividade": data_atividade,
                "previsao_do_dia_da_trilha": previsao_do_dia,
                "previsao_completa": previsao,
            }, 200

        except requests.exceptions.RequestException as e:
            return {"erro": f"Erro ao consultar serviço de previsão do tempo: {str(e)}"}, 502
        except Exception as e:
            return {"erro": f"Erro interno: {str(e)}"}, 500