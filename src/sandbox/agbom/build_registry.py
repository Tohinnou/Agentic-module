"""Builder du tool_registry — la slice "tools" de l'AgBOM (Agent Bill of Materials).

Idée centrale : on importe les 6 modules tools, on lit leur `TOOL_METADATA`
(source de vérité côté code), on l'enrichit avec le chemin du module + des
métadonnées de build (timestamp, version Python, version générateur), on trie
deterministiquement (risk_level → name), et on retourne un `dict` propre.

Deux entry points :
  - `build_registry()` : fonction pure, testable, retourne le dict en mémoire.
  - `python -m sandbox.agbom.build_registry` : dump `meta/tool_registry.json`.

Le split fonction/CLI est volontaire (cf. learning_notes) — les tests tapent
`build_registry()` direct, sans dépendre du JSON sur disque.
"""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Liste figée des modules tools à inventorier. C'est la *seule* source de
# vérité pour "quels tools existent dans le projet". Si on ajoute un 7e tool,
# il faut l'ajouter ici explicitement — pas de discovery magique par glob,
# pour qu'un tool oublié soit visible à la code review (Slopsquatting-aware).
TOOL_MODULES: list[str] = [
    "sandbox.tools.retrieve_docs",
    "sandbox.tools.classify_ticket",
    "sandbox.tools.draft_reply",
    "sandbox.tools.create_ticket",
    "sandbox.tools.evaluate_answer",
    "sandbox.tools.generate_report",
]

# Ordre des risk_level pour le tri : read d'abord (fréquents, peu de
# cérémonie), act en bas (visibilité maximale à la lecture humaine).
_RISK_ORDER = {"read": 0, "draft": 1, "act": 2}

# Version du *générateur* du registry, pas des tools. Bump = changement de
# format du dict retourné (ajout/suppression de champs meta, restructuration).
# Permet à l'AgBOM downstream de savoir comment parser cette slice.
GENERATOR_VERSION = "0.1.0"


def _load_tool_metadata(module_path: str) -> dict:
    """Importe un module tool et extrait son TOOL_METADATA enrichi du module path.

    Lève ImportError si le module n'existe pas, AttributeError si le module
    n'expose pas TOOL_METADATA — deux erreurs *bonnes à faire péter* le build,
    pas à avaler silencieusement.
    """
    module = importlib.import_module(module_path)
    metadata = module.TOOL_METADATA
    # On copie pour ne pas muter le dict du module en mémoire (les tests
    # peuvent importer le module ailleurs et s'attendre à un dict propre).
    enriched = dict(metadata)
    enriched["module"] = module_path
    return enriched


def build_registry() -> dict:
    """Construit le registry complet en mémoire.

    Retourne un dict avec deux clés top-level :
      - "meta"  : provenance du build (timestamp, versions)
      - "tools" : liste triée des 6 tools avec leur contrat MCP
    """
    tools = [_load_tool_metadata(mod) for mod in TOOL_MODULES]

    # Tri déterministe : risk_level croissant (read < draft < act), puis name
    # alphabétique. Pour qu'un diff git du JSON ne soit jamais bruité par un
    # changement d'ordre d'import.
    tools.sort(key=lambda t: (_RISK_ORDER[t["risk_level"]], t["name"]))

    meta = {
        # UTC + isoformat → comparable, triable, ISO 8601 standard.
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_version": GENERATOR_VERSION,
        # Capturé en clair pour qu'un audit puisse vérifier que le registry
        # a été buildé avec le Python attendu (les schemas Pydantic peuvent
        # varier subtilement entre versions Python).
        "python_version": sys.version.split()[0],
        "tool_count": len(tools),
    }

    return {"meta": meta, "tools": tools}


def _write_registry_to_disk(registry: dict, output_path: Path) -> None:
    """Dump le registry en JSON pretty-printed et UTF-8."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        # indent=2 : lisible par humain à la code review.
        # ensure_ascii=False : on garde les accents français dans les
        #   descriptions (sinon on a des \uXXXX illisibles).
        # sort_keys=False : on a déjà trié `tools` ; on veut préserver
        #   l'ordre d'insertion des clés dans `meta` et chaque tool dict.
        json.dump(registry, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")  # newline final POSIX, sinon git râle.


if __name__ == "__main__":
    # Path résolu relativement à la racine repo (3 niveaux au-dessus de ce
    # fichier : src/sandbox/agbom/build_registry.py → ../../../meta/).
    repo_root = Path(__file__).resolve().parents[3]
    output = repo_root / "meta" / "tool_registry.json"

    registry = build_registry()
    _write_registry_to_disk(registry, output)

    print(f"[agbom] wrote {output} ({registry['meta']['tool_count']} tools)")
