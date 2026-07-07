---
name: answering-support-questions
description: |
  Répond aux questions utilisateur sur les politiques Marina Rentals
  (annulation, réservation, paiement, sécurité, météo, équipement,
  remboursement, escalation, privacy) en citant docs/. Refuse si absent.
version: 0.1.0
license: MIT
allowed-tools:
  - retrieve_docs
---

# Skill : Answering Support Questions

Procédure documentée pour répondre à toute question utilisateur portant sur
les **politiques internes Marina Rentals** (`docs/`).

Niveau d'autorité : **read-only**. Cette skill ne rédige aucun message adressé
à un client, ne crée aucun ticket, ne modifie rien.

---

## Quand cette skill s'active (trigger)

Le message utilisateur ressemble à une **question sur une règle interne** :

- « Quelles sont les conditions d'annulation ? »
- « Est-ce que je peux annuler à cause de la météo ? »
- « Combien de temps ai-je pour payer après réservation ? »

Indice syntaxique typique : verbe interrogatif (`quel`, `comment`,
`est-ce que`, `puis-je`, `y a-t-il`) + thème correspondant à un des 10
docs de `docs/`.

## Quand NE PAS invoquer cette skill

- L'utilisateur demande de **rédiger** un message client → `drafting-customer-replies`.
- L'utilisateur demande de **noter** une réponse existante → `evaluating-agent-answers`.
- L'utilisateur demande un **rapport agrégé** → `generating-weekly-report`.
- L'utilisateur demande une **action** (réserver, envoyer, annuler pour lui) → aucune skill : renvoyer au HITL.
- La question porte sur un **domaine hors Marina Rentals** (physique, cuisine, actualités) → refuser au routeur.
- Le contexte est purement **conversationnel** (bonjour, merci) → ne rien faire.

## Procédure — les 5 étapes

1. **Reformuler la question intérieurement** pour extraire les mots-clés
   (ex. « annuler à cause météo » → `{ theme: cancellation, condition: weather }`).

2. **Invoquer `retrieve_docs`** avec `top_k=3` sur la question reformulée.

3. **Filtrer les chunks** dont le score TF-IDF/BM25 < seuil (défaut `0.15`).
   Si aucun chunk ne passe le seuil → **refuser** (voir §Cas de refus).

4. **Composer la réponse** :
   - Une phrase directe qui répond à la question.
   - Une citation explicite des sources sous la forme `[source: nom_fichier.md]`.
   - Ne rien ajouter qui ne soit pas dans les chunks retournés (Context Hygiene, §4 règle 6).

5. **Rendre la sortie structurée** :

   ```json
   {
     "answer": "…",
     "sources": ["cancellation_policy.md", "weather_policy.md"],
     "chunks_used": ["chunk_id_1", "chunk_id_2"],
     "confidence": 0.87,
     "refused": false
   }
   ```

## Cas de refus

Si aucun chunk ne passe le seuil, ou si la question est manifestement hors
domaine :

> « Je n'ai pas trouvé cette information dans nos politiques internes.
>   Contactez le support à `[[SUPPORT_EMAIL]]` pour un traitement dédié. »

Retour structuré :

```json
{
  "answer": null,
  "sources": [],
  "refused": true,
  "refusal_reason": "no_source_matched" | "out_of_scope"
}
```

**Interdit** : inventer un chiffre, un délai ou une politique absents des
sources. Toute PII (email, téléphone, ID) reste en placeholder `[[VAR]]`
résolu au runtime — jamais en dur (§4 règle 6).

## Tools autorisés

Le frontmatter verrouille : **`retrieve_docs` uniquement**.

Si le raisonnement conduit à vouloir appeler `create_ticket`, `draft_reply`
ou tout autre tool → c'est un signal que la skill a été mal déclenchée.
Le routeur doit être corrigé, pas la skill élargie.

## Références (Progressive Disclosure niveau 3)

À créer à la demande dans `references/` :

- `policy_index.md` — mapping keyword → doc de `docs/`. Utile quand la
  question est ambiguë (« puis-je annuler ? » → cancellation vs refund).
- `refusal_phrasings.md` — variantes de refus selon le ton (urgent, VIP,
  standard). Utile si la sortie doit être adaptée au contexte du ticket.

À créer à la demande dans `assets/` :

- `answer_template.md` — squelette Markdown pour la réponse si les callers
  attendent un format riche (Markdown, HTML) plutôt que du JSON brut.

## Contrat de sortie (invariants)

- **`refused == true` ⇒ `answer == null`** — pas de réponse partielle si refus.
- **`sources` non vide ⇒ chaque nom de fichier existe dans `docs/`** — pas
  d'hallucination de nom de source.
- **`confidence ∈ [0.0, 1.0]`** — la valeur reflète le score retrieval du
  meilleur chunk utilisé, pas une auto-évaluation LLM.

## Éval

Voir `eval_cases.json` — 10 positifs + 8 négatifs.
Cible : **trigger accuracy ≥ 0.90**, **false positive ≤ 0.10**.
