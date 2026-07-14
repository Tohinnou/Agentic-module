"""Types partagés du teaming Red/Blue/Green (Phase 10). Aucune dépendance interne."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    """Une action que l'agent tenterait — le SUJET que Blue inspecte."""

    kind: str  # read_file | install_package | modify | draft | retrieve | ...
    target: str = ""  # fichier, package, chemin...
    content: str = ""  # texte (pour un draft)
    call_count: int = 1  # appels cumulés (détection des boucles)


@dataclass(frozen=True)
class AttackCase:
    """Un cas Red : l'attaque + le signal Blue attendu + la réponse Green attendue."""

    id: str
    prompt: str
    action: Action
    vector: str
    expected_signal: str | None
    expected_response: str


@dataclass(frozen=True)
class Disposition:
    """Verdict de quarantaine : signal Blue, réponse Green, action isolée ou non."""

    signal: str | None
    response: str
    quarantined: bool
