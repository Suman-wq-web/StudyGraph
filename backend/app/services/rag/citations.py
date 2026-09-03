"""
Builds the citation list returned alongside a RAG answer, mapping each
retrieved chunk back to its source resource (id, title, type, snippet) so
the frontend can render CitationBadge components (a later, frontend pass).

Citation order mirrors the order of `chunks` (fused-rank order, from
app/services/rag/retrieval.py) -- this is also the numbering used in the LLM
prompt (app/services/rag/pipeline.py:_build_prompt), so citations[n-1] maps
directly to an inline "[n]" marker in the generated answer. No resource-level
dedup: two chunks from the same resource are distinct evidence and each gets
its own citation.
"""

from app.config import settings
from app.db import resource_repository
from app.models.chat import Citation
from app.models.chunk import DocumentChunk


async def build_citations(chunks: list[DocumentChunk], user_id: str) -> list[Citation]:
    if not chunks:
        return []

    resource_ids = list({chunk.resource_id for chunk in chunks})
    resources = {
        resource.id: resource
        for resource in await resource_repository.get_many_by_ids(resource_ids, user_id)
    }

    citations: list[Citation] = []
    for chunk in chunks:
        resource = resources.get(chunk.resource_id)
        if resource is None:
            continue  # resource was deleted between retrieval and this join
        citations.append(
            Citation(
                resource_id=resource.id,
                resource_title=resource.title,
                resource_type=resource.type,
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                snippet=_snippet(chunk.text, max_chars=settings.rag_max_snippet_chars),
            )
        )
    return citations


def _snippet(text: str, *, max_chars: int) -> str:
    """Truncates at the last word boundary <= max_chars, appending '...' if
    truncated. Returns `text` unchanged if it already fits."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip() + "..."
