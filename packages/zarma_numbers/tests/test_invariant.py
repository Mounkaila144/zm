"""Invariant exhaustif ``parse(normalize(generate(n))) == n`` (stories 1.6 + 1.7).

Depuis la story 1.7 (marqueur ``dala`` + forme ``million``), l'invariant est
**garanti sur toute la plage `0`–`1 000 000`**. En CI, `pytest` enforce une
couverture chunkée représentative (rapide) + les cas de désambiguïsation clés,
et la preuve **exhaustive complète** est exécutée par ``make invariant`` (étape
CI dédiée). Toute violation fait échouer la CI (AC5).
"""

import pytest
from zarma_numbers.generator import MAX_VALUE, generate
from zarma_numbers.normalizer import normalize
from zarma_numbers.parser import parse
from zarma_numbers.validator import validate_invariant

_CHUNK = 10_000
# Plage enforcée en pytest (rapide) : bas + haut (exerce `dala`). La preuve
# exhaustive 0..1 000 000 est faite par `make invariant`.
_PYTEST_RANGES = [(0, 99_999), (100_000, 199_999), (900_000, 999_999)]


@pytest.mark.parametrize(
    "chunk_start",
    [s for lo, hi in _PYTEST_RANGES for s in range(lo, hi + 1, _CHUNK)],
)
def test_invariant_holds_chunk(chunk_start):
    report = validate_invariant(chunk_start, chunk_start + _CHUNK - 1)
    assert not report.has_violations, report.summary()
    assert report.ambiguous == []
    assert report.unresolved == []


def test_boundaries_and_million():
    for n in (0, 999, 1_000, 99_999, 100_000, 999_999, 1_000_000, MAX_VALUE):
        assert parse(normalize(generate(n))) == n
    assert generate(1_000_000) == "million"


# --- Extension million (au-delà de 1 000 000, même mécanisme que `zambar`) ---
# Pas de preuve exhaustive possible ici (~10^11 valeurs) : échantillonnage
# ciblé + aléatoire, cf. RESOLVED_MAX dans validator.py.


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (100_000_005, 105_000_000),
        (1_000_000_005, 1_005_000_000),
        (900_099_000, 999_000_000),
    ],
)
def test_million_dala_pairs_no_longer_collide(a, b):
    assert generate(a) != generate(b)
    assert parse(normalize(generate(a))) == a
    assert parse(normalize(generate(b))) == b


def test_million_scale_random_sample_roundtrips():
    import random

    rng = random.Random(20260726)
    for _ in range(5000):
        n = rng.randint(1_000_001, MAX_VALUE)
        assert parse(normalize(generate(n))) == n


# --- Story 1.7 : désambiguïsation `dala` (paires qui collisionnaient avant) ---


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (100_005, 105_000),
        (100_015, 115_000),
        (200_005, 205_000),
        (900_099, 999_000),
    ],
)
def test_dala_pairs_no_longer_collide(a, b):
    assert generate(a) != generate(b)
    assert parse(normalize(generate(a))) == a
    assert parse(normalize(generate(b))) == b


def test_full_range_report_has_no_violations_on_sample():
    # Vérifie le mécanisme de rapport sur une plage haute dense (dala partout).
    report = validate_invariant(100_000, 101_000)
    assert not report.has_violations
    assert report.unresolved == []
    assert report.ambiguous == []
