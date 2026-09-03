import os
import requests


class Rotas:
    BASE_URL = "https://api.openrouteservice.org/v2/directions"
    PERFIS_VALIDOS = {
        "driving-car", "driving-hgv",
        "cycling-regular", "cycling-road", "cycling-mountain", "cycling-electric",
        "foot-walking", "foot-hiking", "wheelchair"
    }

    @staticmethod
    def calcular_rota(latitude_origem, longitude_origem, latitude_destino, longitude_destino, perfil="driving-car"):
        try:
            if perfil not in Rotas.PERFIS_VALIDOS:
                return {"erro": f"Perfil inválido. Use um de: {', '.join(sorted(Rotas.PERFIS_VALIDOS))}"}, 400

            api_key = os.getenv("ORS_API_KEY")
            if not api_key:
                return {"erro": "Chave da API de rotas (ORS_API_KEY) não configurada no servidor (.env)"}, 500

            headers = {
                "Authorization": api_key,
                "Accept": "application/geo+json, application/json; charset=utf-8"
            }
            # ATENÇÃO: OpenRouteService espera "longitude,latitude" (invertido do
            # padrão que usamos no resto do projeto, que é sempre latitude primeiro)
            params = {
                "start": f"{longitude_origem},{latitude_origem}",
                "end": f"{longitude_destino},{latitude_destino}"
            }

            resposta = requests.get(f"{Rotas.BASE_URL}/{perfil}", headers=headers, params=params, timeout=10)
            resposta.raise_for_status()
            dados = resposta.json()

            feature = (dados.get("features") or [{}])[0]
            propriedades = feature.get("properties", {})
            resumo = propriedades.get("summary", {})
            coordenadas = feature.get("geometry", {}).get("coordinates", [])

            # A resposta vem em [longitude, latitude] — convertemos de volta pro
            # padrão {latitude, longitude} que o resto da nossa API usa
            trajeto = [{"latitude": lat, "longitude": lon} for lon, lat in coordenadas]

            return {
                "distancia_km": round(resumo.get("distance", 0) / 1000, 2),
                "duracao_minutos": round(resumo.get("duration", 0) / 60, 1),
                "perfil": perfil,
                "trajeto": trajeto
            }, 200

        except requests.exceptions.HTTPError as e:
            codigo = e.response.status_code if e.response is not None else 502
            return {"erro": f"Erro ao consultar serviço de rotas: {str(e)}"}, codigo if codigo in (400, 401, 403, 404) else 502
        except requests.exceptions.RequestException as e:
            return {"erro": f"Erro ao consultar serviço de rotas: {str(e)}"}, 502
        except Exception as e:
            return {"erro": f"Erro interno: {str(e)}"}, 500