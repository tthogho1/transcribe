import os
import json
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass

# 必要なライブラリ
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType
import numpy as np

from dotenv import load_dotenv

load_dotenv()


@dataclass
class ConversationChunk:
    """会話チャンクのデータクラス"""

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
    ):
        """
        初期化
        Args:
            zilliz_uri: Zilliz CloudのURI
            zilliz_token: Zilliz Cloudのトークン
            embedding_model: 使用する埋め込みモデル
        """
        self.zilliz_uri = zilliz_uri
        self.zilliz_token = zilliz_token
        self.embedding_model = SentenceTransformer(embedding_model)
        self.collection_name = "conversation_chunks"

        # テキスト分割器の初期化
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=300,  # チャンクサイズ
            chunk_overlap=50,  # オーバーラップ
            separators=["\n\n", "\n", "。", "！", "？", " ", ""],
        )

        self._connect_to_zilliz()
        self._setup_collection()

    def _connect_to_zilliz(self):
        """Zilliz Cloudに接続"""
        try:
            connections.connect(
                alias="default", uri=self.zilliz_uri, token=self.zilliz_token
            )
            print("✅ Zilliz Cloudに接続しました")
        except Exception as e:
            print(f"❌ Zilliz Cloud接続エラー: {e}")
            raise

    def _setup_collection(self):
        """コレクションの設定"""
        # フィールドスキーマの定義
        fields = [
            FieldSchema(
                name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True
            ),
            FieldSchema(
                name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768
            ),  # all-MiniLM-L6-v2の次元数
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=2000),
            FieldSchema(name="speaker", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="timestamp", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(name="original_length", dtype=DataType.INT64),
        ]

        schema = CollectionSchema(fields, "会話チャンクのコレクション")

        # コレクションの作成（既存の場合は削除）
        try:
            from pymilvus import utility

            if utility.has_collection(self.collection_name):
                utility.drop_collection(self.collection_name)

            self.collection = Collection(self.collection_name, schema)
            print(f"✅ コレクション '{self.collection_name}' を作成しました")
        except Exception as e:
            print(f"❌ コレクション作成エラー: {e}")
            raise

    def parse_monologue(self, text: str) -> List[Dict[str, Any]]:
        """
        一人語りのテキストを意味のある単位に分析
        Args:
            text: 一人語りのテキスト
        Returns:
            分割された内容のリスト
        """
        utterances = []

        # 改行で区切られている場合は段落単位で処理
        if "\n" in text:
            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
            for i, paragraph in enumerate(paragraphs):
                utterances.append(
                    {
                        "speaker": "Speaker",
                        "content": paragraph,
                        "timestamp": datetime.now().isoformat(),
                        "paragraph_index": i,
                    }
                )
        else:
            # 改行がない場合は句点で分割
            sentences = []
            current_sentence = ""

            for char in text:
                current_sentence += char
                if char in ["。", "！", "？"]:
                    if current_sentence.strip():
                        sentences.append(current_sentence.strip())
                        current_sentence = ""

            # 最後の文が句点で終わらない場合
            if current_sentence.strip():
                sentences.append(current_sentence.strip())

            for i, sentence in enumerate(sentences):
                utterances.append(
                    {
                        "speaker": "Speaker",
                        "content": sentence,
                        "timestamp": datetime.now().isoformat(),
                        "sentence_index": i,
                    }
                )

        return utterances

    def chunk_conversations(
        self, utterances: List[Dict[str, Any]]
    ) -> List[ConversationChunk]:
        """
        発話をチャンクに分割
        Args:
            utterances: 発話のリスト
        Returns:
            チャンクのリスト
        """
        chunks = []
        chunk_id = 0

        for utterance in utterances:
            content = utterance["content"]

            # 長い発話は分割
            if len(content) > 300:
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
            else:
                # 短い発話はそのまま
                chunks.append(
                    ConversationChunk(
                        id=f"chunk_{chunk_id:06d}",
                        text=content,
                        speaker=utterance["speaker"],
                        timestamp=utterance["timestamp"],
                        chunk_index=0,
                        original_length=len(content),
                    )
                )
                chunk_id += 1

        return chunks

    def generate_embeddings(self, chunks: List[ConversationChunk]) -> List[np.ndarray]:
        """
        チャンクのベクトル化
        Args:
            chunks: チャンクのリスト
        Returns:
            埋め込みベクトルのリスト
        """
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedding_model.encode(texts)
        print(f"✅ {len(chunks)}個のチャンクをベクトル化しました")
        return embeddings

    def insert_to_zilliz(
        self, chunks: List[ConversationChunk], embeddings: List[np.ndarray]
    ):
        """
        Zilliz Cloudにデータを挿入
        Args:
            chunks: チャンクのリスト
            embeddings: 埋め込みベクトルのリスト
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
            print(f"✅ {len(chunks)}個のチャンクをZilliz Cloudに保存しました")

            # インデックスの作成
            index_params = {
                "metric_type": "IP",  # Inner Product
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            }
            self.collection.create_index("embedding", index_params)
            self.collection.load()
            print("✅ インデックスを作成し、コレクションをロードしました")

        except Exception as e:
            print(f"❌ データ挿入エラー: {e}")
            raise

    def process_monologue(self, text: str):
        """
        一人語りテキストの全体処理
        Args:
            text: 一人語りのテキスト
        """
        print("🔄 一人語りテキストの処理を開始...")

        # 1. テキストの解析
        utterances = self.parse_monologue(text)
        print(f"📝 {len(utterances)}個の単位に分割しました")

        # 2. チャンク化
        chunks = self.chunk_conversations(utterances)
        print(f"✂️ {len(chunks)}個のチャンクに分割しました")

        # 3. ベクトル化
        embeddings = self.generate_embeddings(chunks)

        # 4. Zilliz Cloudに保存
        self.insert_to_zilliz(chunks, embeddings)

        print("🎉 処理が完了しました！")
        return chunks

    def search_similar(self, query: str, limit: int = 5) -> List[Dict]:
        """
        類似検索
        Args:
            query: 検索クエリ
            limit: 取得件数
        Returns:
            検索結果
        """
        # クエリのベクトル化
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


# 使用例
def main():
    # サンプル一人語りテキスト
    sample_monologue = """
今日は人工知能の発展について考えてみたいと思います。
近年、機械学習技術の進歩により、様々な分野で AI の活用が進んでいます。特に自然言語処理の分野では、大規模言語モデルの登場により、人間とほぼ同等の文章生成が可能になりました。

しかし、これらの技術にはまだ課題も多く存在します。データの品質やバイアスの問題、計算資源の大量消費、そして何より人間の雇用への影響などが懸念されています。

一方で、AI技術は医療診断の精度向上や、新薬開発の加速、気候変動対策など、人類の重要な課題解決にも大きく貢献する可能性を秘めています。重要なのは、技術の発展と人間社会の調和を保ちながら、持続可能な方法で AI を活用することだと考えています。
"""

    # 環境変数から認証情報を取得（実際の使用時）
    zilliz_uri = os.getenv("ZILLIZ_URI", "your-zilliz-uri")
    zilliz_token = os.getenv("ZILLIZ_TOKEN", "your-zilliz-token")

    try:
        # ベクトライザーの初期化
        vectorizer = ConversationVectorizer(zilliz_uri, zilliz_token)

        # 一人語りテキストの処理
        chunks = vectorizer.process_monologue(sample_monologue)

        # サンプル検索
        print("\n🔍 検索テスト:")
        results = vectorizer.search_similar("AIの課題", limit=3)
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['text'][:100]}... (スコア: {result['score']:.3f})")

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")


if __name__ == "__main__":
    main()
