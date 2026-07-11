# Policy Server

Governance layer qui inspecte chaque tool call **avant** exécution.
Deux couches en cascade : allowlist déterministe (structural) puis
LLM-judge (semantic) qui inspecte le contenu du payload.

> Contexte projet : §7 CLAUDE.md, Day 4 Pillar 4-5 du cours Kaggle × Google.
> Ce module est le pilier "Governance & Safety" du sandbox Marina Rentals.

---

## Flux

```
check(agent, env, tool, payload, user_message)
  │
  ▼
┌───────────────────────────────┐
│  structural_gate.py           │  fast (~μs), no LLM
│  allowlist déterministe       │  source : meta/agent_security_policy.md
│  + act_rules.force_hitl       │
└──────────────┬────────────────┘
               │
        ┌──────┴──────┐
        │             │
    BLOCK / HITL     ALLOW
        │             │
        │             ▼
        │      ┌──────────────────────────┐
        │      │  semantic_gate.py        │  slow (~500ms), LLM-judge
        │      │  OpenRouter Haiku-4.5    │  cache : data/policy_semantic_cache.json
        │      │  T=0, response_format=json│  prompt v1 (bump → invalide cache)
        │      └────────────┬─────────────┘
        │                   │
        └─────────┬─────────┘
                  │
                  ▼
         ┌────────────────────────┐
         │  vibe_diff.py          │  only when verdict == HITL_REQUIRED
         │  4 templates fixes     │  source : meta/vibe_diff_checklist.md
         │  + fallback + PII mask │
         └────────────┬───────────┘
                      │
                      ▼
              PolicyDecision (frozen, immutable)
              { verdict, reason, vibe_diff, layer_triggered }
```

---

## Public API

Tout ce qu'un consommateur (ex. `SupportAgent`) importe :

```python
from sandbox.policy_server import check, PolicyDecision
from sandbox.policy_server.exceptions import (
    PolicyRefusal,       # base commune
    PolicyBlockError,    # verdict = block
    PolicyHITLRequired,  # verdict = hitl_required
)
```

### `check(agent, env, tool, payload, user_message) -> PolicyDecision`

Point d'entrée unique. Retourne une décision immuable — jamais None,
jamais raise (les erreurs internes deviennent `PolicyDecision(verdict="block", reason="semantic_gate_error:*")`).

Le caller décide de faire quoi : ignorer, logger, ou raise `PolicyBlockError` /
`PolicyHITLRequired` selon sa politique. `SupportAgent` fait ce dernier
(cf. `agents/orchestrator.py::_call_tool`).

### `PolicyDecision` (frozen dataclass)

```python
@dataclass(frozen=True)
class PolicyDecision:
    verdict: Literal["allow", "block", "hitl_required"]
    reason: str                                    # kebab-case
    vibe_diff: str | None                          # non-None ssi HITL
    layer_triggered: Literal["structural", "semantic"]
```

Invariants :

- `verdict == "hitl_required"` ⇒ `vibe_diff is not None`
- `verdict == "allow"` ⇒ `vibe_diff is None`
- `verdict == "block"` ⇒ `vibe_diff is None` (BLOCK est final)

---

## Modules internes (détail d'implémentation)

| Fichier | Rôle | Ligne d'entrée publique |
|---|---|---|
| `__init__.py` | Orchestration `check()`, contrat `PolicyDecision` | `check(...)` |
| `structural_gate.py` | Parse `meta/agent_security_policy.md`, allow-list + act_rules | `check_structural(agent, env, tool)` |
| `semantic_gate.py` | Appel OpenRouter + cache + parsing JSON tolérant | `check_semantic(tool, payload, user_message)` |
| `vibe_diff.py` | 4 templates + PII masking + enforcement longueur | `generate(reason, tool, payload, user_message, layer)` |
| `exceptions.py` | Hiérarchie `PolicyRefusal` → `PolicyBlockError` / `PolicyHITLRequired` | classes |

---

## Étendre le système

### Ajouter un nouveau tool

1. Créer le tool sous `src/sandbox/tools/<name>.py` avec `Input/Output` Pydantic + `TOOL_METADATA`.
2. Ajouter le tool à `meta/agent_security_policy.md` sous `allowlist[<agent>][<env>][allowed_tools]`.
3. Si `risk_level: "act"` → ajouter à `act_rules[<tool>]` avec `force_hitl: true` et `reason_code`.
4. **Redémarrer le process** — `_load_policy()` a un `lru_cache(maxsize=1)`, pas de hot-reload.

### Ajouter un nouvel agent

Symétrique : nouveau bloc `allowlist[<new_agent>]` dans le policy file avec ses envs autorisés. L'agent Python doit setter `AGENT_NAME = "<new_agent>"` en class constant.

### Ajouter une catégorie Semantic

1. Ajouter la ligne au `SYSTEM_PROMPT` dans `semantic_gate.py` sous BLOCK ou HITL selon le compromis (HITL > BLOCK sur ambigu — cf. Phase 6.2).
2. Bump `PROMPT_VERSION = "v2"` — invalide le cache entier automatiquement (le hash inclut la version).
3. Ajouter le template dédié dans `vibe_diff.TEMPLATES` + la section `### Template \`<name>\`` dans `meta/vibe_diff_checklist.md`.
4. Ajouter un cas dans `evals/adversarial_policy.yaml` pour tester la reconnaissance.

---

## Pièges classiques

- **Cache stale** — modifier `SYSTEM_PROMPT` sans bump `PROMPT_VERSION` = servir des verdicts obsolètes indéfiniment. Le hash de cache inclut la version, mais pas le texte du prompt.
- **Allowlist trou** — un tool absent de l'allowlist = BLOCK immédiat. Le fail-closed ne pardonne pas les oublis. Ajouter EXPLICITEMENT dans le policy file.
- **HITL en dev** — `strict_hitl=False` par défaut côté `SupportAgent`. Le pipeline continue même sur un HITL — check la trajectoire (`policy_verdict="hitl_required"`) pour l'audit post-hoc.
- **OpenRouter down** — `check_semantic()` fail-closed sur `httpx.HTTPError` → BLOCK avec `reason="semantic_gate_error:HTTPError"`. Prévoir un fallback humain si le gate doit rester opérationnel offline.
- **PROMPT_VERSION oublié** — après un ajout de catégorie sans bump, ancien verdict + nouveau verdict cohabitent silencieusement dans le cache selon l'ordre de première invocation. Résultat : tests flakys sans erreur apparente.

---

## Renvois

- **Contrat data** : `meta/agent_security_policy.md`, `meta/vibe_diff_checklist.md`
- **Tests unité** : `tests/test_policy_server.py` (31 tests)
- **Tests intégration** : `tests/test_policy_server_integration.py` (5 tests)
- **Fixture adversariale** : `evals/adversarial_policy.yaml` (10 cases : adv_01..adv_10)
- **Course** : Day 4 Pillar 4-5 (`day4.txt`), §7 CLAUDE.md
- **WHY blocks** : `meta/learning_notes.md` sections Phase 6.0..6.5
