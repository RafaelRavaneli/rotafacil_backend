"""Links públicos com segredo no fragmento, fora dos parâmetros HTTP."""
import os
from urllib.parse import urlencode, urlsplit


def link_autenticacao(destino, email, token):
    base = os.getenv('APP_PUBLIC_URL', 'https://www.rotafacil.eco.br').strip().rstrip('/')
    parsed = urlsplit(base)
    if (parsed.scheme not in {'https', 'http'} or not parsed.netloc or
            parsed.query or parsed.fragment or parsed.username or parsed.password or
            (parsed.scheme == 'http' and parsed.hostname not in {'localhost', '127.0.0.1'})):
        raise ValueError('APP_PUBLIC_URL inválida.')
    return f"{base}/#/{destino}?{urlencode({'email': email, 'token': token})}"
