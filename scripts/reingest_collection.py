"""Rebuild the transcript index into a new Zilliz collection.

Reads every {video_id}_transcription.json from S3, extracts the text with the
same extract_text() as generate_embeddings_with_vectorizer.py, chunks and
embeds it with the same ConversationVectorizer, and inserts the chunks into
the collection given by --collection (created automatically if missing).

Unlike generate_embeddings_with_vectorizer.py, this script:
  - processes every transcript, not only videos with embedding=false
  - never changes the DynamoDB transcribed/embedding flags
  - inserts in batches and refuses to write into the live collection
    (conversation_chunks_bm25_v2, which the chat server on the HF Space uses), so
    a forgotten or mistyped name can't mix new chunks into the index users
    are searching

Usage (from the project root):
  python scripts/reingest_collection.py --collection conversation_chunks_bm25_v3 --dry-run --limit 5
  python scripts/reingest_collection.py --collection conversation_chunks_bm25_v3 --limit 5
  python scripts/reingest_collection.py --collection conversation_chunks_bm25_v3 --resume

--resume skips videos that already have chunks in the target collection, so
an interrupted run can be continued. Videos are inserted whole (a batch never
splits a video), so a video is either fully present or absent.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Dict, List, Set

import boto3
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from core.conversation_vectorizer import ConversationVectorizer  # noqa: E402
from generate_embeddings_with_vectorizer import EmbeddingPipeline  # noqa: E402
from pymilvus import MilvusClient  # noqa: E402

logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

LIVE_COLLECTION = "conversation_chunks_bm25_v2"
SUFFIX = "_transcription.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Re-embed all transcripts into a new Zilliz collection")
    p.add_argument("--collection", required=True, help="Target collection (must not be the live one)")
    p.add_argument("--bucket", default=os.getenv("S3_TRANSCRIPT_BUCKET", "audio4gladia"))
    p.add_argument("--limit", type=int, default=0, help="Process only the first N videos (0 = all)")
    p.add_argument("--batch-chunks", type=int, default=500,
                   help="Insert once at least this many chunks are buffered (default 500)")
    p.add_argument("--resume", action="store_true",
                   help="Skip videos that already have chunks in the target collection")
    p.add_argument("--dry-run", action="store_true",
                   help="Download, extract, chunk and embed, but do not connect to or write Zilliz")
    return p.parse_args()


def list_transcript_keys(bucket: str) -> List[str]:
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION"))
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        keys += [o["Key"] for o in page.get("Contents", []) if o["Key"].endswith(SUFFIX)]
    return sorted(keys)


def load_titles() -> Dict[str, str]:
    table_name = os.getenv("DYNAMO_TABLE_NAME")
    if not table_name:
        sys.exit("DYNAMO_TABLE_NAME is not set.")
    table = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION")).Table(table_name)
    titles, kwargs = {}, {"ProjectionExpression": "video_id, title"}
    while True:
        resp = table.scan(**kwargs)
        for item in resp["Items"]:
            titles[item["video_id"]] = item.get("title") or ""
        if "LastEvaluatedKey" not in resp:
            return titles
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def existing_file_names(client: MilvusClient, collection: str) -> Set[str]:
    names: Set[str] = set()
    it = client.query_iterator(collection, filter="chunk_index >= 0",
                               output_fields=["file_name"], batch_size=1000)
    while True:
        batch = it.next()
        if not batch:
            it.close()
            return names
        names.update(row["file_name"] for row in batch)


def main() -> None:
    args = parse_args()
    if args.collection == LIVE_COLLECTION:
        sys.exit(f"Refusing to write into the live collection '{LIVE_COLLECTION}'. "
                 "Use a new name such as conversation_chunks_bm25_v3.")

    uri, token = os.getenv("ZILLIZ_URI"), os.getenv("ZILLIZ_TOKEN")
    if not args.dry_run and not (uri and token):
        sys.exit("ZILLIZ_URI / ZILLIZ_TOKEN are not set.")

    keys = list_transcript_keys(args.bucket)
    titles = load_titles()
    print(f"📋 {len(keys)} transcripts in s3://{args.bucket}, {len(titles)} titles in DynamoDB")

    # With zilliz_uri=None the vectorizer only loads the embedding model, so a
    # dry run never creates the target collection.
    vectorizer = ConversationVectorizer(
        None if args.dry_run else uri, token,
        bm25_collection_name=args.collection, reranker_model="",
    )
    if not args.dry_run and not vectorizer.bm25_client:
        sys.exit("Could not connect to Zilliz.")

    client = None if args.dry_run else MilvusClient(uri=uri, token=token)
    if args.resume and client:
        done = existing_file_names(client, args.collection)
        before = len(keys)
        keys = [k for k in keys if k not in done]
        print(f"⏭️  --resume: {before - len(keys)} videos already in '{args.collection}', skipping them")
    elif args.resume:
        print("ℹ️  --resume is ignored in a dry run (Zilliz is not contacted)")
    if args.limit:
        keys = keys[: args.limit]

    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION"))
    buf_chunks, buf_vecs = [], []
    stats = {"videos": 0, "chunks": 0, "skipped": [], "inserted_batches": 0}
    started = time.perf_counter()

    def flush_buffer() -> None:
        if not buf_chunks or args.dry_run:
            buf_chunks.clear(); buf_vecs.clear()
            return
        vectorizer.bm25_client.insert_data(list(buf_chunks), np.vstack(buf_vecs))
        stats["inserted_batches"] += 1
        buf_chunks.clear(); buf_vecs.clear()

    for n, key in enumerate(keys, 1):
        video_id = key[: -len(SUFFIX)]
        try:
            body = s3.get_object(Bucket=args.bucket, Key=key)["Body"].read()
            text = EmbeddingPipeline.extract_text(json.loads(body))
        except Exception as e:
            print(f"⚠️  [{n}/{len(keys)}] {video_id}: could not read transcript ({e}); skipped")
            stats["skipped"].append(video_id)
            continue
        if not text:
            print(f"⚠️  [{n}/{len(keys)}] {video_id}: empty transcript; skipped")
            stats["skipped"].append(video_id)
            continue

        chunks = vectorizer.text_processor.process_text(text, key, titles.get(video_id, ""))
        vecs = vectorizer.vector_generator.dense_generator.generate([c.text for c in chunks])
        buf_chunks.extend(chunks)
        buf_vecs.append(vecs)
        stats["videos"] += 1
        stats["chunks"] += len(chunks)
        print(f"   [{n}/{len(keys)}] {video_id}: {len(text)} chars -> {len(chunks)} chunks")

        if len(buf_chunks) >= args.batch_chunks:
            flush_buffer()

    flush_buffer()
    elapsed = time.perf_counter() - started

    print("\n===== Re-ingest summary =====")
    print(f"Target collection : {args.collection}{' (dry run, nothing written)' if args.dry_run else ''}")
    print(f"Videos processed  : {stats['videos']}")
    print(f"Chunks            : {stats['chunks']}")
    print(f"Skipped           : {len(stats['skipped'])} {stats['skipped'][:10]}")
    print(f"Insert batches    : {stats['inserted_batches']}")
    print(f"Elapsed           : {elapsed / 60:.1f} min")
    if client:
        rows = client.get_collection_stats(args.collection).get("row_count")
        videos = len(existing_file_names(client, args.collection))
        print(f"Collection now    : {rows} rows, {videos} videos")


if __name__ == "__main__":
    main()
