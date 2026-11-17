"""Zera o Firestore e popula dados de demonstração do RotaFácil.

ATENÇÃO: com --aplicar, APAGA TODOS OS DADOS do projeto Firebase configurado
(contas reais inclusive). Use somente com autorização de quem responde pelo banco.

Uso (a partir da pasta do backend):
    venv/Scripts/python.exe scripts/popular_demo.py            # só simula e valida
    venv/Scripts/python.exe scripts/popular_demo.py --aplicar  # backup + apaga + popula
    venv/Scripts/python.exe scripts/validar_demo.py            # confere os dados pela API

Com --aplicar, o script:
  1. salva um backup JSON de todas as coleções em .demo_local/backup-*.json;
  2. apaga todos os documentos de todas as coleções;
  3. cria contas, convites, roteiros, reservas, avaliações, favoritos,
     checklist e notificações de demonstração;
  4. grava as credenciais das contas em .demo_local/CONTAS_DEMO.md.

A pasta .demo_local é ignorada pelo Git: backup e credenciais nunca vão para o repositório.
As saídas dos roteiros usam datas fixas (ROTEIROS e RESERVAS); atualize-as antes de rodar
quando elas já tiverem passado, ou o backend recusará os roteiros.
"""
import argparse
import base64
import datetime as dt
import hashlib
import json
import random
import secrets
import string
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from werkzeug.security import generate_password_hash  # noqa: E402
from firebase_admin import firestore  # noqa: E402

from models.database import bd  # noqa: E402
from services.avaliacoes import Avaliacoes  # noqa: E402
from services.cadastur import Cadastur  # noqa: E402
from services.checklists import Checklists  # noqa: E402
from services.documentos_legais import DocumentosLegais  # noqa: E402
from services.trilhas import Trilhas  # noqa: E402
from services.usuarios import Usuarios  # noqa: E402

PASTA = BACKEND / '.demo_local'
PROJETO_ESPERADO = 'rota-facil-3be4f'
DOMINIO = 'demo.rotafacil.eco.br'
RNG = random.Random(20261116)
AGORA = dt.datetime.now(dt.timezone.utc)


def unsplash(foto):
    return f'https://images.unsplash.com/photo-{foto}?auto=format&fit=crop&w=1200&q=80'


def ibb(codigo):
    return f'https://i.ibb.co/{codigo}/foto.jpg'


# ---------------------------------------------------------------- documentos
def _digito(base, pesos):
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    return '0' if resto < 2 else str(11 - resto)


def gerar_cpf():
    base = ''.join(str(RNG.randint(0, 9)) for _ in range(9))
    d1 = _digito(base, range(10, 1, -1))
    d2 = _digito(base + d1, range(11, 1, -1))
    return base + d1 + d2


def gerar_cnpj():
    base = ''.join(str(RNG.randint(0, 9)) for _ in range(8)) + '0001'
    d1 = _digito(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = _digito(base + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return base + d1 + d2


def aceite_legal():
    docs = DocumentosLegais.documentos()
    return DocumentosLegais.validar_aceite({
        'aceite_termos': True, 'ciencia_privacidade': True,
        'termos_versao': docs['termos']['version'],
        'privacidade_versao': docs['privacidade']['version'],
    })


# ---------------------------------------------------------------- contas
CONTAS = [
    # chave, tipo, nome, cidade, UF, extras
    ('admin', 'admin', 'Administração RotaFácil', 'Maringá', 'PR', {}),
    ('mariana', 'usuario', 'Mariana Costa', 'Maringá', 'PR', {
        'telefone': '(44) 90000-1001',
        'contato_emergencia_nome': 'Roberto Costa',
        'contato_emergencia_telefone': '(44) 90000-1099',
        'contato_emergencia_relacao': 'Pai',
        'contato_emergencia_consentimento': True,
    }),
    ('bruno', 'usuario', 'Bruno Almeida', 'Curitiba', 'PR', {'telefone': '(41) 90000-1002'}),
    ('camila', 'usuario', 'Camila Rocha', 'Londrina', 'PR', {'telefone': '(43) 90000-1003'}),
    ('juliana', 'usuario', 'Juliana Tanaka', 'Ponta Grossa', 'PR', {'telefone': '(42) 90000-1004'}),
    ('pedro', 'usuario', 'Pedro Oliveira', 'Foz do Iguaçu', 'PR', {'telefone': '(45) 90000-1005'}),
    ('tiago', 'guia', 'Tiago Mendes', 'Maringá', 'PR', {
        'telefone': '(44) 90000-2001', 'verificado': True,
        'descricao_profissional': 'Guia de turismo no Norte do Paraná, com roteiros leves em parques urbanos, '
                                  'mata atlântica e cicloturismo pela região do café.',
        'especialidades': ['Caminhada', 'Cicloturismo', 'Observação de aves'],
    }),
    ('ana', 'guia', 'Ana Paula Ribeiro', 'Foz do Iguaçu', 'PR', {
        'telefone': '(45) 90000-2002', 'verificado': True,
        'descricao_profissional': 'Guia em Foz do Iguaçu há mais de oito anos, especializada em rafting '
                                  'e trilhas na mata do Parque Nacional.',
        'especialidades': ['Rafting', 'Trilhas', 'Caiaque'],
    }),
    ('lucas', 'guia', 'Lucas Andrade', 'Curitiba', 'PR', {
        'telefone': '(41) 90000-2003', 'verificado': True,
        'descricao_profissional': 'Montanhista e guia na Serra do Mar paranaense, com foco em segurança '
                                  'e travessias de um ou dois dias.',
        'especialidades': ['Montanhismo', 'Trekking', 'Acampamento'],
    }),
    ('diego', 'guia', 'Diego Kowalski', 'Ponta Grossa', 'PR', {
        'telefone': '(42) 90000-2004', 'verificado': False,
        'descricao_profissional': 'Condutor nos Campos Gerais: cânions, furnas e cachoeiras.',
        'especialidades': ['Cânions', 'Cachoeiras', 'Trilhas'],
    }),
    ('araucaria', 'agencia', 'Araucária Trilhas & Expedições', 'Curitiba', 'PR', {
        'telefone': '(41) 90000-3001', 'verificado': True,
        'descricao_profissional': 'Agência de ecoturismo de Curitiba com saídas para a Serra do Mar '
                                  'e o litoral do Paraná.',
        'especialidades': ['Serra do Mar', 'Litoral', 'Montanhismo'],
    }),
    ('canyon', 'agencia', 'Canyon Gerais Aventuras', 'Ponta Grossa', 'PR', {
        'telefone': '(42) 90000-3002', 'verificado': True,
        'descricao_profissional': 'Aventura nos Campos Gerais e na região das cachoeiras de Prudentópolis.',
        'especialidades': ['Cânions', 'Rapel', 'Aquatrekking'],
    }),
]

# Convites: (agência, guia, status)
CONVITES = [('araucaria', 'lucas', 'aceito'), ('canyon', 'diego', 'aceito'),
            ('araucaria', 'tiago', 'pendente')]


def saida(dia, inicio, fim, dia_fim=None):
    return {'data_hora_inicio': f'{dia}T{inicio}', 'data_hora_fim': f'{dia_fim or dia}T{fim}'}


ITENS_TRILHA = (['Água (mínimo 1,5 L)', 'Calçado fechado com boa aderência', 'Documento com foto'],
                ['Protetor solar', 'Repelente', 'Lanche leve', 'Capa de chuva'])

# Roteiros: chave, criador, guia, dados
ROTEIROS = [
    ('inga', 'tiago', 'tiago', dict(
        nome='Caminhada no Parque do Ingá', cidade='Maringá', estado='PR',
        descricao='Caminhada leve pela mata do Parque do Ingá, no centro de Maringá, com paradas para '
                  'observar aves e conhecer espécies nativas. Ideal para quem está começando e para famílias.',
        dificuldade='Iniciante', modalidade='Trilha', atividades=['Trilha', 'Observação de aves', 'Passeio ecológico'],
        distancia_km=4.5, latitude=-23.4280, longitude=-51.9300, preco=45.0, capacidade=15,
        ponto_encontro='Portão principal do Parque do Ingá',
        imagem_url=ibb('60LvBy1p'), acessivel=True,
        acessibilidade={'trechos_acessiveis': True, 'mobilidade_reduzida': True, 'banheiro_acessivel': True,
                        'idade_minima': 6, 'observacoes': 'Trecho principal pavimentado; trilhas internas de terra.'},
        datas=[saida('2026-11-22', '08:00', '11:00'), saida('2026-12-06', '08:00', '11:00')])),
    ('cafe', 'tiago', 'tiago', dict(
        nome='Pedal pela Rota do Café', cidade='Mandaguari', estado='PR',
        descricao='Cicloturismo por estradas rurais do Norte do Paraná, passando por fazendas de café, '
                  'mirantes e uma parada para degustação. Ritmo tranquilo, com carro de apoio.',
        dificuldade='Intermediário', modalidade='Cicloturismo', atividades=['Cicloturismo', 'Passeio ecológico'],
        distancia_km=28.0, latitude=-23.5470, longitude=-51.6710, preco=120.0, capacidade=12,
        ponto_encontro='Praça central de Mandaguari',
        imagem_url=ibb('F4DB3Qkx'),
        acessibilidade={'idade_minima': 14, 'condicionamento': 'Saber pedalar em estrada de terra.'},
        datas=[saida('2026-11-29', '07:00', '13:00'), saida('2026-12-13', '07:00', '13:00')])),
    ('godoy', 'tiago', 'tiago', dict(
        nome='Trilha na Mata dos Godoy', cidade='Londrina', estado='PR',
        descricao='Trilha interpretativa no Parque Estadual Mata dos Godoy, um dos remanescentes de mata '
                  'atlântica do Norte do Paraná, com árvores centenárias e muitas aves.',
        dificuldade='Iniciante', modalidade='Trilha', atividades=['Trilha', 'Observação de aves'],
        distancia_km=6.0, latitude=-23.4470, longitude=-51.2430, preco=60.0, capacidade=15,
        ponto_encontro='Centro de visitantes do parque',
        imagem_url=unsplash('1501555088652-021faa106b9b'),
        acessibilidade={'idade_minima': 8},
        datas=[saida('2026-11-28', '08:00', '12:00'), saida('2026-12-12', '08:00', '12:00')])),
    ('rafting', 'ana', 'ana', dict(
        nome='Rafting no Rio Iguaçu', cidade='Foz do Iguaçu', estado='PR',
        descricao='Descida de bote em corredeiras do Rio Iguaçu com instrutores, equipamentos de segurança '
                  'e briefing completo antes de entrar na água.',
        dificuldade='Intermediário', modalidade='Rafting', atividades=['Rafting'],
        distancia_km=5.0, latitude=-25.6000, longitude=-54.4900, preco=180.0, capacidade=16,
        ponto_encontro='Base de apoio às margens do rio',
        imagem_url=unsplash('1530866495561-507c9faab2ed'),
        acessibilidade={'idade_minima': 12, 'condicionamento': 'Saber nadar é recomendado.'},
        datas=[saida('2026-11-21', '09:00', '13:00'), saida('2026-12-05', '09:00', '13:00'),
               saida('2026-12-19', '09:00', '13:00')])),
    ('pocopreto', 'ana', 'ana', dict(
        nome='Trilha do Poço Preto', cidade='Foz do Iguaçu', estado='PR',
        descricao='Trilha pela mata do Parque Nacional do Iguaçu, com trecho de bicicleta, observação de '
                  'fauna e remada de caiaque no rio no fim do percurso.',
        dificuldade='Iniciante', modalidade='Trilha', atividades=['Trilha', 'Caiaque', 'Observação de fauna'],
        distancia_km=9.0, latitude=-25.6150, longitude=-54.4000, preco=150.0, capacidade=20,
        ponto_encontro='Centro de visitantes do Parque Nacional',
        imagem_url=unsplash('1441974231531-c6227db76b6e'),
        acessibilidade={'idade_minima': 10},
        datas=[saida('2026-11-22', '08:00', '13:00'), saida('2026-12-06', '08:00', '13:00')])),
    ('pico', 'araucaria', 'lucas', dict(
        nome='Pico Paraná com pernoite', cidade='Campina Grande do Sul', estado='PR',
        descricao='Travessia de dois dias até o ponto mais alto do Sul do Brasil, com acampamento na '
                  'montanha e nascer do sol acima das nuvens. Indicado para quem já tem experiência em trilhas.',
        dificuldade='Avançado', modalidade='Trekking', atividades=['Trekking', 'Acampamento'],
        distancia_km=18.0, latitude=-25.2140, longitude=-48.8320, preco=420.0, capacidade=10,
        ponto_encontro='Fazenda Pico Paraná, na BR-116',
        imagem_url=ibb('ccrdp42T'),
        acessibilidade={'idade_minima': 16, 'condicionamento': 'Bom preparo físico; subidas íngremes.'},
        itens_obrigatorios=['Mochila cargueira', 'Saco de dormir', 'Lanterna de cabeça', 'Água (mínimo 3 L)',
                            'Agasalho impermeável'],
        itens_recomendados=['Bastão de caminhada', 'Protetor solar', 'Refeições leves'],
        datas=[saida('2026-11-28', '05:00', '15:00', '2026-11-29'),
               saida('2026-12-12', '05:00', '15:00', '2026-12-13')])),
    ('anhangava', 'araucaria', 'lucas', dict(
        nome='Nascer do sol no Morro do Anhangava', cidade='Quatro Barras', estado='PR',
        descricao='Subida curta e intensa para ver o nascer do sol sobre a Serra do Mar, com vista para '
                  'Curitiba e região. Café da manhã no cume.',
        dificuldade='Intermediário', modalidade='Trilha', atividades=['Trilha', 'Escalada'],
        distancia_km=5.0, latitude=-25.3870, longitude=-49.0030, preco=110.0, capacidade=12,
        ponto_encontro='Estacionamento do Parque Estadual da Serra da Baitaca',
        imagem_url=ibb('TMzTj03t'),
        acessibilidade={'idade_minima': 12},
        datas=[saida('2026-11-21', '04:30', '09:30'), saida('2026-12-05', '04:30', '09:30')])),
    ('itupava', 'araucaria', 'lucas', dict(
        nome='Caminho do Itupava', cidade='Quatro Barras', estado='PR',
        descricao='Caminhada pelo histórico Caminho do Itupava, calçado em pedra, descendo a Serra do Mar '
                  'pela mata atlântica, com rios, ruínas e retorno de van.',
        dificuldade='Intermediário', modalidade='Trekking', atividades=['Trekking', 'Trilha'],
        distancia_km=20.0, latitude=-25.3690, longitude=-48.9640, preco=160.0, capacidade=14,
        ponto_encontro='Borda do Campo, em Quatro Barras',
        imagem_url=unsplash('1473448912268-2022ce9509d8'),
        acessibilidade={'idade_minima': 12, 'condicionamento': 'Descida longa e piso escorregadio.'},
        datas=[saida('2026-11-22', '07:00', '16:00'), saida('2026-12-06', '07:00', '16:00')])),
    ('canal', 'araucaria', 'araucaria', dict(
        nome='Acampamento no Morro do Canal', cidade='Piraquara', estado='PR',
        descricao='Subida no fim da tarde, noite acampado no topo e amanhecer com vista para a Serra do Mar. '
                  'Barracas e fogareiro fornecidos pela agência.',
        dificuldade='Intermediário', modalidade='Acampamento', atividades=['Acampamento', 'Trilha'],
        distancia_km=7.0, latitude=-25.5110, longitude=-48.9690, preco=260.0, capacidade=10,
        ponto_encontro='Mananciais da Serra, em Piraquara',
        imagem_url=unsplash('1510312305653-8ed496efae75'),
        acessibilidade={'idade_minima': 14},
        itens_obrigatorios=['Saco de dormir', 'Lanterna de cabeça', 'Agasalho', 'Água (mínimo 2 L)'],
        itens_recomendados=['Isolante térmico', 'Lanche', 'Protetor solar'],
        datas=[saida('2026-11-21', '14:00', '10:00', '2026-11-22'),
               saida('2026-12-19', '14:00', '10:00', '2026-12-20')])),
    ('ilhadomel', 'araucaria', 'araucaria', dict(
        nome='Trilhas da Ilha do Mel', cidade='Paranaguá', estado='PR',
        descricao='Dia inteiro na Ilha do Mel: trilha até o Farol das Conchas, praias e a Gruta das '
                  'Encantadas. Travessia de barco inclusa.',
        dificuldade='Iniciante', modalidade='Trilha', atividades=['Trilha', 'Passeio ecológico'],
        distancia_km=10.0, latitude=-25.5680, longitude=-48.3150, preco=230.0, capacidade=20,
        ponto_encontro='Trapiche de Pontal do Sul',
        imagem_url=ibb('8n3g2pdQ'), acessivel=False,
        acessibilidade={'idade_minima': 6},
        datas=[saida('2026-11-29', '08:00', '17:00'), saida('2026-12-13', '08:00', '17:00')])),
    ('vilavelha', 'canyon', 'diego', dict(
        nome='Arenitos de Vila Velha', cidade='Ponta Grossa', estado='PR',
        descricao='Passeio guiado pelos arenitos do Parque Estadual de Vila Velha, furnas e Lagoa Dourada, '
                  'com explicações sobre a formação dos Campos Gerais.',
        dificuldade='Iniciante', modalidade='Trilha', atividades=['Trilha', 'Passeio ecológico'],
        distancia_km=6.0, latitude=-25.2450, longitude=-50.0100, preco=90.0, capacidade=20,
        ponto_encontro='Centro de visitantes do Parque Estadual de Vila Velha',
        imagem_url=unsplash('1470071459604-3b5ec3a7fe05'), acessivel=True,
        acessibilidade={'trechos_acessiveis': True, 'mobilidade_reduzida': True, 'idade_minima': 0,
                        'observacoes': 'Passarelas no circuito principal.'},
        datas=[saida('2026-11-21', '09:00', '13:00'), saida('2026-11-28', '09:00', '13:00'),
               saida('2026-12-12', '09:00', '13:00')])),
    ('buraco', 'canyon', 'diego', dict(
        nome='Buraco do Padre e cachoeira', cidade='Ponta Grossa', estado='PR',
        descricao='Trilha curta até a furna do Buraco do Padre, onde uma cachoeira cai dentro de uma '
                  'caverna iluminada pela luz natural.',
        dificuldade='Iniciante', modalidade='Trilha', atividades=['Trilha', 'Cachoeirismo'],
        distancia_km=3.0, latitude=-25.1690, longitude=-49.9440, preco=80.0, capacidade=20,
        ponto_encontro='Entrada do Buraco do Padre',
        imagem_url=ibb('Hff24VWd'),
        acessibilidade={'idade_minima': 5},
        datas=[saida('2026-11-22', '09:00', '12:00'), saida('2026-12-06', '09:00', '12:00')])),
    ('guartela', 'canyon', 'diego', dict(
        nome='Cânion Guartelá', cidade='Tibagi', estado='PR',
        descricao='Trilha pelo Cânion Guartelá, um dos maiores cânions do Brasil, com mirantes, cachoeira '
                  'e banho nas panelas de pedra do Rio Iapó.',
        dificuldade='Intermediário', modalidade='Trilha', atividades=['Trilha', 'Cachoeirismo'],
        distancia_km=12.0, latitude=-24.5650, longitude=-50.2580, preco=170.0, capacidade=15,
        ponto_encontro='Portaria do Parque Estadual do Guartelá',
        imagem_url=ibb('ymGDSw5y'),
        acessibilidade={'idade_minima': 10},
        datas=[saida('2026-11-29', '07:00', '17:00'), saida('2026-12-13', '07:00', '17:00')])),
    ('saltosf', 'canyon', 'canyon', dict(
        nome='Rapel no Salto São Francisco', cidade='Prudentópolis', estado='PR',
        descricao='Rapel ao lado de uma das maiores quedas d\'água do Sul do Brasil, com instrutores '
                  'certificados e todo o equipamento incluso.',
        dificuldade='Avançado', modalidade='Rapel', atividades=['Rapel', 'Cachoeirismo'],
        distancia_km=4.0, latitude=-25.0700, longitude=-51.2700, preco=350.0, capacidade=8,
        ponto_encontro='Mirante do Salto São Francisco',
        imagem_url=unsplash('1432405972618-c60b0225b8f9'),
        acessibilidade={'idade_minima': 16, 'condicionamento': 'Não ter medo de altura; peso até 110 kg.'},
        datas=[saida('2026-12-05', '07:00', '16:00'), saida('2026-12-19', '07:00', '16:00')])),
    ('aquatrek', 'canyon', 'canyon', dict(
        nome='Aquatrekking em Prudentópolis', cidade='Prudentópolis', estado='PR',
        descricao='Caminhada dentro do rio, entre pedras e poços de água cristalina, na "terra das '
                  'cachoeiras". Termina com banho de cachoeira.',
        dificuldade='Intermediário', modalidade='Aquatrekking', atividades=['Aquatrekking', 'Cachoeirismo'],
        distancia_km=6.0, latitude=-25.1800, longitude=-51.0500, preco=190.0, capacidade=12,
        ponto_encontro='Praça central de Prudentópolis',
        imagem_url=ibb('N2H2rrKh'),
        acessibilidade={'idade_minima': 12, 'condicionamento': 'Saber nadar.'},
        itens_obrigatorios=['Tênis que possa molhar', 'Roupa de banho', 'Muda de roupa seca'],
        itens_recomendados=['Bolsa estanque', 'Protetor solar', 'Lanche'],
        datas=[saida('2026-11-28', '08:00', '16:00'), saida('2026-12-12', '08:00', '16:00')])),
]

CRIADORES = {chave: criador for chave, criador, _, _ in ROTEIROS}

TELEFONES_EMERGENCIA = {'tiago': '(44) 90000-2001', 'ana': '(45) 90000-2002',
                        'araucaria': '(41) 90000-3001', 'canyon': '(42) 90000-3002'}

# Reservas: turista, roteiro, status, saída (índice em datas ou data passada), avaliação
PASSADO = 'passado'
RESERVAS = [
    # Mariana (persona da apresentação)
    ('mariana', 'cafe', 'confirmado', 0, None),
    ('mariana', 'ilhadomel', 'pendente', 1, None),
    ('mariana', 'inga', 'concluido', (PASSADO, '2026-10-18', '08:00', '11:00'),
     (5, 5, None, 'Passeio tranquilo e muito bem explicado. Ótimo para começar!')),
    ('mariana', 'godoy', 'concluido', (PASSADO, '2026-11-01', '08:00', '12:00'), None),
    ('mariana', 'vilavelha', 'concluido', (PASSADO, '2026-10-17', '09:00', '13:00'),
     (4, 5, 4, 'Paisagem incrível e guia muito atencioso. Levaria mais água.')),
    # Demais turistas
    ('bruno', 'pico', 'confirmado', 0, None),
    ('bruno', 'cafe', 'pendente', 1, None),
    ('bruno', 'rafting', 'concluido', (PASSADO, '2026-10-17', '09:00', '13:00'),
     (5, 5, None, 'Adrenalina na medida certa e equipe muito segura.')),
    ('bruno', 'anhangava', 'concluido', (PASSADO, '2026-10-18', '04:30', '09:30'),
     (5, 5, 5, 'O nascer do sol lá de cima vale cada passo.')),
    ('bruno', 'itupava', 'concluido', (PASSADO, '2026-10-25', '07:00', '16:00'),
     (4, 5, 4, 'Trilha linda, mas a descida cansa. Bom ir preparado.')),
    ('camila', 'inga', 'pendente', 1, None),
    ('camila', 'guartela', 'confirmado', 0, None),
    ('camila', 'inga', 'concluido', (PASSADO, '2026-10-18', '08:00', '11:00'),
     (4, 5, None, 'Ótimo passeio para fazer com as crianças.')),
    ('camila', 'godoy', 'concluido', (PASSADO, '2026-11-01', '08:00', '12:00'),
     (5, 5, None, 'Vimos tucanos e muitas outras aves. Recomendo!')),
    ('camila', 'ilhadomel', 'concluido', (PASSADO, '2026-10-24', '08:00', '17:00'),
     (5, 5, 5, 'Dia perfeito: trilha, praia e a gruta. Organização impecável.')),
    ('camila', 'aquatrek', 'concluido', (PASSADO, '2026-11-07', '08:00', '16:00'),
     (5, None, 5, 'Diferente de tudo que já fiz. Água geladinha e cristalina.')),
    ('juliana', 'saltosf', 'pendente', 0, None),
    ('juliana', 'cafe', 'concluido', (PASSADO, '2026-10-25', '07:00', '13:00'),
     (5, 5, None, 'Pedal gostoso e o café no final foi o ponto alto.')),
    ('juliana', 'itupava', 'concluido', (PASSADO, '2026-10-25', '07:00', '16:00'),
     (5, 5, 5, 'História e natureza no mesmo caminho. Inesquecível.')),
    ('juliana', 'ilhadomel', 'concluido', (PASSADO, '2026-10-24', '08:00', '17:00'),
     (4, 4, 4, 'Muito bom, só o barco atrasou um pouco na volta.')),
    ('juliana', 'vilavelha', 'concluido', (PASSADO, '2026-10-17', '09:00', '13:00'),
     (5, 5, 5, 'Guia explicou tudo sobre os arenitos. Adorei.')),
    ('pedro', 'rafting', 'confirmado', 1, None),
    ('pedro', 'pocopreto', 'cancelado', 0, None),
    ('pedro', 'rafting', 'concluido', (PASSADO, '2026-10-17', '09:00', '13:00'),
     (5, 5, None, 'Já é a segunda vez e continua sensacional.')),
    ('pedro', 'pocopreto', 'concluido', (PASSADO, '2026-10-24', '08:00', '13:00'),
     (4, 5, None, 'Trilha bonita e o caiaque no final fecha com chave de ouro.')),
    ('pedro', 'guartela', 'concluido', (PASSADO, '2026-10-25', '07:00', '17:00'),
     (5, 4, 5, 'Que cânion! Os mirantes são de tirar o fôlego.')),
]

FAVORITOS = [('mariana', 'pico'), ('mariana', 'guartela'), ('mariana', 'ilhadomel'),
             ('bruno', 'canal'), ('camila', 'aquatrek'), ('pedro', 'saltosf')]


# ---------------------------------------------------------------- utilidades
def serializar(valor):
    if isinstance(valor, dt.datetime):
        return {'__datetime__': valor.isoformat()}
    if isinstance(valor, bytes):
        return {'__bytes__': base64.b64encode(valor).decode()}
    if isinstance(valor, dict):
        return {k: serializar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [serializar(v) for v in valor]
    if hasattr(valor, 'latitude') and hasattr(valor, 'longitude'):
        return {'__geopoint__': [valor.latitude, valor.longitude]}
    if hasattr(valor, 'path') and hasattr(valor, 'id'):
        return {'__ref__': valor.path}
    return valor


def exportar_documento(doc):
    item = {'id': doc.id, 'dados': serializar(doc.to_dict() or {}), 'subcolecoes': {}}
    for sub in doc.reference.collections():
        item['subcolecoes'][sub.id] = [exportar_documento(d) for d in sub.stream()]
    return item


def fazer_backup():
    backup = {'projeto': bd.project, 'gerado_em': AGORA.isoformat(), 'colecoes': {}}
    for col in bd.collections():
        backup['colecoes'][col.id] = [exportar_documento(d) for d in col.stream()]
    caminho = PASTA / f"backup-{AGORA.strftime('%Y%m%d-%H%M%S')}.json"
    caminho.write_text(json.dumps(backup, ensure_ascii=False, indent=1), encoding='utf-8')
    total = sum(len(v) for v in backup['colecoes'].values())
    # Confere que o arquivo pode ser lido de volta antes de apagar qualquer coisa.
    relido = json.loads(caminho.read_text(encoding='utf-8'))
    assert sum(len(v) for v in relido['colecoes'].values()) == total
    return caminho, {k: len(v) for k, v in backup['colecoes'].items()}


def apagar_tudo():
    def apagar_colecao(col):
        apagados = 0
        while True:
            docs = list(col.limit(300).stream())
            if not docs:
                return apagados
            lote = bd.batch()
            for d in docs:
                for sub in d.reference.collections():
                    apagar_colecao(sub)
                lote.delete(d.reference)
            lote.commit()
            apagados += len(docs)
    return {col.id: apagar_colecao(col) for col in bd.collections()}


def gerar_senha():
    letras = string.ascii_letters + string.digits
    return 'Trilha-' + ''.join(secrets.choice(letras) for _ in range(8))


# ---------------------------------------------------------------- montagem
def montar_contas(senha):
    hash_senha = generate_password_hash(senha)
    aceite = aceite_legal()
    contas = {}
    for chave, tipo, nome, cidade, uf, extras in CONTAS:
        uid = str(uuid.uuid4())
        doc = {
            'id': uid, 'nome': nome, 'email': f'{chave}@{DOMINIO}',
            'telefone': extras.get('telefone'), 'cidade': cidade, 'estado': uf,
            'senha': hash_senha, 'tipo': tipo, 'documento': None, 'tipo_documento': None,
            'contato_emergencia_nome': extras.get('contato_emergencia_nome', ''),
            'contato_emergencia_telefone': extras.get('contato_emergencia_telefone', ''),
            'contato_emergencia_relacao': extras.get('contato_emergencia_relacao', ''),
            'contato_emergencia_consentimento': extras.get('contato_emergencia_consentimento', False),
            'aceite_legal': aceite, 'historico_aceites_legais': [aceite],
            'verificado': extras.get('verificado', False),
            'email_confirmado': True, 'email_confirmado_em': AGORA,
            'exigir_confirmacao_email': False, 'ativo': True, 'versao_auth': 0,
            'foto_url': None, 'createdAt': AGORA,
        }
        if doc['contato_emergencia_consentimento']:
            doc['contato_emergencia_consentimento_em'] = AGORA
        if tipo in {'guia', 'agencia'}:
            documento = gerar_cpf() if tipo == 'guia' else gerar_cnpj()
            valido, tipo_doc = Usuarios._validar_documento(documento)
            assert valido and tipo_doc == ('cpf' if tipo == 'guia' else 'cnpj'), documento
            numero = f'{RNG.randint(10, 99)}.{RNG.randint(100000, 999999)}.10.0001-{RNG.randint(0, 9)}'
            doc.update({'documento': documento, 'tipo_documento': tipo_doc,
                        **Cadastur.normalizar({'cadastur_numero': numero,
                                               'cadastur_validade': '2028-06-30'}, obrigatorio=True),
                        'descricao_profissional': extras.get('descricao_profissional', ''),
                        'especialidades': extras.get('especialidades', [])})
        contas[chave] = doc
    return contas


def payload_roteiro(chave, criador, dados):
    obrig, recom = ITENS_TRILHA
    return {
        **dados,
        'acessivel': dados.get('acessivel', False),
        'itens_obrigatorios': dados.get('itens_obrigatorios', obrig),
        'itens_recomendados': dados.get('itens_recomendados', recom),
        'emergencia_organizador_telefone': TELEFONES_EMERGENCIA[criador],
        'emergencia_instrucoes': 'Em caso de emergência, ligue para o organizador. Se não houver sinal, '
                                 'siga até o ponto de encontro e acione o SAMU (192) ou os Bombeiros (193).',
        'trajeto': [],
    }


def validar_plano(contas):
    """Valida roteiros com as mesmas regras do backend, sem gravar nada."""
    for chave, criador, guia, dados in ROTEIROS:
        payload = payload_roteiro(chave, criador, dict(dados))
        payload['id_guia'] = 'x'
        erro = Trilhas._validar_campos_publicos(dict(payload), criacao=True)
        assert erro is None, f'{chave}: {erro}'
        Trilhas._normalizar_datas(dict(payload))
    # Conflitos de agenda por responsável (o backend recusaria saídas sobrepostas).
    agenda = {}
    for chave, criador, guia, dados in ROTEIROS:
        for s in dados['datas']:
            ini = dt.datetime.fromisoformat(s['data_hora_inicio'])
            fim = dt.datetime.fromisoformat(s['data_hora_fim'])
            for outro, oi, of in agenda.get(guia, []):
                assert not (ini < of and fim > oi), f'conflito de agenda: {chave} x {outro}'
            agenda.setdefault(guia, []).append((chave, ini, fim))
    chaves = {r[0] for r in ROTEIROS}
    for turista, rot, status, saida_ref, aval in RESERVAS:
        assert turista in contas and rot in chaves, (turista, rot)
    return True


def aplicar(contas, senha):
    # 1. Contas
    lote = bd.batch()
    for doc in contas.values():
        lote.set(bd.collection('usuarios').document(doc['id']), doc)
    lote.commit()

    # 2. Convites (aceitos antes dos roteiros, para a agência poder atribuir o guia)
    convites = {}
    for agencia, guia, status in CONVITES:
        a, g = contas[agencia], contas[guia]
        cid = hashlib.sha256(f"{a['id']}:{g['id']}".encode()).hexdigest()
        dados = {'participantes': [a['id'], g['id']], 'id_agencia': a['id'], 'id_guia': g['id'],
                 'nome_agencia': a['nome'], 'nome_guia': g['nome'], 'status': status,
                 'criado_em': (AGORA - dt.timedelta(days=40)).isoformat()}
        if status != 'pendente':
            dados['respondido_em'] = (AGORA - dt.timedelta(days=39)).isoformat()
        bd.collection('convites_guias').document(cid).set(dados)
        convites[(agencia, guia)] = cid

    # 3. Roteiros pelo serviço do backend (valida, gera geohash e checa agenda)
    roteiros = {}
    for chave, criador, guia, dados in ROTEIROS:
        c = contas[criador]
        usuario_atual = {'id': c['id'], 'email': c['email'], 'tipo': c['tipo']}
        payload = payload_roteiro(chave, criador, dict(dados))
        payload['id_guia'] = contas[guia]['id']
        resposta, status = Trilhas.cadastrar_trilha(bd, payload, usuario_atual)
        assert status == 201, f'{chave}: {resposta}'
        roteiros[chave] = bd.collection('trilhas').document(resposta['id']).get().to_dict()

    # 4. Reservas
    reservas = []
    for turista, rot, status, saida_ref, aval in RESERVAS:
        t, r = contas[turista], roteiros[rot]
        if isinstance(saida_ref, tuple):
            _, dia, hi, hf = saida_ref
            inicio, fim, id_data = f'{dia}T{hi}', f'{dia}T{hf}', str(uuid.uuid4())
        else:
            s = r['datas'][saida_ref]
            inicio, fim, id_data = s['data_hora_inicio'], s['data_hora_fim'], s['id']
        rid = str(uuid.uuid4())
        criado = dt.datetime.fromisoformat(inicio).replace(tzinfo=dt.timezone.utc) - dt.timedelta(days=12)
        criado = min(criado, AGORA - dt.timedelta(days=1))
        doc = {'id': rid, 'id_usuario': t['id'], 'id_trilha': r['id'], 'id_guia': r['id_guia'],
               'id_data': id_data, 'data_agendada': inicio[:10], 'data_hora_inicio': inicio,
               'data_hora_fim': fim, 'valor_pago': float(r['preco']), 'status': 'confirmado'
               if status == 'concluido' else status, 'createdAt': criado}
        operador = contas[CRIADORES[rot]]
        if status in {'confirmado', 'recusado', 'concluido'}:
            doc.update({'respondido_em': criado + dt.timedelta(hours=5), 'respondido_por': operador['id']})
        if status == 'cancelado':
            doc.update({'cancelado_em': criado + dt.timedelta(days=2), 'cancelado_por': t['id']})
        if status == 'concluido':
            doc.update({'status': 'concluido', 'finalizado_em': dt.datetime.fromisoformat(fim).replace(
                tzinfo=dt.timezone.utc), 'finalizado_por': operador['id']})
        bd.collection('agendamentos').document(rid).set(doc)
        reservas.append((turista, rot, status, rid, aval, operador))

    # 5. Avaliações pelo serviço (recalcula as médias dos roteiros e responsáveis)
    for turista, rot, status, rid, aval, _ in reservas:
        if not aval:
            continue
        nota, nota_guia, nota_agencia, comentario = aval
        t, r = contas[turista], roteiros[rot]
        resposta, st = Avaliacoes.adicionar_avaliacao(
            bd, t['id'], r['id'], nota, comentario, t['nome'], id_agendamento=rid,
            nota_guia=nota_guia or nota, nota_agencia=nota_agencia or nota)
        assert st == 201, f'avaliação {turista}/{rot}: {resposta}'

    # 6. Favoritos
    for turista, rot in FAVORITOS:
        uid, tid = contas[turista]['id'], roteiros[rot]['id']
        bd.collection('favoritos').document(f'{uid}__{tid}').set(
            {'id_usuario': uid, 'id_trilha': tid, 'createdAt': AGORA - dt.timedelta(days=3)})

    # 7. Checklist da Mariana na reserva confirmada (2 itens já preparados)
    for turista, rot, status, rid, _, _ in reservas:
        if turista == 'mariana' and status == 'confirmado':
            r = roteiros[rot]
            itens = (r.get('itens_obrigatorios') or [])[:2]
            bd.collection('checklists_pessoais').document(rid).set({
                'id_agendamento': rid, 'id_trilha': r['id'], 'id_usuario': contas['mariana']['id'],
                'marcados': {Checklists.chave(i): True for i in itens}, 'atualizado_em': AGORA})

    # 8. Notificações coerentes com as reservas
    notas = []

    def notificar(usuario, titulo, corpo, dados, horas_atras, lida):
        nid = str(uuid.uuid4())
        tipo = dados.get('tipo')
        categoria = 'agendamentos' if tipo in {'reserva', 'novo_agendamento', 'cancelamento',
                                               'resposta_agendamento', 'roteiro_finalizado'} else 'sistema'
        notas.append((nid, {'id': nid, 'id_usuario': usuario['id'], 'titulo': titulo, 'corpo': corpo,
                            'dados': {k: str(v) for k, v in dados.items()}, 'categoria': categoria,
                            'lida': lida,
                            'criado_em': (AGORA - dt.timedelta(hours=horas_atras)).isoformat()}))

    for turista, rot, status, rid, aval, operador in reservas:
        t, r = contas[turista], roteiros[rot]
        nome = r['nome']
        if status == 'pendente':
            notificar(t, 'Solicitação de reserva enviada',
                      f"Sua reserva para '{nome}' aguarda confirmação do responsável.",
                      {'tipo': 'reserva', 'id_agendamento': rid}, 20, False)
            notificar(operador, 'Novo agendamento recebido!',
                      f"Você recebeu um novo agendamento para o roteiro '{nome}'.",
                      {'tipo': 'novo_agendamento', 'id_agendamento': rid}, 20, False)
        elif status == 'confirmado':
            notificar(t, 'Reserva confirmada', f"Sua solicitação para '{nome}' foi confirmado.",
                      {'tipo': 'resposta_agendamento', 'id_agendamento': rid}, 30, turista != 'mariana')
        elif status == 'cancelado':
            notificar(operador, 'Agendamento cancelado',
                      f"Um participante cancelou o agendamento no roteiro '{nome}'.",
                      {'tipo': 'cancelamento', 'id_agendamento': rid}, 72, True)
        elif status == 'concluido':
            recente = not aval
            notificar(t, 'Roteiro finalizado',
                      f"O roteiro '{nome}' foi finalizado. Sua avaliação já está disponível.",
                      {'tipo': 'roteiro_finalizado', 'id_agendamento': rid}, 48 if recente else 400,
                      not recente)
    cid = convites[('araucaria', 'tiago')]
    notificar(contas['tiago'], 'Novo convite de agência',
              f"{contas['araucaria']['nome']} convidou você para integrar sua equipe.",
              {'tipo': 'convite_guia', 'id_convite': cid}, 26, False)
    for i in range(0, len(notas), 300):
        lote = bd.batch()
        for nid, doc in notas[i:i + 300]:
            lote.set(bd.collection('notificacoes').document(nid), doc)
        lote.commit()

    return roteiros, reservas, len(notas)


def gravar_credenciais(contas, senha):
    linhas = ['# Contas de demonstração do RotaFácil', '',
              f'Geradas em {AGORA.strftime("%d/%m/%Y %H:%M")} UTC no projeto `{bd.project}`.',
              'Arquivo local: não envie ao Git nem compartilhe publicamente.', '',
              f'**Senha de todas as contas:** `{senha}`', '',
              '| Perfil | Nome | E-mail |', '|---|---|---|']
    rotulos = {'admin': 'Administrador', 'usuario': 'Turista', 'guia': 'Guia', 'agencia': 'Agência'}
    for doc in contas.values():
        linhas.append(f"| {rotulos[doc['tipo']]} | {doc['nome']} | {doc['email']} |")
    linhas += ['', 'Persona principal da apresentação: **Mariana Costa** (turista, Maringá).']
    caminho = PASTA / 'CONTAS_DEMO.md'
    caminho.write_text('\n'.join(linhas) + '\n', encoding='utf-8')
    return caminho


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--aplicar', action='store_true', help='Faz backup, apaga e popula o banco.')
    args = parser.parse_args()

    print('Projeto Firebase:', bd.project)
    assert bd.project == PROJETO_ESPERADO, 'Projeto inesperado; nada foi alterado.'
    senha = gerar_senha()
    contas = montar_contas(senha)
    validar_plano(contas)
    avaliacoes = sum(1 for r in RESERVAS if r[4])
    print(f'Plano válido: {len(contas)} contas, {len(CONVITES)} convites, {len(ROTEIROS)} roteiros, '
          f'{len(RESERVAS)} reservas, {avaliacoes} avaliações, {len(FAVORITOS)} favoritos.')
    if not args.aplicar:
        print('Simulação concluída. Nada foi gravado. Use --aplicar para executar.')
        return

    PASTA.mkdir(exist_ok=True)
    caminho, contagem = fazer_backup()
    print('Backup salvo:', caminho.name, contagem)
    print('Apagados:', apagar_tudo())
    roteiros, reservas, notas = aplicar(contas, senha)
    credenciais = gravar_credenciais(contas, senha)
    print(f'Populado: {len(contas)} contas, {len(roteiros)} roteiros, {len(reservas)} reservas, '
          f'{avaliacoes} avaliações, {notas} notificações.')
    print('Credenciais salvas em:', credenciais.name)


if __name__ == '__main__':
    main()
