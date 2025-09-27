import boto3
import json
import logging
import os
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 環境変数を読み込み
load_dotenv()


class S3JsonTextExtractor:
    """S3からJSONファイルを読み込んでテキストを抽出するクラス"""

    def __init__(self):
        """初期化 - AWS認証情報を設定"""
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION"),
        )
        logger.info("S3クライアントを初期化しました")

    def read_json_from_s3(self, bucket_name: str, object_key: str) -> Optional[Dict]:
        """
        S3からJSONファイルを読み込む

        Args:
            bucket_name: S3バケット名
            object_key: オブジェクトキー（ファイルパス）

        Returns:
            JSONデータ（辞書形式）、失敗時はNone
        """
        try:
            logger.info(
                f"S3からJSONファイルを読み込み中: s3://{bucket_name}/{object_key}"
            )

            response = self.s3_client.get_object(Bucket=bucket_name, Key=object_key)
            json_content = response["Body"].read().decode("utf-8")

            data = json.loads(json_content)
            logger.info(
                f"JSONファイルの読み込みが完了しました: {len(json_content)} bytes"
            )

            return data

        except Exception as e:
            logger.error(f"JSONファイルの読み込みに失敗しました: {e}")
            return None

    def extract_text_from_transcribe_result(
        self, transcribe_data: Dict
    ) -> Optional[str]:
        """
        Transcribeの結果JSONからテキストを抽出

        Args:
            transcribe_data: Transcribeの結果JSON

        Returns:
            抽出されたテキスト、失敗時はNone
        """
        try:
            # Transcribeの結果構造からテキストを抽出
            if (
                "result" in transcribe_data
                and "transcription" in transcribe_data["result"]
            ):
                transcripts = transcribe_data["result"]["transcription"]
                if transcripts and len(transcripts) > 0:
                    full_text = transcripts.get("full_transcript", "")
                    logger.info(
                        f"Transcribeテキストを抽出しました: {len(full_text)} 文字"
                    )
                    return full_text

            logger.warning("Transcribe結果にテキストが見つかりませんでした")
            return None

        except Exception as e:
            logger.error(f"Transcribeテキストの抽出に失敗しました: {e}")
            return None

    def extract_text_generic(
        self, json_data: Dict, text_fields: List[str] = None
    ) -> List[str]:
        """
        汎用的なJSONからテキストフィールドを抽出

        Args:
            json_data: JSONデータ
            text_fields: 抽出対象のフィールド名リスト（指定しない場合は一般的なフィールドを使用）

        Returns:
            抽出されたテキストのリスト
        """
        if text_fields is None:
            # 一般的なテキストフィールド名
            text_fields = [
                "text",
                "content",
                "message",
                "description",
                "transcript",
                "body",
            ]

        extracted_texts = []

        def search_text_recursive(obj: Any, current_path: str = ""):
            """再帰的にJSONからテキストを検索"""
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_path = f"{current_path}.{key}" if current_path else key

                    # テキストフィールドかチェック
                    if key.lower() in [field.lower() for field in text_fields]:
                        if isinstance(value, str) and value.strip():
                            extracted_texts.append(
                                {"field": new_path, "text": value.strip()}
                            )
                            logger.debug(
                                f"テキストを発見: {new_path} = {value[:50]}..."
                            )

                    # 再帰的に検索
                    search_text_recursive(value, new_path)

            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    new_path = f"{current_path}[{i}]" if current_path else f"[{i}]"
                    search_text_recursive(item, new_path)

        try:
            search_text_recursive(json_data)
            logger.info(
                f"汎用テキスト抽出が完了: {len(extracted_texts)} 個のテキストフィールドを発見"
            )
            return extracted_texts

        except Exception as e:
            logger.error(f"汎用テキスト抽出に失敗しました: {e}")
            return []

    def extract_text_from_s3_json(
        self, bucket_name: str, object_key: str, extraction_type: str = "auto"
    ) -> Optional[Dict]:
        """
        S3のJSONファイルからテキストを抽出（メインメソッド）

        Args:
            bucket_name: S3バケット名
            object_key: オブジェクトキー
            extraction_type: 抽出タイプ ('auto', 'transcribe', 'generic')

        Returns:
            抽出結果の辞書
        """
        # JSONファイルを読み込み
        json_data = self.read_json_from_s3(bucket_name, object_key)
        if json_data is None:
            return None

        result = {
            "source": f"s3://{bucket_name}/{object_key}",
            "extraction_type": extraction_type,
            "extracted_texts": [],
        }

        if extraction_type == "auto":
            # 自動判定: Transcribeの結果かどうかチェック
            if "result" in json_data and "transcription" in json_data.get("result", {}):
                extraction_type = "transcribe"
                logger.info("Transcribeの結果JSONと判定しました")
            else:
                extraction_type = "generic"
                logger.info("汎用JSONと判定しました")

        if extraction_type == "transcribe":
            # Transcribe専用抽出
            text = self.extract_text_from_transcribe_result(json_data)
            if text:
                result["extracted_texts"].append({"field": "transcript", "text": text})
        else:
            # 汎用抽出
            texts = self.extract_text_generic(json_data)
            result["extracted_texts"] = texts

        result["extraction_type"] = extraction_type
        logger.info(
            f"テキスト抽出完了: {len(result['extracted_texts'])} 個のテキストを抽出"
        )

        return result

    def list_json_files_in_bucket(
        self, bucket_name: str, prefix: str = ""
    ) -> List[str]:
        """
        S3バケット内のJSONファイル一覧を取得

        Args:
            bucket_name: S3バケット名
            prefix: プレフィックス（フォルダパス）

        Returns:
            JSONファイルのキーリスト
        """
        try:
            logger.info(f"S3バケット内のJSONファイルを検索中: {bucket_name}/{prefix}")

            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

            json_files = []
            for page in pages:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        key = obj["Key"]
                        if key.lower().endswith(".json"):
                            json_files.append(key)

            logger.info(f"JSONファイルを {len(json_files)} 個発見しました")
            return json_files

        except Exception as e:
            logger.error(f"JSONファイル一覧の取得に失敗しました: {e}")
            return []

    def batch_extract_texts(
        self, bucket_name: str, prefix: str = "", extraction_type: str = "auto"
    ) -> List[Dict]:
        """
        バッチでJSONファイルからテキストを抽出

        Args:
            bucket_name: S3バケット名
            prefix: プレフィックス（フォルダパス）
            extraction_type: 抽出タイプ

        Returns:
            抽出結果のリスト
        """
        json_files = self.list_json_files_in_bucket(bucket_name, prefix)
        results = []

        for json_file in json_files:
            logger.info(f"処理中: {json_file}")
            result = self.extract_text_from_s3_json(
                bucket_name, json_file, extraction_type
            )
            if result:
                results.append(result)

        logger.info(f"バッチ処理完了: {len(results)} ファイルを処理しました")
        return results


def main():
    """メイン関数 - 使用例"""
    try:
        # テキスト抽出器を初期化
        extractor = S3JsonTextExtractor()

        # 使用例1: 単一ファイルからテキスト抽出
        bucket_name = os.getenv("S3_BUCKET_NAME")
        json_file_key = "lW-9J9yHtB4.json"

        print("=" * 60)
        print("単一ファイルからのテキスト抽出")
        print("=" * 60)

        result = extractor.extract_text_from_s3_json(bucket_name, json_file_key)
        if result:
            print(f"抽出元: {result['source']}")
            print(f"抽出タイプ: {result['extraction_type']}")
            print(f"抽出されたテキスト数: {len(result['extracted_texts'])}")

            for i, text_info in enumerate(result["extracted_texts"], 1):
                print(f"\n[{i}] フィールド: {text_info['field']}")
                text_preview = (
                    text_info["text"][:200] + "..."
                    if len(text_info["text"]) > 200
                    else text_info["text"]
                )
                print(f"    テキスト: {text_preview}")

        # 使用例2: バッチ処理
        print("\n" + "=" * 60)
        print("バッチ処理でのテキスト抽出")
        print("=" * 60)

        batch_results = extractor.batch_extract_texts(bucket_name, "transcribe-output/")

        for result in batch_results:
            print(f"\nファイル: {result['source']}")
            print(f"抽出されたテキスト数: {len(result['extracted_texts'])}")

            # 最初のテキストのプレビューを表示
            if result["extracted_texts"]:
                first_text = result["extracted_texts"][0]["text"]
                preview = (
                    first_text[:100] + "..." if len(first_text) > 100 else first_text
                )
                print(f"プレビュー: {preview}")

    except Exception as e:
        logger.error(f"メイン処理でエラーが発生しました: {e}")


if __name__ == "__main__":
    main()
