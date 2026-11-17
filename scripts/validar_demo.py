"""Valida os dados de demonstração pela API (cliente de testes do Flask, sem servidor)."""
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app import app  # noqa: E402

texto = (BACKEND / '.demo_local' / 'CONTAS_DEMO.md').read_text(encoding='utf-8')
senha = re.search(r'senha de todas as contas:\*\* `([^`]+)`', texto, re.I).group(1)
cliente = app.test_client()


def entrar(email):
    r = cliente.post('/api/auth/login', json={'email': email, 'senha': senha})
    assert r.status_code == 200, (email, r.status_code, r.get_json())
    dados = r.get_json()
    return dados['id'], {'Authorization': f"Bearer {dados['token']}"}, dados['tipo']


_, H, _ = entrar('mariana@demo.rotafacil.eco.br')
trilhas = cliente.get('/api/trilhas/', headers=H).get_json()
lista = trilhas if isinstance(trilhas, list) else trilhas.get('trilhas') or trilhas.get('itens') or []
print('roteiros publicos:', len(lista))
for t in sorted(lista, key=lambda x: x.get('nome', '')):
    print(f"  - {t.get('nome')} | {t.get('cidade')} | nota={t.get('media_avaliacao', t.get('nota_media'))} "
          f"| aval={t.get('total_avaliacoes', t.get('quantidade_avaliacoes'))} | img={'ok' if t.get('imagem_url') else 'sem'}")

for nome, lat, lon in [('Maringá', -23.4205, -51.9333), ('Curitiba', -25.4284, -49.2733),
                       ('Ponta Grossa', -25.0945, -50.1633), ('Foz do Iguaçu', -25.5469, -54.5882)]:
    r = cliente.get(f'/api/trilhas/busca?latitude={lat}&longitude={lon}&raio_km=100', headers=H)
    corpo = r.get_json()
    itens = corpo if isinstance(corpo, list) else (corpo.get('trilhas') or corpo.get('itens') or corpo.get('resultados') or [])
    print(f'perto de {nome} (100 km): status={r.status_code} roteiros={len(itens)}')

for email in ['mariana', 'tiago', 'araucaria', 'admin', 'lucas', 'canyon']:
    uid, h, tipo = entrar(f'{email}@demo.rotafacil.eco.br')
    if tipo == 'usuario':
        reservas = cliente.get(f'/api/agendamentos/usuario/{uid}', headers=h).get_json()
        favs = cliente.get('/api/favoritos/', headers=h).get_json()
        notas = cliente.get('/api/notificacoes/', headers=h).get_json()
        print(f'{email} ({tipo}): reservas={[r.get("status") for r in reservas]} '
              f'favoritos={len(favs if isinstance(favs, list) else favs.get("favoritos", []))} '
              f'notificacoes={len(notas if isinstance(notas, list) else notas.get("notificacoes", []))}')
    elif tipo == 'guia':
        r = cliente.get(f'/api/agendamentos/guia/{uid}', headers=h).get_json()
        conv = cliente.get('/api/convites-guias', headers=h).get_json()
        print(f'{email} ({tipo}): reservas={[x.get("status") for x in r]} convites={[c.get("status") for c in conv]}')
    elif tipo == 'agencia':
        r = cliente.get(f'/api/agendamentos/agencia/{uid}', headers=h)
        corpo = r.get_json()
        print(f'{email} ({tipo}): status={r.status_code} reservas={[x.get("status") for x in corpo] if isinstance(corpo, list) else corpo}')
    else:
        r = cliente.get('/api/admin/contas', headers=h)
        corpo = r.get_json()
        print(f'{email} ({tipo}): painel admin status={r.status_code} contas={len(corpo) if isinstance(corpo, list) else len(corpo.get("contas", []))}')
