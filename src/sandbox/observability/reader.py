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
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load_trajectory_file(path: Path) -> list[dict[str, Any]]:
    """
    Charge un fichier `.jsonl` de trajectoire en liste de dicts.

    Contrat :
    - Une ligne = un event = un dict après `json.loads`.
    - Ligne malformée (JSON invalide, ligne blanche, non-dict) = skip
      + warning stderr, PAS crash. La ligne #N est signalée.
    - Fichier absent = `FileNotFoundError` (bruyant, pas d'ambiguïté).
    - Fichier vide = liste vide (silencieux).

    Args:
        path: chemin absolu vers le fichier `.jsonl`.

    Returns:
        Liste de dicts (raw events, non validés contre TrajectoryEvent).

    Raises:
        FileNotFoundError: si le fichier n'existe pas.
    """
    if not path.exists():
        raise FileNotFoundError(f"Trajectory file introuvable : {path}")

    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue  # ligne blanche silencieuse — JSONL le tolère
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                print(
                    f"[reader] skip {path}:{lineno} — JSON invalide ({exc.msg})",
                    file=sys.stderr,
                )
                continue
            if not isinstance(parsed, dict):
                print(
                    f"[reader] skip {path}:{lineno} — non-dict ({type(parsed).__name__})",
                    file=sys.stderr,
                )
                continue
            events.append(parsed)
    return events


def load_trajectory_dir(path: Path) -> dict[str, list[dict[str, Any]]]:
    """
    Charge TOUS les `.jsonl` d'un dossier, regroupés par `session_id`.

    Contrat :
    - Scanne récursivement `path/**/*.jsonl` (append-only sinks peuvent
      partitionner par date ou tenant, on ratisse tout).
    - Chaque event est regroupé par sa clé `session_id`.
    - Sessions partagent l'ordre d'apparition dans les fichiers (par
      ordre de scan + ordre des lignes) — PAS de tri par timestamp,
      c'est la responsabilité du caller si nécessaire.
    - Dossier absent = `FileNotFoundError`.
    - Dossier vide de `.jsonl` = dict vide.

    Args:
        path: chemin vers le dossier (typiquement `trajectories/`).

    Returns:
        Dict `session_id → list[dict]`.

    Raises:
        FileNotFoundError: si le dossier n'existe pas.
        NotADirectoryError: si le chemin existe mais n'est pas un dossier.
    """
    if not path.exists():
        raise FileNotFoundError(f"Trajectory directory introuvable : {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Chemin n'est pas un dossier : {path}")

    all_events: list[dict[str, Any]] = []
    # Tri des fichiers pour un ordre déterministe (utile en tests + audit).
    for jsonl_file in sorted(path.rglob("*.jsonl")):
        all_events.extend(load_trajectory_file(jsonl_file))
    return group_by_session(all_events)


def group_by_session(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """
    Regroupe une liste plate d'events par `session_id`.

    Contrat :
    - Ordre préservé au sein d'une session (ordre d'apparition dans la liste).
    - Event sans `session_id` (clé absente ou None) → skip + warning stderr.
    - Idempotent au sens : `group_by_session([e for evts in result.values() for e in evts])`
      reproduit le même regroupement (si events déjà groupés en ordre stable).

    Args:
        events: liste plate d'events.

    Returns:
        Dict `session_id → list[dict]` — l'ordre des clés suit l'ordre
        de première apparition de chaque `session_id` dans `events`.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for i, event in enumerate(events):
        session_id = event.get("session_id")
        if not session_id:  # None, "", ou clé absente
            print(
                f"[reader] skip event[{i}] — session_id absent ou vide",
                file=sys.stderr,
            )
            continue
        grouped.setdefault(session_id, []).append(event)
    return grouped


__all__ = ["load_trajectory_file", "load_trajectory_dir", "group_by_session"]
