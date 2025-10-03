import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv, find_dotenv

# Ensure src on path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from services.processing.tfidf_vectorizer import TfidfSparseVectorizer


def connect_collection() -> "Collection":
    from pymilvus import connections, Collection

    zilliz_uri = os.getenv("ZILLIZ_URI")
    zilliz_token = os.getenv("ZILLIZ_TOKEN")
    collection_name = os.getenv("ZILLIZ_COLLECTION", "conversation_chunks_hybrid")

    if not zilliz_uri or not zilliz_token:
        raise RuntimeError("ZILLIZ_URI and ZILLIZ_TOKEN are required in .env")

    connections.connect(alias="default", uri=zilliz_uri, token=zilliz_token)
    col = Collection(collection_name)
    try:
        col.load()
    except Exception:
        pass
    return col


def iter_rows(col, batch_size: int, output_fields: List[str]):
    """Yield rows in batches using query_iterator if available, else offset loop."""
    # Prefer query_iterator if available (pymilvus >= 2.5)
    if hasattr(col, "query_iterator"):
        it = col.query_iterator(
            expr=None, output_fields=output_fields, batch_size=batch_size
        )
        try:
            while True:
                batch = it.next()
                if not batch:
                    break
                yield batch
            return
        except Exception as e:
            logging.debug(f"query_iterator failed, falling back to offset: {e}")
        finally:
            try:
                it.close()
            except Exception:
                pass

    # Fallback: use offset pagination (may not be supported in all environments)
    offset = 0
    while True:
        try:
            rows = col.query(
                expr=None,
                output_fields=output_fields,
                limit=batch_size,
                offset=offset,
                consistency_level="Eventually",
            )
        except TypeError:
            raise RuntimeError(
                "Your Milvus/Zilliz version doesn't support offset or query_iterator. "
                "Please upgrade pymilvus or use a different pagination method."
            )
        if not rows:
            break
        yield rows
        offset += len(rows)


def upsert_rows(col, rows: List[Dict[str, Any]]):
    """Upsert rows if supported; otherwise delete + insert."""
    if not rows:
        return

    ids = [r["id"] for r in rows]
    dense = [r.get("dense_vector") for r in rows]
    sparse = [r.get("sparse_vector") for r in rows]
    text = [r.get("text", "") for r in rows]
    speaker = [r.get("speaker", "") for r in rows]
    timestamp = [r.get("timestamp", "") for r in rows]
    chunk_index = [r.get("chunk_index", 0) for r in rows]
    original_length = [r.get("original_length", 0) for r in rows]
    file_name = [r.get("file_name", "") for r in rows]

    data = [
        ids,
        dense,
        sparse,
        text,
        speaker,
        timestamp,
        chunk_index,
        original_length,
        file_name,
    ]

    if hasattr(col, "upsert"):
        col.upsert(data)
        return

    # Fallback: delete + insert
    quoted = ",".join([f'"{i}"' for i in ids])
    expr = f"id in [{quoted}]"
    col.delete(expr)
    col.insert(data)


def main():
    load_dotenv(find_dotenv(usecwd=True))
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    tfidf_model_path = os.getenv("TFIDF_MODEL_PATH")
    if not tfidf_model_path or not os.path.exists(tfidf_model_path):
        raise RuntimeError(
            "TFIDF_MODEL_PATH is not set or file not found. Please set it in .env and run the fit script first."
        )

    batch_size = int(os.getenv("SPARSE_REBUILD_BATCH", "500"))
    col = connect_collection()

    # Load TF-IDF model
    tfidf = TfidfSparseVectorizer.load_sklearn(
        tfidf_model_path,
        max_features=10000,
        ngram_range=(1, 2),
        min_df=1,
        max_df=0.95,
        use_mecab=True,
    )
    logging.info(f"Loaded TF-IDF model: {tfidf_model_path}")

    fields = [
        "id",
        "dense_vector",
        "sparse_vector",
        "text",
        "speaker",
        "timestamp",
        "chunk_index",
        "original_length",
        "file_name",
    ]

    processed = 0
    for rows in iter_rows(col, batch_size, fields):
        texts = [r.get("text", "") for r in rows]
        new_sparse = tfidf.transform(texts)

        # Replace sparse vectors
        for i, r in enumerate(rows):
            r["sparse_vector"] = new_sparse[i]

        upsert_rows(col, rows)
        processed += len(rows)
        logging.info(f"Updated sparse vectors: {processed}")

    try:
        col.flush()
    except Exception:
        pass

    logging.info("Done rebuilding sparse vectors.")


if __name__ == "__main__":
    main()
