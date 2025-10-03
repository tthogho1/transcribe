"""Embedding pipeline that pulls pending videos from DynamoDB, loads their
transcriptions from S3, generates embeddings via ConversationVectorizer, stores
them in Zilliz Cloud, and updates DynamoDB flags."""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Ensure project root is on the path before importing local modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in os.sys.path:
    os.sys.path.insert(0, PROJECT_ROOT)

from src.core.conversation_vectorizer import ConversationVectorizer


load_dotenv()


@dataclass
class VideoRecord:
    """Minimal representation of a video item we need to process."""

    video_id: str
    title: Optional[str] = None


class EmbeddingPipeline:
    """Pipeline orchestrating DynamoDB → S3 → Zilliz embedding generation."""

    def __init__(self, batch_size: int, dry_run: bool, log: logging.Logger):
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.logger = log

        aws_region = os.getenv("AWS_REGION")
        aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")

        if not aws_region:
            raise RuntimeError("AWS_REGION environment variable is required")

        session = boto3.Session(
            region_name=aws_region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret,
        )

        # DynamoDB setup
        table_name = os.getenv("DYNAMO_TABLE_NAME")
        if not table_name:
            raise RuntimeError("DYNAMO_TABLE_NAME environment variable is required")

        self.dynamodb_table = session.resource("dynamodb").Table(table_name)

        # S3 setup
        self.s3_client = session.client("s3")
        self.s3_bucket = os.getenv("S3_TRANSCRIPT_BUCKET", os.getenv("S3_BUCKET_NAME"))
        if not self.s3_bucket:
            raise RuntimeError(
                "S3_TRANSCRIPT_BUCKET or S3_BUCKET_NAME environment variable is required"
            )
        self.s3_prefix = os.getenv("S3_TRANSCRIPT_PREFIX", "")

        # Zilliz credentials
        zilliz_uri = os.getenv("ZILLIZ_URI")
        zilliz_token = os.getenv("ZILLIZ_TOKEN")

        if not zilliz_uri or not zilliz_token:
            raise RuntimeError(
                "ZILLIZ_URI and ZILLIZ_TOKEN environment variables are required"
            )

        # Conversation vectorizer handles chunking, embedding, and Zilliz insertion
        self.logger.info("🔧 Initializing ConversationVectorizer...")
        self.vectorizer = ConversationVectorizer(zilliz_uri, zilliz_token)
        self.logger.info("✅ ConversationVectorizer ready")

    # ------------------------------------------------------------------
    # DynamoDB helpers
    # ------------------------------------------------------------------
    def fetch_pending_videos(self) -> List[VideoRecord]:
        """Return video IDs where embedding flag is missing or false."""

        filter_expression = (
            Attr("embedding").not_exists()
            | Attr("embedding").eq(False)
            | Attr("embedding").eq(Decimal("0"))
        )

        projection = "video_id, title, embedding"

        results: List[VideoRecord] = []
        exclusive_start_key: Optional[Dict[str, Any]] = None

        while True:
            scan_kwargs: Dict[str, Any] = {
                "FilterExpression": filter_expression,
                "ProjectionExpression": projection,
            }
            if exclusive_start_key:
                scan_kwargs["ExclusiveStartKey"] = exclusive_start_key

            response = self.dynamodb_table.scan(**scan_kwargs)
            for item in response.get("Items", []):
                video_id = item.get("video_id")
                if not video_id:
                    continue
                results.append(VideoRecord(video_id=video_id, title=item.get("title")))

            exclusive_start_key = response.get("LastEvaluatedKey")
            if not exclusive_start_key or len(results) >= self.batch_size:
                break

        limited = results[: self.batch_size]
        self.logger.info("📋 Pending videos fetched: %d", len(limited))
        return limited

    def update_embedding_flag(self, video_id: str, success: bool) -> None:
        """Update embedding flag in DynamoDB."""

        if self.dry_run:
            self.logger.info("🔍 DRY RUN: Skipping DynamoDB update for %s", video_id)
            return

        try:
            self.dynamodb_table.update_item(
                Key={"video_id": video_id},
                UpdateExpression="SET embedding = :flag, embedding_updated_at = :ts",
                ExpressionAttributeValues={
                    ":flag": Decimal("1") if success else Decimal("0"),
                    ":ts": datetime.utcnow().isoformat(),
                },
            )
            self.logger.info(
                "📝 Updated embedding flag for %s -> %s",
                video_id,
                "success" if success else "failed",
            )
        except ClientError as exc:
            self.logger.error("❌ Failed to update DynamoDB for %s: %s", video_id, exc)

    # ------------------------------------------------------------------
    # S3 helpers
    # ------------------------------------------------------------------
    def download_transcription(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Download the transcription JSON for a given video."""

        key = f"{self.s3_prefix}{video_id}_transcription.json"
        try:
            response = self.s3_client.get_object(Bucket=self.s3_bucket, Key=key)
            body = response["Body"].read().decode("utf-8")
            return json.loads(body)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "NoSuchKey":
                self.logger.warning(
                    "⚠️ Transcription file not found for %s (%s)", video_id, key
                )
            else:
                self.logger.error("❌ S3 error for %s: %s", video_id, exc)
            return None
        except Exception as exc:
            self.logger.error(
                "❌ Failed to download transcription for %s: %s", video_id, exc
            )
            return None

    # ------------------------------------------------------------------
    # Text extraction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def extract_text(transcription: Dict[str, Any]) -> str:
        """Extract plain text from AWS Transcribe or Gladia style JSON."""

        text_fragments: List[str] = []

        # AWS Transcribe format
        results = transcription.get("results")
        if isinstance(results, dict):
            transcripts = results.get("transcripts")
            if isinstance(transcripts, list):
                for transcript in transcripts:
                    if isinstance(transcript, dict):
                        candidate = transcript.get("transcript")
                        if isinstance(candidate, str) and candidate.strip():
                            text_fragments.append(candidate.strip())

            # Some variants include items with alternatives
            items = results.get("items")
            if isinstance(items, list) and not text_fragments:
                words: List[str] = []
                for entry in items:
                    if isinstance(entry, dict):
                        alternatives = entry.get("alternatives")
                        if isinstance(alternatives, list) and alternatives:
                            top = alternatives[0]
                            if isinstance(top, dict):
                                word = top.get("content")
                                if isinstance(word, str):
                                    words.append(word)
                if words:
                    text_fragments.append(" ".join(words))

        # Gladia and custom formats
        transcription_field = transcription.get("transcription")
        if isinstance(transcription_field, str) and transcription_field.strip():
            text_fragments.append(transcription_field.strip())
        elif isinstance(transcription_field, dict):
            if "full_transcript" in transcription_field:
                candidate = transcription_field.get("full_transcript")
                if isinstance(candidate, str) and candidate.strip():
                    text_fragments.append(candidate.strip())
            if "text" in transcription_field:
                candidate = transcription_field.get("text")
                if isinstance(candidate, str) and candidate.strip():
                    text_fragments.append(candidate.strip())
            segments = (
                transcription_field.get("segments")
                if isinstance(transcription_field, dict)
                else None
            )
            segment_text = EmbeddingPipeline._join_segments(segments)
            if segment_text:
                text_fragments.append(segment_text)

        # Root level text or segments
        if isinstance(transcription.get("text"), str) and transcription["text"].strip():
            text_fragments.append(transcription["text"].strip())

        segment_text = EmbeddingPipeline._join_segments(transcription.get("segments"))
        if segment_text:
            text_fragments.append(segment_text)

        # Fallback: collect sizeable strings
        if not text_fragments:
            text_fragments = EmbeddingPipeline._collect_strings(transcription)

        combined = "\n".join(fragment for fragment in text_fragments if fragment)
        return combined.strip()

    @staticmethod
    def _join_segments(segments: Any) -> str:
        if not isinstance(segments, list):
            return ""
        texts: List[str] = []
        for segment in segments:
            if isinstance(segment, dict):
                text = segment.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
        return " \n".join(texts)

    @staticmethod
    def _collect_strings(data: Any, max_items: int = 20) -> List[str]:
        collected: List[str] = []

        def _walk(node: Any) -> None:
            if len(collected) >= max_items:
                return
            if isinstance(node, str):
                text = node.strip()
                if len(text) > 20:
                    collected.append(text)
                return
            if isinstance(node, dict):
                for value in node.values():
                    _walk(value)
            elif isinstance(node, list):
                for item in node:
                    _walk(item)

        _walk(data)
        return collected

    # ------------------------------------------------------------------
    # Main processing flow
    # ------------------------------------------------------------------
    def process_video(self, record: VideoRecord) -> bool:
        video_id = record.video_id
        self.logger.info("▶ Processing %s", video_id)

        transcription = self.download_transcription(video_id)
        if transcription is None:
            self.update_embedding_flag(video_id, False)
            return False

        text = self.extract_text(transcription)
        if not text:
            self.logger.warning("⚠️ No usable text extracted for %s", video_id)
            self.update_embedding_flag(video_id, False)
            return False

        if self.dry_run:
            self.logger.info(
                "🔍 DRY RUN: Skipping embedding generation for %s (text length=%d)",
                video_id,
                len(text),
            )
            self.update_embedding_flag(video_id, True)
            return True

        try:
            chunks = self.vectorizer.process_monologue(
                text, f"{video_id}_transcription.json"
            )
            success = bool(chunks)
        except Exception as exc:
            self.logger.error(
                "❌ Embedding generation failed for %s: %s", video_id, exc
            )
            success = False

        self.update_embedding_flag(video_id, success)
        return success

    def run(self) -> None:
        pending = self.fetch_pending_videos()
        if not pending:
            self.logger.info("🎉 No videos require embedding updates")
            return

        stats = {"total": len(pending), "success": 0, "failed": 0}

        for record in pending:
            if self.process_video(record):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        self.logger.info("===== Embedding run summary =====")
        self.logger.info("Total: %d", stats["total"])
        self.logger.info("Success: %d", stats["success"])
        self.logger.info("Failed: %d", stats["failed"])
        if stats["total"]:
            success_rate = (stats["success"] / stats["total"]) * 100
            self.logger.info("Success rate: %.1f%%", success_rate)


def configure_logging(level: str) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger("embedding_pipeline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate embeddings for videos with embedding=false in DynamoDB",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Maximum number of videos to process in this run (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without generating embeddings or updating DynamoDB",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = configure_logging(args.log_level)

    try:
        pipeline = EmbeddingPipeline(args.batch_size, args.dry_run, logger)
        pipeline.run()
    except KeyboardInterrupt:
        logger.warning("⏹️ Interrupted by user")
    except Exception as exc:
        logger.error("❌ Fatal error: %s", exc)
        raise


if __name__ == "__main__":
    main()
