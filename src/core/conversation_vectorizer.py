"""
Main conversation vectorizer orchestrating all components.

This module does not load .env: entry points (chat_server, scripts) do that
before constructing a ConversationVectorizer. Progress is reported through
the `core.conversation_vectorizer` logger.
"""

import logging
import os
from dataclasses import replace
from typing import List, Dict, Optional

from models.conversation_chunk import ConversationChunk, SearchResult
from services.processing.text_processor import TextProcessor
from services.processing.vector_generator import DenseVectorGenerator
from services.processing.reranker import Reranker
from services.database.zilliz_bm25_client import ZillizBM25Client

logger = logging.getLogger(__name__)


class SearchUnavailableError(RuntimeError):
    """Search can't run at all (e.g. Zilliz was unreachable at startup)."""


def _join_overlapping(texts: List[str], max_overlap: int = 120) -> str:
    """
    Join consecutive chunks, dropping the text each chunk repeats from the end
    of the previous one (chunks are cut with a character overlap).
    """
    if not texts:
        return ""
    joined = texts[0]
    for text in texts[1:]:
        overlap = 0
        for k in range(min(max_overlap, len(text), len(joined)), 9, -1):
            if joined.endswith(text[:k]):
                overlap = k
                break
        joined += text[overlap:]
    return joined


class ConversationVectorizer:
    """Main conversation vectorizer orchestrating all components"""

    def __init__(
        self,
        zilliz_uri: str,
        zilliz_token: str,
        embedding_model: str = "cl-nagoya/ruri-v3-310m",
        chunk_size: int = 300,
        chunk_overlap: int = 50,
        bm25_collection_name: Optional[str] = None,
        dense_query_prefix: str = "検索クエリ: ",
        dense_document_prefix: str = "検索文書: ",
        reranker_model: Optional[str] = None,
        rerank_candidates: Optional[int] = None,
    ):
        """
        Initialize conversation vectorizer
        Args:
            zilliz_uri: Zilliz Cloud URI
            zilliz_token: Zilliz Cloud token
            embedding_model: SentenceTransformer model name. Defaults to ruri-v3-310m
                              (768D, matches the existing dense_vector schema).
            chunk_size: Chunk size in characters
            chunk_overlap: Overlap size in characters
            bm25_collection_name: Zilliz collection name (dense + native BM25 sparse).
                              None reads ZILLIZ_BM25_COLLECTION (default
                              "conversation_chunks_bm25_v2"). This is deliberately not
                              ZILLIZ_COLLECTION_NAME, which older deployments still
                              set to the retired TF-IDF collection.
            dense_query_prefix / dense_document_prefix: ruri-v3 uses asymmetric
                              retrieval prefixes ("1+3 prefix scheme"); pass "" for
                              models that don't use them.
            reranker_model: CrossEncoder used to re-score hybrid search
                              candidates. None reads RERANKER_MODEL from the
                              environment; "" (or an unset variable) disables
                              reranking.
            rerank_candidates: How many hybrid results the reranker re-scores.
                              None reads RERANK_CANDIDATES (default 10).
        """
        self.text_processor = TextProcessor(chunk_size, chunk_overlap)

        # Dense embeddings only: the sparse (BM25) vector is derived server-side
        # by Zilliz from the chunk text. The same generator embeds documents at
        # ingest time and queries at search time, so both sides always match.
        logger.info("🔧 Loading embedding model %s...", embedding_model)
        self.dense_generator = DenseVectorGenerator(
            embedding_model,
            query_prefix=dense_query_prefix,
            document_prefix=dense_document_prefix,
        )

        if bm25_collection_name is None:
            bm25_collection_name = os.getenv(
                "ZILLIZ_BM25_COLLECTION", "conversation_chunks_bm25_v2"
            )

        # A failed connection doesn't stop the server from starting: searches
        # then raise SearchUnavailableError and /health reports "disconnected".
        self.bm25_client = None
        if zilliz_uri:
            try:
                self.bm25_client = ZillizBM25Client(
                    zilliz_uri, zilliz_token, bm25_collection_name
                )
                logger.info("✅ Connected to Zilliz collection %s", bm25_collection_name)
            except Exception as e:
                logger.error("⚠️ ZillizBM25Client initialization failed: %s", e)
        else:
            logger.warning("⚠️ ZILLIZ_URI not provided - search and ingest are unavailable")

        if reranker_model is None:
            reranker_model = os.getenv("RERANKER_MODEL", "")
        if rerank_candidates is None:
            rerank_candidates = int(os.getenv("RERANK_CANDIDATES", "10"))
        self.rerank_candidates = rerank_candidates
        # Neighbouring chunks added around each hit by search_passages().
        self.context_before = int(os.getenv("CONTEXT_CHUNKS_BEFORE", "1"))
        self.context_after = int(os.getenv("CONTEXT_CHUNKS_AFTER", "3"))
        self.reranker = None
        if reranker_model:
            logger.info("🔧 Loading reranker %s...", reranker_model)
            self.reranker = Reranker(reranker_model)

        logger.info("✅ ConversationVectorizer ready")

    def process_monologue_bm25(
        self, text: str, file_name: str, title: str = ""
    ) -> List[ConversationChunk]:
        """
        Complete processing pipeline for monologue text.
        Only dense embeddings are computed client-side; the sparse vector is
        derived automatically by Zilliz's BM25 function from the chunk text.
        Args:
            text: Monologue text
            file_name: Name of the file being processed
            title: Human-readable title (e.g. YouTube video title) stored
                   alongside each chunk for display in search results
        Returns:
            List of processed chunks
        Raises:
            RuntimeError: If the BM25 client is not available
            Exception: Whatever the Zilliz insert raises, so callers never see
                       chunks that were not actually stored
        """
        if not self.bm25_client:
            raise RuntimeError("BM25 client not available - cannot insert data")

        chunks = self.text_processor.process_text(text, file_name, title)
        dense_embeddings = self.dense_generator.generate([chunk.text for chunk in chunks])
        self.bm25_client.insert_data(chunks, dense_embeddings)

        logger.info("🎉 Inserted %d chunks for %s", len(chunks), file_name)
        return chunks

    def hybrid_search_bm25(
        self, query: str, limit: int = 5, rerank_k: int = 100
    ) -> List[SearchResult]:
        """
        Perform hybrid search using the native-BM25 collection: dense ANN
        combined server-side with BM25 full-text search on the raw query text.
        When a reranker is configured, the top `rerank_candidates` fused
        results (at least `limit`) are re-scored by the cross-encoder and the
        best `limit` are returned.
        Args:
            query: Search query
            limit: Number of final results
            rerank_k: Number of candidates considered per side before fusion
        Returns:
            List of search results ([] only when nothing matched)
        Raises:
            SearchUnavailableError: If the Zilliz client failed to initialise
            Exception: Whatever embedding, Zilliz or the reranker raises. A
                       failure is never reported as "no results".
        """
        n = max(limit, self.rerank_candidates) if self.reranker else limit
        return self._rerank(query, self._candidates(query, n, rerank_k), limit)

    def search_passages(
        self, query: str, limit: int = 5, rerank_k: int = 100
    ) -> List[SearchResult]:
        """
        Search for answer passages rather than single chunks.

        A 300-character chunk often holds only the set-up of a story while the
        punchline sits in the next chunks, and a story repeated inside one
        transcript can fill the top results with near-identical set-ups. So:
          1. hybrid search a wider pool of chunks,
          2. keep only the best chunk per video (file_name). Near-identical
             chunks from *different* videos, e.g. a clip and its full-length
             source, are not merged,
          3. rerank those (if a reranker is configured) and take `limit`,
          4. replace each chunk's text with the passage from
             `context_before` chunks before it to `context_after` chunks after.
        If fetching the neighbouring chunks fails, the single chunks are
        returned unchanged (they are still correct results). Any other failure
        raises, as in hybrid_search_bm25(): [] means nothing matched.
        """
        pool = max(limit * 4, self.rerank_candidates, 20)
        hits = self._candidates(query, pool, rerank_k)

        best_per_video: List[SearchResult] = []
        seen = set()
        for hit in hits:
            if hit.file_name not in seen:
                seen.add(hit.file_name)
                best_per_video.append(hit)

        return self._expand_to_passages(self._rerank(query, best_per_video, limit))

    def _candidates(self, query: str, n: int, rerank_k: int) -> List[SearchResult]:
        """Embed `query` and return the top `n` fused dense + BM25 hits."""
        if not self.bm25_client:
            raise SearchUnavailableError(
                "Zilliz search is unavailable: the BM25 client failed to initialise "
                "(check ZILLIZ_URI / ZILLIZ_TOKEN and the startup log)"
            )
        dense_query = self.dense_generator.generate_query_embedding(query)
        return self.bm25_client.hybrid_search(dense_query, query, n, rerank_k)

    def _rerank(
        self, query: str, results: List[SearchResult], limit: int
    ) -> List[SearchResult]:
        """Best `limit` results: cross-encoder re-scored if a reranker is set."""
        if not self.reranker:
            return results[:limit]
        return self.reranker.rerank(
            query, results[: max(limit, self.rerank_candidates)], limit
        )

    def _expand_to_passages(self, results: List[SearchResult]) -> List[SearchResult]:
        if self.context_before == 0 and self.context_after == 0:
            return results
        ranges = [
            (r.file_name, max(0, r.chunk_index - self.context_before),
             r.chunk_index + self.context_after)
            for r in results
            if r.chunk_index >= 0
        ]
        try:
            texts_by_file = self.bm25_client.fetch_chunk_ranges(ranges)
        except Exception as e:
            logger.warning("⚠️ Could not fetch neighbouring chunks, using single chunks: %s", e)
            return results

        passages = []
        for r in results:
            chunks = texts_by_file.get(r.file_name, {})
            if r.chunk_index < 0 or r.chunk_index not in chunks:
                passages.append(r)
                continue
            lo = r.chunk_index - self.context_before
            hi = r.chunk_index + self.context_after
            ordered = [chunks[i] for i in sorted(chunks) if lo <= i <= hi]
            passages.append(
                replace(r, text=_join_overlapping(ordered),
                        search_type=f"{r.search_type}+context")
            )
        return passages

    def get_stats(self) -> Dict:
        """
        Get vectorizer statistics
        Returns:
            Dictionary containing statistics
        """
        return {
            "bm25_stats": self.bm25_client.get_collection_stats() if self.bm25_client else {},
            "text_processor": {
                "chunk_size": self.text_processor.chunker.chunk_size,
                "chunk_overlap": self.text_processor.chunker.chunk_overlap,
            },
            "vector_generator": {
                "dense_model": self.dense_generator.model_name,
            },
        }
