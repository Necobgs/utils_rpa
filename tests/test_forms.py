from bs4 import BeautifulSoup

from utils_rpa import extract_inputs


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_extracts_named_text_inputs():
    soup = _soup(
        """
        <form>
            <input type="text" name="usuario" value="joao">
            <input type="hidden" name="token" value="abc123">
        </form>
        """
    )
    assert extract_inputs(soup) == {"usuario": "joao", "token": "abc123"}


def test_ignores_inputs_without_name():
    soup = _soup('<input type="text" value="sem-nome">')
    assert extract_inputs(soup) == {}


def test_input_without_value_becomes_empty_string():
    soup = _soup('<input type="text" name="vazio">')
    assert extract_inputs(soup) == {"vazio": ""}


def test_skips_submit_and_button_types():
    soup = _soup(
        """
        <input type="text" name="campo" value="x">
        <input type="submit" name="enviar" value="Enviar">
        <input type="button" name="btn" value="Clique">
        <input type="file" name="arquivo">
        """
    )
    assert extract_inputs(soup) == {"campo": "x"}


def test_radio_only_selected_is_returned():
    soup = _soup(
        """
        <input type="radio" name="cor" value="azul">
        <input type="radio" name="cor" value="verde" checked>
        <input type="radio" name="cor" value="vermelho">
        """
    )
    assert extract_inputs(soup) == {"cor": "verde"}


def test_radio_none_selected_is_omitted():
    soup = _soup(
        """
        <input type="radio" name="cor" value="azul">
        <input type="radio" name="cor" value="verde">
        """
    )
    assert extract_inputs(soup) == {}


def test_checkbox_only_checked_is_returned():
    soup = _soup(
        """
        <input type="checkbox" name="aceito" value="sim" checked>
        <input type="checkbox" name="newsletter" value="1">
        """
    )
    assert extract_inputs(soup) == {"aceito": "sim"}


def test_checkbox_checked_without_value_defaults_to_on():
    soup = _soup('<input type="checkbox" name="flag" checked>')
    assert extract_inputs(soup) == {"flag": "on"}


def test_textarea_uses_inner_text():
    soup = _soup('<textarea name="mensagem">Olá mundo</textarea>')
    assert extract_inputs(soup) == {"mensagem": "Olá mundo"}


def test_select_returns_selected_option_value():
    soup = _soup(
        """
        <select name="estado">
            <option value="SP">São Paulo</option>
            <option value="RJ" selected>Rio de Janeiro</option>
            <option value="MG">Minas Gerais</option>
        </select>
        """
    )
    assert extract_inputs(soup) == {"estado": "RJ"}


def test_select_defaults_to_first_option_when_none_selected():
    soup = _soup(
        """
        <select name="estado">
            <option value="SP">São Paulo</option>
            <option value="RJ">Rio de Janeiro</option>
        </select>
        """
    )
    assert extract_inputs(soup) == {"estado": "SP"}


def test_select_option_without_value_uses_text():
    soup = _soup(
        """
        <select name="opcao">
            <option selected>Primeira</option>
        </select>
        """
    )
    assert extract_inputs(soup) == {"opcao": "Primeira"}


def test_full_form_combination():
    soup = _soup(
        """
        <form>
            <input type="text" name="nome" value="Maria">
            <input type="radio" name="genero" value="F" checked>
            <input type="radio" name="genero" value="M">
            <input type="checkbox" name="termos" value="ok" checked>
            <textarea name="obs">nota</textarea>
            <select name="uf">
                <option value="SP">SP</option>
                <option value="RS" selected>RS</option>
            </select>
            <input type="submit" name="go" value="Ir">
        </form>
        """
    )
    assert extract_inputs(soup) == {
        "nome": "Maria",
        "genero": "F",
        "termos": "ok",
        "obs": "nota",
        "uf": "RS",
    }
