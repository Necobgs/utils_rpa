import utils_rpa


def test_version_esta_definida():
    assert isinstance(utils_rpa.__version__, str)
    assert utils_rpa.__version__ != ""


def test_pacote_importavel():
    assert utils_rpa is not None
