class Acessibilidade:
    BOOLEANOS = (
        'mobilidade_reduzida', 'apoio_visual', 'apoio_auditivo',
        'acompanhante_necessario', 'trechos_acessiveis',
        'banheiro_acessivel', 'transporte_acessivel',
    )
    TEXTOS = ('restricoes_fisicas', 'condicionamento', 'adaptacoes', 'observacoes')

    @staticmethod
    def validar(valor):
        if not isinstance(valor, dict):
            raise ValueError('acessibilidade deve ser um objeto')
        permitidos = set(Acessibilidade.BOOLEANOS + Acessibilidade.TEXTOS + ('idade_minima',))
        if set(valor) - permitidos:
            raise ValueError('Campo de acessibilidade desconhecido')
        for campo, item in valor.items():
            if campo in Acessibilidade.BOOLEANOS:
                if item is not None and not isinstance(item, bool):
                    raise ValueError(f'{campo} deve ser verdadeiro, falso ou nulo')
            elif campo == 'idade_minima':
                if item is not None and (type(item) is not int or not 0 <= item <= 120):
                    raise ValueError('idade_minima deve ser um inteiro de 0 a 120 ou nulo')
            elif not isinstance(item, str) or len(item.strip()) > 1500:
                raise ValueError(f'{campo} deve ser texto com até 1500 caracteres')
        return {campo: item.strip() if isinstance(item, str) else item
                for campo, item in valor.items()}
