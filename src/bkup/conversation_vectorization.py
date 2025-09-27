import os
import json
from datetime import datetime
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

# Required libraries
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from pymilvus import (
    connections,
    Collection,
    FieldSchema,
    CollectionSchema,
    DataType,
    AnnSearchRequest,
    RRFRanker,
    Function,
    FunctionType,
)
import numpy as np

from extract_text_fromS3 import S3JsonTextExtractor

from dotenv import load_dotenv

load_dotenv()


@dataclass
class ConversationChunk:
    """Data class for conversation chunks"""

    id: str
    text: str
    speaker: str
    timestamp: str
    chunk_index: int
    original_length: int
    file_name: str  # New field to store the file name


class ConversationVectorizer:

    def __init__(
        self,
        zilliz_uri: str,
        zilliz_token: str,
        embedding_model: str = "sonoisa/sentence-bert-base-ja-mean-tokens-v2",
        chunk_size: int = 300,
        chunk_overlap: int = 50,
    ):
        """
        Initialization with hybrid search support
        Args:
            zilliz_uri: Zilliz Cloud URI
            zilliz_token: Zilliz Cloud token
            embedding_model: Embedding model to use
            chunk_size: Chunk size in characters
            chunk_overlap: Overlap size in characters
        """
        self.zilliz_uri = zilliz_uri
        self.zilliz_token = zilliz_token
        self.embedding_model = SentenceTransformer(embedding_model)
        self.collection_name = "conversation_chunks_hybrid"
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Initialize simple character-based text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,  # Maximum chunk size
            chunk_overlap=chunk_overlap,  # Overlap between chunks
            separators=[
                "\n\n",
                "\n",
                "。",
                "！",
                "？",
                " ",
                "",
            ],  # Recursive separators
        )

        self._connect_to_zilliz()
        self._setup_collection()

    def _connect_to_zilliz(self):
        """Connect to Zilliz Cloud"""
        try:
            connections.connect(
                alias="default", uri=self.zilliz_uri, token=self.zilliz_token
            )
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
            # デンスベクトル（意味的埋め込み）
            FieldSchema(name="dense_vector", dtype=DataType.FLOAT_VECTOR, dim=768),
            # スパースベクトル（BM25/TF-IDF）
            FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=2000),
            FieldSchema(name="speaker", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="timestamp", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(name="original_length", dtype=DataType.INT64),
            FieldSchema(
                name="file_name", dtype=DataType.VARCHAR, max_length=255
            ),  # Add file_name field
        ]

        schema = CollectionSchema(
            fields, "Collection for conversation chunks with hybrid search"
        )

        # Add BM25 function for automatic sparse vector generation
        # bm25_function = Function(
        #     name="text_bm25_emb",  # Function name
        #     input_field_names=[
        #         "text"
        #     ],  # Name of the VARCHAR field containing raw text data
        #     output_field_names=[
        #         "sparse_vector"
        #     ],  # Name of the SPARSE_FLOAT_VECTOR field reserved to store generated embeddings
        #     function_type=FunctionType.BM25,
        # )
        # schema.add_function(bm25_function)

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

    def parse_monologue(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse monologue text as a single unit for character-based chunking
        Args:
            text: Monologue text
        Returns:
            List of parsed content (single item containing entire text)
        """
        # Simply treat the entire text as one utterance
        # Character-based chunking will be handled in chunk_conversations method
        utterances = [
            {
                "speaker": "Speaker",
                "content": text.strip(),  # 全テキストを1つの発言として扱う
                "timestamp": datetime.now().isoformat(),
                "text_index": 0,
            }
        ]

        return utterances

    def chunk_conversations(
        self, utterances: List[Dict[str, Any]], file_name: str
    ) -> List[ConversationChunk]:
        """
        Split utterances into chunks using simple character-based splitting
        Args:
            utterances: List of utterances
            file_name: Name of the file being processed
        Returns:
            List of chunks
        """
        chunks = []
        chunk_id = 0

        for utterance in utterances:
            content = utterance["content"]

            # Always use character-based splitting regardless of length
            text_chunks = self.text_splitter.split_text(content)
            for i, chunk_text in enumerate(text_chunks):
                chunks.append(
                    ConversationChunk(
                        id=f"chunk_{chunk_id:06d}",
                        text=chunk_text,
                        speaker=utterance["speaker"],
                        timestamp=utterance["timestamp"],
                        chunk_index=i,
                        original_length=len(content),
                        file_name=file_name,  # Include file name
                    )
                )
                chunk_id += 1

        return chunks

    def tokenize_japanese(self, text: str) -> str:
        """
        Tokenize Japanese text using MeCab
        Args:
            text: Input text
        Returns:
            Tokenized text
        """
        if self.mecab:
            try:
                return self.mecab.parse(text).strip()
            except Exception as e:
                print(f"⚠️ MeCab tokenization error: {e}")
                return text
        else:
            # Simple fallback tokenization
            return text

    # BM25関数使用時は不要になったメソッド
    # def generate_sparse_vectors(self, texts: List[str]) -> sp.csr_matrix:
    #     """
    #     Generate sparse vectors (BM25/TF-IDF) for texts
    #     Args:
    #         texts: List of text strings
    #     Returns:
    #         Sparse matrix
    #     """
    #     # 日本語テキストの分かち書き
    #     tokenized_texts = [self.tokenize_japanese(text) for text in texts]

    #     # TF-IDF/BM25ベクトル生成
    #     sparse_vectors = self.sparse_vectorizer.fit_transform(tokenized_texts)

    #     print(f"✅ Generated sparse vectors: {sparse_vectors.shape}")
    #     return sparse_vectors

    # BM25関数使用時は不要になったメソッド
    # def sparse_matrix_to_dict(
    #     self, sparse_matrix: sp.csr_matrix
    # ) -> List[Dict[int, float]]:
    #     """
    #     Convert scipy sparse matrix to Zilliz sparse vector format
    #     Args:
    #         sparse_matrix: Scipy sparse matrix
    #     Returns:
    #         List of sparse vectors in Zilliz format
    #     """
    #     sparse_vectors = []

    #     for i in range(sparse_matrix.shape[0]):
    #         row = sparse_matrix.getrow(i)
    #         indices = row.indices
    #     data = row.data

    #         # Zillizのスパースベクトル形式: {index: value}
    #         sparse_dict = {int(idx): float(val) for idx, val in zip(indices, data)}
    #         sparse_vectors.append(sparse_dict)

    #     return sparse_vectors

    def generate_embeddings(
        self, chunks: List[ConversationChunk]
    ) -> Tuple[np.ndarray, List[Dict[int, float]]]:
        """
        Generate both dense and sparse embeddings
        Args:
            chunks: List of chunks
        Returns:
            Tuple of (dense_embeddings, sparse_embeddings)
        """
        texts = [chunk.text for chunk in chunks]

        # デンスベクトル（SentenceTransformer）
        dense_embeddings = self.embedding_model.encode(texts)
        # L2正規化
        dense_embeddings = dense_embeddings / np.linalg.norm(
            dense_embeddings, axis=1, keepdims=True
        )

        # スパースベクトルはBM25関数が自動生成するため、空のリストを使用
        sparse_embeddings = (
            []
        )  # BM25 function will generate sparse vectors automatically

        print(
            f"✅ Generated {len(chunks)} dense embeddings (sparse vectors auto-generated by BM25 function)"
        )
        return dense_embeddings, sparse_embeddings

    def insert_to_zilliz(
        self,
        chunks: List[ConversationChunk],
        dense_embeddings: np.ndarray,
        sparse_embeddings: List[Dict[int, float]],
    ):
        """
        Insert data with both dense and sparse vectors into Zilliz Cloud
        Args:
            chunks: List of chunks
            dense_embeddings: Dense embedding vectors
            sparse_embeddings: Sparse embedding vectors (not used with BM25 function)
        """
        # BM25関数使用時はsparse_vectorフィールドを除外（自動生成されるため）
        data = [
            [chunk.id for chunk in chunks],
            dense_embeddings.tolist(),
            # sparse_vectorフィールドは除外（BM25関数が自動生成）
            sparse_embeddings.tolist(),
            [chunk.text for chunk in chunks],
            [chunk.speaker for chunk in chunks],
            [chunk.timestamp for chunk in chunks],
            [chunk.chunk_index for chunk in chunks],
            [chunk.original_length for chunk in chunks],
            [chunk.file_name for chunk in chunks],
        ]

        # フィールド名もsparse_vectorを除外
        field_names = [
            "id",
            "dense_vector",
            "sparse_vector",  # BM25関数が自動生成するため除外
            "text",
            "speaker",
            "timestamp",
            "chunk_index",
            "original_length",
            "file_name",
        ]

        try:
            # フィールド名を指定してinsert
            self.collection.insert(data, field_names=field_names)
            print(f"✅ Saved {len(chunks)} chunks with hybrid vectors to Zilliz Cloud")

            # デンスベクトル用インデックス
            dense_index_params = {
                "metric_type": "IP",  # Inner Product
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            }
            self.collection.create_index("dense_vector", dense_index_params)

            # スパースベクトル用インデックス（BM25関数が自動作成する場合があるが、明示的に作成）
            sparse_index_params = {
                "index_type": "SPARSE_INVERTED_INDEX",
                "metric_type": "BM25",
            }
            self.collection.create_index("sparse_vector", sparse_index_params)

            self.collection.load()
            print("✅ Created hybrid indexes and loaded collection")

        except Exception as e:
            print(f"❌ Data insertion error: {e}")
            raise

    def process_monologue(self, text: str, file_name: str):
        """
        Complete processing with hybrid vectors
        Args:
            text: Monologue text
            file_name: Name of the file being processed
        """
        print("🔄 Starting hybrid monologue processing...")

        # 1. Parse text
        utterances = self.parse_monologue(text)
        print(f"📝 Split into {len(utterances)} units")

        # 2. Create chunks
        chunks = self.chunk_conversations(utterances, file_name)
        print(f"✂️ Split into {len(chunks)} chunks")

        # 3. Generate both dense and sparse embeddings
        dense_embeddings, sparse_embeddings = self.generate_embeddings(chunks)

        # 4. Save to Zilliz Cloud with hybrid vectors
        self.insert_to_zilliz(chunks, dense_embeddings, sparse_embeddings)

        print("🎉 Hybrid processing completed!")
        return chunks

    def hybrid_search(
        self, query: str, limit: int = 5, rerank_k: int = 100
    ) -> List[Dict]:
        """
        Official Zilliz hybrid search (Dense + Sparse vectors)
        Args:
            query: Search query
            limit: Number of final results
            rerank_k: Number of candidates for reranking
        Returns:
            Hybrid search results
        """
        try:
            # クエリのデンスベクトル生成
            dense_query = self.embedding_model.encode([query])
            dense_query = dense_query / np.linalg.norm(
                dense_query, axis=1, keepdims=True
            )

            # クエリのスパースベクトル生成 (BM25関数使用時はテキストを直接渡す)
            # BM25関数が自動的にsparseベクトルを生成するため、手動生成不要

            # デンス検索リクエスト
            dense_search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
            dense_req = AnnSearchRequest(
                data=[dense_query[0].tolist()],
                anns_field="dense_vector",
                param=dense_search_params,
                limit=rerank_k,
            )

            # スパース検索リクエスト (BM25関数使用時はクエリテキストを直接渡す)
            sparse_search_params = {"metric_type": "IP", "params": {}}
            sparse_req = AnnSearchRequest(
                data=[query],  # クエリテキストを直接渡す
                anns_field="sparse_vector",  # BM25関数が生成したフィールド
                param=sparse_search_params,
                limit=rerank_k,
            )

            # RRF (Reciprocal Rank Fusion) でランキング統合
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
                    {
                        "text": hit.entity.get("text"),
                        "speaker": hit.entity.get("speaker"),
                        "timestamp": hit.entity.get("timestamp"),
                        "file_name": hit.entity.get("file_name"),
                        "score": hit.score,
                        "search_type": "hybrid",
                    }
                )

            print(f"✅ Hybrid search returned {len(search_results)} results")
            return search_results

        except Exception as e:
            print(f"❌ Hybrid search error: {e}")
            # フォールバック：デンス検索のみ
            return self.search_similar(query, limit)

    def search_similar(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Dense vector similarity search (fallback method)
        Args:
            query: Search query
            limit: Number of results to return
        Returns:
            Search results
        """
        # Vectorize query and apply L2 normalization
        query_embedding = self.embedding_model.encode([query])
        query_embedding = query_embedding / np.linalg.norm(
            query_embedding, axis=1, keepdims=True
        )

        search_params = {"metric_type": "IP", "params": {"nprobe": 10}}

        try:
            results = self.collection.search(
                query_embedding,
                "dense_vector",  # Updated field name
                search_params,
                limit=limit,
                output_fields=["text", "speaker", "timestamp", "file_name"],
            )

            return [
                {
                    "text": hit.entity.get("text"),
                    "speaker": hit.entity.get("speaker"),
                    "timestamp": hit.entity.get("timestamp"),
                    "file_name": hit.entity.get("file_name"),
                    "score": hit.score,
                    "search_type": "dense",
                }
                for hit in results[0]
            ]
        except Exception as e:
            print(f"❌ Dense search error: {e}")
            return []


# Usage example
def main():
    print("🚀 Starting Conversation Vectorizer...")
    extractor = S3JsonTextExtractor()

    bucket_name = os.getenv("S3_BUCKET_NAME")
    json_files = extractor.list_json_files_in_bucket(bucket_name)

    # Get authentication info from environment variables (for actual use)
    zilliz_uri = os.getenv("ZILLIZ_URI", "your-zilliz-uri")
    zilliz_token = os.getenv("ZILLIZ_TOKEN", "your-zilliz-token")

    try:
        # Initialize with custom chunk size and overlap
        vectorizer = ConversationVectorizer(
            zilliz_uri,
            zilliz_token,
            chunk_size=200,  # 文字数ベースのチャンクサイズ
            chunk_overlap=40,  # オーバーラップサイズ
        )
        for json_file_key in json_files:
            print(f"Processing file: {json_file_key}")

            # Extract text from JSON file
            result = extractor.extract_text_from_s3_json(bucket_name, json_file_key)
            sample_monologue = result["extracted_texts"][0]["text"]
            chunks = vectorizer.process_monologue(sample_monologue, json_file_key)

    except Exception as e:
        print(f"❌ An error occurred: {e}")

    # Sample search
    print("\n🔍 Hybrid Search test:")
    hybrid_results = vectorizer.hybrid_search("仕事の楽しみ方", limit=3)
    for i, result in enumerate(hybrid_results, 1):
        print(
            f"{i}. [{result['search_type']}] {result['text'][:100]}... (Score: {result['score']:.3f})"
        )

    print("\n🔍 Dense Search test:")
    dense_results = vectorizer.search_similar("仕事の楽しみ方", limit=3)
    for i, result in enumerate(dense_results, 1):
        print(
            f"{i}. [{result['search_type']}] {result['text'][:100]}... (Score: {result['score']:.3f})"
        )


if __name__ == "__main__":
    main()
