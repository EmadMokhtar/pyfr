import {{ cookiecutter.package_name }}


def test_package_exposes_a_version() -> None:
    assert isinstance({{ cookiecutter.package_name }}.__version__, str)
    assert {{ cookiecutter.package_name }}.__version__ != ""
