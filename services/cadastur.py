import re
from datetime import date


class Cadastur:
    """Validação de entrada; não confirma regularidade no cadastro oficial."""

    @staticmethod
    def normalizar(dados, obrigatorio=False):
        numero = dados.get('cadastur_numero', '')
        validade = dados.get('cadastur_validade', '')
        if not isinstance(numero, str) or not isinstance(validade, str):
            raise ValueError('Número e validade do Cadastur devem ser textos.')
        numero, validade = numero.strip(), validade.strip()
        if not numero:
            if obrigatorio or validade:
                raise ValueError('Número do Cadastur é obrigatório para guias e agências.')
            return {'cadastur_numero': '', 'cadastur_validade': ''}
        if len(numero) > 40 or not re.fullmatch(r'[0-9][0-9. /-]*', numero):
            raise ValueError('Informe o número do Cadastur conforme o certificado, usando números e separadores.')
        numero = re.sub(r'[^0-9]', '', numero)
        if len(numero) > 30:
            raise ValueError('Número do Cadastur deve ter até 30 dígitos.')
        if validade:
            try:
                if date.fromisoformat(validade).isoformat() != validade:
                    raise ValueError()
            except ValueError as exc:
                raise ValueError('Validade do Cadastur deve estar no formato AAAA-MM-DD.') from exc
        return {'cadastur_numero': numero, 'cadastur_validade': validade}
