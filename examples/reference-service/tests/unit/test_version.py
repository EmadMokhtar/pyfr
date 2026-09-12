import reference_service


def test_package_exposes_a_version() -> None:
    assert isinstance(reference_service.__version__, str)
    assert reference_service.__version__ != ""
