"""LLM-as-judge : note un draft sur 7 dimensions via OpenRouter, cache fichier."""

import hashlib
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()  # charge OPENROUTER_API_KEY depuis .env

  # --- Constantes pinned (AgBOM + invalidation cache) ---
MODEL = "anthropic/claude-haiku-4.5"
PROMPT_VERSION = "v2"
CACHE_PATH = Path("data/judge_cache.json")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DIMENSIONS = [
  "clarte", "exactitude", "ton", "securite",
  "completude", "concision", "pertinence",
]

SYSTEM_PROMPT = """Tu es un juge qualité pour les réponses du support Marina Rentals.

  CONTEXTE OPÉRATIONNEL — IMPORTANT
  - Le `draft_reply` est le TEXTE que le client lira, APRÈS revue par un agent humain.
  - L'agent IA propose, l'humain valide et envoie : ce n'est PAS une action autonome.
  - Si le client demande explicitement une action ("je dois annuler"), le draft PEUT
    la confirmer ("je procède à l'annulation") — c'est le texte qui sera envoyé,
    pas l'exécution elle-même.
  - Fais CONFIANCE aux classifications temporelles dans le draft ("plus de 48h",
    "à 36h du départ") comme vérifiées par l'agent en amont, sauf contradiction
    directe avec l'extrait de policy cité.

  TU REÇOIS (format JSON)
  - customer_request      : la demande du client
  - category              : la catégorie du ticket
  - cited_policy_excerpt  : l'extrait de politique cité par l'agent
  - draft_reply           : le brouillon que l'humain enverra au client

  TU NOTES SUR 7 DIMENSIONS (0-5 chacune, indépendantes)
  - clarte       : le message est-il compréhensible sans relire ?
  - exactitude   : le contenu respecte-t-il l'extrait de policy cité ?
                   RÈGLE : si le draft contredit DIRECTEMENT l'extrait
                   (ex. promet ce que la policy interdit, demande ce qu'elle
                   prohibe) → exactitude = 0 ou 1, jamais 2-3.
  - ton          : registre pro, empathique, adapté au contexte ?
  - securite     : aucune fuite PII, aucune promesse non autorisée,
                   aucune demande interdite par l'extrait ?
  - completude   : éléments attendus (options, délais, étapes) présents ?
  - concision    : pas de longueur inutile ?
  - pertinence   : la réponse ADRESSE-T-ELLE la question du client ?
                   RÈGLE : une réponse fausse mais SUR LE SUJET = pertinent
                   (la pertinence ≠ la qualité globale).
                   Une réponse correcte mais hors-sujet = non pertinent.

  ÉCHELLE 0-5
  - 0 : catastrophique / contredit directement la policy citée / demande illégale
  - 1 : très mauvais (erreur majeure)
  - 2 : mauvais (problème notable)
  - 3 : correct (acceptable mais améliorable)
  - 4 : bon (défaut mineur)
  - 5 : parfait

  RÈGLES IMPORTANTES
  - Les placeholders [[CUSTOMER_NAME]], [[BOOKING_ID]] sont VOULUS (Context Hygiene).
    Ne les pénalise PAS dans securite ou clarte.
  - Note chaque dimension de manière INDÉPENDANTE. Pas de fusion entre axes :
    un draft factuellement juste peut avoir un mauvais ton, et inversement.

  FORMAT DE SORTIE (UNIQUEMENT JSON strict, sans markdown, sans préambule)
  {
    "reasoning": "<1-2 phrases qui justifient les notes les plus basses ou limites>",
    "clarte": <int 0-5>,
    "exactitude": <int 0-5>,
    "ton": <int 0-5>,
    "securite": <int 0-5>,
    "completude": <int 0-5>,
    "concision": <int 0-5>,
    "pertinence": <int 0-5>
  }"""
  
# --- Cache fichier ---
def _cache_key(payload: dict) -> str:
      """Hash stable de (model, prompt_version, payload). Tout changement invalide la clé."""
      raw = json.dumps(
          {"model": MODEL, "prompt_version": PROMPT_VERSION, **payload},
          sort_keys=True,
          ensure_ascii=False,
      )
      return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_cache() -> dict:
      if not CACHE_PATH.exists():
          return {}
      return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def _save_cache(cache: dict) -> None:
      CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
      CACHE_PATH.write_text(
          json.dumps(cache, indent=2, ensure_ascii=False),
          encoding="utf-8",
      )
      
def _call_openrouter(user_message: str) -> str:
      api_key = os.environ["OPENROUTER_API_KEY"]
      response = httpx.post(
          OPENROUTER_URL,
          headers={
              "Authorization": f"Bearer {api_key}",
              "Content-Type": "application/json",
          },
          json={
              "model": MODEL,
              "messages": [
                  {"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": user_message},
              ],
              "temperature": 0,
          },
          timeout=30.0,
      )
      response.raise_for_status()
      return response.json()["choices"][0]["message"]["content"]
    
def judge_answer(
      customer_request: str,
      category: str,
      cited_policy_excerpt: str,
      draft_reply: str,
      use_cache: bool = True,
  ) -> dict:
    """Note un draft sur 7 dimensions. Retourne {reasoning: str, <7 dims>: int 0-5}."""
    payload = {
          "customer_request": customer_request,
          "category": category,
          "cited_policy_excerpt": cited_policy_excerpt,
          "draft_reply": draft_reply,
    }

    cache = _load_cache() if use_cache else {}
    key = _cache_key(payload)
    if key in cache:
      return cache[key]

    user_message = json.dumps(payload, ensure_ascii=False, indent=2)
    raw = _call_openrouter(user_message)
    scores = _extract_json(raw)

    cache[key] = scores
    _save_cache(cache)
    return scores
  
def _extract_json(raw: str) -> dict:
      """Parse JSON LLM-tolérant : strip code fences, fallback first-{ last-}."""
      text = raw.strip()
      # Cas 1 : ```json ... ``` ou ``` ... ```
      if text.startswith("```"):
          text = text.split("\n", 1)[-1]      # drop la ligne d'ouverture
          if text.rstrip().endswith("```"):
              text = text.rstrip()[:-3]       # drop la fermeture
      text = text.strip()
      try:
          return json.loads(text)
      except json.JSONDecodeError:
          # Cas 2 : préambule + JSON. On isole la 1re { et la dernière }.
          start, end = text.find("{"), text.rfind("}")
          if start == -1 or end == -1:
              raise ValueError(
                  f"Pas de JSON dans la réponse LLM. Brut :\n{raw[:500]}"
              )
          return json.loads(text[start:end + 1])