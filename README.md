# RotaFácil — Backend

API REST em Flask para o aplicativo RotaFácil, responsável por usuários, trilhas, agendamentos e autenticação. O frontend (Flutter) e a documentação de planejamento vivem em repositórios separados.

## Stack

- Python 3.13 + Flask
- Firebase Firestore (banco de dados)
- JWT para autenticação
- ImgBB para upload de imagens

## Estrutura

    rotafacil_backend/
    ├── app.py                  # Ponto de entrada, registra os blueprints
    ├── models/
    │   └── database.py         # Inicialização do Firebase/Firestore
    ├── routes/                 # Camada HTTP (um blueprint por módulo)
    │   ├── usuarios_routes.py
    │   ├── auth_routes.py
    │   ├── trilhas_routes.py
    │   ├── agendamentos_routes.py
    │   └── uploads_routes.py
    └── services/                # Regras de negócio (usadas pelas routes)
        ├── usuarios.py
        ├── autenticacao.py
        ├── trilhas.py
        ├── agendamentos.py
        └── uploads.py

## Configuração local

### 1. Clone e crie o ambiente virtual

```bash
git clone https://github.com/RafaelRavaneli/rotafacil_backend.git
cd rotafacil_backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

### 2. Configure as variáveis de ambiente

Copie `.env.example` para `.env` e preencha os valores reais:

```bash
copy .env.example .env        # Windows
# cp .env.example .env        # Mac/Linux
```

### 3. Configure o Firebase

Baixe o arquivo de credenciais do seu projeto Firebase (Console → Configurações do Projeto → Contas de Serviço → Gerar nova chave privada) e salve como `firebase-key.json` na raiz do projeto. **Esse arquivo nunca deve ser commitado** — já está no `.gitignore`.

### 4. Rode o servidor

```bash
python app.py
```

A API sobe em `http://127.0.0.1:5000`.

## Autenticação e Papéis (RBAC)

Rotas protegidas exigem um header `Authorization: Bearer <token>`, obtido via `POST /api/auth/login`.

Papéis de usuário disponíveis: `usuario`, `guia`, `agencia`, `admin`. O papel `admin` não pode ser autoatribuído no cadastro — precisa ser definido manualmente no Firestore.

## Principais endpoints

| Módulo | Base | Observação |
|---|---|---|
| Usuários | `/api/usuarios` | Cadastro público; demais rotas exigem dono ou admin |
| Autenticação | `/api/auth/login` | Retorna token JWT |
| Trilhas | `/api/trilhas` | Criação restrita a `guia`/`agencia` |
| Agendamentos | `/api/agendamentos` | Restrito a `usuario`/`agencia`/`guia` |
| Uploads | `/api/uploads/imagem` | Qualquer usuário autenticado |

## Repositórios relacionados

- Frontend (Flutter): `<link do repo do frontend>`
- Documentação e backlog: `<link do repo rotafacil-docs>`
