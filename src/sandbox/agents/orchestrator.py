"""SupportAgent — l'orchestrateur du support client Marina Rentals (Phase 3).

Rôle : coordonner un pipeline fixe de 4 tools en boucle "perceive → plan → act →
observe", en instrumentant chaque appel dans une Vibe Trajectory (JSONL post-hoc).

Pipeline :
  1. classify_ticket   (read)   : catégorie + priorité
  2. retrieve_docs     (read)   : policy la plus pertinente (top-1)
  3. draft_reply       (draft)  : brouillon avec [[VAR]] non résolus (HITL)
  4. evaluate_answer   (read)   : LLM-as-judge (optionnel — désactivable ou skip
                                  auto si pas de clé API côté juge)

Design decisions (validées par l'utilisateur) :
  - Pipeline fixe (pas LLM-driven) : reproductible, bounded, testable comme un
    tool. L'agent devient lui-même un artefact bounded (voir §7 CLAUDE.md).
  - Classe `SupportAgent` (pas simple fonction) : porte l'état de session,
    la trajectoire courante, et la config du sink JSONL.
  - Trajectoire in-memory + dump JSONL optionnel : la trace vit d'abord en RAM
    (retour de `run()`), puis est facultativement dumpée pour audit post-hoc
    (Vibe Trajectory, Day 4).

Auto-évaluation par le SupportAgent : chaque tour appelle `evaluate_answer`
tant que `evaluate=True`. C'est un "gut check" en ligne, distinct de l'Evaluator
agent (Phase 4) qui fera de l'audit systématique offline sur les JSONL loggés.

HITL respecté : `SupportResponse.answer` renvoie le `draft_text` BRUT avec ses
[[VAR]] non résolus. Aucun envoi client, aucun render final — l'humain doit
substituer les placeholders avant tout `send_email` (qui n'existe pas encore).
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, TypeVar

from pydantic import BaseModel, Field

from sandbox.classification.rules import Category, Priority
from sandbox.tools import classify_ticket as _classify_mod
from sandbox.tools import draft_reply as _draft_mod
from sandbox.tools import evaluate_answer as _evaluate_mod
from sandbox.tools import retrieve_docs as _retrieve_mod
from sandbox.tools.classify_ticket import (
    ClassifyTicketInput,
    ClassifyTicketOutput,
    classify_ticket,
)
from sandbox.tools.draft_reply import (
    DraftReplyInput,
    DraftReplyOutput,
    draft_reply,
)
from sandbox.tools.evaluate_answer import (
    EvaluateAnswerInput,
    EvaluateAnswerOutput,
    evaluate_answer,
)
from sandbox.tools.retrieve_docs import (
    RetrieveDocsInput,
    RetrieveDocsOutput,
    retrieve_docs,
)

# Vocabulaire du cours : read | draft | act (CLAUDE.md §7 "Read/Draft/Act ladder").
# On refuse *volontairement* le vocabulaire alternatif low/medium/high — même si
# PROJECT.MD Phase 7 le montre en exemple, c'est illustratif, pas normatif.
RiskLevel = Literal["read", "draft", "act"]
Status = Literal["success", "error"]

# Longueur max des summaries dans la trace : assez pour humaniser le log, pas
# assez pour polluer / faire fuiter tout le payload en clair.
_SUMMARY_MAX_CHARS = 200

# Source de vérité des risk levels : les tools eux-mêmes via TOOL_METADATA.
# On ne les hardcode pas ici pour éviter le drift si un tool bump son niveau.
# Anti-pattern évité : "l'orchestrateur pense qu'un tool est read alors qu'il
# est passé draft" — le drift-check est mécanique.
_TOOL_RISK: dict[str, RiskLevel] = {
    "classify_ticket": _classify_mod.TOOL_METADATA["risk_level"],
    "retrieve_docs": _retrieve_mod.TOOL_METADATA["risk_level"],
    "draft_reply": _draft_mod.TOOL_METADATA["risk_level"],
    "evaluate_answer": _evaluate_mod.TOOL_METADATA["risk_level"],
}


class TrajectoryEvent(BaseModel):
    """Un tour de l'agent : quel tool a été invoqué, avec quel résumé I/O, timing.

    Format inspiré d'OpenTelemetry (span-like), sérialisable en JSONL.
    Aligné sur l'exemple TrajectoryEvent de PROJECT.MD Phase 7, avec le
    vocabulaire risk verrouillé sur celui de TOOL_METADATA.
    """

    session_id: str
    step: int = Field(..., ge=1)
    agent: str = "support_agent"
    action: str  # nom du tool invoqué
    risk: RiskLevel
    status: Status
    input_summary: str
    output_summary: str
    timestamp: str  # UTC ISO 8601
    duration_ms: int = Field(..., ge=0)


class SupportResponse(BaseModel):
    """Sortie finale de `SupportAgent.run()`.

    - `answer` : le `draft_text` BRUT avec [[VAR]] non résolus. HITL — ne pas
      envoyer tel quel à un client.
    - `placeholders` : liste des [[VAR]] à substituer côté humain avant envoi.
    - `evaluation` : résultat du juge LLM (None si `evaluate=False`).
    - `trajectory` : les 3 ou 4 events du tour, pour audit/replay immédiat.
    """

    answer: str
    placeholders: list[str]
    category: Category
    priority: Priority
    policy_doc_id: str
    cited_policy_excerpt: str
    evaluation: EvaluateAnswerOutput | None
    trajectory: list[TrajectoryEvent]


T = TypeVar("T", bound=BaseModel)


class SupportAgent:
    """Orchestrateur bounded du support client Marina Rentals.

    Une instance = une session logique (session_id fixe). Chaque `run()` = un
    tour de conversation avec sa propre trajectoire (steps repartent à 1).
    """

    def __init__(
        self,
        *,
        trajectory_sink: Path | None = None,
        session_id: str | None = None,
        evaluate: bool = True,
    ) -> None:
        self.trajectory_sink = trajectory_sink
        # session_id fourni → tests déterministes ; sinon uuid tronqué (8 hex
        # suffisent pour la lisibilité, unicité largement suffisante en sandbox).
        self.session_id = session_id or f"s-{uuid.uuid4().hex[:8]}"
        self.evaluate = evaluate
        self._step_counter = 0
        self._trajectory: list[TrajectoryEvent] = []

    @property
    def trajectory(self) -> list[TrajectoryEvent]:
        """Copie de la trajectoire courante (inspection sûre, même après erreur)."""
        return list(self._trajectory)

    def run(self, question: str) -> SupportResponse:
        """Exécute un tour complet : classify → retrieve → draft → (evaluate)."""
        # Reset per-run : chaque run() est atomique côté trace.
        self._step_counter = 0
        self._trajectory = []

        try:
            classification: ClassifyTicketOutput = self._call_tool(
                action="classify_ticket",
                fn=classify_ticket,
                payload=ClassifyTicketInput(text=question),
                input_summary=f"question: {question}",
            )

            retrieval: RetrieveDocsOutput = self._call_tool(
                action="retrieve_docs",
                fn=retrieve_docs,
                payload=RetrieveDocsInput(query=question, top_k=3),
                input_summary=f"query: {question}",
            )
            if not retrieval.results:
                raise RuntimeError(
                    "retrieve_docs a renvoyé 0 résultats — impossible de drafter."
                )
            top_doc = retrieval.results[0]

            draft: DraftReplyOutput = self._call_tool(
                action="draft_reply",
                fn=draft_reply,
                payload=DraftReplyInput(
                    category=classification.category,
                    priority=classification.priority,
                    policy_doc_id=top_doc.doc_id,
                ),
                input_summary=(
                    f"category={classification.category} "
                    f"priority={classification.priority} "
                    f"policy={top_doc.doc_id}"
                ),
            )

            evaluation: EvaluateAnswerOutput | None = None
            if self.evaluate:
                evaluation = self._call_tool(
                    action="evaluate_answer",
                    fn=evaluate_answer,
                    payload=EvaluateAnswerInput(
                        customer_request=question,
                        category=classification.category,
                        cited_policy_id=top_doc.doc_id,
                        cited_policy_excerpt=top_doc.content,
                        draft_reply=draft.draft_text,
                    ),
                    input_summary=(
                        f"judging draft for category={classification.category}"
                    ),
                )

            return SupportResponse(
                # BRUT avec [[VAR]] intacts — HITL préservé (§4 règle 3, §4 règle 6).
                answer=draft.draft_text,
                placeholders=draft.placeholders,
                category=classification.category,
                priority=classification.priority,
                policy_doc_id=top_doc.doc_id,
                cited_policy_excerpt=top_doc.content,
                evaluation=evaluation,
                trajectory=list(self._trajectory),
            )
        finally:
            # Dump JSONL même en cas d'erreur : la trace d'un run raté est
            # exactement ce qu'un audit post-hoc veut voir (Day 4).
            if self.trajectory_sink is not None and self._trajectory:
                _dump_jsonl(self._trajectory, self.trajectory_sink)

    def _call_tool(
        self,
        *,
        action: str,
        fn: Callable[..., T],
        payload: BaseModel,
        input_summary: str,
    ) -> T:
        """Wrap un appel de tool : timing, event success/error, propagation."""
        risk = _TOOL_RISK[action]
        start = time.perf_counter()
        try:
            result = fn(payload)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._record(
                action=action,
                risk=risk,
                status="error",
                input_summary=input_summary,
                output_summary=f"{type(exc).__name__}: {exc}",
                duration_ms=duration_ms,
            )
            raise
        duration_ms = int((time.perf_counter() - start) * 1000)
        self._record(
            action=action,
            risk=risk,
            status="success",
            input_summary=input_summary,
            output_summary=_summarize_output(result),
            duration_ms=duration_ms,
        )
        return result

    def _record(
        self,
        *,
        action: str,
        risk: RiskLevel,
        status: Status,
        input_summary: str,
        output_summary: str,
        duration_ms: int,
    ) -> None:
        self._step_counter += 1
        self._trajectory.append(
            TrajectoryEvent(
                session_id=self.session_id,
                step=self._step_counter,
                action=action,
                risk=risk,
                status=status,
                input_summary=_truncate(input_summary),
                output_summary=_truncate(output_summary),
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_ms=duration_ms,
            )
        )


def _truncate(text: str) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= _SUMMARY_MAX_CHARS:
        return text
    return text[: _SUMMARY_MAX_CHARS - 3] + "..."


def _summarize_output(result: BaseModel) -> str:
    """Résumé lisible d'une sortie de tool pour la trajectoire.

    Le fallback `model_dump_json()` marche pour tout Pydantic, mais on préfère
    des résumés spécialisés par type pour que la trace reste lisible humainement.
    """
    if isinstance(result, ClassifyTicketOutput):
        return (
            f"category={result.category} priority={result.priority} "
            f"conf={result.confidence:.2f}"
        )
    if isinstance(result, RetrieveDocsOutput):
        top = result.results[0] if result.results else None
        if top is None:
            return "results=0"
        return (
            f"top_doc={top.doc_id} score={top.score:.2f} n={len(result.results)}"
        )
    if isinstance(result, DraftReplyOutput):
        return (
            f"tone={result.tone} placeholders={len(result.placeholders)} "
            f"cited={result.cited_policy_id}"
        )
    if isinstance(result, EvaluateAnswerOutput):
        return (
            f"clarte={result.clarte} exact={result.exactitude} "
            f"ton={result.ton} sec={result.securite} model={result.judge_model}"
        )
    return _truncate(result.model_dump_json())


def _dump_jsonl(events: list[TrajectoryEvent], path: Path) -> None:
    """Append la trajectoire à un fichier JSONL (1 event = 1 ligne).

    Append mode : plusieurs runs dans la même session s'accumulent, un `tail -f`
    marche naturellement. Le fichier est créé si absent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for event in events:
            f.write(event.model_dump_json())
            f.write("\n")
