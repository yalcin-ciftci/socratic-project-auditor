"""Trusted, local SQLite state. Never construct this state from model ledger claims.

Initialization and exam registration are privileged orchestrator operations. Events
and responses are append-only. SQLite serializes revision checks and disclosure
commits, including the canonical package's delivered flag and its new digest.
Code-defense tables (ledgers, exams, events, responses) and their 20-record cap
remain unchanged; document-defense sessions use separate tables without a 20-record cap.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3


class StoreError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def package_digest(package: dict) -> str:
    body = {key: value for key, value in package.items() if key != "exam_package_sha256"}
    return hashlib.sha256(_dump(body).encode("utf-8")).hexdigest()


def doc_package_digest(package: dict) -> str:
    body = {key: value for key, value in package.items() if key != "batch_package_sha256"}
    return hashlib.sha256(_dump(body).encode("utf-8")).hexdigest()


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


EVENTS = {"QUESTION_SHOWN", "HINT_1_SHOWN", "HINT_2_SHOWN", "DIAGNOSIS_SHOWN",
          "RUBRIC_SHOWN", "EXTERNAL_REFERENCE_USED", "BRAINSTORMING_USED"}

DOC_EVENTS = {
    "DOC_QUESTION_SHOWN",
    "DOC_FOLLOWUP_SHOWN",
    "DOC_HINT_1_SHOWN",
    "DOC_HINT_2_SHOWN",
    "DEFENSE_RECORD_CLOSED_FOR_TEACHING",
    "TEACHING_EXPLANATION_SHOWN",
    "QUESTION_VOIDED_DEFECTIVE",
    "DOCUMENT_VERSION_UPDATED",
    "SESSION_PAUSED",
    "SESSION_RESUMED",
    "SESSION_STOPPED_BY_USER",
    "PRIOR_HELP_RECORDED",
}


class RuntimeStore:
    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.state_dir / "project_auditor.sqlite3"
        with self._connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS ledgers (
                  ledger_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK(revision>=1));
                CREATE TABLE IF NOT EXISTS exams (
                  exam_id TEXT PRIMARY KEY, package TEXT NOT NULL,
                  questions TEXT NOT NULL, assistance_level TEXT);
                CREATE TABLE IF NOT EXISTS events (
                  event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                  ledger_id TEXT NOT NULL REFERENCES ledgers(ledger_id),
                  exam_id TEXT NOT NULL REFERENCES exams(exam_id),
                  attempt_id TEXT NOT NULL, question_id TEXT NOT NULL,
                  artifact_id TEXT NOT NULL, snapshot_id TEXT NOT NULL,
                  event_type TEXT NOT NULL, hint_id TEXT NOT NULL DEFAULT '',
                  UNIQUE(ledger_id,exam_id,attempt_id,question_id,event_type,hint_id));
                CREATE TABLE IF NOT EXISTS responses (
                  exam_id TEXT NOT NULL REFERENCES exams(exam_id),
                  attempt_id TEXT NOT NULL, question_id TEXT NOT NULL,
                  response_text TEXT NOT NULL,
                  PRIMARY KEY(exam_id,attempt_id,question_id));

                CREATE TABLE IF NOT EXISTS doc_defense_sessions (
                  defense_session_id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL,
                  document_id TEXT NOT NULL,
                  document_version TEXT NOT NULL,
                  document_sha256 TEXT NOT NULL,
                  session_revision INTEGER NOT NULL CHECK(session_revision>=1),
                  session_status TEXT NOT NULL CHECK(session_status IN ('ACTIVE','PAUSED','COMPLETED','STOPPED_BY_USER')),
                  current_batch_index INTEGER NOT NULL DEFAULT 1,
                  active_batch_exam_id TEXT,
                  active_question_id TEXT,
                  pending_followup_id TEXT);

                CREATE TABLE IF NOT EXISTS doc_defense_scope_items (
                  item_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                  defense_session_id TEXT NOT NULL REFERENCES doc_defense_sessions(defense_session_id),
                  section_id TEXT NOT NULL,
                  section_ordinal INTEGER NOT NULL,
                  heading_path TEXT NOT NULL,
                  section_sha256 TEXT NOT NULL,
                  dimension TEXT NOT NULL,
                  status TEXT NOT NULL CHECK(status IN ('INSPECTED','OPEN','ADDRESSED_WITH_TEACHING','OUT_OF_SCOPE')),
                  status_reason TEXT NOT NULL DEFAULT 'AWAITING_BATCH_OR_QUESTION',
                  explanation_mode TEXT NOT NULL DEFAULT 'NONE' CHECK(explanation_mode IN ('NONE','UNASSISTED','ASSISTED')),
                  assistance_sources TEXT NOT NULL DEFAULT '[]',
                  UNIQUE(defense_session_id, section_id, dimension));

                CREATE TABLE IF NOT EXISTS doc_defense_batches (
                  batch_exam_id TEXT PRIMARY KEY,
                  defense_session_id TEXT NOT NULL REFERENCES doc_defense_sessions(defense_session_id),
                  project_id TEXT NOT NULL,
                  document_id TEXT NOT NULL,
                  document_version TEXT NOT NULL,
                  document_sha256 TEXT NOT NULL,
                  created_as_of TEXT NOT NULL,
                  batch_index INTEGER NOT NULL DEFAULT 1,
                  assistance_level TEXT NOT NULL,
                  package TEXT NOT NULL,
                  questions TEXT NOT NULL);

                CREATE TABLE IF NOT EXISTS doc_defense_questions (
                  q_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                  defense_session_id TEXT NOT NULL REFERENCES doc_defense_sessions(defense_session_id),
                  batch_exam_id TEXT NOT NULL REFERENCES doc_defense_batches(batch_exam_id),
                  question_id TEXT NOT NULL,
                  parent_question_id TEXT,
                  document_version TEXT NOT NULL,
                  document_sha256 TEXT NOT NULL,
                  section_id TEXT NOT NULL,
                  passage_id TEXT NOT NULL,
                  target_dimension TEXT NOT NULL,
                  claim_epistemic_status TEXT NOT NULL,
                  question_payload TEXT NOT NULL,
                  immutable_criteria TEXT NOT NULL,
                  delivered_to_learner INTEGER NOT NULL DEFAULT 0,
                  voided INTEGER NOT NULL DEFAULT 0,
                  void_reason TEXT,
                  defense_record_closed INTEGER NOT NULL DEFAULT 0,
                  UNIQUE(defense_session_id, question_id));

                CREATE TABLE IF NOT EXISTS doc_defense_responses (
                  response_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                  defense_session_id TEXT NOT NULL REFERENCES doc_defense_sessions(defense_session_id),
                  batch_exam_id TEXT NOT NULL REFERENCES doc_defense_batches(batch_exam_id),
                  response_id TEXT NOT NULL,
                  turn_id TEXT NOT NULL,
                  question_id TEXT NOT NULL,
                  parent_question_id TEXT,
                  document_version TEXT NOT NULL,
                  document_sha256 TEXT NOT NULL,
                  section_id TEXT NOT NULL,
                  passage_id TEXT NOT NULL,
                  target_dimension TEXT NOT NULL,
                  response_text TEXT NOT NULL,
                  is_idk_declaration INTEGER NOT NULL DEFAULT 0,
                  declared_design_change INTEGER NOT NULL DEFAULT 0,
                  was_assisted_at_submission INTEGER NOT NULL DEFAULT 0,
                  evaluation_verdict TEXT,
                  UNIQUE(defense_session_id, question_id),
                  UNIQUE(defense_session_id, response_id));

                CREATE TABLE IF NOT EXISTS doc_defense_events (
                  event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                  defense_session_id TEXT NOT NULL REFERENCES doc_defense_sessions(defense_session_id),
                  batch_exam_id TEXT,
                  turn_id TEXT NOT NULL,
                  question_id TEXT NOT NULL DEFAULT '',
                  section_id TEXT NOT NULL DEFAULT '',
                  dimension TEXT NOT NULL DEFAULT '',
                  document_version TEXT NOT NULL,
                  document_sha256 TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  detail_id TEXT NOT NULL DEFAULT '',
                  payload TEXT NOT NULL DEFAULT '{}');
            """)

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(self.database_path, timeout=15, isolation_level="DEFERRED")
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA synchronous=FULL")
        try:
            with con:
                yield con
        finally:
            con.close()

    # -------------------------------------------------------------------------
    # Code Defense Storage (v1.2 — untouched)
    # -------------------------------------------------------------------------

    def initialize_ledger(self, ledger_id: str) -> dict:
        """Explicit privileged operation; no supplied history/flags accepted."""
        if not isinstance(ledger_id, str) or not re.fullmatch(r"LEDGER-[A-Za-z0-9._-]+", ledger_id):
            raise StoreError("INVALID_LEDGER_ID")
        with self._connect() as con:
            con.execute("INSERT OR IGNORE INTO ledgers VALUES (?,1)", (ledger_id,))
            return self._ledger(con, ledger_id)

    def get_ledger(self, ledger_id: str) -> dict | None:
        with self._connect() as con:
            return self._ledger(con, ledger_id)

    def _ledger(self, con, ledger_id):
        row = con.execute("SELECT revision FROM ledgers WHERE ledger_id=?", (ledger_id,)).fetchone()
        if row is None:
            return None
        records, questions, hints = {}, set(), set()
        rubric = False
        for event in con.execute("SELECT * FROM events WHERE ledger_id=? ORDER BY event_seq", (ledger_id,)):
            key = tuple(event[k] for k in ("attempt_id", "question_id", "artifact_id", "snapshot_id"))
            rec = records.setdefault(key, dict(zip(("attempt_id", "question_id", "artifact_id", "snapshot_id"), key),
                                             disclosed_event_types=[], disclosed_hint_ids=[]))
            if event["event_type"] not in rec["disclosed_event_types"]:
                rec["disclosed_event_types"].append(event["event_type"])
            if event["event_type"] == "QUESTION_SHOWN":
                questions.add(event["question_id"])
            if event["hint_id"]:
                hints.add(event["hint_id"])
                if event["hint_id"] not in rec["disclosed_hint_ids"]:
                    rec["disclosed_hint_ids"].append(event["hint_id"])
            rubric |= event["event_type"] in {"RUBRIC_SHOWN", "DIAGNOSIS_SHOWN"}
        return {"ledger_source_id": ledger_id, "ledger_revision": row["revision"],
                "assistance_log_present": True, "rubric_or_diagnosis_disclosed": rubric,
                "attempt_disclosure_records": list(records.values()),
                "disclosed_question_ids": sorted(questions), "disclosed_hint_ids": sorted(hints),
                "prior_assistance_summary": None}

    def save_exam(self, package: dict, *, question_pack: list | None = None,
                  assistance_level: str | None = None) -> None:
        """Register post-validated orchestrator output, never a claimed prior package.

        A new package must be wholly undelivered. Existing canonical packages are
        immutable here; only committed QUESTION_SHOWN events change their flags.
        """
        required = {"exam_id", "created_as_of", "objective_id", "registered_questions", "exam_package_sha256"}
        if not isinstance(package, dict) or set(package) != required or package_digest(package) != package["exam_package_sha256"]:
            raise StoreError("INVALID_EXAM_PACKAGE_HASH")
        if assistance_level not in {None, "QUESTION_ONLY", "QUESTION_AND_CONCEPTUAL_HINT", "SILENT_OBSERVATION_ONLY"}:
            raise StoreError("INVALID_ASSISTANCE_LEVEL")
        questions = copy.deepcopy(question_pack or [])
        registered = package["registered_questions"]
        if not isinstance(registered, list) or not registered or len({q["question_id"] for q in registered}) != len(registered):
            raise StoreError("INVALID_QUESTION_PACK")
        if questions:
            if len(questions) != len(registered):
                raise StoreError("INVALID_QUESTION_PACK")
            for q, reg in zip(questions, registered):
                source = q.get("source_ref", {})
                if (q.get("question_id") != reg["question_id"] or q.get("question_type") != reg["question_type"]
                    or q.get("objective_id") != package["objective_id"]
                    or q.get("expected_explanation_criteria") != reg["immutable_criteria"]
                    or any(source.get(k) != reg[k] for k in ("artifact_id", "snapshot_id", "start_line", "end_line"))):
                    raise StoreError("INVALID_QUESTION_PACK")
        encoded = (_dump(package), _dump(questions), assistance_level)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute("SELECT package,questions,assistance_level FROM exams WHERE exam_id=?", (package["exam_id"],)).fetchone()
            if existing:
                if tuple(existing) != encoded:
                    raise StoreError("CANONICAL_EXAM_MUTATION")
                return
            if any(q.get("delivered_to_learner") is not False for q in registered):
                raise StoreError("UNTRUSTED_DELIVERY_FLAG")
            con.execute("INSERT INTO exams VALUES (?,?,?,?)", (package["exam_id"], *encoded))

    def get_exam(self, exam_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute("SELECT package FROM exams WHERE exam_id=?", (exam_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def get_exam_questions(self, exam_id: str) -> list:
        with self._connect() as con:
            row = con.execute("SELECT questions FROM exams WHERE exam_id=?", (exam_id,)).fetchone()
            return json.loads(row[0]) if row else []

    def get_exam_assistance(self, exam_id: str) -> str | None:
        with self._connect() as con:
            row = con.execute("SELECT assistance_level FROM exams WHERE exam_id=?", (exam_id,)).fetchone()
            return row[0] if row else None

    def record_event(self, ledger_id: str, *, exam_id: str, attempt_id: str, question_id: str,
                     artifact_id: str, snapshot_id: str, event_type: str, hint_id: str | None = None,
                     expected_revision: int, require_new: bool = False) -> dict:
        """Atomic append. Exact retry is idempotent; stale distinct events conflict."""
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            return self._record_event(con, ledger_id, exam_id=exam_id, attempt_id=attempt_id,
                                      question_id=question_id, artifact_id=artifact_id, snapshot_id=snapshot_id,
                                      event_type=event_type, hint_id=hint_id, expected_revision=expected_revision,
                                      require_new=require_new)

    def _record_event(self, con, ledger_id, *, exam_id, attempt_id, question_id, artifact_id,
                      snapshot_id, event_type, hint_id, expected_revision, require_new=False):
        if event_type not in EVENTS or not re.fullmatch(r"ATT-[0-9]{8}-[0-9]{2}", attempt_id):
            raise StoreError("INVALID_DISCLOSURE_EVENT")
        ledger = self._ledger(con, ledger_id)
        if ledger is None:
            raise StoreError("LEDGER_NOT_INITIALIZED")
        row = con.execute("SELECT package,questions,assistance_level FROM exams WHERE exam_id=?", (exam_id,)).fetchone()
        if row is None:
            raise StoreError("UNREGISTERED_EXAM")
        package, pack = json.loads(row["package"]), json.loads(row["questions"])
        matches = [q for q in package["registered_questions"] if q["question_id"] == question_id
                   and q["artifact_id"] == artifact_id and q["snapshot_id"] == snapshot_id]
        if len(matches) != 1:
            raise StoreError("UNREGISTERED_QUESTION_OR_CRITERION_REF")
        q = matches[0]
        args = (ledger_id, exam_id, attempt_id, question_id, event_type, hint_id or "")
        duplicate = con.execute("SELECT 1 FROM events WHERE ledger_id=? AND exam_id=? AND attempt_id=? AND question_id=? AND event_type=? AND hint_id=?", args).fetchone()
        if duplicate:
            if require_new:
                raise StoreError("ALREADY_DELIVERED")
            return ledger
        if type(expected_revision) is not int or ledger["ledger_revision"] != expected_revision:
            raise StoreError("LEDGER_REVISION_CONFLICT")
        question_events = list(con.execute("SELECT event_type,hint_id FROM events WHERE exam_id=? AND attempt_id=? AND question_id=?", (exam_id, attempt_id, question_id)))
        if event_type.startswith("HINT_"):
            if row["assistance_level"] != "QUESTION_AND_CONCEPTUAL_HINT":
                raise StoreError("HINT_NOT_ALLOWED")
            full_q = next((x for x in pack if x["question_id"] == question_id), {})
            order = 1 if event_type == "HINT_1_SHOWN" else 2
            if not any(h["hint_id"] == hint_id and h["hint_order"] == order for h in full_q.get("on_demand_hints", [])):
                raise StoreError("UNREGISTERED_HINT")
            if not any(e["event_type"] == "QUESTION_SHOWN" for e in question_events):
                raise StoreError("QUESTION_NOT_DELIVERED")
            if order == 2 and not any(e["event_type"] == "HINT_1_SHOWN" for e in question_events):
                raise StoreError("HINT_ORDER_VIOLATION")
        elif hint_id is not None:
            raise StoreError("INVALID_DISCLOSURE_EVENT")
        if event_type in {"QUESTION_SHOWN", "HINT_1_SHOWN", "HINT_2_SHOWN"}:
            # A fresh ledger cannot replay delivery and hide a previous event.
            if any(e["event_type"] == event_type for e in question_events):
                raise StoreError("ALREADY_DELIVERED")
            for prior in con.execute("SELECT e.ledger_id,e.artifact_id,e.snapshot_id,x.package FROM events e JOIN exams x USING(exam_id) WHERE e.ledger_id<>?", (ledger_id,)):
                prior_package = json.loads(prior["package"])
                if (prior_package["objective_id"] == package["objective_id"]
                    or prior["artifact_id"] == artifact_id or prior["snapshot_id"] == snapshot_id):
                    raise StoreError("RELATED_DISCLOSURE_LEDGER_MISMATCH")
        if event_type == "QUESTION_SHOWN":
            if row["assistance_level"] == "SILENT_OBSERVATION_ONLY":
                raise StoreError("DELIVERY_NOT_ALLOWED")
            index = package["registered_questions"].index(q)
            if index and not self._has_response(con, exam_id, attempt_id, package["registered_questions"][index-1]["question_id"]):
                raise StoreError("PRIOR_RESPONSE_REQUIRED")
            q["delivered_to_learner"] = True
            package["exam_package_sha256"] = package_digest(package)
            con.execute("UPDATE exams SET package=? WHERE exam_id=?", (_dump(package), exam_id))
        con.execute("INSERT INTO events(ledger_id,exam_id,attempt_id,question_id,artifact_id,snapshot_id,event_type,hint_id) VALUES(?,?,?,?,?,?,?,?)",
                    (ledger_id, exam_id, attempt_id, question_id, artifact_id, snapshot_id, event_type, hint_id or ""))
        con.execute("UPDATE ledgers SET revision=revision+1 WHERE ledger_id=?", (ledger_id,))
        result = self._ledger(con, ledger_id)
        if (len(result["attempt_disclosure_records"]) > 20 or len(result["disclosed_question_ids"]) > 20
            or len(result["disclosed_hint_ids"]) > 20):
            raise StoreError("LEDGER_CAPACITY_EXCEEDED")
        return result

    def has_event(self, exam_id, attempt_id, question_id, event_type, hint_id=None) -> bool:
        with self._connect() as con:
            return bool(con.execute("SELECT 1 FROM events WHERE exam_id=? AND attempt_id=? AND question_id=? AND event_type=? AND hint_id=?",
                                    (exam_id, attempt_id, question_id, event_type, hint_id or "")).fetchone())

    def record_response(self, exam_id: str, attempt_id: str, question_id: str, response_text: str) -> None:
        if not isinstance(response_text, str) or not response_text.strip():
            raise StoreError("EMPTY_OR_UNUSABLE_RESPONSE")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if not con.execute("SELECT 1 FROM events WHERE exam_id=? AND attempt_id=? AND question_id=? AND event_type='QUESTION_SHOWN'", (exam_id, attempt_id, question_id)).fetchone():
                raise StoreError("QUESTION_NOT_DELIVERED")
            row = con.execute("SELECT response_text FROM responses WHERE exam_id=? AND attempt_id=? AND question_id=?", (exam_id, attempt_id, question_id)).fetchone()
            if row:
                if row[0] != response_text:
                    raise StoreError("RESPONSE_MUTATION")
                return
            con.execute("INSERT INTO responses VALUES (?,?,?,?)", (exam_id, attempt_id, question_id, response_text))

    @staticmethod
    def _has_response(con, exam_id, attempt_id, question_id):
        return bool(con.execute("SELECT 1 FROM responses WHERE exam_id=? AND attempt_id=? AND question_id=?", (exam_id, attempt_id, question_id)).fetchone())

    def has_response(self, exam_id: str, attempt_id: str, question_id: str) -> bool:
        with self._connect() as con:
            return self._has_response(con, exam_id, attempt_id, question_id)

    def get_disclosed_context(self, ledger_id: str | None = None) -> list[dict]:
        """Canonical previously exposed text, including hints from other questions."""
        with self._connect() as con:
            result = []
            query = "SELECT e.*,x.questions FROM events e JOIN exams x USING(exam_id)"
            if ledger_id is not None:
                query += " WHERE ledger_id=?"
            for e in con.execute(query + " ORDER BY event_seq", (ledger_id,) if ledger_id is not None else ()):
                q = next((q for q in json.loads(e["questions"]) if q["question_id"] == e["question_id"]), None)
                if q is None:
                    continue
                text = q["neutral_question_prompt"] if e["event_type"] == "QUESTION_SHOWN" else None
                if e["hint_id"]:
                    text = next((h["conceptual_nudge"] for h in q["on_demand_hints"] if h["hint_id"] == e["hint_id"]), None)
                if text is not None:
                    result.append({"exam_id": e["exam_id"], "question_id": e["question_id"], "event_type": e["event_type"], "text": text})
            return result

    def get_related_disclosures(self, *, objective_id: str, artifact_ids: list[str], snapshot_ids: list[str]) -> list[dict]:
        """Detect sticky disclosure history even if a caller selects a new ledger."""
        with self._connect() as con:
            result = []
            for e in con.execute("SELECT e.*,x.package FROM events e JOIN exams x USING(exam_id) ORDER BY event_seq"):
                package = json.loads(e["package"])
                if package["objective_id"] == objective_id or e["artifact_id"] in artifact_ids or e["snapshot_id"] in snapshot_ids:
                    result.append({k: e[k] for k in ("ledger_id", "exam_id", "attempt_id", "question_id", "artifact_id", "snapshot_id", "event_type", "hint_id")})
            return result

    # -------------------------------------------------------------------------
    # Document Defense Storage (v1.3 — separate tables, no 20-record truncation)
    # -------------------------------------------------------------------------

    def initialize_doc_session(self, defense_session_id: str, *, project_id: str,
                               document_id: str, document_version: str,
                               document_sha256: str,
                               section_inventory: list[dict] | None = None) -> dict:
        if not isinstance(defense_session_id, str) or not re.fullmatch(r"DDS-[A-Za-z0-9._-]{3,64}", defense_session_id):
            raise StoreError("INVALID_DOC_SESSION_ID")
        if not isinstance(project_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", project_id):
            raise StoreError("INVALID_PROJECT_ID")
        if not isinstance(document_id, str) or not re.fullmatch(r"DOC-[A-Za-z0-9._-]{2,64}", document_id):
            raise StoreError("INVALID_DOCUMENT_ID")
        if not isinstance(document_sha256, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", document_sha256):
            raise StoreError("INVALID_DOCUMENT_HASH")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT 1 FROM exams WHERE exam_id=?", (defense_session_id,)).fetchone() or con.execute("SELECT 1 FROM ledgers WHERE ledger_id=?", (defense_session_id,)).fetchone():
                raise StoreError("SESSION_MODE_COLLISION_WITH_CODE_DEFENSE")
            existing = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if existing is None:
                con.execute("""
                    INSERT INTO doc_defense_sessions(
                      defense_session_id, project_id, document_id, document_version,
                      document_sha256, session_revision, session_status, current_batch_index
                    ) VALUES (?,?,?,?,?,1,'ACTIVE',1)
                """, (defense_session_id, project_id, document_id, document_version, document_sha256))
            elif existing["project_id"] != project_id or existing["document_id"] != document_id:
                raise StoreError("DOC_SESSION_IDENTITY_CONFLICT")
            if section_inventory:
                self._sync_scope_inventory(con, defense_session_id, section_inventory)
            return self._doc_session_state(con, defense_session_id)

    def _sync_scope_inventory(self, con, defense_session_id: str, section_inventory: list[dict]) -> None:
        for sec in section_inventory:
            sec_id = sec["section_id"]
            ordinal = sec["ordinal"]
            heading = sec["heading_path"]
            sec_sha = sec["section_sha256"]
            for dim in sec["relevant_dimensions"]:
                init_status = "OPEN"
                reason = "UNREADABLE_VISUAL_WAITING" if sec.get("has_unreadable_visuals") and dim == "METHOD" else "AWAITING_BATCH_OR_QUESTION"
                existing_item = con.execute(
                    "SELECT section_sha256 FROM doc_defense_scope_items WHERE defense_session_id=? AND section_id=? AND dimension=?",
                    (defense_session_id, sec_id, dim)).fetchone()
                if existing_item is None:
                    con.execute("""
                        INSERT INTO doc_defense_scope_items(
                          defense_session_id, section_id, section_ordinal, heading_path,
                          section_sha256, dimension, status, status_reason, explanation_mode, assistance_sources
                        ) VALUES (?,?,?,?,?,?,?,?, 'NONE', '[]')
                    """, (defense_session_id, sec_id, ordinal, heading, sec_sha, dim, init_status, reason))
                elif existing_item["section_sha256"] != sec_sha:
                    con.execute("""
                        UPDATE doc_defense_scope_items
                        SET section_ordinal=?, heading_path=?, section_sha256=?,
                            status=?, status_reason=?, explanation_mode='NONE'
                        WHERE defense_session_id=? AND section_id=? AND dimension=?
                    """, (ordinal, heading, sec_sha, init_status, reason, defense_session_id, sec_id, dim))

    def get_doc_session_state(self, defense_session_id: str) -> dict | None:
        with self._connect() as con:
            return self._doc_session_state(con, defense_session_id)

    def _doc_session_state(self, con, defense_session_id: str) -> dict | None:
        row = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
        if row is None:
            return None
        delivered = [r["question_id"] for r in con.execute(
            "SELECT question_id FROM doc_defense_questions WHERE defense_session_id=? AND delivered_to_learner=1 ORDER BY q_seq",
            (defense_session_id,))]
        voided = [r["question_id"] for r in con.execute(
            "SELECT question_id FROM doc_defense_questions WHERE defense_session_id=? AND voided=1 ORDER BY q_seq",
            (defense_session_id,))]
        hints = []
        taught = []
        for ev in con.execute("SELECT * FROM doc_defense_events WHERE defense_session_id=? ORDER BY event_seq", (defense_session_id,)):
            if ev["event_type"] in {"DOC_HINT_1_SHOWN", "DOC_HINT_2_SHOWN"} and ev["detail_id"] and ev["detail_id"] not in hints:
                hints.append(ev["detail_id"])
            if ev["event_type"] == "TEACHING_EXPLANATION_SHOWN":
                taught.append({
                    "section_id": ev["section_id"],
                    "dimension": ev["dimension"],
                    "teaching_event_id": ev["detail_id"],
                    "closed_question_id": ev["question_id"],
                })
        unassisted = []
        assisted = []
        for item in con.execute("SELECT * FROM doc_defense_scope_items WHERE defense_session_id=? ORDER BY item_seq", (defense_session_id,)):
            pair = {"section_id": item["section_id"], "dimension": item["dimension"]}
            if item["status"] == "INSPECTED" and item["explanation_mode"] == "UNASSISTED":
                unassisted.append(pair)
            elif item["status"] == "INSPECTED" and item["explanation_mode"] == "ASSISTED":
                assisted.append(pair)
        return {
            "defense_session_id": defense_session_id,
            "project_id": row["project_id"],
            "session_revision": row["session_revision"],
            "session_status": row["session_status"],
            "current_document_version": row["document_version"],
            "current_document_sha256": row["document_sha256"],
            "delivered_question_ids": delivered,
            "voided_question_ids": voided,
            "disclosed_hint_ids": hints,
            "taught_dimensions": taught,
            "unassisted_explained_dimensions": unassisted,
            "assisted_explained_dimensions": assisted,
        }

    def get_doc_resume_manifest(self, defense_session_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if row is None:
                return None
            state = self._doc_session_state(con, defense_session_id)
            scope_items = []
            for item in con.execute("SELECT * FROM doc_defense_scope_items WHERE defense_session_id=? ORDER BY item_seq", (defense_session_id,)):
                scope_items.append({
                    "section_id": item["section_id"],
                    "section_ordinal": item["section_ordinal"],
                    "heading_path": item["heading_path"],
                    "section_sha256": item["section_sha256"],
                    "dimension": item["dimension"],
                    "status": item["status"],
                    "status_reason": item["status_reason"],
                    "explanation_mode": item["explanation_mode"],
                    "assistance_sources": json.loads(item["assistance_sources"]),
                })
            event_count = con.execute("SELECT COUNT(*) FROM doc_defense_events WHERE defense_session_id=?", (defense_session_id,)).fetchone()[0]
            response_count = con.execute("SELECT COUNT(*) FROM doc_defense_responses WHERE defense_session_id=?", (defense_session_id,)).fetchone()[0]
            return {
                "defense_session_id": defense_session_id,
                "project_id": row["project_id"],
                "document_id": row["document_id"],
                "session_status": row["session_status"],
                "current_batch_index": row["current_batch_index"],
                "active_batch_exam_id": row["active_batch_exam_id"],
                "active_question_id": row["active_question_id"],
                "pending_followup_id": row["pending_followup_id"],
                "total_events_recorded": event_count,
                "total_responses_recorded": response_count,
                "session_state_snapshot": state,
                "scope_items": scope_items,
            }

    def pause_doc_session(self, defense_session_id: str, *, turn_id: str = "DTURN-20261017-90") -> dict:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if row is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            con.execute("UPDATE doc_defense_sessions SET session_status='PAUSED', session_revision=session_revision+1 WHERE defense_session_id=?", (defense_session_id,))
            con.execute("""
                INSERT INTO doc_defense_events(defense_session_id, batch_exam_id, turn_id, document_version, document_sha256, event_type)
                VALUES (?,?,?,?,?,'SESSION_PAUSED')
            """, (defense_session_id, row["active_batch_exam_id"], turn_id, row["document_version"], row["document_sha256"]))
            return self._doc_session_state(con, defense_session_id)

    def resume_doc_session(self, defense_session_id: str, *, turn_id: str = "DTURN-20261017-91") -> dict:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if row is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            con.execute("UPDATE doc_defense_sessions SET session_status='ACTIVE', session_revision=session_revision+1 WHERE defense_session_id=?", (defense_session_id,))
            con.execute("""
                INSERT INTO doc_defense_events(defense_session_id, batch_exam_id, turn_id, document_version, document_sha256, event_type)
                VALUES (?,?,?,?,?,'SESSION_RESUMED')
            """, (defense_session_id, row["active_batch_exam_id"], turn_id, row["document_version"], row["document_sha256"]))
        return self.get_doc_resume_manifest(defense_session_id)

    def stop_doc_session(self, defense_session_id: str, *, turn_id: str = "DTURN-20261017-92") -> dict:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if row is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            con.execute("UPDATE doc_defense_sessions SET session_status='STOPPED_BY_USER', session_revision=session_revision+1 WHERE defense_session_id=?", (defense_session_id,))
            con.execute("""
                INSERT INTO doc_defense_events(defense_session_id, batch_exam_id, turn_id, document_version, document_sha256, event_type)
                VALUES (?,?,?,?,?,'SESSION_STOPPED_BY_USER')
            """, (defense_session_id, row["active_batch_exam_id"], turn_id, row["document_version"], row["document_sha256"]))
            return self._doc_session_state(con, defense_session_id)

    def record_prior_help_for_dimension(self, defense_session_id: str, *, section_id: str,
                                        dimension: str, source: str = "PRIOR_RECORDED_HELP",
                                        turn_id: str = "DTURN-20261017-00") -> dict:
        if source not in {"HINT_USED", "TEACHING_DELIVERED", "PRIOR_RECORDED_HELP"}:
            raise StoreError("INVALID_ASSISTANCE_SOURCE")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if row is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            item = con.execute(
                "SELECT * FROM doc_defense_scope_items WHERE defense_session_id=? AND section_id=? AND dimension=?",
                (defense_session_id, section_id, dimension)).fetchone()
            if item is None:
                raise StoreError("UNKNOWN_SCOPE_DIMENSION")
            sources = json.loads(item["assistance_sources"])
            if source not in sources:
                sources.append(source)
            con.execute("""
                UPDATE doc_defense_scope_items
                SET assistance_sources=?
                WHERE defense_session_id=? AND section_id=? AND dimension=?
            """, (_dump(sources), defense_session_id, section_id, dimension))
            con.execute("""
                INSERT INTO doc_defense_events(defense_session_id, turn_id, section_id, dimension, document_version, document_sha256, event_type, detail_id)
                VALUES (?,?,?,?,?,?,'PRIOR_HELP_RECORDED',?)
            """, (defense_session_id, turn_id, section_id, dimension, row["document_version"], row["document_sha256"], source))
            con.execute("UPDATE doc_defense_sessions SET session_revision=session_revision+1 WHERE defense_session_id=?", (defense_session_id,))
            return self._doc_session_state(con, defense_session_id)

    def update_doc_version(self, defense_session_id: str, *, new_version: str,
                           new_sha256: str, updated_sections: list[dict] | None = None,
                           turn_id: str = "DTURN-20261017-95") -> dict:
        """Advance document version without mutating any historical batch, question, response, or event."""
        if not isinstance(new_version, str) or not new_version.strip():
            raise StoreError("INVALID_DOCUMENT_VERSION")
        if not isinstance(new_sha256, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", new_sha256):
            raise StoreError("INVALID_DOCUMENT_HASH")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if row is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            old_version = row["document_version"]
            old_sha = row["document_sha256"]
            con.execute("""
                UPDATE doc_defense_sessions
                SET document_version=?, document_sha256=?, pending_followup_id=NULL, session_revision=session_revision+1
                WHERE defense_session_id=?
            """, (new_version, new_sha256, defense_session_id))
            archived_sections = []
            for sec in (updated_sections or []):
                prior_items = [
                    {
                        "dimension": r["dimension"],
                        "prior_section_sha256": r["section_sha256"],
                        "prior_status": r["status"],
                        "prior_status_reason": r["status_reason"],
                        "prior_explanation_mode": r["explanation_mode"],
                        "assistance_sources": json.loads(r["assistance_sources"]),
                    }
                    for r in con.execute(
                        "SELECT * FROM doc_defense_scope_items WHERE defense_session_id=? AND section_id=? ORDER BY item_seq",
                        (defense_session_id, sec["section_id"]))
                ]
                archived_sections.append({
                    "section_id": sec["section_id"],
                    "new_section_sha256": sec["section_sha256"],
                    "prior_items": prior_items,
                })
                con.execute("""
                    UPDATE doc_defense_scope_items
                    SET section_sha256=?, status='OPEN', status_reason='AWAITING_BATCH_OR_QUESTION', explanation_mode='NONE'
                    WHERE defense_session_id=? AND section_id=?
                """, (sec["section_sha256"], defense_session_id, sec["section_id"]))
            con.execute("""
                INSERT INTO doc_defense_events(
                  defense_session_id, batch_exam_id, turn_id, document_version, document_sha256,
                  event_type, detail_id, payload
                ) VALUES (?,?,?,?,?,'DOCUMENT_VERSION_UPDATED',?,?)
            """, (defense_session_id, row["active_batch_exam_id"], turn_id, new_version, new_sha256,
                  f"{old_version}->{new_version}",
                  _dump({
                      "prior_version": old_version,
                      "prior_sha256": old_sha,
                      "new_version": new_version,
                      "new_sha256": new_sha256,
                      "archived_updated_sections": archived_sections,
                  })))
            return self._doc_session_state(con, defense_session_id)

    def save_doc_batch(self, package: dict, *, question_pack: list, assistance_level: str,
                       batch_index: int = 1, section_inventory: list[dict] | None = None) -> None:
        required = {"batch_exam_id", "defense_session_id", "project_id", "document_id",
                    "document_version", "document_sha256", "created_as_of",
                    "registered_questions", "batch_package_sha256"}
        if not isinstance(package, dict) or set(package) != required or doc_package_digest(package) != package["batch_package_sha256"]:
            raise StoreError("INVALID_DOC_BATCH_PACKAGE_HASH")
        if assistance_level not in {"QUESTION_ONLY", "QUESTION_AND_CONCEPTUAL_HINT", "SILENT_OBSERVATION_ONLY"}:
            raise StoreError("INVALID_ASSISTANCE_LEVEL")
        registered = package["registered_questions"]
        questions = copy.deepcopy(question_pack or [])
        if not registered or len(questions) != len(registered):
            raise StoreError("INVALID_QUESTION_PACK")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            sess = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (package["defense_session_id"],)).fetchone()
            if sess is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            if sess["project_id"] != package["project_id"] or sess["document_id"] != package["document_id"]:
                raise StoreError("DOC_SESSION_IDENTITY_CONFLICT")
            if sess["document_version"] != package["document_version"] or sess["document_sha256"] != package["document_sha256"]:
                raise StoreError("DOC_VERSION_MISMATCH")
            if section_inventory:
                self._sync_scope_inventory(con, package["defense_session_id"], section_inventory)
            existing = con.execute("SELECT package, questions, assistance_level FROM doc_defense_batches WHERE batch_exam_id=?", (package["batch_exam_id"],)).fetchone()
            encoded = (_dump(package), _dump(questions), assistance_level)
            if existing:
                if tuple(existing) != encoded:
                    raise StoreError("CANONICAL_EXAM_MUTATION")
                return
            if any(q.get("delivered_to_learner") is not False or q.get("voided") is not False or q.get("defense_record_closed") is not False for q in registered):
                raise StoreError("UNTRUSTED_DELIVERY_FLAG")
            con.execute("""
                INSERT INTO doc_defense_batches(
                  batch_exam_id, defense_session_id, project_id, document_id,
                  document_version, document_sha256, created_as_of, batch_index,
                  assistance_level, package, questions
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (package["batch_exam_id"], package["defense_session_id"], package["project_id"],
                  package["document_id"], package["document_version"], package["document_sha256"],
                  package["created_as_of"], batch_index, assistance_level, _dump(package), _dump(questions)))
            for q, reg in zip(questions, registered):
                if q["question_id"] != reg["question_id"] or q["expected_explanation_criteria"] != reg["immutable_criteria"]:
                    raise StoreError("INVALID_QUESTION_PACK")
                existing_q = con.execute(
                    "SELECT 1 FROM doc_defense_questions WHERE defense_session_id=? AND question_id=?",
                    (package["defense_session_id"], q["question_id"])).fetchone()
                if existing_q:
                    raise StoreError("DUPLICATE_QUESTION_ID_IN_SESSION")
                con.execute("""
                    INSERT INTO doc_defense_questions(
                      defense_session_id, batch_exam_id, question_id, parent_question_id,
                      document_version, document_sha256, section_id, passage_id,
                      target_dimension, claim_epistemic_status, question_payload,
                      immutable_criteria, delivered_to_learner, voided, defense_record_closed
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,0,0)
                """, (package["defense_session_id"], package["batch_exam_id"], q["question_id"],
                      reg["parent_question_id"], package["document_version"], package["document_sha256"],
                      q["section_id"], q["passage_id"], q["target_dimension"], q["claim_epistemic_status"],
                      _dump(q), _dump(reg["immutable_criteria"])))
            con.execute("""
                UPDATE doc_defense_sessions
                SET current_batch_index=?, active_batch_exam_id=?
                WHERE defense_session_id=?
            """, (batch_index, package["batch_exam_id"], package["defense_session_id"]))

    def get_doc_batch(self, batch_exam_id: str) -> dict | None:
        with self._connect() as con:
            return self._get_doc_batch(con, batch_exam_id)

    def _get_doc_batch(self, con, batch_exam_id: str) -> dict | None:
        row = con.execute("SELECT * FROM doc_defense_batches WHERE batch_exam_id=?", (batch_exam_id,)).fetchone()
        if row is None:
            return None
        package = json.loads(row["package"])
        q_rows = list(con.execute(
            "SELECT * FROM doc_defense_questions WHERE batch_exam_id=? ORDER BY q_seq",
            (batch_exam_id,)))
        reg_list = []
        for qr in q_rows:
            reg_list.append({
                "question_id": qr["question_id"],
                "parent_question_id": qr["parent_question_id"],
                "section_id": qr["section_id"],
                "passage_id": qr["passage_id"],
                "target_dimension": qr["target_dimension"],
                "claim_epistemic_status": qr["claim_epistemic_status"],
                "delivered_to_learner": bool(qr["delivered_to_learner"]),
                "voided": bool(qr["voided"]),
                "defense_record_closed": bool(qr["defense_record_closed"]),
                "immutable_criteria": json.loads(qr["immutable_criteria"]),
            })
        package["registered_questions"] = reg_list
        package["batch_package_sha256"] = doc_package_digest(package)
        return package

    def get_doc_batch_questions(self, batch_exam_id: str) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("SELECT question_payload, voided, delivered_to_learner, defense_record_closed, parent_question_id FROM doc_defense_questions WHERE batch_exam_id=? ORDER BY q_seq", (batch_exam_id,)).fetchall()
            result = []
            for r in rows:
                q = json.loads(r["question_payload"])
                q["_voided"] = bool(r["voided"])
                q["_delivered"] = bool(r["delivered_to_learner"])
                q["_closed"] = bool(r["defense_record_closed"])
                q["_parent_question_id"] = r["parent_question_id"]
                result.append(q)
            return result

    def get_doc_batch_assistance(self, batch_exam_id: str) -> str | None:
        with self._connect() as con:
            row = con.execute("SELECT assistance_level FROM doc_defense_batches WHERE batch_exam_id=?", (batch_exam_id,)).fetchone()
            return row["assistance_level"] if row else None

    def record_doc_event(self, defense_session_id: str, *, batch_exam_id: str,
                         turn_id: str, question_id: str, event_type: str,
                         detail_id: str = "", payload: dict | None = None,
                         expected_revision: int) -> dict:
        if event_type not in DOC_EVENTS or not re.fullmatch(r"DTURN-[0-9]{8}-[0-9]{2,4}", turn_id):
            raise StoreError("INVALID_DISCLOSURE_EVENT")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            sess = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if sess is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            if sess["session_status"] != "ACTIVE":
                raise StoreError("DOC_SESSION_NOT_ACTIVE")
            if sess["session_revision"] != expected_revision:
                raise StoreError("SESSION_REVISION_CONFLICT")
            b_row = con.execute("SELECT * FROM doc_defense_batches WHERE batch_exam_id=? AND defense_session_id=?", (batch_exam_id, defense_session_id)).fetchone()
            if b_row is None:
                raise StoreError("UNREGISTERED_DOC_BATCH")
            q_row = con.execute("SELECT * FROM doc_defense_questions WHERE defense_session_id=? AND batch_exam_id=? AND question_id=?", (defense_session_id, batch_exam_id, question_id)).fetchone()
            if q_row is None:
                raise StoreError("UNREGISTERED_QUESTION_OR_CRITERION_REF")
            if (b_row["document_id"] != sess["document_id"]
                    or b_row["document_version"] != sess["document_version"]
                    or b_row["document_sha256"] != sess["document_sha256"]
                    or q_row["document_version"] != sess["document_version"]
                    or q_row["document_sha256"] != sess["document_sha256"]):
                raise StoreError("DOC_VERSION_MISMATCH")
            if q_row["voided"]:
                raise StoreError("QUESTION_IS_VOIDED")

            if event_type in {"DOC_QUESTION_SHOWN", "DOC_FOLLOWUP_SHOWN"}:
                if b_row["assistance_level"] == "SILENT_OBSERVATION_ONLY":
                    raise StoreError("DELIVERY_NOT_ALLOWED")
                if q_row["delivered_to_learner"]:
                    raise StoreError("ALREADY_DELIVERED")
                if event_type == "DOC_FOLLOWUP_SHOWN":
                    if not q_row["parent_question_id"]:
                        raise StoreError("NOT_A_FOLLOWUP_QUESTION")
                    if not self._has_doc_response(con, defense_session_id, q_row["parent_question_id"]):
                        raise StoreError("PRIOR_RESPONSE_REQUIRED")
                else:
                    if q_row["parent_question_id"]:
                        raise StoreError("FOLLOWUP_REQUIRES_FOLLOWUP_DELIVERY")
                    # Block advancing to another main question if an active pending follow-up in the current document version is unanswered/open/non-voided
                    if sess["pending_followup_id"]:
                        pf_row = con.execute(
                            "SELECT question_id, voided, defense_record_closed, document_version, document_sha256 FROM doc_defense_questions WHERE defense_session_id=? AND question_id=?",
                            (defense_session_id, sess["pending_followup_id"])).fetchone()
                        if (pf_row
                                and pf_row["document_version"] == sess["document_version"]
                                and pf_row["document_sha256"] == sess["document_sha256"]
                                and not pf_row["voided"]
                                and not pf_row["defense_record_closed"]
                                and not self._has_doc_response(con, defense_session_id, pf_row["question_id"])):
                            raise StoreError("PRIOR_RESPONSE_REQUIRED")
                    # Ensure all prior non-voided main questions in this batch have a response (or closed record)
                    prior_main = list(con.execute("""
                        SELECT question_id, voided, defense_record_closed
                        FROM doc_defense_questions
                        WHERE defense_session_id=? AND batch_exam_id=? AND parent_question_id IS NULL AND q_seq < ?
                        ORDER BY q_seq
                    """, (defense_session_id, batch_exam_id, q_row["q_seq"])))
                    for pm in prior_main:
                        if not pm["voided"] and not pm["defense_record_closed"] and not self._has_doc_response(con, defense_session_id, pm["question_id"]):
                            raise StoreError("PRIOR_RESPONSE_REQUIRED")
                    # Ensure any delivered follow-up question in this batch has a response (or is voided/closed)
                    open_followups = list(con.execute("""
                        SELECT question_id, voided, defense_record_closed
                        FROM doc_defense_questions
                        WHERE defense_session_id=? AND batch_exam_id=? AND parent_question_id IS NOT NULL AND delivered_to_learner=1
                        ORDER BY q_seq
                    """, (defense_session_id, batch_exam_id)))
                    for fq_r in open_followups:
                        if not fq_r["voided"] and not fq_r["defense_record_closed"] and not self._has_doc_response(con, defense_session_id, fq_r["question_id"]):
                            raise StoreError("PRIOR_RESPONSE_REQUIRED")
                con.execute("UPDATE doc_defense_questions SET delivered_to_learner=1 WHERE defense_session_id=? AND question_id=?", (defense_session_id, question_id))
                con.execute("UPDATE doc_defense_sessions SET active_question_id=?, pending_followup_id=? WHERE defense_session_id=?",
                            (question_id, question_id if event_type == "DOC_FOLLOWUP_SHOWN" else None, defense_session_id))
                pkg = self._get_doc_batch(con, batch_exam_id)
                con.execute("UPDATE doc_defense_batches SET package=? WHERE batch_exam_id=?", (_dump(pkg), batch_exam_id))

            elif event_type in {"DOC_HINT_1_SHOWN", "DOC_HINT_2_SHOWN"}:
                if b_row["assistance_level"] != "QUESTION_AND_CONCEPTUAL_HINT":
                    raise StoreError("HINT_NOT_ALLOWED")
                if not q_row["delivered_to_learner"]:
                    raise StoreError("QUESTION_NOT_DELIVERED")
                if q_row["defense_record_closed"]:
                    raise StoreError("DEFENSE_RECORD_ALREADY_CLOSED")
                q_payload = json.loads(q_row["question_payload"])
                order = 1 if event_type == "DOC_HINT_1_SHOWN" else 2
                if not any(h["hint_id"] == detail_id and h["hint_order"] == order for h in q_payload.get("on_demand_hints", [])):
                    raise StoreError("UNREGISTERED_HINT")
                prior_q_events = [e["event_type"] for e in con.execute(
                    "SELECT event_type FROM doc_defense_events WHERE defense_session_id=? AND question_id=?",
                    (defense_session_id, question_id))]
                if event_type in prior_q_events:
                    raise StoreError("ALREADY_DELIVERED")
                if order == 2 and "DOC_HINT_1_SHOWN" not in prior_q_events:
                    raise StoreError("HINT_ORDER_VIOLATION")
                self._add_scope_assistance_source(con, defense_session_id, q_row["section_id"], q_row["target_dimension"], "HINT_USED")

            con.execute("""
                INSERT INTO doc_defense_events(
                  defense_session_id, batch_exam_id, turn_id, question_id,
                  section_id, dimension, document_version, document_sha256,
                  event_type, detail_id, payload
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (defense_session_id, batch_exam_id, turn_id, question_id,
                  q_row["section_id"], q_row["target_dimension"],
                  q_row["document_version"], q_row["document_sha256"],
                  event_type, detail_id or "", _dump(payload or {})))
            con.execute("UPDATE doc_defense_sessions SET session_revision=session_revision+1 WHERE defense_session_id=?", (defense_session_id,))
            return self._doc_session_state(con, defense_session_id)

    @staticmethod
    def _add_scope_assistance_source(con, defense_session_id: str, section_id: str, dimension: str, source: str) -> None:
        item = con.execute(
            "SELECT assistance_sources FROM doc_defense_scope_items WHERE defense_session_id=? AND section_id=? AND dimension=?",
            (defense_session_id, section_id, dimension)).fetchone()
        if item is not None:
            sources = json.loads(item["assistance_sources"])
            if source not in sources:
                sources.append(source)
                con.execute("""
                    UPDATE doc_defense_scope_items
                    SET assistance_sources=?
                    WHERE defense_session_id=? AND section_id=? AND dimension=?
                """, (_dump(sources), defense_session_id, section_id, dimension))

    @staticmethod
    def _has_doc_response(con, defense_session_id: str, question_id: str) -> bool:
        return bool(con.execute(
            "SELECT 1 FROM doc_defense_responses WHERE defense_session_id=? AND question_id=?",
            (defense_session_id, question_id)).fetchone())

    def has_doc_response(self, defense_session_id: str, question_id: str) -> bool:
        with self._connect() as con:
            return self._has_doc_response(con, defense_session_id, question_id)

    def get_doc_response(self, defense_session_id: str, question_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM doc_defense_responses WHERE defense_session_id=? AND question_id=?",
                (defense_session_id, question_id)).fetchone()
            return dict(row) if row else None

    def get_doc_responses(self, defense_session_id: str, *, batch_exam_id: str | None = None) -> dict[str, dict]:
        with self._connect() as con:
            if batch_exam_id is not None:
                rows = con.execute(
                    "SELECT * FROM doc_defense_responses WHERE defense_session_id=? AND batch_exam_id=? ORDER BY response_seq",
                    (defense_session_id, batch_exam_id)).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM doc_defense_responses WHERE defense_session_id=? ORDER BY response_seq",
                    (defense_session_id,)).fetchall()
            return {r["response_id"]: dict(r) for r in rows}

    def record_doc_response(self, defense_session_id: str, *, batch_exam_id: str,
                            response_id: str, turn_id: str, question_id: str,
                            response_text: str, is_idk_declaration: bool = False,
                            declared_design_change: bool = False) -> dict:
        if not isinstance(response_text, str) or not response_text.strip():
            raise StoreError("EMPTY_OR_UNUSABLE_RESPONSE")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            sess = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if sess is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            if sess["session_status"] != "ACTIVE":
                raise StoreError("DOC_SESSION_NOT_ACTIVE")
            q_row = con.execute(
                "SELECT * FROM doc_defense_questions WHERE defense_session_id=? AND batch_exam_id=? AND question_id=?",
                (defense_session_id, batch_exam_id, question_id)).fetchone()
            if q_row is None:
                raise StoreError("UNREGISTERED_QUESTION_OR_CRITERION_REF")
            if sess["document_version"] != q_row["document_version"] or sess["document_sha256"] != q_row["document_sha256"]:
                raise StoreError("DOC_VERSION_MISMATCH")
            if q_row["voided"]:
                raise StoreError("QUESTION_IS_VOIDED")
            if not q_row["delivered_to_learner"]:
                raise StoreError("QUESTION_NOT_DELIVERED")
            if q_row["defense_record_closed"]:
                raise StoreError("DEFENSE_RECORD_ALREADY_CLOSED")
            if q_row["parent_question_id"] and not self._has_doc_response(con, defense_session_id, q_row["parent_question_id"]):
                raise StoreError("PARENT_RESPONSE_MISSING")

            existing = con.execute(
                "SELECT * FROM doc_defense_responses WHERE defense_session_id=? AND question_id=?",
                (defense_session_id, question_id)).fetchone()
            if existing:
                if (existing["response_id"] != response_id
                        or existing["response_text"] != response_text
                        or bool(existing["is_idk_declaration"]) != bool(is_idk_declaration)
                        or bool(existing["declared_design_change"]) != bool(declared_design_change)):
                    raise StoreError("RESPONSE_MUTATION")
                return self._doc_session_state(con, defense_session_id)

            scope_item = con.execute(
                "SELECT assistance_sources FROM doc_defense_scope_items WHERE defense_session_id=? AND section_id=? AND dimension=?",
                (defense_session_id, q_row["section_id"], q_row["target_dimension"])).fetchone()
            sources = json.loads(scope_item["assistance_sources"]) if scope_item else []
            was_assisted = 1 if sources else 0

            con.execute("""
                INSERT INTO doc_defense_responses(
                  defense_session_id, batch_exam_id, response_id, turn_id,
                  question_id, parent_question_id, document_version, document_sha256,
                  section_id, passage_id, target_dimension, response_text,
                  is_idk_declaration, declared_design_change, was_assisted_at_submission
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (defense_session_id, batch_exam_id, response_id, turn_id,
                  question_id, q_row["parent_question_id"], q_row["document_version"],
                  q_row["document_sha256"], q_row["section_id"], q_row["passage_id"],
                  q_row["target_dimension"], response_text,
                  1 if is_idk_declaration else 0, 1 if declared_design_change else 0,
                  was_assisted))
            if sess["pending_followup_id"] == question_id:
                con.execute("UPDATE doc_defense_sessions SET pending_followup_id=NULL WHERE defense_session_id=?", (defense_session_id,))
            return self._doc_session_state(con, defense_session_id)

    def close_doc_question_defense_record(self, defense_session_id: str, *,
                                          batch_exam_id: str, question_id: str,
                                          response_id: str, turn_id: str) -> dict:
        """Close the defense record for a question+response before transitioning to teaching."""
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            sess = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if sess is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            b_row = con.execute(
                "SELECT * FROM doc_defense_batches WHERE batch_exam_id=? AND defense_session_id=?",
                (batch_exam_id, defense_session_id)).fetchone()
            if b_row is None:
                raise StoreError("UNREGISTERED_DOC_BATCH")
            q_row = con.execute(
                "SELECT * FROM doc_defense_questions WHERE defense_session_id=? AND batch_exam_id=? AND question_id=?",
                (defense_session_id, batch_exam_id, question_id)).fetchone()
            if q_row is None:
                raise StoreError("UNREGISTERED_QUESTION_OR_CRITERION_REF")
            if (b_row["document_id"] != sess["document_id"]
                    or b_row["document_version"] != sess["document_version"]
                    or b_row["document_sha256"] != sess["document_sha256"]
                    or q_row["document_version"] != sess["document_version"]
                    or q_row["document_sha256"] != sess["document_sha256"]):
                raise StoreError("DOC_VERSION_MISMATCH")
            r_row = con.execute(
                "SELECT * FROM doc_defense_responses WHERE defense_session_id=? AND question_id=? AND response_id=?",
                (defense_session_id, question_id, response_id)).fetchone()
            if r_row is None:
                raise StoreError("RESPONSE_REQUIRED_BEFORE_CLOSING_DEFENSE_RECORD")
            if not q_row["defense_record_closed"]:
                con.execute(
                    "UPDATE doc_defense_questions SET defense_record_closed=1 WHERE defense_session_id=? AND question_id=?",
                    (defense_session_id, question_id))
                if sess["pending_followup_id"] == question_id:
                    con.execute("UPDATE doc_defense_sessions SET pending_followup_id=NULL WHERE defense_session_id=?", (defense_session_id,))
                pkg = self._get_doc_batch(con, batch_exam_id)
                con.execute("UPDATE doc_defense_batches SET package=? WHERE batch_exam_id=?", (_dump(pkg), batch_exam_id))
                con.execute("""
                    INSERT INTO doc_defense_events(
                      defense_session_id, batch_exam_id, turn_id, question_id,
                      section_id, dimension, document_version, document_sha256,
                      event_type, detail_id, payload
                    ) VALUES (?,?,?,?,?,?,?,?,'DEFENSE_RECORD_CLOSED_FOR_TEACHING',?,?)
                """, (defense_session_id, batch_exam_id, turn_id, question_id,
                      q_row["section_id"], q_row["target_dimension"],
                      q_row["document_version"], q_row["document_sha256"],
                      response_id, _dump({"closed_question_id": question_id, "closed_response_id": response_id})))
                con.execute("UPDATE doc_defense_sessions SET session_revision=session_revision+1 WHERE defense_session_id=?", (defense_session_id,))
            return self._doc_session_state(con, defense_session_id)

    def commit_doc_teaching_event(self, defense_session_id: str, *,
                                  batch_exam_id: str, question_id: str,
                                  response_id: str, teaching_packet: dict,
                                  turn_id: str, expected_revision: int) -> dict:
        """Commit help record BEFORE teaching explanation is shown; taint dimension and downstream dimensions."""
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            sess = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if sess is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            if sess["session_status"] != "ACTIVE":
                raise StoreError("DOC_SESSION_NOT_ACTIVE")
            if sess["session_revision"] != expected_revision:
                raise StoreError("SESSION_REVISION_CONFLICT")
            b_row = con.execute(
                "SELECT * FROM doc_defense_batches WHERE batch_exam_id=? AND defense_session_id=?",
                (batch_exam_id, defense_session_id)).fetchone()
            if b_row is None:
                raise StoreError("UNREGISTERED_DOC_BATCH")
            q_row = con.execute(
                "SELECT * FROM doc_defense_questions WHERE defense_session_id=? AND batch_exam_id=? AND question_id=?",
                (defense_session_id, batch_exam_id, question_id)).fetchone()
            if q_row is None:
                raise StoreError("UNREGISTERED_QUESTION_OR_CRITERION_REF")
            if (b_row["document_id"] != sess["document_id"]
                    or b_row["document_version"] != sess["document_version"]
                    or b_row["document_sha256"] != sess["document_sha256"]
                    or q_row["document_version"] != sess["document_version"]
                    or q_row["document_sha256"] != sess["document_sha256"]):
                raise StoreError("DOC_VERSION_MISMATCH")
            if not q_row["defense_record_closed"]:
                raise StoreError("DEFENSE_RECORD_NOT_CLOSED")
            r_row = con.execute(
                "SELECT * FROM doc_defense_responses WHERE defense_session_id=? AND question_id=? AND response_id=?",
                (defense_session_id, question_id, response_id)).fetchone()
            if r_row is None:
                raise StoreError("RESPONSE_REQUIRED_BEFORE_TEACHING")

            teaching_id = teaching_packet["teaching_packet_id"]
            dup = con.execute(
                "SELECT 1 FROM doc_defense_events WHERE defense_session_id=? AND question_id=? AND event_type='TEACHING_EXPLANATION_SHOWN'",
                (defense_session_id, question_id)).fetchone()
            if dup:
                raise StoreError("ALREADY_DELIVERED")

            sec_id = q_row["section_id"]
            dim = q_row["target_dimension"]
            self._add_scope_assistance_source(con, defense_session_id, sec_id, dim, "TEACHING_DELIVERED")
            # Preserve prior INSPECTED (UNASSISTED or ASSISTED) scope status if an earlier question in this
            # dimension was already explained; only transition OPEN scope items to ADDRESSED_WITH_TEACHING.
            con.execute("""
                UPDATE doc_defense_scope_items
                SET status='ADDRESSED_WITH_TEACHING', status_reason='TEACHING_DELIVERED'
                WHERE defense_session_id=? AND section_id=? AND dimension=? AND explanation_mode='NONE'
            """, (defense_session_id, sec_id, dim))

            for affected in teaching_packet.get("downstream_affected_dimensions", []):
                self._add_scope_assistance_source(con, defense_session_id, affected["section_id"], affected["dimension"], "TEACHING_DELIVERED")

            con.execute("""
                INSERT INTO doc_defense_events(
                  defense_session_id, batch_exam_id, turn_id, question_id,
                  section_id, dimension, document_version, document_sha256,
                  event_type, detail_id, payload
                ) VALUES (?,?,?,?,?,?,?,?,'TEACHING_EXPLANATION_SHOWN',?,?)
            """, (defense_session_id, batch_exam_id, turn_id, question_id,
                  sec_id, dim, q_row["document_version"], q_row["document_sha256"],
                  teaching_id, _dump(teaching_packet)))
            con.execute("UPDATE doc_defense_sessions SET session_revision=session_revision+1 WHERE defense_session_id=?", (defense_session_id,))
            return self._doc_session_state(con, defense_session_id)

    def register_doc_followup(self, defense_session_id: str, *, batch_exam_id: str,
                              followup_obj: dict, turn_id: str) -> dict:
        """Register at most 1 follow-up question for a main question with its own ID."""
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            sess = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if sess is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            b_row = con.execute(
                "SELECT * FROM doc_defense_batches WHERE batch_exam_id=? AND defense_session_id=?",
                (batch_exam_id, defense_session_id)).fetchone()
            if b_row is None:
                raise StoreError("UNREGISTERED_DOC_BATCH")
            parent_id = followup_obj["parent_question_id"]
            fq_id = followup_obj["followup_question_id"]
            parent_row = con.execute(
                "SELECT * FROM doc_defense_questions WHERE defense_session_id=? AND batch_exam_id=? AND question_id=?",
                (defense_session_id, batch_exam_id, parent_id)).fetchone()
            if parent_row is None:
                raise StoreError("UNREGISTERED_QUESTION_OR_CRITERION_REF")
            if (b_row["document_id"] != sess["document_id"]
                    or b_row["document_version"] != sess["document_version"]
                    or b_row["document_sha256"] != sess["document_sha256"]
                    or parent_row["document_version"] != sess["document_version"]
                    or parent_row["document_sha256"] != sess["document_sha256"]):
                raise StoreError("DOC_VERSION_MISMATCH")
            if parent_row["parent_question_id"] is not None:
                raise StoreError("FOLLOWUP_ON_FOLLOWUP_FORBIDDEN")
            if not self._has_doc_response(con, defense_session_id, parent_id):
                raise StoreError("PRIOR_RESPONSE_REQUIRED")
            existing_fq = con.execute(
                "SELECT question_id FROM doc_defense_questions WHERE defense_session_id=? AND parent_question_id=?",
                (defense_session_id, parent_id)).fetchone()
            if existing_fq is not None:
                if existing_fq["question_id"] == fq_id:
                    return self._get_doc_batch(con, batch_exam_id)
                raise StoreError("FOLLOWUP_CAP_EXCEEDED")
            q_payload = {
                "question_id": fq_id,
                "parent_question_id": parent_id,
                "section_id": followup_obj["section_id"],
                "passage_id": followup_obj["passage_id"],
                "heading_path": json.loads(parent_row["question_payload"])["heading_path"],
                "target_dimension": followup_obj["target_dimension"],
                "claim_epistemic_status": parent_row["claim_epistemic_status"],
                "followup_reason": followup_obj["followup_reason"],
                "neutral_question_prompt": followup_obj["neutral_followup_prompt"],
                "expected_explanation_criteria": json.loads(parent_row["immutable_criteria"]),
                "on_demand_hints": [],
            }
            con.execute("""
                INSERT INTO doc_defense_questions(
                  defense_session_id, batch_exam_id, question_id, parent_question_id,
                  document_version, document_sha256, section_id, passage_id,
                  target_dimension, claim_epistemic_status, question_payload,
                  immutable_criteria, delivered_to_learner, voided, defense_record_closed
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,0,0)
            """, (defense_session_id, batch_exam_id, fq_id, parent_id,
                  parent_row["document_version"], parent_row["document_sha256"],
                  followup_obj["section_id"], followup_obj["passage_id"],
                  followup_obj["target_dimension"], parent_row["claim_epistemic_status"],
                  _dump(q_payload), parent_row["immutable_criteria"]))
            con.execute("UPDATE doc_defense_sessions SET pending_followup_id=? WHERE defense_session_id=?", (fq_id, defense_session_id))
            pkg = self._get_doc_batch(con, batch_exam_id)
            con.execute("UPDATE doc_defense_batches SET package=? WHERE batch_exam_id=?", (_dump(pkg), batch_exam_id))
            return pkg

    def void_doc_question(self, defense_session_id: str, *, batch_exam_id: str,
                          question_id: str, reason: str,
                          turn_id: str = "DTURN-20261017-99") -> dict:
        """Void a defective question without mutating historical records or counting against learner."""
        if not isinstance(reason, str) or not reason.strip():
            raise StoreError("VOID_REASON_REQUIRED")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            sess = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if sess is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            q_row = con.execute(
                "SELECT * FROM doc_defense_questions WHERE defense_session_id=? AND batch_exam_id=? AND question_id=?",
                (defense_session_id, batch_exam_id, question_id)).fetchone()
            if q_row is None:
                raise StoreError("UNREGISTERED_QUESTION_OR_CRITERION_REF")
            con.execute(
                "UPDATE doc_defense_questions SET voided=1, void_reason=? WHERE defense_session_id=? AND question_id=?",
                (reason.strip(), defense_session_id, question_id))
            if sess["pending_followup_id"] == question_id:
                con.execute("UPDATE doc_defense_sessions SET pending_followup_id=NULL WHERE defense_session_id=?", (defense_session_id,))
            pkg = self._get_doc_batch(con, batch_exam_id)
            con.execute("UPDATE doc_defense_batches SET package=? WHERE batch_exam_id=?", (_dump(pkg), batch_exam_id))
            con.execute("""
                INSERT INTO doc_defense_events(
                  defense_session_id, batch_exam_id, turn_id, question_id,
                  section_id, dimension, document_version, document_sha256,
                  event_type, detail_id, payload
                ) VALUES (?,?,?,?,?,?,?,?,'QUESTION_VOIDED_DEFECTIVE',?,?)
            """, (defense_session_id, batch_exam_id, turn_id, question_id,
                  q_row["section_id"], q_row["target_dimension"],
                  q_row["document_version"], q_row["document_sha256"],
                  question_id, _dump({"voided_question_id": question_id, "reason": reason.strip()})))
            con.execute("UPDATE doc_defense_sessions SET session_revision=session_revision+1 WHERE defense_session_id=?", (defense_session_id,))
            return self._doc_session_state(con, defense_session_id)

    def apply_doc_analysis_outcomes(self, defense_session_id: str, *,
                                    batch_exam_id: str, output: dict,
                                    turn_id: str = "DTURN-20261017-50",
                                    expected_responses: list[dict] | None = None) -> dict:
        """Persist validated response evaluations, follow-up registrations, and scope outcomes."""
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            sess = con.execute("SELECT * FROM doc_defense_sessions WHERE defense_session_id=?", (defense_session_id,)).fetchone()
            if sess is None:
                raise StoreError("DOC_SESSION_NOT_FOUND")
            b_row = con.execute(
                "SELECT * FROM doc_defense_batches WHERE batch_exam_id=? AND defense_session_id=?",
                (batch_exam_id, defense_session_id)).fetchone()
            if b_row is None:
                raise StoreError("UNREGISTERED_DOC_BATCH")
            if b_row["document_version"] != sess["document_version"] or b_row["document_sha256"] != sess["document_sha256"]:
                raise StoreError("DOC_VERSION_MISMATCH")
            exp_by_id = {r["response_id"]: r for r in expected_responses} if expected_responses is not None else {}
            observations = output.get("orchestrator_only_payload", {}).get("defense_response_observations", [])
            for obs in observations:
                q_id = obs["question_id"]
                resp_id = obs["response_id"]
                verdict = obs["evaluation_verdict"]
                r_row = con.execute(
                    "SELECT * FROM doc_defense_responses WHERE defense_session_id=? AND batch_exam_id=? AND response_id=?",
                    (defense_session_id, batch_exam_id, resp_id)).fetchone()
                if r_row is None:
                    raise StoreError("UNREGISTERED_RESPONSE_REF")
                if (r_row["question_id"] != q_id
                        or r_row["turn_id"] != obs["turn_id"]
                        or r_row["parent_question_id"] != obs["parent_question_id"]
                        or r_row["section_id"] != obs["section_id"]
                        or r_row["passage_id"] != obs["passage_id"]
                        or r_row["target_dimension"] != obs["target_dimension"]
                        or r_row["document_version"] != sess["document_version"]
                        or r_row["document_sha256"] != sess["document_sha256"]):
                    raise StoreError("RESPONSE_RECORD_MISMATCH")
                if bool(r_row["is_idk_declaration"]) != (verdict == "IDK_DECLARED_READY_FOR_TEACHING"):
                    raise StoreError("RESPONSE_RECORD_MISMATCH")
                if expected_responses is not None:
                    exp = exp_by_id.get(resp_id)
                    if (exp is None
                            or exp.get("raw_response_text") != r_row["response_text"]
                            or bool(exp.get("is_idk_declaration")) != bool(r_row["is_idk_declaration"])
                            or bool(exp.get("declared_design_change")) != bool(r_row["declared_design_change"])):
                        raise StoreError("RESPONSE_RECORD_MISMATCH")

                con.execute(
                    "UPDATE doc_defense_responses SET evaluation_verdict=? WHERE defense_session_id=? AND response_id=?",
                    (verdict, defense_session_id, resp_id))
                sec_id = obs["section_id"]
                dim = obs["target_dimension"]
                scope_row = con.execute(
                    "SELECT * FROM doc_defense_scope_items WHERE defense_session_id=? AND section_id=? AND dimension=?",
                    (defense_session_id, sec_id, dim)).fetchone()
                # F3: Assistance taint for a response is determined by its submission-time state
                # (was_assisted_at_submission), never retroactively by help recorded AFTER the response was submitted.
                sub_assisted = bool(r_row["was_assisted_at_submission"])
                if sub_assisted and obs["assistance_classification_for_response"] == "UNASSISTED":
                    raise StoreError("ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH")
                was_assisted = sub_assisted or obs["assistance_classification_for_response"] in {
                    "ASSISTED_BY_HINT", "ASSISTED_BY_PRIOR_TEACHING_IN_DIMENSION", "ASSISTED_BY_PRIOR_HELP_RECORD"
                }

                if verdict in {"DIRECT_CRITERION_MATCH", "ALTERNATIVE_VALID_EXPLANATION"}:
                    if was_assisted:
                        # Preserve prior UNASSISTED if a previous question in this dimension was already unassisted;
                        # otherwise mark ASSISTED.
                        if scope_row and scope_row["explanation_mode"] != "UNASSISTED":
                            con.execute("""
                                UPDATE doc_defense_scope_items
                                SET status='INSPECTED', status_reason='EXPLAINED_WITH_ASSISTANCE', explanation_mode='ASSISTED'
                                WHERE defense_session_id=? AND section_id=? AND dimension=?
                            """, (defense_session_id, sec_id, dim))
                    else:
                        con.execute("""
                            UPDATE doc_defense_scope_items
                            SET status='INSPECTED', status_reason='EXPLAINED_UNASSISTED', explanation_mode='UNASSISTED'
                            WHERE defense_session_id=? AND section_id=? AND dimension=?
                        """, (defense_session_id, sec_id, dim))
                elif verdict == "IDK_DECLARED_READY_FOR_TEACHING":
                    # Close defense record immediately so teaching transition can proceed safely
                    con.execute(
                        "UPDATE doc_defense_questions SET defense_record_closed=1 WHERE defense_session_id=? AND question_id=?",
                        (defense_session_id, q_id))
                    if sess["pending_followup_id"] == q_id:
                        con.execute("UPDATE doc_defense_sessions SET pending_followup_id=NULL WHERE defense_session_id=?", (defense_session_id,))
                    pkg = self._get_doc_batch(con, batch_exam_id)
                    con.execute("UPDATE doc_defense_batches SET package=? WHERE batch_exam_id=?", (_dump(pkg), batch_exam_id))
                    con.execute("""
                        INSERT INTO doc_defense_events(
                          defense_session_id, batch_exam_id, turn_id, question_id,
                          section_id, dimension, document_version, document_sha256,
                          event_type, detail_id, payload
                        ) VALUES (?,?,?,?,?,?,?,?,'DEFENSE_RECORD_CLOSED_FOR_TEACHING',?,?)
                    """, (defense_session_id, batch_exam_id, turn_id, q_id,
                          sec_id, dim, sess["document_version"], sess["document_sha256"],
                          resp_id, _dump({"closed_question_id": q_id, "closed_response_id": resp_id})))

                if obs.get("followup_question"):
                    fq = obs["followup_question"]
                    existing_fq = con.execute(
                        "SELECT question_id FROM doc_defense_questions WHERE defense_session_id=? AND parent_question_id=?",
                        (defense_session_id, fq["parent_question_id"])).fetchone()
                    if existing_fq is not None and existing_fq["question_id"] != fq["followup_question_id"]:
                        raise StoreError("FOLLOWUP_CAP_EXCEEDED")
                    if existing_fq is None:
                        parent_row = con.execute(
                            "SELECT * FROM doc_defense_questions WHERE defense_session_id=? AND question_id=?",
                            (defense_session_id, fq["parent_question_id"])).fetchone()
                        q_payload = {
                            "question_id": fq["followup_question_id"],
                            "parent_question_id": fq["parent_question_id"],
                            "section_id": fq["section_id"],
                            "passage_id": fq["passage_id"],
                            "heading_path": json.loads(parent_row["question_payload"])["heading_path"],
                            "target_dimension": fq["target_dimension"],
                            "claim_epistemic_status": parent_row["claim_epistemic_status"],
                            "followup_reason": fq["followup_reason"],
                            "neutral_question_prompt": fq["neutral_followup_prompt"],
                            "expected_explanation_criteria": json.loads(parent_row["immutable_criteria"]),
                            "on_demand_hints": [],
                        }
                        con.execute("""
                            INSERT INTO doc_defense_questions(
                              defense_session_id, batch_exam_id, question_id, parent_question_id,
                              document_version, document_sha256, section_id, passage_id,
                              target_dimension, claim_epistemic_status, question_payload,
                              immutable_criteria, delivered_to_learner, voided, defense_record_closed
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,0,0)
                        """, (defense_session_id, batch_exam_id, fq["followup_question_id"],
                              fq["parent_question_id"], parent_row["document_version"],
                              parent_row["document_sha256"], fq["section_id"], fq["passage_id"],
                              fq["target_dimension"], parent_row["claim_epistemic_status"],
                              _dump(q_payload), parent_row["immutable_criteria"]))
                        con.execute("UPDATE doc_defense_sessions SET pending_followup_id=? WHERE defense_session_id=?",
                                    (fq["followup_question_id"], defense_session_id))
                        pkg = self._get_doc_batch(con, batch_exam_id)
                        con.execute("UPDATE doc_defense_batches SET package=? WHERE batch_exam_id=?", (_dump(pkg), batch_exam_id))

            con.execute("UPDATE doc_defense_sessions SET session_revision=session_revision+1 WHERE defense_session_id=?", (defense_session_id,))
            return self._doc_session_state(con, defense_session_id)

    def get_doc_disclosed_context(self, defense_session_id: str) -> list[dict]:
        with self._connect() as con:
            result = []
            for ev in con.execute("SELECT * FROM doc_defense_events WHERE defense_session_id=? ORDER BY event_seq", (defense_session_id,)):
                if ev["event_type"] in {"DOC_QUESTION_SHOWN", "DOC_FOLLOWUP_SHOWN"}:
                    qr = con.execute("SELECT question_payload FROM doc_defense_questions WHERE defense_session_id=? AND question_id=?",
                                     (defense_session_id, ev["question_id"])).fetchone()
                    if qr:
                        qp = json.loads(qr["question_payload"])
                        result.append({"question_id": ev["question_id"], "event_type": ev["event_type"], "text": qp.get("neutral_question_prompt", "")})
                elif ev["event_type"] in {"DOC_HINT_1_SHOWN", "DOC_HINT_2_SHOWN"}:
                    qr = con.execute("SELECT question_payload FROM doc_defense_questions WHERE defense_session_id=? AND question_id=?",
                                     (defense_session_id, ev["question_id"])).fetchone()
                    if qr:
                        qp = json.loads(qr["question_payload"])
                        hint_text = next((h["conceptual_nudge"] for h in qp.get("on_demand_hints", []) if h["hint_id"] == ev["detail_id"]), None)
                        if hint_text:
                            result.append({"question_id": ev["question_id"], "event_type": ev["event_type"], "text": hint_text})
                elif ev["event_type"] == "TEACHING_EXPLANATION_SHOWN":
                    tp = json.loads(ev["payload"])
                    result.append({"question_id": ev["question_id"], "event_type": ev["event_type"],
                                   "text": tp.get("concept_and_rationale_explanation", "")})
            return result
