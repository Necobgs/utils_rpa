# Design: limpeza de logs antigos por idade em `configure_logger`

## Objetivo

Oferecer uma opção em `configure_logger` para excluir arquivos `.log`/`.lock` antigos da pasta de logs, com o limite de idade definido pelo usuário.

## Decisões

| Decisão | Escolha |
|---------|---------|
| Quando roda | Automaticamente dentro de `configure_logger`, na primeira configuração do logger (quando os handlers são criados) |
| Parâmetro | `max_age_days: int \| None = None` |
| Default | `None` → nenhuma limpeza (opt-in) |
| Escopo dos arquivos | Todos os arquivos que casem com `*.log*` ou `*.lock` em `log_dir` (não recursivo), de **qualquer** logger/processo que grave na mesma pasta |
| Referência de idade | `mtime` (data de última modificação) do arquivo |
| Erro ao excluir um arquivo | `logger.warning(...)` com o nome do arquivo e o erro; continua para os demais arquivos |
| API pública | Nova função `cleanup_old_logs(log_dir, max_age_days)` exportada em `utils_rpa`, reutilizável fora de `configure_logger` |

## Comportamento

`cleanup_old_logs(log_dir: str | Path, max_age_days: int, *, logger: logging.Logger | None = None) -> list[Path]`:

1. Resolve `log_dir` como `Path`. Se não existir, retorna lista vazia (nada a fazer).
2. Calcula `cutoff = time.time() - max_age_days * 86400`.
3. Varre (não recursivo) `log_dir.glob("*.log*")` e `log_dir.glob("*.lock")`, unindo os resultados sem duplicar.
4. Para cada arquivo cujo `mtime` seja anterior ao `cutoff`, tenta apagar (`Path.unlink`).
   - Sucesso → adiciona à lista de retorno (arquivos removidos).
   - Falha (`OSError`, ex.: arquivo em uso) → loga warning e segue para o próximo arquivo. O warning usa `logger` se informado; caso contrário, usa `logging.getLogger(__name__)` (logger do próprio módulo) como fallback — assim a função funciona sozinha, sem exigir um logger já configurado.
5. Retorna a lista de arquivos efetivamente removidos.

`configure_logger(..., max_age_days: int | None = None, ...)`:

- Parâmetro novo, mantém compatibilidade (default `None` = sem mudança de comportamento).
- Dentro do bloco que cria os handlers (após todos criados, antes do `return logger`), se `max_age_days is not None`, chama `cleanup_old_logs(log_dir, max_age_days, logger=logger)` — passando o logger já configurado, para que os warnings apareçam no console/arquivo do próprio bot.
- Como a função só executa dentro do bloco `if logger.handlers: return logger` (guarda de deduplicação), a limpeza roda uma vez por logger/processo — igual ao restante da configuração.

## Arquivos afetados

| Arquivo | Mudança |
|---------|---------|
| `src/utils_rpa/logger.py` | Nova função `cleanup_old_logs`; novo parâmetro `max_age_days` em `configure_logger` |
| `src/utils_rpa/__init__.py` | Exportar `cleanup_old_logs` |
| `tests/test_logger.py` | Testes para `cleanup_old_logs` isolada e para o parâmetro `max_age_days` em `configure_logger` |
| `README.md` | Documentar o novo parâmetro e a função `cleanup_old_logs` |

## Fora de escopo

- Agendamento/thread em background para rodar a limpeza periodicamente
- Limpeza recursiva em subpastas
- Qualquer alteração na rotação por tamanho (`max_bytes`/`backup_count`) já existente

## Critérios de sucesso

- Com `max_age_days=None` (default), comportamento de `configure_logger` idêntico ao atual
- Arquivos `.log`/`.lock` com `mtime` mais antigo que `max_age_days` são removidos da pasta ao configurar o logger
- Arquivos dentro do limite de idade permanecem intactos
- Falha ao excluir um arquivo específico não interrompe a configuração do logger, apenas gera um warning
- `cleanup_old_logs` pode ser chamada isoladamente, fora de `configure_logger`
