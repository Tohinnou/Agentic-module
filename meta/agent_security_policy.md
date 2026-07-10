# Agent Security Policy — Sandbox

## Purpose

Ce fichier est la **source de vérité** consommée par `structural_gate.py`
(Policy Server, Phase 6). Il décrit, de manière **déterministe**, quels
agents peuvent invoquer quels tools dans quels environnements.

Toute modification à ce fichier = redémarrage du Policy Server (pas de
hot-reload en sandbox).

**Convention** : Markdown pour la prose, YAML pour les données structurées
(§4 règle 2 CLAUDE.md).

---

## Environnements

Trois environnements, du plus permissif au plus strict :

| Env | Description | Politique par défaut |
|---|---|---|
| `dev` | Développement local, sandbox | Permissif (allow-list large) |
| `staging` | Tests d'intégration | Modéré (allow-list large + HITL sur `act`) |
| `prod` | Non applicable dans le sandbox | Référence future — allow-list vide |

Le sandbox tourne en `env: dev` par défaut. Le champ existe pour montrer
que le Structural Gate se **paramètre par environnement** — un vrai
déploiement prod utiliserait la même mécanique.

## Rôles agents

Alignés sur les Agent Cards (Phase 4) :

- `support_agent` — pipeline fixed classify → retrieve → draft → evaluate
- `evaluator_agent` — audit read-only
- `security_reviewer_agent` — intercepteur, aucun tool métier

---

## Allow-list (source de vérité machine-lisible)

```yaml
version: "1.0.0"
default_policy: deny  # default-deny (Day 4 baseline)

allowlist:
  support_agent:
    dev:
      allowed_tools:
        - retrieve_docs
        - classify_ticket
        - draft_reply
        - evaluate_answer
        - generate_report
      # NOT allowed in dev: create_ticket (act, staging seulement)
    staging:
      allowed_tools:
        - retrieve_docs
        - classify_ticket
        - draft_reply
        - evaluate_answer
        - generate_report
        - create_ticket   # Autorisé structurellement mais force_hitl (voir act_rules)
    prod:
      allowed_tools: []   # Non déployé en prod dans le sandbox

  evaluator_agent:
    dev:
      allowed_tools:
        - evaluate_answer
    staging:
      allowed_tools:
        - evaluate_answer
    prod:
      allowed_tools: []

  security_reviewer_agent:
    dev:
      allowed_tools: []   # N'invoque jamais de tool métier (§7.2 Card)
    staging:
      allowed_tools: []
    prod:
      allowed_tools: []
```

---

## Overrides — tools `act`

Certains tools sont **toujours** en HITL_REQUIRED quel que soit l'agent ou
l'env où ils sont autorisés :

```yaml
act_rules:
  create_ticket:
    force_hitl: true
    reason_code: act_tool_default_hitl
    rationale: "Création ticket = side-effect base de données. HITL obligatoire (§4 règle 3 CLAUDE.md, Day 4 Pillar 5)."
  # Extensible : send_email, charge_payment, etc.
```

Le Structural Gate applique cette règle **après** l'allow-list. Séquence :

1. Le tool est-il dans `allowlist[agent][env]` ? Sinon → **BLOCK** (`reason: tool_not_allowed`)
2. Le tool a-t-il `force_hitl: true` dans `act_rules` ? Si oui → **HITL_REQUIRED** (`reason: act_tool_default_hitl`)
3. Sinon → **ALLOW** (`reason: allowlist_match`)

---

## Rate limits (placeholder Phase 7)

Non enforcé en Phase 6. Documenté ici pour tracer la roadmap :

```yaml
rate_limits:
  # Phase 7 : intégration avec AgBOM et Vibe Trajectory.
  # Ex. support_agent max 60 retrieve_docs / minute.
```

---

## Contrat de sortie de `structural_gate.check()`

Trois cas possibles, tous encodés dans `PolicyDecision` :

| Cas | verdict | layer_triggered | reason |
|---|---|---|---|
| Tool absent de l'allow-list | `block` | `structural` | `tool_not_allowed` |
| Tool présent + `force_hitl: true` | `hitl_required` | `structural` | `act_tool_default_hitl` |
| Tool présent + rule normale | `allow` | `structural` | `allowlist_match` |

Note : ALLOW du Structural Gate est **provisoire** — l'appel enchaîne
ensuite sur Semantic Gate qui peut re-classifier en HITL ou BLOCK.

---

## Chargement & validation

- Chargement au démarrage du Policy Server (import statique)
- Aucun hot-reload : modification = redémarrer le service
- Validation de schéma via `pyyaml` + `dataclass` (frozen)
- Un cas non couvert par l'allow-list = **default_policy** appliqué (deny)

---

## Extension future

- **Phase 7** : rate limits + observation dynamique via AgBOM
- **Phase 10** : Green Team peut proposer des ajouts (Auto-Refactoring Day 4)
- **Prod réelle** : ce fichier serait signé cryptographiquement (Day 4 Pillar 3)
