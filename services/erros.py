"""Respostas de erro inesperado sem expor detalhes internos ao cliente."""
import logging

logger = logging.getLogger('rotafacil')


def erro_interno(mensagem, status=500):
    """Registra a exceção atual no log e devolve uma mensagem genérica.

    Deve ser chamada dentro de um bloco ``except``: o rastreamento completo
    vai para o log do servidor, e o cliente recebe só a mensagem informada.
    """
    logger.exception(mensagem)
    return {'erro': f'{mensagem}. Tente novamente em instantes.'}, status
