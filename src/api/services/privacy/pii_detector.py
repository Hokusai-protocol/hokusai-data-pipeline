"""PII detection service based on spaCy NER plus deterministic regex patterns."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .pii_patterns import PII_PATTERNS

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

try:
    import spacy
except ImportError:  # pragma: no cover
    spacy = None


SPACY_ENTITY_MAP = {
    "PERSON": "PERSON",
    "GPE": "ADDRESS",
    "LOC": "ADDRESS",
}


@dataclass
class PIIFinding:
    """Represents one detected PII element without storing sensitive content."""

    entity_type: str
    start: int
    end: int
    confidence: float
    severity: str
    source: str


@dataclass
class PIIScanResult:
    """Aggregate results for a scan request."""

    findings: list[PIIFinding]
    total_findings: int
    by_entity_type: dict[str, int]
    severity: str
    scanned_records: int

    def to_dict(self) -> dict[str, Any]:
        """Convert structured result into JSON-safe dictionary."""
        return {
            "findings": [asdict(item) for item in self.findings],
            "total_findings": self.total_findings,
            "by_entity_type": self.by_entity_type,
            "severity": self.severity,
            "scanned_records": self.scanned_records,
        }


@lru_cache(maxsize=1)
def _load_spacy_model():
    if spacy is None:
        return None
    try:
        return spacy.load("en_core_web_sm")
    except Exception:  # pragma: no cover
        return None


class PIIDetector:
    """Detects PII from strings, dataframe data, and local files."""

    def __init__(self) -> None:
        self._nlp = _load_spacy_model()

    def scan_text(self, text: str) -> list[PIIFinding]:
        """Scan one text input and return findings."""
        findings: list[PIIFinding] = []

        for pii_pattern in PII_PATTERNS:
            for match in pii_pattern.pattern.finditer(text):
                findings.append(
                    PIIFinding(
                        entity_type=pii_pattern.entity_type,
                        start=match.start(),
                        end=match.end(),
                        confidence=1.0,
                        severity=pii_pattern.severity,
                        source="regex",
                    )
                )

        if self._nlp is not None:
            doc = self._nlp(text)
            for ent in doc.ents:
                mapped = SPACY_ENTITY_MAP.get(ent.label_)
                if not mapped:
                    continue
                findings.append(
                    PIIFinding(
                        entity_type=mapped,
                        start=ent.start_char,
                        end=ent.end_char,
                        confidence=float(getattr(ent, "kb_id", 0) or 0.65),
                        severity="high" if mapped == "PERSON" else "medium",
                        source="spacy",
                    )
                )

        return self._dedupe(findings)

    def scan_text_result(self, text: str) -> PIIScanResult:
        """Scan text and return aggregate result wrapper."""
        findings = self.scan_text(text)
        return self._as_scan_result(findings, scanned_records=1)

    def scan_dataframe(self, df: pd.DataFrame) -> PIIScanResult:
        """Scan all string-like values in a pandas dataframe."""
        findings: list[PIIFinding] = []
        scanned_records = len(df.index)
        for column in df.columns:
            series = df[column]
            if getattr(series, "dtype", None) is None:
                continue
            if str(series.dtype) not in {"object", "string"}:
                continue
            for value in series.dropna().astype(str):
                findings.extend(self.scan_text(value))
        return self._as_scan_result(findings, scanned_records=scanned_records)

    def scan_file(self, file_path: str) -> PIIScanResult:
        """Scan a CSV, JSON, or JSONL file for PII."""
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".csv":
            return self._scan_csv(path)
        if suffix == ".json":
            return self._scan_json(path)
        if suffix == ".jsonl":
            return self._scan_jsonl(path)
        raise ValueError(f"Unsupported file type: {suffix}")

    def _scan_csv(self, path: Path) -> PIIScanResult:
        findings: list[PIIFinding] = []
        scanned_records = 0
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                scanned_records += 1
                for value in row.values():
                    if value:
                        findings.extend(self.scan_text(str(value)))
        return self._as_scan_result(findings, scanned_records)

    def _scan_json(self, path: Path) -> PIIScanResult:
        findings: list[PIIFinding] = []
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        records: list[dict[str, Any]]
        if isinstance(payload, list):
            records = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            records = [payload]
        else:
            records = []

        for row in records:
            for value in row.values():
                if isinstance(value, str):
                    findings.extend(self.scan_text(value))
        return self._as_scan_result(findings, scanned_records=len(records))

    def _scan_jsonl(self, path: Path) -> PIIScanResult:
        findings: list[PIIFinding] = []
        scanned_records = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                scanned_records += 1
                record = json.loads(line)
                if isinstance(record, dict):
                    for value in record.values():
                        if isinstance(value, str):
                            findings.extend(self.scan_text(value))
        return self._as_scan_result(findings, scanned_records)

    @staticmethod
    def _dedupe(findings: list[PIIFinding]) -> list[PIIFinding]:
        seen: set[tuple[str, int, int]] = set()
        result: list[PIIFinding] = []
        for finding in findings:
            key = (finding.entity_type, finding.start, finding.end)
            if key in seen:
                continue
            seen.add(key)
            result.append(finding)
        return result

    def _as_scan_result(self, findings: list[PIIFinding], scanned_records: int) -> PIIScanResult:
        by_type: dict[str, int] = {}
        severities: set[str] = set()
        for finding in findings:
            by_type[finding.entity_type] = by_type.get(finding.entity_type, 0) + 1
            severities.add(finding.severity)

        if "critical" in severities:
            overall_severity = "critical"
        elif "high" in severities:
            overall_severity = "high"
        elif "medium" in severities:
            overall_severity = "medium"
        else:
            overall_severity = "none"

        return PIIScanResult(
            findings=findings,
            total_findings=len(findings),
            by_entity_type=by_type,
            severity=overall_severity,
            scanned_records=scanned_records,
        )
