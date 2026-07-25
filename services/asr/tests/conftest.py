"""Fixtures des tests du service ASR (CI sans GPU, sans réseau).

``services/asr/app`` porte le même nom de paquet que ``services/api/app``
(déjà sur le ``pythonpath`` pytest). On charge donc le paquet **par chemin**
sous un alias unique (``zarma_asr_app``) : les imports relatifs internes
(``from .decoding import …``) continuent de fonctionner, sans jamais entrer en
collision avec le paquet ``app`` de l'API.

Seuls les modules **sans torch ni modal** sont chargés ici : ``decoding``,
``transcription``, ``config``. ``main.py`` (runtime Modal/GPU) n'est jamais
importé par la CI.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
_PACKAGE = "zarma_asr_app"


def _load_package() -> None:
    """Enregistre ``services/asr/app`` sous l'alias ``zarma_asr_app``."""
    if _PACKAGE in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        _PACKAGE,
        _APP_DIR / "__init__.py",
        submodule_search_locations=[str(_APP_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PACKAGE] = module
    spec.loader.exec_module(module)


def _submodule(name: str):
    _load_package()
    return importlib.import_module(f"{_PACKAGE}.{name}")


@pytest.fixture(scope="session")
def decoding():
    """Module ``services/asr/app/decoding.py`` — décodeur CTC contraint."""
    return _submodule("decoding")


@pytest.fixture(scope="session")
def transcription():
    """Module ``services/asr/app/transcription.py`` — pont vers ``/transcribe``."""
    return _submodule("transcription")


@pytest.fixture(scope="session")
def asr_config():
    """Module ``services/asr/app/config.py`` — ``AsrSettings``."""
    return _submodule("config")
