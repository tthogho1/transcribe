"""
Cross-encoder reranker for search results.

Hybrid search fuses dense and BM25 rankings with RRF, which only looks at
ranks, not at whether a chunk actually answers the question. A cross-encoder
reads the query and each candidate chunk together and scores their relevance,
so re-scoring a few dozen candidates puts the chunk that answers the question
on top more often.

Import this after services.processing.vector_generator: that module patches
torch.compile before sentence-transformers / transformers are imported.
"""

from dataclasses import replace
from typing import List

from sentence_transformers import CrossEncoder

from models.conversation_chunk import SearchResult


class Reranker:
    """Re-score SearchResults with a sentence-transformers CrossEncoder."""

    def __init__(self, model_name: str = "cl-nagoya/ruri-v3-reranker-310m"):
        self.model_name = model_name
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, results: List[SearchResult], limit: int) -> List[SearchResult]:
        """
        Return the top `limit` results ordered by cross-encoder score. The
        returned SearchResults carry the reranker score in `score` and keep the
        original fusion score in `similarity`.
        """
        if not results:
            return []
        scores = self.model.predict(
            [(query, r.text) for r in results], show_progress_bar=False
        )
        ranked = sorted(zip(results, scores), key=lambda pair: float(pair[1]), reverse=True)
        return [
            replace(r, score=float(s), search_type=f"{r.search_type}+rerank")
            for r, s in ranked[:limit]
        ]
