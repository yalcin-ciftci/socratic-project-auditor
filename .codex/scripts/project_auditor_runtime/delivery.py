"""DELIV-01..06 & DOC-DELIV-01..08: canonical extraction, mandatory semantic review, durable commit.

The reviewer is a trusted orchestrator callback, not a model-supplied safety claim.
It receives private review context; none of that context is returned to learners.
"""
from __future__ import annotations

import copy
import re
import sqlite3
from typing import Callable

from .store import RuntimeStore, StoreError


SEMANTIC_KEYS = frozenset({"reveals_expected_answer", "determines_solution_steps",
                           "combined_context_completes_solution", "reveals_unfound_diagnosis"})
NOTICE_PARTIAL = "TPL_NOTICE_PARTIAL_EVIDENCE: Kesilmiş artefaktlar kapsam dışı bırakılarak yalnız tam kanıtlı kesit için ilk nötr soru gösterilmiştir."
NOTICE_QUESTION_ONLY = "TPL_NOTICE_IN_SCOPE_QUESTION_ONLY: Kapsam içi yalnız ilk nötr soru gösterilmiştir; bu denemede ipucu kapalıdır (QUESTION_ONLY)."
NOTICE_HINTS = "TPL_NOTICE_IN_SCOPE_ON_DEMAND_HINTS: Kapsam içi yalnız ilk nötr soru gösterilmiştir; ipucu yalnızca talep edilirse açılır ve yardım günlüğüne işlenir."

DOC_NOTICE_PARTIAL = "TPL_DOC_NOTICE_PARTIAL_OR_DEFERRED_SCOPE: İncelenmeyen bölümler ve/veya okunamayan görsel kapsamı görünür tutularak mevcut bölüm grubu için yalnız ilk nötr soru gösterilmiştir."
DOC_NOTICE_QUESTION_ONLY = "TPL_DOC_NOTICE_FULL_BATCH_QUESTION_ONLY: Belge savunması kapsamında mevcut bölüm grubu için yalnız ilk nötr soru gösterilmiştir; bu oturumda ipucu kapalıdır (QUESTION_ONLY)."
DOC_NOTICE_HINTS = "TPL_DOC_NOTICE_FULL_BATCH_ON_DEMAND_HINTS: Belge savunması kapsamında mevcut bölüm grubu için yalnız ilk nötr soru gösterilmiştir; ipucu yalnızca talep edilirse açılır ve yardım kaydına işlenir."

_CODE = re.compile(
    r"```|~~~|\bSELECT\b[\s\S]*?\bFROM\b|\b(?:CREATE|ALTER|DROP)\s+(?:TABLE|INDEX)\b|"
    r"\bGROUP\s+BY\b[\s\S]*?\bHAVING\b|\b(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|MERGE\s+INTO)\b|"
    r"\bdef\s+|\bimport\s+|\bfor\s+[^\n]+?\s+in\b|\bwhile\s+|;\s*$|"
    r"(?m:^\s*(?:\$\s+|sudo\s+|git\s+(?:apply|diff)|diff\s+--git))",
    re.IGNORECASE | re.MULTILINE,
)


def lexical_solution_leak(text: str) -> bool:
    """A deterministic blocker, explicitly not a semantic safety guarantee."""
    return not isinstance(text, str) or bool(_CODE.search(text))


def rubric_text_leak(text: str, criteria: list[dict]) -> bool:
    """Block verbatim or normalized private rubric criterion disclosure."""
    if not isinstance(text, str):
        return True
    norm_text = " ".join(text.lower().split())
    for c in criteria:
        crit = " ".join(c.get("criterion_text", "").lower().split())
        if crit and crit in norm_text:
            return True
    return False


class DeliveryGate:
    def __init__(self, store: RuntimeStore, semantic_reviewer: Callable | None = None):
        self.store = store
        self.semantic_reviewer = semantic_reviewer

    @staticmethod
    def _blocked(code: str, *, pedagogical: bool = False) -> dict:
        return {"ok": False, "learner_visible_payload": None, "error_code": code,
                "terminal_status": "PEDAGOGICAL_LOCK_TRIGGERED" if pedagogical else None}

    def _context(self, payload, exam_id):
        if not isinstance(payload, dict):
            raise StoreError("INVALID_DELIVERY_INPUT")
        ledger_claim = payload.get("disclosure_state", {})
        if not isinstance(ledger_claim, dict):
            raise StoreError("INVALID_DELIVERY_INPUT")
        ledger_id = ledger_claim.get("ledger_source_id")
        ledger = self.store.get_ledger(ledger_id)
        if ledger is None:
            raise StoreError("LEDGER_NOT_INITIALIZED")
        if ledger_claim != ledger:
            raise StoreError("LEDGER_REVISION_CONFLICT")
        package = self.store.get_exam(exam_id)
        questions = self.store.get_exam_questions(exam_id)
        if package is None or not questions:
            raise StoreError("UNREGISTERED_EXAM")
        if package["objective_id"] != payload.get("objective_id"):
            raise StoreError("UNREGISTERED_EXAM")
        level = self.store.get_exam_assistance(exam_id)
        if level != payload.get("allowed_assistance_level"):
            raise StoreError("ASSISTANCE_LEVEL_MISMATCH")
        if level == "SILENT_OBSERVATION_ONLY":
            raise StoreError("DELIVERY_NOT_ALLOWED")
        related = self.store.get_related_disclosures(objective_id=package["objective_id"],
                    artifact_ids=[q["artifact_id"] for q in package["registered_questions"]],
                    snapshot_ids=[q["snapshot_id"] for q in package["registered_questions"]])
        if payload.get("session_mode") == "INDEPENDENT_EVIDENCE_COLLECTION" and any(
                e["event_type"] in {"RUBRIC_SHOWN", "DIAGNOSIS_SHOWN"} for e in related):
            raise StoreError("RUBRIC_ALREADY_DISCLOSED_LOCK")
        # A new ledger cannot erase help from a matching objective/artifact/snapshot.
        if any(e["ledger_id"] != ledger_id for e in related):
            raise StoreError("RELATED_DISCLOSURE_LEDGER_MISMATCH")
        return ledger, package, questions, level

    def _safe(self, text, *, question, questions, ledger):
        if lexical_solution_leak(text) or self.semantic_reviewer is None:
            return False
        context = {"candidate_text": text,
                   "private_criteria": copy.deepcopy(question["expected_explanation_criteria"]),
                   "all_private_criteria": [{"question_id": q["question_id"], "criteria": copy.deepcopy(q["expected_explanation_criteria"])} for q in questions],
                   "prior_disclosed_context": self.store.get_disclosed_context(),
                   "question_id": question["question_id"],
                   "ledger_revision": ledger["ledger_revision"]}
        try:
            verdict = self.semantic_reviewer(context)
        except Exception:
            return False
        return (isinstance(verdict, dict) and set(verdict) == SEMANTIC_KEYS
                and all(type(verdict[k]) is bool and verdict[k] is False for k in SEMANTIC_KEYS))

    @staticmethod
    def _question(q):
        return {key: copy.deepcopy(q[key]) for key in ("question_id", "question_type", "source_ref", "neutral_question_prompt")}

    def _commit(self, ledger, package, question, attempt_id, event_type, hint_id=None):
        source = question["source_ref"]
        return self.store.record_event(ledger["ledger_source_id"], exam_id=package["exam_id"],
                    attempt_id=attempt_id, question_id=question["question_id"],
                    artifact_id=source["artifact_id"], snapshot_id=source["snapshot_id"],
                    event_type=event_type, hint_id=hint_id,
                    expected_revision=ledger["ledger_revision"], require_new=True)

    def deliver_initial(self, payload: dict, output: dict, *, exam_id: str, attempt_id: str) -> dict:
        try:
            if not isinstance(output, dict) or output.get("terminal_status") not in {"EXAM_PREPARED", "PARTIAL_EXAM_PREPARED"}:
                return self._blocked("DELIVERY_NOT_ALLOWED")
            if payload.get("allowed_assistance_level") == "SILENT_OBSERVATION_ONLY":
                return self._blocked("DELIVERY_NOT_ALLOWED")
            ledger, package, questions, level = self._context(payload, exam_id)
            # The persisted package, not a caller-edited public/private candidate,
            # is authoritative. Reject a desynchronized candidate rather than use it.
            if output.get("orchestrator_only_payload", {}).get("socratic_questions") != questions:
                return self._blocked("CANONICAL_QUESTION_MISMATCH")
            q = questions[0]
            if not self._safe(q["neutral_question_prompt"], question=q, questions=questions, ledger=ledger):
                return self._blocked("SOLUTION_LEAKAGE_PREVENTED", pedagogical=True)
            notice = (NOTICE_PARTIAL if output["terminal_status"] == "PARTIAL_EXAM_PREPARED" else
                      NOTICE_QUESTION_ONLY if level == "QUESTION_ONLY" else NOTICE_HINTS)
            new_ledger = self._commit(ledger, package, q, attempt_id, "QUESTION_SHOWN")
            return {"ok": True, "learner_visible_payload": {"canonical_initial_question_id": q["question_id"],
                        "initial_neutral_question": self._question(q), "active_scope_notice": notice},
                    "error_code": None, "disclosure_state": new_ledger}
        except (StoreError, KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
            return self._blocked(getattr(exc, "code", "INVALID_DELIVERY_INPUT"),
                                 pedagogical=getattr(exc, "code", "") == "RUBRIC_ALREADY_DISCLOSED_LOCK")

    def deliver_hint(self, payload: dict, *, exam_id: str, attempt_id: str,
                     question_id: str, hint_id: str) -> dict:
        """Calling this method is an explicit on-demand hint request."""
        try:
            ledger, package, questions, level = self._context(payload, exam_id)
            if level != "QUESTION_AND_CONCEPTUAL_HINT":
                return self._blocked("HINT_NOT_ALLOWED")
            q = next((q for q in questions if q["question_id"] == question_id), None)
            if q is None:
                return self._blocked("UNREGISTERED_QUESTION_OR_CRITERION_REF")
            hint = next((h for h in q["on_demand_hints"] if h["hint_id"] == hint_id), None)
            if hint is None or hint["hint_order"] not in (1, 2):
                return self._blocked("UNREGISTERED_HINT")
            event = f"HINT_{hint['hint_order']}_SHOWN"
            if not self.store.has_event(exam_id, attempt_id, question_id, "QUESTION_SHOWN"):
                return self._blocked("QUESTION_NOT_DELIVERED")
            if hint["hint_order"] == 2 and not self.store.has_event(exam_id, attempt_id, question_id, "HINT_1_SHOWN", q["on_demand_hints"][0]["hint_id"]):
                return self._blocked("HINT_ORDER_VIOLATION")
            if not self._safe(hint["conceptual_nudge"], question=q, questions=questions, ledger=ledger):
                return self._blocked("SOLUTION_LEAKAGE_PREVENTED", pedagogical=True)
            new_ledger = self._commit(ledger, package, q, attempt_id, event, hint_id)
            return {"ok": True, "learner_visible_payload": {"question_id": question_id,
                        "hint_id": hint_id, "hint_order": hint["hint_order"], "conceptual_nudge": hint["conceptual_nudge"]},
                    "error_code": None, "disclosure_state": new_ledger}
        except (StoreError, KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
            return self._blocked(getattr(exc, "code", "INVALID_DELIVERY_INPUT"),
                                 pedagogical=getattr(exc, "code", "") == "RUBRIC_ALREADY_DISCLOSED_LOCK")

    def deliver_next(self, payload: dict, *, exam_id: str, attempt_id: str, after_question_id: str) -> dict:
        try:
            ledger, package, questions, level = self._context(payload, exam_id)
            index = next((i for i, q in enumerate(questions) if q["question_id"] == after_question_id), None)
            if index is None or index + 1 >= len(questions):
                return self._blocked("NO_NEXT_QUESTION")
            if not self.store.has_response(exam_id, attempt_id, after_question_id):
                return self._blocked("PRIOR_RESPONSE_REQUIRED")
            q = questions[index + 1]
            if not self._safe(q["neutral_question_prompt"], question=q, questions=questions, ledger=ledger):
                return self._blocked("SOLUTION_LEAKAGE_PREVENTED", pedagogical=True)
            new_ledger = self._commit(ledger, package, q, attempt_id, "QUESTION_SHOWN")
            return {"ok": True, "learner_visible_payload": {"neutral_question": self._question(q)},
                    "error_code": None, "disclosure_state": new_ledger}
        except (StoreError, KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
            return self._blocked(getattr(exc, "code", "INVALID_DELIVERY_INPUT"),
                                 pedagogical=getattr(exc, "code", "") == "RUBRIC_ALREADY_DISCLOSED_LOCK")

    # -------------------------------------------------------------------------
    # Project & Document Defense Controlled Delivery (v1.3: DOC-DELIV-01..08)
    # -------------------------------------------------------------------------

    def _doc_context(self, payload: dict, batch_exam_id: str):
        if not isinstance(payload, dict):
            raise StoreError("INVALID_DELIVERY_INPUT")
        session_claim = payload.get("session_state_snapshot", {})
        if not isinstance(session_claim, dict):
            raise StoreError("INVALID_DELIVERY_INPUT")
        session_id = payload.get("defense_session_id") or session_claim.get("defense_session_id")
        state = self.store.get_doc_session_state(session_id)
        if state is None:
            raise StoreError("DOC_SESSION_NOT_FOUND")
        if state["session_status"] != "ACTIVE":
            raise StoreError("DOC_SESSION_NOT_ACTIVE")
        if session_claim != state:
            raise StoreError("SESSION_REVISION_CONFLICT")
        package = self.store.get_doc_batch(batch_exam_id)
        questions = self.store.get_doc_batch_questions(batch_exam_id)
        if package is None or not questions:
            raise StoreError("UNREGISTERED_DOC_BATCH")
        if package["defense_session_id"] != session_id or package["project_id"] != payload.get("project_id"):
            raise StoreError("UNREGISTERED_DOC_BATCH")
        doc_desc = payload.get("document_descriptor")
        if isinstance(doc_desc, dict):
            if (doc_desc.get("document_id") != package["document_id"]
                    or doc_desc.get("document_version") != state["current_document_version"]
                    or doc_desc.get("document_sha256") != state["current_document_sha256"]):
                raise StoreError("DOC_VERSION_MISMATCH")
        if (package["document_version"] != state["current_document_version"]
                or package["document_sha256"] != state["current_document_sha256"]):
            raise StoreError("DOC_VERSION_MISMATCH")
        level = self.store.get_doc_batch_assistance(batch_exam_id)
        if level != payload.get("allowed_assistance_level"):
            raise StoreError("ASSISTANCE_LEVEL_MISMATCH")
        if level == "SILENT_OBSERVATION_ONLY":
            raise StoreError("DELIVERY_NOT_ALLOWED")
        return state, package, questions, level

    def _doc_safe(self, text: str, *, question: dict, questions: list[dict],
                  state: dict, allow_teaching_concept: bool = False) -> bool:
        criteria = question.get("expected_explanation_criteria", [])
        if lexical_solution_leak(text) or rubric_text_leak(text, criteria) or self.semantic_reviewer is None:
            return False
        context = {
            "kind": "DOC_TEACHING_REVIEW" if allow_teaching_concept else "DOC_DELIVERY_REVIEW",
            "candidate_text": text,
            "private_criteria": copy.deepcopy(criteria),
            "all_private_criteria": [
                {"question_id": q["question_id"], "criteria": copy.deepcopy(q.get("expected_explanation_criteria", []))}
                for q in questions
            ],
            "prior_disclosed_context": self.store.get_doc_disclosed_context(state["defense_session_id"]),
            "question_id": question["question_id"],
            "session_revision": state["session_revision"],
        }
        try:
            verdict = self.semantic_reviewer(context)
        except Exception:
            return False
        return (isinstance(verdict, dict) and set(verdict) == SEMANTIC_KEYS
                and all(type(verdict[k]) is bool and verdict[k] is False for k in SEMANTIC_KEYS))

    @staticmethod
    def _doc_public_question(q: dict) -> dict:
        keys = ("question_id", "section_id", "passage_id", "heading_path",
                "target_dimension", "claim_epistemic_status", "neutral_question_prompt")
        return {k: copy.deepcopy(q[k]) for k in keys if k in q}

    def deliver_doc_initial(self, payload: dict, output: dict, *,
                            batch_exam_id: str, turn_id: str) -> dict:
        try:
            if not isinstance(output, dict) or output.get("terminal_status") not in {"PROJECT_DEFENSE_PREPARED", "PARTIAL_PROJECT_DEFENSE_PREPARED"}:
                return self._blocked("DELIVERY_NOT_ALLOWED")
            if payload.get("allowed_assistance_level") == "SILENT_OBSERVATION_ONLY":
                return self._blocked("DELIVERY_NOT_ALLOWED")
            state, package, questions, level = self._doc_context(payload, batch_exam_id)
            main_questions = [
                {k: v for k, v in q.items() if not k.startswith("_")}
                for q in questions if not q.get("_parent_question_id")
            ]
            if output.get("orchestrator_only_payload", {}).get("defense_questions") != main_questions:
                return self._blocked("CANONICAL_QUESTION_MISMATCH")
            active_candidates = [q for q in questions if not q.get("_parent_question_id") and not q.get("_voided")]
            if not active_candidates:
                return self._blocked("NO_ACTIVE_QUESTIONS")
            q = active_candidates[0]
            if not self._doc_safe(q["neutral_question_prompt"], question=q, questions=questions, state=state):
                return self._blocked("SOLUTION_LEAKAGE_PREVENTED", pedagogical=True)
            notice = (DOC_NOTICE_PARTIAL if output["terminal_status"] == "PARTIAL_PROJECT_DEFENSE_PREPARED"
                      else DOC_NOTICE_QUESTION_ONLY if level == "QUESTION_ONLY"
                      else DOC_NOTICE_HINTS)
            new_state = self.store.record_doc_event(
                state["defense_session_id"], batch_exam_id=batch_exam_id,
                turn_id=turn_id, question_id=q["question_id"],
                event_type="DOC_QUESTION_SHOWN", expected_revision=state["session_revision"])
            scope = output.get("project_defense_scope_evaluation", {})
            return {
                "ok": True,
                "learner_visible_payload": {
                    "canonical_initial_question_id": q["question_id"],
                    "initial_neutral_question": self._doc_public_question(q),
                    "uninspected_section_ids": copy.deepcopy(scope.get("uninspected_section_ids", [])),
                    "waiting_visual_section_ids": copy.deepcopy(scope.get("waiting_visual_section_ids", [])),
                    "active_scope_notice": notice,
                },
                "error_code": None,
                "session_state_snapshot": new_state,
            }
        except (StoreError, KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
            return self._blocked(getattr(exc, "code", "INVALID_DELIVERY_INPUT"))

    def deliver_doc_next(self, payload: dict, *, batch_exam_id: str,
                         turn_id: str, after_question_id: str) -> dict:
        try:
            state, package, questions, level = self._doc_context(payload, batch_exam_id)
            main_qs = [q for q in questions if not q.get("_parent_question_id")]
            idx = next((i for i, q in enumerate(main_qs) if q["question_id"] == after_question_id), None)
            if idx is None:
                return self._blocked("NO_NEXT_QUESTION")
            current_q = main_qs[idx]
            if not current_q.get("_voided") and not current_q.get("_closed") and not self.store.has_doc_response(state["defense_session_id"], after_question_id):
                return self._blocked("PRIOR_RESPONSE_REQUIRED")
            for fq in questions:
                if fq.get("_parent_question_id") and fq.get("_delivered") and not fq.get("_voided") and not fq.get("_closed"):
                    if not self.store.has_doc_response(state["defense_session_id"], fq["question_id"]):
                        return self._blocked("PRIOR_RESPONSE_REQUIRED")
            next_q = next((q for q in main_qs[idx + 1:] if not q.get("_voided") and not q.get("_delivered")), None)
            if next_q is None:
                return self._blocked("NO_NEXT_QUESTION")
            if not self._doc_safe(next_q["neutral_question_prompt"], question=next_q, questions=questions, state=state):
                return self._blocked("SOLUTION_LEAKAGE_PREVENTED", pedagogical=True)
            new_state = self.store.record_doc_event(
                state["defense_session_id"], batch_exam_id=batch_exam_id,
                turn_id=turn_id, question_id=next_q["question_id"],
                event_type="DOC_QUESTION_SHOWN", expected_revision=state["session_revision"])
            return {
                "ok": True,
                "learner_visible_payload": {"neutral_question": self._doc_public_question(next_q)},
                "error_code": None,
                "session_state_snapshot": new_state,
            }
        except (StoreError, KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
            return self._blocked(getattr(exc, "code", "INVALID_DELIVERY_INPUT"))

    def deliver_doc_followup(self, payload: dict, *, batch_exam_id: str,
                             turn_id: str, followup_question_id: str) -> dict:
        try:
            state, package, questions, level = self._doc_context(payload, batch_exam_id)
            fq = next((q for q in questions if q["question_id"] == followup_question_id and q.get("_parent_question_id")), None)
            if fq is None:
                return self._blocked("UNREGISTERED_QUESTION_OR_CRITERION_REF")
            if fq.get("_voided"):
                return self._blocked("QUESTION_IS_VOIDED")
            parent_id = fq["_parent_question_id"]
            if not self.store.has_doc_response(state["defense_session_id"], parent_id):
                return self._blocked("PRIOR_RESPONSE_REQUIRED")
            if not self._doc_safe(fq["neutral_question_prompt"], question=fq, questions=questions, state=state):
                return self._blocked("SOLUTION_LEAKAGE_PREVENTED", pedagogical=True)
            new_state = self.store.record_doc_event(
                state["defense_session_id"], batch_exam_id=batch_exam_id,
                turn_id=turn_id, question_id=followup_question_id,
                event_type="DOC_FOLLOWUP_SHOWN", expected_revision=state["session_revision"])
            return {
                "ok": True,
                "learner_visible_payload": {
                    "followup_question": {
                        "followup_question_id": fq["question_id"],
                        "parent_question_id": parent_id,
                        "section_id": fq["section_id"],
                        "passage_id": fq["passage_id"],
                        "target_dimension": fq["target_dimension"],
                        "followup_reason": fq.get("followup_reason", "CLARIFY_VAGUE_RESPONSE"),
                        "neutral_followup_prompt": fq["neutral_question_prompt"],
                    }
                },
                "error_code": None,
                "session_state_snapshot": new_state,
            }
        except (StoreError, KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
            return self._blocked(getattr(exc, "code", "INVALID_DELIVERY_INPUT"))

    def deliver_doc_hint(self, payload: dict, *, batch_exam_id: str,
                         turn_id: str, question_id: str, hint_id: str) -> dict:
        try:
            state, package, questions, level = self._doc_context(payload, batch_exam_id)
            if level != "QUESTION_AND_CONCEPTUAL_HINT":
                return self._blocked("HINT_NOT_ALLOWED")
            q = next((q for q in questions if q["question_id"] == question_id), None)
            if q is None:
                return self._blocked("UNREGISTERED_QUESTION_OR_CRITERION_REF")
            hint = next((h for h in q.get("on_demand_hints", []) if h["hint_id"] == hint_id), None)
            if hint is None or hint["hint_order"] not in (1, 2):
                return self._blocked("UNREGISTERED_HINT")
            if not self._doc_safe(hint["conceptual_nudge"], question=q, questions=questions, state=state):
                return self._blocked("SOLUTION_LEAKAGE_PREVENTED", pedagogical=True)
            event = f"DOC_HINT_{hint['hint_order']}_SHOWN"
            new_state = self.store.record_doc_event(
                state["defense_session_id"], batch_exam_id=batch_exam_id,
                turn_id=turn_id, question_id=question_id,
                event_type=event, detail_id=hint_id,
                expected_revision=state["session_revision"])
            return {
                "ok": True,
                "learner_visible_payload": {
                    "question_id": question_id,
                    "hint_id": hint_id,
                    "hint_order": hint["hint_order"],
                    "conceptual_nudge": hint["conceptual_nudge"],
                },
                "error_code": None,
                "session_state_snapshot": new_state,
            }
        except (StoreError, KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
            return self._blocked(getattr(exc, "code", "INVALID_DELIVERY_INPUT"))

    def deliver_doc_teaching(self, payload: dict, *, batch_exam_id: str,
                             turn_id: str, question_id: str,
                             response_id: str, teaching_packet: dict) -> dict:
        """Separate Morks teaching delivery path after closing an IDK defense record.

        1. Verifies the question+response defense record is already closed.
        2. Blocks any private rubric text disclosure or ready-made project code.
        3. Commits TEACHING_EXPLANATION_SHOWN help record to SQLite BEFORE returning explanation.
        4. Taints the dimension and declared downstream dimensions as assisted while preserving prior unassisted records.
        """
        try:
            state, package, questions, level = self._doc_context(payload, batch_exam_id)
            q = next((q for q in questions if q["question_id"] == question_id), None)
            if q is None:
                return self._blocked("UNREGISTERED_QUESTION_OR_CRITERION_REF")
            if not q.get("_closed"):
                return self._blocked("DEFENSE_RECORD_NOT_CLOSED")
            if (teaching_packet.get("closed_question_id") != question_id
                    or teaching_packet.get("closed_response_id") != response_id
                    or teaching_packet.get("section_id") != q["section_id"]
                    or teaching_packet.get("target_dimension") != q["target_dimension"]):
                return self._blocked("TEACHING_PACKET_IDENTITY_MISMATCH")
            combined_text = (teaching_packet.get("concept_and_rationale_explanation", "")
                             + "\n" + "\n".join(teaching_packet.get("suggested_approaches", [])))
            if not self._doc_safe(combined_text, question=q, questions=questions, state=state, allow_teaching_concept=True):
                return self._blocked("SOLUTION_LEAKAGE_PREVENTED", pedagogical=True)
            # Commit help record BEFORE returning teaching content to learner
            new_state = self.store.commit_doc_teaching_event(
                state["defense_session_id"],
                batch_exam_id=batch_exam_id,
                question_id=question_id,
                response_id=response_id,
                teaching_packet=teaching_packet,
                turn_id=turn_id,
                expected_revision=state["session_revision"],
            )
            return {
                "ok": True,
                "learner_visible_payload": {
                    "teaching_transition_active": True,
                    "teaching_packet_id": teaching_packet["teaching_packet_id"],
                    "closed_question_id": question_id,
                    "closed_response_id": response_id,
                    "section_id": q["section_id"],
                    "target_dimension": q["target_dimension"],
                    "concept_and_rationale_explanation": teaching_packet["concept_and_rationale_explanation"],
                    "suggested_approaches": copy.deepcopy(teaching_packet["suggested_approaches"]),
                    "downstream_affected_dimensions": copy.deepcopy(teaching_packet.get("downstream_affected_dimensions", [])),
                },
                "error_code": None,
                "session_state_snapshot": new_state,
            }
        except (StoreError, KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
            return self._blocked(getattr(exc, "code", "INVALID_DELIVERY_INPUT"))
