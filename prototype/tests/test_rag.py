import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rag


def test_query_classifier_control_status():
    c = rag.QueryClassifier()
    r = c.classify("What is the current status of SOC 2 CC6.1?")
    assert r.intent == "CONTROL_STATUS"
    assert r.entities.get("framework") == "SOC2"
    assert r.entities.get("section_or_control") == "CC6.1"


def test_query_classifier_failure_explanation():
    c = rag.QueryClassifier()
    r = c.classify("Why is CC-MFA-001 failing?")
    assert r.intent == "FAILURE_EXPLANATION"
    assert r.entities.get("common_control") == "CC-MFA-001"


def test_query_classifier_framework_mapping():
    c = rag.QueryClassifier()
    r = c.classify("What other frameworks are impacted by CC6.1?")
    assert r.intent == "FRAMEWORK_MAPPING"
    assert r.entities.get("section_or_control") == "CC6.1"


def test_query_classifier_failing_controls():
    c = rag.QueryClassifier()
    r = c.classify("Which controls are currently failing?")
    assert r.intent == "FAILING_CONTROLS"


def test_query_classifier_evidence():
    c = rag.QueryClassifier()
    r = c.classify("What evidence supports CC6.1?")
    assert r.intent == "EVIDENCE_SEARCH"
    assert r.entities.get("section_or_control") == "CC6.1"


def test_citation_manager_dedupes():
    cm = rag.CitationManager()
    a = cm.add("COMMON_CONTROL", "cc-1", "MFA Control")
    b = cm.add("COMMON_CONTROL", "cc-1", "MFA Control")
    c = cm.add("TEST", "t-1", "MFA Test")
    assert a == b
    assert c == "S2"
    assert len(cm.citations) == 2


def test_context_builder_includes_citations():
    cm = rag.CitationManager()
    retrieval = {
        "control": {
            "id": "cc-1",
            "code": "CC-MFA-001",
            "statement": "Enforce MFA",
            "owner_email": "a@example.com",
        },
        "status": "NEEDS_ATTENTION",
        "frameworks": [{"id": "f1", "code": "SOC2", "name": "SOC 2", "requirement_text": "MFA", "section_code": "CC6.1", "section_title": ""}],
        "failing_resources": [],
    }
    context, citations = rag.ContextBuilder().build(retrieval, cm)
    assert "CC-MFA-001" in context
    assert "NEEDS_ATTENTION" in context
    assert len(citations) > 0


def test_mock_llm_framework_mapping():
    llm = rag.MockLLMProvider()
    retrieval = {
        "control": {"id": "cc-1", "code": "CC-MFA-001"},
        "frameworks": [
            {"id": "f1", "code": "SOC2", "name": "SOC 2", "requirement_text": "MFA", "section_code": "CC6.1"},
            {"id": "f2", "code": "ISO27001", "name": "ISO 27001", "requirement_text": "MFA", "section_code": "A.9.4.2"},
            {"id": "f3", "code": "SOC2", "name": "SOC 2", "requirement_text": "MFA", "section_code": "CC6.2"},
        ],
    }
    answer, conf = llm.generate("?", "", [], retrieval)
    assert "SOC2" in answer
    assert "ISO27001" in answer
    # Should not list SOC2 twice even though it appears twice in retrieval
    assert answer.count("SOC2") == 1
    assert conf > 0


def test_mock_llm_control_status_with_reason():
    llm = rag.MockLLMProvider()
    retrieval = {
        "control": {"id": "cc-1", "code": "CC-MFA-001"},
        "status": "NEEDS_ATTENTION",
        "total": 2,
        "ok": 1,
        "needs_attention": 1,
        "frameworks": [{"id": "f1", "code": "SOC2"}],
        "failing_resources": [
            {"id": "r1", "resource_external_id": "bob", "status": "NEEDS_ATTENTION", "reason": "MFA off"},
        ],
    }
    answer, conf = llm.generate("?", "", [], retrieval)
    assert "NEEDS_ATTENTION" in answer
    assert "bob" in answer
    assert "MFA off" in answer


def test_mock_llm_does_not_invent_when_missing():
    llm = rag.MockLLMProvider()
    answer, conf = llm.generate("?", "", [], {"not_found": "Could not resolve control"})
    assert "Insufficient" in answer
    assert conf == 0.0
