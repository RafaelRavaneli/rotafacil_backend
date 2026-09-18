import os
from flask import Flask
# from flask_cors import CORS  # Descomente se estiver usando CORS para conectar com o Flutter

# Importa o blueprint que criamos na pasta routes
from routes.trilhas_routes import trilhas_bp
from routes.usuarios_routes import usuarios_bp
from routes.auth_routes import auth_bp
from routes.agendamentos_routes import agendamentos_bp
from routes.uploads_routes import uploads_bp
from routes.redefinicao_senha_routes import redefinicao_senha_bp
from routes.favoritos_routes import favoritos_bp
from routes.avaliacoes_routes import avaliacoes_bp
from services.agendador import iniciar_agendador

app = Flask(__name__)
# CORS(app)  # Descomente se estiver usando CORS

# Registra o Blueprint de trilhas
# O url_prefix='/api/trilhas' garante que a rota '/' lá no trilhas_routes.py 
# vire automaticamente '/api/trilhas/' no navegador/Postman.
app.register_blueprint(trilhas_bp, url_prefix='/api/trilhas')
app.register_blueprint(usuarios_bp, url_prefix='/api/usuarios')
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(agendamentos_bp, url_prefix='/api/agendamentos')
app.register_blueprint(uploads_bp, url_prefix='/api/uploads')
app.register_blueprint(redefinicao_senha_bp, url_prefix='/api/auth/senha')
app.register_blueprint(favoritos_bp, url_prefix='/api/favoritos')
app.register_blueprint(avaliacoes_bp, url_prefix='/api/avaliacoes')


# Rota de teste simples na raiz da API só para garantir que o servidor subiu
@app.route('/', methods=['GET'])
def index():
    return {"mensagem": "API do Rota Fácil rodando com sucesso na arquitetura MVC!"}, 200

if __name__ == '__main__':
    # Evita que o agendador rode em dobro por causa do reloader do modo debug do Flask
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        iniciar_agendador()
    app.run(debug=True)