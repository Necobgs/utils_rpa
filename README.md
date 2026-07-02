# utils_rpa

Conjunto de utilitários e configurações para facilitar o desenvolvimento de **RPA (Robotic Process Automation)** com Python.

> **Status:** em desenvolvimento inicial. A estrutura do pacote está pronta, mas as funcionalidades ainda serão implementadas.

## Instalação

```bash
pip install utils-rpa
```

Ou, para desenvolvimento com [Poetry](https://python-poetry.org/):

```bash
poetry install
```

## Requisitos

- Python >= 3.14

## Uso

```python
import utils_rpa

print(utils_rpa.__version__)
```

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
