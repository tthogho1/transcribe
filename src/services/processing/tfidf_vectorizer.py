"""
TF-IDF based sparse vector generator for Japanese text
"""

import re
import numpy as np
import os
from typing import List, Dict
from sklearn.feature_extraction.text import TfidfVectorizer
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()

IPA_DIC_FOLDER = os.getenv("IPA_DIC_FOLDER", "C:/mecab/dic/ipadic")

# Try to import MeCab for Japanese tokenization
try:
    import fugashi

    MECAB_AVAILABLE = True
    print("✅ fugashi available for Japanese tokenization")
except ImportError:
    try:
        import MeCab

        MECAB_AVAILABLE = True
        print("✅ MeCab available for Japanese tokenization")
    except ImportError:
        MECAB_AVAILABLE = False
        print("⚠️ MeCab/fugashi not available, using simple tokenization")


class TfidfSparseVectorizer:
    """TF-IDF based sparse vector generator for Japanese text"""

    def __init__(
        self,
        max_features: int = 10000,
        ngram_range: tuple = (1, 2),
        min_df: int = 1,
        max_df: float = 0.95,
        use_mecab: bool = True,
    ):
        """
        Initialize TF-IDF sparse vectorizer
        Args:
            max_features: Maximum number of features
            ngram_range: Range of n-grams to extract
            min_df: Minimum document frequency
            max_df: Maximum document frequency
            use_mecab: Whether to use MeCab for Japanese tokenization
        """
        self.max_features = max_features
        self.ngram_range = ngram_range
        self.min_df = min_df
        self.max_df = max_df
        self.use_mecab = use_mecab and MECAB_AVAILABLE

        # Initialize MeCab
        self.mecab = None
        if self.use_mecab:
            try:
                print("🔧 [TfidfSparseVectorizer] Initializing MeCab...")
                # Try fugashi with unidic first
                try:
                    import fugashi
                    import unidic

                    # Try different initialization methods
                    try:
                        # Method 1: Use unidic's default setup
                        self.mecab = fugashi.Tagger("-r /dev/null")
                        print(
                            "✅ [TfidfSparseVectorizer] fugashi with UniDic (method 1) initialized"
                        )
                    except Exception as tagger_error:
                        # Method 2: Simple initialization (fugashi should find unidic automatically)
                        print(f"⚠️ Method 1 failed: {tagger_error}")
                        try:
                            self.mecab = fugashi.Tagger()
                            print(
                                "✅ [TfidfSparseVectorizer] fugashi with UniDic (method 2) initialized"
                            )
                        except Exception as method2_error:
                            print(f"❌ Method 2 also failed: {method2_error}")
                            raise method2_error
                except ImportError:
                    import MeCab

                    self.mecab = MeCab.Tagger("-Owakati")
                    print("✅ [TfidfSparseVectorizer] MeCab tokenizer initialized")
            except Exception as e:
                print(f"❌ [TfidfSparseVectorizer] MeCab initialization failed: {e}")
                print("ℹ️ [TfidfSparseVectorizer] Falling back to simple tokenization")
                self.use_mecab = False

        # Initialize TF-IDF vectorizer
        self.vectorizer = TfidfVectorizer(
            max_features=self.max_features,
            ngram_range=self.ngram_range,
            min_df=self.min_df,
            max_df=self.max_df,
            tokenizer=self._tokenize_japanese if self.use_mecab else None,
            lowercase=True,
            stop_words=None,
        )

        self.is_fitted = False
        print("✅ TfidfSparseVectorizer initialized")

    def _tokenize_japanese(self, text: str) -> List[str]:
        """Tokenize Japanese text using MeCab with UniDic"""
        if not self.mecab:
            return text.split()

        try:
            # Clean text
            text = re.sub(r"[^\w\s]", "", text)
            text = re.sub(r"\s+", " ", text).strip()

            # Check if using fugashi (supports better parsing)
            try:
                # fugashi with detailed parsing - extract surface forms only
                tokens = []
                for word in self.mecab(text):
                    surface = word.surface.strip()
                    if len(surface) > 1 and not surface.isdigit() and surface != "EOS":
                        tokens.append(surface)
                return tokens
            except:
                # Standard MeCab parsing fallback
                result = self.mecab.parse(text).strip()
                tokens = result.split() if result else []

                # Filter tokens
                filtered_tokens = []
                for token in tokens:
                    if len(token) > 1 and not token.isdigit():
                        filtered_tokens.append(token)

                return filtered_tokens

        except Exception as e:
            print(f"⚠️ Tokenization error: {e}")
            return text.split()

    def fit_transform(self, texts: List[str]) -> List[Dict[int, float]]:
        """Fit and transform texts to sparse vectors"""
        try:
            sparse_matrix = self.vectorizer.fit_transform(texts)
            self.is_fitted = True
            sparse_vectors = self._sparse_matrix_to_dict_list(sparse_matrix)

            print(
                f"✅ TF-IDF vectorizer fitted with {len(self.vectorizer.vocabulary_)} features"
            )
            print(f"✅ Generated {len(sparse_vectors)} sparse vectors")

            return sparse_vectors

        except Exception as e:
            print(f"❌ TF-IDF fit_transform error: {e}")
            return []

    def transform(self, texts: List[str]) -> List[Dict[int, float]]:
        """Transform texts to sparse vectors"""
        if not self.is_fitted:
            print("⚠️ TF-IDF vectorizer not fitted")
            return []

        try:
            sparse_matrix = self.vectorizer.transform(texts)
            sparse_vectors = self._sparse_matrix_to_dict_list(sparse_matrix)
            return sparse_vectors

        except Exception as e:
            print(f"❌ TF-IDF transform error: {e}")
            return []

    def _sparse_matrix_to_dict_list(self, sparse_matrix) -> List[Dict[int, float]]:
        """Convert scipy sparse matrix to list of dictionaries"""
        sparse_vectors = []

        for i in range(sparse_matrix.shape[0]):
            row = sparse_matrix.getrow(i)
            sparse_dict = {}

            for j in range(row.nnz):
                col_idx = row.indices[j]
                value = row.data[j]
                if value > 0:
                    sparse_dict[col_idx] = float(value)

            sparse_vectors.append(sparse_dict)

        return sparse_vectors

    def get_vocabulary_size(self) -> int:
        """Get vocabulary size"""
        return len(self.vectorizer.vocabulary_) if self.is_fitted else 0
