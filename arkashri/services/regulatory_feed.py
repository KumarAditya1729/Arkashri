"""
Gap 7 — Standards Update Pipeline
Automated feed for ICAI SA circulars, SEBI circulars, MCA Companies Act amendments.
Runs daily as an ARQ background job; each source is polled and new items stored
as RegulatoryDocument records, then broadcast to all ADMIN users.
"""
from __future__ import annotations

import hashlib
import httpx
import re
from datetime import datetime, timezone
from typing import NamedTuple
from xml.etree import ElementTree

import structlog

logger = structlog.get_logger(__name__)

# ── Feed definitions ──────────────────────────────────────────────────────────

class FeedItem(NamedTuple):
    external_id: str
    title: str
    summary: str
    url: str
    published_on: datetime | None
    content_text: str


FEEDS = {
    "ICAI_SA": {
        "authority": "ICAI",
        "jurisdiction": "IN",
        "description": "ICAI Standards on Auditing (SA) and circulars",
        # ICAI provides a news RSS feed; circulars listed at standards page
        "rss_url": "https://www.icai.org/new_rss.html",
        "fallback_url": "https://www.icai.org/post.html?post_id=17543",
    },
    "SEBI": {
        "authority": "SEBI",
        "jurisdiction": "IN",
        "description": "SEBI circulars and notifications",
        "rss_url": "https://www.sebi.gov.in/sebi_data/commondocs/circular_rss.xml",
        "fallback_url": "https://www.sebi.gov.in/legal/circulars.html",
    },
    "MCA": {
        "authority": "MCA",
        "jurisdiction": "IN",
        "description": "Ministry of Corporate Affairs Companies Act amendments",
        "rss_url": "https://www.mca.gov.in/content/mca/global/en/acts-rules/ebooks/acts.html",
        "fallback_url": "https://www.mca.gov.in/MinistryV2/companiesact2013.html",
    },
}


# ── RSS parser ────────────────────────────────────────────────────────────────

def _parse_rss(xml_text: str, source_key: str) -> list[FeedItem]:
    """Parse RSS/Atom feed XML into FeedItem list."""
    items: list[FeedItem] = []
    try:
        root = ElementTree.fromstring(xml_text)
        # Handle both RSS <item> and Atom <entry>
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for entry in entries[:20]:  # max 20 per run
            def _text(tag: str) -> str:
                el = entry.find(tag) or entry.find(f"atom:{tag}", ns)
                return (el.text or "").strip() if el is not None else ""

            title = _text("title") or _text("name") or "Untitled"
            url = _text("link") or _text("atom:link")
            summary = _text("description") or _text("summary") or _text("content") or title
            pub_str = _text("pubDate") or _text("published") or _text("updated")

            pub_dt: datetime | None = None
            if pub_str:
                for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
                    try:
                        pub_dt = datetime.strptime(pub_str.strip(), fmt)
                        break
                    except ValueError:
                        continue

            # Strip HTML tags from summary
            clean_summary = re.sub(r"<[^>]+>", " ", summary).strip()
            ext_id = hashlib.sha256(f"{source_key}:{url}:{title}".encode()).hexdigest()[:32]

            items.append(FeedItem(
                external_id=ext_id,
                title=title[:500],
                summary=clean_summary[:2000],
                url=url[:2048] if url else f"https://arkashri.app/regulatory/{source_key}/{ext_id}",
                published_on=pub_dt,
                content_text=clean_summary,
            ))
    except ElementTree.ParseError as exc:
        logger.warning("rss_parse_failed", error=str(exc))
    return items


async def _fetch_feed(source_key: str) -> list[FeedItem]:
    """Fetch RSS for a given source, with fallback to a simulated item on error."""
    cfg = FEEDS[source_key]
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(cfg["rss_url"], headers={"User-Agent": "Arkashri-RegulatoryBot/1.0"})
            resp.raise_for_status()
            return _parse_rss(resp.text, source_key)
    except Exception as exc:
        logger.warning("feed_fetch_failed", source=source_key, error=str(exc))
        # Return a synthetic placeholder so the pipeline doesn't fail silently
        now = datetime.now(timezone.utc)
        return [FeedItem(
            external_id=f"{source_key}-placeholder-{now.strftime('%Y%m%d')}",
            title=f"{cfg['authority']} — Feed temporarily unavailable ({now.strftime('%d %b %Y')})",
            summary=f"Could not fetch live {cfg['authority']} feed. Check {cfg['fallback_url']} manually.",
            url=cfg["fallback_url"],
            published_on=now,
            content_text=f"Auto-fetch failed: {exc}",
        )]


# ── DB persistence ────────────────────────────────────────────────────────────

async def ingest_feed(source_key: str, db) -> int:
    """
    Fetch feed and upsert new items into RegulatoryDocument.
    Returns number of new items inserted.
    """
    from sqlalchemy import select
    from arkashri.models import RegulatorySource, RegulatoryDocument

    # Look up or create the RegulatorySource row
    source = (await db.scalars(
        select(RegulatorySource).where(RegulatorySource.source_key == source_key)
    )).first()

    if not source:
        cfg = FEEDS[source_key]
        from arkashri.models import RegulatorySourceType
        source = RegulatorySource(
            source_key=source_key,
            jurisdiction=cfg["jurisdiction"],
            authority=cfg["authority"],
            source_type=RegulatorySourceType.GOVERNMENT_PORTAL,
            endpoint=cfg["rss_url"],
            parser_config={"type": "rss"},
            is_active=True,
        )
        db.add(source)
        await db.flush()

    items = await _fetch_feed(source_key)
    new_count = 0

    for item in items:
        existing = (await db.scalars(
            select(RegulatoryDocument).where(
                RegulatoryDocument.source_id == source.id,
                RegulatoryDocument.external_id == item.external_id,
            )
        )).first()
        if existing:
            continue

        content_hash = hashlib.sha256(item.content_text.encode()).hexdigest()
        doc = RegulatoryDocument(
            source_id=source.id,
            jurisdiction=source.jurisdiction,
            authority=source.authority,
            external_id=item.external_id,
            title=item.title,
            summary=item.summary,
            document_url=item.url,
            published_on=item.published_on,
            content_text=item.content_text,
            content_hash=content_hash,
            metadata_json={"source_key": source_key, "ingested_via": "regulatory_feed"},
        )
        db.add(doc)
        new_count += 1

    # Update last_success_at
    source.last_success_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info("regulatory_feed_ingested", source=source_key, new_items=new_count)
    return new_count


# ── Public helpers ────────────────────────────────────────────────────────────

async def run_all_feeds(db) -> dict[str, int]:
    """Run all three feeds and return counts. Called by daily ARQ job."""
    results: dict[str, int] = {}
    for source_key in FEEDS:
        try:
            results[source_key] = await ingest_feed(source_key, db)
        except Exception as exc:
            logger.error("feed_ingest_error", source=source_key, error=str(exc))
            results[source_key] = -1
    return results
