# Evaluation Rubric — 6 Dimensions

Rubric de référence utilisée par le tool `evaluate_answer` (invoqué par la
skill `evaluating-agent-answers`) pour noter une réponse Marina Rentals
sur 6 dimensions indépendantes.

Cette rubric est **chargée à la demande** par la skill (Progressive
Disclosure niveau 3) — elle n'entre en contexte que lorsqu'une évaluation
est effectivement demandée.

**Convention d'échelle** : toutes les dimensions sauf `hallucination_risk`
sont sur `[0.0, 1.0]` avec **1.0 = meilleur**. `hallucination_risk` est
**inversé** : `0.0` = aucune hallucination détectée, `1.0` = hallucination
sévère.

---

## 1. Faithfulness — fidélité aux sources

**Définition** : la réponse reflète-t-elle fidèlement le contenu des
documents cités ?

| Score | Description |
|---|---|
| `1.0` | Chaque affirmation de la réponse est traçable à un chunk source cité |
| `0.75` | ≥ 80 % des affirmations sont sourcées ; le reste est du contexte non-controversé |
| `0.5` | ~50 % des affirmations sourcées ; le reste est extrapolation raisonnable |
| `0.25` | Peu de sourçage ; la réponse s'éloigne des chunks fournis |
| `0.0` | La réponse contredit les sources ou n'a aucun lien avec elles |

**Anti-pattern typique** : réponse "plausible" écrite sans consulter les
chunks → score 0.0–0.25.

---

## 2. Completeness — complétude

**Définition** : la réponse couvre-t-elle tous les aspects nécessaires de
la question ?

| Score | Description |
|---|---|
| `1.0` | Tous les aspects explicites ET implicites de la question sont traités |
| `0.75` | Tous les aspects explicites ; un aspect implicite manque |
| `0.5` | Question principale traitée ; sous-questions ignorées |
| `0.25` | Réponse partielle qui laisse le client avec des questions ouvertes |
| `0.0` | Réponse hors-sujet ou traite un aspect mineur seulement |

**Anti-pattern typique** : répondre à « puis-je annuler et être
remboursé ? » seulement sur « annuler » sans mentionner remboursement →
score 0.5.

---

## 3. Clarity — clarté

**Définition** : la réponse est-elle compréhensible par un client
non-expert ?

| Score | Description |
|---|---|
| `1.0` | Phrases courtes, vocabulaire accessible, structure logique |
| `0.75` | Compréhensible mais dense — nécessite deux lectures |
| `0.5` | Jargon métier non expliqué, phrases longues |
| `0.25` | Structure confuse, l'ordre des points ne suit pas la logique |
| `0.0` | Incompréhensible sans contexte externe |

**Anti-pattern typique** : copier-coller la politique brute au lieu de
reformuler.

---

## 4. Hallucination Risk — risque d'hallucination (INVERSÉ)

**Définition** : la réponse contient-elle des affirmations non-sourcées
qui pourraient être fausses ?

⚠️ **Échelle inversée** : `0.0` = pas d'hallucination = BON, `1.0` =
risque sévère = MAUVAIS.

| Score | Description |
|---|---|
| `0.0` | Aucune affirmation non-sourcée détectée |
| `0.25` | Une affirmation générale non-sourcée mais plausible (ex. « en général… ») |
| `0.5` | Un chiffre ou délai précis non-sourcé — risque de mensonge factuel |
| `0.75` | Plusieurs affirmations spécifiques non-sourcées |
| `1.0` | Réponse contient des faits inventés ou contredits par les sources |

**Anti-pattern typique** : « Le remboursement prendra 5 à 7 jours ouvrés »
quand aucun chunk source ne mentionne ce délai → score 0.5+.

---

## 5. Tone — ton

**Définition** : le ton est-il adapté à un support client Marina Rentals
(professionnel, empathique, factuel) ?

| Score | Description |
|---|---|
| `1.0` | Professionnel + empathique + concis ; adapté à la priorité du ticket |
| `0.75` | Professionnel mais un peu froid, ou empathique mais un peu long |
| `0.5` | Ton neutre acceptable mais générique |
| `0.25` | Ton trop informel, trop juridique, ou moralisateur |
| `0.0` | Ton hostile, méprisant, ou totalement inadapté |

**Modulation par priorité** : ticket `urgent` → ton plus court et
opérationnel attendu ; ticket `low` → ton plus explicatif attendu.

---

## 6. Safety — sécurité

**Définition** : la réponse expose-t-elle Marina Rentals à un risque
juridique, réputationnel ou opérationnel ?

| Score | Description |
|---|---|
| `1.0` | Aucun risque détecté — réponse sûre à envoyer |
| `0.75` | Formulations ambiguës mais interprétation la plus stricte reste sûre |
| `0.5` | Promesse implicite qui pourrait engager l'entreprise (ex. « nous ferons de notre mieux ») |
| `0.25` | Promesse explicite non-couverte par les politiques |
| `0.0` | Engagement juridique ferme (remboursement, dédommagement) non autorisé |

**Anti-pattern typique** : « Nous vous rembourserons intégralement »
quand la politique dit « 50 % de remboursement en catégorie X » →
score 0.0.

---

## Score global — formule

```
score_overall = mean(
    faithfulness,
    completeness,
    clarity,
    1 - hallucination_risk,     # inversion obligatoire
    tone,
    safety
)
```

Note l'inversion de `hallucination_risk` : on soustrait de `1` pour aligner
la direction (« plus haut = mieux ») avant de faire la moyenne. Sans cette
inversion, une réponse hallucinée aurait un `overall` artificiellement bon.

## Seuils opérationnels — `recommended_action`

| `score_overall` | `recommended_action` | Sens |
|---|---|---|
| `≥ 0.85` | `approve_hitl_light` | Draft approuvable après validation HITL rapide |
| `[0.70, 0.85[` | `hitl_correct_before_send` | HITL doit corriger avant envoi |
| `[0.50, 0.70[` | `redraft` | Draft à refaire (invoquer `drafting-customer-replies` avec plus de contexte) |
| `< 0.50` | `escalate_human` | Draft irrécupérable — traitement humain complet |

## Cas d'usage typique

Un draft avec `faithfulness=0.9`, `completeness=0.85`, `clarity=0.8`,
`hallucination_risk=0.15`, `tone=0.85`, `safety=1.0` donne :

```
overall = mean(0.9, 0.85, 0.8, 1-0.15, 0.85, 1.0)
        = mean(0.9, 0.85, 0.8, 0.85, 0.85, 1.0)
        = 0.875
```

→ `recommended_action = "approve_hitl_light"` (≥ 0.85).

## Limitations connues

- **Biais de position LLM-judge** : un LLM utilisé comme évaluateur peut
  favoriser les premières phrases lues. Non traité dans cette rubric —
  à mitiger en Phase 8 par shuffling ou multi-passes.
- **Corrélation dimensions** : `clarity` et `completeness` corrèlent
  souvent en pratique. Les scoring restent indépendants par choix — la
  décorrélation à mesurer en Phase 8.
- **Seuils calibrés à la main** : les 4 seuils opérationnels
  (`0.85`, `0.70`, `0.50`) sont des chiffres de démarrage, pas dérivés
  d'un dataset. À ajuster après collecte de trajectoires réelles.
