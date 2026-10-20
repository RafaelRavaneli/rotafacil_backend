import os

import requests


class Geocodificacao:
    URL = 'https://api.openrouteservice.org/geocode/search'

    @staticmethod
    def buscar(texto):
        consulta = str(texto or '').strip()
        if len(consulta) < 3 or len(consulta) > 250:
            return {'erro': 'Informe um endereço ou ponto de encontro válido.'}, 400

        api_key = os.getenv('ORS_API_KEY', '').strip()
        if not api_key:
            return {'erro': 'A busca de endereço não está configurada.'}, 503

        try:
            resposta = requests.get(
                Geocodificacao.URL,
                params={
                    'api_key': api_key,
                    'text': consulta,
                    'size': 5,
                    'boundary.country': 'BR',
                },
                timeout=10,
            )
            resposta.raise_for_status()
            resultados = []
            for feature in resposta.json().get('features', []):
                coordenadas = feature.get('geometry', {}).get('coordinates', [])
                if len(coordenadas) < 2:
                    continue
                propriedades = feature.get('properties', {})
                resultados.append({
                    'label': propriedades.get('label') or propriedades.get('name') or consulta,
                    'cidade': propriedades.get('locality') or propriedades.get('county'),
                    'estado': propriedades.get('region_a') or propriedades.get('region'),
                    'latitude': coordenadas[1],
                    'longitude': coordenadas[0],
                })
            return resultados, 200
        except requests.exceptions.RequestException:
            return {'erro': 'Não foi possível consultar o endereço agora.'}, 502

