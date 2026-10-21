# Acessibilidade, restrições e adaptações

Implementação local do tópico obrigatório https://trello.com/c/Bey7GxiX.

## Contrato

O objeto `acessibilidade` pertence ao roteiro e usa as mesmas chaves em armazenamento, API e frontend:

- `mobilidade_reduzida`, `apoio_visual`, `apoio_auditivo`, `acompanhante_necessario`, `trechos_acessiveis`, `banheiro_acessivel`, `transporte_acessivel`: booleanos ou nulo. Campo ausente ou nulo significa não informado; falso significa não.
- `idade_minima`: inteiro entre 0 e 120, ou nulo. Zero é uma informação válida; vazio significa não informado.
- `restricoes_fisicas`, `condicionamento`, `adaptacoes`, `observacoes`: texto com até 1500 caracteres. Vazio significa não informado.

Cadastro e edição do roteiro oferecem todos os campos. O envio do objeto na edição substitui as informações anteriores de acessibilidade. Omissão do objeto mantém as informações atuais. Dados antigos não são convertidos em promessas de acessibilidade: o antigo booleano `acessivel` continua compatível, mas não confirma nenhum recurso detalhado.

Turista consulta todos os campos nos detalhes do roteiro. Filtros combinam recursos com E: todos precisam estar explicitamente confirmados. Nenhum filtro inclui roteiros com informação ausente como se fossem acessíveis. A API `/api/trilhas/busca` aceita `recursos_acessibilidade` com as chaves separadas por vírgulas (exceto acompanhante, que não é um recurso ofertado). Filtro é aplicado após os filtros existentes, sem novos índices compostos.

Não é necessária migração de dados. Nenhuma publicação foi feita. Testes manuais integrados permanecem para o encerramento da primeira versão. Informações são declarações do organizador, não uma certificação automática.
