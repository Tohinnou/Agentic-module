"""
CLI observability report — analyse post-hoc des trajectoires JSONL.

Phase 7.3 (§7 CLAUDE.md, Day 4 — Vibe Trajectory analysis).

Usage :
    python -m sandbox.observability.report [--path DIR] [--agent NAME]

Charge tous les `.jsonl` d'un dossier, groupe par session, invoque
`detect_drift()` par session, imprime un tableau ASCII sur stdout.

Exit codes :
- 0 : aucune session `severity="high"` détectée.
- 1 : au moins une session avec `severity="high"` (utile en CI/cron).
- 2 : erreur d'entrée (path absent, argparse fail).

C'est le seul consommateur "humain" du detector. La lib `drift.py` reste
importable pour d'autres usages (dashboard futur, alertes, etc.).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sandbox.observability import DriftReport, detect_drift
from sandbox.observability.reader import load_trajectory_dir


# Longueur max d'affichage pour le session_id — un uuid8 fait 8 chars mais
# on prévoit un peu de marge pour les préfixes ("s-...", "test-...").
_SESSION_ID_MAX_WIDTH = 20


def format_report_table(reports: list[DriftReport]) -> str:
    """Formate une liste de `DriftReport` en tableau ASCII lisible.

    Contrat : jamais None, jamais raise. Une liste vide retourne une
    ligne d'info explicite (pas juste un header sans data).
    """
    if not reports:
        return "Aucune session à analyser.\n"

    id_width = min(
        _SESSION_ID_MAX_WIDTH,
        max(len("session_id"), max(len(r.session_id) for r in reports)),
    )
    sev_width = max(len("severity"), max(len(r.severity) for r in reports))

    header = f"{'session_id':<{id_width}} | {'severity':<{sev_width}} | signals"
    separator = f"{'-' * id_width}-+-{'-' * sev_width}-+-{'-' * 40}"

    lines = [header, separator]
    for r in reports:
        sid = r.session_id[:id_width]
        signals = (
            ", ".join(s.code for s in r.signals) if r.signals else "(nominal)"
        )
        lines.append(f"{sid:<{id_width}} | {r.severity:<{sev_width}} | {signals}")

    return "\n".join(lines) + "\n"


def analyze_directory(path: Path, expected_agent: str) -> list[DriftReport]:
    """Charge un dossier JSONL, retourne un `DriftReport` par session.

    Une session avec un input malformé (ex. session_id manquant) est
    skipée avec un warning stderr — pas de crash. Continue le traitement
    des autres sessions.
    """
    grouped = load_trajectory_dir(path)
    reports: list[DriftReport] = []
    for session_id, events in grouped.items():
        try:
            report = detect_drift(events, expected_agent=expected_agent)
            reports.append(report)
        except ValueError as exc:
            print(
                f"[report] skip {session_id} — {exc}",
                file=sys.stderr,
            )
    return reports


def main(argv: list[str] | None = None) -> int:
    """Entrée CLI — parse argv, analyse, imprime le tableau, retourne exit code.

    Signature testable directement (pas via subprocess) : `main(["--path", "/tmp"])`.
    """
    parser = argparse.ArgumentParser(
        prog="sandbox.observability.report",
        description=(
            "Analyse post-hoc des trajectoires JSONL pour détecter l'Intent Drift. "
            "Sortie : tableau ASCII sur stdout, exit 1 si severity=high détectée."
        ),
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("./trajectories/"),
        help="Dossier contenant les .jsonl (défaut : ./trajectories/)",
    )
    parser.add_argument(
        "--agent",
        default="support_agent",
        help=(
            "Nom de l'agent attendu, détermine la séquence pattern pour "
            "unexpected_tool_sequence (défaut : support_agent)"
        ),
    )
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"[report] path introuvable : {args.path}", file=sys.stderr)
        return 2

    reports = analyze_directory(args.path, args.agent)
    print(format_report_table(reports), end="")

    # Exit code : 1 si au moins une session est severity=high (utile en CI).
    if any(r.severity == "high" for r in reports):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
