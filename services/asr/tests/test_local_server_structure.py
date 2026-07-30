"""Structure de `local_server.py`, vérifiée sans l'importer.

Ce fichier ne s'importe pas en test : il tire `torch`, `transformers` et
`omnilingual_asr`, absents de l'environnement de CI. On l'analyse donc au
niveau syntaxique — ce qui suffit pour attraper la seule classe d'erreur qui
échappe à tout le reste.

**Pourquoi ce test existe.** Un refactoring a déjà déplacé
`_omnilingual_logits` au milieu du corps de `LocalAsr`, ce qui a rendu
`transcribe` méthode imbriquée dans cette fonction au lieu de méthode de la
classe. Le fichier restait syntaxiquement valide — `py_compile` passait — et
aucun test existant ne charge ce module : le défaut n'est apparu qu'au
redémarrage du service en production, où *toutes* les transcriptions
échouaient.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVER = Path(__file__).resolve().parents[1] / "local_server.py"


@pytest.fixture(scope="module")
def module_tree() -> ast.Module:
    return ast.parse(_SERVER.read_text(encoding="utf-8"))


def _classe(tree: ast.Module, nom: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == nom:
            return node
    raise AssertionError(f"classe {nom} absente du module")


@pytest.mark.parametrize(
    "methode", ["__init__", "transcribe", "model_name", "_logits", "_detect_separator"]
)
def test_local_asr_expose_ses_methodes(module_tree: ast.Module, methode: str) -> None:
    """`transcribe` est le point d'entrée HTTP : l'imbriquer ailleurs casse tout."""
    methodes = {
        n.name for n in _classe(module_tree, "LocalAsr").body if isinstance(n, ast.FunctionDef)
    }
    assert methode in methodes


@pytest.mark.parametrize("nom", ["Wav2Vec2Backend", "OmnilingualBackend"])
def test_les_deux_backends_ont_le_meme_contrat(module_tree: ast.Module, nom: str) -> None:
    """Les deux modèles sont interchangeables : `LocalAsr` n'appelle qu'eux."""
    methodes = {
        n.name for n in _classe(module_tree, nom).body if isinstance(n, ast.FunctionDef)
    }
    assert {"encode", "logits"} <= methodes


def test_omnilingual_logits_reste_au_niveau_module(module_tree: ast.Module) -> None:
    """Seul endroit du projet dépendant de l'API interne d'`omnilingual_asr` :
    il doit rester isolé et repérable, pas noyé dans une classe."""
    fonctions = {n.name for n in module_tree.body if isinstance(n, ast.FunctionDef)}
    assert "_omnilingual_logits" in fonctions
