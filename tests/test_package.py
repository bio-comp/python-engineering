"""Executable package identity and import contracts."""

from importlib.metadata import version
from importlib.resources import files


def test_distribution_and_importable_package() -> None:
    assert version("python-engineering-lab") == "0.1.0"
    assert files("python_engineering").joinpath("__init__.py").is_file()
