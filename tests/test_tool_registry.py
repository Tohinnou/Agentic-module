"""Tests : tool_registry (Phase 2 wrap — inventaire AgBOM des 6 tools).

Stratégie : on teste la fonction `build_registry()` (dict en mémoire), pas
le JSON sur disque. Avantages : (1) pas besoin de regen avant chaque run de
test, (2) pas de couplage à l'étape write-to-disk, (3) le JSON sur disque
devient un simple artefact de `json.dump(build_registry(), ...)`.
"""

import importlib
import json
from datetime import datetime

import pytest

from sandbox.agbom.build_registry import build_registry


# --- Source de vérité du test : ce que le registry DOIT contenir ---

EXPECTED_TOOLS = {
    "retrieve_docs",
    "classify_ticket",
    "draft_reply",
    "create_ticket",
    "evaluate_answer",
    "generate_report",
}

KNOWN_RISK_LEVELS = {"read", "draft", "act"}
RISK_ORDER = {"read": 0, "draft": 1, "act": 2}

REQUIRED_META_FIELDS = {
    "generated_at",
    "generator_version",
    "python_version",
    "tool_count",
}

REQUIRED_TOOL_FIELDS = {
    "name",
    "module",
    "risk_level",
    "description",
    "input_schema",
    "output_schema",
}


# --- Fixture : build le registry UNE fois — l'import des 6 tools n'est pas gratuit ---

@pytest.fixture(scope="module")
def registry():
    return build_registry()


# --- Shape top-level ---

def test_registry_top_level_keys(registry):
    assert set(registry.keys()) == {"meta", "tools"}, (
        f"top-level keys = {set(registry.keys())}, expected {{'meta', 'tools'}}"
    )


def test_meta_contains_required_fields(registry):
    missing = REQUIRED_META_FIELDS - set(registry["meta"].keys())
    assert not missing, f"meta missing fields : {missing}"


def test_meta_generated_at_is_iso_format(registry):
    """Doit parser comme ISO 8601 — sinon les consommateurs aval (trajectory,
    AgBOM signing) ne peuvent pas comparer / classer les builds entre eux."""
    generated_at = registry["meta"]["generated_at"]
    # `datetime.fromisoformat` accepte "+00:00" mais pas "Z" avant Python 3.11.
    # On normalise par tolérance — si ça parse, c'est valide.
    datetime.fromisoformat(generated_at.replace("Z", "+00:00"))


def test_meta_tool_count_matches_tools_length(registry):
    assert registry["meta"]["tool_count"] == len(registry["tools"]), (
        f"meta.tool_count={registry['meta']['tool_count']}, "
        f"len(tools)={len(registry['tools'])}"
    )


# --- Complétude : les 6 tools sont tous présents, ni plus ni moins ---

def test_all_six_tools_present(registry):
    names = {t["name"] for t in registry["tools"]}
    assert names == EXPECTED_TOOLS, (
        f"missing : {EXPECTED_TOOLS - names}\n"
        f"extra   : {names - EXPECTED_TOOLS}"
    )


def test_each_tool_has_required_fields(registry):
    for tool in registry["tools"]:
        missing = REQUIRED_TOOL_FIELDS - set(tool.keys())
        assert not missing, (
            f"tool '{tool.get('name', '?')}' missing fields : {missing}"
        )


# --- Contraintes sémantiques sur risk_level ---

def test_risk_levels_are_all_known(registry):
    for tool in registry["tools"]:
        assert tool["risk_level"] in KNOWN_RISK_LEVELS, (
            f"tool '{tool['name']}' has unknown risk_level "
            f"'{tool['risk_level']}', expected one of {KNOWN_RISK_LEVELS}"
        )


def test_critical_risk_level_mappings(registry):
    """Spot-check des mappings clés. Protège contre un downgrade silencieux
    (ex : create_ticket passe de 'act' à 'read' pour éviter la friction HITL
    Phase 4 — la régression serait invisible sans ce test)."""
    by_name = {t["name"]: t for t in registry["tools"]}

    assert by_name["create_ticket"]["risk_level"] == "act", (
        "create_ticket DOIT être 'act' — exige Vibe Diff + HITL Phase 4"
    )
    assert by_name["draft_reply"]["risk_level"] == "draft", (
        "draft_reply DOIT être 'draft' — sortie relue par humain avant envoi"
    )
    assert by_name["retrieve_docs"]["risk_level"] == "read", (
        "retrieve_docs DOIT être 'read' — lecture pure du corpus"
    )


def test_tools_sorted_by_risk_then_name(registry):
    """Convention de tri : read → draft → act, puis alphabétique. Lisibilité
    humaine — les Read d'abord (les plus fréquents, sans cérémonie), les Act
    en bas où ils sautent aux yeux pendant la revue."""
    actual = [t["name"] for t in registry["tools"]]
    expected = [
        t["name"]
        for t in sorted(
            registry["tools"],
            key=lambda t: (RISK_ORDER[t["risk_level"]], t["name"]),
        )
    ]
    assert actual == expected, (
        f"ordre incorrect :\n  got      {actual}\n  expected {expected}"
    )


# --- Schemas valides (Pydantic model_json_schema) ---

def test_schemas_have_properties_key(registry):
    """input_schema et output_schema sont issus de Pydantic `model_json_schema()`.
    Doivent avoir une clé 'properties' — sinon le contrat MCP est vide ou cassé,
    et l'agent LLM ne saura pas quoi passer en entrée."""
    for tool in registry["tools"]:
        for field in ("input_schema", "output_schema"):
            schema = tool[field]
            assert isinstance(schema, dict), (
                f"'{tool['name']}'.{field} n'est pas un dict"
            )
            assert "properties" in schema, (
                f"'{tool['name']}'.{field} n'a pas de clé 'properties'"
            )


# --- Sérialisabilité (le registry sera écrit en JSON sur disque) ---

def test_registry_is_json_serializable(registry):
    """Si une valeur n'est pas JSON-sérialisable (datetime, Path, custom class),
    json.dumps lève TypeError. Garde-fou pour l'étape write-to-disk en aval —
    le bug serait visible seulement au moment du dump si on ne testait pas ici."""
    json.dumps(registry, ensure_ascii=False)


# --- Sanity : les modules référencés existent réellement ---

def test_tool_modules_are_importable(registry):
    """Chaque 'module' string doit être importable. Détecte un typo ou un tool
    renommé qui aurait laissé un path obsolète dans le registry. Cheap defense
    in depth — l'overhead d'import est déjà payé par le fixture."""
    for tool in registry["tools"]:
        importlib.import_module(tool["module"])
