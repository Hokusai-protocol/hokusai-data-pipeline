"""Regex-based PII patterns used by the PII detector."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PIIPattern:
    """Simple wrapper for a named regular expression pattern."""

    entity_type: str
    pattern: re.Pattern[str]
    severity: str


PII_PATTERNS: list[PIIPattern] = [
    PIIPattern(
        entity_type="EMAIL",
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        severity="high",
    ),
    PIIPattern(
        entity_type="PHONE",
        pattern=re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        severity="high",
    ),
    PIIPattern(
        entity_type="SSN",
        pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        severity="critical",
    ),
    PIIPattern(
        entity_type="CREDIT_CARD",
        pattern=re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
        severity="critical",
    ),
    PIIPattern(
        entity_type="IP_ADDRESS",
        pattern=re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        severity="medium",
    ),
    PIIPattern(
        entity_type="DATE_OF_BIRTH",
        pattern=re.compile(r"\b(?:19|20)\d{2}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])\b"),
        severity="medium",
    ),
    PIIPattern(
        entity_type="ADDRESS",
        pattern=re.compile(
            r"\b\d{1,6}\s+[A-Za-z0-9.\-\s]+\s(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd)\b",
            re.IGNORECASE,
        ),
        severity="medium",
    ),
]
