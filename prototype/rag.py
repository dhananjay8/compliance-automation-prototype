import hashlib
import json
import os
import re
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from db import Database, db


class RAGQuery(BaseModel):
    query: str = Field(..., min_length=1)


class RAGResponse(BaseModel):
    answer: str
    intent: str = ""
    confidence: float = 0.0
    citations: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    retrieved_entities: list[Any] = Field(default_factory=list)


class RAGIndexRequest(BaseModel):
    entity_type: str
    entity_id: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks; keeps small content as one chunk."""
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
        if start >= len(text) - overlap:
            break
    return chunks


def _to_jsonb(value: Any) -> str:
    return json.dumps(value)


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------


class RAGIndexer:
    def __init__(self, database: Database) -> None:
        self.db = database

    def rebuild(self, tenant_id: str) -> dict[str, int]:
        self.db.execute("DELETE FROM rag_document WHERE tenant_id = %s", (tenant_id,))
        counts: dict[str, int] = {}
        for entity_type in (
            "COMMON_CONTROL",
            "FRAMEWORK_CONTROL",
            "TEST",
            "EVIDENCE",
            "POLICY",
            "AUDIT_REQUEST",
        ):
            counts[entity_type] = self._index_type(tenant_id, entity_type)
        return counts

    def index_entity(self, tenant_id: str, entity_type: str, entity_id: str) -> int:
        self.db.execute(
            "DELETE FROM rag_document WHERE tenant_id = %s AND entity_type = %s AND entity_id = %s",
            (tenant_id, entity_type, entity_id),
        )
        return self._index_type(tenant_id, entity_type, entity_id)

    def _index_type(self, tenant_id: str, entity_type: str, specific_id: str | None = None) -> int:
        rows = self._load_rows(tenant_id, entity_type, specific_id)
        count = 0
        for row in rows:
            content = self._canonical_content(entity_type, row)
            if not content:
                continue
            chunks = _chunk_text(content)
            self._upsert_document(tenant_id, entity_type, str(row["id"]), content, chunks)
            count += 1
        return count

    def _load_rows(self, tenant_id: str, entity_type: str, specific_id: str | None) -> list[dict[str, Any]]:
        if entity_type == "COMMON_CONTROL":
            sql = """SELECT cc.*, u.email as owner_email
                     FROM common_control cc
                     LEFT JOIN "user" u ON u.id = cc.owner_id
                     WHERE cc.tenant_id = %s AND cc.active = true"""
            params = (tenant_id,)
        elif entity_type == "FRAMEWORK_CONTROL":
            sql = """SELECT fc.*, f.code as framework_code, f.name as framework_name,
                            s.code as section_code, s.title as section_title,
                            cc.code as common_control_code, cc.statement as common_control_statement
                     FROM framework_control fc
                     JOIN framework f ON f.id = fc.framework_id
                     LEFT JOIN section s ON s.id = fc.section_id
                     JOIN common_control cc ON cc.id = fc.common_control_id
                     WHERE fc.tenant_id = %s"""
            params = (tenant_id,)
        elif entity_type == "TEST":
            sql = """SELECT t.*, rt.name as resource_type_name
                     FROM test t
                     JOIN resource_type rt ON rt.id = (
                         SELECT id FROM resource_type WHERE tenant_id = %s AND name = t.resource_type LIMIT 1
                     )
                     WHERE t.tenant_id = %s AND t.active = true"""
            params = (tenant_id, tenant_id)
        elif entity_type == "EVIDENCE":
            sql = """SELECT e.*, t.name as test_name, tr.status as test_result_status,
                            r.external_id as resource_external_id, tr.evaluated_at
                     FROM evidence e
                     JOIN test_result tr ON tr.id = e.test_result_id
                     JOIN test_run trun ON trun.id = tr.test_run_id
                     JOIN test t ON t.id = trun.test_id
                     LEFT JOIN resource r ON r.id = tr.resource_id
                     WHERE e.tenant_id = %s"""
            params = (tenant_id,)
        elif entity_type == "POLICY":
            sql = """SELECT p.*, u.email as owner_email
                     FROM policy p
                     LEFT JOIN "user" u ON u.id = p.owner_id
                     WHERE p.tenant_id = %s AND p.active = true"""
            params = (tenant_id,)
        elif entity_type == "AUDIT_REQUEST":
            sql = """SELECT ar.*, cc.code as control_code
                     FROM audit_request ar
                     LEFT JOIN common_control cc ON cc.id = ar.control_id
                     WHERE ar.tenant_id = %s"""
            params = (tenant_id,)
        else:
            return []

        if specific_id:
            sql += " AND {}.id = %s".format(self._alias_for(entity_type))
            params = params + (specific_id,)
        return self.db.execute(sql, params)

    def _alias_for(self, entity_type: str) -> str:
        return {
            "COMMON_CONTROL": "cc",
            "FRAMEWORK_CONTROL": "fc",
            "TEST": "t",
            "EVIDENCE": "e",
            "POLICY": "p",
            "AUDIT_REQUEST": "ar",
        }.get(entity_type, "t")

    def _canonical_content(self, entity_type: str, row: dict[str, Any]) -> str:
        if entity_type == "COMMON_CONTROL":
            return (
                f"Common Control {row['code']} ({row['domain']})\n"
                f"Statement: {row['statement']}\n"
                f"Owner: {row.get('owner_email') or 'unassigned'}\n"
                f"Expected evidence: {row.get('expected_evidence') or 'N/A'}"
            )
        if entity_type == "FRAMEWORK_CONTROL":
            return (
                f"Framework {row['framework_code']} - {row['framework_name']}\n"
                f"Section: {row.get('section_code') or ''} {row.get('section_title') or ''}\n"
                f"Common Control: {row['common_control_code']}\n"
                f"Requirement: {row['requirement_text']}"
            )
        if entity_type == "TEST":
            rule = row.get("rule", {})
            if isinstance(rule, str):
                rule = json.loads(rule)
            return (
                f"Test {row['name']}\n"
                f"Resource type: {row['resource_type']}\n"
                f"Schedule: {row.get('schedule', '')}\n"
                f"Rule: {json.dumps(rule, default=str)}"
            )
        if entity_type == "EVIDENCE":
            return (
                f"Evidence type: {row['evidence_type']}\n"
                f"Test: {row.get('test_name', '')}\n"
                f"Resource: {row.get('resource_external_id') or 'N/A'}\n"
                f"Test result status: {row.get('test_result_status', '')}\n"
                f"Description: {row.get('description') or ''}\n"
                f"Collected: {row.get('collected_at')}\n"
                f"Expires: {row.get('expires_at')}"
            )
        if entity_type == "POLICY":
            body = (row.get("content") or "")[:800]
            return (
                f"Policy: {row['title']} (version {row.get('version') or 'N/A'})\n"
                f"Owner: {row.get('owner_email') or 'unassigned'}\n"
                f"{body}"
            )
        if entity_type == "AUDIT_REQUEST":
            return (
                f"Audit request\n"
                f"Control: {row.get('control_code') or 'none'}\n"
                f"Status: {row['status']}\n"
                f"Request: {row['request_text']}"
            )
        return ""

    def _upsert_document(self, tenant_id: str, entity_type: str, entity_id: str, content: str, chunks: list[str]) -> None:
        content_hash = _hash(content)
        existing = self.db.fetchone(
            "SELECT id, content_hash FROM rag_document WHERE tenant_id = %s AND entity_type = %s AND entity_id = %s",
            (tenant_id, entity_type, entity_id),
        )
        if existing and existing["content_hash"] == content_hash:
            return

        doc_id = str(uuid.uuid4())
        if existing:
            self.db.execute(
                """UPDATE rag_document
                   SET content = %s, content_hash = %s, version = version + 1, updated_at = %s
                   WHERE id = %s""",
                (content, content_hash, _now(), existing["id"]),
            )
            doc_id = existing["id"]
            self.db.execute("DELETE FROM rag_chunk WHERE rag_document_id = %s", (doc_id,))
        else:
            self.db.execute(
                """INSERT INTO rag_document (id, tenant_id, entity_type, entity_id, content, content_hash, version)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (doc_id, tenant_id, entity_type, entity_id, content, content_hash, 1),
            )

        for idx, chunk in enumerate(chunks):
            self.db.execute(
                """INSERT INTO rag_chunk (id, tenant_id, rag_document_id, chunk_index, content, content_hash)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (str(uuid.uuid4()), tenant_id, doc_id, idx, chunk, _hash(chunk)),
            )


# ---------------------------------------------------------------------------
# Query classification and entity extraction
# ---------------------------------------------------------------------------


class QueryClassification(BaseModel):
    intent: str
    entities: dict[str, Any] = Field(default_factory=dict)


class QueryClassifier:
    _FRAMEWORKS = [
        "SOC2", "SOC 2",
        "ISO27001", "ISO 27001",
        "HIPAA",
        "GDPR",
        "PCIDSS", "PCI DSS", "PCI-DSS",
        "NISTCSF", "NIST CSF",
        "CIS",
    ]

    _INTENT_PATTERNS = [
        ("FAILURE_EXPLANATION", r"\b(why is|why does|why did|why.*fail|what caused|explain why)\b"),
        ("EVIDENCE_SEARCH", r"\b(evidence|proof|support)\b"),
        ("FRAMEWORK_MAPPING", r"\b(impacted|affected|overlap|equivalent|which other frameworks|frameworks impacted)\b"),
        ("FAILING_CONTROLS", r"\b(failing|which controls are failing|what is failing|non[- ]?compliant|fails)\b"),
        ("CONTROL_STATUS", r"\b(status|compliant|compliance|are we|is.*compliant)\b"),
    ]

    def classify(self, query: str) -> QueryClassification:
        q = query.lower()
        intent = "GENERAL_COMPLIANCE_SEARCH"
        for pattern_intent, pattern in self._INTENT_PATTERNS:
            if re.search(pattern, q):
                intent = pattern_intent
                break

        entities: dict[str, Any] = {}

        # Framework code
        for fw in self._FRAMEWORKS:
            if re.search(rf"\b{re.escape(fw.lower())}\b", q):
                entities["framework"] = fw.upper().replace(" ", "")
                break

        # Section/control references like CC6.1, 164.312(d), 8.3, A.9.4.2
        section_match = re.search(r"\b(cc\d+(?:\.\d+)?|a\.\d+(?:\.\d+)*|164\.\d{3}[a-z]?\([^)]*\)|\d+\.\d+(?:\.\d+)*)\b", q)
        if section_match:
            entities["section_or_control"] = section_match.group(1).upper()

        # Common control codes like CC-MFA-001
        cc_match = re.search(r"\b(cc-[a-z]{2,}-\d{3})\b", q)
        if cc_match:
            entities["common_control"] = cc_match.group(1).upper()

        # Topics
        for topic in ["mfa", "encryption", "vulnerability", "training", "access", "backup", "logging"]:
            if re.search(rf"\b{topic}\b", q):
                entities["topic"] = topic
                break

        return QueryClassification(intent=intent, entities=entities)


# ---------------------------------------------------------------------------
# Entity resolver (turn extracted strings into actual DB ids)
# ---------------------------------------------------------------------------


class ResolvedEntities(BaseModel):
    framework_id: str | None = None
    section_id: str | None = None
    common_control_id: str | None = None
    test_id: str | None = None
    topic: str | None = None


class EntityResolver:
    def __init__(self, database: Database) -> None:
        self.db = database

    def resolve(self, tenant_id: str, entities: dict[str, Any]) -> ResolvedEntities:
        resolved = ResolvedEntities()

        framework_code = entities.get("framework")
        if framework_code:
            row = self.db.fetchone(
                "SELECT id FROM framework WHERE tenant_id = %s AND code = %s",
                (tenant_id, framework_code),
            )
            if row:
                resolved.framework_id = row["id"]

        section_or_control = entities.get("section_or_control")
        common_control = entities.get("common_control")

        if common_control:
            row = self.db.fetchone(
                "SELECT id FROM common_control WHERE tenant_id = %s AND code = %s",
                (tenant_id, common_control),
            )
            if row:
                resolved.common_control_id = row["id"]

        if section_or_control and not resolved.common_control_id:
            # Try framework control / section code first (specific framework if known)
            if resolved.framework_id:
                row = self.db.fetchone(
                    """SELECT fc.id, fc.common_control_id
                       FROM framework_control fc
                       JOIN common_control cc ON cc.id = fc.common_control_id
                       LEFT JOIN section s ON s.id = fc.section_id
                       WHERE fc.tenant_id = %s AND fc.framework_id = %s
                         AND (fc.requirement_text ILIKE %s OR cc.code ILIKE %s OR s.code ILIKE %s)""",
                    (tenant_id, resolved.framework_id, f"%{section_or_control}%", f"%{section_or_control}%", f"%{section_or_control}%"),
                )
                if row:
                    resolved.common_control_id = row["common_control_id"]

        if section_or_control and not resolved.common_control_id:
            # Fallback: any framework with this section code, or any common control with this code
            row = self.db.fetchone(
                """SELECT fc.common_control_id
                   FROM framework_control fc
                   LEFT JOIN section s ON s.id = fc.section_id
                   JOIN common_control cc ON cc.id = fc.common_control_id
                   WHERE fc.tenant_id = %s
                     AND (s.code ILIKE %s OR cc.code ILIKE %s)
                   LIMIT 1""",
                (tenant_id, f"%{section_or_control}%", f"%{section_or_control}%"),
            )
            if row:
                resolved.common_control_id = row["common_control_id"]

        resolved.topic = entities.get("topic")
        return resolved


# ---------------------------------------------------------------------------
# Structured retriever (authoritative SQL)
# ---------------------------------------------------------------------------


class StructuredRetriever:
    def __init__(self, database: Database) -> None:
        self.db = database

    def retrieve(self, intent: str, tenant_id: str, resolved: ResolvedEntities, query: str) -> dict[str, Any]:
        if intent == "CONTROL_STATUS" or intent == "FAILURE_EXPLANATION":
            return self._control_status(tenant_id, resolved)
        if intent == "EVIDENCE_SEARCH":
            return self._evidence_search(tenant_id, resolved)
        if intent == "FRAMEWORK_MAPPING":
            return self._framework_mapping(tenant_id, resolved)
        if intent == "FAILING_CONTROLS":
            return self._failing_controls(tenant_id)
        return {}

    def _control_status(self, tenant_id: str, resolved: ResolvedEntities) -> dict[str, Any]:
        if resolved.common_control_id:
            control_id = resolved.common_control_id
        else:
            control_id = self._find_control_by_topic(tenant_id, resolved.topic)

        if not control_id:
            return {"not_found": "Could not resolve control"}

        control = self.db.fetchone(
            """SELECT cc.*, u.email as owner_email
               FROM common_control cc
               LEFT JOIN "user" u ON u.id = cc.owner_id
               WHERE cc.id = %s AND cc.tenant_id = %s""",
            (control_id, tenant_id),
        )
        if not control:
            return {"not_found": "Control not found"}

        tests = self._tests_for_control(tenant_id, control_id)
        results = []
        for test in tests:
            latest = self._latest_results(tenant_id, test["id"])
            results.append({"test": test, "latest_results": latest})

        status_data = self._rollup_control_status(results)
        failing_resources: list[dict[str, Any]] = []
        for item in results:
            failing_resources.extend(r for r in item["latest_results"] if r["status"] in ("NEEDS_ATTENTION", "INVALID"))
        return {
            "control": control,
            "frameworks": self._frameworks_for_control(tenant_id, control_id),
            "test_results": results,
            "failing_resources": failing_resources,
            **status_data,
        }

    def _evidence_search(self, tenant_id: str, resolved: ResolvedEntities) -> dict[str, Any]:
        control_id = resolved.common_control_id or self._find_control_by_topic(tenant_id, resolved.topic)
        if not control_id:
            return {"not_found": "Could not resolve control"}

        tests = self._tests_for_control(tenant_id, control_id)
        all_evidence: list[dict[str, Any]] = []
        for test in tests:
            rows = self.db.execute(
                """SELECT e.*, t.name as test_name, r.external_id as resource_external_id,
                          tr.status as test_result_status, tr.evaluated_at
                   FROM evidence e
                   JOIN test_result tr ON tr.id = e.test_result_id
                   JOIN test_run trun ON trun.id = tr.test_run_id
                   JOIN test t ON t.id = trun.test_id
                   LEFT JOIN resource r ON r.id = tr.resource_id
                   WHERE e.tenant_id = %s AND trun.test_id = %s
                   ORDER BY e.collected_at DESC""",
                (tenant_id, test["id"]),
            )
            all_evidence.extend(rows)

        return {
            "control_id": control_id,
            "evidence": all_evidence,
            "frameworks": self._frameworks_for_control(tenant_id, control_id),
        }

    def _framework_mapping(self, tenant_id: str, resolved: ResolvedEntities) -> dict[str, Any]:
        control_id = resolved.common_control_id or self._find_control_by_topic(tenant_id, resolved.topic)
        if not control_id:
            return {"not_found": "Could not resolve control"}

        control = self.db.fetchone(
            "SELECT * FROM common_control WHERE id = %s AND tenant_id = %s",
            (control_id, tenant_id),
        )
        return {
            "control": control,
            "frameworks": self._frameworks_for_control(tenant_id, control_id),
            "related_controls": self._related_controls_by_topic(tenant_id, control),
        }

    def _failing_controls(self, tenant_id: str) -> dict[str, Any]:
        control_ids = self._all_common_control_ids(tenant_id)
        failing = []
        for cc_id in control_ids:
            tests = self._tests_for_control(tenant_id, cc_id)
            has_na = False
            for test in tests:
                latest = self._latest_results(tenant_id, test["id"])
                if any(r["status"] == "NEEDS_ATTENTION" for r in latest):
                    has_na = True
                    break
            if has_na:
                control = self.db.fetchone(
                    "SELECT * FROM common_control WHERE id = %s AND tenant_id = %s",
                    (cc_id, tenant_id),
                )
                if control:
                    failing.append(control)
        return {"failing_controls": failing}

    def _all_common_control_ids(self, tenant_id: str) -> list[str]:
        rows = self.db.execute(
            "SELECT id FROM common_control WHERE tenant_id = %s AND active = true",
            (tenant_id,),
        )
        return [r["id"] for r in rows]

    def _tests_for_control(self, tenant_id: str, common_control_id: str) -> list[dict[str, Any]]:
        return self.db.execute(
            """SELECT t.*
               FROM control_test ct
               JOIN test t ON t.id = ct.test_id
               WHERE ct.tenant_id = %s AND ct.common_control_id = %s AND t.active = true""",
            (tenant_id, common_control_id),
        )

    def _latest_results(self, tenant_id: str, test_id: str) -> list[dict[str, Any]]:
        run = self.db.fetchone(
            """SELECT id, completed_at
               FROM test_run
               WHERE tenant_id = %s AND test_id = %s AND status = 'completed'
               ORDER BY completed_at DESC
               LIMIT 1""",
            (tenant_id, test_id),
        )
        if not run:
            return []
        return self.db.execute(
            """SELECT tr.*, r.external_id as resource_external_id
               FROM test_result tr
               LEFT JOIN resource r ON r.id = tr.resource_id
               WHERE tr.test_run_id = %s AND tr.tenant_id = %s
               ORDER BY tr.evaluated_at DESC""",
            (run["id"], tenant_id),
        )

    def _rollup_control_status(self, test_results: list[dict[str, Any]]) -> dict[str, Any]:
        all_statuses: list[str] = []
        total_resources = 0
        ok = 0
        na = 0
        for item in test_results:
            for r in item["latest_results"]:
                all_statuses.append(r["status"])
                total_resources += 1
                if r["status"] == "OK":
                    ok += 1
                elif r["status"] == "NEEDS_ATTENTION":
                    na += 1

        if not all_statuses:
            return {"status": "NOT_TESTED", "total": 0, "ok": 0, "needs_attention": 0}
        if "NEEDS_ATTENTION" in all_statuses:
            status = "NEEDS_ATTENTION"
        elif "INVALID" in all_statuses:
            status = "INVALID"
        elif all(s == "OK" for s in all_statuses):
            status = "OK"
        else:
            status = "NEEDS_ATTENTION"
        return {"status": status, "total": total_resources, "ok": ok, "needs_attention": na}

    def _frameworks_for_control(self, tenant_id: str, common_control_id: str) -> list[dict[str, Any]]:
        return self.db.execute(
            """SELECT f.id, f.code, f.name, fc.requirement_text, s.code as section_code, s.title as section_title
               FROM framework_control fc
               JOIN framework f ON f.id = fc.framework_id
               LEFT JOIN section s ON s.id = fc.section_id
               WHERE fc.tenant_id = %s AND fc.common_control_id = %s""",
            (tenant_id, common_control_id),
        )

    def _find_control_by_topic(self, tenant_id: str, topic: str | None) -> str | None:
        if not topic:
            return None
        # Search common control code or statement for topic word
        row = self.db.fetchone(
            """SELECT id FROM common_control
               WHERE tenant_id = %s AND active = true
               AND (code ILIKE %s OR statement ILIKE %s)
               LIMIT 1""",
            (tenant_id, f"%{topic}%", f"%{topic}%"),
        )
        return row["id"] if row else None

    def _related_controls_by_topic(self, tenant_id: str, control: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not control:
            return []
        topic = ""
        for word in ["mfa", "encryption", "vulnerability", "training", "access", "backup", "logging"]:
            if word in (control.get("statement") or "").lower() or word in (control.get("code") or "").lower():
                topic = word
                break
        if not topic:
            return []
        return self.db.execute(
            """SELECT * FROM common_control
               WHERE tenant_id = %s AND active = true AND id != %s
               AND (code ILIKE %s OR statement ILIKE %s)""",
            (tenant_id, control["id"], f"%{topic}%", f"%{topic}%"),
        )


# ---------------------------------------------------------------------------
# Keyword / trigram retriever
# ---------------------------------------------------------------------------


class KeywordRetriever:
    def __init__(self, database: Database) -> None:
        self.db = database

    def search(self, tenant_id: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        # Prefer pg_trgm similarity if extension is loaded, otherwise use ILIKE
        try:
            rows = self.db.execute(
                """SELECT c.content, c.rag_document_id, d.entity_type, d.entity_id,
                          similarity(c.content, %s) as score
                   FROM rag_chunk c
                   JOIN rag_document d ON d.id = c.rag_document_id
                   WHERE d.tenant_id = %s
                   ORDER BY score DESC
                   LIMIT %s""",
                (query, tenant_id, top_k),
            )
            return rows
        except Exception:
            q = f"%{query}%"
            return self.db.execute(
                """SELECT c.content, c.rag_document_id, d.entity_type, d.entity_id, 1.0 as score
                   FROM rag_chunk c
                   JOIN rag_document d ON d.id = c.rag_document_id
                   WHERE d.tenant_id = %s AND c.content ILIKE %s
                   LIMIT %s""",
                (tenant_id, q, top_k),
            )


# ---------------------------------------------------------------------------
# Context builder and citation manager
# ---------------------------------------------------------------------------


class CitationManager:
    def __init__(self) -> None:
        self.citations: list[dict[str, Any]] = []
        self._by_key: dict[str, str] = {}

    def add(self, entity_type: str, entity_id: str, title: str, timestamp: str | None = None) -> str:
        key = f"{entity_type}:{entity_id}"
        if key in self._by_key:
            return self._by_key[key]
        cid = f"S{len(self.citations) + 1}"
        self.citations.append(
            {
                "id": cid,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "title": title,
                "timestamp": timestamp,
            }
        )
        self._by_key[key] = cid
        return cid


class ContextBuilder:
    def build(self, retrieval: dict[str, Any], cm: CitationManager) -> tuple[str, list[dict[str, Any]]]:
        parts: list[str] = []

        if retrieval.get("not_found"):
            parts.append(f"NOT FOUND: {retrieval['not_found']}")
            return "\n\n".join(parts), cm.citations

        if "control" in retrieval:
            c = retrieval["control"]
            c_cid = cm.add("COMMON_CONTROL", c["id"], f"Common Control {c['code']}")
            parts.append(
                f"[{c_cid}] Common Control {c['code']}\n"
                f"Statement: {c['statement']}\n"
                f"Owner: {c.get('owner_email') or 'unassigned'}\n"
                f"Overall status: {retrieval.get('status', 'UNKNOWN')}"
            )

        if "frameworks" in retrieval:
            for fw in retrieval["frameworks"]:
                f_cid = cm.add("FRAMEWORK", fw["id"], f"{fw['code']} - {fw['name']}")
                sec = f"{fw.get('section_code') or ''} {fw.get('section_title') or ''}".strip()
                parts.append(f"[{f_cid}] Framework {fw['code']} ({fw['name']}) Section {sec}: {fw['requirement_text']}")

        if "test_results" in retrieval:
            for tr in retrieval["test_results"]:
                test = tr["test"]
                t_cid = cm.add("TEST", test["id"], f"Test {test['name']}")
                results = tr["latest_results"]
                status_counts: dict[str, int] = {}
                for r in results:
                    status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
                parts.append(
                    f"[{t_cid}] Test {test['name']} results: "
                    f"{len(results)} resources; {status_counts}"
                )
                for r in results[:10]:
                    e_cid = cm.add("EVIDENCE", r["id"], f"Result for {r.get('resource_external_id') or 'N/A'}")
                    parts.append(
                        f"  [{e_cid}] {r.get('resource_external_id') or 'N/A'}: {r['status']} - {r.get('reason') or ''}"
                    )

        if "evidence" in retrieval:
            for ev in retrieval["evidence"][:15]:
                e_cid = cm.add("EVIDENCE", ev["id"], f"Evidence {ev.get('test_name', '')} {ev.get('resource_external_id') or ''}")
                parts.append(
                    f"[{e_cid}] Evidence for {ev.get('test_name', '')} / {ev.get('resource_external_id') or 'N/A'}: "
                    f"status {ev.get('test_result_status', '')}, type {ev['evidence_type']}, "
                    f"collected {ev.get('collected_at')}"
                )

        if "failing_controls" in retrieval:
            for fc in retrieval["failing_controls"]:
                cid = cm.add("COMMON_CONTROL", fc["id"], f"Failing control {fc['code']}")
                parts.append(f"[{cid}] {fc['code']} - {fc['statement']} (NEEDS_ATTENTION)")

        return "\n\n".join(parts), cm.citations


# ---------------------------------------------------------------------------
# LLM provider abstraction
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, query: str, context: str, citations: list[dict[str, Any]], retrieval: dict[str, Any]) -> tuple[str, float]:
        ...


class MockLLMProvider(LLMProvider):
    def _framework_names(self, retrieval: dict[str, Any]) -> list[str]:
        seen: set[str] = set()
        names: list[str] = []
        for fw in retrieval.get("frameworks", []):
            code = fw["code"]
            if code not in seen:
                seen.add(code)
                names.append(code)
        return names

    def generate(self, query: str, context: str, citations: list[dict[str, Any]], retrieval: dict[str, Any]) -> tuple[str, float]:
        if retrieval.get("not_found"):
            return "Insufficient supporting evidence found in tenant data.", 0.0

        if "failing_controls" in retrieval:
            controls = retrieval["failing_controls"]
            if not controls:
                return "No controls are currently failing.", 1.0
            names = ", ".join(f"{c['code']}" for c in controls[:10])
            return f"{len(controls)} control(s) currently need attention: {names}.", 0.9

        # Framework mapping: control is present but no status rollup
        if "control" in retrieval and "frameworks" in retrieval and "status" not in retrieval:
            c = retrieval["control"]
            frameworks = self._framework_names(retrieval)
            related = [r["code"] for r in retrieval.get("related_controls", [])[:10]]
            answer = f"{c['code']} is mapped to {len(frameworks)} framework(s): {', '.join(frameworks)}."
            if related:
                answer += f" Related common controls: {', '.join(related)}."
            return answer, 0.9

        if "control" in retrieval and "status" in retrieval:
            c = retrieval["control"]
            status = retrieval.get("status", "UNKNOWN")
            ok = retrieval.get("ok", 0)
            na = retrieval.get("needs_attention", 0)
            total = retrieval.get("total", 0)
            frameworks = self._framework_names(retrieval)
            answer = (
                f"{c['code']} is currently {status}. "
                f"Latest test evaluated {total} resource(s): {ok} OK, {na} need attention. "
            )
            if frameworks:
                answer += f"It maps to: {', '.join(frameworks)}. "
            failing = retrieval.get("failing_resources", [])
            if failing:
                reasons = "; ".join(
                    f"{r.get('resource_external_id') or r['id']} ({r['status']}): {r.get('reason') or 'no reason'}"
                    for r in failing[:5]
                )
                answer += f"It is failing because: {reasons}."
            return answer, 0.92

        if "evidence" in retrieval:
            ev_list = retrieval["evidence"]
            if not ev_list:
                return "No supporting evidence was found.", 0.0
            answer = f"Found {len(ev_list)} evidence record(s) for the control."
            return answer, 0.9

        if not context.strip():
            return "Insufficient supporting evidence found in tenant data.", 0.0

        return f"Based on the retrieved compliance data: {context[:500]}", 0.7


class OpenAILLMProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL")

    def _get_client(self):
        import openai
        return openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate(self, query: str, context: str, citations: list[dict[str, Any]], retrieval: dict[str, Any]) -> tuple[str, float]:
        if not self.api_key:
            return "OpenAI not configured; returning context summary.", 0.0
        client = self._get_client()
        system = (
            "You are a compliance assistant. Answer using ONLY the provided context. "
            "Do not invent evidence, statuses, or dates. Cite sources using [S1], [S2], etc. "
            "If the context is insufficient, say so."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Question: {query}\n\nContext:\n{context}"},
        ]
        try:
            resp = client.chat.completions.create(model=self.model, messages=messages, temperature=0.0)
            content = resp.choices[0].message.content or ""
            return content, 1.0
        except Exception as exc:
            return f"LLM generation failed: {exc}", 0.0


# ---------------------------------------------------------------------------
# RAG Service
# ---------------------------------------------------------------------------


class RAGService:
    def __init__(
        self,
        database: Database,
        llm: LLMProvider | None = None,
    ) -> None:
        self.db = database
        self.indexer = RAGIndexer(database)
        self.classifier = QueryClassifier()
        self.resolver = EntityResolver(database)
        self.retriever = StructuredRetriever(database)
        self.keyword = KeywordRetriever(database)
        self.context_builder = ContextBuilder()
        self.llm = llm or MockLLMProvider()

    def query(self, query_text: str, tenant_id: str, user_role: str | None = None) -> RAGResponse:
        start = time.time()

        classification = self.classifier.classify(query_text)
        resolved = self.resolver.resolve(tenant_id, classification.entities)

        retrieval = self.retriever.retrieve(classification.intent, tenant_id, resolved, query_text)

        # For general search or empty retrieval, augment with keyword chunks
        if classification.intent == "GENERAL_COMPLIANCE_SEARCH" or not retrieval:
            chunks = self.keyword.search(tenant_id, query_text, top_k=5)
            if chunks:
                retrieval = {
                    "chunks": chunks,
                    **(retrieval or {}),
                }

        cm = CitationManager()
        context, citations = self.context_builder.build(retrieval, cm)

        answer, confidence = self.llm.generate(query_text, context, citations, retrieval)

        latency_ms = int((time.time() - start) * 1000)
        self._log_query(tenant_id, query_text, classification, retrieval, latency_ms, answer)

        warnings: list[str] = []
        if not retrieval or retrieval.get("not_found"):
            warnings.append("Limited structured data available for the query.")

        return RAGResponse(
            answer=answer,
            intent=classification.intent,
            confidence=confidence,
            citations=citations,
            warnings=warnings,
            retrieved_entities=list(retrieval.values())[:20],
        )

    def index_rebuild(self, tenant_id: str) -> dict[str, int]:
        return self.indexer.rebuild(tenant_id)

    def index_entity(self, tenant_id: str, entity_type: str, entity_id: str) -> int:
        return self.indexer.index_entity(tenant_id, entity_type, entity_id)

    def health(self, tenant_id: str) -> dict[str, Any]:
        doc_count = self.db.execute(
            "SELECT COUNT(*) as c FROM rag_document WHERE tenant_id = %s", (tenant_id,)
        )[0]["c"]
        chunk_count = self.db.execute(
            "SELECT COUNT(*) as c FROM rag_chunk WHERE tenant_id = %s", (tenant_id,)
        )[0]["c"]
        return {"status": "ok", "documents": doc_count, "chunks": chunk_count}

    def _log_query(self, tenant_id: str, query_text: str, classification: QueryClassification, retrieval: dict[str, Any], latency_ms: int, answer: str) -> None:
        self.db.execute(
            """INSERT INTO rag_query_log (id, tenant_id, query, intent, entities, latency_ms, answer_status)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                str(uuid.uuid4()),
                tenant_id,
                query_text,
                classification.intent,
                _to_jsonb(classification.entities),
                latency_ms,
                "ok" if not retrieval.get("not_found") else "insufficient",
            ),
        )


# Global service instance for API import
rag = RAGService(db)
