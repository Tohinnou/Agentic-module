# Specs - Spec-Driven Development

Voir `CLAUDE.md` §3 et `day5.txt` (Spec-Driven Production Grade Development) pour le rationale.

## Convention

- 1 feature = 1 fichier (`.md` pour la prose, `.yaml` pour les structures profondes)
- Format **hybride** : Markdown narratif + YAML pour configs nestees > 3 niveaux
- BDD Gherkin (`Scenario / Given / When / Then`) pour les comportements

## Workflow

1. Ecris/edite le spec.
2. Soumets-le a review (humain ou Critic agent).
3. L'agent genere le code a partir du spec valide - pas l'inverse.
4. Si le spec change -> on regenere, on ne patche pas le code.

> **"Code is disposable. The spec is the source of truth."** - Day 5, Lee Boonstra
