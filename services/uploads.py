import requests
import os
from dotenv import load_dotenv

# O override=True força o Python a ler as alterações mais recentes do seu arquivo .env
load_dotenv(override=True)

class Uploads:
    @staticmethod
    def enviar_para_imgbb(arquivo_imagem):
        try:
            # Puxando ambas as variáveis de ambiente
            IMGBB_API_KEY = os.getenv('IMGBB_API_KEY')
            URL_IMGBB = os.getenv('URL_IMGBB')

            # Validação de segurança para garantir que as variáveis existem
            if not IMGBB_API_KEY or not URL_IMGBB:
                return {"erro": "Chave de API ou URL do ImgBB não configuradas no servidor (.env)"}, 500

            # O .strip() garante que qualquer espaço invisível copiado sem querer seja removido da chave
            payload = {
                "key": IMGBB_API_KEY.strip(),
            }

            arquivos = {
                "image": (arquivo_imagem.filename, arquivo_imagem.read(), arquivo_imagem.content_type)
            }

            # Executa a requisição para a API do ImgBB
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