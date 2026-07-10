# Vibe Diff Checklist

## Purpose

Le **Vibe Diff** est la traduction plain-English d'une action risquée
présentée à l'humain **AVANT** exécution, pour consentement éclairé
(§7 CLAUDE.md, Day 4 Pillar 5).

Il combat la **Confirmation Fatigue** (Day 4 : les devs cliquent "Approuver"
en réflexe si les demandes sont trop nombreuses ou trop opaques).

Cette checklist définit :
- **quand** un Vibe Diff est OBLIGATOIRE
- **quand** il est INTERDIT
- **quel format** il doit respecter
- **quels anti-patterns** invalident un Vibe Diff

---

## Quand un Vibe Diff est OBLIGATOIRE

Un Vibe Diff **doit** être généré (aucune exception) dans les cas suivants :

- [x] **Tout tool avec `risk_level: "act"`** — irréversible ou observable
      externement. Exemples : `create_ticket`, `send_message` (hypothétique
      Phase 7), `delete_record` (hypothétique).

- [x] **Draft en conflit avec les sources citées** — Semantic Gate détecte
      `policy_conflict`. L'humain doit valider l'override.

- [x] **PII détectée en dur dans le payload** — `pii_leak_risk`. L'humain
      décide : résoudre en `[[VAR]]` placeholder, ou continuer (dev/test).

- [x] **Exclusion sélective avec justification** —
      `exclusion_with_business_context`. L'humain valide la légitimité
      opérationnelle de la séparation.

- [x] **Toute décision Semantic Gate qui produit `hitl_required`** —
      même si la catégorie exacte n'est pas dans la liste ci-dessus.

## Quand un Vibe Diff est INTERDIT

Ne **jamais** générer de Vibe Diff dans les cas suivants :

- [ ] **Verdict BLOCK** — le refus est final, pas de review humaine.
      L'humain ne peut PAS approuver après un BLOCK. Les faux positifs
      BLOCK passent par un canal séparé (audit / recours), pas par HITL.

- [ ] **Verdict ALLOW** — aucune friction sur les cas nominaux (~95 % du
      trafic).

- [ ] **Retry après HITL rejeté** — la première décision humaine tient.
      Un retry avec le même payload est bloqué au niveau orchestrator.

---

## Format d'un Vibe Diff

Un Vibe Diff est un **texte court** conforme aux contraintes :

- **≤ 5 lignes** de contenu principal
- **≤ 350 caractères** au total (mesure ferme, testée dans le contrat)
- **Structure imposée** :
  1. **Ligne 1** — Ce qui va se passer : verbe d'action + objet concret
  2. **Lignes 2-3** — Le point d'attention : pourquoi la machine hésite
  3. **Ligne 4** — Ce que l'humain doit décider : Approuve / Rejette

Un Vibe Diff qui dépasse 350 caractères viole le contrat — le générateur
doit tronquer les détails ou déléguer à un lien "voir contexte complet".

---

## Templates par catégorie

### Template `act_tool_default_hitl`

```
Action : {verbe} {objet} pour {audience}.
Détails : {champ_1}={valeur_1}, {champ_2}={valeur_2}.
⚠ Cette action est irréversible.
[Approuver] [Rejeter]
```

**Exemple concret** :
```
Action : créer un ticket support pour Jean Dupont.
Détails : catégorie=annulation, priorité=urgent, message="Client demande annulation dans 48h".
⚠ Cette action modifie la base de données.
[Approuver] [Rejeter]
```

### Template `policy_conflict`

```
Draft proposé : {résumé_1_ligne}.
Politique citée ({source}) : {ce_que_dit_la_politique}.
Ces deux points sont en désaccord.
[Approuver le draft] [Rejeter et refaire]
```

**Exemple** :
```
Draft proposé : remboursement intégral pour annulation à 22h hier.
Politique refund_policy.md : "annulation <24h = 0% sauf force majeure".
Ces deux points sont en désaccord.
[Approuver] [Rejeter]
```

### Template `pii_leak_risk`

```
Payload contient : {liste_pii_detectees} en clair.
Convention : ces valeurs devraient être des placeholders [[VAR]].
Contexte : {si_test_dev_ok, sinon_rejeter}.
[Approuver] [Rejeter et corriger]
```

### Template `exclusion_with_business_context`

```
Filtre demandé : exclure {catégorie}.
Raison offerte : {citation_user_message}.
Cette exclusion modifie le rapport final.
[Approuver l'exclusion] [Rapport complet à la place]
```

---

## Anti-patterns interdits

Un Vibe Diff qui contient ces éléments est **invalide** et sera rejeté par
le générateur :

- ❌ **Dump du payload complet** — l'humain doit voir le SENS, pas le JSON
      brut. Un Vibe Diff qui affiche `{"customer_name":"J.Dupont", "priority":"urgent", ...}` est cassé.

- ❌ **Jargon technique non-résolu** — `tool: draft_reply` → traduire en
      "rédiger un mail". `payload.category=cancellation` → "annulation".

- ❌ **Options non-actionables** — pas de "Voir plus", "Consulter les logs",
      "Revenir plus tard". Chaque option doit avoir une **conséquence
      immédiate** (approuver = tool s'exécute, rejeter = tool ne
      s'exécute pas).

- ❌ **Longueur > 5 lignes ou > 350 caractères** — au-delà, l'humain ne lit
      plus et clique en réflexe = Confirmation Fatigue.

- ❌ **Question ambiguë** — "Ceci va bien ?" ou "Continuer ?". Un Vibe Diff
      doit décrire l'action précise et proposer des choix clairs.

---

## Contrat testable

Le générateur `vibe_diff.generate()` doit satisfaire :

- **Output ≠ None** si et seulement si verdict == `hitl_required`
- **len(output) ≤ 350** caractères (assertion dans les tests)
- **len(output.split('\n')) ≤ 5** lignes principales
- **output contient au moins deux options** entre `[…]` (Approuver / Rejeter)
- **output ne contient jamais** de JSON brut du payload (regex negative)

Ces contraintes sont testées dans `tests/test_policy_server.py`.
