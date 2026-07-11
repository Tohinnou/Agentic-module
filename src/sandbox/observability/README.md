# Observability

Analyse post-hoc des Vibe Trajectory JSONL logs — détection d'**Intent Drift**
sur des sessions déjà exécutées. Rule-based, reproductible, sans LLM.

> Contexte projet : §7 CLAUDE.md, Day 4 du cours Kaggle × Google.
> Ce module est le pilier "Observability" du sandbox Marina Rentals.

---

## Flux

```
trajectories/*.jsonl
  │
  ▼
┌───────────────────────────────┐
│  reader.py                    │  I/O tolérant (skip + warn sur
│  load_trajectory_dir(path)    │  ligne corrompue)
└──────────────┬────────────────┘
               │
               │  dict[session_id -> list[dict]]
               ▼
┌───────────────────────────────┐
│  __init__.py                  │  Point d'entrée public
│  detect_drift(events, agent)  │  Rule-based, ~μs par session
└──────────────┬────────────────┘
               │
               │  DriftReport (frozen, immuable)
               ▼
┌───────────────────────────────┐
│  report.py                    │  CLI human-facing
│  main(argv) -> exit_code      │  Table ASCII sur stdout
└───────────────────────────────┘
```

---

## Usage CLI

```bash
python -m sandbox.observability.report --path trajectories/
```

Sortie type :

```
session_id           | severity | signals
---------------------+----------+----------------------------------------
s-a3f2b1c9           | none     | (nominal)
s-4e7d2f01           | medium   | hitl_bypassed
s-9c1b3a58           | high     | policy_block_encountered, unexpected_tool_sequence
```

**Arguments** :
- `--path` (défaut `./trajectories/`) — dossier scanné récursivement pour tous les `.jsonl`.
- `--agent` (défaut `support_agent`) — agent attendu, détermine le pattern de séquence valide.

**Exit codes** :
- `0` : aucune session `severity="high"` détectée — sain.
- `1` : au moins une session `severity="high"` — action requise.
- `2` : erreur d'entrée (path absent, argparse fail).

Le code de sortie `1` est fait pour être utilisé en CI/cron : `python -m sandbox.observability.report && ...` s'arrête si un drift high est détecté.

---

## Public API (usage bibliothèque)

```python
from sandbox.observability import detect_drift, DriftReport, DriftSignal
from sandbox.observability.reader import (
    load_trajectory_file,
    load_trajectory_dir,
    group_by_session,
)
```

### `detect_drift(events, expected_agent="support_agent") -> DriftReport`

Point d'entrée principal. Analyse UNE session (liste d'events du même `session_id`) et retourne un report immuable.

**Contrat** :
- Ne mute jamais `events` (analyse read-only).
- Déterministe : mêmes events → même report.
- Signaux triés alphabétiquement par `code`.
- Fail-loud sur input incohérent (session_ids mélangés, events vides).

### `DriftReport` (frozen dataclass)

```python
session_id: str
signals: tuple[DriftSignal, ...]   # tuple, pas list — immuabilité transitive
severity: Literal["none", "low", "medium", "high"]  # max des signal severities
```

**Invariant** : `signals == ()` ⇔ `severity == "none"`.

### `DriftSignal` (frozen dataclass)

```python
code: str                    # slug kebab-case (1 des 4 catégories)
severity: Literal["low", "medium", "high"]
detail: str                  # message humain-lisible
events: tuple[int, ...]      # step numbers concernés
```

---

## Les 4 signaux détectés

Source de vérité : [`meta/intent_drift_signals.md`](../../../meta/intent_drift_signals.md).

| Code | Sévérité | Signal |
|---|---|---|
| `policy_block_encountered` | high | Au moins un event `policy_verdict=block` |
| `hitl_bypassed` | medium | `policy_verdict=hitl_required` + `status=success` (mode sandbox permissif) |
| `unexpected_tool_sequence` | high | Actions ne matchent aucun pattern `EXPECTED_SEQUENCES[agent]` |
| `duplicate_action` | medium | Même action apparaît 2+ fois dans la session |

Un `DriftReport` peut porter plusieurs signaux. La sévérité globale est le max.

---

## Étendre le système

### Ajouter un nouveau signal

1. **DATA d'abord** — ajouter la spec dans `meta/intent_drift_signals.md` (section, catégorie, sévérité, contre-exemples).
2. **Fixture** — ajouter des cas dans `evals/drift_cases.yaml` (au moins 1 positif + 1 négatif).
3. **Code** — ajouter un helper `_detect_<nouveau_signal>(events)` dans `drift.py`. Retour : `DriftSignal | None`.
4. **Wiring** — ajouter l'appel dans `detect_drift()` (`__init__.py`) à la liste `raw_signals`.
5. **Tests** — les tests parametrisés sur `drift_cases.yaml` couvriront automatiquement le nouveau signal.

### Ajouter un nouvel agent

1. Ajouter une clé dans `EXPECTED_SEQUENCES` (`drift.py`) avec la liste des séquences de tools valides pour cet agent.
2. Le CLI accepte déjà `--agent NAME` — pas de modification nécessaire.

### Ajouter un nouveau format de sortie (JSON, CSV)

Hors-scope Phase 7 mais planifié :
1. Ajouter `--format {ascii,json,csv}` à l'argparse de `report.py`.
2. Écrire des formatters dédiés (`format_report_json`, `format_report_csv`).

---

## Pièges classiques

- **JSONL corrompu** — le reader skip + warn sur stderr. Regarde `stderr` si le report semble incomplet.
- **`session_id` absent** — event skipé silencieusement (avec warning). Une session peut disparaître du report si TOUS ses events sont sans id.
- **Ordre des signaux** — trié alphabétiquement par `code`. Ne pas se fier à l'ordre d'insertion.
- **Sévérité globale** — utilise `_SEVERITY_ORDER` dict, pas `max()` sur strings. `max(["low", "high"]) == "low"` (piège lexicographique).
- **`expected_agent` inconnu** — `EXPECTED_SEQUENCES.get(agent, [])` retourne `[]` → toute séquence est "inattendue" → signal high sur toute session. Ajouter la clé pour un nouvel agent avant d'analyser ses trajectoires.

---

## Renvois

- **Contrat data** : `meta/intent_drift_signals.md`
- **Fixture** : `evals/drift_cases.yaml` (6 cas synthétiques)
- **Tests** : `tests/test_observability.py` (29 tests, dont 6 parametrisés sur la fixture)
- **Source des events** : `src/sandbox/agents/orchestrator.py::TrajectoryEvent`
- **Course** : Day 4 — Vibe Trajectory (`day4.txt`), §7 CLAUDE.md
- **WHY blocks** : `meta/learning_notes.md` sections Phase 7.0..7.3
