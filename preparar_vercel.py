"""Publica o contrato OpenAPI na pasta de arquivos estáticos do Vercel."""
from pathlib import Path
import shutil


def preparar_assets():
    root = Path(__file__).resolve().parent
    destination = root / 'public' / 'static' / 'openapi.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / 'static' / 'openapi.json', destination)
    return destination


if __name__ == '__main__':
    preparar_assets()
