"""Extração de campos de formulário a partir de HTML (BeautifulSoup)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, Tag

# Tipos de ``input`` que não são enviados numa submissão comum de formulário.
_SKIPPED_INPUT_TYPES = frozenset({"submit", "button", "reset", "image", "file"})

# Tipos de ``input`` que só são enviados quando marcados (checked).
_TOGGLE_INPUT_TYPES = frozenset({"radio", "checkbox"})

__all__ = ["extract_inputs"]


def extract_inputs(soup: BeautifulSoup | Tag) -> dict[str, str]:
    """Extrai os campos de um formulário como se ele fosse submetido.

    Percorre o objeto BeautifulSoup e monta um dicionário ``name: value``,
    seguindo o comportamento de um navegador ao enviar o formulário:

    - ``input`` com atributo ``name``: usa o ``value`` (vazio se ausente).
      Tipos ``submit``, ``button``, ``reset``, ``image`` e ``file`` são
      ignorados.
    - ``input`` do tipo ``radio``/``checkbox``: só é incluído se estiver
      marcado (``checked``); usa o ``value`` (ou ``"on"`` se ausente).
    - ``textarea`` com ``name``: usa o texto interno.
    - ``select`` com ``name``: usa o ``value`` da ``option`` selecionada
      (ou, na ausência de seleção, a primeira ``option``). Se a opção não
      tiver ``value``, usa o texto dela.

    Campos sem atributo ``name`` são ignorados.

    Args:
        soup: Objeto BeautifulSoup (ou Tag, como um ``<form>`` específico).

    Returns:
        Dicionário ``{name: value}`` com os campos do formulário.
    """
    data: dict[str, str] = {}

    # ── inputs ────────────────────────────────────────────────────────────────
    for input_tag in soup.find_all("input"):
        name = input_tag.get("name")
        if not name:
            continue

        input_type = (input_tag.get("type") or "text").lower()

        if input_type in _SKIPPED_INPUT_TYPES:
            continue

        if input_type in _TOGGLE_INPUT_TYPES:
            # Só entra na submissão se estiver marcado.
            if input_tag.has_attr("checked"):
                data[name] = input_tag.get("value", "true")
            continue

        data[name] = input_tag.get("value", "")

    # ── textareas ───────────────────────────────────────────────────────────
    for textarea in soup.find_all("textarea"):
        name = textarea.get("name")
        if not name:
            continue
        data[name] = textarea.get_text()

    # ── selects ─────────────────────────────────────────────────────────────
    for select in soup.find_all("select"):
        name = select.get("name")
        if not name:
            continue

        options = select.find_all("option")
        if not options:
            continue

        selected = [opt for opt in options if opt.has_attr("selected")]
        chosen = selected[0] if selected else options[0]

        value = chosen.get("value")
        if value is None:
            value = chosen.get_text(strip=True)
        data[name] = value

    return data
