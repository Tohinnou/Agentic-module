# Golden Dataset — contrat de scope (Phase 8.1)

> Contrat human-editable qui précède `evals/golden.yaml` (SDD : la spec est la source
> de vérité, le YAML l'implémente). Analogue de `meta/intent_drift_signals.md` pour la
> Phase 7. À lire avant d'ajouter/modifier un cas golden.

---

## 1. Ce que ce dataset garde

Le **Golden Dataset** est le filet de régression **déterministe** du `SupportAgent` :
« pour ce ticket, l'agent DOIT produire *ce geste* ». Il matérialise le pattern
`eval_as_unit_test` de CLAUDE.md §6 — le seul des 5 patterns qui est vrai/faux, offline,
sans LLM.

**Dette EDD assumée.** L'EDD dit « eval *avant* skill ». Ici les skills existent depuis
la Phase 5 : ce golden est donc *rétrospectif* pour l'existant — on rembourse la dette.
Sa vraie valeur *forward* arrive au **canary** (Phase 8.5) : le jour où on modifie une
skill, ce golden devient le filet anti-régression.

**Le 80% Problem, rendu visible.** Un agent juste 4 fois sur 5 *a l'air* de marcher.
Ce dataset est l'instrument qui mesure ce 5ᵉ échec avant qu'il n'atteigne la prod.

---

## 2. La surface comportementale (déterministe vs probabiliste)

`SupportAgent.run(question) -> SupportResponse`. Ligne de partage nette entre les champs
**golden-assertables** (déterministes) et le reste :

| Champ de `SupportResponse` | Origine | Golden ? | Pourquoi |
|---|---|---|---|
| `category` | `classify_text` (keyword argmax) | ✅ | dérivable à la main depuis `CATEGORY_KEYWORDS` |
| `priority` | `compute_priority` (règles 2-axes) | ✅ | fonction pure de (catégorie, mots-clés) |
| `placeholders` (non-vide) | `extract_placeholders(template)` | ✅ | template statique par catégorie |
| `policy_doc_id` | `retrieve_docs` **BM25 top-1** | ⚠️ | **empirique** — non dérivable, à vérifier en run (voir §5) |
| `tone` | `select_tone(category, priority)` | ➖ | déterministe **mais non exposé** sur `SupportResponse` → déjà couvert par `test_draft_reply.py` (unit) — pas rejoué ici |
| `answer` (draft brut) | template statique | ❌ | c'est le *texte* ; sa **qualité** = judge |
| `evaluation` | LLM-as-judge | ❌ | probabiliste → `evals/judge_golden.yaml` (Phase 8.3) |
| `trajectory` | trace des tools | ➖ | assertable (séquence/statuts) mais déjà couvert par `test_orchestrator.py` — pas rejoué ici |

**Point clé** : `draft_reply` ne dépend **que** de (catégorie, priorité). Il n'insère pas
le contenu retrieval — `policy_doc_id` reste un champ d'audit. `tone` est donc aussi
déterministe que `category`/`priority`, mais comme il ne remonte pas sur `SupportResponse`
(il vit dans `DraftReplyOutput`, déjà testé unitairement), le golden ne le rejoue pas :
un golden n'assert que la **sortie observable** de `run()`.

---

## 3. Champs assertés par un cas golden

```yaml
assertable_fields:
  category:            # enum 8 : cancellation|payment|booking|safety|weather|equipment|damage|other
    kind: exact
    derivation: "argmax de |tokens ∩ CATEGORY_KEYWORDS[cat]|, tie → ordre du dict, 0 hit → other"
  priority:            # enum 4 : urgent|high|normal|low
    kind: exact
    derivation: "compute_priority(category, matched, tokens) — voir classification/rules.py"
  policy_doc_id:       # stem d'un des 10 .md de docs/
    kind: exact
    derivation: "BM25 top-1 — VÉRIFIÉ EN RUN, jamais deviné (voir §5)"
  placeholders_nonempty:
    kind: boolean
    derivation: "len(placeholders) > 0 — HITL fail-safe : un draft a toujours des [[VAR]]"
```

---

## 4. Hors-scope (délégué, pas oublié)

| Hors-scope ici | Où c'est couvert |
|---|---|
| Qualité/ton *rédactionnel* du draft (score 0-5) | `evals/judge_golden.yaml` — LLM-as-Judge (8.3) |
| Refus sur injection / jailbreak | `evals/adversarial.yaml` (8.2 agent) + `adversarial_policy.yaml` (gate, P6) |
| Décision du Policy Server (allow/block/hitl) | `test_policy_server*.py` + `adversarial_policy.yaml` (P6) |
| Déclenchement de skill (trigger accuracy) | `evals/skill_trigger_cases.yaml` (8.2) |
| Intent Drift post-hoc | `evals/drift_cases.yaml` (P7) |

Un cas golden qui commence à asserter la *chair* du draft (« la phrase X doit apparaître »)
est un signal de dérive : c'est le job du judge. On garde le golden sur le **squelette**.

---

## 5. Golden = comportement VOULU, pas comportement OBSERVÉ

Principe non négociable de ce dataset (c'est ce qui le distingue d'une characterization) :

- `category`, `priority`, `tone`, `placeholders` : dérivés des **règles** → l'attendu est
  *connaissable* sans lancer l'agent. On l'écrit à la main.
- `policy_doc_id` : sort de BM25, **non dérivable**. Procédure :
  1. on écrit l'attendu = le doc **sémantiquement correct** (l'intention),
  2. on **lance** l'agent,
  3. si BM25 renvoie ce doc → cas vert.
  4. si BM25 renvoie un autre doc → **c'est un finding** (gap retrieval), à documenter dans
     le backlog / `learning_notes.md`, **jamais** à ré-encoder en douce comme « golden ».

> Bénir le mauvais doc en « golden », c'est de la characterization déguisée : le test
> passe au vert en gelant un bug. On perd exactement ce que le 80% Problem veut exposer.

---

## 6. Schéma d'un cas (BDD Gherkin en YAML)

```yaml
- id: <kebab-case unique>
  scenario: "<résumé State > Action > Outcome en une ligne>"
  given: "<état initial en langage naturel>"
  when:
    question: "<le message client passé à run()>"
  then:
    category: <enum>
    priority: <enum>
    policy_doc_id: <stem>            # l'INTENTION — le doc sémantiquement correct (§5)
    placeholders_nonempty: true
  retrieval_status: confirmed|gap    # BM25 top-1 satisfait-il l'intention AUJOURD'HUI ?
  observed_doc: <stem>               # présent seulement si gap — ce que BM25 renvoie réellement
  notes: "<pourquoi cet attendu ; tie-break éventuel ; description du finding si gap>"
```

Chaque cas est **additif-by-append** : un bloc = un contrat signé. On ajoute des cas, on
ne réécrit jamais un cas existant (sinon on invalide l'historique de régression).

**`retrieval_status` pilote le test** (voir `tests/test_golden.py`) : un cas `gap` est marqué
`xfail(strict=True)` sur l'assertion `policy_doc_id`. Quand le retrieval sera corrigé, le cas
passera *XPASS* → pytest le signalera en échec → on flippe `gap` → `confirmed`. Scoreboard
auto-nettoyant du fix retrieval.

---

## 7. Runner & config

```yaml
runner:
  instantiation: 'SupportAgent(enforce_policy=False, evaluate=False, session_id=<case_id>)'
  enforce_policy: false   # la gouvernance a ses propres evals (P6) — on isole le comportement
  evaluate: false         # pas d'appel LLM juge — golden = 100% offline/déterministe
  network: none
```

Pourquoi `enforce_policy=False` : le golden teste *ce que l'agent décide de faire*, pas
*ce que le gate autorise*. Mélanger les deux couplerait le filet comportemental à la
gouvernance (déjà testée ailleurs). Même choix que `test_orchestrator.py`.

---

## 8. pass^k — sémantique correcte

`pass^k` = **même input × k runs × seed identique**, fraction des runs qui reproduisent le
même pass. **Pièges** (à ne pas confondre) :

- ❌ « moyenne sur k *reformulations* de la question » → ça mesure la robustesse au
  paraphrasage, pas la flakiness.
- ❌ seed/température qui bougent entre runs → on ne mesure plus la reproductibilité.

Sur ce golden **déterministe**, `pass^k = 1.0` par construction (aucune source d'aléa).
Le harness pass^k y sert de **garde de déterminisme** : s'il flanche un jour, c'est qu'une
non-déterminisme a fui (itération de `set`, ordre de dict, horloge). Les vraies *dents* de
pass^k arrivent en **8.3** (judge LLM, où `pass^3 ≥ 0.85` de CLAUDE.md §6 prend son sens).

---

*Phase 8.1 — révision : voir `git log meta/golden_dataset_spec.md`.*
