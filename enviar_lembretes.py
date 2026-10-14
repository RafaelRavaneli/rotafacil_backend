"""Executa uma rodada de lembretes; indicado para um job cron separado."""
from services.agendador import enviar_lembretes_diarios


if __name__ == '__main__':
    enviar_lembretes_diarios(raise_errors=True)
