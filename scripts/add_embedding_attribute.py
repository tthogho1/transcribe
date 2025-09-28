#!/usr/bin/env python3
"""
DynamoDB Embedding Attribute Updater

DynamoDBテーブル内の全項目に新規属性'embedding'を追加するスクリプト
- transcribed = 1 の場合: embedding = true
- それ以外の場合: embedding = false
"""

import os
import sys
import json
import time
import argparse
import logging
from typing import Dict, List, Any, Optional
from decimal import Decimal

# 環境変数を読み込み
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    print("dotenv not available, using system environment variables")

# boto3をインポート
try:
    import boto3
    from boto3.dynamodb.conditions import Key, Attr
    from botocore.exceptions import ClientError, BotoCoreError
except ImportError as e:
    print(f"❌ boto3 is required. Install with: pip install boto3")
    sys.exit(1)


class DynamoDBEmbeddingUpdater:
    """DynamoDB embedding属性更新クラス"""

    def __init__(self, table_name: str, region: str = "ap-northeast-1"):
        """
        初期化

        Args:
            table_name: DynamoDBテーブル名
            region: AWSリージョン
        """
        self.table_name = table_name
        self.region = region

        # ロガー設定
        self.logger = logging.getLogger(__name__)

        try:
            # DynamoDBクライアント初期化
            self.dynamodb = boto3.resource("dynamodb", region_name=region)
            self.table = self.dynamodb.Table(table_name)

            # テーブル存在確認
            self._verify_table_exists()

        except Exception as e:
            self.logger.error(f"❌ DynamoDB initialization failed: {e}")
            raise

    def _verify_table_exists(self):
        """テーブル存在確認"""
        try:
            response = self.table.meta.client.describe_table(TableName=self.table_name)
            table_status = response["Table"]["TableStatus"]

            if table_status != "ACTIVE":
                raise ValueError(
                    f"Table {self.table_name} is not active. Status: {table_status}"
                )

            self.logger.info(f"✅ Table {self.table_name} is active")

        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                raise ValueError(f"Table {self.table_name} does not exist")
            else:
                raise

    def scan_all_items(self, dry_run: bool = False) -> List[Dict[str, Any]]:
        """
        テーブルの全アイテムをスキャンして取得

        Args:
            dry_run: ドライランモード

        Returns:
            全アイテムのリスト
        """
        items = []
        scan_kwargs = {}

        try:
            while True:
                response = self.table.scan(**scan_kwargs)
                items.extend(response.get("Items", []))

                # 次のページがある場合は継続
                last_evaluated_key = response.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    break

                scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

                if not dry_run:
                    # スキャン制限回避のため少し待機
                    time.sleep(0.1)

            self.logger.info(f"📊 Total items scanned: {len(items)}")
            return items

        except ClientError as e:
            self.logger.error(f"❌ Scan operation failed: {e}")
            raise

    def analyze_items(self, items: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        アイテムを分析して統計情報を取得

        Args:
            items: アイテムリスト

        Returns:
            統計情報辞書
        """
        stats = {
            "total_items": len(items),
            "transcribed_true": 0,
            "transcribed_false": 0,
            "transcribed_missing": 0,
            "embedding_exists": 0,
            "needs_update": 0,
        }

        for item in items:
            transcribed = item.get("transcribed")
            embedding = item.get("embedding")

            # transcribed値の分析
            if transcribed == 1:
                stats["transcribed_true"] += 1
            elif transcribed == 0:
                stats["transcribed_false"] += 1
            else:
                stats["transcribed_missing"] += 1

            # embedding属性の存在確認
            if "embedding" in item:
                stats["embedding_exists"] += 1
            else:
                stats["needs_update"] += 1

        return stats

    def print_analysis(self, stats: Dict[str, int]):
        """統計情報を表示"""
        print("\n📊 Analysis Results:")
        print(f"   Total items: {stats['total_items']:,}")
        print(f"   Transcribed (true/1): {stats['transcribed_true']:,}")
        print(f"   Transcribed (false/0): {stats['transcribed_false']:,}")
        print(f"   Transcribed (missing): {stats['transcribed_missing']:,}")
        print(f"   Embedding attribute exists: {stats['embedding_exists']:,}")
        print(f"   Items needing update: {stats['needs_update']:,}")
        print()

    def update_items_batch(
        self, items: List[Dict[str, Any]], dry_run: bool = False
    ) -> Dict[str, int]:
        """
        バッチ処理でアイテムを更新

        Args:
            items: 更新対象アイテムリスト
            dry_run: ドライランモード

        Returns:
            更新結果統計
        """
        results = {"success_count": 0, "error_count": 0, "skipped_count": 0}

        batch_size = 25  # DynamoDB batch_write_itemの制限

        for i in range(0, len(items), batch_size):
            batch_items = items[i : i + batch_size]

            if dry_run:
                self.logger.info(
                    f"[DRY RUN] Would update batch {i//batch_size + 1}: {len(batch_items)} items"
                )
                results["success_count"] += len(batch_items)
                continue

            try:
                self._update_batch(batch_items, results)

                # レート制限回避
                time.sleep(0.1)

            except Exception as e:
                self.logger.error(
                    f"❌ Batch update failed for items {i}-{i+len(batch_items)}: {e}"
                )
                results["error_count"] += len(batch_items)

        return results

    def _update_batch(self, batch_items: List[Dict[str, Any]], results: Dict[str, int]):
        """個別バッチの更新処理"""
        with self.table.batch_writer() as batch:
            for item in batch_items:
                try:
                    # 主キーを取得（video_idを想定）
                    video_id = item.get("video_id")
                    if not video_id:
                        self.logger.warning(f"⚠️ video_id missing in item: {item}")
                        results["skipped_count"] += 1
                        continue

                    # embedding値を決定
                    transcribed = item.get("transcribed", 0)
                    embedding_value = True if transcribed == 1 else False

                    # 更新処理
                    self.table.update_item(
                        Key={"video_id": video_id},
                        UpdateExpression="SET embedding = :embedding_val",
                        ExpressionAttributeValues={":embedding_val": embedding_value},
                    )

                    results["success_count"] += 1

                    if results["success_count"] % 100 == 0:
                        self.logger.info(
                            f"✅ Updated {results['success_count']} items so far..."
                        )

                except Exception as e:
                    self.logger.error(f"❌ Failed to update item {video_id}: {e}")
                    results["error_count"] += 1

    def run_update(self, dry_run: bool = False) -> bool:
        """
        メイン更新処理

        Args:
            dry_run: ドライランモード

        Returns:
            成功フラグ
        """
        try:
            self.logger.info(
                f"🚀 Starting embedding attribute update for table: {self.table_name}"
            )

            if dry_run:
                self.logger.info(
                    "🔍 Running in DRY RUN mode - no actual changes will be made"
                )

            # 1. 全アイテムスキャン
            self.logger.info("📋 Scanning all items...")
            items = self.scan_all_items(dry_run=dry_run)

            if not items:
                self.logger.warning("⚠️ No items found in table")
                return False

            # 2. アイテム分析
            stats = self.analyze_items(items)
            self.print_analysis(stats)

            # 3. 更新が必要かチェック
            if stats["needs_update"] == 0:
                self.logger.info("✅ All items already have embedding attribute")
                return True

            # 4. 更新実行
            self.logger.info(f"🔄 Updating {len(items)} items...")
            update_results = self.update_items_batch(items, dry_run=dry_run)

            # 5. 結果表示
            self._print_update_results(update_results, dry_run)

            return update_results["error_count"] == 0

        except Exception as e:
            self.logger.error(f"❌ Update process failed: {e}")
            return False

    def _print_update_results(self, results: Dict[str, int], dry_run: bool):
        """更新結果を表示"""
        mode_text = "[DRY RUN] " if dry_run else ""

        print(f"\n🎯 {mode_text}Update Results:")
        print(f"   ✅ Success: {results['success_count']:,}")
        print(f"   ❌ Errors: {results['error_count']:,}")
        print(f"   ⏭️  Skipped: {results['skipped_count']:,}")

        if results["error_count"] > 0:
            print(
                f"\n⚠️ {results['error_count']} items failed to update. Check logs for details."
            )
        else:
            print(f"\n🎉 {mode_text}All items updated successfully!")


def setup_logging(level: str = "INFO"):
    """ログ設定"""
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="Add embedding attribute to all DynamoDB items"
    )

    parser.add_argument(
        "--table-name",
        default=os.getenv("DYNAMO_TABLE_NAME", "YoutubeList"),
        help="DynamoDB table name (default: YoutubeList)",
    )

    parser.add_argument(
        "--region",
        default=os.getenv("AWS_REGION", "ap-northeast-1"),
        help="AWS region (default: ap-northeast-1)",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Run in dry-run mode (no actual changes)"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # ログ設定
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        # 更新処理実行
        updater = DynamoDBEmbeddingUpdater(args.table_name, args.region)
        success = updater.run_update(dry_run=args.dry_run)

        if success:
            logger.info("🎉 Embedding attribute update completed successfully!")
            sys.exit(0)
        else:
            logger.error("❌ Embedding attribute update failed!")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("🛑 Update process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
