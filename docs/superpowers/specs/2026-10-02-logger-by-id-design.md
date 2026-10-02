# Design: logger por id e limpeza pela última atualização

## Objetivo

Gravar cada execução num arquivo marcado por um id numérico, com backup ilimitado por padrão, e limitar quantos ids permanecem. A limpeza pelo menor id fica junto da criação do logger. A limpeza pela data da última atualização fica numa função separada.

## Decisões

| Decisão | Escolha |
|---------|---------|
| Criação com id | Nova função `configure_logger_by_id`. `configure_logger` permanece com o comportamento atual |
| Limpeza por data | Nova função `cleanup_logs_by_last_update`. Não cria logger e não é chamada por `configure_logger_by_id` |
| Limpeza por dias | `cleanup_old_logs` / `max_age_days` permanecem como estão. `configure_logger_by_id` não recebe `max_age_days` |
| Id | Inteiro positivo. Zero, negativo, texto, decimal e booleano geram `ValueError` antes de criar pasta ou apagar arquivo |
| Nome do arquivo | `{stem}-id-{id}.log`. Ex.: `automation.log` vira `automation-id-123.log`. O `name` do logger Python não inclui o id |
| Backup com id, sem `backup_count` | Ilimitado. A numeração é a do handler atual: `.log.1` é o backup mais recente e a cadeia é renomeada |
| Backup com `backup_count` informado | O valor é repassado ao handler, nos dois modos |
| `max_ids` | Opcional. Omitido, nenhum id é apagado. Menor que 1 gera `ValueError`. Acima do limite, sai sempre o menor id; o id desta chamada nunca sai |
| `keep` | Quantos ids daquele nome-base permanecem na limpeza por data. Menor que 0 gera `ValueError`. `0` apaga todos os grupos daquele nome-base |
| Data usada | `mtime` do arquivo base. Se ele não existir, `mtime` do backup de menor índice. Id que só tem `.lock` é o mais antigo |
| Empate de data | Sai primeiro o menor id |
| Id em uso na limpeza por data | A função não recebe o id em uso. Esse id pode ser apagado se estiver entre os mais antigos |
| Escopo | Só `{stem}-id-{número}.log`, `{stem}-id-{número}.log.{n}` e `{stem}-id-{número}.lock` na pasta, sem recursão. Outro nome-base fica de fora |
| Número no nome | Sem zero à esquerda (`[1-9]\d*`). `automation-id-007.log` não entra no grupo do id 7 |
| Falha ao apagar | Warning com o caminho e o erro; segue. O caminho não entra na lista devolvida. Se o grupo escolhido continuar no disco, a mesma chamada tenta o próximo candidato e não repete o mesmo id |
| Pasta inexistente na limpeza por data | Lista vazia |
| Mesmo processo, mesmo `name`, outro arquivo | `configure_logger_by_id` troca só o handler de arquivo. Nível, formato e console ficam os da primeira chamada. O handler antigo é fechado antes da limpeza por id |
| Mesmo arquivo de novo | Não duplica handler. Se `max_ids` veio, a limpeza por id roda mesmo assim |
| `configure_logger` depois | A guarda atual permanece: se o logger já tem handlers, `configure_logger` não troca o arquivo |
| Vários processos | Cada processo que configura o próprio id grava no próprio arquivo. O mesmo id em processos diferentes compartilha o arquivo |

## Funções públicas

### `cleanup_logs_by_last_update`

```python
def cleanup_logs_by_last_update(
    log_dir: str | Path,
    file_name: str,
    keep: int,
    *,
    logger: logging.Logger | None = None,
) -> list[Path]:
```

1. `keep` é `int`, não booleano, e `>= 0`. Caso contrário, `ValueError`.
2. `file_name` vazio gera `ValueError`. Se terminar com `.log`, esse sufixo é removido para obter o stem (`automation.log` e `automation` casam os mesmos grupos).
3. Se `log_dir` não existir, retorna `[]`.
4. Agrupa os arquivos do stem por id.
5. Enquanto houver mais grupos do que `keep`, escolhe o mais antigo pela data definida acima e apaga o grupo inteiro.
6. Retorna os caminhos efetivamente apagados.
7. O warning usa `logger` quando informado; senão, `logging.getLogger(__name__)`.

### `configure_logger_by_id`

```python
def configure_logger_by_id(
    name: str | None = None,
    *,
    id: int,
    log_dir: str | Path = DEFAULT_LOG_DIR,
    file_name: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int | None = None,
    max_ids: int | None = None,
    level: int = DEFAULT_LEVEL,
    log_format: str = DEFAULT_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
) -> logging.Logger:
```

`id` é argumento obrigatório e só por nome: `configure_logger_by_id("meu_bot", id=123, max_ids=5)`.

Resolução do arquivo, igual à de `configure_logger`, e depois o sufixo do id:

- stem = `file_name`, senão `name`, senão `automation`
- se o stem terminar com `.log`, esse sufixo sai antes de inserir o id
- arquivo final = `{stem}-id-{id}.log`

`backup_count is None` usa a constante `UNLIMITED_BACKUP_COUNT = sys.maxsize` no `ConcurrentRotatingFileHandler`. O laço de rotação da biblioteca para no primeiro índice ausente, então o valor alto não percorre essa faixa; ele só impede o descarte. Cada rotação ainda renomeia a cadeia existente. `backup_count` informado, inclusive `0`, é repassado ao handler como em `configure_logger`.

`max_ids`, quando informado, é `int`, não booleano, e `>= 1`. A conta usa só os ids daquele stem. O id desta chamada entra na conta mesmo que ainda não tenha arquivo. Enquanto a quantidade passar de `max_ids`, apaga o menor id entre os outros. Os warnings dessa limpeza usam o logger que está sendo configurado.

Ordem:

1. Validar `id`, `max_ids` e o nome do arquivo. Erro aqui não cria pasta nem apaga arquivo.
2. Criar `log_dir` se precisar.
3. Se o logger já tem handler de arquivo e o caminho é outro, fechar e remover esse handler.
4. Se o logger ainda não tem handlers, criar os de console e aplicar `level` e formato, para o warning da limpeza ter para onde ir. Se já tem, o console permanece.
5. Se `max_ids` veio, apagar os menores ids excedentes.
6. Se o handler de arquivo desse caminho ainda não existe, adicioná-lo.
7. Quando o logger já tinha handlers, não alterar `level`, formato nem console.

Nome diferente continua sendo outro logger: os dois gravam ao mesmo tempo, cada um no seu arquivo.

## Código compartilhado

Em `logger.py`, funções internas usadas pelos dois fluxos:

- resolver o stem e o nome do arquivo
- listar os grupos de id de um stem
- apagar um grupo (base, backups e `.lock`)
- criar os handlers de console
- criar o `ConcurrentRotatingFileHandler`

`configure_logger` passa a usar a resolução de nome, o console e o handler de arquivo. O comportamento observável permanece o atual, inclusive `backup_count` padrão 3, `max_age_days` só na primeira configuração e o retorno imediato quando o logger já tem handlers.

A limpeza pelo menor id não é função pública. Ela vive em `configure_logger_by_id` e usa as internas de listar e apagar grupo. A limpeza por data usa as mesmas internas.

## Arquivos afetados

| Arquivo | Mudança |
|---------|---------|
| `src/utils_rpa/logger.py` | `configure_logger_by_id`, `cleanup_logs_by_last_update`, constante do backup ilimitado e internas compartilhadas |
| `src/utils_rpa/__init__.py` | Exportar as duas funções novas |
| `tests/test_logger.py` | Testes das duas funções e da compatibilidade de `configure_logger` |
| `README.md` | Documentar as duas funções |

## Fora de escopo

- `max_age_days` em `configure_logger_by_id`
- Função pública só para apagar pelo menor id
- Limpeza recursiva
- Gzip na rotação
- Troca de arquivo feita por `configure_logger` quando o logger já está configurado

## Critérios de sucesso

- `configure_logger` sem id permanece com o comportamento atual, inclusive limite padrão de 3 backups
- `configure_logger_by_id("meu_bot", id=123)` cria `meu_bot-id-123.log`
- `id` inválido, `max_ids` menor que 1, `keep` menor que 0 e `file_name` vazio geram `ValueError` e não alteram a pasta
- Sem `backup_count`, o handler não descarta backup e `.1` continua sendo o mais novo
- Com `backup_count`, o handler usa esse limite
- Com `max_ids`, sai o menor id; o id desta chamada permanece; repetir a mesma chamada não duplica handler; outro id no mesmo processo passa a gravar só no arquivo novo
- `cleanup_logs_by_last_update` mantém `keep` grupos, os mais recentes pela data definida acima
- Sem arquivo base, usa o backup de menor índice; só `.lock` conta como o mais antigo; empate de data apaga o menor id; `keep=0` apaga todos os grupos daquele stem
- Arquivo de outro nome-base na mesma pasta permanece
- Falha ao apagar um arquivo gera warning e não interrompe a configuração do logger
- As duas funções são chamáveis por `utils_rpa` sem passar pela outra
