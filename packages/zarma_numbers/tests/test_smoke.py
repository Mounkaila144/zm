"""Test smoke minimal (story 1.1) : le paquet s'importe et expose sa version."""

import zarma_numbers


def test_package_importable():
    assert zarma_numbers is not None


def test_version_exposed():
    assert zarma_numbers.__version__ == "0.1.0"
