# Design: `retry_with_logging` com suporte async

## Objetivo

Estender `@retry_with_logging` para funções `async def`, mantendo a API única e compatibilidade total com usos sync existentes.

## Decisões

| Decisão | Escolha |
|---------|---------|
| API | Um único `@retry_with_logging` |
| Detecção | No decorate-time via `inspect.iscoroutinefunction` |
| Delay async | `asyncio.sleep` (não bloqueia o event loop) |
| Delay sync | `time.sleep` (comportamento atual) |
| anti_captcha | Fora de escopo (sem import nem decorator) |
| Testes async | `asyncio.run(...)` (sem adicionar `pytest-asyncio`) |

## Comportamento

Parâmetros inalterados: `logger_name`, `attempts`, `delay`, `use_log`.

No decorate-time:

1. Se a função for coroutine function → retorna wrapper `async` que:
   - em cada tentativa faz `await func(*args, **kwargs)`
   - em falha, loga (se `use_log`) e `await asyncio.sleep(delay)` entre tentativas
   - esgotadas as tentativas, loga erro e re-raise da última exceção
2. Caso contrário → retorna o wrapper sync atual (`time.sleep`)

Logging, mensagens e política de exceção (`except Exception`) são idênticos nos dois caminhos.

## Arquivos

| Arquivo | Mudança |
|---------|---------|
| `src/utils_rpa/retry.py` | Wrappers sync/async; imports `asyncio`, `inspect` |
| `tests/test_retry.py` | Casos async espelhando sync (sucesso, retry, esgotar, log on/off) |
| `README.md` | Exemplo com `async def` + `await` |

## Fora de escopo

- Qualquer mudança em `anti_captcha` (import ou decorator)
- Adicionar `pytest-asyncio` como dependência
- Tratar funções sync que retornam awaitables

## Critérios de sucesso

- Testes sync existentes continuam passando
- Novos testes async cobrem sucesso, retry até sucesso, esgotamento e logging
- `@retry_with_logging` em `async def` retorna coroutine awaitable
