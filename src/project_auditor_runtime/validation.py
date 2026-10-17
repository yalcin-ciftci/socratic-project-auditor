"""Fail-closed structural/cross-document checks for accepted auditor contracts v1.2 & v1.3.

This module never invokes a model, executes artifacts or mutates trusted stores.
POST-11's semantic prerequisite question needs an external review whenever the
input declares early topics. Passing this module alone is not delivery approval.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any


class ValidationDependencyError(RuntimeError):
    """The full schema/calendar validator is unavailable; never bypass it."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError("Nonfinite JSON numbers are forbidden")


def strict_json(value: str | bytes | dict) -> dict:
    """Parse exactly one finite JSON object without silently discarding keys."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="strict")
    if isinstance(value, str):
        result = json.loads(value, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    elif isinstance(value, dict):
        # A dict has already lost duplicate-key evidence. Check JSON data types,
        # keys and finiteness recursively before making an independent copy.
        def check(item: Any) -> None:
            if item is None or type(item) in (str, bool, int):
                return
            if type(item) is float and math.isfinite(item):
                return
            if type(item) is list:
                for child in item:
                    check(child)
                return
            if type(item) is dict and all(type(k) is str for k in item):
                for child in item.values():
                    check(child)
                return
            raise ValueError("Value is not finite JSON data")
        check(value)
        result = copy.deepcopy(value)
    else:
        raise ValueError("JSON object required")
    if not isinstance(result, dict):
        raise ValueError("JSON object required")
    # Also catches UTF-8 lone surrogates and huge exponents decoded as infinity.
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
    encoded.encode("utf-8", errors="strict")
    return result


def canonical_hash(package: dict) -> str:
    body = {key: value for key, value in package.items() if key != "exam_package_sha256"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def doc_package_hash(package: dict) -> str:
    body = {key: value for key, value in package.items() if key != "batch_package_sha256"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def extract_schemas(agent_dir: Path) -> tuple[dict, dict]:
    """Load the sole authoritative code-defense schemas directly from accepted Markdown."""
    contract = (Path(agent_dir) / "CONTRACT.md").read_text(encoding="utf-8-sig")
    schemas = {}
    for block in re.findall(r"^```json\s*\n(.*?)^```\s*$", contract, re.M | re.S):
        candidate = strict_json(block)
        version = candidate.get("properties", {}).get("schema_version", {}).get("const")
        if candidate.get("$schema") == "https://json-schema.org/draft/2020-12/schema" and version:
            if version in schemas:
                raise ValueError("Duplicate authoritative schema")
            schemas[version] = candidate
    try:
        return schemas["harmanos.project_auditor.input.v1"], schemas["harmanos.project_auditor.output.v1"]
    except KeyError as exc:
        raise ValueError("Accepted input/output schemas missing") from exc


def extract_doc_defense_schemas(agent_dir: Path) -> tuple[dict, dict]:
    """Load the authoritative document-defense schemas from PROJECT_DEFENSE_CONTRACT.md."""
    contract_path = Path(agent_dir) / "PROJECT_DEFENSE_CONTRACT.md"
    contract = contract_path.read_text(encoding="utf-8-sig")
    schemas = {}
    for block in re.findall(r"^```json\s*\n(.*?)^```\s*$", contract, re.M | re.S):
        candidate = strict_json(block)
        version = candidate.get("properties", {}).get("schema_version", {}).get("const")
        if candidate.get("$schema") == "https://json-schema.org/draft/2020-12/schema" and version:
            if version in schemas:
                raise ValueError("Duplicate authoritative doc defense schema")
            schemas[version] = candidate
    try:
        return (schemas["harmanos.project_auditor.doc_defense.input.v1"],
                schemas["harmanos.project_auditor.doc_defense.output.v1"])
    except KeyError as exc:
        raise ValueError("Accepted document-defense input/output schemas missing") from exc


# Section 4.1: language, contexts, binding sources and evaluator compatibility.
MATRIX = {
    "SQL_DATA_ENG": ({"SQL"}, {"ECOMMERCE_MVP", "DATACAMP_EXERCISE", "DEMO_PROJECT"},
                     {"DOC-ECOMMERCE-MVP-PLAN-V1", "DOC-DATACAMP-TRACK-V1", "DOC-DEMO-SPEC-V1"}, True),
    "PYTHON_DATA_ENG": ({"PYTHON", "BASH_SH"}, {"ECOMMERCE_MVP", "DATACAMP_EXERCISE", "DEMO_PROJECT"},
                        {"DOC-ECOMMERCE-MVP-PLAN-V1", "DOC-DATACAMP-TRACK-V1", "DOC-DEMO-SPEC-V1"}, True),
    "PYTHON_CORE_PE1": ({"PYTHON"}, {"PE1_COURSEWORK"}, {"DOC-PE1-SPEC-V1"}, False),
    "R_STATS": ({"R"}, {"UNI_COURSEWORK", "DATACAMP_EXERCISE"},
                {"DOC-UNI-SYLLABUS-V1", "DOC-DATACAMP-TRACK-V1"}, True),
    "SPSS_STATS": ({"SPSS_SYNTAX"}, {"UNI_COURSEWORK"}, {"DOC-UNI-SYLLABUS-V1"}, True),
    "CYBERSEC_UNI": ({"PYTHON", "BASH_SH", "POWERSHELL"}, {"UNI_COURSEWORK"}, {"DOC-UNI-SYLLABUS-V1"}, True),
    "HARMANOS_SYSTEM_ARCH": ({"PYTHON", "POWERSHELL", "BASH_SH", "MARKDOWN_CONTRACT"},
                             {"HARMANOS_INFRA"}, {"DOC-HARMANOS-ARCH-V1"}, False),
}
CONTEXT_SOURCE = {
    "ECOMMERCE_MVP": "DOC-ECOMMERCE-MVP-PLAN-V1", "DATACAMP_EXERCISE": "DOC-DATACAMP-TRACK-V1",
    "DEMO_PROJECT": "DOC-DEMO-SPEC-V1", "UNI_COURSEWORK": "DOC-UNI-SYLLABUS-V1",
    "PE1_COURSEWORK": "DOC-PE1-SPEC-V1", "HARMANOS_INFRA": "DOC-HARMANOS-ARCH-V1",
}

_DOC_CODE_LEAK = re.compile(
    r"```|~~~|\bSELECT\b[\s\S]*?\bFROM\b|\b(?:CREATE|ALTER|DROP)\s+(?:TABLE|INDEX)\b|"
    r"\bGROUP\s+BY\b[\s\S]*?\bHAVING\b|\b(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|MERGE\s+INTO)\b|"
    r"\bdef\s+\w+\s*\(|\bclass\s+\w+\s*[:(]|\bimport\s+\w+|\bfor\s+[^\n]+?\s+in\b.+:|"
    r"(?m:^\s*(?:\$\s+|sudo\s+|git\s+(?:apply|diff)|diff\s+--git))",
    re.IGNORECASE | re.MULTILINE,
)


def is_doc_defense_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return (payload.get("schema_version") == "harmanos.project_auditor.doc_defense.input.v1"
            or payload.get("operation") in ("PREPARE_PROJECT_DEFENSE", "ANALYZE_PROJECT_DEFENSE")
            or "document_descriptor" in payload
            or "full_section_inventory" in payload)


def is_doc_defense_output(output: Any) -> bool:
    if not isinstance(output, dict):
        return False
    return (output.get("schema_version") == "harmanos.project_auditor.doc_defense.output.v1"
            or output.get("operation_evaluated") in ("PREPARE_PROJECT_DEFENSE", "ANALYZE_PROJECT_DEFENSE")
            or "project_defense_scope_evaluation" in output)


class RuntimeValidator:
    def __init__(self, agent_dir: Path, semantic_reviewer=None):
        self.semantic_reviewer = semantic_reviewer
        try:
            from jsonschema import Draft202012Validator, FormatChecker
            from rfc3339_validator import validate_rfc3339
        except ImportError as exc:
            raise ValidationDependencyError("jsonschema and rfc3339-validator are required; validation is disabled closed") from exc
        checker = FormatChecker()
        # Do not assume jsonschema silently installed its optional formats extra.
        @checker.checks("date-time", raises=(ValueError, TypeError))
        def date_time(value: Any) -> bool:
            return not isinstance(value, str) or validate_rfc3339(value)
        if checker.conforms("2026-02-31T12:00:00+03:00", "date-time"):
            raise ValidationDependencyError("RFC3339 calendar checker is not enforcing dates")
        self.input_schema, self.output_schema = extract_schemas(agent_dir)
        for schema in (self.input_schema, self.output_schema):
            Draft202012Validator.check_schema(schema)
        self._input = Draft202012Validator(self.input_schema, format_checker=checker)
        self._output = Draft202012Validator(self.output_schema, format_checker=checker)
        notices = self.output_schema["properties"]["learner_visible_payload"]["properties"]["active_scope_notice"]["enum"]
        self._notices = {notice.split(":", 1)[0]: notice for notice in notices}

        doc_contract = Path(agent_dir) / "PROJECT_DEFENSE_CONTRACT.md"
        if doc_contract.is_file():
            self.doc_input_schema, self.doc_output_schema = extract_doc_defense_schemas(agent_dir)
            for schema in (self.doc_input_schema, self.doc_output_schema):
                Draft202012Validator.check_schema(schema)
            self._doc_input = Draft202012Validator(self.doc_input_schema, format_checker=checker)
            self._doc_output = Draft202012Validator(self.doc_output_schema, format_checker=checker)
            doc_notices = self.doc_output_schema["properties"]["learner_visible_payload"]["properties"]["active_scope_notice"]["enum"]
            self._doc_notices = {notice.split(":", 1)[0]: notice for notice in doc_notices}
        else:
            self.doc_input_schema = self.doc_output_schema = None
            self._doc_input = self._doc_output = None
            self._doc_notices = {}

    @staticmethod
    def _pre(payload: dict | None, status: str, error: str, rule: str, detail: str) -> dict:
        return {"ok": False, "payload": payload, "terminal_status": status,
                "error_code": error, "rule": rule, "detail": detail}

    @staticmethod
    def _post(error: str, rule: str, detail: str) -> dict:
        return {"ok": False, "output": None, "error_code": error, "rule": rule, "detail": detail}

    @staticmethod
    def _calendar(value: str) -> bool:
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return date.tzinfo is not None and date.utcoffset() is not None
        except (ValueError, TypeError, AttributeError):
            return False

    @staticmethod
    def _unique(items: list[dict], key: str) -> bool:
        ids = [item[key] for item in items]
        return len(ids) == len(set(ids))

    @staticmethod
    def _reference(ref: dict, artifacts: list[dict], *, complete: bool = False) -> bool:
        return any(a["artifact_id"] == ref["artifact_id"] and a["snapshot_id"] == ref["snapshot_id"]
                   and a["start_line"] <= ref["start_line"] <= ref["end_line"] <= a["end_line"]
                   and (not complete or a["completeness"] == "COMPLETE") for a in artifacts)

    @staticmethod
    def _ledger_matches(payload: dict, ledger: dict | None) -> bool:
        # The caller must load this from trusted local storage, not the request.
        # Exact equality is intentionally stronger than mere revision equality:
        # callers cannot remove hints, events, summary, log completeness or flags.
        return ledger is not None and ledger == payload["disclosure_state"]

    def _registry_valid(self, p: dict, registry: dict) -> bool:
        package = p["prior_exam_package"]
        if package is None or not isinstance(registry, dict):
            return False
        if package["objective_id"] != p["objective_id"] or canonical_hash(package) != package["exam_package_sha256"]:
            return False
        if registry.get(package["exam_id"]) != package:
            return False
        questions = package["registered_questions"]
        if not self._unique(questions, "question_id"):
            return False
        all_criteria = []
        for q in questions:
            if not self._unique(q["immutable_criteria"], "criterion_id") or not self._reference(q, p["code_artifacts"]):
                return False
            all_criteria.extend(c["criterion_id"] for c in q["immutable_criteria"])
        if len(all_criteria) != len(set(all_criteria)):
            return False
        for response in p["learner_responses"]:
            matches = [q for q in questions if q["question_id"] == response["question_id"]
                       and q["delivered_to_learner"] and q["artifact_id"] == response["artifact_id"]
                       and q["snapshot_id"] == response["snapshot_id"]]
            if len(matches) != 1 or not set(response["criterion_ids_to_evaluate"]) <= {
                c["criterion_id"] for c in matches[0]["immutable_criteria"]}:
                return False
        return True

    def preflight(self, raw: str | bytes | dict, *, exam_registry: dict, ledger: dict | None) -> dict:
        try:
            p = strict_json(raw)
            if not isinstance(p.get("task_id"), str) or not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", p["task_id"]):
                raise ValueError("Invalid task identity")
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            return self._pre(None, "INVALID_INPUT_CONTRACT", "UNPARSEABLE_OR_MISSING_TASK_ID", "PRE-01", "A finite UTF-8 JSON object and valid task_id are required.")
        if is_doc_defense_payload(p):
            return self.preflight_doc_defense(raw, batch_registry=exam_registry, session_state=ledger)
        size = len(raw.decode("utf-8") if isinstance(raw, bytes) else raw) if isinstance(raw, (str, bytes)) else len(json.dumps(p, ensure_ascii=False))
        arts = p.get("code_artifacts")
        bc = p.get("binding_constraints")
        bounded = size > 65536
        if isinstance(arts, list):
            # Content bounds/schema operate on LF-normalized evidence, while
            # the transport-size limit above still measures the original JSON.
            for artifact in arts:
                if isinstance(artifact, dict) and isinstance(artifact.get("content"), str):
                    artifact["content"] = artifact["content"].replace("\r\n", "\n").replace("\r", "\n")
            bounded |= len(arts) > 10
            bounded |= any(isinstance(a, dict) and isinstance(a.get("content"), str) and len(a["content"]) > 16384 for a in arts)
        if isinstance(p.get("acceptance_criteria"), list):
            bounded |= len(p["acceptance_criteria"]) > 10
        if isinstance(bc, dict):
            bounded |= any(type(bc.get(key)) is int and bc[key] > maximum for key, maximum in (("max_questions", 5), ("max_hints_per_question", 2)))
        if bounded:
            return self._pre(p, "INVALID_INPUT_CONTRACT", "PAYLOAD_BOUNDS_EXCEEDED", "PRE-02", "Input exceeds a declared contract payload bound.")
        errors = list(self._input.iter_errors(p))
        if errors:
            # Preserve dedicated zero-tool and unknown-domain diagnostics without
            # leaking arbitrary untrusted source text into error messages.
            permissions = p.get("tool_permissions")
            error = "SCHEMA_OR_VERSION_MISMATCH"
            if isinstance(permissions, dict) and (permissions.get("allowed_tools") or any(permissions.get(k) is True for k in ("code_execution_allowed", "mutation_allowed", "web_or_mcp_allowed", "subagent_invocation_allowed"))):
                error = "TOOL_PERMISSION_VIOLATION"
            elif any(isinstance(p.get(k), str) and p[k] not in self.input_schema["properties"][k]["enum"] for k in ("learning_domain", "programming_language")):
                error = "UNKNOWN_DOMAIN_OR_LANGUAGE"
            return self._pre(p, "INVALID_INPUT_CONTRACT", error, "PRE-03", "Input does not satisfy accepted Draft 2020-12 schema/calendar constraints.")
        if not self._calendar(p["as_of"]) or (p["prior_exam_package"] and not self._calendar(p["prior_exam_package"]["created_as_of"])):
            return self._pre(p, "INVALID_INPUT_CONTRACT", "SCHEMA_OR_VERSION_MISMATCH", "PRE-03", "Input timestamp is not a real timezone-aware calendar value.")
        for artifact in p["code_artifacts"]:
            artifact["content"] = artifact["content"].replace("\r\n", "\n").replace("\r", "\n")
            start, end = artifact["start_line"], artifact["end_line"]
            if not (1 <= start <= end <= 300) or len(artifact["content"].split("\n")) != end - start + 1:
                return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_ARTIFACT_OR_LINE_REF", "PRE-04", "Artifact content does not exactly match the declared line interval.")
            for omitted in artifact["omitted_line_ranges"]:
                if omitted["start_line"] > omitted["end_line"] or max(start, omitted["start_line"]) <= min(end, omitted["end_line"]):
                    return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_ARTIFACT_OR_LINE_REF", "PRE-04", "Omitted line interval is invalid or overlaps supplied content.")
        if not all(self._unique(p[name], key) for name, key in (("code_artifacts", "artifact_id"), ("upstream_review_refs", "finding_id"), ("learner_responses", "response_id"))) or any(not self._reference(ref, p["code_artifacts"]) for ref in p["upstream_review_refs"]):
            return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_ARTIFACT_OR_LINE_REF", "PRE-05", "Identifiers must be unique and upstream references must resolve within their exact snapshot.")
        if p["operation"] == "ANALYZE_RESPONSE" and not self._registry_valid(p, exam_registry):
            return self._pre(p, "INVALID_INPUT_CONTRACT", "UNREGISTERED_QUESTION_OR_CRITERION_REF", "PRE-06", "Canonical exam hash, trusted registry or delivered question/criterion reference does not match.")
        if not self._ledger_matches(p, ledger):
            return self._pre(p, "INVALID_INPUT_CONTRACT", "SCHEMA_OR_VERSION_MISMATCH", "PRE-07", "A trusted local ledger must exactly match disclosure_state; request-supplied history is insufficient.")
        if p["learning_domain"] in {"C_PROGRAMMING", "42_PISCINE"} or p["programming_language"] == "C" or p["project_context_type"] in {"42_PISCINE", "C_STANDALONE"}:
            return self._pre(p, "OUT_OF_SCOPE", "FORBIDDEN_DOMAIN_C_OR_42", "PRE-08", "C and 42 domains, languages and contexts are outside this agent's scope.")
        languages, contexts, sources, _ = MATRIX[p["learning_domain"]]
        forbidden = any(re.search(r"(?<!\w)" + re.escape(tool) + r"(?!\w)", p["single_question"], re.I) for tool in p["binding_constraints"]["forbidden_tools"])
        if p["programming_language"] not in languages or p["project_context_type"] not in contexts or p["binding_constraints"]["binding_source_id"] not in sources or CONTEXT_SOURCE.get(p["project_context_type"]) != p["binding_constraints"]["binding_source_id"] or forbidden:
            return self._pre(p, "OUT_OF_SCOPE", "FORBIDDEN_CONTEXT_OR_TOOL", "PRE-08", "The requested language, context, binding source or named forbidden tool violates the scope matrix.")
        disclosure = p["disclosure_state"]
        events = {event for record in disclosure["attempt_disclosure_records"] for event in record["disclosed_event_types"]}
        if p["session_mode"] == "INDEPENDENT_EVIDENCE_COLLECTION" and (disclosure["rubric_or_diagnosis_disclosed"] or events & {"RUBRIC_SHOWN", "DIAGNOSIS_SHOWN"}):
            return self._pre(p, "PEDAGOGICAL_LOCK_TRIGGERED", "RUBRIC_ALREADY_DISCLOSED_LOCK", "PRE-09", "Known rubric or diagnosis disclosure prevents an independent evidence attempt.")
        # Only task instructions are inspected here; artifacts/responses remain
        # untrusted evidence and never become operative instructions (AV-09).
        if re.search(r"(?:write|output|generate|produce|give)\s+(?:the\s+|full\s+|a\s+)*(?:solution|fix|patch|sql\s+(?:fix|solution)|code)|(?:çözüm(?:ü|unu)?|kodu|kodunu|düzeltilmiş\s+kodu)\s+(?:yaz|üret|ver)", p["single_question"], re.I):
            return self._pre(p, "PEDAGOGICAL_LOCK_TRIGGERED", "SOLUTION_LEAKAGE_PREVENTED", "PRE-09", "The task directly requests prohibited solution production.")
        if any((a["optional_ast_summary"] or {}).get("snapshot_id_match") is False or a["execution_evidence"]["status"] == "CONFLICTING_LOGS" for a in p["code_artifacts"]):
            return self._pre(p, "CONFLICTING_EVIDENCE", "AST_OR_LOG_CONTRADICTION", "PRE-10", "AST snapshot or execution evidence contains a direct contradiction.")
        if not any(a["completeness"] == "COMPLETE" for a in p["code_artifacts"]):
            return self._pre(p, "INSUFFICIENT_EVIDENCE", "TRUNCATED_OR_MISSING_TARGET_EVIDENCE", "PRE-10", "No complete artifact supports a question or response analysis.")
        if p["operation"] == "ANALYZE_RESPONSE" and any(not r["raw_response_text"].strip() for r in p["learner_responses"]):
            return self._pre(p, "INSUFFICIENT_EVIDENCE", "EMPTY_OR_UNUSABLE_RESPONSE", "PRE-10", "A learner response contains no usable text.")
        if p["scope_readiness_input"] != "IN_SCOPE":
            return self._pre(p, "SCOPE_DECISION_REQUIRED", "NON_IN_SCOPE_READINESS_TAG", "PRE-10", "An explicit scope decision is required for the requested readiness tag.")
        return {"ok": True, "payload": p}

    @staticmethod
    def assistance_values(p: dict) -> dict:
        d = p["disclosure_state"]
        events = {event for record in d["attempt_disclosure_records"] for event in record["disclosed_event_types"]}
        if d["rubric_or_diagnosis_disclosed"] or events & {"RUBRIC_SHOWN", "DIAGNOSIS_SHOWN", "EXTERNAL_REFERENCE_USED"}:
            known = floor = "EXTERNAL_REFERENCE_USED"
        else:
            known = "HINT_OR_BRAINSTORMING" if d["disclosed_hint_ids"] or any(r["disclosed_hint_ids"] for r in d["attempt_disclosure_records"]) or events & {"HINT_1_SHOWN", "HINT_2_SHOWN", "BRAINSTORMING_USED"} else "NONE_OBSERVED"
            floor = "UNKNOWN_UNVERIFIED" if not d["assistance_log_present"] else "HINT_OR_BRAINSTORMING" if known == "HINT_OR_BRAINSTORMING" or p["session_mode"] == "GUIDED_PRACTICE" else "NONE_INDEPENDENT"
        compatible = MATRIX.get(p["learning_domain"], (None, None, None, False))[3]
        return {"known_disclosed_assistance_class": known, "effective_assistance_floor": floor,
                "eligible_for_independent_attempt_submission": compatible and p["session_mode"] == "INDEPENDENT_EVIDENCE_COLLECTION" and known == "NONE_OBSERVED" and floor == "NONE_INDEPENDENT"}

    def postflight(self, payload: dict, output: dict | str, *, exam_registry: dict, ledger: dict | None) -> dict:
        try:
            o = strict_json(output)
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            return self._post("INVALID_OUTPUT_SCHEMA", "POST-01", "Output must be a single finite JSON object without code fences or duplicate keys.")
        try:
            parsed_input = strict_json(payload)
        except Exception:
            parsed_input = {}
        if is_doc_defense_payload(parsed_input) or is_doc_defense_output(o):
            return self.postflight_doc_defense(payload, o, batch_registry=exam_registry, session_state=ledger)
        schema_errors = list(self._output.iter_errors(o))
        if schema_errors or not self._calendar(o.get("as_of_evaluated")):
            result = self._post("INVALID_OUTPUT_SCHEMA", "POST-01", "Output violates the accepted schema, state matrix, locks or real calendar timestamp.")
            result["schema_errors"] = [{"path": list(e.absolute_path), "keyword": e.validator,
                                        "message": e.message[:600]} for e in schema_errors[:8]]
            return result
        # Validate the input again against current trusted state; callers cannot
        # bypass preflight or race the registry/ledger between the two phases.
        pre = self.preflight(payload, exam_registry=exam_registry, ledger=ledger)
        p = pre.get("payload")
        if p is None:
            return self._post("INVALID_OUTPUT_ECHO_MISMATCH", "POST-02", "A valid input identity is required for model output validation.")
        status = o["terminal_status"]
        if not pre["ok"]:
            if status != pre["terminal_status"] or o["error_code"] != pre["error_code"]:
                return self._post("INVALID_OUTPUT_STATUS", "POST-02", "Output does not preserve deterministic input error precedence.")
            if status == "INVALID_INPUT_CONTRACT":
                # Invalid requests may lack operation/as_of; validate the safe
                # terminal envelope without indexing absent request fields.
                operation = p.get("operation") if p.get("operation") in ("PREPARE_EXAM", "ANALYZE_RESPONSE") else None
                if o["task_id"] != p["task_id"] or o["operation_evaluated"] != operation or (self._calendar(p.get("as_of")) and o["as_of_evaluated"] != p["as_of"]):
                    return self._post("INVALID_OUTPUT_ECHO_MISMATCH", "POST-02", "Invalid-input terminal envelope must preserve every available valid identity field.")
                return {"ok": True, "output": o}
        else:
            expected = "RESPONSE_ANALYZED" if p["operation"] == "ANALYZE_RESPONSE" else "SILENT_OBSERVATION_COMPLETED" if p["allowed_assistance_level"] == "SILENT_OBSERVATION_ONLY" else "PARTIAL_EXAM_PREPARED" if any(a["completeness"] != "COMPLETE" for a in p["code_artifacts"]) else "EXAM_PREPARED"
            # The model may conservatively identify genuinely unusable prose or
            # unavoidable leakage, but may never invent a different scope lock.
            permitted = {expected, "PEDAGOGICAL_LOCK_TRIGGERED"}
            if p["operation"] == "ANALYZE_RESPONSE":
                permitted.add("INSUFFICIENT_EVIDENCE")
            if status not in permitted or (status == "PEDAGOGICAL_LOCK_TRIGGERED" and o["error_code"] != "SOLUTION_LEAKAGE_PREVENTED") or (status == "INSUFFICIENT_EVIDENCE" and o["error_code"] != "EMPTY_OR_UNUSABLE_RESPONSE"):
                return self._post("INVALID_OUTPUT_STATUS", "POST-02", "Output status contradicts input operation, completeness, scope or assistance mode.")
        scope = o["scope_evaluation"]
        echo = {"objective_id": "objective_id", "session_mode_evaluated": "session_mode", "evaluated_domain": "learning_domain", "evaluated_language": "programming_language", "evaluated_context_type": "project_context_type", "allowed_assistance_level_evaluated": "allowed_assistance_level"}
        if any(o[k] != p[v] for k, v in (("task_id", "task_id"), ("as_of_evaluated", "as_of"), ("operation_evaluated", "operation"))) or (scope is not None and any(scope[k] != p[v] for k, v in echo.items())):
            return self._post("INVALID_OUTPUT_ECHO_MISMATCH", "POST-02", "Input identity, timestamp, operation and scope fields must echo exactly.")
        if scope is not None:
            tag = "OUT_OF_SCOPE" if status == "OUT_OF_SCOPE" else p["scope_readiness_input"]
            c_detected = p["learning_domain"] in {"C_PROGRAMMING", "42_PISCINE"} or p["programming_language"] == "C" or p["project_context_type"] in {"42_PISCINE", "C_STANDALONE"}
            if scope["scope_readiness_tag"] != tag or scope["c_or_42_detected"] != c_detected or scope["prior_assistance_preserved"] is not True:
                return self._post("INVALID_OUTPUT_ECHO_MISMATCH", "POST-02", "Scope readiness, C/42 detection and preserved assistance must reflect the input.")
        private = o["orchestrator_only_payload"]
        questions, observations, manifest = private["socratic_questions"], private["response_observations"], private["evaluator_bridge_manifest"]
        bc = p.get("binding_constraints", {})
        if len(questions) > bc.get("max_questions", 0) or any(len(q["on_demand_hints"]) > bc.get("max_hints_per_question", 0) or (p["allowed_assistance_level"] == "QUESTION_ONLY" and q["on_demand_hints"]) for q in questions):
            return self._post("HINT_OR_QUESTION_CAP_VIOLATION", "POST-03", "Output exceeds dynamic question or hint limits.")
        visible = o["learner_visible_payload"]
        if visible:
            notice = "TPL_NOTICE_PARTIAL_EVIDENCE" if status == "PARTIAL_EXAM_PREPARED" else "TPL_NOTICE_IN_SCOPE_QUESTION_ONLY" if p["allowed_assistance_level"] == "QUESTION_ONLY" else "TPL_NOTICE_IN_SCOPE_ON_DEMAND_HINTS"
            if visible["active_scope_notice"] != self._notices[notice]:
                return self._post("HINT_OR_QUESTION_CAP_VIOLATION", "POST-03", "Active notice does not match deterministic partial/assistance priority.")
        seen_criteria, seen_hints = set(), set()
        for ordinal, q in enumerate(questions, 1):
            if not q["question_id"].startswith(f"Q-{ordinal:02d}-") or q["objective_id"] != p["objective_id"]:
                return self._post("DUPLICATE_OR_UNORDERED_OUTPUT_ID", "POST-04", "Question ordinals or objective identifiers are inconsistent.")
            for index, c in enumerate(q["expected_explanation_criteria"], 1):
                if c["criterion_id"] != f"CRIT-Q{ordinal:02d}-{index:02d}" or c["criterion_id"] in seen_criteria:
                    return self._post("DUPLICATE_OR_UNORDERED_OUTPUT_ID", "POST-04", "Criterion identifiers must be unique and ordinal within their question.")
                seen_criteria.add(c["criterion_id"])
            for index, h in enumerate(q["on_demand_hints"], 1):
                if not h["hint_id"].startswith(f"H-{ordinal:02d}-") or h["hint_order"] != index or h["hint_id"] in seen_hints:
                    return self._post("DUPLICATE_OR_UNORDERED_OUTPUT_ID", "POST-04", "Hint identifiers and hint_order must be unique and sequential.")
                seen_hints.add(h["hint_id"])
        for ref in [q["source_ref"] for q in questions] + private["unverified_observations_requiring_review"]:
            if not self._reference(ref, p["code_artifacts"], complete=True):
                return self._post("OUT_OF_BOUNDS_SOURCE_REF", "POST-05", "Every output source reference must resolve within a complete input artifact.")
            finding = ref.get("upstream_finding_id")
            if finding is not None and not any(u["finding_id"] == finding and u["artifact_id"] == ref["artifact_id"] and u["snapshot_id"] == ref["snapshot_id"] for u in p["upstream_review_refs"]):
                return self._post("OUT_OF_BOUNDS_SOURCE_REF", "POST-05", "Upstream finding reference does not match its artifact and snapshot.")
        if status == "PARTIAL_EXAM_PREPARED":
            incomplete = {a["artifact_id"] for a in p["code_artifacts"] if a["completeness"] != "COMPLETE"}
            limited = {l["artifact_id"] for l in o["analysis_limitations"] if l["limitation_code"] == "PARTIAL_ARTIFACT_TRUNCATED"}
            if not incomplete <= limited:
                return self._post("OUT_OF_BOUNDS_SOURCE_REF", "POST-05", "Each excluded incomplete artifact requires its own partial-evidence limitation.")
        if status == "RESPONSE_ANALYZED":
            if not self._registry_valid(p, exam_registry) or not self._unique(observations, "response_id") or {r["response_id"] for r in observations} != {r["response_id"] for r in p["learner_responses"]}:
                return self._post("CRITERION_MUTATION_DETECTED", "POST-06", "Response observations must cover the exact trusted response and exam records.")
            responses = {r["response_id"]: r for r in p["learner_responses"]}
            registered = {q["question_id"]: q for q in p["prior_exam_package"]["registered_questions"]}
            for observation in observations:
                response = responses[observation["response_id"]]
                question = registered[response["question_id"]]
                criteria = {c["criterion_id"]: c["criterion_text"] for c in question["immutable_criteria"]}
                evaluations = observation["criterion_evaluations"]
                if any(observation[k] != response[k] for k in ("question_id", "attempt_id", "artifact_id", "snapshot_id")) or not self._unique(evaluations, "criterion_id") or {c["criterion_id"] for c in evaluations} != set(response["criterion_ids_to_evaluate"]) or any(criteria.get(c["criterion_id"]) != c["criterion_text"] for c in evaluations):
                    return self._post("CRITERION_MUTATION_DETECTED", "POST-06", "Response identity and immutable criterion pairs must match the requested trusted criteria exactly.")
                if any(c["verbatim_response_excerpt"] is not None and c["verbatim_response_excerpt"] not in response["raw_response_text"] for c in evaluations):
                    return self._post("CRITERION_MUTATION_DETECTED", "POST-06", "Verbatim excerpts must occur in the original learner response.")
        if manifest:
            expected_assistance = self.assistance_values(p)
            if any(manifest[k] != value for k, value in expected_assistance.items()):
                return self._post("ASSISTANCE_LATTICE_MISMATCH", "POST-07", "Known assistance, effective floor and eligibility must equal the deterministic trusted-ledger lattice.")
        if visible:
            initial = questions[0]
            expected_visible = {k: initial[k] for k in ("question_id", "question_type", "neutral_question_prompt")}
            expected_visible.update({k: initial["source_ref"][k] for k in ("artifact_id", "snapshot_id", "start_line", "end_line")})
            if visible["canonical_initial_question_id"] != initial["question_id"] or visible["initial_neutral_question"] != expected_visible:
                return self._post("VISIBLE_PRIVATE_QUESTION_DESYNC", "POST-08", "The public initial question must exactly match the private first question.")
        if manifest:
            refs = [q["source_ref"]["artifact_id"] for q in questions]
            responses = p["learner_responses"]
            duplicate = len(refs) != len(set(refs)) or any(len([r[key] for r in responses]) != len({r[key] for r in responses}) for key in ("artifact_id", "context_signature"))
            if manifest["duplicate_context_warning"] != duplicate:
                return self._post("DUPLICATE_CONTEXT_WARNING_MISMATCH", "POST-09", "Duplicate context warning must reflect repeated artifacts or response context signatures.")
        for artifact in p["code_artifacts"]:
            if status != "INVALID_INPUT_CONTRACT" and artifact["static_syntax_status"] == "SYNTAX_ERROR_OBSERVED" and not any(l["artifact_id"] == artifact["artifact_id"] and l["limitation_code"] == "STATIC_ONLY_SYNTAX_ERROR_OBSERVED" for l in o["analysis_limitations"]):
                return self._post("MISSING_SYNTAX_LIMITATION", "POST-10", "Each syntax-error artifact requires an explicit static-only limitation.")
        skill = p.get("verified_skill_evidence", {})
        if not skill.get("verified_skills") and any(q["question_type"] == "ARCHITECTURAL_TRADEOFF" for q in questions):
            return self._post("UNVERIFIED_SKILL_OVERREACH", "POST-11", "Architectural tradeoff questions require verified foundational skills.")
        if questions and skill.get("unverified_or_early_topics"):
            if self.semantic_reviewer is None:
                return self._post("SEMANTIC_REVIEW_REQUIRED", "POST-11", "A trusted semantic reviewer must establish that questions do not require early topics; lexical matching cannot guarantee this.")
            try:
                review = self.semantic_reviewer({
                    "kind": "POST-11_EARLY_TOPIC_EXCLUSION",
                    "payload": copy.deepcopy(p), "questions": copy.deepcopy(questions),
                })
            except Exception:
                return self._post("SEMANTIC_REVIEW_REQUIRED", "POST-11", "The trusted early-topic semantic reviewer failed closed.")
            required = {"early_topic_overreach", "architectural_prerequisites_unverified"}
            if not isinstance(review, dict) or set(review) != required or any(type(value) is not bool for value in review.values()):
                return self._post("SEMANTIC_REVIEW_REQUIRED", "POST-11", "Semantic reviewer did not return the exact two required boolean findings.")
            if any(review.values()):
                return self._post("UNVERIFIED_SKILL_OVERREACH", "POST-11", "Trusted semantic review found unverified topic or architectural prerequisite overreach.")
        if manifest:
            compatible = MATRIX.get(p["learning_domain"], (None, None, None, False))[3]
            mapped = p["learning_domain"] if compatible else None
            if manifest["compatible_with_learning_evaluator"] != compatible or manifest["mapped_evaluator_domain"] != mapped or manifest["eligible_for_independent_attempt_submission"] != self.assistance_values(p)["eligible_for_independent_attempt_submission"]:
                return self._post("EVALUATOR_MAPPING_VIOLATION", "POST-12", "Evaluator domain and independent eligibility must match the accepted scope matrix and assistance lattice.")
        return {"ok": True, "output": o}

    # -------------------------------------------------------------------------
    # Project & Document Defense Validation (v1.3: PREPARE_PROJECT_DEFENSE / ANALYZE_PROJECT_DEFENSE)
    # -------------------------------------------------------------------------

    def _doc_batch_registry_valid(self, p: dict, batch_registry: dict, response_registry: dict | None = None) -> bool:
        pkg = p.get("prior_defense_batch_package")
        doc = p.get("document_descriptor", {})
        if pkg is None or not isinstance(batch_registry, dict):
            return False
        if (pkg["project_id"] != p["project_id"]
                or pkg["defense_session_id"] != p["defense_session_id"]
                or pkg["document_id"] != doc.get("document_id")
                or pkg["document_version"] != doc.get("document_version")
                or pkg["document_sha256"] != doc.get("document_sha256")
                or doc_package_hash(pkg) != pkg["batch_package_sha256"]):
            return False
        if batch_registry.get(pkg["batch_exam_id"]) != pkg:
            return False
        questions = pkg["registered_questions"]
        if not self._unique(questions, "question_id"):
            return False
        all_criteria = []
        by_id = {q['question_id']: q for q in questions}
        for q in questions:
            if not self._unique(q["immutable_criteria"], "criterion_id"):
                return False
            if q['parent_question_id']:
                parent = by_id.get(q['parent_question_id'])
                if parent is None or q['immutable_criteria'] != parent['immutable_criteria']:
                    return False
            else:
                all_criteria.extend(c["criterion_id"] for c in q["immutable_criteria"])
        if len(all_criteria) != len(set(all_criteria)):
            return False
        by_id = {q["question_id"]: q for q in questions}
        for resp in p["defense_responses"]:
            q = by_id.get(resp["question_id"])
            if q is None or not q["delivered_to_learner"] or q["voided"] or q["defense_record_closed"]:
                return False
            if (q["parent_question_id"] != resp["parent_question_id"]
                    or q["section_id"] != resp["section_id"]
                    or q["passage_id"] != resp["passage_id"]
                    or q["target_dimension"] != resp["target_dimension"]):
                return False
            if not set(resp["criterion_ids_to_evaluate"]) <= {c["criterion_id"] for c in q["immutable_criteria"]}:
                return False
            if response_registry is not None:
                if not isinstance(response_registry, dict):
                    return False
                trusted_resp = response_registry.get(resp["response_id"])
                if trusted_resp is None:
                    return False
                if (trusted_resp.get("defense_session_id") != p["defense_session_id"]
                        or trusted_resp.get("batch_exam_id") != pkg["batch_exam_id"]
                        or trusted_resp.get("question_id") != resp["question_id"]
                        or trusted_resp.get("parent_question_id") != resp["parent_question_id"]
                        or trusted_resp.get("turn_id") != resp["turn_id"]
                        or trusted_resp.get("section_id") != resp["section_id"]
                        or trusted_resp.get("passage_id") != resp["passage_id"]
                        or trusted_resp.get("target_dimension") != resp["target_dimension"]
                        or trusted_resp.get("document_version") != doc.get("document_version")
                        or trusted_resp.get("document_sha256") != doc.get("document_sha256")
                        or trusted_resp.get("response_text") != resp["raw_response_text"]
                        or bool(trusted_resp.get("is_idk_declaration")) != bool(resp["is_idk_declaration"])
                        or bool(trusted_resp.get("declared_design_change")) != bool(resp["declared_design_change"])):
                    return False
        return True

    def preflight_doc_defense(self, raw: str | bytes | dict, *, batch_registry: dict,
                              session_state: dict | None, response_registry: dict | None = None) -> dict:
        if self._doc_input is None:
            raise ValidationDependencyError("PROJECT_DEFENSE_CONTRACT.md schemas are not loaded")
        try:
            p = strict_json(raw)
            if not isinstance(p.get("task_id"), str) or not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", p["task_id"]):
                raise ValueError("Invalid task identity")
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            return self._pre(None, "INVALID_INPUT_CONTRACT", "UNPARSEABLE_OR_MISSING_TASK_ID", "DOC-PRE-01", "A finite UTF-8 JSON object and valid task_id are required.")
        size = len(raw.decode("utf-8") if isinstance(raw, bytes) else raw) if isinstance(raw, (str, bytes)) else len(json.dumps(p, ensure_ascii=False))
        inv = p.get("full_section_inventory")
        passages = p.get("current_batch_passages")
        bounded = size > 98304
        if isinstance(inv, list):
            bounded |= len(inv) > 64
        if isinstance(passages, list):
            for psg in passages:
                if isinstance(psg, dict) and isinstance(psg.get("verbatim_text"), str):
                    psg["verbatim_text"] = psg["verbatim_text"].replace("\r\n", "\n").replace("\r", "\n")
            bounded |= len(passages) > 24
            bounded |= any(isinstance(psg, dict) and isinstance(psg.get("verbatim_text"), str) and len(psg["verbatim_text"]) > 16384 for psg in passages)
        if bounded:
            return self._pre(p, "INVALID_INPUT_CONTRACT", "PAYLOAD_BOUNDS_EXCEEDED", "DOC-PRE-02", "Document defense input exceeds declared contract payload bounds.")
        errors = list(self._doc_input.iter_errors(p))
        if errors:
            permissions = p.get("tool_permissions")
            error = "SCHEMA_OR_VERSION_MISMATCH"
            if isinstance(permissions, dict) and (permissions.get("allowed_tools") or any(permissions.get(k) is True for k in ("code_execution_allowed", "mutation_allowed", "web_or_mcp_allowed", "subagent_invocation_allowed"))):
                error = "TOOL_PERMISSION_VIOLATION"
            elif isinstance(p.get("learning_domain"), str) and p["learning_domain"] not in self.doc_input_schema["properties"]["learning_domain"]["enum"]:
                error = "UNKNOWN_DOMAIN_OR_LANGUAGE"
            return self._pre(p, "INVALID_INPUT_CONTRACT", error, "DOC-PRE-03", "Document defense input does not satisfy Draft 2020-12 schema constraints.")
        pkg = p["prior_defense_batch_package"]
        if not self._calendar(p["as_of"]) or (pkg is not None and not self._calendar(pkg["created_as_of"])):
            return self._pre(p, "INVALID_INPUT_CONTRACT", "SCHEMA_OR_VERSION_MISMATCH", "DOC-PRE-03", "Timestamp is not a real timezone-aware calendar value.")
        doc = p["document_descriptor"]
        if doc["batch_index"] > doc["total_batches"]:
            return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_SECTION_OR_PASSAGE_REF", "DOC-PRE-04", "batch_index cannot exceed total_batches.")
        if not self._unique(inv, "section_id") or [s["ordinal"] for s in inv] != list(range(1, len(inv) + 1)):
            return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_SECTION_OR_PASSAGE_REF", "DOC-PRE-04", "Section inventory must have unique section_ids and sequential ordinals 1..N.")
        sections_by_id = {s["section_id"]: s for s in inv}
        for s in inv:
            prior_dims = [d["dimension"] for d in s["prior_dimension_statuses"]]
            if len(prior_dims) != len(set(prior_dims)) or set(prior_dims) != set(s["relevant_dimensions"]):
                return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_SECTION_OR_PASSAGE_REF", "DOC-PRE-04", "prior_dimension_statuses must match relevant_dimensions 1-to-1.")
        if not self._unique(passages, "passage_id"):
            return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_SECTION_OR_PASSAGE_REF", "DOC-PRE-04", "Passage IDs must be unique.")
        batch_sec_ids = {s["section_id"] for s in inv if s["in_current_batch"]}
        if not batch_sec_ids:
            return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_SECTION_OR_PASSAGE_REF", "DOC-PRE-04", "At least one section must be marked in_current_batch.")
        seen_batch_sections = set()
        for psg in passages:
            sec = sections_by_id.get(psg["section_id"])
            if sec is None or not sec["in_current_batch"] or psg["heading_path"] != sec["heading_path"]:
                return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_SECTION_OR_PASSAGE_REF", "DOC-PRE-04", "Passage section_id/heading_path must belong to an active batch section.")
            expected_sha = "sha256:" + hashlib.sha256(psg["verbatim_text"].encode("utf-8")).hexdigest()
            if psg["passage_sha256"] != expected_sha:
                return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_SECTION_OR_PASSAGE_REF", "DOC-PRE-04", "Passage SHA-256 digest does not match verbatim_text.")
            if any(ref not in sections_by_id for ref in psg["cross_section_refs"]):
                return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_SECTION_OR_PASSAGE_REF", "DOC-PRE-04", "Cross-section reference points to an unknown section_id.")
            seen_batch_sections.add(psg["section_id"])
        if seen_batch_sections != batch_sec_ids:
            return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_SECTION_OR_PASSAGE_REF", "DOC-PRE-04", "Every section in_current_batch must have at least one verbatim passage.")
        contrib = p["contribution_context"]
        owned = set(contrib["declared_owned_section_ids"])
        delegated = set(contrib["delegated_or_teammate_section_ids"])
        if not (owned <= set(sections_by_id)) or not (delegated <= set(sections_by_id)) or (owned & delegated):
            return self._pre(p, "INVALID_INPUT_CONTRACT", "INVALID_SECTION_OR_PASSAGE_REF", "DOC-PRE-04", "Contribution section IDs must exist in inventory and not overlap.")
        if p["learning_domain"] in {"C_PROGRAMMING", "42_PISCINE"}:
            return self._pre(p, "OUT_OF_SCOPE", "FORBIDDEN_DOMAIN_C_OR_42", "DOC-PRE-08", "C and 42 domains are outside this agent's scope.")
        for psg in passages:
            status_ep = psg["claim_epistemic_status"]
            basis = psg["evidence_basis"]
            refs = psg["observed_evidence_refs"]
            if (status_ep == "MEASURED_RESULT" and (basis == "USER_DECLARATION" or not refs)) or (basis == "USER_DECLARATION" and refs) or (basis in {"OBSERVED_EVIDENCE", "MIXED"} and not refs):
                return self._pre(p, "CONFLICTING_EVIDENCE", "EPISTEMIC_CLAIM_CONTRADICTION", "DOC-PRE-05", "Claim epistemic status contradicts evidence basis or observed_evidence_refs.")
        if p["operation"] == "PREPARE_PROJECT_DEFENSE":
            if pkg is not None or p["defense_responses"]:
                return self._pre(p, "INVALID_INPUT_CONTRACT", "UNREGISTERED_QUESTION_OR_CRITERION_REF", "DOC-PRE-06", "PREPARE_PROJECT_DEFENSE must not include prior_defense_batch_package or defense_responses.")
        else:
            if not p["defense_responses"] or not self._unique(p["defense_responses"], "response_id") or p["allowed_assistance_level"] == "SILENT_OBSERVATION_ONLY" or not self._doc_batch_registry_valid(p, batch_registry, response_registry=response_registry):
                return self._pre(p, "INVALID_INPUT_CONTRACT", "UNREGISTERED_QUESTION_OR_CRITERION_REF", "DOC-PRE-06", "ANALYZE_PROJECT_DEFENSE requires a trusted batch package and valid delivered response references.")
        if session_state is None or session_state != p["session_state_snapshot"]:
            return self._pre(p, "INVALID_INPUT_CONTRACT", "TRUSTED_SESSION_STATE_MISMATCH", "DOC-PRE-07", "Trusted local session_state_snapshot does not match SQLite session state.")
        snap = p["session_state_snapshot"]
        if (snap["defense_session_id"] != p["defense_session_id"]
                or snap["project_id"] != p["project_id"]
                or snap["session_status"] != "ACTIVE"
                or snap["current_document_version"] != doc["document_version"]
                or snap["current_document_sha256"] != doc["document_sha256"]):
            return self._pre(p, "INVALID_INPUT_CONTRACT", "TRUSTED_SESSION_STATE_MISMATCH", "DOC-PRE-07", "Session identity, active status, or current document version/hash does not match SQLite session state.")
        if not any(psg["completeness"] == "COMPLETE" for psg in passages):
            return self._pre(p, "INSUFFICIENT_EVIDENCE", "UNREADABLE_OR_MISSING_TARGET_EVIDENCE", "DOC-PRE-09", "All current batch passages are unreadable visuals; cannot prepare or analyze defense.")
        if p["operation"] == "ANALYZE_PROJECT_DEFENSE" and any(not r["raw_response_text"].strip() for r in p["defense_responses"]):
            return self._pre(p, "INSUFFICIENT_EVIDENCE", "EMPTY_OR_UNUSABLE_RESPONSE", "DOC-PRE-10", "A defense response contains no usable text.")
        return {"ok": True, "payload": p}

    @staticmethod
    def _has_private_text_leak(query: str, p: dict) -> bool:
        q_norm = " ".join(query.lower().split())
        doc = p["document_descriptor"]
        for identifier in (p["project_id"], doc["document_id"], doc["document_title"]):
            if identifier and identifier.lower() in q_norm:
                return True
        sources = [doc["document_summary"]] + [psg["verbatim_text"] for psg in p["current_batch_passages"]]
        for src in sources:
            s_norm = " ".join(src.lower().split())
            if len(s_norm) >= 24:
                for idx in range(0, len(s_norm) - 23, 4):
                    if s_norm[idx:idx + 24] in q_norm:
                        return True
        return False

    def postflight_doc_defense(self, payload: dict, output: dict | str, *, batch_registry: dict,
                               session_state: dict | None, response_registry: dict | None = None) -> dict:
        if self._doc_output is None:
            raise ValidationDependencyError("PROJECT_DEFENSE_CONTRACT.md schemas are not loaded")
        try:
            o = strict_json(output)
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            return self._post("INVALID_OUTPUT_SCHEMA", "DOC-POST-01", "Output must be a single finite JSON object.")
        schema_errors = list(self._doc_output.iter_errors(o))
        if schema_errors or not self._calendar(o.get("as_of_evaluated")):
            result = self._post("INVALID_OUTPUT_SCHEMA", "DOC-POST-01", "Output violates the accepted document-defense schema or real calendar timestamp.")
            result["schema_errors"] = [{"path": list(e.absolute_path), "keyword": e.validator,
                                        "message": e.message[:600]} for e in schema_errors[:8]]
            return result
        pre = self.preflight_doc_defense(payload, batch_registry=batch_registry, session_state=session_state, response_registry=response_registry)
        p = pre.get("payload")
        if p is None:
            return self._post("INVALID_OUTPUT_ECHO_MISMATCH", "DOC-POST-02", "A valid input identity is required for model output validation.")
        status = o["terminal_status"]
        if not pre["ok"]:
            if status != pre["terminal_status"] or o["error_code"] != pre["error_code"]:
                return self._post("INVALID_OUTPUT_STATUS", "DOC-POST-02", "Output does not preserve deterministic document-defense input error precedence.")
            if status == "INVALID_INPUT_CONTRACT":
                op = p.get("operation") if p.get("operation") in ("PREPARE_PROJECT_DEFENSE", "ANALYZE_PROJECT_DEFENSE") else None
                if o["task_id"] != p["task_id"] or o["operation_evaluated"] != op or (self._calendar(p.get("as_of")) and o["as_of_evaluated"] != p["as_of"]):
                    return self._post("INVALID_OUTPUT_ECHO_MISMATCH", "DOC-POST-02", "Invalid-input terminal envelope must echo identity fields.")
                return {"ok": True, "output": o}
            return {"ok": True, "output": o}

        inv = p["full_section_inventory"]
        doc = p["document_descriptor"]
        expected_inspected = [s["section_id"] for s in inv if s["in_current_batch"]]
        expected_uninspected = [s["section_id"] for s in inv if not s["in_current_batch"]]
        expected_waiting = [s["section_id"] for s in inv if s["has_unreadable_visuals"]]
        expected_missing_contrib = p["contribution_context"]["missing_contribution_fields"]

        if p["operation"] == "ANALYZE_PROJECT_DEFENSE":
            expected_status = "PROJECT_DEFENSE_ANALYZED"
        elif p["allowed_assistance_level"] == "SILENT_OBSERVATION_ONLY":
            expected_status = "SILENT_OBSERVATION_COMPLETED"
        elif expected_uninspected or expected_waiting or any(psg["completeness"] != "COMPLETE" for psg in p["current_batch_passages"]):
            expected_status = "PARTIAL_PROJECT_DEFENSE_PREPARED"
        else:
            expected_status = "PROJECT_DEFENSE_PREPARED"

        permitted = {expected_status, "PEDAGOGICAL_LOCK_TRIGGERED"}
        if p["operation"] == "ANALYZE_PROJECT_DEFENSE":
            permitted.add("INSUFFICIENT_EVIDENCE")
        if status not in permitted or (status == "PEDAGOGICAL_LOCK_TRIGGERED" and o["error_code"] != "SOLUTION_LEAKAGE_PREVENTED") or (status == "INSUFFICIENT_EVIDENCE" and o["error_code"] != "EMPTY_OR_UNUSABLE_RESPONSE"):
            return self._post("INVALID_OUTPUT_STATUS", "DOC-POST-02", "Output terminal_status contradicts operation, batch completeness, or assistance level.")
        if status in {"PROJECT_DEFENSE_PREPARED", "PARTIAL_PROJECT_DEFENSE_PREPARED", "PROJECT_DEFENSE_ANALYZED", "SILENT_OBSERVATION_COMPLETED"} and (o["error_code"] is not None or o["error_detail"] is not None):
            return self._post("INVALID_OUTPUT_STATUS", "DOC-POST-02", "Successful terminal status must have null error_code and error_detail.")

        scope = o["project_defense_scope_evaluation"]
        if scope is None:
            return self._post("INVALID_OUTPUT_ECHO_MISMATCH", "DOC-POST-02", "project_defense_scope_evaluation is required.")
        if (o["task_id"] != p["task_id"]
                or o["as_of_evaluated"] != p["as_of"]
                or o["operation_evaluated"] != p["operation"]
                or scope["project_id"] != p["project_id"]
                or scope["defense_session_id"] != p["defense_session_id"]
                or scope["document_id"] != doc["document_id"]
                or scope["document_version_evaluated"] != doc["document_version"]
                or scope["document_sha256_evaluated"] != doc["document_sha256"]
                or scope["document_type_evaluated"] != doc["document_type"]
                or scope["evaluated_domain"] != p["learning_domain"]
                or scope["allowed_assistance_level_evaluated"] != p["allowed_assistance_level"]
                or scope["c_or_42_detected"] is not False
                or scope["prior_assistance_preserved"] is not True
                or scope["batch_index_evaluated"] != doc["batch_index"]
                or scope["total_batches_evaluated"] != doc["total_batches"]
                or scope["inspected_section_ids_in_batch"] != expected_inspected
                or scope["uninspected_section_ids"] != expected_uninspected
                or scope["waiting_visual_section_ids"] != expected_waiting
                or scope["missing_contribution_fields_to_ask"] != expected_missing_contrib):
            return self._post("INVALID_OUTPUT_ECHO_MISMATCH", "DOC-POST-02", "Scope evaluation fields, uninspected sections, waiting visual sections, or missing contribution fields do not match input.")

        private = o["orchestrator_only_payload"]
        if private is None:
            return self._post("INVALID_OUTPUT_SCHEMA", "DOC-POST-01", "orchestrator_only_payload is required.")
        questions = private["defense_questions"]
        observations = private["defense_response_observations"]
        summary = private["defense_outcome_summary"]
        visible = o["learner_visible_payload"]

        if status in {"PROJECT_DEFENSE_PREPARED", "PARTIAL_PROJECT_DEFENSE_PREPARED"}:
            if not questions or observations or visible is None:
                return self._post("HINT_OR_QUESTION_CAP_VIOLATION", "DOC-POST-03", "Prepared defense must include questions, no response observations, and a learner_visible_payload.")
            notice_key = ("TPL_DOC_NOTICE_PARTIAL_OR_DEFERRED_SCOPE" if status == "PARTIAL_PROJECT_DEFENSE_PREPARED"
                          else "TPL_DOC_NOTICE_FULL_BATCH_QUESTION_ONLY" if p["allowed_assistance_level"] == "QUESTION_ONLY"
                          else "TPL_DOC_NOTICE_FULL_BATCH_ON_DEMAND_HINTS")
            if visible["active_scope_notice"] != self._doc_notices[notice_key]:
                return self._post("HINT_OR_QUESTION_CAP_VIOLATION", "DOC-POST-03", "active_scope_notice does not match deterministic batch/assistance priority.")
        else:
            if visible is not None:
                return self._post("HINT_OR_QUESTION_CAP_VIOLATION", "DOC-POST-03", "learner_visible_payload must be null outside prepared defense statuses.")
            if status == "PROJECT_DEFENSE_ANALYZED" and (questions or not observations):
                return self._post("HINT_OR_QUESTION_CAP_VIOLATION", "DOC-POST-03", "ANALYZE_PROJECT_DEFENSE must return observations and no new main defense_questions.")
            if status == "SILENT_OBSERVATION_COMPLETED" and (questions or observations):
                return self._post("HINT_OR_QUESTION_CAP_VIOLATION", "DOC-POST-03", "SILENT_OBSERVATION_COMPLETED must not emit questions or observations.")

        if p["allowed_assistance_level"] == "QUESTION_ONLY" and any(q["on_demand_hints"] for q in questions):
            return self._post("HINT_OR_QUESTION_CAP_VIOLATION", "DOC-POST-03", "QUESTION_ONLY mode forbids on_demand_hints.")

        seen_q, seen_c, seen_h = set(), set(), set()
        for ordinal, q in enumerate(questions, 1):
            if not q["question_id"].startswith(f"DQ-{ordinal:02d}-") or q["question_id"] in seen_q:
                return self._post("DUPLICATE_OR_UNORDERED_OUTPUT_ID", "DOC-POST-04", "Defense question IDs must be sequential DQ-01-*, DQ-02-* and unique.")
            seen_q.add(q["question_id"])
            if _DOC_CODE_LEAK.search(q["neutral_question_prompt"]):
                return self._post("SOLUTION_LEAKAGE_PREVENTED", "DOC-POST-04", "Question prompt contains prohibited code or solution syntax.")
            for c_idx, c in enumerate(q["expected_explanation_criteria"], 1):
                if c["criterion_id"] != f"DCRIT-Q{ordinal:02d}-{c_idx:02d}" or c["criterion_id"] in seen_c:
                    return self._post("DUPLICATE_OR_UNORDERED_OUTPUT_ID", "DOC-POST-04", "Criterion IDs must be sequential DCRIT-Qxx-yy and unique.")
                seen_c.add(c["criterion_id"])
            for h_idx, h in enumerate(q["on_demand_hints"], 1):
                if not h["hint_id"].startswith(f"DH-{ordinal:02d}-{h_idx:02d}-") or h["hint_order"] != h_idx or h["hint_id"] in seen_h:
                    return self._post("DUPLICATE_OR_UNORDERED_OUTPUT_ID", "DOC-POST-04", "Hint IDs must be sequential DH-xx-yy-* and unique.")
                if _DOC_CODE_LEAK.search(h["conceptual_nudge"]):
                    return self._post("SOLUTION_LEAKAGE_PREVENTED", "DOC-POST-04", "Hint contains prohibited code or solution syntax.")
                seen_h.add(h["hint_id"])

        passages_by_id = {psg["passage_id"]: psg for psg in p["current_batch_passages"] if psg["completeness"] == "COMPLETE"}
        sections_by_id = {s["section_id"]: s for s in inv}
        for q in questions:
            psg = passages_by_id.get(q["passage_id"])
            sec = sections_by_id.get(q["section_id"])
            if (psg is None or sec is None or psg["section_id"] != q["section_id"]
                    or q["heading_path"] != psg["heading_path"]
                    or q["claim_epistemic_status"] != psg["claim_epistemic_status"]
                    or q["evidence_basis"] != psg["evidence_basis"]
                    or not set(q["cross_section_refs"]) <= set(psg["cross_section_refs"])
                    or q["target_dimension"] not in sec["relevant_dimensions"]):
                return self._post("OUT_OF_BOUNDS_SOURCE_REF", "DOC-POST-05", "Question reference does not match a COMPLETE passage and relevant section dimension.")
            if q["addresses_missing_contribution"] and not expected_missing_contrib:
                return self._post("OUT_OF_BOUNDS_SOURCE_REF", "DOC-POST-05", "addresses_missing_contribution cannot be true when no contribution fields are missing.")

        lim_codes = {(l["limitation_code"], l["section_id"]) for l in o["analysis_limitations"]}
        for wait_sec in expected_waiting:
            if ("UNREADABLE_VISUAL_SCOPE_DEFERRED", wait_sec) not in lim_codes:
                return self._post("OUT_OF_BOUNDS_SOURCE_REF", "DOC-POST-05", "Each section with unreadable visuals requires UNREADABLE_VISUAL_SCOPE_DEFERRED.")
        if expected_uninspected and not any(l["limitation_code"] == "UNINSPECTED_BATCH_SECTIONS_REMAIN" for l in o["analysis_limitations"]):
            return self._post("OUT_OF_BOUNDS_SOURCE_REF", "DOC-POST-05", "Remaining uninspected sections require UNINSPECTED_BATCH_SECTIONS_REMAIN.")

        if visible is not None:
            q0 = questions[0]
            expected_vis_q = {k: q0[k] for k in ("question_id", "section_id", "passage_id", "heading_path", "target_dimension", "claim_epistemic_status", "neutral_question_prompt")}
            if (visible["canonical_initial_question_id"] != q0["question_id"]
                    or visible["initial_neutral_question"] != expected_vis_q
                    or visible["uninspected_section_ids"] != expected_uninspected
                    or visible["waiting_visual_section_ids"] != expected_waiting):
                return self._post("VISIBLE_PRIVATE_QUESTION_DESYNC", "DOC-POST-08", "learner_visible_payload does not match the first private question or section visibility lists.")

        snap = p["session_state_snapshot"]
        taught_pairs = {(t["section_id"], t["dimension"]) for t in snap["taught_dimensions"]}
        prior_assisted_pairs = {(a["section_id"], a["dimension"]) for a in snap["assisted_explained_dimensions"]}
        prior_unassisted_pairs = {(u["section_id"], u["dimension"]) for u in snap["unassisted_explained_dimensions"]}

        obs_unassisted: set[tuple[str, str]] = set()
        obs_assisted: set[tuple[str, str]] = set()
        obs_unexplained: set[tuple[str, str]] = set()

        if status == "PROJECT_DEFENSE_ANALYZED":
            if not self._unique(observations, "response_id") or [r["response_id"] for r in observations] != [r["response_id"] for r in p["defense_responses"]]:
                return self._post("CRITERION_MUTATION_DETECTED", "DOC-POST-06", "Observations must match defense_responses in order and identity.")
            registered = {q["question_id"]: q for q in p["prior_defense_batch_package"]["registered_questions"]}
            for obs, resp in zip(observations, p["defense_responses"]):
                q = registered[resp["question_id"]]
                crit_map = {c["criterion_id"]: c["criterion_text"] for c in q["immutable_criteria"]}
                evals = obs["criterion_evaluations"]
                if (any(obs[k] != resp[k] for k in ("question_id", "turn_id", "parent_question_id", "section_id", "passage_id", "target_dimension"))
                        or not self._unique(evals, "criterion_id")
                        or {c["criterion_id"] for c in evals} != set(resp["criterion_ids_to_evaluate"])
                        or any(crit_map.get(c["criterion_id"]) != c["criterion_text"] for c in evals)):
                    return self._post("CRITERION_MUTATION_DETECTED", "DOC-POST-06", "Observation identity or immutable criterion text does not match trusted registry.")
                if any(c["verbatim_response_excerpt"] is not None and c["verbatim_response_excerpt"] not in resp["raw_response_text"] for c in evals):
                    return self._post("CRITERION_MUTATION_DETECTED", "DOC-POST-06", "verbatim_response_excerpt must appear in raw_response_text.")

                verdict = obs["evaluation_verdict"]
                assist_cls = obs["assistance_classification_for_response"]

                followup = obs["followup_question"]
                if resp["parent_question_id"] is not None and followup is not None:
                    return self._post("FOLLOWUP_RULE_VIOLATION", "DOC-POST-07", "A follow-up response cannot trigger a second follow-up question.")
                if verdict in {"VAGUE_OR_INCOMPLETE_NEEDS_FOLLOWUP", "DESIGN_CHANGED_WITHOUT_RATIONALE"}:
                    if resp["parent_question_id"] is not None or followup is None:
                        return self._post("FOLLOWUP_RULE_VIOLATION", "DOC-POST-07", "Follow-up verdict on a main question requires a followup_question object.")
                    expected_reason = "DESIGN_DECISION_CHANGE_RATIONALE" if verdict == "DESIGN_CHANGED_WITHOUT_RATIONALE" else "CLARIFY_VAGUE_RESPONSE"
                    if (followup["parent_question_id"] != resp["question_id"]
                            or followup["followup_question_id"] != f"FQ-{resp['question_id']}-01"
                            or followup["section_id"] != resp["section_id"]
                            or followup["passage_id"] != resp["passage_id"]
                            or followup["target_dimension"] != resp["target_dimension"]
                            or followup["followup_reason"] != expected_reason
                            or _DOC_CODE_LEAK.search(followup["neutral_followup_prompt"])):
                        return self._post("FOLLOWUP_RULE_VIOLATION", "DOC-POST-07", "Follow-up question identity, reason, or safety check failed.")
                elif followup is not None:
                    return self._post("FOLLOWUP_RULE_VIOLATION", "DOC-POST-07", "followup_question is only permitted for vague or unstated-design-change verdicts.")

                ver_req = obs["external_verification_request"]
                if verdict == "PENDING_EXTERNAL_VERIFICATION":
                    if ver_req is None or self._has_private_text_leak(ver_req["sanitized_public_search_topic"], p):
                        return self._post("EXTERNAL_VERIFICATION_BOUNDARY_VIOLATION", "DOC-POST-09", "PENDING_EXTERNAL_VERIFICATION requires a sanitized public search topic without private project text.")
                elif ver_req is not None:
                    return self._post("EXTERNAL_VERIFICATION_BOUNDARY_VIOLATION", "DOC-POST-09", "external_verification_request must be null unless verdict is PENDING_EXTERNAL_VERIFICATION.")

                ext_out = resp.get("external_verification_outcome")
                if ext_out is not None and ext_out["status"] == "INCONCLUSIVE" and verdict != "UNVERIFIED_EXTERNAL_CLAIM":
                    return self._post("EXTERNAL_VERIFICATION_BOUNDARY_VIOLATION", "DOC-POST-09", "Inconclusive external verification must not fabricate a positive or negative verdict.")

                teach = obs["teaching_transition_packet"]
                if resp["is_idk_declaration"] or verdict == "IDK_DECLARED_READY_FOR_TEACHING":
                    if not resp["is_idk_declaration"] or verdict != "IDK_DECLARED_READY_FOR_TEACHING" or teach is None:
                        return self._post("TEACHING_TRANSITION_VIOLATION", "DOC-POST-10", "IDK declaration must produce IDK_DECLARED_READY_FOR_TEACHING and a teaching_transition_packet.")
                    if (teach["closed_question_id"] != resp["question_id"]
                            or teach["closed_response_id"] != resp["response_id"]
                            or teach["section_id"] != resp["section_id"]
                            or teach["target_dimension"] != resp["target_dimension"]):
                        return self._post("TEACHING_TRANSITION_VIOLATION", "DOC-POST-10", "Teaching transition packet must reference the exact closed question and response.")
                    combined_teach = teach["concept_and_rationale_explanation"] + "\n" + "\n".join(teach["suggested_approaches"])
                    if _DOC_CODE_LEAK.search(combined_teach):
                        return self._post("TEACHING_TRANSITION_VIOLATION", "DOC-POST-10", "Teaching transition packet must not contain ready-made project code.")
                    for crit_text in crit_map.values():
                        if crit_text.lower() in combined_teach.lower():
                            return self._post("TEACHING_TRANSITION_VIOLATION", "DOC-POST-10", "Teaching transition packet must not leak verbatim private rubric criteria.")
                elif teach is not None:
                    return self._post("TEACHING_TRANSITION_VIOLATION", "DOC-POST-10", "teaching_transition_packet is only permitted on IDK_DECLARED_READY_FOR_TEACHING.")

                pair = (resp["section_id"], resp["target_dimension"])
                if response_registry is not None and resp["response_id"] in response_registry:
                    tainted_at_submission = bool(response_registry[resp["response_id"]].get("was_assisted_at_submission"))
                else:
                    tainted_at_submission = (pair in taught_pairs or pair in prior_assisted_pairs)
                if tainted_at_submission and assist_cls == "UNASSISTED":
                    return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "A response submitted after teaching or assistance in its dimension cannot be classified as UNASSISTED.")

                if verdict in {"DIRECT_CRITERION_MATCH", "ALTERNATIVE_VALID_EXPLANATION"}:
                    if assist_cls == "NOT_EXPLAINED":
                        return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "Explained verdict cannot have NOT_EXPLAINED assistance classification.")
                    if any(c["status"] != "DEMONSTRATED" for c in evals):
                        return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "Explained verdict requires all evaluated criteria to have DEMONSTRATED status.")
                    if assist_cls == "UNASSISTED":
                        obs_unassisted.add(pair)
                    else:
                        obs_assisted.add(pair)
                else:
                    if assist_cls != "NOT_EXPLAINED":
                        return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "Non-explained verdict must have NOT_EXPLAINED assistance classification.")
                    obs_unexplained.add(pair)

        out_unassisted = {(u["section_id"], u["dimension"]) for u in summary["unassisted_explained_dimensions"]}
        out_assisted = {(a["section_id"], a["dimension"]) for a in summary["assisted_explained_dimensions"]}
        out_open = {(op["section_id"], op["dimension"]) for op in summary["open_dimensions"]}

        if (len(out_unassisted) != len(summary["unassisted_explained_dimensions"])
                or len(out_assisted) != len(summary["assisted_explained_dimensions"])
                or len(out_open) != len(summary["open_dimensions"])):
            return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "defense_outcome_summary lists must not contain duplicate (section_id, dimension) pairs.")

        expected_unassisted = prior_unassisted_pairs | obs_unassisted
        expected_assisted = (prior_assisted_pairs | obs_assisted) - expected_unassisted

        if not (prior_unassisted_pairs <= out_unassisted):
            return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "Previously unassisted explained dimensions must be preserved.")
        if out_unassisted != expected_unassisted or out_assisted != expected_assisted or (out_unassisted & out_assisted):
            return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "defense_outcome_summary explained dimensions must match prior session state plus verified observations without fabricated or tainted outcomes.")

        locks = summary["governance_locks"]
        if any(locks[k] is not False for k in ("overall_score_generated", "independent_competency_granted", "project_gate_approval_granted", "eligible_for_independent_attempt_submission")):
            return self._post("GOVERNANCE_LOCK_VIOLATION", "DOC-POST-12", "Governance locks must all be false.")

        expected_pairs = [(s["section_id"], dim) for s in inv for dim in s["relevant_dimensions"]]
        matrix_pairs = [(m["section_id"], m["dimension"]) for m in o["section_dimension_matrix"]]
        if matrix_pairs != expected_pairs:
            return self._post("GOVERNANCE_LOCK_VIOLATION", "DOC-POST-12", "section_dimension_matrix must cover every relevant (section_id, dimension) in inventory order.")

        matrix_open_pairs = set()
        open_reasons = {"AWAITING_BATCH_OR_QUESTION", "UNREADABLE_VISUAL_WAITING", "REQUIRES_FOLLOWUP_OR_VERIFICATION"}
        for m in o["section_dimension_matrix"]:
            mpair = (m["section_id"], m["dimension"])
            if mpair in expected_unassisted:
                if m["status"] != "INSPECTED" or m["status_reason"] != "EXPLAINED_UNASSISTED":
                    return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "section_dimension_matrix must mark unassisted explained dimensions as INSPECTED / EXPLAINED_UNASSISTED.")
            elif mpair in expected_assisted:
                if m["status"] != "INSPECTED" or m["status_reason"] != "EXPLAINED_WITH_ASSISTANCE":
                    return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "section_dimension_matrix must mark assisted explained dimensions as INSPECTED / EXPLAINED_WITH_ASSISTANCE.")
            elif mpair in taught_pairs and mpair not in obs_unexplained:
                if m["status"] == "ADDRESSED_WITH_TEACHING":
                    if m["status_reason"] != "TEACHING_DELIVERED":
                        return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "ADDRESSED_WITH_TEACHING entries in section_dimension_matrix must have status_reason TEACHING_DELIVERED.")
                elif m["status"] == "OPEN":
                    if m["status_reason"] not in open_reasons:
                        return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "OPEN entries in section_dimension_matrix must use a valid OPEN status_reason.")
                    matrix_open_pairs.add(mpair)
                else:
                    return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "Taught but unexplained relevant dimensions in section_dimension_matrix must be ADDRESSED_WITH_TEACHING or OPEN.")
            else:
                if m["status"] != "OPEN" or m["status_reason"] not in open_reasons:
                    return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "Relevant dimensions in section_dimension_matrix that are neither explained nor taught in canonical session state must remain OPEN.")
                matrix_open_pairs.add(mpair)

        if out_open != matrix_open_pairs:
            return self._post("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH", "DOC-POST-11", "defense_outcome_summary.open_dimensions must match OPEN entries in section_dimension_matrix.")
        return {"ok": True, "output": o}
