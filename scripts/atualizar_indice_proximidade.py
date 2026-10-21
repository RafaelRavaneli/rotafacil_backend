"""Verifique o projeto Firebase selecionado antes de executar com --aplicar."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.database import bd
from services.indice_proximidade import atualizar_indice

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Inspeciona geohash legado; por padrão não altera registros.')
    parser.add_argument('--aplicar', action='store_true', help='Atualiza somente índices ausentes ou incorretos.')
    args = parser.parse_args()
    print(json.dumps(atualizar_indice(bd, aplicar=args.aplicar), ensure_ascii=False))
