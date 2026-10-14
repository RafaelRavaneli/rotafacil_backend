"""Origem das credenciais Firebase para execução local e hospedagem."""
import json
import os
from pathlib import Path


def firebase_credential_source():
    """Aceita JSON protegido no ambiente sem exigir arquivo no servidor."""
    inline = os.getenv('FIREBASE_CREDENTIALS_JSON')
    if inline:
        try:
            source = json.loads(inline)
        except (ValueError, TypeError):
            # Não inclui o conteúdo da variável nem a chave privada no erro.
            raise ValueError('FIREBASE_CREDENTIALS_JSON deve conter um objeto JSON válido.') from None
        if not isinstance(source, dict):
            raise ValueError('FIREBASE_CREDENTIALS_JSON deve conter um objeto JSON válido.')
        return source
    return os.getenv(
        'FIREBASE_CREDENTIALS_PATH',
        str(Path(__file__).resolve().parents[1] / 'firebase-key.json'),
    )
