import requests
import os
from dotenv import load_dotenv

load_dotenv()

class Uploads:
    @staticmethod
    def enviar_para_imgbb(arquivo_imagem):
        try:
            # Puxando ambas as variáveis de ambiente (Ideia do José)
            IMGBB_API_KEY = os.getenv('IMGBB_API_KEY')
            URL_IMGBB = os.getenv('URL_IMGBB')

            # Validação dupla de segurança
            if not IMGBB_API_KEY or not URL_IMGBB:
                return {"erro": "Chave de API ou URL do ImgBB não configuradas no servidor (.env)"}, 500

            payload = {
                "key": IMGBB_API_KEY,
            }

            arquivos = {
                "image": (arquivo_imagem.filename, arquivo_imagem.read(), arquivo_imagem.content_type)
            }

            # Usando a variável de ambiente na requisição
            resposta = requests.post(URL_IMGBB, data=payload, files=arquivos)
            dados = resposta.json()

            if resposta.status_code == 200 and dados.get('success'):
                url_publica = dados['data']['url']
                return {
                    "mensagem": "Upload realizado com sucesso!",
                    "url": url_publica
                }, 200
            else:
                return {
                    "erro": "Falha ao enviar para o ImgBB",
                    "detalhes": dados.get('error', {}).get('message', 'Erro desconhecido')
                }, resposta.status_code

        except Exception as e:
            return {"erro": f"Erro interno no serviço de upload: {str(e)}"}, 500