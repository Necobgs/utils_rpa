# Logger por id Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gravar cada execução num arquivo `nome-id-{id}.log`, com backup ilimitado por padrão e descarte do menor id via `max_ids`, e oferecer limpeza separada pela data da última atualização.

**Architecture:** `cleanup_logs_by_last_update` lista grupos `{stem}-id-{número}` e apaga os mais antigos até sobrar `keep`. `configure_logger_by_id` cria o logger, troca só o handler de arquivo quando o id muda e, se `max_ids` vier, apaga o menor id exceto o da chamada. As duas funções compartilham internas de stem, grupo e exclusão. `configure_logger` passa a usar as internas de nome, console e arquivo sem mudar o comportamento observável.

**Tech Stack:** Python >= 3.12, `logging`, `pathlib`, `re`, `concurrent-log-handler` (já dependência). Sem dependência nova.

## Global Constraints

- `configure_logger` permanece com o comportamento atual, inclusive `backup_count` padrão 3, `max_age_days` só na primeira configuração e retorno imediato quando o logger já tem handlers
- `configure_logger_by_id` não recebe `max_age_days` e não chama `cleanup_logs_by_last_update`
- Id é inteiro positivo; zero, negativo, texto, decimal e booleano geram `ValueError` antes de criar pasta ou apagar arquivo
- Arquivo: `{stem}-id-{id}.log`; o `name` do logger Python não inclui o id
- Sem `backup_count`, usar `UNLIMITED_BACKUP_COUNT = sys.maxsize`; `.log.1` continua sendo o backup mais recente
- `backup_count` informado, inclusive `0`, é repassado ao `ConcurrentRotatingFileHandler`
- `max_ids` omitido não apaga ids; menor que 1 gera `ValueError`; acima do limite sai o menor id; o id desta chamada nunca sai
- `keep` menor que 0 gera `ValueError`; `keep=0` apaga todos os grupos daquele stem; `file_name` vazio gera `ValueError`
- Data: `mtime` do arquivo base; sem base, `mtime` do backup de menor índice; só `.lock` conta como o mais antigo; empate de data apaga o menor id
- A limpeza por data não recebe o id em uso e pode apagá-lo
- Escopo: só `{stem}-id-{número}.log`, `.log.{n}` e `.lock` no topo de `log_dir`, número sem zero à esquerda (`[1-9]\d*`)
- Falha ao apagar um arquivo: warning, segue, caminho fora da lista; se o grupo continuar no disco, a mesma chamada tenta o próximo id e não repete esse
- Pasta inexistente em `cleanup_logs_by_last_update` devolve `[]`
- No mesmo processo, outro arquivo no mesmo `name` troca só o handler de arquivo; nível, formato e console ficam os da primeira chamada; o handler antigo fecha antes da limpeza por id
- Mesma chamada de novo não duplica handler; com `max_ids`, a limpeza por id roda mesmo assim
- `configure_logger` chamado depois não troca o arquivo
- Cada teste novo usa `name` exclusivo, porque `logging.getLogger` é global; no fim do teste fecha os handlers
- Spec: `docs/superpowers/specs/2026-10-02-logger-by-id-design.md`

---

## File Structure

| Arquivo | Responsabilidade |
|---------|------------------|
| `src/utils_rpa/logger.py` | Internas de stem, grupo e exclusão; `cleanup_logs_by_last_update`; refactor de `configure_logger`; `configure_logger_by_id` |
| `src/utils_rpa/__init__.py` | Exporta as duas funções novas |
| `tests/test_logger.py` | Contratos das duas funções e a compatibilidade de `configure_logger` |
| `README.md` | Uso das duas funções |

Não há tarefa de multiprocessing. O mesmo `ConcurrentRotatingFileHandler` já permite dois processos no mesmo arquivo e ids diferentes em arquivos diferentes.

---

### Task 1: `cleanup_logs_by_last_update`

**Files:**
- Modify: `src/utils_rpa/logger.py`
- Test: `tests/test_logger.py`

**Interfaces:**
- Consumes: `_touch_with_age` já existente em `tests/test_logger.py`
- Produces:
  - `cleanup_logs_by_last_update(log_dir: str | Path, file_name: str, keep: int, *, logger: logging.Logger | None = None) -> list[Path]`
  - `_log_stem(file_name: str) -> str`
  - `_iter_log_id_groups(log_dir: Path, stem: str) -> dict[int, list[Path]]`
  - `_group_age_key(stem: str, log_id: int, files: list[Path]) -> tuple[int, float, int]`
  - `_delete_log_files(files: list[Path], logger: logging.Logger) -> list[Path]`

- [ ] **Step 1: Acrescentar os testes ao final de `tests/test_logger.py`**

Incluir `import pytest` no topo do arquivo, junto dos imports existentes.

```python
def test_cleanup_logs_by_last_update_removes_oldest_group(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    old = tmp_path / "automation-id-1.log"
    old_backup = tmp_path / "automation-id-1.log.1"
    old_lock = tmp_path / "automation-id-1.lock"
    mid = tmp_path / "automation-id-2.log"
    new = tmp_path / "automation-id-3.log"
    _touch_with_age(old, 300)
    _touch_with_age(old_backup, 50)
    _touch_with_age(old_lock, 50)
    _touch_with_age(mid, 200)
    _touch_with_age(new, 100)

    removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=2)

    assert set(removed) == {old, old_backup, old_lock}
    assert not old.exists()
    assert not old_backup.exists()
    assert not old_lock.exists()
    assert mid.exists()
    assert new.exists()


def test_cleanup_logs_by_last_update_accepts_log_suffix_in_file_name(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    old = tmp_path / "automation-id-1.log"
    new = tmp_path / "automation-id-2.log"
    _touch_with_age(old, 300)
    _touch_with_age(new, 100)

    removed = cleanup_logs_by_last_update(tmp_path, "automation.log", keep=1)

    assert removed == [old]
    assert not old.exists()
    assert new.exists()


def test_cleanup_logs_by_last_update_uses_lowest_backup_index_when_base_missing(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    low_index = tmp_path / "automation-id-1.log.1"
    high_index = tmp_path / "automation-id-1.log.3"
    other = tmp_path / "automation-id-2.log"
    _touch_with_age(low_index, 10)
    _touch_with_age(high_index, 900)
    _touch_with_age(other, 200)

    removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=1)

    assert set(removed) == {other}
    assert low_index.exists()
    assert high_index.exists()
    assert not other.exists()


def test_cleanup_logs_by_last_update_treats_lock_only_as_oldest(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    lock = tmp_path / "automation-id-8.lock"
    base = tmp_path / "automation-id-9.log"
    _touch_with_age(lock, 1)
    _touch_with_age(base, 10)

    removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=1)

    assert removed == [lock]
    assert not lock.exists()
    assert base.exists()


def test_cleanup_logs_by_last_update_tie_removes_smaller_id(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    smaller = tmp_path / "automation-id-4.log"
    larger = tmp_path / "automation-id-9.log"
    _touch_with_age(smaller, 100)
    _touch_with_age(larger, 100)

    removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=1)

    assert removed == [smaller]
    assert not smaller.exists()
    assert larger.exists()


def test_cleanup_logs_by_last_update_keep_zero_removes_only_matching_stem(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    match = tmp_path / "automation-id-1.log"
    other = tmp_path / "other-id-1.log"
    leading_zero = tmp_path / "automation-id-007.log"
    match.write_text("a")
    other.write_text("b")
    leading_zero.write_text("c")

    removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=0)

    assert removed == [match]
    assert not match.exists()
    assert other.exists()
    assert leading_zero.exists()


def test_cleanup_logs_by_last_update_keeps_all_when_under_limit(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    kept = tmp_path / "automation-id-1.log"
    kept.write_text("a")

    assert cleanup_logs_by_last_update(tmp_path, "automation", keep=3) == []
    assert kept.exists()


def test_cleanup_logs_by_last_update_missing_dir_returns_empty(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    assert cleanup_logs_by_last_update(tmp_path / "nao", "automation", keep=1) == []


def test_cleanup_logs_by_last_update_rejects_invalid_keep_and_empty_name(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    missing = tmp_path / "nao"
    with pytest.raises(ValueError, match="keep"):
        cleanup_logs_by_last_update(missing, "automation", keep=-1)
    with pytest.raises(ValueError, match="keep"):
        cleanup_logs_by_last_update(missing, "automation", keep=True)
    with pytest.raises(ValueError, match="file_name"):
        cleanup_logs_by_last_update(tmp_path, "", keep=1)
    assert not missing.exists()


def test_cleanup_logs_by_last_update_skips_id_that_remains_after_failure(tmp_path, monkeypatch, caplog):
    from utils_rpa.logger import cleanup_logs_by_last_update

    first = tmp_path / "automation-id-1.log"
    second = tmp_path / "automation-id-2.log"
    first.write_text("a")
    second.write_text("b")

    def _boom(self):
        raise OSError("arquivo em uso")

    monkeypatch.setattr(Path, "unlink", _boom)
    with caplog.at_level(logging.WARNING):
        removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=0)

    assert removed == []
    assert first.exists()
    assert second.exists()
    assert any("automation-id-1.log" in message for message in caplog.messages)
    assert any("automation-id-2.log" in message for message in caplog.messages)
```

- [ ] **Step 2: Rodar os testes e confirmar a falha**

Run: `python -m pytest tests/test_logger.py::test_cleanup_logs_by_last_update_removes_oldest_group tests/test_logger.py::test_cleanup_logs_by_last_update_rejects_invalid_keep_and_empty_name -v`

Expected: FAIL com `ImportError` em `cleanup_logs_by_last_update`.

- [ ] **Step 3: Implementar em `src/utils_rpa/logger.py`**

Acrescentar `import re` junto dos imports da stdlib.

Inserir o bloco abaixo depois de `cleanup_old_logs` e antes de `configure_logger`. Atualizar `__all__` só na Task 4.

```python
def _log_stem(file_name: str) -> str:
    if file_name.endswith(".log"):
        return file_name[:-4]
    return file_name


def _id_patterns(stem: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    escaped = re.escape(stem)
    file_re = re.compile(rf"^{escaped}-id-([1-9]\d*)\.log(?:\.(\d+))?$")
    lock_re = re.compile(rf"^{escaped}-id-([1-9]\d*)\.lock$")
    return file_re, lock_re


def _iter_log_id_groups(log_dir: Path, stem: str) -> dict[int, list[Path]]:
    file_re, lock_re = _id_patterns(stem)
    groups: dict[int, list[Path]] = {}
    if not log_dir.is_dir():
        return groups
    for entry in log_dir.iterdir():
        if not entry.is_file():
            continue
        match = file_re.match(entry.name) or lock_re.match(entry.name)
        if match is None:
            continue
        groups.setdefault(int(match.group(1)), []).append(entry)
    return groups


def _group_age_key(stem: str, log_id: int, files: list[Path]) -> tuple[int, float, int]:
    file_re, _lock_re = _id_patterns(stem)
    base_mtime: float | None = None
    lowest_backup: tuple[int, float] | None = None
    for file_path in files:
        match = file_re.match(file_path.name)
        if match is None:
            continue
        backup_index = match.group(2)
        mtime = file_path.stat().st_mtime
        if backup_index is None:
            base_mtime = mtime
            continue
        index = int(backup_index)
        if lowest_backup is None or index < lowest_backup[0]:
            lowest_backup = (index, mtime)
    if base_mtime is not None:
        return (1, base_mtime, log_id)
    if lowest_backup is not None:
        return (1, lowest_backup[1], log_id)
    return (0, 0.0, log_id)


def _delete_log_files(files: list[Path], logger: logging.Logger) -> list[Path]:
    removed: list[Path] = []
    for file_path in files:
        try:
            file_path.unlink()
        except OSError as exc:
            logger.warning(
                "Não foi possível excluir o log antigo '%s': %s",
                file_path,
                exc,
            )
        else:
            removed.append(file_path)
    return removed


def cleanup_logs_by_last_update(
    log_dir: str | Path,
    file_name: str,
    keep: int,
    *,
    logger: logging.Logger | None = None,
) -> list[Path]:
    """Remove grupos de log por id até sobrar ``keep`` grupos, dos mais antigos para os mais novos.

    A data de um grupo é o ``mtime`` de ``{stem}-id-{id}.log``. Se esse arquivo
    não existir, usa o ``mtime`` do backup de menor índice. Um id que só tem
    ``.lock`` é tratado como o mais antigo. Empate de data remove o menor id.

    Args:
        log_dir: Pasta dos logs. Se não existir, retorna lista vazia.
        file_name: Nome-base. ``automation`` e ``automation.log`` casam os mesmos grupos.
        keep: Quantidade de ids que permanecem. ``0`` remove todos os grupos do stem.
        logger: Logger dos warnings de falha. Se ``None``, usa o logger do módulo.

    Returns:
        Caminhos efetivamente removidos.
    """
    if isinstance(keep, bool) or not isinstance(keep, int) or keep < 0:
        raise ValueError("keep deve ser um inteiro maior ou igual a zero")
    if file_name == "":
        raise ValueError("file_name não pode ser vazio")

    log = logger or logging.getLogger(__name__)
    path = Path(log_dir)
    if not path.is_dir():
        return []

    stem = _log_stem(file_name)
    removed: list[Path] = []
    skipped: set[int] = set()
    while True:
        groups = _iter_log_id_groups(path, stem)
        if len(groups) <= keep:
            return removed
        candidates = [log_id for log_id in groups if log_id not in skipped]
        if not candidates:
            return removed
        victim = min(
            candidates,
            key=lambda log_id: _group_age_key(stem, log_id, groups[log_id]),
        )
        deleted = _delete_log_files(groups[victim], log)
        removed.extend(deleted)
        if any(file_path.exists() for file_path in groups[victim]):
            skipped.add(victim)
```

- [ ] **Step 4: Rodar os testes novos**

Run: `python -m pytest tests/test_logger.py -k cleanup_logs_by_last_update -v`

Expected: PASS em todos os testes `cleanup_logs_by_last_update`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_logger.py src/utils_rpa/logger.py
git commit -m "feat: add cleanup_logs_by_last_update"
```

---

### Task 2: Reusar nome, console e arquivo em `configure_logger`

**Files:**
- Modify: `src/utils_rpa/logger.py` (`configure_logger`, por volta das linhas 73-150)
- Test: `tests/test_logger.py` (suíte já existente; não criar teste novo)

**Interfaces:**
- Consumes: `_log_stem(file_name: str) -> str` da Task 1
- Produces:
  - `_resolve_log_file_name(name: str | None, file_name: str | None, log_id: int | None = None) -> str`
  - `_build_console_handlers(formatter: logging.Formatter) -> tuple[logging.Handler, logging.Handler]`
  - `_build_file_handler(file_path: Path, max_bytes: int, backup_count: int, formatter: logging.Formatter) -> ConcurrentRotatingFileHandler`

- [ ] **Step 1: Extrair as internas e substituir o corpo de `configure_logger`**

Inserir as três funções imediatamente acima de `configure_logger`. Substituir o corpo de `configure_logger` pelo bloco abaixo. A assinatura e a docstring de `configure_logger` não mudam. `logger.setLevel(level)` continua antes da guarda `if logger.handlers`.

```python
def _resolve_log_file_name(
    name: str | None,
    file_name: str | None,
    log_id: int | None = None,
) -> str:
    stem = _log_stem(file_name or name or "automation")
    if log_id is None:
        return f"{stem}.log"
    return f"{stem}-id-{log_id}.log"


def _build_console_handlers(
    formatter: logging.Formatter,
) -> tuple[logging.Handler, logging.Handler]:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(lambda record: record.levelno < logging.ERROR)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.ERROR)
    return console_handler, stderr_handler


def _build_file_handler(
    file_path: Path,
    max_bytes: int,
    backup_count: int,
    formatter: logging.Formatter,
) -> ConcurrentRotatingFileHandler:
    file_handler = ConcurrentRotatingFileHandler(
        str(file_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    return file_handler
```

Corpo novo de `configure_logger`, depois da guarda de handlers:

```python
    formatter = logging.Formatter(log_format, datefmt=date_format)
    for handler in _build_console_handlers(formatter):
        logger.addHandler(handler)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    if max_age_days is not None:
        cleanup_old_logs(log_path, max_age_days, logger=logger)

    file_path = log_path / _resolve_log_file_name(name, file_name)
    logger.addHandler(_build_file_handler(file_path, max_bytes, backup_count, formatter))
    return logger
```

- [ ] **Step 2: Rodar a suíte do logger**

Run: `python -m pytest tests/test_logger.py -v`

Expected: PASS, inclusive os testes antigos de `configure_logger` e `cleanup_old_logs`.

- [ ] **Step 3: Commit**

```bash
git add src/utils_rpa/logger.py
git commit -m "refactor: share logger file and console handler setup"
```

---

### Task 3: `configure_logger_by_id`

**Files:**
- Modify: `src/utils_rpa/logger.py`
- Test: `tests/test_logger.py`

**Interfaces:**
- Consumes:
  - `_log_stem(file_name: str) -> str`
  - `_iter_log_id_groups(log_dir: Path, stem: str) -> dict[int, list[Path]]`
  - `_delete_log_files(files: list[Path], logger: logging.Logger) -> list[Path]`
  - `_resolve_log_file_name(name: str | None, file_name: str | None, log_id: int | None = None) -> str`
  - `_build_console_handlers(formatter: logging.Formatter) -> tuple[logging.Handler, logging.Handler]`
  - `_build_file_handler(file_path: Path, max_bytes: int, backup_count: int, formatter: logging.Formatter) -> ConcurrentRotatingFileHandler`
- Produces:
  - `UNLIMITED_BACKUP_COUNT: int`
  - `configure_logger_by_id(name: str | None = None, *, id: int, log_dir: str | Path = DEFAULT_LOG_DIR, file_name: str | None = None, max_bytes: int = DEFAULT_MAX_BYTES, backup_count: int | None = None, max_ids: int | None = None, level: int = DEFAULT_LEVEL, log_format: str = DEFAULT_FORMAT, date_format: str = DEFAULT_DATE_FORMAT) -> logging.Logger`

- [ ] **Step 1: Acrescentar os testes ao final de `tests/test_logger.py`**

```python
def _close_logger(name: str | None) -> None:
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def test_configure_logger_by_id_creates_id_file(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id("test_rpa_by_id_create", id=123, log_dir=tmp_path)
        logger.info("mensagem")
        assert (tmp_path / "test_rpa_by_id_create-id-123.log").exists()
        assert logger.name == "test_rpa_by_id_create"
    finally:
        _close_logger("test_rpa_by_id_create")


def test_configure_logger_by_id_uses_file_name_stem(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        configure_logger_by_id(
            "test_rpa_by_id_stem",
            id=8,
            log_dir=tmp_path,
            file_name="automation.log",
        )
        assert (tmp_path / "automation-id-8.log").exists()
        assert not (tmp_path / "test_rpa_by_id_stem-id-8.log").exists()
    finally:
        _close_logger("test_rpa_by_id_stem")


def test_configure_logger_by_id_name_none_uses_automation(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    root = logging.getLogger()
    previous = list(root.handlers)
    root.handlers.clear()
    try:
        logger = configure_logger_by_id(id=4, log_dir=tmp_path)
        assert logger is root
        assert (tmp_path / "automation-id-4.log").exists()
    finally:
        _close_logger(None)
        for handler in previous:
            root.addHandler(handler)


def test_configure_logger_by_id_rejects_invalid_id_before_mkdir(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    missing = tmp_path / "nao"
    for invalid in (0, -1, True, "1", 1.5):
        with pytest.raises(ValueError, match="id"):
            configure_logger_by_id("test_rpa_by_id_bad", id=invalid, log_dir=missing)
    assert not missing.exists()


def test_configure_logger_by_id_rejects_invalid_max_ids_and_empty_file_name(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    missing = tmp_path / "nao"
    with pytest.raises(ValueError, match="max_ids"):
        configure_logger_by_id("test_rpa_by_id_bad_max", id=1, log_dir=missing, max_ids=0)
    with pytest.raises(ValueError, match="max_ids"):
        configure_logger_by_id("test_rpa_by_id_bad_max", id=1, log_dir=missing, max_ids=True)
    with pytest.raises(ValueError, match="file_name"):
        configure_logger_by_id(
            "test_rpa_by_id_bad_name",
            id=1,
            log_dir=missing,
            file_name="",
        )
    assert not missing.exists()


def test_configure_logger_by_id_unlimited_backup_and_explicit_limit(tmp_path):
    from utils_rpa.logger import UNLIMITED_BACKUP_COUNT, configure_logger_by_id

    try:
        unlimited = configure_logger_by_id("test_rpa_by_id_unlim", id=1, log_dir=tmp_path)
        limited = configure_logger_by_id(
            "test_rpa_by_id_lim",
            id=1,
            log_dir=tmp_path,
            backup_count=4,
            max_bytes=1024,
        )
        unlimited_handler = next(
            handler
            for handler in unlimited.handlers
            if isinstance(handler, ConcurrentRotatingFileHandler)
        )
        limited_handler = next(
            handler
            for handler in limited.handlers
            if isinstance(handler, ConcurrentRotatingFileHandler)
        )
        assert unlimited_handler.backupCount == UNLIMITED_BACKUP_COUNT
        assert limited_handler.backupCount == 4
        assert limited_handler.maxBytes == 1024
    finally:
        _close_logger("test_rpa_by_id_unlim")
        _close_logger("test_rpa_by_id_lim")


def test_configure_logger_by_id_rollover_keeps_newest_backup_as_dot_1(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id(
            "test_rpa_by_id_roll",
            id=7,
            log_dir=tmp_path,
            max_bytes=80,
        )
        logger.info("FIRST-MARKER " + ("a" * 100))
        logger.info("SECOND-MARKER " + ("b" * 100))
        logger.info("THIRD-MARKER " + ("c" * 100))
        newest_backup = (tmp_path / "test_rpa_by_id_roll-id-7.log.1").read_text(encoding="utf-8")
        older_backup = (tmp_path / "test_rpa_by_id_roll-id-7.log.2").read_text(encoding="utf-8")
        assert "SECOND-MARKER" in newest_backup
        assert "FIRST-MARKER" in older_backup
    finally:
        _close_logger("test_rpa_by_id_roll")


def test_configure_logger_by_id_backup_count_discards_older_backups(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id(
            "test_rpa_by_id_discard",
            id=7,
            log_dir=tmp_path,
            max_bytes=80,
            backup_count=1,
        )
        logger.info("FIRST-MARKER " + ("a" * 100))
        logger.info("SECOND-MARKER " + ("b" * 100))
        logger.info("THIRD-MARKER " + ("c" * 100))
        assert (tmp_path / "test_rpa_by_id_discard-id-7.log.1").exists()
        assert not (tmp_path / "test_rpa_by_id_discard-id-7.log.2").exists()
    finally:
        _close_logger("test_rpa_by_id_discard")


def test_configure_logger_by_id_max_ids_removes_lowest_and_protects_current(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        _touch_with_age(tmp_path / "bot-id-50.log", 5000)
        _touch_with_age(tmp_path / "bot-id-2.log", 10)
        (tmp_path / "other-id-1.log").write_text("z")
        configure_logger_by_id("test_rpa_by_id_max", id=60, log_dir=tmp_path, file_name="bot.log", max_ids=2)
        assert not (tmp_path / "bot-id-2.log").exists()
        assert (tmp_path / "bot-id-50.log").exists()
        assert (tmp_path / "bot-id-60.log").exists()
        assert (tmp_path / "other-id-1.log").exists()
    finally:
        _close_logger("test_rpa_by_id_max")


def test_configure_logger_by_id_keeps_current_when_it_is_the_lowest(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        (tmp_path / "bot-id-5.log").write_text("a")
        (tmp_path / "bot-id-9.log").write_text("b")
        configure_logger_by_id("test_rpa_by_id_current", id=1, log_dir=tmp_path, file_name="bot", max_ids=2)
        assert (tmp_path / "bot-id-1.log").exists()
        assert not (tmp_path / "bot-id-5.log").exists()
        assert (tmp_path / "bot-id-9.log").exists()
    finally:
        _close_logger("test_rpa_by_id_current")


def test_configure_logger_by_id_without_max_ids_keeps_other_ids(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        (tmp_path / "bot-id-1.log").write_text("a")
        configure_logger_by_id("test_rpa_by_id_nomax", id=9, log_dir=tmp_path, file_name="bot")
        assert (tmp_path / "bot-id-1.log").exists()
    finally:
        _close_logger("test_rpa_by_id_nomax")


def test_configure_logger_by_id_repeat_does_not_duplicate_and_still_purges(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id(
            "test_rpa_by_id_repeat",
            id=5,
            log_dir=tmp_path,
            file_name="bot",
            max_ids=1,
        )
        handler_count = len(logger.handlers)
        (tmp_path / "bot-id-1.log").write_text("later")
        again = configure_logger_by_id(
            "test_rpa_by_id_repeat",
            id=5,
            log_dir=tmp_path,
            file_name="bot",
            max_ids=1,
            level=logging.DEBUG,
        )
        file_handlers = [
            handler
            for handler in again.handlers
            if isinstance(handler, ConcurrentRotatingFileHandler)
        ]
        assert again is logger
        assert len(again.handlers) == handler_count
        assert len(file_handlers) == 1
        assert again.level == logging.INFO
        assert not (tmp_path / "bot-id-1.log").exists()
    finally:
        _close_logger("test_rpa_by_id_repeat")


def test_configure_logger_by_id_switches_file_and_drops_previous_id(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id(
            "test_rpa_by_id_switch",
            id=123,
            log_dir=tmp_path,
            max_ids=1,
        )
        logger.info("linha-123")
        handler_count = len(logger.handlers)
        same = configure_logger_by_id(
            "test_rpa_by_id_switch",
            id=456,
            log_dir=tmp_path,
            max_ids=1,
            level=logging.DEBUG,
            log_format="SOMENTE %(message)s",
        )
        same.info("linha-456")
        file_handlers = [
            handler
            for handler in same.handlers
            if isinstance(handler, ConcurrentRotatingFileHandler)
        ]
        text_456 = (tmp_path / "test_rpa_by_id_switch-id-456.log").read_text(encoding="utf-8")
        assert same is logger
        assert same.level == logging.INFO
        assert len(same.handlers) == handler_count
        assert len(file_handlers) == 1
        assert "SOMENTE" not in text_456
        assert "|" in text_456
        assert not (tmp_path / "test_rpa_by_id_switch-id-123.log").exists()
        assert "linha-456" in text_456
        assert "linha-123" not in text_456
    finally:
        _close_logger("test_rpa_by_id_switch")


def test_configure_logger_by_id_different_names_write_separate_files(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        first = configure_logger_by_id("test_rpa_by_id_a", id=1, log_dir=tmp_path)
        second = configure_logger_by_id("test_rpa_by_id_b", id=2, log_dir=tmp_path)
        first.info("texto-a")
        second.info("texto-b")
        assert "texto-a" in (tmp_path / "test_rpa_by_id_a-id-1.log").read_text(encoding="utf-8")
        assert "texto-b" in (tmp_path / "test_rpa_by_id_b-id-2.log").read_text(encoding="utf-8")
    finally:
        _close_logger("test_rpa_by_id_a")
        _close_logger("test_rpa_by_id_b")


def test_configure_logger_after_by_id_does_not_switch_file(tmp_path):
    from utils_rpa import configure_logger
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id("test_rpa_by_id_sticky", id=4, log_dir=tmp_path)
        configure_logger("test_rpa_by_id_sticky", log_dir=tmp_path, file_name="outro.log")
        logger.info("continua-no-id")
        assert "continua-no-id" in (tmp_path / "test_rpa_by_id_sticky-id-4.log").read_text(
            encoding="utf-8"
        )
        assert not (tmp_path / "outro.log").exists()
    finally:
        _close_logger("test_rpa_by_id_sticky")


def test_configure_logger_by_id_warns_and_continues_when_delete_fails(tmp_path, monkeypatch, caplog):
    from utils_rpa.logger import configure_logger_by_id

    (tmp_path / "bot-id-1.log").write_text("a")

    def _boom(self):
        raise OSError("arquivo em uso")

    monkeypatch.setattr(Path, "unlink", _boom)
    try:
        with caplog.at_level(logging.WARNING):
            logger = configure_logger_by_id(
                "test_rpa_by_id_warn",
                id=9,
                log_dir=tmp_path,
                file_name="bot",
                max_ids=1,
            )
        assert logger.name == "test_rpa_by_id_warn"
        assert (tmp_path / "bot-id-1.log").exists()
        assert any("bot-id-1.log" in message for message in caplog.messages)
    finally:
        _close_logger("test_rpa_by_id_warn")
```

- [ ] **Step 2: Rodar um teste e confirmar a falha**

Run: `python -m pytest tests/test_logger.py::test_configure_logger_by_id_creates_id_file -v`

Expected: FAIL com `ImportError` em `configure_logger_by_id`.

- [ ] **Step 3: Implementar em `src/utils_rpa/logger.py`**

Acrescentar `import sys` se ainda não estiver importado. Ele já está. Perto de `DEFAULT_BACKUP_COUNT`, acrescentar:

```python
UNLIMITED_BACKUP_COUNT = sys.maxsize
```

Inserir `_remove_lowest_log_ids` e `configure_logger_by_id` depois de `configure_logger`.

```python
def _require_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} deve ser um inteiro positivo")
    return value


def _remove_lowest_log_ids(
    log_dir: Path,
    stem: str,
    max_ids: int,
    current_id: int,
    logger: logging.Logger,
) -> list[Path]:
    removed: list[Path] = []
    skipped: set[int] = set()
    while True:
        groups = _iter_log_id_groups(log_dir, stem)
        present = set(groups) | {current_id}
        if len(present) <= max_ids:
            return removed
        candidates = [
            log_id
            for log_id in present
            if log_id != current_id and log_id not in skipped
        ]
        if not candidates:
            return removed
        victim = min(candidates)
        files = groups.get(victim, [])
        removed.extend(_delete_log_files(files, logger))
        if any(file_path.exists() for file_path in files):
            skipped.add(victim)


def _formatter_in_use(logger: logging.Logger) -> logging.Formatter:
    for handler in logger.handlers:
        if isinstance(handler.formatter, logging.Formatter):
            return handler.formatter
    raise RuntimeError("logger sem formatter")


def _file_handler_for(logger: logging.Logger, file_path: Path) -> ConcurrentRotatingFileHandler | None:
    resolved = file_path.resolve()
    for handler in logger.handlers:
        if not isinstance(handler, ConcurrentRotatingFileHandler):
            continue
        if Path(handler.baseFilename).resolve() == resolved:
            return handler
    return None


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
    """Cria um logger cujo arquivo termina em ``-id-{id}.log``.

    Sem ``backup_count``, os backups não são descartados. Com ``max_ids``,
    remove os menores ids do mesmo nome-base até sobrar esse limite, sem
    remover o ``id`` desta chamada.

    Args:
        name: Nome do logger. Se ``None``, usa o logger root.
        id: Identificador positivo do arquivo.
        log_dir: Pasta dos logs. Criada se não existir.
        file_name: Nome-base do arquivo. Se ``None``, usa ``name`` ou ``automation``.
        max_bytes: Tamanho máximo do arquivo ativo antes de rotacionar.
        backup_count: Backups mantidos. ``None`` não descarta backup.
        max_ids: Máximo de ids do mesmo nome-base. ``None`` não remove ids.
        level: Nível aplicado só na primeira configuração desse logger.
        log_format: Formato aplicado só na primeira configuração.
        date_format: Formato de data aplicado só na primeira configuração.

    Returns:
        O logger configurado.
    """
    _require_positive_int(id, "id")
    if max_ids is not None:
        _require_positive_int(max_ids, "max_ids")
    if file_name == "":
        raise ValueError("file_name não pode ser vazio")

    resolved_backup_count = UNLIMITED_BACKUP_COUNT if backup_count is None else backup_count
    resolved_file_name = _resolve_log_file_name(name, file_name, id)
    stem = _log_stem(file_name or name or "automation")

    logger = logging.getLogger(name)
    already_configured = bool(logger.handlers)
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    file_path = log_path / resolved_file_name

    for handler in list(logger.handlers):
        if not isinstance(handler, ConcurrentRotatingFileHandler):
            continue
        if Path(handler.baseFilename).resolve() == file_path.resolve():
            continue
        handler.close()
        logger.removeHandler(handler)

    if not already_configured:
        logger.setLevel(level)
        formatter = logging.Formatter(log_format, datefmt=date_format)
        for handler in _build_console_handlers(formatter):
            logger.addHandler(handler)
    else:
        formatter = _formatter_in_use(logger)

    if max_ids is not None:
        _remove_lowest_log_ids(log_path, stem, max_ids, id, logger)

    if _file_handler_for(logger, file_path) is None:
        logger.addHandler(
            _build_file_handler(file_path, max_bytes, resolved_backup_count, formatter)
        )
    return logger
```

- [ ] **Step 4: Rodar a suíte do logger**

Run: `python -m pytest tests/test_logger.py -v`

Expected: PASS. Se o teste de rotação falhar porque uma linha não passou de 80 bytes, aumentar o preenchimento `"a" * 100` para `"a" * 400` nos dois testes de rotação e rodar de novo. A relação esperada permanece: `FIRST-MARKER` em `.log.2`, `SECOND-MARKER` em `.log.1`, e com `backup_count=1` o `.log.2` não existe.

- [ ] **Step 5: Commit**

```bash
git add tests/test_logger.py src/utils_rpa/logger.py
git commit -m "feat: add configure_logger_by_id"
```

---

### Task 4: Exportar e documentar

**Files:**
- Modify: `src/utils_rpa/logger.py` (`__all__`)
- Modify: `src/utils_rpa/__init__.py`
- Modify: `README.md`
- Test: `tests/test_logger.py`

**Interfaces:**
- Consumes: `cleanup_logs_by_last_update` e `configure_logger_by_id` já definidas
- Produces: as duas funções importáveis de `utils_rpa`

- [ ] **Step 1: Acrescentar o teste de exportação ao final de `tests/test_logger.py`**

```python
def test_logger_by_id_functions_are_exported():
    import utils_rpa
    from utils_rpa.logger import cleanup_logs_by_last_update, configure_logger_by_id

    assert utils_rpa.cleanup_logs_by_last_update is cleanup_logs_by_last_update
    assert utils_rpa.configure_logger_by_id is configure_logger_by_id
```

- [ ] **Step 2: Rodar o teste e confirmar a falha**

Run: `python -m pytest tests/test_logger.py::test_logger_by_id_functions_are_exported -v`

Expected: FAIL com `AttributeError` em `utils_rpa.cleanup_logs_by_last_update`.

- [ ] **Step 3: Exportar e documentar**

Em `src/utils_rpa/logger.py`, `__all__` fica:

```python
__all__ = [
    "configure_logger",
    "configure_logger_by_id",
    "cleanup_old_logs",
    "cleanup_logs_by_last_update",
    "DEFAULT_LOG_DIR",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_BACKUP_COUNT",
    "UNLIMITED_BACKUP_COUNT",
]
```

Em `src/utils_rpa/__init__.py`, trocar o import do logger e incluir os dois nomes em `__all__`, mantendo a ordem atual e inserindo os novos logo após os já existentes do logger:

```python
from utils_rpa.logger import (
    cleanup_logs_by_last_update,
    cleanup_old_logs,
    configure_logger,
    configure_logger_by_id,
)
```

```python
__all__ = [
    "__version__",
    "configure_logger",
    "configure_logger_by_id",
    "cleanup_old_logs",
    "cleanup_logs_by_last_update",
    "retry_with_logging",
    "capture_screen",
    "extract_inputs",
]
```

Em `README.md`, na lista "Ferramentas disponíveis", depois do item de `configure_logger`:

```markdown
- [`configure_logger_by_id`](#configure_logger_by_id) — logger com arquivo por id e limite de ids.
- [`cleanup_logs_by_last_update`](#cleanup_logs_by_last_update) — remove os grupos de id mais antigos.
```

Depois da seção `configure_logger` (depois da dica de `logger.exception`, antes do separador `---`), acrescentar:

```markdown
### `configure_logger_by_id`

Igual ao `configure_logger`, com o id no arquivo: `meu_bot.log` vira `meu_bot-id-123.log`. Sem `backup_count`, o backup não é descartado. Com `max_ids`, os menores ids do mesmo nome-base são removidos; o id desta chamada permanece.

```python
from utils_rpa import configure_logger_by_id

logger = configure_logger_by_id("meu_bot", id=123, max_ids=5)
logger.info("executando 123")

logger = configure_logger_by_id("meu_bot", id=456, max_ids=5)
logger.info("esta linha vai só para meu_bot-id-456.log")
```

Para limitar os backups desse id, passe `backup_count`:

```python
logger = configure_logger_by_id("meu_bot", id=123, backup_count=3)
```

### `cleanup_logs_by_last_update`

Remove grupos `{nome}-id-{número}` até sobrar `keep` ids. A data é a do arquivo base; se ele não existir, a do backup de menor índice. O id em uso não é protegido.

```python
from utils_rpa import cleanup_logs_by_last_update

removidos = cleanup_logs_by_last_update("./logs", "meu_bot", keep=5)
print(f"{len(removidos)} arquivo(s) removido(s).")
```
```

- [ ] **Step 4: Rodar a suíte do logger**

Run: `python -m pytest tests/test_logger.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/utils_rpa/logger.py src/utils_rpa/__init__.py tests/test_logger.py README.md
git commit -m "docs: export and document logger by id"
```
