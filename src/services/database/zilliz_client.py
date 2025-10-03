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
        """Setup collection with hybrid search support - create if doesn't exist"""
        try:
            from pymilvus import utility

            # Check if collection exists
            if not utility.has_collection(self.collection_name):
                print(
                    f"⚠️ Collection '{self.collection_name}' does not exist. Creating it..."
                )
                self._create_collection()
            else:
                # Connect to existing collection
                self.collection = Collection(self.collection_name)
                print(f"✅ Connected to existing collection '{self.collection_name}'")

            # Verify required indexes exist (for existing collections)
            if utility.has_collection(self.collection_name):
                try:
                    self._verify_required_indexes()
                except Exception as idx_err:
                    print(f"⚠️ Index verification failed: {idx_err}")
                    print("💡 This is normal for newly created collections")

            # Try to load collection
            try:
                self.collection.load()
                print("✅ Collection loaded successfully")
            except Exception as load_err:
                if "already loaded" in str(load_err).lower():
                    print("✅ Collection already loaded")
                else:
                    print(f"⚠️ Collection load warning: {load_err}")

        except Exception as e:
            print(f"❌ Collection setup error: {e}")
            raise

    def _create_collection(self):
        """Create new collection with hybrid search schema"""
        try:
            print(
                f"🔨 Creating collection '{self.collection_name}' with hybrid search schema..."
            )

            # Define schema fields
            fields = [
                FieldSchema(
                    name="id", dtype=DataType.VARCHAR, max_length=500, is_primary=True
                ),
                FieldSchema(
                    name="dense_vector", dtype=DataType.FLOAT_VECTOR, dim=768
                ),  # SentenceTransformer embedding dimension
                FieldSchema(
                    name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR
                ),  # TF-IDF sparse vector
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=2000),
                FieldSchema(name="speaker", dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name="timestamp", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(name="original_length", dtype=DataType.INT64),
                FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=500),
            ]

            # Create schema
            schema = CollectionSchema(
                fields=fields,
                description="Conversation chunks with hybrid (dense + sparse) vectors for Japanese text",
            )

            # Create collection
            self.collection = Collection(
                name=self.collection_name, schema=schema, using="default"
            )

            print(f"✅ Collection '{self.collection_name}' created successfully")
            print("📋 Schema:")
            print(f"   - id: Primary key (VARCHAR)")
            print(f"   - dense_vector: SentenceTransformer embeddings (768D)")
            print(f"   - sparse_vector: TF-IDF sparse vectors")
            print(
                f"   - text, speaker, timestamp, chunk_index, original_length, file_name"
            )

            # Create initial indexes for empty collection
            self._create_indexes_for_empty_collection()

        except Exception as e:
            print(f"❌ Collection creation error: {e}")
            raise

    def _verify_required_indexes(self):
        """Verify that required indexes exist"""
        try:
            indexes = self.collection.indexes
            existing_fields = [idx.field_name for idx in indexes] if indexes else []

            required_indexes = ["dense_vector", "sparse_vector"]
            missing_indexes = [
                field for field in required_indexes if field not in existing_fields
            ]

            if missing_indexes:
                raise Exception(
                    f"❌ Required indexes missing: {missing_indexes}. Please create them first."
                )

            print(f"✅ All required indexes exist: {existing_fields}")

        except Exception as e:
            print(f"❌ Index verification error: {e}")
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

            # Only create indexes if they don't exist yet
            self._create_indexes_if_needed()

        except Exception as e:
            print(f"❌ Data insertion error: {e}")
            raise

    def _create_indexes_for_empty_collection(self):
        """Create indexes for empty collection (called during setup)"""
        try:
            print("🔧 Creating initial indexes for empty collection...")

            # Dense vector index - use FLAT for small collections
            dense_index_params = {
                "metric_type": "IP",  # Inner Product for cosine similarity
                "index_type": "FLAT",  # Simple flat index for new collections
            }
            self.collection.create_index("dense_vector", dense_index_params)
            print("   ✅ Dense vector index created (FLAT/IP)")

            # Sparse vector index
            sparse_index_params = {
                "index_type": "SPARSE_INVERTED_INDEX",
                "metric_type": "IP",
            }
            self.collection.create_index("sparse_vector", sparse_index_params)
            print("   ✅ Sparse vector index created (SPARSE_INVERTED_INDEX/IP)")

            # Load collection
            self.collection.load()
            print("✅ Created initial indexes and loaded collection")

        except Exception as e:
            print(f"❌ Initial index creation error: {e}")
            print("💡 Indexes can be created later when data is inserted")
            # Don't raise - continue without indexes (they can be created later)

    def _create_indexes_if_needed(self):
        """Create indexes only if they don't exist yet"""
        try:
            # Check existing indexes
            indexes = self.collection.indexes
            existing_fields = [idx.field_name for idx in indexes] if indexes else []

            # Dense vector index
            if "dense_vector" not in existing_fields:
                print("🔧 Creating dense vector index...")
                dense_index_params = {
                    "metric_type": "IP",  # Inner Product
                    "index_type": "IVF_FLAT",
                    "params": {"nlist": 128},
                }
                self.collection.create_index("dense_vector", dense_index_params)
                print("   ✅ Dense vector index created")
            else:
                print("   ✅ Dense vector index already exists")

            # Sparse vector index
            if "sparse_vector" not in existing_fields:
                print("🔧 Creating sparse vector index...")
                sparse_index_params = {
                    "index_type": "SPARSE_INVERTED_INDEX",
                    "metric_type": "IP",
                }
                self.collection.create_index("sparse_vector", sparse_index_params)
                print("   ✅ Sparse vector index created")
            else:
                print("   ✅ Sparse vector index already exists")

            # Load collection if not loaded
            try:
                self.collection.load()
                print("✅ Collection loaded after index update")
            except Exception as load_err:
                if "already loaded" in str(load_err).lower():
                    print("✅ Collection already loaded")
                else:
                    print(f"⚠️ Load warning: {load_err}")

        except Exception as e:
            print(f"❌ Index update error: {e}")
            # Don't raise - data insertion was successful

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
        sparse_query: Dict[str, float],
        limit: int = 5,
        rerank_k: int = 100,
        alpha: float = 0.5,
    ) -> List[SearchResult]:
        """
        Perform hybrid search by independently searching dense and sparse,
        then fusing with Reciprocal Rank Fusion (RRF).
        - dense: weight alpha, sparse: weight (1-alpha)
        """
        try:
            if self.collection is None:
                print("❌ Hybrid search error: collection is not initialized")
                return []

            # Ensure parameters
            alpha = min(max(alpha, 0.0), 1.0)
            k = max(limit, rerank_k)

            out_fields = [
                "text",
                "speaker",
                "timestamp",
                "file_name",
                "chunk_index",
                "original_length",
            ]

            # Dense phase
            dense_params = {"metric_type": "IP", "params": {"nprobe": 16}}
            dense_hits = []
            try:
                dres = self.collection.search(
                    dense_query,
                    "dense_vector",
                    dense_params,
                    limit=k,
                    output_fields=out_fields,
                )
                if dres and dres[0]:
                    dense_hits = list(dres[0])
            except Exception as de:
                print(f"⚠️ Dense phase failed in hybrid: {de}")

            # Sparse phase
            sparse_params = {"metric_type": "IP", "params": {}}
            sparse_hits = []
            try:
                sres = self.collection.search(
                    [sparse_query],
                    "sparse_vector",
                    sparse_params,
                    limit=k,
                    output_fields=out_fields,
                )
                if sres and sres[0]:
                    sparse_hits = list(sres[0])
            except Exception as se:
                print(f"⚠️ Sparse phase failed in hybrid: {se}")

            # If only one side available, return it
            if not dense_hits and not sparse_hits:
                return []
            if dense_hits and not sparse_hits:
                return [
                    self._to_search_result(h, "hybrid[dense-only]")
                    for h in dense_hits[:limit]
                ]
            if sparse_hits and not dense_hits:
                return [
                    self._to_search_result(h, "hybrid[sparse-only]")
                    for h in sparse_hits[:limit]
                ]

            # Build rank maps (1-based ranks)
            def rank_map(hits):
                m = {}
                for i, h in enumerate(hits, start=1):
                    try:
                        key = h.id
                    except Exception:
                        # Fallback if .id isn't available
                        try:
                            key = h.entity.get("id")
                        except Exception:
                            key = str(i)
                    m[key] = i
                return m

            r_dense = rank_map(dense_hits)
            r_sparse = rank_map(sparse_hits)

            # RRF fusion
            K = 60.0
            candidates = set(r_dense.keys()) | set(r_sparse.keys())
            fused = {}
            for cid in candidates:
                s = 0.0
                rd = r_dense.get(cid)
                rs = r_sparse.get(cid)
                if rd is not None:
                    s += alpha * (1.0 / (K + rd))
                if rs is not None:
                    s += (1.0 - alpha) * (1.0 / (K + rs))
                fused[cid] = s

            # Map id -> hit
            hit_by_id = {}
            for h in dense_hits:
                try:
                    hit_by_id[h.id] = h
                except Exception:
                    pass
            for h in sparse_hits:
                try:
                    if h.id not in hit_by_id:
                        hit_by_id[h.id] = h
                except Exception:
                    pass

            # Sort and take top limit
            top_ids = sorted(fused.keys(), key=lambda x: fused[x], reverse=True)[:limit]
            results: List[SearchResult] = []
            for cid in top_ids:
                h = hit_by_id.get(cid)
                if h is None:
                    continue
                results.append(
                    self._to_search_result(h, "hybrid", override_score=fused[cid])
                )

            return results

        except Exception as e:
            print(f"❌ Hybrid search error: {e}")
            return []

    def _to_search_result(
        self, hit, search_type: str, override_score: float | None = None
    ) -> SearchResult:
        """Convert Milvus hit to SearchResult with safe fallbacks."""
        try:
            text = hit.entity.get("text", "")
        except Exception:
            try:
                text = hit.get("text", "")
            except Exception:
                text = ""
        try:
            speaker = hit.entity.get("speaker", "")
            timestamp = hit.entity.get("timestamp", "")
            file_name = hit.entity.get("file_name", "")
        except Exception:
            speaker = timestamp = file_name = ""

        score = (
            float(override_score)
            if override_score is not None
            else float(getattr(hit, "score", 0.0))
        )

        return SearchResult(
            text=text,
            speaker=speaker,
            timestamp=timestamp,
            file_name=file_name,
            score=score,
            similarity=score,
            search_type=search_type,
        )

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
                        similarity=hit.score,  # Use score as similarity for now
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
            # Basic stats
            try:
                stats = self.collection.describe()
            except Exception:
                stats = None

            try:
                num_entities = self.collection.num_entities
            except Exception:
                try:
                    num_entities = self.collection.num_entities()
                except Exception:
                    num_entities = None

            # is_loaded indicator
            try:
                is_loaded = getattr(self.collection, "is_loaded", None)
            except Exception:
                is_loaded = None

            # Index list (use utility.list_indexes where possible to avoid AmbiguousIndexName)
            index_list = []
            try:
                from pymilvus import utility

                try:
                    index_list = utility.list_indexes(self.collection_name)
                except Exception:
                    # Fallback to get_index_info or empty
                    try:
                        info = utility.get_index_info(self.collection_name)
                        index_list = info if info is not None else []
                    except Exception:
                        index_list = []
            except Exception:
                index_list = []

            return {
                "collection_name": self.collection_name,
                "schema": stats,
                "num_entities": num_entities,
                "is_loaded": is_loaded,
                "indexes": index_list,
            }
        except Exception as e:
            print(f"❌ Error getting collection stats: {e}")
            return {}
