import os
from flask import Flask, render_template
from flask_cors import CORS

# Importa o blueprint que criamos na pasta routes
from routes.trilhas_routes import trilhas_bp
from routes.usuarios_routes import usuarios_bp
from routes.auth_routes import auth_bp
from routes.agendamentos_routes import agendamentos_bp
from routes.uploads_routes import uploads_bp
from routes.redefinicao_senha_routes import redefinicao_senha_bp
from routes.favoritos_routes import favoritos_bp
from routes.avaliacoes_routes import avaliacoes_bp
from routes.documentos_profissionais_routes import documentos_profissionais_bp
from routes.notificacoes_routes import notificacoes_bp
from services.agendador import iniciar_agendador

from routes.community_routes import community_bp

app = Flask(__name__)
# Desenvolvimento local; em produção defina as origens exatas, separadas por vírgula.
cors_origins = os.getenv('CORS_ORIGINS')
CORS(app, resources={r"/api/*": {"origins":
    [origin.strip() for origin in cors_origins.split(',') if origin.strip()]
    if cors_origins else [r"http://localhost:\d+", r"http://127\.0\.0\.1:\d+"]
}}, allow_headers=['Authorization', 'Content-Type'])

# Registra o Blueprint de trilhas
# O url_prefix='/api/trilhas' garante que a rota '/' lá no trilhas_routes.py 
# vire automaticamente '/api/trilhas/' no navegador/Postman.
app.register_blueprint(community_bp, url_prefix='/api')
app.register_blueprint(trilhas_bp, url_prefix='/api/trilhas')
app.register_blueprint(usuarios_bp, url_prefix='/api/usuarios')
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(agendamentos_bp, url_prefix='/api/agendamentos')
app.register_blueprint(uploads_bp, url_prefix='/api/uploads')
app.register_blueprint(redefinicao_senha_bp, url_prefix='/api/auth/senha')
app.register_blueprint(favoritos_bp, url_prefix='/api/favoritos')
app.register_blueprint(avaliacoes_bp, url_prefix='/api/avaliacoes')
app.register_blueprint(
    documentos_profissionais_bp,
    url_prefix='/api/documentos-profissionais')
app.register_blueprint(notificacoes_bp, url_prefix='/api/notificacoes')


# Rota de teste simples na raiz da API só para garantir que o servidor subiu
@app.route('/', methods=['GET'])
def index():
    return {"mensagem": "API do Rota Fácil rodando com sucesso na arquitetura MVC!"}, 200

@app.route('/docs', methods=['GET'])
def swagger_docs():
    return render_template('swagger.html')

if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG', 'false').lower() in {'1', 'true', 'yes'}
    scheduler_enabled = os.getenv('ENABLE_SCHEDULER', 'false').lower() in {'1', 'true', 'yes'}
    # No modo debug, inicia o agendador apenas no processo do reloader.
    if scheduler_enabled and (not debug or os.getenv('WERKZEUG_RUN_MAIN') == 'true'):
        iniciar_agendador()
    app.run(debug=debug)
