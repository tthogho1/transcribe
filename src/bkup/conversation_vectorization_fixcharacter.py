import os
import json
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass

# Required libraries
from langchain.text_splitter import CharacterTextSplitter
from sentence_transformers import SentenceTransformer
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType
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
        Initialization
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
        self.collection_name = "conversation_chunks"
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Initialize simple character-based text splitter
        self.text_splitter = CharacterTextSplitter(
            chunk_size=chunk_size,  # 厳密な文字数制限
            chunk_overlap=chunk_overlap,  # オーバーラップサイズ
            separator="",  # 文字単位で分割（区切り文字なし）
            length_function=len,  # 文字数をカウント
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
        """Set up collection"""
        # Define field schema
        fields = [
            FieldSchema(
                name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True
            ),
            FieldSchema(
                name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768
            ),  # Embedding vector dimension
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=2000),
            FieldSchema(name="speaker", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="timestamp", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(name="original_length", dtype=DataType.INT64),
        ]

        schema = CollectionSchema(fields, "Collection for conversation chunks")

        # Create collection (drop if exists)
        try:
            from pymilvus import utility

            if utility.has_collection(self.collection_name):
                utility.drop_collection(self.collection_name)

            self.collection = Collection(self.collection_name, schema)
            print(f"✅ Created collection '{self.collection_name}'")
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
        self, utterances: List[Dict[str, Any]]
    ) -> List[ConversationChunk]:
        """
        Split utterances into chunks using simple character-based splitting
        Args:
            utterances: List of utterances
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
                    )
                )
                chunk_id += 1

        return chunks

    def generate_embeddings(self, chunks: List[ConversationChunk]) -> List[np.ndarray]:
        """
        Vectorize chunks
        Args:
            chunks: List of chunks
        Returns:
            List of embedding vectors
        """
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedding_model.encode(texts)
        print(f"✅ Vectorized {len(chunks)} chunks")
        return embeddings

    def insert_to_zilliz(
        self, chunks: List[ConversationChunk], embeddings: List[np.ndarray]
    ):
        """
        Insert data into Zilliz Cloud
        Args:
            chunks: List of chunks
            embeddings: List of embedding vectors
        """
        data = [
            [chunk.id for chunk in chunks],
            embeddings.tolist(),
            [chunk.text for chunk in chunks],
            [chunk.speaker for chunk in chunks],
            [chunk.timestamp for chunk in chunks],
            [chunk.chunk_index for chunk in chunks],
            [chunk.original_length for chunk in chunks],
        ]

        try:
            self.collection.insert(data)
            print(f"✅ Saved {len(chunks)} chunks to Zilliz Cloud")

            # Create index
            index_params = {
                "metric_type": "IP",  # Inner Product
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            }
            self.collection.create_index("embedding", index_params)
            self.collection.load()
            print("✅ Created index and loaded collection")

        except Exception as e:
            print(f"❌ Data insertion error: {e}")
            raise

    def process_monologue(self, text: str):
        """
        Complete processing of monologue text
        Args:
            text: Monologue text
        """
        print("🔄 Starting monologue text processing...")

        # 1. Parse text
        utterances = self.parse_monologue(text)
        print(f"📝 Split into {len(utterances)} units")

        # 2. Create chunks
        chunks = self.chunk_conversations(utterances)
        print(f"✂️ Split into {len(chunks)} chunks")

        # 3. Vectorize
        embeddings = self.generate_embeddings(chunks)

        # 4. Save to Zilliz Cloud
        self.insert_to_zilliz(chunks, embeddings)

        print("🎉 Processing completed!")
        return chunks

    def search_similar(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Similarity search
        Args:
            query: Search query
            limit: Number of results to return
        Returns:
            Search results
        """
        # Vectorize query
        query_embedding = self.embedding_model.encode([query])

        search_params = {"metric_type": "IP", "params": {"nprobe": 10}}

        results = self.collection.search(
            query_embedding,
            "embedding",
            search_params,
            limit=limit,
            output_fields=["text", "speaker", "timestamp"],
        )

        return [
            {
                "text": hit.entity.get("text"),
                "speaker": hit.entity.get("speaker"),
                "timestamp": hit.entity.get("timestamp"),
                "score": hit.score,
            }
            for hit in results[0]
        ]


# Usage example
def main():

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
            chunks = vectorizer.process_monologue(sample_monologue)

    except Exception as e:
        print(f"❌ An error occurred: {e}")

    # Sample search
    print("\n🔍 Search test:")
    results = vectorizer.search_similar("仕事の楽しみ方", limit=3)
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['text'][:100]}... (Score: {result['score']:.3f})")


if __name__ == "__main__":
    main()
