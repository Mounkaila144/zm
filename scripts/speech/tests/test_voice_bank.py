"""Tests de la restitution vocale par concaténation (story 6.1, task 6).

Aucun enregistrement réel n'est nécessaire : la banque est faite de WAV
canoniques synthétiques écrits dans ``tmp_path``. Ce qui est prouvé ici est la
logique — et surtout le **fail-closed**, qui est la propriété de sûreté de cette
task : un utilisateur qui ne lit pas ne peut pas détecter un énoncé tronqué,
donc un mot manquant doit produire *rien du tout*, jamais un résultat partiel.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from voice_bank import (
    PROMPT,
    PROMPT_CANNOT_ANSWER,
    PROMPT_CONFIRM,
    TARGET_RATE,
    VoiceBank,
    VoiceBankError,
    build_bank,
    confirmation_utterance,
    duration_seconds,
    expression_utterance,
    missing_prompts,
    missing_vocabulary,
    number_coverage,
    number_utterance,
    read_pcm,
    refusal_utterance,
    result_utterance,
    synthesize,
    target_vocabulary,
    write_wav,
)
from zarma_numbers.expressions import Expression, evaluate, render_result
from zarma_numbers.generator import generate

#: Durée d'un mot factice — assez pour distinguer les concaténations.
_WORD_SECONDS = 0.1


def _write_tone(path: Path, seconds: float = _WORD_SECONDS) -> None:
    """Écrit un WAV canonique (mono 16 kHz PCM16) rempli de silence."""
    write_wav(path, b"\x00" * (int(seconds * TARGET_RATE) * 2))


def _bank_covering(tmp_path: Path, words, prompts=()) -> VoiceBank:
    word_dir = tmp_path / "words"
    word_dir.mkdir(exist_ok=True)
    for word in words:
        _write_tone(word_dir / f"{word}.wav")
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir(exist_ok=True)
    for name in prompts:
        _write_tone(prompt_dir / f"{name}.wav")
    return build_bank("vtest", sources=(), word_dir=word_dir, prompt_dir=prompt_dir)


# --------------------------------------------------------------------------- #
# Ce qui est prononcé vient de zarma_numbers, jamais réécrit
# --------------------------------------------------------------------------- #


def test_number_utterance_follows_the_generator():
    assert number_utterance(38) == tuple(("word", w) for w in generate(38).split())


def test_result_utterance_says_the_division_remainder():
    """« 20 reste 3 » doit être dit, marqueur `ga cindi` compris."""
    result = evaluate(Expression(103, "/", 5))
    assert render_result(result) == "waranka ga cindi hinza"
    assert result_utterance(result) == (
        ("word", "waranka"),
        ("word", "ga"),
        ("word", "cindi"),
        ("word", "hinza"),
    )


def test_expression_utterance_replays_the_operation():
    words = [segment[1] for segment in expression_utterance(Expression(23, "+", 15))]
    assert "tonton" in words


def test_the_remainder_marker_is_part_of_the_target_vocabulary():
    """Sans `ga`, aucun résultat de division non entière n'est prononçable."""
    assert "ga" in target_vocabulary()


def test_resolved_operators_are_part_of_the_target_vocabulary():
    """Sans les mots d'opérateur, l'app ne peut pas relire l'opération entendue.

    Or la relecture *est* la confirmation, c'est-à-dire le chemin nominal : les
    oublier rendrait la liste d'enregistrement silencieusement incomplète.
    """
    from zarma_numbers.loader import load_lexicon

    vocabulary = target_vocabulary()
    for operator in load_lexicon().operators.values():
        if operator.canonical is None:
            assert operator.canonical not in vocabulary
        else:
            assert set(operator.canonical.split()) <= vocabulary


def test_an_expression_is_sayable_with_the_target_vocabulary(tmp_path):
    bank = _bank_covering(tmp_path, target_vocabulary())
    assert bank.can_say(expression_utterance(Expression(23, "+", 15)))


def test_target_vocabulary_stays_a_closed_set():
    """L'argument central de D3 : ~33 mots suffisent pour 1 000 001 nombres."""
    assert len(target_vocabulary()) <= 40


# --------------------------------------------------------------------------- #
# Fail-closed : rien plutôt qu'un énoncé tronqué (FR21)
# --------------------------------------------------------------------------- #


def test_missing_word_produces_nothing_at_all(tmp_path):
    form = generate(38)
    incomplete = form.split()[:-1]  # il manque le dernier mot
    bank = _bank_covering(tmp_path, incomplete)

    with pytest.raises(VoiceBankError, match="absents"):
        synthesize(number_utterance(38), bank)


def test_missing_prompt_blocks_the_whole_confirmation(tmp_path):
    """La consigne manque : on ne prononce pas le nombre seul, qui serait ambigu."""
    bank = _bank_covering(tmp_path, generate(42).split())
    utterance = confirmation_utterance(number_utterance(42))

    with pytest.raises(VoiceBankError):
        synthesize(utterance, bank)


def test_empty_utterance_is_refused(tmp_path):
    with pytest.raises(VoiceBankError, match="vide"):
        synthesize((), _bank_covering(tmp_path, []))


def test_missing_reports_each_absent_segment_once(tmp_path):
    bank = _bank_covering(tmp_path, [])
    utterance = (("word", "waranka"), ("word", "waranka"), (PROMPT, PROMPT_CONFIRM))
    assert bank.missing(utterance) == [("word", "waranka"), (PROMPT, PROMPT_CONFIRM)]


def test_non_canonical_audio_is_refused(tmp_path):
    """Un WAV au mauvais format est rejeté, jamais rééchantillonné en silence."""
    path = tmp_path / "bad.wav"
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(44_100)
        writer.writeframes(b"\x00" * 400)

    with pytest.raises(VoiceBankError, match="format non canonique"):
        read_pcm(path)


# --------------------------------------------------------------------------- #
# Assemblage
# --------------------------------------------------------------------------- #


def test_complete_bank_produces_audio(tmp_path):
    bank = _bank_covering(tmp_path, generate(38).split())
    pcm = synthesize(number_utterance(38), bank)
    assert duration_seconds(pcm) > 0


def test_audio_grows_with_the_number_of_words(tmp_path):
    words = set(generate(38).split()) | set(generate(5).split())
    bank = _bank_covering(tmp_path, words)

    short = synthesize(number_utterance(5), bank)
    long = synthesize(number_utterance(38), bank)
    assert duration_seconds(long) > duration_seconds(short)


def test_confirmation_puts_the_prompt_first(tmp_path):
    bank = _bank_covering(tmp_path, generate(42).split(), prompts=[PROMPT_CONFIRM])
    utterance = confirmation_utterance(number_utterance(42))

    assert utterance[0] == (PROMPT, PROMPT_CONFIRM)
    assert synthesize(utterance, bank)


def test_refusal_is_audible(tmp_path):
    """Un refus doit s'entendre : le silence serait pris pour une panne (AC4)."""
    bank = _bank_covering(tmp_path, [], prompts=[PROMPT_CANNOT_ANSWER])
    assert synthesize(refusal_utterance(), bank)


def test_synthesize_works_offline(tmp_path, monkeypatch):
    """Contrainte terrain : aucun accès réseau pendant la restitution."""
    import socket

    def forbidden(*_args, **_kwargs):
        raise AssertionError("la restitution vocale ne doit jamais toucher le réseau")

    monkeypatch.setattr(socket, "socket", forbidden)
    bank = _bank_covering(tmp_path, generate(38).split())
    assert synthesize(number_utterance(38), bank)


# --------------------------------------------------------------------------- #
# Couverture : ce qu'il reste à faire enregistrer
# --------------------------------------------------------------------------- #


def test_coverage_reports_the_gap_honestly(tmp_path):
    bank = _bank_covering(tmp_path, [])
    ok, total = number_coverage(bank, upper=20)
    assert (ok, total) == (0, 21)


def test_full_bank_covers_every_number_up_to_1000(tmp_path):
    bank = _bank_covering(tmp_path, target_vocabulary())
    ok, total = number_coverage(bank)
    assert ok == total == 1001


def test_missing_lists_are_actionable(tmp_path):
    bank = _bank_covering(tmp_path, ["waranka"], prompts=[PROMPT_CONFIRM])
    assert "waranka" not in missing_vocabulary(bank)
    assert missing_prompts(bank) == [PROMPT_CANNOT_ANSWER]
