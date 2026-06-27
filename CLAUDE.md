# CLAUDE.md — Project DNA

> Ce fichier est lu en premier par tout agent (Claude Code, Antigravity, Gemini CLI…) qui ouvre ce repo.
> Il définit l'identité du projet, les règles d'ingénierie et le vocabulaire à respecter.
> Pour la roadmap détaillée → voir `PROJECT.MD`. Pour la théorie du cours → voir `day{1..5}.txt`.

---

## 1. Identity

**Nom du projet :** Agentic Support & Operations Sandbox
**Domaine fictif :** **Marina Rentals** — entreprise SaaS imaginaire de location de bateaux et d'équipements nautiques. Sert de playground pour tous les artefacts du projet (RAG, agents, skills, evals). Les 10 docs `docs/` utilisent déjà ce nom de manière cohérente.

**Mission pédagogique :** assimiler les 5 jours du *Kaggle × Google 5-Day AI Agents: Intensive Vibe Coding Course With Google* en construisant un système agentic complet. Chaque décision d'architecture doit pouvoir être tracée à une notion du cours.

**Ce projet n'est PAS :** une production, une fork de `bchat`, une démo client. C'est un sandbox d'apprentissage solo.

---

## 2. Stack & Boundaries

```yaml
runtime:
  python: ">=3.11"
backend:    fastapi
storage:    sqlite (data/sandbox.db)
testing:    pytest
linting:    ruff
ui:         streamlit
llm:
  default:   mock (TF-IDF + BM25 fallback, offline)
  optional:  openrouter or ollama (gated by env var)
frameworks_forbidden_in_core:
  - langchain
  - llama_index
frameworks_allowed_in_phase_11_only:
  - langchain
  - llama_index
  reason: "Excursion comparative pédagogique (1 skill réimplémentée pour contraster avec l'approche primitive)"
```

**Pourquoi pas LangChain/LlamaIndex dans le core :** ils abstraient exactement les primitives que le cours enseigne (boucle agent, MCP wiring, SKILL.md). Coder à la main = comprendre.

---

## 3. File Hierarchy & Naming

```
kaggle/
├── CLAUDE.md            ← ce fichier (DNA, lu en premier)
├── PROJECT.MD           ← roadmap des 10 phases
├── README.md            ← onboarding humain
├── pyproject.toml       ← deps + ruff + pytest config
├── .env.example         ← variables d'env (jamais de secrets)
│
├── day{1..5}.txt        ← théorie du cours (référence)
│
├── docs/                ← corpus RAG (10 policies Marina Rentals en français)
├── specs/               ← Spec-Driven Dev (1 feature = 1 .md ou .yaml hybride)
├── .agent/skills/       ← 4 skills, chacune dans son dossier
│   └── {skill-name}/
│       ├── SKILL.md         ← frontmatter YAML obligatoire (voir §5)
│       ├── scripts/         ← code exécutable
│       ├── references/      ← docs longues (chargées à la demande)
│       └── assets/          ← templates, exemples
│
├── src/sandbox/         ← code de l'application
│   ├── agents/             ← Support, Evaluator, Security Reviewer
│   ├── tools/              ← outils MCP-style (1 fichier par tool)
│   ├── policy_server/      ← Structural + Semantic gating (voir §4)
│   ├── retrieval/          ← BM25 / TF-IDF / chunking
│   └── api.py              ← FastAPI entry point
│
├── tests/               ← pytest (Eval-as-Unit-Test pattern)
├── evals/               ← golden datasets, LLM-judge cases, adversarial
│   ├── golden.yaml         ← cas BDD format Gherkin
│   ├── adversarial.yaml    ← prompt injections, jailbreaks
│   └── judge_prompts.md    ← prompts du LLM-as-Judge
└── trajectories/        ← Vibe Trajectory logs (JSONL, post-hoc)
```

**Règle de nommage :** `snake_case` pour Python, `kebab-case` pour skills et specs (`cancellation-policy.md`).

---

## 4. Engineering Rules

Ces règles sont **non négociables**. Un agent qui les viole produit du code à rejeter.

| # | Règle | Pourquoi |
|---|---|---|
| 1 | **TDD inversé** : pour tout bug, écrire un test qui FAIL avant le fix | Day 5 — empêche la régression et force la reproduction |
| 2 | **Format hybride** : Markdown pour la prose, YAML pour toute structure nestée > 3 | Day 5 — 51.9 % accuracy YAML vs 33.8 % XML sur configs profondes |
| 3 | **Vibe Diff obligatoire** avant tout tool à side-effect (write/delete/spend/send) | Day 4 — protège du Confused Deputy + HITL fail-safe |
| 4 | **Tous les tool calls passent par le Policy Server** (Structural + Semantic) | Day 4/5 — séparation execution/governance |
| 5 | **Zero Ambient Authority** : aucun outil n'a de permissions par défaut, scope au moment de l'appel | Day 4 — JIT Token Downscoping |
| 6 | **Context Hygiene** : pas d'email/téléphone/ID en dur, utiliser `[[VAR_NAME]]` résolu au runtime | Day 5 — empêche le context hallucination + leak PII |
| 7 | **Vibe Trajectory logué pour 100 % des tours** (JSONL dans `trajectories/`) | Day 4 — détection post-hoc de l'Intent Drift |
| 8 | **AgBOM mis à jour** à chaque ajout de dep, MCP, skill, modèle | Day 4 — Slopsquatting + supply chain |
| 9 | **Pas de renommage dans un bug fix** — toujours un commit séparé | Day 5 — simplifie la review |

---

## 5. Skill Authoring Standard

Chaque skill dans `.agent/skills/{name}/SKILL.md` doit avoir ce frontmatter exact :

```yaml
---
name: cancellation-policy-skill            # kebab-case, ≤ 60 chars
description: |                              # ≤ 200 chars, scénario explicite
  Quand un client demande à annuler une réservation Marina Rentals,
  applique la politique (48h gratuit, 24-48h frais 30%, <24h non
  remboursable sauf raisons sécurité/météo/indisponibilité).
version: 0.1.0
license: MIT
allowed-tools:
  - search_policy
  - generate_response
---
```

**Règles d'écriture :**
- `description` = **router function** : c'est elle qui décide si l'agent invoque la skill. Doit décrire le *trigger* (quand), pas le *what* (que fait la skill).
- `SKILL.md` body ≤ **500 lignes**. Au-delà → déplacer dans `references/` (Progressive Disclosure niveau 3).
- `allowed-tools` exhaustif : si un tool n'est pas listé, l'agent doit refuser.
- Cible : **trigger accuracy ≥ 0.90** (mesurée par eval golden).

---

## 6. Eval Discipline — les 5 patterns

Aucune skill, aucun agent ne passe en "fini" sans ces 5 couches d'éval :

```yaml
patterns:
  - name: eval_as_unit_test
    where: tests/
    format: pytest
    purpose: "Régression déterministe (search_policy renvoie le bon doc)"

  - name: golden_dataset
    where: evals/golden.yaml
    format: BDD Gherkin (Scenario / Given / When / Then)
    purpose: "Comportement attendu sur cas connus"
    target: pass^3 >= 0.85    # 3 runs identiques sur 50 cas

  - name: llm_as_judge
    where: evals/judge_prompts.md
    runner: Evaluator agent
    purpose: "Notation 0-5 sur 7 dimensions (clarté, exactitude, ton, sécurité, completude, concision, pertinence)"

  - name: adversarial
    where: evals/adversarial.yaml
    purpose: "Prompt injection, jailbreak, MCP spoofing, intent drift"
    target: refus correct sur 100 % des cas

  - name: canary_shadow
    where: src/sandbox/canary.py
    purpose: "Quand on modifie une skill, ancien+nouveau tournent en parallèle sur 10 % du trafic test, on compare"
```

**EDD (Evaluation-Driven Development) :** l'eval est écrite **avant** la skill, jamais après.

---

## 7. Vocabulary Lock

Ces termes du cours sont à utiliser **verbatim** (dans le code, les commits, la doc). Pas de synonymes maison.

| Terme | Définition |
|---|---|
| **Vibe Coding** | Coder en exprimant une intention de haut niveau et en laissant l'agent générer — orientation rapidité, sans garanties production. |
| **Agentic Engineering** | Discipline qui transforme le vibe coding en système fiable : specs, evals, guardrails, observabilité. C'est la cible de ce projet. |
| **Context Engineering** | Art de fournir à l'agent les 6 bons types de contexte : Instructions, Knowledge, Memory, Examples, Tools, Guardrails. |
| **Harness** | L'ensemble de l'infrastructure autour du modèle (prompts, tools, memory, orchestration, observabilité). CLAUDE.md = harness config. |
| **MCP** (Model Context Protocol) | Standard ouvert (Anthropic) qui expose tools/resources à n'importe quel agent compatible. "USB-C de l'IA." |
| **A2A** (Agent-to-Agent) | Protocole standardisant la communication entre agents distincts (Linux Foundation). |
| **A2UI** (Agent-to-UI) | Protocole standardisant la façon dont un agent rend une interface utilisateur (v0.9, 18 composants). |
| **AgBOM** (Agent Bill of Materials) | Inventaire signé de tout ce que ton agent consomme : modèles, MCPs, skills, deps, prompts versionnés. Anti-Slopsquatting. |
| **Progressive Disclosure** | Mécanique en 3 niveaux des Skills : metadata (toujours en contexte) → SKILL.md body (chargé si trigger) → references/ (chargé à la demande). |
| **EDD** (Evaluation-Driven Development) | Écrire l'eval avant la skill. Analogue de TDD pour l'agentic. |
| **pass^k** | Métrique : taux de réussite identique sur k runs consécutifs du même cas. Détecte la flakiness probabiliste. Cible : pass^3 ≥ 0.85. |
| **Zero Ambient Authority** | Politique : aucun token, aucune permission par défaut. Chaque appel ré-authentifie avec le scope minimal. |
| **JIT Token Downscoping** | Réduire le scope du token au strict nécessaire *au moment* de l'appel, jamais avant. |
| **Confused Deputy** | Faille : un agent avec des droits élevés est manipulé pour exécuter une action au profit d'un attaquant. Le Vibe Diff la prévient. |
| **Vibe Diff** | Résumé en plain English d'une action sensible présenté à l'humain **avant** exécution, pour consentement. Pré-action. |
| **Vibe Trajectory** | Trace structurée (OpenTelemetry-style) de chaque tour de l'agent, loguée **après** coup pour audit/replay/détection d'Intent Drift. |
| **Intent Drift** | Dérive progressive du comportement d'un agent par rapport à son objectif initial sur plusieurs tours. Détecté via Trajectory. |
| **Trust Decay** | Le score de confiance d'une skill/tool décroît mécaniquement avec le temps si elle n'est pas réévaluée. |
| **Slopsquatting** | Attaque supply-chain : publier un package avec un nom proche d'un nom hallucinable par un LLM, pour qu'il soit installé par un agent. |
| **MCP Spoofing** | Un serveur MCP malveillant imite un serveur légitime pour intercepter les appels. |
| **HITL** (Human-in-the-Loop) | Pattern où un humain valide explicitement chaque action à risque avant exécution. |
| **SDD** (Spec-Driven Development) | "Code is disposable, spec is the source of truth." On régénère le code à partir du spec, pas l'inverse. |
| **BDD** (Behavior-Driven Development) | Spec en langage naturel structuré (Gherkin : Scenario / Given / When / Then). Force le State > Action > Outcome. |
| **Policy Server** | Service qui intercepte les tool calls. 2 couches : **Structural Gating** (YAML deterministe role/env → tool allow/deny) + **Semantic Gating** (LLM-as-judge inspecte le *contenu* de l'appel pour PII/policy). |
| **Context Hygiene** | Pratique : remplacer tout PII/secret par des placeholders `[[VAR]]` résolus au runtime, jamais en dur dans les prompts. |
| **Approval Fatigue** | Burnout des devs qui cliquent "Approve" en réflexe sous le flot de micro-demandes de l'agent. +45 % chez les power-users. |
| **Red / Blue / Green Teaming** | Red attaque, Blue défend (en design), Green mesure en continu post-déploiement. |
| **80 % Problem** | Un agent qui réussit 80 % du temps n'est pas "presque parfait" — il échoue 1 fois sur 5 en prod. Le delta vers 99 % est le vrai travail. |
| **Bounded vs Unbounded** | Outils = bounded (input/output spec strict). Agents = unbounded (boucle ouverte). Choisir le bon niveau d'abstraction. |
| **Read / Draft / Act ladder** | Les skills se classent en 3 niveaux de risque : Read (lecture), Draft (génère sans envoyer), Act (action irréversible). Plus le niveau monte, plus le harness se durcit. |

---

## 8. What this Project is NOT

- **PAS production-ready.** Aucun SLA, aucun monitoring réel. Sandbox.
- **PAS multi-tenant.** Un seul user (toi), une seule entreprise fictive (Marina Rentals).
- **PAS une dépendance externe.** Personne d'autre n'importe ce code.
- **PAS un projet à scaler.** Si une décision augmente la complexité "pour scaler", elle est rejetée.
- **PAS un fork de `bchat`.** `bchat` est ton projet RAG production. Ici on apprend des patterns, on ne réutilise pas de code.
- **PAS un benchmark de frameworks.** Phase 11 (LangChain/LlamaIndex) est une excursion comparative, pas le sujet principal.

---

## 9. When in Doubt

Avant de coder une décision architecturale ou d'ajouter une dépendance :

1. **Lis `PROJECT.MD`** → la phase active a-t-elle déjà cadré la décision ?
2. **Lis le `day{N}.txt`** correspondant à la notion → le cours impose-t-il un pattern ?
3. **Lis ce `CLAUDE.md`** → §4 (rules) et §7 (vocabulary) couvrent-ils le cas ?
4. **Pose une question dans le chat** avant d'écrire 100 lignes de code dans une mauvaise direction.

**Anti-patterns à signaler immédiatement :**
- Une skill sans frontmatter YAML conforme
- Un tool sans schema d'entrée/sortie explicite
- Un tool à side-effect sans Vibe Diff
- Une action qui by-pass le Policy Server "pour aller plus vite"
- Une variable hardcodée qui contient un email, un nom client, un ID
- L'ajout d'une dépendance non listée dans l'AgBOM
- Un commit qui mélange bug fix + renommage + refactor

---

*Dernière révision : voir `git log CLAUDE.md`. Toute modification de §4 ou §7 nécessite une discussion explicite — ce sont les invariants du projet.*
