"""Canary / Shadow — comparer ANCIEN vs NOUVEAU avant promotion (Phase 8, pattern 5).

Quand on modifie un composant (skill, retrieval, prompt), on ne le promeut pas à
l'aveugle : on fait tourner l'ANCIEN et le NOUVEAU en parallèle (shadow, sans impact
réel) sur le trafic d'éval, on compare, et on ne promeut QUE si zéro régression.

Générique (cf. passk, trigger_accuracy, shadow) : le harness ignore CE qu'il compare.
On lui passe `old_fn(x)->y`, `new_fn(x)->y`, et — pour juger les divergences — un
`golden_fn(x)->y_attendu`. Testable offline avec des stand-ins ; démo réelle sur le
changement BM25 stemming de 8.1. Déterministe, aucun LLM.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

Fn = Callable[[Any], Any]


@dataclass(frozen=True)
class Divergence:
    """Un input où old et new diffèrent, classé par rapport au golden."""

    item: Any
    old: Any
    new: Any
    verdict: str  # "improvement" | "regression" | "neutral"


@dataclass(frozen=True)
class ShadowReport:
    n: int
    agreements: int
    divergences: list[Divergence]

    @property
    def agreement_rate(self) -> float:
        return self.agreements / self.n if self.n else 0.0

    @property
    def improvements(self) -> list[Divergence]:
        return [d for d in self.divergences if d.verdict == "improvement"]

    @property
    def regressions(self) -> list[Divergence]:
        return [d for d in self.divergences if d.verdict == "regression"]

    @property
    def neutrals(self) -> list[Divergence]:
        return [d for d in self.divergences if d.verdict == "neutral"]


def shadow_run(
    old_fn: Fn,
    new_fn: Fn,
    inputs: Sequence[Any],
    golden_fn: Fn | None = None,
) -> ShadowReport:
    """Fait tourner old ET new sur chaque input, classe les divergences via golden_fn.

    `golden_fn(x)` donne la sortie ATTENDUE. Une divergence (old != new) est :
    - improvement : new == golden != old  (le nouveau CORRIGE)
    - regression  : old == golden != new  (le nouveau CASSE)
    - neutral     : ni l'un ni l'autre n'égale le golden, ou pas de golden fourni
    """
    agreements = 0
    divergences: list[Divergence] = []
    for x in inputs:
        old, new = old_fn(x), new_fn(x)
        if old == new:
            agreements += 1
            continue
        verdict = "neutral"
        if golden_fn is not None:
            g = golden_fn(x)
            if new == g and old != g:
                verdict = "improvement"
            elif old == g and new != g:
                verdict = "regression"
        divergences.append(Divergence(item=x, old=old, new=new, verdict=verdict))
    return ShadowReport(n=len(inputs), agreements=agreements, divergences=divergences)


def promotion_verdict(report: ShadowReport) -> str:
    """Décision de promotion : PROMOTE ssi zéro régression, sinon HOLD.

    Politique conservatrice = le sens même du canary : UNE seule régression bloque la
    promotion, même s'il y a des improvements par ailleurs. On ne troque pas une
    régression contre un gain — on corrige d'abord, on promeut ensuite.
    """
    return "HOLD" if report.regressions else "PROMOTE"
