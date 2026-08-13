import firebase_admin
from firebase_admin import credentials, firestore

# Tratamento de erro para evitar que o Firebase tente inicializar mais de uma vez
try:
    # ATENÇÃO: Substitua 'caminho_para_sua_chave.json' pelo nome real do arquivo 
    # JSON que você baixou do Firebase (ex: 'rota-facil-firebase-adminsdk.json').
    # Lembre-se de garantir que esse arquivo JSON esteja no seu .gitignore!
    cred = credentials.Certificate("firebase-key.json")
    firebase_admin.initialize_app(cred)
except ValueError:
    # Se o aplicativo já estiver inicializado, o Firebase lança um ValueError.
    # O comando 'pass' faz o Python ignorar o erro e continuar normalmente.
    pass

# Inicializa o cliente do banco de dados e o exporta na variável 'bd'
bd = firestore.client()