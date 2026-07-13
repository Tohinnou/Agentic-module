"""Abstraction LLMProvider — le point de bascule unique mock ↔ réseau (Phase 8.3).

Pourquoi ce module. Deux sites d'appel LLM (`evaluation/judge.py`,
`policy_server/semantic_gate.py`) étaient câblés EN DUR sur OpenRouter, et
`LLM_PROVIDER` était grep-zero : le chemin `mock (offline)` que CLAUDE.md §2
DÉCLARE comme défaut du stack n'existait pas. Ce module comble l'écart entre le
contrat de stack et la réalité — il ne rajoute pas de complexité « pour scaler »,
il livre ce qui était promis.

Modèle deux-tiers (voir meta/learning_notes.md) :
- MockLLMProvider    : déterministe, offline. Rend le harness d'éval REJOUABLE
                       (garde pass^k + plomberie parsing/cache). Il ne fait
                       AUCUNE promesse sémantique — ne juge pas, ne bloque pas.
- OpenRouterProvider : appel réseau réel (opt-in, coût). Teste le discernement.

Leçon 8.1 récursée d'un cran : le mock ne rend pas le juge intelligent, il rend
son harness testable hors-ligne. Le squelette est déterministe, la chair non.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Protocol

import httpx
from dotenv import load_dotenv

load_dotenv()  # charge OPENROUTER_API_KEY / LLM_PROVIDER depuis .env

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"

# Les 7 dimensions du juge, dupliquées ici VOLONTAIREMENT : le mock reste
# autonome, sans importer evaluation.judge — évite tout cycle d'import.
_JUDGE_DIMS = (
    "clarte", "exactitude", "ton", "securite",
    "completude", "concision", "pertinence",
)


class LLMProvider(Protocol):
    """Contrat minimal : une complétion chat (system + user) → texte brut."""

    def complete(self, system: str, user: str) -> str: ...


class OpenRouterProvider:
    """Provider réseau. Extrait le pattern httpx commun aux 2 call sites.

    Fail-hard si OPENROUTER_API_KEY absent : un provider réseau sans clé est une
    erreur de config, pas un cas nominal. Le fallback offline s'obtient
    EXPLICITEMENT via LLM_PROVIDER=mock, jamais par défaut silencieux.
    """

    def __init__(self, model: str = DEFAULT_MODEL, *, temperature: float = 0.0) -> None:
        self.model = model
        self.temperature = temperature

    def complete(self, system: str, user: str) -> str:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY absent — OpenRouterProvider ne peut pas "
                "fonctionner. Utilise LLM_PROVIDER=mock pour le chemin offline."
            )
        response = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": self.temperature,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class MockLLMProvider:
    """Provider offline déterministe. AUCUNE promesse sémantique.

    Détecte la tâche via un marqueur du system prompt et renvoie une réponse
    (1) VALIDE — parsable par le caller — et (2) DÉTERMINISTE — même (system,
    user) → sortie identique. Les valeurs dérivent d'un hash stable de l'entrée :
    elles varient d'un cas à l'autre (pour que la garde pass^k ne soit pas un
    no-op) mais restent reproductibles. Elles NE REFLÈTENT AUCUN jugement.
    """

    def complete(self, system: str, user: str) -> str:
        if self._is_judge_task(system):
            return json.dumps(self._judge_scores(user), ensure_ascii=False)
        # Fallback générique : un objet JSON minimal, toujours parsable. Le
        # responder du Semantic Gate s'ajoutera quand on câblera ce 2e site.
        return json.dumps({"mock": True}, ensure_ascii=False)

    @staticmethod
    def _is_judge_task(system: str) -> bool:
        """Vrai si le prompt système est celui du juge (≥ 6 des 7 dims présentes)."""
        s = system.lower()
        return sum(dim in s for dim in _JUDGE_DIMS) >= 6

    @staticmethod
    def _judge_scores(user: str) -> dict:
        """7 notes déterministes dans [0,5], dérivées de bytes distincts du hash."""
        digest = hashlib.sha256(user.encode("utf-8")).digest()
        scores = {dim: digest[i] % 6 for i, dim in enumerate(_JUDGE_DIMS)}
        return {"reasoning": "mock: déterministe, non sémantique", **scores}


_PROVIDERS = {
    "mock": MockLLMProvider,
    "openrouter": OpenRouterProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    """Résout le provider : arg explicite > env LLM_PROVIDER > défaut 'mock'.

    Défaut 'mock' = contrat de stack CLAUDE.md §2 (offline-first). Le réseau est
    un opt-in explicite (LLM_PROVIDER=openrouter), jamais un effet de bord.
    """
    resolved = (name or os.environ.get("LLM_PROVIDER") or "mock").strip().lower()
    if resolved not in _PROVIDERS:
        raise ValueError(
            f"LLM_PROVIDER inconnu : {resolved!r}. "
            f"Providers disponibles : {sorted(_PROVIDERS)}."
        )
    return _PROVIDERS[resolved]()
