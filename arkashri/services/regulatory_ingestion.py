# pyre-ignore-all-errors
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from arkashri.models import (
    AlertSeverity,
    AlertType,
    IngestRunStatus,
    KnowledgeDocument,
    KnowledgeSourceType,
    RegulatoryDocument,
    RegulatoryIngestRun,
    RegulatorySource,
    RegulatorySourceType,
    RegulatorySyncAlert,
    RegulatorySyncSchedule,
    ScheduleCadence,
    ScheduleState,
)
from arkashri.services.canonical import hash_object
from arkashri.services.rag import create_knowledge_document


@dataclass
class RegulatoryItem:
    external_id: str
    title: str
    summary: str | None
    document_url: str
    published_on: datetime | None
    content_text: str
    metadata_json: dict[str, Any]


@dataclass
class RegulatorySchedulerTick:
    evaluated_at: datetime
    processed_schedules: int = 0
    successful_runs: int = 0
    retry_runs: int = 0
    failed_runs: int = 0
    alerts_created: int = 0
    run_ids: list[uuid.UUID] | None = None
    alert_ids: list[uuid.UUID] | None = None


class _AnchorExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._active_href: str | None = None
        self._text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attributes = {key.lower(): value for key, value in attrs}
        href = attributes.get("href")
        if not href:
            return
        self._active_href = href.strip()
        self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._active_href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        href = self._active_href
        if tag.lower() != "a" or href is None:
            return
        title = _clean_text(" ".join(self._text_parts))
        if title:
            self.links.append((href, title))
        self._active_href = None
        self._text_parts = []


async def bootstrap_regulatory_sources(session: AsyncSession) -> tuple[int, int]:
    defaults: list[dict[str, Any]] = [
        {
            "source_key": "US_FEDERAL_REGISTER_GENERAL",
            "jurisdiction": "US",
            "authority": "Federal Register",
            "source_type": RegulatorySourceType.API_JSON,
            "endpoint": "https://www.federalregister.gov/api/v1/documents.json",
            "parser_config": {
                "query": {
                    "per_page": "30",
                    "order": "newest",
                },
                "results_path": "results",
                "id_field": "document_number",
                "title_field": "title",
                "summary_field": "abstract",
                "url_field": "html_url",
                "date_field": "publication_date",
            },
        },
        {
            "source_key": "IN_MCA_NOTIFICATIONS",
            "jurisdiction": "IN",
            "authority": "MCA",
            "source_type": RegulatorySourceType.HTML,
            "endpoint": "https://www.mca.gov.in/content/mca/global/en/acts-rules/notifications.html",
            "parser_config": {
                "base_url": "https://www.mca.gov.in",
                "include_patterns": [
                    r"notification",
                    r"circular",
                    r"rule",
                    r"order",
                    r"amend",
                ],
                "exclude_patterns": [
                    r"archive",
                    r"contact",
                    r"help",
                    r"javascript:",
                ],
            },
        },
        {
            "source_key": "IN_CBIC_NOTIFICATIONS",
            "jurisdiction": "IN",
            "authority": "CBIC",
            "source_type": RegulatorySourceType.HTML,
            "endpoint": "https://www.cbic.gov.in/resources/htdocs-cbec/deptt_offcr/cx-act/cx-act-listing.htm",
            "parser_config": {
                "base_url": "https://www.cbic.gov.in",
                "include_patterns": [
                    r"notification",
                    r"circular",
                    r"instruction",
                    r"regulation",
                    r"gst",
                    r"custom",
                    r"excise",
                ],
                "exclude_patterns": [
                    r"archive",
                    r"contact",
                    r"help",
                    r"javascript:",
                ],
            },
        },
        {
            "source_key": "EU_EURLEX_LEGISLATION_RSS",
            "jurisdiction": "EU",
            "authority": "EUR-Lex",
            "source_type": RegulatorySourceType.RSS,
            "endpoint": "https://eur-lex.europa.eu/rss.html?legislation=true",
            "parser_config": {
                "feed_url_patterns": [
                    r"rss",
                    r"legislation",
                ],
            },
        },
    ]

    inserted: int = 0
    existing: int = 0
    for item in defaults:
        source = await session.scalar(select(RegulatorySource).where(RegulatorySource.source_key == item["source_key"]))
        if source is not None:
            existing += 1
            continue
        session.add(RegulatorySource(**item))
        inserted += 1

    await session.flush()
    return inserted, existing


async def ingest_source(
    session: AsyncSession,
    *,
    source: RegulatorySource,
    max_items: int = 50,
    timeout_seconds: int = 30,
    raise_on_error: bool = True,
) -> RegulatoryIngestRun:
    run = RegulatoryIngestRun(source_id=source.id, status=IngestRunStatus.STARTED)
    session.add(run)
    await session.flush()

    try:
        items = fetch_source_items(source, max_items=max_items, timeout_seconds=timeout_seconds)
        run.fetched_count = len(items)

        inserted_count: int = 0
        for item in items:
            existing_doc = await session.scalar(
                select(RegulatoryDocument).where(
                    RegulatoryDocument.source_id == source.id,
                    RegulatoryDocument.external_id == item.external_id,
                )
            )
            if existing_doc is None:
                pub_date = item.published_on
                session.add(
                    RegulatoryDocument(
                        source_id=source.id,
                        jurisdiction=source.jurisdiction,
                        authority=source.authority,
                        external_id=item.external_id,
                        title=item.title,
                        summary=item.summary,
                        document_url=item.document_url,
                        published_on=pub_date,
                        content_text=item.content_text,
                        content_hash=hash_object(
                            {
                                "external_id": item.external_id,
                                "title": item.title,
                                "summary": item.summary,
                                "document_url": item.document_url,
                                "published_on": pub_date.isoformat() if pub_date else None,
                                "content_text": item.content_text,
                            }
                        ),
                        metadata_json=item.metadata_json,
                    )
                )
                inserted_count += 1
            else:
                assert existing_doc is not None
                pub_date = item.published_on
                existing_doc.title = item.title
                existing_doc.summary = item.summary
                existing_doc.document_url = item.document_url
                existing_doc.published_on = pub_date
                existing_doc.content_text = item.content_text
                existing_doc.content_hash = hash_object(
                    {
                        "external_id": item.external_id,
                        "title": item.title,
                        "summary": item.summary,
                        "document_url": item.document_url,
                        "published_on": pub_date.isoformat() if pub_date else None,
                        "content_text": item.content_text,
                    }
                )
                existing_doc.metadata_json = item.metadata_json
                session.add(existing_doc)

        now = datetime.now(timezone.utc)
        source.last_success_at = now
        run.inserted_count = inserted_count
        run.status = IngestRunStatus.SUCCESS
        run.ended_at = now
        session.add(source)
        session.add(run)
        await session.flush()
        return run
    except Exception as exc:
        run.status = IngestRunStatus.FAILED
        run.error_message = str(exc)[:4000]  # type: ignore
        run.ended_at = datetime.now(timezone.utc)
        session.add(run)
        await session.flush()
        if raise_on_error:
            raise
        return run


async def upsert_sync_schedule(
    session: AsyncSession,
    *,
    source: RegulatorySource,
    cadence: ScheduleCadence,
    interval_hours: int = 1,
    daily_hour: int | None = None,
    daily_minute: int = 0,
    max_retries: int = 3,
    backoff_base_seconds: int = 60,
    is_active: bool = True,
    run_immediately: bool = True,
    now: datetime | None = None,
) -> RegulatorySyncSchedule:
    if interval_hours < 1:
        raise ValueError("interval_hours must be >= 1")
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    if backoff_base_seconds < 1:
        raise ValueError("backoff_base_seconds must be >= 1")
    if cadence == ScheduleCadence.DAILY and daily_hour is None:
        raise ValueError("daily_hour is required when cadence is DAILY")
    if daily_hour is not None and not 0 <= daily_hour <= 23:
        raise ValueError("daily_hour must be between 0 and 23")
    if not 0 <= daily_minute <= 59:
        raise ValueError("daily_minute must be between 0 and 59")

    current_time = _ensure_utc(now or datetime.now(timezone.utc))
    schedule = await session.scalar(select(RegulatorySyncSchedule).where(RegulatorySyncSchedule.source_id == source.id))

    if schedule is None:
        schedule = RegulatorySyncSchedule(
            source_id=source.id,
            cadence=cadence,
            interval_hours=interval_hours,
            daily_hour=daily_hour,
            daily_minute=daily_minute,
            max_retries=max_retries,
            backoff_base_seconds=backoff_base_seconds,
            is_active=is_active,
            next_run_at=(
                current_time
                if run_immediately
                else compute_next_cadence_run(
                    cadence=cadence,
                    interval_hours=interval_hours,
                    daily_hour=daily_hour,
                    daily_minute=daily_minute,
                    from_time=current_time,
                )
            ),
            last_status=ScheduleState.IDLE,
            retry_count=0,
            consecutive_failures=0,
        )
        session.add(schedule)
        await session.flush()
        return schedule

    assert schedule is not None
    schedule.cadence = cadence
    schedule.interval_hours = interval_hours
    schedule.daily_hour = daily_hour
    schedule.daily_minute = daily_minute
    schedule.max_retries = max_retries
    schedule.backoff_base_seconds = backoff_base_seconds
    schedule.is_active = is_active

    if run_immediately and is_active:
        schedule.next_run_at = current_time
    elif is_active and (schedule.next_run_at is None or schedule.next_run_at <= current_time):
        schedule.next_run_at = compute_next_cadence_run(
            cadence=cadence,
            interval_hours=interval_hours,
            daily_hour=daily_hour,
            daily_minute=daily_minute,
            from_time=current_time,
        )

    if not is_active:
        schedule.retry_count = 0
        schedule.consecutive_failures = 0
        if schedule.last_status != ScheduleState.SUCCESS:
            schedule.last_status = ScheduleState.IDLE

    session.add(schedule)
    await session.flush()
    return schedule


async def run_due_schedules(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 20,
    max_items: int = 50,
    timeout_seconds: int = 30,
) -> RegulatorySchedulerTick:
    current_time = _ensure_utc(now or datetime.now(timezone.utc))
    tick = RegulatorySchedulerTick(
        evaluated_at=current_time,
        run_ids=[],
        alert_ids=[],
    )

    result = await session.scalars(
        select(RegulatorySyncSchedule)
        .options(joinedload(RegulatorySyncSchedule.source))
        .join(RegulatorySource, RegulatorySource.id == RegulatorySyncSchedule.source_id)
        .where(
            RegulatorySyncSchedule.is_active.is_(True),
            RegulatorySource.is_active.is_(True),
            RegulatorySyncSchedule.next_run_at <= current_time,
        )
        .order_by(RegulatorySyncSchedule.next_run_at.asc(), RegulatorySyncSchedule.id.asc())
        .limit(limit)
    )
    schedules = list(result)

    for schedule in schedules:
        run, alerts = await execute_sync_schedule(
            session,
            schedule=schedule,
            max_items=max_items,
            timeout_seconds=timeout_seconds,
            now=current_time,
        )

        tick.processed_schedules += 1
        if tick.run_ids is not None:
            rids = tick.run_ids
            rids.append(run.id)
        for alert in alerts:
            if tick.alert_ids is not None:
                aids = tick.alert_ids
                aids.append(alert.id)

        if run.status == IngestRunStatus.SUCCESS:
            tick.successful_runs += 1
        elif schedule.last_status == ScheduleState.RETRY:
            tick.retry_runs += 1
        else:
            tick.failed_runs += 1

        tick.alerts_created += len(alerts)

    return tick


async def execute_sync_schedule(
    session: AsyncSession,
    *,
    schedule: RegulatorySyncSchedule,
    max_items: int = 50,
    timeout_seconds: int = 30,
    now: datetime | None = None,
) -> tuple[RegulatoryIngestRun, list[RegulatorySyncAlert]]:
    source = schedule.source or await session.scalar(select(RegulatorySource).where(RegulatorySource.id == schedule.source_id))
    assert source is not None
    if source is None:
        raise ValueError(f"Schedule {schedule.id} references missing source {schedule.source_id}")

    current_time = _ensure_utc(now or datetime.now(timezone.utc))
    run = await ingest_source(
        session,
        source=source,
        max_items=max_items,
        timeout_seconds=timeout_seconds,
        raise_on_error=False,
    )

    alerts: list[RegulatorySyncAlert] = []
    schedule.last_run_at = current_time

    if run.status == IngestRunStatus.SUCCESS:
        recovered = schedule.consecutive_failures > 0 or schedule.last_status in {
            ScheduleState.RETRY,
            ScheduleState.FAILED,
        }
        schedule.last_status = ScheduleState.SUCCESS
        schedule.retry_count = 0
        schedule.consecutive_failures = 0
        schedule.next_run_at = compute_next_cadence_run(
            cadence=schedule.cadence,
            interval_hours=schedule.interval_hours,
            daily_hour=schedule.daily_hour,
            daily_minute=schedule.daily_minute,
            from_time=current_time,
        )
        if recovered:
            alerts.append(
                await _create_sync_alert(
                    session,
                    source=source,
                    schedule=schedule,
                    ingest_run=run,
                    severity=AlertSeverity.INFO,
                    alert_type=AlertType.SYNC_RECOVERY,
                    message=(
                        f"Regulatory sync recovered for source {source.source_key}. "
                        f"Run {run.id} fetched={run.fetched_count} inserted={run.inserted_count}."
                    ),
                )
            )
    else:
        schedule.consecutive_failures += 1
        error_message = run.error_message or "Unknown ingest failure"

        if schedule.retry_count < schedule.max_retries:
            schedule.retry_count += 1
            schedule.last_status = ScheduleState.RETRY
            schedule.next_run_at = compute_retry_run(
                retry_count=schedule.retry_count,
                backoff_base_seconds=schedule.backoff_base_seconds,
                from_time=current_time,
            )
            alerts.append(
                await _create_sync_alert(
                    session,
                    source=source,
                    schedule=schedule,
                    ingest_run=run,
                    severity=AlertSeverity.WARNING,
                    alert_type=AlertType.SYNC_FAILURE,
                    message=(
                        f"Regulatory sync failed for source {source.source_key}. "
                        f"Retry {schedule.retry_count}/{schedule.max_retries}. Error: {error_message}"
                    ),
                )
            )
        else:
            schedule.last_status = ScheduleState.FAILED
            schedule.retry_count = 0
            schedule.next_run_at = compute_next_cadence_run(
                cadence=schedule.cadence,
                interval_hours=schedule.interval_hours,
                daily_hour=schedule.daily_hour,
                daily_minute=schedule.daily_minute,
                from_time=current_time,
            )
            alerts.append(
                await _create_sync_alert(
                    session,
                    source=source,
                    schedule=schedule,
                    ingest_run=run,
                    severity=AlertSeverity.CRITICAL,
                    alert_type=AlertType.SYNC_FAILURE,
                    message=(
                        f"Regulatory sync failed for source {source.source_key} and retries exhausted. "
                        f"Error: {error_message}"
                    ),
                )
            )

    session.add(schedule)
    await session.flush()
    return run, alerts


def compute_next_cadence_run(
    *,
    cadence: ScheduleCadence,
    interval_hours: int,
    daily_hour: int | None,
    daily_minute: int,
    from_time: datetime,
) -> datetime:
    normalized = _ensure_utc(from_time)
    if cadence == ScheduleCadence.HOURLY:
        return normalized + timedelta(hours=max(interval_hours, 1))

    if daily_hour is None:
        raise ValueError("daily_hour is required for daily cadence")
    run_at = normalized.replace(hour=daily_hour, minute=daily_minute, second=0, microsecond=0)
    if run_at <= normalized:
        run_at += timedelta(days=1)
    return run_at


def compute_retry_run(
    *,
    retry_count: int,
    backoff_base_seconds: int,
    from_time: datetime,
) -> datetime:
    normalized = _ensure_utc(from_time)
    backoff_multiplier = 2 ** max(retry_count - 1, 0)
    delay_seconds = max(backoff_base_seconds, 1) * backoff_multiplier
    return normalized + timedelta(seconds=delay_seconds)


async def _create_sync_alert(
    session: AsyncSession,
    *,
    source: RegulatorySource,
    schedule: RegulatorySyncSchedule | None,
    ingest_run: RegulatoryIngestRun | None,
    severity: AlertSeverity,
    alert_type: AlertType,
    message: str,
) -> RegulatorySyncAlert:
    alert = RegulatorySyncAlert(
        source_id=source.id,
        schedule_id=schedule.id if schedule is not None else None,
        ingest_run_id=ingest_run.id if ingest_run is not None else None,
        severity=severity,
        alert_type=alert_type,
        message=message[:4000],  # type: ignore
        is_acknowledged=False,
    )
    session.add(alert)
    await session.flush()
    return alert


async def ingest_jurisdiction_sources(
    session: AsyncSession,
    *,
    jurisdiction: str,
    max_items: int = 50,
    timeout_seconds: int = 30,
) -> list[RegulatoryIngestRun]:
    result = await session.scalars(
        select(RegulatorySource)
        .where(RegulatorySource.jurisdiction == jurisdiction, RegulatorySource.is_active.is_(True))
        .order_by(RegulatorySource.id.asc())
    )
    sources = list(result)
    runs: list[RegulatoryIngestRun] = []
    for source in sources:
        run = await ingest_source(
            session,
            source=source,
            max_items=max_items,
            timeout_seconds=timeout_seconds,
            raise_on_error=False,
        )
        runs.append(run)
    return runs


async def promote_regulatory_document(
    session: AsyncSession,
    *,
    regulatory_document: RegulatoryDocument,
    source_type: KnowledgeSourceType = KnowledgeSourceType.LAW,
) -> int:
    if regulatory_document.is_promoted and regulatory_document.promoted_knowledge_doc_id:
        return regulatory_document.promoted_knowledge_doc_id

    doc_key = _build_doc_key(regulatory_document)
    max_version = int(
        await session.scalar(
            select(func.coalesce(func.max(KnowledgeDocument.version), 0)).where(
                KnowledgeDocument.document_key == doc_key,
                KnowledgeDocument.jurisdiction == regulatory_document.jurisdiction,
            )
        )
        or 0
    )
    next_version = max(max_version + 1, 1)

    content_text = regulatory_document.content_text.strip() or (regulatory_document.summary or regulatory_document.title)
    knowledge_document = await create_knowledge_document(
        session,
        document_key=doc_key,
        jurisdiction=regulatory_document.jurisdiction,
        source_type=source_type,
        version=next_version,
        title=regulatory_document.title,
        content=content_text,
        metadata_json={
            "authority": regulatory_document.authority,
            "external_id": regulatory_document.external_id,
            "document_url": regulatory_document.document_url,
            "source": "regulatory_ingestion",
            **(regulatory_document.metadata_json or {}),
        },
        is_active=True,
    )

    regulatory_document.is_promoted = True
    regulatory_document.promoted_knowledge_doc_id = knowledge_document.id
    session.add(regulatory_document)
    await session.flush()
    return knowledge_document.id


def fetch_source_items(
    source: RegulatorySource,
    *,
    max_items: int = 50,
    timeout_seconds: int = 30,
) -> list[RegulatoryItem]:
    if source.source_type == RegulatorySourceType.MANUAL:
        return []
    if source.source_type == RegulatorySourceType.API_JSON:
        return _fetch_api_json(source, max_items=max_items, timeout_seconds=timeout_seconds)
    if source.source_type == RegulatorySourceType.RSS:
        return _fetch_rss(source, max_items=max_items, timeout_seconds=timeout_seconds)
    if source.source_type == RegulatorySourceType.HTML:
        return _fetch_html(source, max_items=max_items, timeout_seconds=timeout_seconds)
    raise ValueError(f"Unsupported source type: {source.source_type}")


def _fetch_api_json(source: RegulatorySource, *, max_items: int, timeout_seconds: int) -> list[RegulatoryItem]:
    parser = source.parser_config or {}
    query = parser.get("query", {})
    headers = parser.get("headers", {})

    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        response = client.get(source.endpoint, params=query, headers=headers)
        response.raise_for_status()
        payload = response.json()

    results_path = parser.get("results_path", "results")
    rows = _extract_path(payload, str(results_path))
    if not isinstance(rows, list):
        raise ValueError(f"JSON results_path did not return a list: {results_path}")

    id_field = parser.get("id_field", "id")
    title_field = parser.get("title_field", "title")
    summary_field = parser.get("summary_field", "summary")
    url_field = parser.get("url_field", "url")
    date_field = parser.get("date_field", "published_on")
    content_field = parser.get("content_field")

    items: list[RegulatoryItem] = []
    for row in rows[:max_items]:  # type: ignore
        if not isinstance(row, dict):
            continue
        document_url = str(row.get(url_field) or source.endpoint)
        title = str(row.get(title_field) or "").strip()
        if not title:
            continue

        summary = str(row.get(summary_field)) if row.get(summary_field) is not None else None
        content_text = (
            str(row.get(content_field))
            if content_field and row.get(content_field) is not None
            else (summary or title)
        )
        published_on = _parse_datetime(row.get(date_field))
        external_id = str(row.get(id_field) or hash_object({"url": document_url, "title": title}))

        items.append(
            RegulatoryItem(
                external_id=external_id,
                title=title,
                summary=summary,
                document_url=document_url,
                published_on=published_on,
                content_text=content_text,
                metadata_json={"raw_row": row},
            )
        )
    return items


def _fetch_rss(source: RegulatorySource, *, max_items: int, timeout_seconds: int) -> list[RegulatoryItem]:
    parser = source.parser_config or {}
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        response = client.get(source.endpoint)
        response.raise_for_status()
        feed_text = response.text

        root = _parse_xml(feed_text)
        if root is None:
            feed_url = _extract_feed_url_from_html(
                html_text=feed_text,
                base_url=source.endpoint,
                preferred_patterns=_as_list(parser.get("feed_url_patterns")),
            )
            if not feed_url:
                raise ValueError("Unable to parse RSS/Atom feed and no feed link found in HTML response")
            followup = client.get(feed_url)
            followup.raise_for_status()
            feed_text = followup.text
            root = _parse_xml(feed_text)

        if root is None:
            raise ValueError("Failed to parse RSS/Atom feed XML")

    if source.source_key.startswith("EU_EURLEX"):
        return _parse_eurlex_feed(source=source, root=root, max_items=max_items)
    return _parse_generic_feed(source=source, root=root, max_items=max_items)


def _fetch_html(source: RegulatorySource, *, max_items: int, timeout_seconds: int) -> list[RegulatoryItem]:
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        response = client.get(source.endpoint)
        response.raise_for_status()
        html = response.text

    if source.source_key.startswith("IN_MCA_"):
        return _parse_mca_html(source=source, html=html, max_items=max_items)
    if source.source_key.startswith("IN_CBIC_"):
        return _parse_cbic_html(source=source, html=html, max_items=max_items)

    parser = source.parser_config or {}
    item_regex = parser.get("item_regex")
    if not item_regex:
        raise ValueError("HTML source requires parser_config.item_regex")

    base_url = parser.get("base_url", source.endpoint)
    regex = re.compile(item_regex, re.IGNORECASE)

    extracted: list[RegulatoryItem] = []
    seen_urls: set[str] = set()
    for match in regex.finditer(html):
        if len(extracted) >= max_items:
            break
        raw_url = (match.groupdict().get("url") or "").strip()
        title = _clean_text(match.groupdict().get("title"))
        if not raw_url or not title:
            continue
        document_url = str(urljoin(base_url, raw_url))
        if document_url in seen_urls:
            continue
        seen_urls.add(document_url)
        published_on = _parse_datetime(match.groupdict().get("date"))
        external_id = hash_object({"url": document_url, "title": title})
        extracted.append(
            RegulatoryItem(
                external_id=external_id,
                title=title,
                summary=None,
                document_url=document_url,
                published_on=published_on,
                content_text=title,
                metadata_json={"source_type": "html", "parser_profile": "regex"},
            )
        )
    return extracted


def _parse_mca_html(source: RegulatorySource, *, html: str, max_items: int) -> list[RegulatoryItem]:
    parser = source.parser_config or {}
    include_patterns = _as_list(parser.get("include_patterns")) or [
        "notification",
        "circular",
        "order",
        "rule",
        "amend",
    ]
    exclude_patterns = _as_list(parser.get("exclude_patterns")) or [
        "archive",
        "contact",
        "help",
        "javascript:",
    ]
    return _parse_anchor_html(
        source=source,
        html=html,
        max_items=max_items,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        parser_profile="mca_hardened",
    )


def _parse_cbic_html(source: RegulatorySource, *, html: str, max_items: int) -> list[RegulatoryItem]:
    parser = source.parser_config or {}
    include_patterns = _as_list(parser.get("include_patterns")) or [
        "notification",
        "circular",
        "instruction",
        "regulation",
        "gst",
        "custom",
        "excise",
    ]
    exclude_patterns = _as_list(parser.get("exclude_patterns")) or [
        "archive",
        "contact",
        "help",
        "javascript:",
    ]
    return _parse_anchor_html(
        source=source,
        html=html,
        max_items=max_items,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        parser_profile="cbic_hardened",
    )


def _parse_anchor_html(
    *,
    source: RegulatorySource,
    html: str,
    max_items: int,
    include_patterns: list[str],
    exclude_patterns: list[str],
    parser_profile: str,
) -> list[RegulatoryItem]:
    parser = source.parser_config or {}
    base_url = str(parser.get("base_url") or source.endpoint)
    extractor = _AnchorExtractor()
    extractor.feed(html)

    include_regexes = [re.compile(pattern, re.IGNORECASE) for pattern in include_patterns]
    exclude_regexes = [re.compile(pattern, re.IGNORECASE) for pattern in exclude_patterns]

    extracted: list[RegulatoryItem] = []
    seen_urls: set[str] = set()
    for raw_url, raw_title in extractor.links:
        if len(extracted) >= max_items:
            break
        title = _clean_text(raw_title)
        if not title:
            continue

        document_url = urljoin(base_url, raw_url.strip())
        lowered_target = f"{document_url} {title}".lower()
        if any(pattern.search(lowered_target) for pattern in exclude_regexes):
            continue
        if not (
            _looks_like_regulatory_doc(document_url)
            or any(pattern.search(lowered_target) for pattern in include_regexes)
        ):
            continue
        if document_url in seen_urls:
            continue
        seen_urls.add(document_url)

        extracted.append(
            RegulatoryItem(
                external_id=hash_object({"url": document_url, "title": title}),
                title=title,
                summary=None,
                document_url=document_url,
                published_on=_extract_date_from_text(title),
                content_text=title,
                metadata_json={
                    "source_type": "html",
                    "parser_profile": parser_profile,
                },
            )
        )
    return extracted


def _parse_eurlex_feed(source: RegulatorySource, *, root: ElementTree.Element, max_items: int) -> list[RegulatoryItem]:
    return _parse_feed_items(
        source=source,
        root=root,
        max_items=max_items,
        title_keys=["title"],
        summary_keys=["summary", "description", "content"],
        id_keys=["identifier", "guid", "id", "celex"],
        date_keys=["updated", "published", "pubdate", "issued", "date"],
        parser_profile="eurlex_hardened",
    )


def _parse_generic_feed(source: RegulatorySource, *, root: ElementTree.Element, max_items: int) -> list[RegulatoryItem]:
    parser = source.parser_config or {}
    title_keys = _as_list(parser.get("title_fields")) or [str(parser.get("title_field", "title"))]
    summary_keys = _as_list(parser.get("summary_fields")) or [str(parser.get("summary_field", "description"))]
    id_keys = _as_list(parser.get("id_fields")) or [str(parser.get("id_field", "guid"))]
    date_keys = _as_list(parser.get("date_fields")) or [str(parser.get("date_field", "pubDate"))]

    return _parse_feed_items(
        source=source,
        root=root,
        max_items=max_items,
        title_keys=title_keys,
        summary_keys=summary_keys,
        id_keys=id_keys,
        date_keys=date_keys,
        parser_profile="rss_generic",
    )


def _parse_feed_items(
    *,
    source: RegulatorySource,
    root: ElementTree.Element,
    max_items: int,
    title_keys: list[str],
    summary_keys: list[str],
    id_keys: list[str],
    date_keys: list[str],
    parser_profile: str,
) -> list[RegulatoryItem]:
    entries = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]

    extracted: list[RegulatoryItem] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if len(extracted) >= max_items:
            break

        title = _extract_entry_text(entry, title_keys)
        if not title:
            continue
        summary = _extract_entry_text(entry, summary_keys)
        document_url = _extract_entry_link(entry) or source.endpoint
        external_id = _extract_entry_text(entry, id_keys)
        if not external_id:
            external_id = hash_object({"url": document_url, "title": title})
        if external_id in seen_ids:
            continue
        seen_ids.add(external_id)

        published_on = _parse_datetime(_extract_entry_text(entry, date_keys))
        clean_summary = _clean_text(summary) if summary else None
        extracted.append(
            RegulatoryItem(
                external_id=external_id,
                title=_clean_text(title),
                summary=clean_summary,
                document_url=document_url,
                published_on=published_on,
                content_text=clean_summary or _clean_text(title),
                metadata_json={
                    "source_type": "rss",
                    "parser_profile": parser_profile,
                },
            )
        )
    return extracted


def _extract_path(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _parse_datetime(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (TypeError, ValueError):
            return None


def _parse_xml(text: str) -> ElementTree.Element | None:
    try:
        return ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return None


def _extract_feed_url_from_html(
    *,
    html_text: str,
    base_url: str,
    preferred_patterns: list[str] | None = None,
) -> str | None:
    extractor = _AnchorExtractor()
    extractor.feed(html_text)

    preferred_regexes = [re.compile(pattern, re.IGNORECASE) for pattern in preferred_patterns or []]

    for raw_url, title in extractor.links:
        absolute_url = urljoin(base_url, raw_url)
        haystack = f"{absolute_url} {title}".lower()
        if preferred_regexes and any(regex.search(haystack) for regex in preferred_regexes):
            return absolute_url

    for raw_url, _ in extractor.links:
        absolute_url = urljoin(base_url, raw_url)
        lowered_url = absolute_url.lower()
        if "rss" in lowered_url or lowered_url.endswith(".xml"):
            return absolute_url
    return None


def _extract_entry_text(entry: ElementTree.Element, keys: list[str]) -> str | None:
    normalized_keys = {_normalize_key(key) for key in keys}
    for node in entry.iter():
        node_key = _normalize_key(_local_name(node.tag))
        if node_key not in normalized_keys:
            continue
        text = _clean_text(" ".join(node.itertext()))
        if text:
            return text
    return None


def _extract_entry_link(entry: ElementTree.Element) -> str | None:
    for node in entry.iter():
        if _local_name(node.tag) != "link":
            continue
        href = node.attrib.get("href")
        if href:
            return href.strip()
        text = _clean_text(" ".join(node.itertext()))
        if text:
            return text
    return None


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1].lower()


def _normalize_key(raw_key: str) -> str:
    return raw_key.lower().replace(":", "").replace("-", "").replace("_", "")


def _as_list(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        clean = raw_value.strip()
        return [clean] if clean else []
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    return [str(raw_value).strip()]


def _clean_text(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    text = str(raw_value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _looks_like_regulatory_doc(url: str) -> bool:
    lowered = url.lower()
    doc_patterns = (
        ".pdf",
        ".doc",
        ".docx",
        ".htm",
        ".html",
        "notification",
        "circular",
        "regulation",
        "order",
        "act",
        "rule",
        "directive",
    )
    return any(pattern in lowered for pattern in doc_patterns)


def _extract_date_from_text(text: str) -> datetime | None:
    patterns = (
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        parsed = _parse_datetime(match.group(0))
        if parsed is not None:
            return parsed
    return None


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _build_doc_key(document: RegulatoryDocument) -> str:
    authority = re.sub(r"[^a-z0-9]+", "_", document.authority.lower()).strip("_")
    ext = re.sub(r"[^a-z0-9]+", "_", document.external_id.lower()).strip("_")
    key = f"{authority}_{ext}"[:100]  # type: ignore
    return key or f"reg_{document.id}"
