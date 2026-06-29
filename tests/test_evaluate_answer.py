"""Calibration : juge LLM vs golden expected scores (±tolerance)."""

import os
from pathlib import Path

import pytest
import yaml

from pydantic import ValidationError

from sandbox.tools.evaluate_answer import (
    TOOL_METADATA,
    EvaluateAnswerInput,
    evaluate_answer,
)

from sandbox.evaluation.judge import DIMENSIONS, judge_answer

GOLDEN_PATH = Path("evals/judge_golden.yaml")


def _load_golden():
    """Charge le golden et déplie chaque case en param pytest."""
    data = yaml.safe_load(GOLDEN_PATH.read_text(encoding="utf-8"))
    tolerance = data["meta"]["tolerance_default"]
    return [
        pytest.param(
            case["input"],
            case["expected"]["scores"],
            tolerance,
            id=case["id"],  # nom affiché dans pytest -v
        )
        for case in data["cases"]
    ]


@pytest.mark.skipif(
      "OPENROUTER_API_KEY" not in os.environ,
      reason="OPENROUTER_API_KEY non défini (calibration nécessite appel LLM réel).",
  )
@pytest.mark.parametrize("inputs, expected_scores, tolerance", _load_golden())
def test_judge_calibration(inputs, expected_scores, tolerance):
      """Chaque dim du juge doit être dans expected ± tolerance."""
      actual = judge_answer(
          customer_request=inputs["customer_request"],
          category=inputs["category"],
          cited_policy_excerpt=inputs["cited_policy_excerpt"],
          draft_reply=inputs["draft_reply"],
      )

      # Vérif structurelle : toutes les dims présentes
      missing = [d for d in DIMENSIONS if d not in actual]
      assert not missing, f"Dimensions manquantes dans la sortie juge : {missing}"

      # Vérif calibration : collecte tous les écarts > tolerance
      deltas = {
          dim: (expected_scores[dim], actual[dim], abs(actual[dim] - expected_scores[dim]))
          for dim in DIMENSIONS
          if abs(actual[dim] - expected_scores[dim]) > tolerance
      }

      assert not deltas, (
          f"\nCalibration KO (tolerance={tolerance}):\n"
          + "\n".join(
              f"  {dim}: expected={exp}, actual={act}, delta={d}"
              for dim, (exp, act, d) in deltas.items()
          )
          + f"\n  Reasoning du juge: {actual.get('reasoning', '<absent>')}"
      )
      
def test_pydantic_rejects_empty_customer_request():
      with pytest.raises(ValidationError):
          EvaluateAnswerInput(
              customer_request="",
              category="cancellation",
              cited_policy_id="cancellation_policy",
              cited_policy_excerpt="excerpt",
              draft_reply="draft",
          )


def test_pydantic_rejects_invalid_category():
      with pytest.raises(ValidationError):
          EvaluateAnswerInput(
              customer_request="ok",
              category="not-a-category",
              cited_policy_id="X",
              cited_policy_excerpt="excerpt",
              draft_reply="draft",
          )


def test_tool_metadata_shape():
      assert TOOL_METADATA["name"] == "evaluate_answer"
      assert TOOL_METADATA["risk_level"] == "read"
      in_props = set(TOOL_METADATA["input_schema"]["properties"].keys())
      assert {"customer_request", "category", "cited_policy_id",
              "cited_policy_excerpt", "draft_reply"} <= in_props
      out_props = set(TOOL_METADATA["output_schema"]["properties"].keys())
      expected_out = {*DIMENSIONS, "reasoning", "judge_model", "prompt_version"}
      assert expected_out <= out_props


@pytest.mark.skipif(
      "OPENROUTER_API_KEY" not in os.environ,
      reason="OPENROUTER_API_KEY non défini.",
)
def test_evaluate_answer_includes_audit_metadata():
      out = evaluate_answer(EvaluateAnswerInput(
          customer_request="test",
          category="cancellation",
          cited_policy_id="cancellation_policy",
          cited_policy_excerpt="gratuit avant 48h",
          draft_reply="OK annulé.",
      ))
      assert out.judge_model == "anthropic/claude-haiku-4.5"
      assert out.prompt_version == "v2"
      for dim in DIMENSIONS:
          score = getattr(out, dim)
          assert isinstance(score, int) and 0 <= score <= 5