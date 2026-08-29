"""AI-assisted remediation suggestions.

Uses a real OpenAI-compatible chat completion when ``OPENAI_API_KEY`` is set,
falling back to a deterministic mock suggestion list otherwise (or if the
live call fails for any reason) so the endpoint always responds successfully.
"""

from __future__ import annotations

import os
from typing import Any

MOCK_SUGGESTIONS = [
    "Review the affected resource configuration and align it with the control requirement.",
    "Enable the missing setting or permission and verify with a follow-up test run.",
    "Rotate any exposed credentials and update evidence records.",
    "Add a compensating control or policy exception if remediation is not immediate.",
]


def _openai_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def _call_openai(prompt: str) -> list[str] | None:
    api_key = _openai_api_key()
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a compliance remediation assistant. Given a control "
                        "finding, respond with 3-5 concise, actionable remediation "
                        "steps as a plain numbered list, no preamble."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.2,
        )
        text = resp.choices[0].message.content or ""
        lines = [
            line.strip(" -0123456789.\t")
            for line in text.splitlines()
            if line.strip()
        ]
        return [line for line in lines if line] or None
    except Exception:
        return None


def suggest_remediation(
    finding: str | None,
    control_id: str | None = None,
    test_result_id: str | None = None,
) -> dict[str, Any]:
    prompt_parts = []
    if finding:
        prompt_parts.append(f"Finding: {finding}")
    if control_id:
        prompt_parts.append(f"Control ID: {control_id}")
    if test_result_id:
        prompt_parts.append(f"Test result ID: {test_result_id}")
    prompt = "\n".join(prompt_parts) or "No finding details provided."

    suggestions = _call_openai(prompt)
    if suggestions:
        return {
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "suggestions": suggestions,
            "test_result_id": test_result_id,
            "control_id": control_id,
            "finding": finding,
            "mocked": False,
        }
    return {
        "model": "mock-llm",
        "suggestions": MOCK_SUGGESTIONS,
        "test_result_id": test_result_id,
        "control_id": control_id,
        "finding": finding,
        "mocked": True,
    }
