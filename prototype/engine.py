from typing import Any

_OK = "OK"
_NEEDS_ATTENTION = "NEEDS_ATTENTION"
_INVALID = "INVALID"


def _get_value(data: dict[str, Any], field: str) -> Any:
    if field in data:
        return data[field]
    # support one level of nesting for common patterns
    if "." in field:
        current = data
        for part in field.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current
    return None


def _is_truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _matches_eq(data: dict[str, Any], field: str, expected: Any) -> tuple[bool, str]:
    actual = _get_value(data, field)
    if actual is None:
        return False, f"missing field '{field}'"
    if actual == expected:
        return True, f"'{field}' is {expected}"
    return False, f"'{field}' is {actual}, expected {expected}"


def _matches_in(data: dict[str, Any], field: str, expected: Any) -> tuple[bool, str]:
    actual = _get_value(data, field)
    if actual is None:
        return False, f"missing field '{field}'"

    if isinstance(expected, list):
        if isinstance(actual, list):
            hits = [v for v in actual if v in expected]
            if hits:
                return True, f"'{field}' contains {hits}"
            return False, f"'{field}' {actual} does not include any of {expected}"
        if actual in expected:
            return True, f"'{field}' is {actual}"
        return False, f"'{field}' is {actual}, expected one of {expected}"

    # expected is a scalar
    if isinstance(actual, list):
        if expected in actual:
            return True, f"'{field}' contains {expected}"
        return False, f"'{field}' {actual} does not contain {expected}"
    return actual == expected, f"'{field}' is {actual}"


def _matches_gt_lt(
    data: dict[str, Any], field: str, expected: Any, op: str
) -> tuple[bool, str]:
    actual = _get_value(data, field)
    if actual is None:
        return False, f"missing field '{field}'"
    try:
        if op == "gt":
            ok = actual > expected
            desc = f"'{field}' ({actual}) > {expected}"
        elif op == "lt":
            ok = actual < expected
            desc = f"'{field}' ({actual}) < {expected}"
        elif op == "gte":
            ok = actual >= expected
            desc = f"'{field}' ({actual}) >= {expected}"
        else:
            ok = actual <= expected
            desc = f"'{field}' ({actual}) <= {expected}"
        return ok, desc
    except TypeError:
        return False, f"'{field}' type mismatch: {actual} vs {expected}"


def evaluate_rule(rule: dict[str, Any], data: dict[str, Any]) -> tuple[str, str]:
    """Evaluate a declarative rule against a resource data dict.

    Returns (status, reason) where status is one of OK/NEEDS_ATTENTION/INVALID.
    """
    if "and" in rule:
        return _evaluate_and(rule["and"], data)
    if "or" in rule:
        return _evaluate_or(rule["or"], data)

    field = rule.get("field")
    operator = rule.get("operator")
    value = rule.get("value")

    if not field or not operator:
        return _INVALID, "rule missing field or operator"

    if operator == "exists":
        actual = _get_value(data, field)
        if _is_truthy(actual):
            return _OK, f"'{field}' present"
        return _NEEDS_ATTENTION, f"'{field}' is missing or empty"

    if operator == "eq":
        ok, reason = _matches_eq(data, field, value)
        return (_OK if ok else _NEEDS_ATTENTION), reason

    if operator == "ne":
        ok, reason = _matches_eq(data, field, value)
        return (_NEEDS_ATTENTION if ok else _OK), reason

    if operator == "in":
        ok, reason = _matches_in(data, field, value)
        return (_OK if ok else _NEEDS_ATTENTION), reason

    if operator == "not_in":
        ok, reason = _matches_in(data, field, value)
        return (_NEEDS_ATTENTION if ok else _OK), reason

    if operator in ("gt", "lt", "gte", "lte"):
        ok, reason = _matches_gt_lt(data, field, value, operator)
        return (_OK if ok else _NEEDS_ATTENTION), reason

    return _INVALID, f"unknown operator '{operator}'"


def _evaluate_and(parts: list[dict[str, Any]], data: dict[str, Any]) -> tuple[str, str]:
    if not parts:
        return _OK, "empty AND"

    reasons: list[str] = []
    worst = _OK
    for part in parts:
        status, reason = evaluate_rule(part, data)
        if status == _INVALID:
            worst = _INVALID
            reasons.append(reason)
            continue
        if status == _NEEDS_ATTENTION:
            worst = _NEEDS_ATTENTION
        reasons.append(reason)

    if worst == _NEEDS_ATTENTION:
        return _NEEDS_ATTENTION, "; ".join(reasons)
    if worst == _INVALID:
        return _INVALID, "; ".join(reasons)
    return _OK, "; ".join(reasons)


def _evaluate_or(parts: list[dict[str, Any]], data: dict[str, Any]) -> tuple[str, str]:
    if not parts:
        return _OK, "empty OR"

    reasons: list[str] = []
    all_needs_attention = True
    for part in parts:
        status, reason = evaluate_rule(part, data)
        if status == _OK:
            return _OK, reason
        reasons.append(reason)
        if status != _NEEDS_ATTENTION:
            all_needs_attention = False

    if all_needs_attention:
        return _NEEDS_ATTENTION, "; ".join(reasons)
    return _INVALID, "; ".join(reasons)
