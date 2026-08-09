# Logger Cleanup-by-Age Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar limpeza opcional de arquivos `.log`/`.lock` antigos (por idade) em `configure_logger`, via nova função pública `cleanup_old_logs`.

**Architecture:** Nova função `cleanup_old_logs(log_dir, max_age_days, *, logger=None)` em `logger.py` que varre `log_dir` (não recursivo) por `*.log*`/`*.lock`, compara `mtime` com um cutoff e apaga os expirados, logando warnings em falhas individuais. `configure_logger` ganha o parâmetro `max_age_days: int | None = None` e chama essa função entre o `mkdir` do `log_dir` e a criação do `file_handler` (evita conflito de arquivo aberto no Windows).

**Tech Stack:** Python >=3.12, `pathlib`, `time`, `logging` (stdlib apenas — sem novas dependências).

## Global Constraints

- Compatibilidade: `max_age_days=None` (default) não altera comportamento atual de `configure_logger`
- Escopo de arquivos: apenas top-level de `log_dir` (sem recursão em subpastas)
- Erro ao excluir um arquivo específico não deve interromper a configuração do logger nem a exclusão dos demais arquivos
- Sem novas dependências externas
- Spec: `docs/superpowers/specs/2026-08-08-logger-cleanup-by-age-design.md`

---

## File Structure

| Arquivo | Responsabilidade |
|---------|------------------|
| `src/utils_rpa/logger.py` | Nova função `cleanup_old_logs`; parâmetro `max_age_days` em `configure_logger` |
| `src/utils_rpa/__init__.py` | Exporta `cleanup_old_logs` |
| `tests/test_logger.py` | Testes de `cleanup_old_logs` isolada e integrada a `configure_logger` |
| `README.md` | Documentação do novo parâmetro e da função |

---

### Task 1: Testes de `cleanup_old_logs` (TDD — falham antes da implementação)

**Files:**
- Modify: `tests/test_logger.py`
- Test: `tests/test_logger.py`

**Interfaces:**
- Consumes: `cleanup_old_logs(log_dir: str | Path, max_age_days: int, *, logger: logging.Logger | None = None) -> list[Path]` (a ser criada na Task 2)
- Produces: casos de teste que definem o contrato da função

- [ ] **Step 1: Acrescentar ao final de `tests/test_logger.py`**

```python
import os
import time


def _touch_with_age(path, age_seconds):
    path.write_text("conteudo")
    old_time = time.time() - age_seconds
    os.utime(path, (old_time, old_time))


def test_cleanup_old_logs_removes_files_older_than_max_age(tmp_path):
    from utils_rpa.logger import cleanup_old_logs

    old_log = tmp_path / "bot.log.1"
    old_lock = tmp_path / "bot.log.lock"
    _touch_with_age(old_log, age_seconds=10 * 86400)
    _touch_with_age(old_lock, age_seconds=10 * 86400)

    removed = cleanup_old_logs(tmp_path, max_age_days=5)

    assert set(removed) == {old_log, old_lock}
    assert not old_log.exists()
    assert not old_lock.exists()


def test_cleanup_old_logs_keeps_recent_files(tmp_path):
    from utils_rpa.logger import cleanup_old_logs

    recent_log = tmp_path / "bot.log"
    _touch_with_age(recent_log, age_seconds=60)

    removed = cleanup_old_logs(tmp_path, max_age_days=5)

    assert removed == []
    assert recent_log.exists()


def test_cleanup_old_logs_ignores_unrelated_extensions(tmp_path):
    from utils_rpa.logger import cleanup_old_logs

    unrelated = tmp_path / "notes.txt"
    _touch_with_age(unrelated, age_seconds=10 * 86400)

    removed = cleanup_old_logs(tmp_path, max_age_days=5)

    assert removed == []
    assert unrelated.exists()


def test_cleanup_old_logs_returns_empty_list_when_dir_missing(tmp_path):
    from utils_rpa.logger import cleanup_old_logs

    missing_dir = tmp_path / "nao_existe"

    assert cleanup_old_logs(missing_dir, max_age_days=5) == []


def test_cleanup_old_logs_logs_warning_on_deletion_failure(tmp_path, monkeypatch, caplog):
    from pathlib import Path

    from utils_rpa.logger import cleanup_old_logs

    old_log = tmp_path / "bot.log.1"
    _touch_with_age(old_log, age_seconds=10 * 86400)

    def _boom(self):
        raise OSError("arquivo em uso")

    monkeypatch.setattr(Path, "unlink", _boom)

    with caplog.at_level(logging.WARNING):
        removed = cleanup_old_logs(tmp_path, max_age_days=5)

    assert removed == []
    assert any("bot.log.1" in m for m in caplog.messages)
```

- [ ] **Step 2: Rodar os testes novos e confirmar falha**

Run: `python -m pytest tests/test_logger.py -k cleanup_old_logs -v`

Expected: FAIL com `ImportError: cannot import name 'cleanup_old_logs'`.

- [ ] **Step 3: Commit dos testes**

```bash
git add tests/test_logger.py
git commit -m "test: add cleanup_old_logs test cases"
```

---

### Task 2: Implementar `cleanup_old_logs` em `logger.py`

**Files:**
- Modify: `src/utils_rpa/logger.py`
- Test: `tests/test_logger.py`

**Interfaces:**
- Produces: `cleanup_old_logs(log_dir: str | Path, max_age_days: int, *, logger: logging.Logger | None = None) -> list[Path]`

- [ ] **Step 1: Adicionar `import time` e a função `cleanup_old_logs` em `src/utils_rpa/logger.py`, antes de `configure_logger`**

```python
import logging
import sys
import time
from pathlib import Path
```

```python
__all__ = [
    "configure_logger",
    "cleanup_old_logs",
    "DEFAULT_LOG_DIR",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_BACKUP_COUNT",
]
```

```python
def cleanup_old_logs(
    log_dir: str | Path,
    max_age_days: int,
    *,
    logger: logging.Logger | None = None,
) -> list[Path]:
    """Remove arquivos ``.log``/``.lock`` de ``log_dir`` mais antigos que ``max_age_days``.

    Considera apenas o nível superior de ``log_dir`` (sem recursão em
    subpastas). A idade é calculada pela data de última modificação
    (``mtime``) do arquivo.

    Args:
        log_dir: Diretório a ser varrido. Se não existir, retorna lista vazia.
        max_age_days: Idade máxima, em dias. Arquivos mais antigos são
            removidos.
        logger: Logger usado para registrar falhas de exclusão. Se ``None``,
            usa o logger do próprio módulo.

    Returns:
        Lista dos caminhos efetivamente removidos.
    """
    log = logger or logging.getLogger(__name__)
    path = Path(log_dir)
    if not path.is_dir():
        return []

    cutoff = time.time() - max_age_days * 86400
    candidates = set(path.glob("*.log*")) | set(path.glob("*.lock"))

    removed: list[Path] = []
    for file_path in candidates:
        if not file_path.is_file():
            continue
        try:
            if file_path.stat().st_mtime >= cutoff:
                continue
            file_path.unlink()
            removed.append(file_path)
        except OSError as exc:
            log.warning("Não foi possível excluir o log antigo '%s': %s", file_path, exc)

    return removed
```

- [ ] **Step 2: Rodar os testes de `cleanup_old_logs`**

Run: `python -m pytest tests/test_logger.py -k cleanup_old_logs -v`

Expected: todos PASS.

- [ ] **Step 3: Commit**

```bash
git add src/utils_rpa/logger.py
git commit -m "feat: add cleanup_old_logs to remove aged log/lock files"
```

---

### Task 3: Integrar `max_age_days` em `configure_logger`

**Files:**
- Modify: `src/utils_rpa/logger.py`
- Test: `tests/test_logger.py`

**Interfaces:**
- Consumes: `cleanup_old_logs` da Task 2
- Produces: `configure_logger(..., max_age_days: int | None = None) -> logging.Logger`

- [ ] **Step 1: Escrever o teste de integração em `tests/test_logger.py`**

```python
def test_configure_logger_cleans_old_files_when_max_age_days_set(tmp_path):
    old_backup = tmp_path / "outro_bot.log.1"
    _touch_with_age(old_backup, age_seconds=10 * 86400)

    configure_logger("test_rpa_cleanup", log_dir=tmp_path, max_age_days=5)

    assert not old_backup.exists()


def test_configure_logger_keeps_files_when_max_age_days_is_none(tmp_path):
    old_backup = tmp_path / "outro_bot.log.1"
    _touch_with_age(old_backup, age_seconds=10 * 86400)

    configure_logger("test_rpa_no_cleanup", log_dir=tmp_path)

    assert old_backup.exists()
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `python -m pytest tests/test_logger.py -k max_age_days -v`

Expected: FAIL em `test_configure_logger_cleans_old_files_when_max_age_days_set` com `TypeError: configure_logger() got an unexpected keyword argument 'max_age_days'`.

- [ ] **Step 3: Adicionar o parâmetro e a chamada em `configure_logger`**

Assinatura (adicionar `max_age_days` após `backup_count`):

```python
def configure_logger(
    name: str = '__main__',
    *,
    log_dir: str | Path = DEFAULT_LOG_DIR,
    file_name: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    max_age_days: int | None = None,
    level: int = DEFAULT_LEVEL,
    log_format: str = DEFAULT_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
) -> logging.Logger:
```

Docstring (adicionar após a linha de `backup_count`):

```python
        max_age_days: Se informado, arquivos ``.log``/``.lock`` em ``log_dir``
            com mais dias que esse valor são excluídos ao configurar o
            logger. Padrão: ``None`` (nenhuma limpeza).
```

Corpo — inserir a chamada de limpeza entre o `mkdir` e a criação do `file_handler`:

```python
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    if max_age_days is not None:
        cleanup_old_logs(log_path, max_age_days, logger=logger)

    file_path = log_path / (file_name or f"{name}.log")
```

(o restante do corpo permanece igual)

- [ ] **Step 4: Rodar a suíte completa de `test_logger.py`**

Run: `python -m pytest tests/test_logger.py -v`

Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add src/utils_rpa/logger.py tests/test_logger.py
git commit -m "feat: add max_age_days option to configure_logger"
```

---

### Task 4: Exportar `cleanup_old_logs` no pacote

**Files:**
- Modify: `src/utils_rpa/__init__.py`
- Test: nenhum novo (cobertura via import direto)

**Interfaces:**
- Consumes: `cleanup_old_logs` de `utils_rpa.logger`
- Produces: `utils_rpa.cleanup_old_logs` disponível no nível do pacote

- [ ] **Step 1: Atualizar `src/utils_rpa/__init__.py`**

```python
"""utils_rpa - utilitários e configurações para facilitar o desenvolvimento de RPA com Python."""

from utils_rpa.forms import extract_inputs
from utils_rpa.logger import cleanup_old_logs, configure_logger
from utils_rpa.retry import retry_with_logging
from utils_rpa.screenshot import capture_screen

__version__ = "0.2.1"

__all__ = [
    "__version__",
    "configure_logger",
    "cleanup_old_logs",
    "retry_with_logging",
    "capture_screen",
    "extract_inputs",
]
```

- [ ] **Step 2: Verificar o import**

Run: `python -c "from utils_rpa import cleanup_old_logs; print(cleanup_old_logs)"`

Expected: imprime a referência da função, sem erro.

- [ ] **Step 3: Rodar a suíte completa**

Run: `python -m pytest tests/ -v`

Expected: mesmo resultado de antes desta feature (todos PASS, exceto a falha pré-existente e não relacionada em `tests/test_forms.py::test_checkbox_checked_without_value_defaults_to_on`).

- [ ] **Step 4: Commit**

```bash
git add src/utils_rpa/__init__.py
git commit -m "feat: export cleanup_old_logs from utils_rpa package"
```

---

### Task 5: Documentar no README

**Files:**
- Modify: `README.md` (seção `### \`configure_logger\``)

**Interfaces:**
- Consumes: API implementada nas Tasks 2-4

- [ ] **Step 1: Inserir exemplo após o bloco "Personalizando os parâmetros"**

Após:

````markdown
```python
import logging
from utils_rpa import configure_logger

logger = configure_logger(
    "meu_bot",
    log_dir="./logs",
    file_name="bot.log",
    max_bytes=10 * 1024 * 1024,  # 10 MB
    backup_count=5,
    level=logging.DEBUG,
)
```
````

Inserir:

````markdown

Limpando arquivos `.log`/`.lock` antigos automaticamente (por idade, em dias):

```python
logger = configure_logger("meu_bot", max_age_days=30)
# Ao configurar, remove de ./logs qualquer *.log*/*.lock com mais de 30 dias.
```

Ou de forma isolada, sem passar por `configure_logger`:

```python
from utils_rpa import cleanup_old_logs

removidos = cleanup_old_logs("./logs", max_age_days=30)
print(f"{len(removidos)} arquivo(s) removido(s).")
```
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document cleanup_old_logs and max_age_days option"
```

---

## Self-Review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| `max_age_days: int \| None = None`, opt-in | Task 3 |
| Escopo `*.log*` e `*.lock`, não recursivo | Task 2 |
| Idade por `mtime` | Task 2 |
| Erro de exclusão individual → warning, não interrompe | Task 1 (teste), Task 2 (implementação) |
| `cleanup_old_logs` pública e reutilizável | Task 2, Task 4 |
| Ordem: depois do `mkdir`, antes do `file_handler` | Task 3 |
| Documentação README | Task 5 |
