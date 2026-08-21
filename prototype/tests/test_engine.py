import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine


def test_evaluate_eq_true():
    status, reason = engine.evaluate_rule(
        {"field": "mfa_enabled", "operator": "eq", "value": True},
        {"mfa_enabled": True},
    )
    assert status == "OK"


def test_evaluate_eq_false():
    status, reason = engine.evaluate_rule(
        {"field": "mfa_enabled", "operator": "eq", "value": True},
        {"mfa_enabled": False},
    )
    assert status == "NEEDS_ATTENTION"


def test_evaluate_missing_field():
    status, reason = engine.evaluate_rule(
        {"field": "mfa_enabled", "operator": "eq", "value": True},
        {},
    )
    assert status == "NEEDS_ATTENTION"


def test_evaluate_in_list():
    status, reason = engine.evaluate_rule(
        {"field": "env", "operator": "in", "value": ["prod", "staging"]},
        {"env": "prod"},
    )
    assert status == "OK"


def test_evaluate_gt():
    status, reason = engine.evaluate_rule(
        {"field": "count", "operator": "gt", "value": 5},
        {"count": 10},
    )
    assert status == "OK"


def test_evaluate_and():
    status, reason = engine.evaluate_rule(
        {
            "and": [
                {"field": "mfa_enabled", "operator": "eq", "value": True},
                {"field": "encrypted", "operator": "eq", "value": True},
            ]
        },
        {"mfa_enabled": True, "encrypted": True},
    )
    assert status == "OK"


def test_evaluate_or():
    status, reason = engine.evaluate_rule(
        {
            "or": [
                {"field": "mfa_enabled", "operator": "eq", "value": True},
                {"field": "encrypted", "operator": "eq", "value": True},
            ]
        },
        {"mfa_enabled": False, "encrypted": True},
    )
    assert status == "OK"


def test_evaluate_exists():
    status, reason = engine.evaluate_rule(
        {"field": "owner", "operator": "exists"},
        {"owner": "admin"},
    )
    assert status == "OK"


def test_evaluate_nested_field():
    status, reason = engine.evaluate_rule(
        {"field": "config.public", "operator": "eq", "value": False},
        {"config": {"public": False}},
    )
    assert status == "OK"
