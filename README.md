# utils_rpa

Conjunto de utilitários e configurações para facilitar o desenvolvimento de **RPA (Robotic Process Automation)** com Python.

## Instalação

```bash
pip install utils-rpa
```

Alguns recursos dependem de bibliotecas extras (Selenium/Playwright). Instale conforme o que for usar:

```bash
pip install "utils-rpa[selenium]"     # resolução de captcha via Selenium
pip install "utils-rpa[playwright]"   # resolução de captcha via Playwright
pip install "utils-rpa[all]"          # todos os extras
```

## Requisitos

- Python >= 3.12

## Ferramentas disponíveis

- [`configure_logger`](#configure_logger) — logger pronto (console + arquivo rotativo).
- [`retry_with_logging`](#retry_with_logging) — decorator de retentativa com logging.
- [`capture_screen`](#capture_screen) — screenshot da tela inteira do computador.
- [`extract_inputs`](#extract_inputs) — extrai os campos de um formulário HTML.
- [`anti_captcha`](#anti_captcha) — resolução de Cloudflare Turnstile e captcha de imagem.

---

### `configure_logger`

Cria um logger que escreve no **console** e em um **arquivo rotativo** (via `concurrent-log-handler`, seguro para múltiplos processos/threads). Por padrão salva em `./logs`, com arquivos de até 5 MB e 3 backups.

```python
from utils_rpa import configure_logger

logger = configure_logger("meu_bot")

logger.info("Iniciando automação")
logger.warning("Algo suspeito aconteceu")
logger.error("Falha ao processar item")
```

Personalizando os parâmetros:

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

Saída (formato padrão, sem milissegundos):

```
2026-07-02 14:04:14 | INFO     | Iniciando automação
```

> Dica: use `logger.exception("...")` **dentro de um bloco `except`** para registrar o traceback automaticamente.

---

### `retry_with_logging`

Decorator que reexecuta a função quando ela lança uma exceção, registrando cada tentativa no logger. Defaults: 5 tentativas, 1 segundo entre elas, logging ativado.

```python
from utils_rpa import retry_with_logging

@retry_with_logging("meu_bot", attempts=3, delay=2)
def baixar_relatorio():
    # ... código que pode falhar (rede, elemento não carregado, etc.)
    return http_get("https://exemplo/relatorio")

# Tenta até 3 vezes, aguardando 2s entre as falhas.
# Se todas falharem, a última exceção é propagada.
relatorio = baixar_relatorio()
```

Sem logging:

```python
@retry_with_logging(attempts=5, delay=1, use_log=False)
def tarefa_silenciosa():
    ...
```

---

### `capture_screen`

Tira um print da **tela inteira** do computador (todos os monitores por padrão), salvando um PNG. Como captura a tela toda, o print inclui qualquer navegador aberto.

```python
from utils_rpa import capture_screen

# Salva em ./screenshots com nome por timestamp e retorna o caminho
caminho = capture_screen()
print(caminho)  # ex.: screenshots/screenshot_20260702_140414_123456.png

# Definindo o arquivo de saída
capture_screen("prints/tela.png")

# Capturando apenas o monitor principal (1 = principal, 2 = segundo, ...)
capture_screen(monitor=1)
```

---

### `extract_inputs`

Recebe um objeto **BeautifulSoup** e extrai os campos do formulário como se ele fosse submetido, retornando um dicionário `{name: value}`. Aplica a lógica de um navegador: `input`/`textarea`/`select` com `name`, radios e checkboxes apenas quando marcados, e a `option` selecionada nos `select`.

```python
from bs4 import BeautifulSoup
from utils_rpa import extract_inputs

html = """
<form>
    <input type="text" name="usuario" value="maria">
    <input type="hidden" name="token" value="abc123">
    <input type="radio" name="genero" value="F" checked>
    <input type="radio" name="genero" value="M">
    <input type="checkbox" name="termos" value="ok" checked>
    <textarea name="observacao">alguma nota</textarea>
    <select name="estado">
        <option value="SP">São Paulo</option>
        <option value="RJ" selected>Rio de Janeiro</option>
    </select>
    <input type="submit" name="enviar" value="Enviar">
</form>
"""

soup = BeautifulSoup(html, "html.parser")
dados = extract_inputs(soup)

# {
#     "usuario": "maria",
#     "token": "abc123",
#     "genero": "F",            # apenas o radio marcado
#     "termos": "true",         # checkbox marcado
#     "observacao": "alguma nota",
#     "estado": "RJ",         # option selecionada
# }                           # o input submit é ignorado
```

Útil para reenviar formulários mantendo os campos ocultos/pré-preenchidos (ex.: tokens CSRF, `viewstate`) ao automatizar requisições.

---

### `anti_captcha`

Estratégias para resolver o **Cloudflare Turnstile** e captchas de imagem, usando o serviço [Anti-Captcha](https://anti-captcha.com/). A chave da API pode ser passada por parâmetro (`api_key`) ou pela variável de ambiente `ANTICAPTCHA_KEY`.

Todos os parâmetros (XPaths, timeouts, etc.) têm defaults e podem ser sobrescritos.

**Com Selenium** (`pip install "utils-rpa[selenium]"`):

```python
from utils_rpa.anti_captcha import cloudflare_solver_selenium

resolvido = cloudflare_solver_selenium(
    driver,                       # WebDriver já na página do desafio
    api_key="SUA_CHAVE",          # ou via ANTICAPTCHA_KEY
    xpath_success='//input[@id="senha"]',   # elemento que confirma o sucesso
)

if not resolvido:
    ...  # reiniciar o fluxo
```

**Com Playwright** (`pip install "utils-rpa[playwright]"`):

```python
from utils_rpa.anti_captcha import cloudflare_solver_playwright

resolvido = cloudflare_solver_playwright(
    page,                         # Page do Playwright (sync API)
    api_key="SUA_CHAVE",
)
```

**Captcha de imagem (ImageToText)** — função assíncrona:

```python
import asyncio
from utils_rpa.anti_captcha import image_to_text

async def main():
    texto = await image_to_text(api_key="SUA_CHAVE", base64_image="iVBORw0KGgo...")
    print(texto)

asyncio.run(main())
```

---

## Desenvolvimento

Clone o repositório e instale as dependências (incluindo as de desenvolvimento):

```bash
poetry install
```

Rodar os testes:

```bash
poetry run pytest
```

Rodar o linter:

```bash
poetry run ruff check .
```

Gerar o build do pacote:

```bash
poetry build
```

## Licença

Distribuído sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
