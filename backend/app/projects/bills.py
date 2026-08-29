from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from pydantic import ValidationError

from .models import EvidenceField, EvidenceKind, UtilityBillDraft


KWH_PATTERN = re.compile(
    r"(?:total\s+(?:electricity\s+)?(?:usage|consumption)|electricity\s+usage|consumption)"
    r"[^\d]{0,40}([\d,]+(?:\.\d+)?)\s*kwh",
    re.IGNORECASE,
)
COST_PATTERN = re.compile(
    r"(?:total\s+(?:amount|charges)|amount\s+due|electricity\s+charges)"
    r"[^\d]{0,40}(?:sgd|s\$|\$)?\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"\b(20\d{2}[-/]\d{2}[-/]\d{2})\b")


def _number(value: str | int | float) -> float:
    return float(str(value).replace(",", "").replace("S$", "").replace("$", "").strip())


def _normalise_date(value: str) -> str:
    return value.replace("/", "-")


def _from_mapping(payload: dict, filename: str) -> UtilityBillDraft:
    start = payload.get("period_start") or payload.get("start_date")
    end = payload.get("period_end") or payload.get("end_date")
    kwh = payload.get("total_kwh") or payload.get("consumption_kwh")
    cost = payload.get("total_cost_sgd") or payload.get("amount_sgd")
    if not all([start, end, kwh, cost]):
        raise ValueError("Bill must include period dates, total kWh, and total cost in SGD.")
    return UtilityBillDraft(
        filename=filename,
        period_start=_normalise_date(str(start)),
        period_end=_normalise_date(str(end)),
        total_kwh=_number(kwh),
        total_cost_sgd=_number(cost),
        account_label=str(payload.get("account_label", "Store electricity account")),
        evidence=_evidence(filename),
    )


def _evidence(filename: str) -> list[EvidenceField]:
    return [
        EvidenceField(
            field="total_kwh",
            value="extracted",
            unit="kWh",
            kind=EvidenceKind.MEASURED,
            source=filename,
            confidence=0.82,
        ),
        EvidenceField(
            field="total_cost_sgd",
            value="extracted",
            unit="SGD",
            kind=EvidenceKind.MEASURED,
            source=filename,
            confidence=0.82,
        ),
    ]


def parse_bill_bytes(filename: str, content: bytes) -> UtilityBillDraft:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError

        try:
            reader = PdfReader(io.BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except PyPdfError as exc:
            raise ValueError("The PDF utility bill could not be read.") from exc
        return _from_text(text, filename)
    decoded = content.decode("utf-8-sig", errors="replace")
    if suffix == ".json":
        try:
            return _from_mapping(json.loads(decoded), filename)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("The JSON utility bill could not be parsed.") from exc
    if suffix == ".csv":
        rows = list(csv.DictReader(io.StringIO(decoded)))
        if not rows:
            raise ValueError("The CSV utility bill has no data rows.")
        return _from_mapping(rows[0], filename)
    if suffix in {".txt", ""}:
        return _from_text(decoded, filename)
    raise ValueError("Supported bill formats are PDF, JSON, CSV, and TXT.")


def _from_text(text: str, filename: str) -> UtilityBillDraft:
    kwh_match = KWH_PATTERN.search(text)
    cost_match = COST_PATTERN.search(text)
    dates = DATE_PATTERN.findall(text)
    if not kwh_match or not cost_match or len(dates) < 2:
        raise ValueError(
            "Could not find two dates, total electricity consumption in kWh, and total cost."
        )
    return UtilityBillDraft(
        filename=filename,
        period_start=_normalise_date(dates[0]),
        period_end=_normalise_date(dates[1]),
        total_kwh=_number(kwh_match.group(1)),
        total_cost_sgd=_number(cost_match.group(1)),
        evidence=_evidence(filename),
    )
