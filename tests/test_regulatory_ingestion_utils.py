from datetime import timezone

from arkashri.models import RegulatorySource, RegulatorySourceType
from arkashri.services.regulatory_ingestion import (
    _extract_path,
    _parse_datetime,
    _build_doc_key,
    fetch_source_items,
)


def test_extract_path_reads_nested_payload() -> None:
    payload = {"outer": {"inner": [{"id": 1}]}}
    assert _extract_path(payload, "outer.inner") == [{"id": 1}]
    assert _extract_path(payload, "outer.missing") is None


def test_parse_datetime_supports_iso_and_rss_date() -> None:
    iso_dt = _parse_datetime("2026-02-24T01:00:00Z")
    rss_dt = _parse_datetime("Tue, 24 Feb 2026 01:00:00 GMT")

    assert iso_dt is not None
    assert rss_dt is not None
    assert iso_dt.tzinfo == timezone.utc
    assert rss_dt.tzinfo is not None


def test_manual_source_returns_no_items() -> None:
    source = RegulatorySource(
        source_key="MANUAL_SOURCE",
        jurisdiction="IN",
        authority="Manual",
        source_type=RegulatorySourceType.MANUAL,
        endpoint="manual://none",
        parser_config={},
        is_active=True,
    )
    assert fetch_source_items(source) == []


def test_build_doc_key_sanitizes_text() -> None:
    doc = type(
        "Doc",
        (),
        {"authority": "ICAI / Standards", "external_id": "NOTIF-44AB/2026", "id": 10},
    )()
    key = _build_doc_key(doc)  # type: ignore[arg-type]
    assert key.startswith("icai_standards_notif_44ab_2026")
