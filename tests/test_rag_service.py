# pyre-ignore-all-errors
from arkashri.services.rag import RagSourceMatch, build_grounded_answer, split_into_chunks, tokenize


def test_tokenize_is_lowercase_and_alphanumeric() -> None:
    tokens = tokenize("GST Section-44AB, India 2026!")
    assert tokens == ["gst", "section", "44ab", "india", "2026"]


def test_split_into_chunks_is_deterministic() -> None:
    content = " ".join([f"word{i}" for i in range(1, 251)])
    chunks = split_into_chunks(content, chunk_words=100, overlap_words=20)
    assert len(chunks) == 3
    assert chunks[0].split()[0] == "word1"
    assert chunks[1].split()[0] == "word81"
    assert chunks[2].split()[0] == "word161"


def test_grounded_answer_without_sources() -> None:
    answer = build_grounded_answer("what is gst audit?", [])
    assert "No grounded evidence was found" in answer


def test_grounded_answer_with_sources() -> None:
    sources = [
        RagSourceMatch(
            document_key="india_companies_act",
            document_title="Companies Act Controls",
            document_version=1,
            jurisdiction="IN",
            chunk_index=1,
            chunk_hash="a" * 64,
            score=0.75,
            snippet="Board approvals and financial statement controls are mandatory.",
        )
    ]
    answer = build_grounded_answer("controls?", sources)
    assert "Grounded findings" in answer
    assert "Companies Act Controls" in answer
