#!/usr/bin/env python3
"""
S3バケットからファイル一覧を取得し、DynamoDBのtranscribe属性をtrueに設定するスクリプト

使用方法:
    python scripts/update_transcribe_status.py [OPTIONS]

例:
    # 全ファイルを対象に実行
    python scripts/update_transcribe_status.py

    # 特定のプレフィックスのファイルのみ対象
    python scripts/update_transcribe_status.py --prefix audio4output/

    # ドライランモード（実際には更新しない）
    python scripts/update_transcribe_status.py --dry-run

    # バッチサイズを指定
    python scripts/update_transcribe_status.py --batch-size 50
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# 必要なモジュールをインポート
from services.data.extract_text_fromS3 import S3JsonTextExtractor
from services.database.youtube_dynamodb_client import YouTubeDynamoDBClient

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TranscribeStatusUpdater:
    """S3ファイル一覧からDynamoDBのtranscribe属性を更新するクラス"""

    def __init__(self, table_name: Optional[str] = None):
        """
        初期化

        Args:
            table_name: DynamoDBテーブル名（指定しない場合は環境変数から取得）
        """
        # 環境変数を読み込み
        load_dotenv()

        # S3クライアント初期化
        self.s3_extractor = S3JsonTextExtractor()

        # DynamoDBクライアント初期化
        if table_name is None:
            table_name = os.getenv("YOUTUBE_DYNAMODB_TABLE", "youtube_videos")

        self.dynamo_client = YouTubeDynamoDBClient(table_name)

        # 設定
        self.s3_bucket = os.getenv("S3_BUCKET_NAME")
        if not self.s3_bucket:
            raise ValueError("S3_BUCKET_NAME環境変数が設定されていません")

        # AWS設定情報をログ出力
        aws_region = os.getenv("AWS_REGION", "ap-northeast-1")
        logger.info(f"📦 S3バケット名: {self.s3_bucket}")
        logger.info(f"🌍 AWSリージョン: {aws_region}")
        logger.info(f"🗃️ DynamoDBテーブル: {table_name}")
        logger.info(f"🔧 設定完了: S3とDynamoDBクライアントを初期化しました")

    def extract_video_id_from_key(self, s3_key: str) -> str:
        """
        S3キーからビデオIDを抽出

        Args:
            s3_key: S3オブジェクトキー (例: "audio4output/Rkpqhl5l9d0_transcription.json")

        Returns:
            ビデオID (例: "Rkpqhl5l9d0")
        """
        # ファイル名を取得
        filename = os.path.basename(s3_key)

        # 拡張子を除去
        name_without_ext = os.path.splitext(filename)[0]

        # "_transcription"で分割して最初の部分をvideo_idとする
        if "_transcription" in name_without_ext:
            video_id = name_without_ext.split("_transcription")[0]
        else:
            # "_transcription"が含まれていない場合は拡張子除去のみ（後方互換性）
            video_id = name_without_ext

        return video_id

    def get_s3_files(self, prefix: str = "") -> List[str]:
        """
        S3バケットからJSONファイル一覧を取得

        Args:
            prefix: 検索対象のプレフィックス

        Returns:
            S3キーのリスト
        """
        logger.info(f"📂 S3ファイル一覧を取得中...")
        logger.info(f"   バケット: {self.s3_bucket}")
        logger.info(f"   プレフィックス: '{prefix}' (空の場合は全ファイル)")

        json_files = self.s3_extractor.list_json_files_in_bucket(self.s3_bucket, prefix)

        logger.info(f"✅ 発見したJSONファイル数: {len(json_files)} 件")
        if len(json_files) > 0:
            logger.info(
                f"   例: {json_files[0]}"
                + (f", {json_files[1]}" if len(json_files) > 1 else "")
            )
        return json_files

    def update_transcribe_status(
        self, video_ids: List[str], batch_size: int = 25, dry_run: bool = False
    ) -> dict:
        """
        複数のビデオIDに対してtranscribe属性をtrueに設定

        Args:
            video_ids: ビデオIDのリスト
            batch_size: バッチ処理サイズ
            dry_run: ドライランモード（実際には更新しない）

        Returns:
            処理結果の統計
        """
        stats = {
            "total": len(video_ids),
            "processed": 0,
            "updated": 0,
            "failed": 0,
            "already_transcribed": 0,
            "not_found": 0,
        }

        logger.info(f"transcribe属性の更新を開始... (対象: {stats['total']}件)")
        if dry_run:
            logger.info("🔍 DRY RUN MODE - 実際の更新は行いません")

        # バッチ処理
        for i in range(0, len(video_ids), batch_size):
            batch = video_ids[i : i + batch_size]
            logger.info(
                f"バッチ処理中 ({i+1}-{min(i+batch_size, len(video_ids))}/{len(video_ids)})"
            )

            for video_id in batch:
                stats["processed"] += 1

                try:
                    if dry_run:
                        # ドライランモード：レコードの存在確認のみ
                        record = self.dynamo_client.get_video_by_id(video_id)
                        if record:
                            if record.transcribed:
                                stats["already_transcribed"] += 1
                                logger.debug(f"✅ {video_id}: すでにtranscribed=true")
                            else:
                                stats["updated"] += 1
                                logger.info(
                                    f"🔄 {video_id}: transcribed=false → true (DRY RUN)"
                                )
                        else:
                            stats["not_found"] += 1
                            logger.warning(
                                f"⚠️ {video_id}: DynamoDBレコードが見つかりません"
                            )
                    else:
                        # 実際の更新処理
                        success = self.dynamo_client.update_transcribed_status(
                            video_id, True
                        )
                        if success:
                            stats["updated"] += 1
                            logger.info(f"✅ {video_id}: transcribed=trueに更新")
                        else:
                            stats["failed"] += 1
                            logger.error(f"❌ {video_id}: 更新に失敗")

                except Exception as e:
                    stats["failed"] += 1
                    logger.error(f"❌ {video_id}: エラー - {e}")
                    continue

        return stats

    def run_update(
        self, prefix: str = "", batch_size: int = 25, dry_run: bool = False
    ) -> dict:
        """
        メイン処理：S3ファイル一覧を取得してDynamoDBを更新

        Args:
            prefix: S3検索プレフィックス
            batch_size: バッチサイズ
            dry_run: ドライランモード

        Returns:
            処理結果の統計
        """
        try:
            # 1. S3ファイル一覧を取得
            s3_files = self.get_s3_files(prefix)

            if not s3_files:
                logger.warning("対象となるJSONファイルが見つかりませんでした")
                return {"total": 0, "processed": 0, "updated": 0, "failed": 0}

            # 2. ビデオIDを抽出
            video_ids = []
            for s3_key in s3_files:
                video_id = self.extract_video_id_from_key(s3_key)
                video_ids.append(video_id)
                logger.debug(f"S3キー: {s3_key} → ビデオID: {video_id}")

            logger.info(f"抽出したビデオID数: {len(video_ids)}")

            # 3. DynamoDBを更新
            stats = self.update_transcribe_status(video_ids, batch_size, dry_run)

            return stats

        except Exception as e:
            logger.error(f"処理中にエラーが発生しました: {e}")
            raise


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="S3バケットからファイル一覧を取得し、DynamoDBのtranscribe属性をtrueに設定"
    )

    parser.add_argument(
        "--prefix",
        type=str,
        default="",
        help="S3検索プレフィックス (例: audio4output/)",
    )

    parser.add_argument(
        "--batch-size", type=int, default=25, help="バッチ処理サイズ (デフォルト: 25)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ドライランモード（実際の更新は行わない）",
    )

    parser.add_argument(
        "--table-name",
        type=str,
        help="DynamoDBテーブル名（指定しない場合は環境変数から取得）",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="ログレベル",
    )

    parser.add_argument(
        "--show-bucket",
        action="store_true",
        help="現在のS3バケット設定を表示して終了",
    )

    args = parser.parse_args()

    # バケット情報表示オプション
    if args.show_bucket:
        show_bucket_info()
        return

    # ログレベル設定
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    try:
        # 環境変数チェック
        load_dotenv()
        required_env_vars = [
            "S3_BUCKET_NAME",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]

        if missing_vars:
            logger.error(f"必要な環境変数が設定されていません: {missing_vars}")
            logger.error("プロジェクトルートの.envファイルを確認してください")
            sys.exit(1)

        # アップデーター初期化
        updater = TranscribeStatusUpdater(args.table_name)

        # 処理実行
        logger.info("=" * 60)
        logger.info("🚀 transcribe属性更新処理を開始")
        logger.info(f"📦 S3バケット: {updater.s3_bucket}")
        logger.info(f"📂 プレフィックス: '{args.prefix}' (空の場合は全ファイル)")
        logger.info(f"📊 バッチサイズ: {args.batch_size}")
        logger.info(f"🔍 ドライランモード: {args.dry_run}")
        logger.info("=" * 60)

        stats = updater.run_update(
            prefix=args.prefix, batch_size=args.batch_size, dry_run=args.dry_run
        )

        # 結果表示
        logger.info("=" * 60)
        logger.info("✅ 処理完了")
        logger.info(f"対象件数: {stats['total']}")
        logger.info(f"処理済み: {stats['processed']}")
        logger.info(f"更新済み: {stats['updated']}")

        if stats.get("already_transcribed", 0) > 0:
            logger.info(f"既にtranscribed=true: {stats['already_transcribed']}")

        if stats.get("not_found", 0) > 0:
            logger.warning(f"レコード未発見: {stats['not_found']}")

        if stats["failed"] > 0:
            logger.warning(f"失敗: {stats['failed']}")

        logger.info("=" * 60)

        # 終了コード
        if stats["failed"] > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\n処理が中断されました")
        sys.exit(1)
    except Exception as e:
        logger.error(f"予期しないエラーが発生しました: {e}")
        sys.exit(1)


def show_bucket_info():
    """現在のS3バケット設定を表示"""
    load_dotenv()

    bucket_name = os.getenv("S3_BUCKET_NAME")
    aws_region = os.getenv("AWS_REGION", "ap-northeast-1")

    print("=" * 60)
    print("📦 現在のS3設定")
    print("=" * 60)
    print(f"バケット名: {bucket_name or '❌ 未設定'}")
    print(f"リージョン: {aws_region}")
    print("=" * 60)

    if not bucket_name:
        print("⚠️ S3_BUCKET_NAME環境変数が設定されていません")
        print("   .envファイルでS3_BUCKET_NAMEを設定してください")


if __name__ == "__main__":
    main()
