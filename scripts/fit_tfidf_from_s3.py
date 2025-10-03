import os
import sys
import logging
import argparse
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv, find_dotenv

# Ensure 'src' folder is on sys.path so we can import 'services.*'
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from services.data.extract_text_fromS3 import S3JsonTextExtractor
from services.processing.text_processor import TextProcessor
from services.processing.tfidf_vectorizer import TfidfSparseVectorizer

try:
    import joblib
except Exception:
    joblib = None


def collect_corpus_from_s3(
    bucket: str,
    prefix: Optional[str],
    chunk_size: int,
    chunk_overlap: int,
    max_files: Optional[int],
) -> List[str]:
    extractor = S3JsonTextExtractor()
    keys = extractor.list_json_files_in_bucket(bucket, prefix or "")
    if max_files:
        keys = keys[:max_files]

    if not keys:
        raise RuntimeError(f"No JSON files found in s3://{bucket}/{prefix or ''}")

    tp = TextProcessor(chunk_size, chunk_overlap)

    corpus: List[str] = []
    for i, key in enumerate(keys, start=1):
        try:
            result = extractor.extract_text_from_s3_json(bucket, key)
            texts: List[str] = []

            if isinstance(result, dict) and "extracted_texts" in result:
                texts = [
                    d.get("text", "")
                    for d in result["extracted_texts"]
                    if d.get("text")
                ]
            else:
                # Fallbacks for common formats
                if isinstance(result, dict):
                    res = result.get("results")
                    if isinstance(res, dict):
                        tr = res.get("transcripts")
                        if isinstance(tr, list) and tr:
                            t = tr[0].get("transcript", "")
                            if t:
                                texts.append(t)
                    if not texts and "transcription" in result:
                        t = result.get("transcription") or ""
                        if t:
                            texts.append(t)
                    if not texts and "text" in result:
                        t = result.get("text") or ""
                        if t:
                            texts.append(t)

            if not texts:
                logging.debug(f"No text extracted: {key}")
                continue

            for t in texts:
                if not t or not t.strip():
                    continue
                chunks = tp.process_text(t, key)
                corpus.extend([ch.text for ch in chunks])

            logging.info(f"[{i}/{len(keys)}] loaded: {key} (texts={len(texts)})")

        except Exception as e:
            logging.warning(f"Skip due to error ({key}): {e}")

    if not corpus:
        raise RuntimeError("No chunks collected from S3 JSON files.")
    return corpus


def fit_and_save_tfidf(corpus: List[str], model_path: Path) -> None:
    if joblib is None:
        raise RuntimeError("joblib is not installed. Run: pip install joblib")

    vec = TfidfSparseVectorizer(
        max_features=10000,
        ngram_range=(1, 2),
        min_df=1,
        max_df=0.95,
        use_mecab=True,
    )

    # Use fit_transform to set is_fitted flag internally
    _ = vec.fit_transform(corpus)
    try:
        setattr(vec, "is_fitted", True)
    except Exception:
        pass

    model_path.parent.mkdir(parents=True, exist_ok=True)
    # Save only the sklearn vectorizer to avoid pickling fugashi/MeCab tagger
    if hasattr(vec, "save_sklearn"):
        vec.save_sklearn(str(model_path))
    else:
        base = getattr(vec, "vectorizer", None)
        if base is None:
            joblib.dump(vec, str(model_path))
        else:
            # Ensure tokenizer is not bound when pickling
            original_tokenizer = getattr(base, "tokenizer", None)
            try:
                base.tokenizer = None
                joblib.dump(base, str(model_path))
            finally:
                base.tokenizer = original_tokenizer


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fit TF-IDF using S3 JSON transcripts and save the model.",
    )
    default_bucket = os.getenv("S3_TRANSCRIPT_BUCKET", os.getenv("S3_BUCKET_NAME"))
    p.add_argument(
        "--bucket",
        type=str,
        default=default_bucket,
        help="S3 bucket name (default: env S3_TRANSCRIPT_BUCKET or S3_BUCKET_NAME)",
    )
    p.add_argument(
        "--prefix",
        type=str,
        default=os.getenv("S3_TRANSCRIPT_PREFIX", None),
        help="S3 prefix filter",
    )
    p.add_argument(
        "--model-path",
        type=str,
        default=os.getenv(
            "TFIDF_MODEL_PATH", str(ROOT / "artifacts" / "tfidf_vectorizer.joblib")
        ),
        help="Output path for joblib",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=int(os.getenv("CHUNK_SIZE", "300")),
        help="Chunk size in characters",
    )
    p.add_argument(
        "--chunk-overlap",
        type=int,
        default=int(os.getenv("CHUNK_OVERLAP", "50")),
        help="Chunk overlap in characters",
    )
    p.add_argument(
        "--max-files",
        type=int,
        default=int(os.getenv("TFIDF_BOOTSTRAP_MAX_FILES", "0") or "0"),
        help="Limit number of files to read (0=all)",
    )
    p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=os.getenv("LOG_LEVEL", "INFO"),
    )
    return p.parse_args()


def main():
    load_dotenv(find_dotenv(usecwd=True))
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if not args.bucket:
        raise RuntimeError("S3 bucket is required. Set --bucket or env S3_BUCKET_NAME.")

    max_files = None if args.max_files in (None, 0) else args.max_files

    logging.info("Start collecting corpus from S3...")
    corpus = collect_corpus_from_s3(
        bucket=args.bucket,
        prefix=args.prefix,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        max_files=max_files,
    )
    logging.info(f"Corpus collected. chunks={len(corpus)}")

    model_path = Path(args.model_path)
    logging.info(f"Fitting TF-IDF and saving to: {model_path}")
    fit_and_save_tfidf(corpus, model_path)
    logging.info("Done.")


if __name__ == "__main__":
    main()
