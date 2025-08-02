"""
Simple import test script to verify the module structure
"""

import sys
import os
from pathlib import Path

# Add src to Python path
project_root = Path(__file__).parent.absolute()
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

print("🧪 Testing import structure...")
print(f"Python path: {sys.path[0]}")

try:
    print("1. Testing models import...")
    from models.conversation_chunk import (
        ConversationChunk,
        SearchResult,
        EmbeddingResult,
    )

    print("✅ Models imported successfully")

    print("2. Testing services import...")
    from services.processing.text_processor import TextProcessor

    print("✅ Text processor imported successfully")

    from services.processing.vector_generator import HybridVectorGenerator

    print("✅ Vector generator imported successfully")

    from services.database.zilliz_client import ZillizClient

    print("✅ Zilliz client imported successfully")

    from services.data.extract_text_fromS3 import S3JsonTextExtractor

    print("✅ S3 extractor imported successfully")

    print("3. Testing core import...")
    from core.conversation_vectorizer import ConversationVectorizer

    print("✅ Core vectorizer imported successfully")

    print("4. Testing API import...")
    from api.chat_server import app, socketio

    print("✅ Chat server imported successfully")

    print("\n🎉 All imports successful! The module structure is correct.")

except ImportError as e:
    print(f"❌ Import error: {e}")
    import traceback

    traceback.print_exc()
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback

    traceback.print_exc()
