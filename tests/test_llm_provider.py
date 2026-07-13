"""Contrat du LLMProvider (Phase 8.3, module #1).

Le mock existe pour rendre le harness d'éval REJOUABLE offline (garde pass^k +
plomberie), PAS pour juger. Ces tests verrouillent : (1) la résolution du
provider via LLM_PROVIDER, (2) le mock renvoie une sortie VALIDE + DÉTERMINISTE
sans réseau, (3) OpenRouterProvider fail-hard sans clé — le réseau est un opt-in
explicite, jamais un défaut silencieux.
"""

import json

import pytest

from sandbox.evaluation.judge import DIMENSIONS
from sandbox.evaluation.judge import SYSTEM_PROMPT as JUDGE_SYSTEM_PROMPT
from sandbox.llm import (
    MockLLMProvider,
    OpenRouterProvider,
    get_provider,
)


# ─── Résolution du provider ───────────────────────────────────────
def test_get_provider_defaults_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Défaut = mock (contrat de stack CLAUDE.md §2, offline-first)."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(get_provider(), MockLLMProvider)


def test_get_provider_honors_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    assert isinstance(get_provider(), OpenRouterProvider)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert isinstance(get_provider(), MockLLMProvider)


def test_get_provider_explicit_arg_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    assert isinstance(get_provider("mock"), MockLLMProvider)


def test_get_provider_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with pytest.raises(ValueError):
        get_provider("gpt-9-turbo")


# ─── MockLLMProvider : valide, déterministe, offline ──────────────
def test_mock_judge_output_is_valid_and_in_range() -> None:
    raw = MockLLMProvider().complete(JUDGE_SYSTEM_PROMPT, '{"draft_reply": "ok"}')
    scores = json.loads(raw)
    for dim in DIMENSIONS:
        assert isinstance(scores[dim], int) and 0 <= scores[dim] <= 5
    assert "reasoning" in scores


def test_mock_is_deterministic() -> None:
    """Même (system, user) → sortie identique : garde pass^k = 1.0 par construction."""
    mock = MockLLMProvider()
    assert mock.complete(JUDGE_SYSTEM_PROMPT, "meme-input") == mock.complete(
        JUDGE_SYSTEM_PROMPT, "meme-input"
    )


def test_mock_is_not_trivially_constant() -> None:
    """La garde pass^k n'est pas un no-op : des entrées ≠ produisent des sorties ≠."""
    mock = MockLLMProvider()
    outputs = {mock.complete(JUDGE_SYSTEM_PROMPT, f"input-{i}") for i in range(8)}
    assert len(outputs) > 1


def test_mock_needs_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le mock est offline : aucune clé lue, aucun réseau."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    raw = MockLLMProvider().complete(JUDGE_SYSTEM_PROMPT, "{}")
    assert json.loads(raw)  # parse OK, aucune exception clé/réseau


# ─── OpenRouterProvider : fail-hard sans clé (opt-in réseau) ──────
def test_openrouter_provider_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        OpenRouterProvider().complete("system", "user")
