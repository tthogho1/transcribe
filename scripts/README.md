# Scripts Directory

このディレクトリには、DynamoDB データベースの管理とメンテナンス用スクリプトが含まれています。

## スクリプト一覧

### `add_embedding_attribute.py`

**目的**: DynamoDB テーブル内の全項目に新規属性`embedding`を追加

**機能**:

- DynamoDB テーブルの全アイテムをスキャン
- `transcribed = 1` の場合: `embedding = true`を設定
- それ以外の場合: `embedding = false`を設定
- バッチ処理による効率的な更新
- ドライランモード対応

**使用方法**:

```bash
# 1. 環境確認・テスト実行
python scripts/test_embedding_script.py

# 2. ドライランでプレビュー
python scripts/add_embedding_attribute.py --dry-run

# 3. 実際の更新実行
python scripts/add_embedding_attribute.py

# 4. カスタムテーブル名での実行
python scripts/add_embedding_attribute.py --table-name MyTable

# 5. デバッグモード
python scripts/add_embedding_attribute.py --log-level DEBUG
```

### `test_embedding_script.py`

**目的**: `add_embedding_attribute.py`のテストと環境確認

**機能**:

- AWS 認証情報の確認
- DynamoDB 接続テスト
- サンプルデータの分析
- ドライランテスト
- 使用例の表示

## 環境設定

### 必要な環境変数

```bash
# AWS認証情報（必須）
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"

# オプション設定（デフォルト値あり）
export AWS_REGION="ap-northeast-1"
export DYNAMO_TABLE_NAME="YoutubeList"
```

### Python 依存関係

```bash
pip install boto3 python-dotenv
```

## 実行例

### 1. 環境テスト

```bash
cd c:\temp\SourceCode\transcribe
python scripts/test_embedding_script.py
```

**出力例**:

```
🧪 DynamoDB Embedding Attribute Updater - Test Suite
============================================================
🔍 Environment Variables Check:
   ✅ AWS_ACCESS_KEY_ID: AKIA**********...
   ✅ AWS_SECRET_ACCESS_KEY: **********...
   ✅ AWS_REGION: ap-northeast-1
   ✅ DYNAMO_TABLE_NAME: YoutubeList

🔗 DynamoDB Connection Test:
   ✅ Successfully connected to table: YoutubeList
   ✅ Region: ap-northeast-1

📊 Sample Data Scan Test:
   📋 Found 5 sample items
   🔍 Sample item keys: ['video_id', 'title', 'transcribed', 'created_at']
   🏷️  Sample transcribed value: 1
   🧠 Has embedding attribute: False
```

### 2. ドライラン実行

```bash
python scripts/add_embedding_attribute.py --dry-run
```

**出力例**:

```
🚀 Starting embedding attribute update for table: YoutubeList
🔍 Running in DRY RUN mode - no actual changes will be made
📋 Scanning all items...
📊 Total items scanned: 245

📊 Analysis Results:
   Total items: 245
   Transcribed (true/1): 15
   Transcribed (false/0): 230
   Transcribed (missing): 0
   Embedding attribute exists: 0
   Items needing update: 245

🔄 Updating 245 items...
[DRY RUN] Would update batch 1: 25 items
[DRY RUN] Would update batch 2: 25 items
...

🎯 [DRY RUN] Update Results:
   ✅ Success: 245
   ❌ Errors: 0
   ⏭️  Skipped: 0

🎉 [DRY RUN] All items updated successfully!
```

### 3. 実際の更新実行

```bash
python scripts/add_embedding_attribute.py
```

## トラブルシューティング

### よくある問題

1. **AWS 認証エラー**

   ```
   ❌ DynamoDB initialization failed: Unable to locate credentials
   ```

   **解決方法**: AWS 認証情報を正しく設定してください

2. **テーブルが見つからない**

   ```
   ❌ Table YoutubeList does not exist
   ```

   **解決方法**: テーブル名を確認するか、`--table-name`パラメータで指定してください

3. **権限不足**
   ```
   ❌ Access denied
   ```
   **解決方法**: IAM ユーザーに DynamoDB 読み取り・書き込み権限を付与してください

### 必要な IAM 権限

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:Scan", "dynamodb:UpdateItem", "dynamodb:DescribeTable"],
      "Resource": "arn:aws:dynamodb:*:*:table/YoutubeList"
    }
  ]
}
```

## ログレベル

- **DEBUG**: 最も詳細な情報
- **INFO**: 一般的な実行情報（デフォルト）
- **WARNING**: 警告メッセージのみ
- **ERROR**: エラーメッセージのみ

```bash
python scripts/add_embedding_attribute.py --log-level DEBUG
```
