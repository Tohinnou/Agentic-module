# Agent Cards — Spec sandbox (Marina Rentals)

## Statut & Contexte

Ce format est **pédagogique**, pas conforme à un standard A2A officiel publié.

Il s'inspire du mouvement Agent-to-Agent (Linux Foundation, en cours de
standardisation à l'heure de ce commit) mais prend des libertés pour rester
lisible en sandbox.

Le champ `spec_version` de chaque Card affirme cette réalité :
`"a2a-0.2-sandbox"` = "inspiré de A2A ~v0.2, adapté sandbox".

Si un jour on migre vers un vrai registre A2A, on retirera le bloc
`sandbox_extensions` (voir §7) et on ajustera les champs standard.

---

## Structure top-level

Chaque Card vit dans `meta/agents/{agent_name}.card.json` et contient
**7 blocs** :

1. `spec_version` (string) — dialecte
2. `agent` (object) — identité
3. `capabilities` (object) — features techniques
4. `authentication` (object) — sécurité (vide en sandbox)
5. `default_input_modes` / `default_output_modes` (arrays) — MIME defaults
6. `skills` (array) — catalogue des services offerts
7. `sandbox_extensions` (object) — nos ajouts spécifiques au projet

---

## 1. `spec_version` (string, requis)

Valeur actuelle : `"a2a-0.2-sandbox"`.

Rôle : identifier le dialecte de la Card. Sert à un outil qui lit les Cards
pour savoir quels champs attendre.

---

## 2. `agent` (object, requis)

L'identité de l'agent.

| Champ | Type | Requis | Description | Exemple |
|---|---|---|---|---|
| `name` | string (snake_case) | oui | Identifiant machine, jamais traduit | `"support_agent"` |
| `description` | string | oui | Description à destination d'un autre agent (router function) | *(voir cards existantes)* |
| `version` | string (semver) | oui | Version de la Card elle-même | `"0.1.0"` |
| `provider` | string | oui | Fournisseur/organisation | `"Marina Rentals (fictif)"` |
| `documentation` | string (path ou URL) | oui | Où trouver le code d'implémentation | `"src/sandbox/agents/orchestrator.py"` |

---

## 3. `capabilities` (object, requis)

Bloc de flags booléens décrivant les features de transport/interaction.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `streaming` | bool | oui | L'agent streame-t-il ses tokens (SSE, chunks) ? |
| `push_notifications` | bool | oui | Peut-il notifier proactivement (webhook, callback) ? |
| `trajectory_history` | bool | oui | Produit et expose une trajectoire post-hoc ? |
| `can_block` | bool | optionnel | Peut refuser une requête d'un caller (rare — agents-guardrails uniquement) |

---

## 4. `authentication` (object, requis)

En sandbox, ce bloc est **présent mais vide**. On le laisse pour discipline
Zero Ambient Authority (§4 règle 5 CLAUDE.md).

| Champ | Type | Requis | Description |
|---|---|---|---|
| `schemes` | array | oui | Schémas d'auth acceptés (vide en sandbox) |
| `note` | string | optionnel | Explication humaine si `schemes` vide |

---

## 5. `default_input_modes` / `default_output_modes` (arrays, requis)

Format MIME des inputs/outputs par défaut de l'agent.

Valeurs courantes :
- `"text/plain"` — texte brut (utile en amont : questions clients)
- `"application/json"` — objet structuré (utile en aval : évaluateurs, gates)

Chaque skill peut **surcharger** ces defaults via ses propres champs
`input_modes` / `output_modes`.

---

## 6. `skills` (array, requis)

Catalogue des **services** exposés par l'agent au monde extérieur.

⚠️ **Attention au vocabulaire** : ces "skills" ne sont **PAS** les Skills de
Day 3 (`.agent/skills/{name}/SKILL.md`). Ici, une skill = une **ligne au menu**
(descriptive). Une Skill de Day 3 = une **recette interne** (exécutable).

Chaque entrée du tableau :

| Champ | Type | Requis | Description |
|---|---|---|---|
| `id` | string (snake_case) | oui | Identifiant machine |
| `name` | string (Title Case) | oui | Label humain |
| `description` | string | oui | Ce que la skill fait (pour matching sémantique par d'autres agents) |
| `tags` | array of strings | oui | Mots-clés pour catégoriser |
| `examples` | array of strings | oui | Cas d'usage typiques (deviennent des tests golden) |
| `input_modes` | array | optionnel | Override du default de l'agent |
| `output_modes` | array | optionnel | Override du default de l'agent |
| `implementation_status` | enum | optionnel | `"planned"`, `"experimental"`, `"stable"`, `"deprecated"` |

Convention `implementation_status` :
- **absent ou `"stable"`** : la skill est implémentée et prête
- **`"planned"`** : déclarée dans le contrat, pas encore codée (SDD)
- **`"experimental"`** : implémentée, comportement non stable
- **`"deprecated"`** : sera retirée à la prochaine version majeure

---

## 7. `sandbox_extensions` (object, requis en sandbox)

Notre bloc maison. Contient tout ce qui n'existe pas dans A2A officiel.

**À supprimer intégralement** si migration vers un vrai registre A2A.

### 7.1 `authority_ladder` (object, requis)

Le Read/Draft/Act ladder du cours (§7 CLAUDE.md).

| Champ | Type | Requis | Description |
|---|---|---|---|
| `read` | bool | oui | Peut lire (retrieve, classify, inspecter) |
| `draft` | bool | oui | Peut produire un artefact **non envoyé** au client |
| `act` | bool | oui | Peut effectuer un side-effect irréversible/observable |

### 7.2 `special_powers` (object, optionnel — guardrails uniquement)

Utilisé quand un agent a des pouvoirs orthogonaux à la ladder Read/Draft/Act
(typiquement : bloquer, suspendre).

| Champ | Type | Description |
|---|---|---|
| `can_block` | bool | Peut refuser une action d'un autre agent |
| `can_require_hitl` | bool | Peut exiger validation humaine avant de laisser passer |
| `can_modify_request` | bool | Peut modifier la requête inspectée. ⚠️ **JAMAIS `true`** pour un guardrail (Confused Deputy) |

### 7.3 `allowed_tools` (array, requis)

Liste des noms de tools que l'agent **peut invoquer aujourd'hui**.

Contrainte de cohérence : aucun tool avec `risk_level: "act"` ne doit
apparaître ici si `authority_ladder.act: false`.

Un array vide (`[]`) est valide (ex. security_reviewer_agent — il n'invoque
pas de tool métier, il inspecte).

### 7.4 `planned_tools` (array, optionnel)

Liste des tools **prévus** mais pas encore autorisés ou implémentés.

Purement documentaire. **Pas** utilisé par le Policy Server. Sert à
communiquer la roadmap dans le contrat.

### 7.5 `pipeline_mode` (enum, requis)

Décrit la nature d'invocation de l'agent.

| Valeur | Signification | Exemple |
|---|---|---|
| `"fixed"` | Pipeline hardcodé de N étapes chaînées | `support_agent` (classify → retrieve → draft → evaluate) |
| `"on_demand"` | Invocation atomique, pas de pipeline | `evaluator_agent` (input → output) |
| `"intercept"` | Agent transversal branché sur le flux d'un autre | `security_reviewer_agent` (inspecte tool calls) |

### 7.6 `pipeline_steps` (array, requis si `pipeline_mode: "fixed"`)

Liste ordonnée des tools invoqués dans le pipeline.

Absent si `pipeline_mode` est `"on_demand"` ou `"intercept"`.

### 7.7 `hitl_guarantee` (string, requis)

Une phrase en langage naturel qui décrit **ce que l'agent ne fera JAMAIS
sans intervention humaine**.

C'est un **contrat formel** — le violer = bumper la version majeure de la
Card (`0.x.y` → `1.0.0` avec breaking change).

### 7.8 `trajectory_sink_default` (string, requis)

Chemin par défaut du JSONL de trajectoire de l'agent (relatif au repo).

Convention : `trajectories/{agent_name}.jsonl`.

### 7.9 `implemented_by` (string, requis)

Chemin d'import Python de la classe qui implémente l'agent, sous la forme
`module.submodule.ClassName`.

Un `importlib.import_module()` doit pouvoir résoudre cette valeur (une fois
l'agent codé). Si l'agent n'existe pas encore, suffixer avec `" (à créer
Phase N)"` pour tracer l'écart entre contrat et code.

---

## Contraintes de cohérence interne

Une Card est **cohérente** si :

1. **Aucun tool `act`** dans `allowed_tools` si `authority_ladder.act: false`.
2. **`pipeline_steps` non vide** si et seulement si `pipeline_mode: "fixed"`.
3. **`special_powers.can_modify_request: false`** pour tous les agents qui ont
   `can_block: true` (règle anti-Confused-Deputy).
4. **Chaque `tag`** d'une skill doit avoir un sens dans le domaine (catégorie
   de tool, domaine métier).
5. **`implemented_by`** doit pointer vers un chemin Python valide OU être
   explicitement marqué comme à créer.

Aucun validateur automatique n'existe encore. Un JSON schema formel sera
introduit en Phase 6 avec le Policy Server.

En attendant, valider manuellement = lecture croisée avec cette doc +
`json.load()` qui plante si JSON mal formé.

---

## Template minimal

Copier ce squelette pour créer une nouvelle Card :

```json
{
  "spec_version": "a2a-0.2-sandbox",
  "agent": {
    "name": "MY_AGENT_NAME",
    "description": "Décrit ce que l'agent fait, pour qu'un autre agent puisse décider de l'appeler.",
    "version": "0.1.0",
    "provider": "Marina Rentals (fictif)",
    "documentation": "src/sandbox/agents/MY_AGENT.py"
  },
  "capabilities": {
    "streaming": false,
    "push_notifications": false,
    "trajectory_history": true
  },
  "authentication": {
    "schemes": [],
    "note": "Sandbox — pas d'auth ; en prod, prévoir OAuth2 + JIT Token Downscoping (Day 4)."
  },
  "default_input_modes": ["text/plain"],
  "default_output_modes": ["application/json"],
  "skills": [
    {
      "id": "MY_SKILL_ID",
      "name": "My skill name",
      "description": "Ce que la skill offre.",
      "tags": [],
      "examples": [],
      "input_modes": ["text/plain"],
      "output_modes": ["application/json"]
    }
  ],
  "sandbox_extensions": {
    "authority_ladder": {"read": true, "draft": false, "act": false},
    "allowed_tools": [],
    "pipeline_mode": "on_demand",
    "hitl_guarantee": "Décrit ce que l'agent ne fera JAMAIS sans humain.",
    "trajectory_sink_default": "trajectories/MY_AGENT.jsonl",
    "implemented_by": "sandbox.agents.MY_AGENT.MyAgentClass"
  }
}
```

---

## Références

- **Cours Kaggle × Google 5-Day AI Agents** — Day 2 (Tools, MCP, A2A, A2UI).
- **CLAUDE.md §7** — vocabulaire A2A, Read/Draft/Act ladder, Policy Server.
- **PROJECT.MD §4 (Phase 4)** — objectif pédagogique des Agent Cards.
- **Cards existantes** dans ce dossier :
  - `support_agent.card.json` — pipeline `"fixed"`, authority draft
  - `evaluator_agent.card.json` — mode `"on_demand"`, read-only, 2 skills
  - `security_reviewer_agent.card.json` — mode `"intercept"`, avec `special_powers`
