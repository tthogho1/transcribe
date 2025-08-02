"""
Zilliz Cloud client for vector database operations
"""

import numpy as np
from typing import List, Dict, Any
from pymilvus import (
    connections,
    Collection,
    FieldSchema,
    CollectionSchema,
    DataType,
    AnnSearchRequest,
    RRFRanker,
)

from models.conversation_chunk import (
    ConversationChunk,
    SearchResult,
    EmbeddingResult,
)


class ZillizClient:
    """Zilliz Cloud client for database operations"""

    def __init__(
        self, uri: str, token: str, collection_name: str = "conversation_chunks_hybrid"
    ):
        """
        Initialize Zilliz client
        Args:
            uri: Zilliz Cloud URI
            token: Zilliz Cloud token
            collection_name: Collection name
        """
        self.uri = uri
        self.token = token
        self.collection_name = collection_name
        self.collection = None

        self._connect()
        self._setup_collection()

    def _connect(self):
        """Connect to Zilliz Cloud"""
        try:
            connections.connect(alias="default", uri=self.uri, token=self.token)
            print("✅ Connected to Zilliz Cloud")
        except Exception as e:
            print(f"❌ Zilliz Cloud connection error: {e}")
            raise

    def _setup_collection(self):
        """Set up collection with hybrid search support"""
        # Define field schema
        fields = [
            FieldSchema(
                name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True
            ),
            # Dense vector (semantic embeddings)
            FieldSchema(name="dense_vector", dtype=DataType.FLOAT_VECTOR, dim=768),
            # Sparse vector (BM25/TF-IDF)
            FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=2000),
            FieldSchema(name="speaker", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="timestamp", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(name="original_length", dtype=DataType.INT64),
            FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=255),
        ]

        schema = CollectionSchema(
            fields, "Collection for conversation chunks with hybrid search"
        )

        # Create collection (drop if exists)
        try:
            from pymilvus import utility

            if utility.has_collection(self.collection_name):
                utility.drop_collection(self.collection_name)

            self.collection = Collection(self.collection_name, schema)
            print(
                f"✅ Created collection '{self.collection_name}' with hybrid search support"
            )
        except Exception as e:
            print(f"❌ Collection creation error: {e}")
            raise

    def insert_data(self, chunks: List[ConversationChunk], embeddings: EmbeddingResult):
        """
        Insert data with both dense and sparse vectors into Zilliz Cloud
        Args:
            chunks: List of conversation chunks
            embeddings: Embedding results containing both dense and sparse vectors
        """
        data = [
            [chunk.id for chunk in chunks],
            embeddings.dense_embeddings.tolist(),
            embeddings.sparse_embeddings,
            [chunk.text for chunk in chunks],
            [chunk.speaker for chunk in chunks],
            [chunk.timestamp for chunk in chunks],
            [chunk.chunk_index for chunk in chunks],
            [chunk.original_length for chunk in chunks],
            [chunk.file_name for chunk in chunks],
        ]

        try:
            self.collection.insert(data)
            print(f"✅ Inserted {len(chunks)} chunks with hybrid vectors")

            self._create_indexes()

        except Exception as e:
            print(f"❌ Data insertion error: {e}")
            raise

    def _create_indexes(self):
        """Create indexes for both dense and sparse vectors"""
        try:
            # Dense vector index
            dense_index_params = {
                "metric_type": "IP",  # Inner Product
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            }
            self.collection.create_index("dense_vector", dense_index_params)

            # Sparse vector index
            sparse_index_params = {
                "index_type": "SPARSE_INVERTED_INDEX",
                "metric_type": "IP",
            }
            self.collection.create_index("sparse_vector", sparse_index_params)

            self.collection.load()
            print("✅ Created hybrid indexes and loaded collection")

        except Exception as e:
            print(f"❌ Index creation error: {e}")
            raise

    def hybrid_search(
        self,
        dense_query: np.ndarray,
        sparse_query: Dict[int, float],
        limit: int = 5,
        rerank_k: int = 100,
    ) -> List[SearchResult]:
        """
        Perform hybrid search using both dense and sparse vectors
        Args:
            dense_query: Dense query vector
            sparse_query: Sparse query vector
            limit: Number of final results
            rerank_k: Number of candidates for reranking
        Returns:
            List of search results
        """
        try:
            # Dense search request
            dense_search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
            dense_req = AnnSearchRequest(
                data=[dense_query[0].tolist()],
                anns_field="dense_vector",
                param=dense_search_params,
                limit=rerank_k,
            )

            # Sparse search request
            sparse_search_params = {"metric_type": "IP", "params": {}}
            sparse_req = AnnSearchRequest(
                data=[sparse_query],
                anns_field="sparse_vector",
                param=sparse_search_params,
                limit=rerank_k,
            )

            # RRF (Reciprocal Rank Fusion) ranking
            ranker = RRFRanker()

            results = self.collection.hybrid_search(
                reqs=[dense_req, sparse_req],
                ranker=ranker,
                limit=limit,
                output_fields=["text", "speaker", "timestamp", "file_name"],
            )

            search_results = []
            for hit in results[0]:
                search_results.append(
                    SearchResult(
                        text=hit.entity.get("text", ""),
                        speaker=hit.entity.get("speaker", ""),
                        timestamp=hit.entity.get("timestamp", ""),
                        file_name=hit.entity.get("file_name", ""),
                        score=hit.score,
                        search_type="hybrid",
                    )
                )

            print(f"✅ Hybrid search returned {len(search_results)} results")
            return search_results

        except Exception as e:
            print(f"❌ Hybrid search error: {e}")
            raise

    def dense_search(
        self, dense_query: np.ndarray, limit: int = 5
    ) -> List[SearchResult]:
        """
        Perform dense vector search only
        Args:
            dense_query: Dense query vector
            limit: Number of results to return
        Returns:
            List of search results
        """
        search_params = {"metric_type": "IP", "params": {"nprobe": 10}}

        try:
            results = self.collection.search(
                dense_query,
                "dense_vector",
                search_params,
                limit=limit,
                output_fields=["text", "speaker", "timestamp", "file_name"],
            )

            search_results = []
            for hit in results[0]:
                search_results.append(
                    SearchResult(
                        text=hit.entity.get("text", ""),
                        speaker=hit.entity.get("speaker", ""),
                        timestamp=hit.entity.get("timestamp", ""),
                        file_name=hit.entity.get("file_name", ""),
                        score=hit.score,
                        search_type="dense",
                    )
                )

            return search_results

        except Exception as e:
            print(f"❌ Dense search error: {e}")
            return []

    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get collection statistics
        Returns:
            Dictionary containing collection statistics
        """
        try:
            stats = self.collection.describe()
            num_entities = self.collection.num_entities

            return {
                "collection_name": self.collection_name,
                "schema": stats,
                "num_entities": num_entities,
                "is_loaded": self.collection.has_index(),
            }
        except Exception as e:
            print(f"❌ Error getting collection stats: {e}")
            return {}
