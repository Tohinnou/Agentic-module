# Evals - Evaluation-Driven Development

Voir `CLAUDE.md` §6 pour les 5 patterns d'evaluation et `PROJECT.MD` Phase 8 pour la roadmap.

## Fichiers attendus

- `golden.yaml` - Golden Dataset en BDD Gherkin (20-50 cas)
- `adversarial.yaml` - Prompt injection, jailbreaks, MCP spoofing
- `judge_prompts.md` - Prompts du LLM-as-Judge (Evaluator Agent)
- `skill_trigger_cases.yaml` - Cas de test pour le declenchement des skills

## Cibles

- `pass^3 >= 0.85` sur le golden dataset
- `trigger accuracy >= 0.90` sur les skills
- 100 % de refus correct sur l'adversarial

## Discipline EDD

L'eval est ecrite **avant** la skill, jamais apres.
Si tu te surprends a ecrire d'abord la skill puis l'eval : stop, recommence.
