#!/usr/bin/env python3
"""
update_transcribe_status.pyスクリプトの使用例とテスト

このファイルは、作成したスクリプトの動作確認と使用方法の説明を提供します。
"""

import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def show_usage_examples():
    """使用例を表示"""
    script_name = "scripts/update_transcribe_status.py"

    examples = [
        {
            "title": "基本的な使用方法（ドライランモード）",
            "command": f"python {script_name} --dry-run",
            "description": "実際の更新を行わずに、どのような処理が行われるかを確認",
        },
        {
            "title": "特定のプレフィックスのファイルのみ対象",
            "command": f"python {script_name} --prefix audio4output/ --dry-run",
            "description": "audio4output/フォルダ内のファイルのみを対象にして処理",
        },
        {
            "title": "実際の更新処理を実行",
            "command": f"python {script_name}",
            "description": "DynamoDBのtranscribe属性を実際に更新",
        },
        {
            "title": "バッチサイズを指定して処理",
            "command": f"python {script_name} --batch-size 10",
            "description": "一度に10件ずつ処理（デフォルトは25件）",
        },
        {
            "title": "詳細ログで実行",
            "command": f"python {script_name} --log-level DEBUG --dry-run",
            "description": "詳細なデバッグ情報を表示して実行",
        },
        {
            "title": "特定のDynamoDBテーブルを指定",
            "command": f"python {script_name} --table-name my_videos_table",
            "description": "デフォルト以外のDynamoDBテーブルを指定",
        },
    ]

    print("=" * 80)
    print("📝 update_transcribe_status.py 使用例")
    print("=" * 80)
    print()

    for i, example in enumerate(examples, 1):
        print(f"{i}. {example['title']}")
        print(f"   コマンド: {example['command']}")
        print(f"   説明: {example['description']}")
        print()

    print("⚠️  注意事項:")
    print(
        "  - 実際の処理を行う前に、必ず --dry-run オプションで動作確認を行ってください"
    )
    print("  - .envファイルに以下の環境変数が設定されていることを確認してください:")
    print("    * S3_BUCKET_NAME")
    print("    * AWS_ACCESS_KEY_ID")
    print("    * AWS_SECRET_ACCESS_KEY")
    print("    * AWS_REGION")
    print("    * YOUTUBE_DYNAMODB_TABLE (オプション)")
    print()


def check_environment():
    """環境変数の確認"""
    from dotenv import load_dotenv

    load_dotenv()

    required_vars = [
        "S3_BUCKET_NAME",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION",
    ]

    optional_vars = ["YOUTUBE_DYNAMODB_TABLE"]

    print("=" * 80)
    print("🔧 環境変数チェック")
    print("=" * 80)
    print()

    print("必須の環境変数:")
    for var in required_vars:
        value = os.getenv(var)
        status = "✅ 設定済み" if value else "❌ 未設定"
        masked_value = f"{value[:10]}..." if value and len(value) > 10 else value
        print(f"  {var}: {status} ({masked_value})")

    print("\nオプションの環境変数:")
    for var in optional_vars:
        value = os.getenv(var)
        status = "✅ 設定済み" if value else "ℹ️ 未設定（デフォルト値を使用）"
        print(f"  {var}: {status} ({value})")

    print()

    # 未設定の必須変数があるかチェック
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print("❌ 以下の必須環境変数が設定されていません:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nプロジェクトルートの.envファイルを確認してください。")
        return False
    else:
        print("✅ すべての必須環境変数が設定されています。")
        return True


def show_script_features():
    """スクリプトの機能説明"""
    print("=" * 80)
    print("🚀 スクリプトの機能")
    print("=" * 80)
    print()

    features = [
        "S3バケットからJSONファイル一覧を自動取得",
        "ファイル名からビデオIDを自動抽出",
        "DynamoDBのtranscribe属性をバッチ更新",
        "ドライランモード（実際の更新なしでテスト可能）",
        "バッチサイズ指定による効率的な処理",
        "詳細なログ出力と処理統計",
        "エラーハンドリングと復旧機能",
        "プレフィックス指定による柔軟なファイル選択",
    ]

    for i, feature in enumerate(features, 1):
        print(f"{i}. {feature}")

    print()


def main():
    """メイン関数"""
    print()
    show_script_features()
    print()
    show_usage_examples()
    print()

    env_ok = check_environment()

    print("=" * 80)
    print("🎯 次のステップ")
    print("=" * 80)
    print()

    if env_ok:
        print("1. まずドライランモードでテスト:")
        print("   python scripts/update_transcribe_status.py --dry-run")
        print()
        print("2. 問題がなければ実際に実行:")
        print("   python scripts/update_transcribe_status.py")
    else:
        print("1. .envファイルで必須環境変数を設定")
        print("2. 再度このスクリプトを実行して環境を確認")
        print("3. ドライランモードでテスト実行")

    print()


if __name__ == "__main__":
    main()
