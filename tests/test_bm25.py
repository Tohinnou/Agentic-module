"""Unit tests pour le stemmer FR léger de BM25 (Phase 8.1).

Le stemming fait converger verbe et nom vers une racine commune pour que BM25
(exact-token) matche 'annuler' (requête) avec 'annulation' (doc). Ces tests
verrouillent le contrat : (1) convergence des familles morphologiques,
(2) convergence singulier/pluriel, (3) garde anti-sur-racinisation, (4) que
`tokenize` reste NON stemmé — le classifier (`classification/rules.py`) l'importe
pour matcher des mots-clés non racinisés, stemmer là le casserait.
"""

import pytest

from sandbox.retrieval.bm25 import stem, tokenize


@pytest.mark.parametrize(
    "word,expected",
    [
        ("annuler", "annul"),
        ("annulation", "annul"),
        ("annulée", "annul"),
        ("annulations", "annul"),
        ("rembourser", "rembours"),
        ("remboursement", "rembours"),
        ("remboursé", "rembours"),
    ],
)
def test_stem_converges_morphological_family(word: str, expected: str) -> None:
    assert stem(word) == expected


def test_stem_converges_singular_and_plural() -> None:
    """orage/orages doivent converger, sinon BM25 rate le match météo."""
    assert stem("orage") == stem("orages")
    assert stem("réservation") == stem("réservations")


def test_stem_preserves_short_tokens() -> None:
    """Garde >= 3 chars de racine : pas de sur-racinisation destructrice."""
    assert stem("eau") == "eau"
    assert stem("48h") == "48h"


def test_tokenize_stays_unstemmed() -> None:
    """tokenize ne doit JAMAIS stemmer : le classifier matche des mots-clés bruts."""
    assert tokenize("annulation gratuite") == ["annulation", "gratuite"]
