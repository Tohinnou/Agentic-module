"""
Trajectory reader — charge les JSONL de `trajectories/` en list[dict].

Phase 7.1 (§7 CLAUDE.md, Day 4 — Vibe Trajectory analysis).

Contrat : robuste au JSONL corrompu (ligne malformée = skip + warning,
pas crash). Le module `drift.py` consomme les dicts en aval — il n'a
pas à se soucier de la validité JSON ligne par ligne.

Public API :
- `load_trajectory_file(path)` : charge un `.jsonl` unique → list[dict]
- `load_trajectory_dir(path)` : charge un dossier → dict[session_id → list[dict]]
- `group_by_session(events)` : regroupe une liste plate en sessions

Phase 7.0 : stubs. Phase 7.1 implémente.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_trajectory_file(path: Path) -> list[dict[str, Any]]:
    """
    Charge un fichier `.jsonl` de trajectoire en liste de dicts.

    Contrat :
    - Une ligne = un event = un dict après `json.loads`.
    - Ligne malformée (JSON invalide) = skip + warning stderr, PAS crash.
    - Fichier absent = FileNotFoundError (bruyant, pas d'ambiguïté).
    - Fichier vide = liste vide (silencieux).

    Args:
        path: chemin absolu vers le fichier `.jsonl`.

    Returns:
        Liste de dicts (raw events, non validés contre TrajectoryEvent).

    Raises:
        FileNotFoundError: si le fichier n'existe pas.
        NotImplementedError: tant que Phase 7.1 non complétée.
    """
    raise NotImplementedError(
        "Phase 7.1 implémentera load_trajectory_file(). "
        "Phase 7.0 pose le contrat."
    )


def load_trajectory_dir(path: Path) -> dict[str, list[dict[str, Any]]]:
    """
    Charge TOUS les `.jsonl` d'un dossier, regroupés par `session_id`.

    Contrat :
    - Scanne récursivement `path/*.jsonl`.
    - Chaque event est regroupé par sa clé `session_id`.
    - Sessions partagent l'ordre d'apparition dans les fichiers
      (pas de tri par timestamp — c'est la responsabilité du caller).
    - Dossier absent = FileNotFoundError.
    - Dossier vide de `.jsonl` = dict vide.

    Args:
        path: chemin vers le dossier (typiquement `trajectories/`).

    Returns:
        Dict `session_id → list[dict]`.

    Raises:
        FileNotFoundError: si le dossier n'existe pas.
        NotImplementedError: tant que Phase 7.1 non complétée.
    """
    raise NotImplementedError(
        "Phase 7.1 implémentera load_trajectory_dir(). "
        "Phase 7.0 pose le contrat."
    )


def group_by_session(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """
    Regroupe une liste plate d'events par `session_id`.

    Contrat :
    - Ordre préservé au sein d'une session (ordre d'apparition).
    - Event sans `session_id` → skip + warning stderr.
    - Idempotent : rejouer sur le résultat regroupé re-produit le même dict.

    Args:
        events: liste plate d'events.

    Returns:
        Dict `session_id → list[dict]`.

    Raises:
        NotImplementedError: tant que Phase 7.1 non complétée.
    """
    raise NotImplementedError(
        "Phase 7.1 implémentera group_by_session(). "
        "Phase 7.0 pose le contrat."
    )


__all__ = ["load_trajectory_file", "load_trajectory_dir", "group_by_session"]
