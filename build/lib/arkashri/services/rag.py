# pyre-ignore-all-errors
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import KnowledgeChunk, KnowledgeDocument, KnowledgeSourceType
from arkashri.services.canonical import hash_object

WORD_PATTERN = re.compile(r"[a-z0-9_]+")
DEFAULT_CHUNK_WORDS = 120
DEFAULT_CHUNK_OVERLAP = 20


@dataclass
class RagSourceMatch:
    document_key: str
    document_title: str
    document_version: int
    jurisdiction: str
    chunk_index: int
    chunk_hash: str
    score: float
    snippet: str


def tokenize(text: str) -> list[str]:
    return WORD_PATTERN.findall(text.lower())


def split_into_chunks(
    content: str,
    *,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    words = content.split()
    if not words:
        return []
    if chunk_words <= overlap_words:
        raise ValueError("chunk_words must be greater than overlap_words")

    chunks: list[str] = []
    position = 0
    step = chunk_words - overlap_words

    while position < len(words):
        chunk = words[position : position + chunk_words]
        chunks.append(" ".join(chunk))
        if position + chunk_words >= len(words):
            break
        position += step

    return chunks


async def create_knowledge_document(
    session: AsyncSession,
    *,
    document_key: str,
    jurisdiction: str,
    source_type: KnowledgeSourceType,
    version: int,
    title: str,
    content: str,
    metadata_json: dict,
    is_active: bool,
) -> KnowledgeDocument:
    content_hash = hash_object(
        {
            "document_key": document_key,
            "jurisdiction": jurisdiction,
            "version": version,
            "title": title,
            "content": content,
        }
    )

    if is_active:
        await session.execute(
            update(KnowledgeDocument)
            .where(
                KnowledgeDocument.document_key == document_key,
                KnowledgeDocument.jurisdiction == jurisdiction,
            )
            .values(is_active=False)
        )

    document = KnowledgeDocument(
        document_key=document_key,
        jurisdiction=jurisdiction,
        source_type=source_type,
        version=version,
        title=title,
        content=content,
        content_hash=content_hash,
        metadata_json=metadata_json,
        is_active=is_active,
    )
    session.add(document)
    await session.flush()

    chunks = split_into_chunks(content)
    for chunk_index, chunk_text in enumerate(chunks, start=1):
        chunk_tokens = tokenize(chunk_text)
        chunk = KnowledgeChunk(
            document_id=document.id,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            chunk_hash=hash_object({"document_id": document.id, "chunk_index": chunk_index, "chunk_text": chunk_text}),
            token_fingerprint=hash_object(sorted(set(chunk_tokens))),
            metadata_json={"token_count": len(chunk_tokens)},
        )
        session.add(chunk)

    await session.flush()
    return document


async def query_knowledge(
    session: AsyncSession,
    *,
    jurisdiction: str,
    query_text: str,
    top_k: int,
    audit_type: str | None = None,
) -> tuple[str, list[RagSourceMatch], str]:
    query_tokens = tokenize(query_text)
    query_token_set = set(query_tokens)
    query_hash = hash_object(
        {
            "jurisdiction": jurisdiction,
            "query_text": query_text,
            "top_k": top_k,
            "audit_type": audit_type,
        }
    )

    stmt = (
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeDocument.is_active.is_(True),
            KnowledgeDocument.jurisdiction.in_([jurisdiction, "GLOBAL"]),
        )
    )
    result = await session.execute(stmt)
    candidates = list(result)

    scored_matches: list[RagSourceMatch] = []
    for chunk, document in candidates:
        score = _lexical_score(query_token_set, tokenize(chunk.chunk_text))
        if audit_type and audit_type.lower() in f"{document.document_key} {document.title}".lower():
            score += 0.05
        if score <= 0:
            continue

        scored_matches.append(
            RagSourceMatch(
                document_key=document.document_key,
                document_title=document.title,
                document_version=document.version,
                jurisdiction=document.jurisdiction,
                chunk_index=chunk.chunk_index,
                chunk_hash=chunk.chunk_hash,
                score=round(score, 6),
                snippet=chunk.chunk_text[:420],
            )
        )

    ranked = sorted(
        scored_matches,
        key=lambda item: (
            -item.score,
            item.document_key,
            item.document_version,
            item.chunk_index,
        ),
    )[:top_k]

    answer = build_grounded_answer(query_text, ranked)
    return answer, ranked, query_hash


def build_grounded_answer(query_text: str, matches: list[RagSourceMatch]) -> str:
    if not matches:
        return (
            "No grounded evidence was found in the active knowledge base for this query. "
            "Add jurisdiction-specific compliance documents and retry."
        )

    lines = [f"Query: {query_text}", "Grounded findings:"]
    for index, match in enumerate(matches, start=1):
        lines.append(
            f"[{index}] {match.document_title} (v{match.document_version}, {match.jurisdiction}) "
            f"score={match.score:.3f}: {match.snippet}"
        )
    return "\n".join(lines)


def _lexical_score(query_tokens: set[str], chunk_tokens: list[str]) -> float:
    if not query_tokens or not chunk_tokens:
        return 0.0
    chunk_token_set = set(chunk_tokens)
    overlap = query_tokens.intersection(chunk_token_set)
    if not overlap:
        return 0.0
    return len(overlap) / len(query_tokens)
