import utils_rpa


def test_version_is_defined():
    assert isinstance(utils_rpa.__version__, str)
    assert utils_rpa.__version__ != ""


def test_package_is_importable():
    assert utils_rpa is not None
