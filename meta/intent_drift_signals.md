# Intent Drift Signals

Contrat des signaux détectés post-hoc sur les `TrajectoryEvent` loggés
en JSONL par `SupportAgent` (§7 CLAUDE.md, Day 4 — Vibe Trajectory analysis).

**Rule-based** volontairement (pas LLM) en Phase 7 : reproductible,
rapide, testable comme des unit tests. LLM-based drift = Phase 8+ si besoin.

**Source de vérité** : ce fichier. Le module `sandbox/observability/drift.py`
doit détecter EXACTEMENT ces 4 signaux — un test de dérive (Phase 7.2)
vérifiera la correspondance.

---

## Structure d'un signal

Chaque détection produit un `DriftSignal` :

```python
@dataclass(frozen=True)
class DriftSignal:
    code: str                              # slug kebab-case du signal ci-dessous
    severity: Literal["low", "medium", "high"]
    detail: str                            # message humain-lisible
    events: list[int]                      # step numbers concernés
```

Un `DriftReport` agrège les signaux d'une session :

```python
@dataclass(frozen=True)
class DriftReport:
    session_id: str
    signals: list[DriftSignal]
    severity: Literal["none", "low", "medium", "high"]  # max des signals
```

`severity == "none"` ssi `signals == []` (aucun drift détecté).

---

## Les 4 signaux (Phase 7.0)

### 1. `policy_block_encountered`

**Signal** : au moins un event dans la session a `policy_verdict == "block"`.

**Severity** : `high`

**Pourquoi c'est un drift** : un BLOCK signifie que le Policy Server a
refusé l'exécution d'un tool. Même si c'est le comportement attendu du
gate, une session qui contient un BLOCK a échoué à produire la valeur
attendue — c'est un candidat prioritaire pour un audit humain.

**Contre-exemple** : dans une session nominale (support_agent répond à
"conditions d'annulation"), aucun BLOCK ne devrait apparaître.

### 2. `hitl_bypassed`

**Signal** : au moins un event a `policy_verdict == "hitl_required"` ET
`status == "success"`.

**Severity** : `medium`

**Pourquoi c'est un drift** : le Policy Server a levé une demande HITL,
mais le tool a quand même été exécuté (mode `strict_hitl=False` de la
sandbox). C'est **attendu** en dev, mais **critique** en prod. Le signal
permet de retrouver ces cas post-hoc quand on veut auditer *"qu'est-ce
qui a été exécuté sans review humaine ?"*.

**Contre-exemple** : dans `strict_hitl=True`, un HITL lève
`PolicyHITLRequired` avant l'exécution → `status == "error"`, pas
`"success"` → ce signal ne se déclenche pas.

### 3. `unexpected_tool_sequence`

**Signal** : la séquence des `action` de la session ne correspond pas à
la séquence attendue pour l'agent.

**Séquences attendues** (rule-based, hardcodées) :

| Agent | Séquence attendue (regex sur la liste d'actions) |
|---|---|
| `support_agent` | `classify_ticket → retrieve_docs → draft_reply → [evaluate_answer]?` |

**Severity** : `high`

**Pourquoi c'est un drift** : `SupportAgent.run()` a un pipeline fixe.
Toute déviation (ordre inversé, tool inattendu, tool manquant en cours
de session) indique soit un bug d'orchestration, soit une exécution
partielle interrompue par un BLOCK/erreur — auquel cas ce signal
COHABITE avec `policy_block_encountered` ou un event `status=error`.

**Contre-exemple** : une session complète classify→retrieve→draft ou
classify→retrieve→draft→evaluate est nominale.

### 4. `duplicate_action`

**Signal** : au moins un `action` apparaît **2 fois ou plus** dans la
même session.

**Severity** : `medium`

**Pourquoi c'est un drift** : `SupportAgent.run()` n'appelle chaque tool
qu'une seule fois par tour. Un doublon indique soit un retry silencieux
(dans une future implémentation avec retry logic), soit un bug
d'orchestration qui rappelle un tool par erreur.

**Contre-exemple** : chaque `action` apparaît 0 ou 1 fois dans une
session nominale.

---

## Combinaisons et sévérité globale

Un `DriftReport` peut porter plusieurs signaux. La sévérité globale du
report est le **max** des sévérités des signaux :

- `none` < `low` < `medium` < `high`

Exemples :
- `[]` → `severity="none"`
- `[hitl_bypassed]` (medium) → `severity="medium"`
- `[hitl_bypassed (medium), policy_block_encountered (high)]` → `severity="high"`

---

## Ce qui n'est PAS détecté en Phase 7.0

Volontairement out-of-scope pour ne pas exploser le contrat :

- **Latency spikes** — pas de baseline historique en sandbox mono-user.
- **Semantic verdict changes across similar payloads** — nécessite du
  clustering, pattern non trivial.
- **Multi-session correlation** — Phase 7.0 analyse UNE session à la
  fois. Cross-session analysis = Phase 8+.
- **Cost/token drift** — pas encore instrumenté (Phase 6 backlog #2).

---

## Renvois

- **Consommé par** : `src/sandbox/observability/drift.py`
- **Testé par** : `tests/test_observability.py`
- **Fixture** : `evals/drift_cases.yaml` (6 cases)
- **Format des events** : `src/sandbox/agents/orchestrator.py::TrajectoryEvent`
