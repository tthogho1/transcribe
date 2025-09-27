"""
Text processing utilities for conversation analysis
"""

import os
from datetime import datetime
from typing import List, Dict, Any
from langchain.text_splitter import RecursiveCharacterTextSplitter
from models.conversation_chunk import ConversationChunk


class JapaneseTokenizer:
    """Japanese text tokenizer using MeCab"""

    def __init__(self, enable_mecab: bool = False):
        """Initialize MeCab tokenizer"""
        self.mecab = None
        if enable_mecab:
            self._initialize_mecab()
        else:
            print("ℹ️ [JapaneseTokenizer] MeCab disabled ")

    def _initialize_mecab(self):
        """Initialize MeCab if available"""
        try:
            import MeCab

            print("🔧 [JapaneseTokenizer] Initializing MeCab...")
            self.mecab = MeCab.Tagger("-Owakati")
            print("✅ [JapaneseTokenizer] MeCab tokenizer initialized")
        except ImportError:
            print(
                "⚠️ [JapaneseTokenizer] MeCab not available, using default tokenization"
            )
        except Exception as e:
            print(f"❌ [JapaneseTokenizer] MeCab initialization failed: {e}")
            self.mecab = None

    def tokenize(self, text: str) -> str:
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


class TextChunker:
    """Text chunking utility for conversations"""

    def __init__(self, chunk_size: int = 300, chunk_overlap: int = 50):
        """
        Initialize text chunker
        Args:
            chunk_size: Maximum chunk size in characters
            chunk_overlap: Overlap size in characters
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Initialize character-based text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=[
                "\n\n",
                "\n",
                "。",
                "！",
                "？",
                " ",
                "",
            ],
        )

    def parse_monologue(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse monologue text as a single unit for character-based chunking
        Args:
            text: Monologue text
        Returns:
            List of parsed content (single item containing entire text)
        """
        utterances = [
            {
                "speaker": "Speaker",
                "content": text.strip(),
                "timestamp": datetime.now().isoformat(),
                "text_index": 0,
            }
        ]
        return utterances

    def chunk_conversations(
        self, utterances: List[Dict[str, Any]], file_name: str
    ) -> List[ConversationChunk]:
        """
        Split utterances into chunks using character-based splitting
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

            # Character-based splitting
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
                        file_name=file_name,
                    )
                )
                chunk_id += 1

        return chunks


class TextProcessor:
    """Main text processor combining tokenization and chunking"""

    def __init__(self, chunk_size: int = 300, chunk_overlap: int = 50):
        """
        Initialize text processor
        Args:
            chunk_size: Maximum chunk size in characters
            chunk_overlap: Overlap size in characters
        """
        self.tokenizer = JapaneseTokenizer(
            enable_mecab=False
        )  # Disable MeCab in JapaneseTokenizer
        self.chunker = TextChunker(chunk_size, chunk_overlap)

    def process_text(self, text: str, file_name: str) -> List[ConversationChunk]:
        """
        Complete text processing pipeline
        Args:
            text: Input text
            file_name: Name of the file being processed
        Returns:
            List of conversation chunks
        """
        print("📝 Processing text...")

        # 1. Parse text
        utterances = self.chunker.parse_monologue(text)
        print(f"Split into {len(utterances)} utterances")

        # 2. Create chunks
        chunks = self.chunker.chunk_conversations(utterances, file_name)
        print(f"✂️ Created {len(chunks)} chunks")

        return chunks

    def tokenize_text(self, text: str) -> str:
        """
        Tokenize text using Japanese tokenizer
        Args:
            text: Input text
        Returns:
            Tokenized text
        """
        return self.tokenizer.tokenize(text)
