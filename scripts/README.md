# Scripts Directory

このディレクトリには、DynamoDB データベースの管理とメンテナンス用スクリプトが含まれています。

## スクリプト一覧

### `generate_embeddings_with_vectorizer.py`

**目的**: DynamoDB で `embedding=false` の動画を対象に、S3 から転写 JSON を取得し、`ConversationVectorizer` を使ってエンベディングを生成・Zilliz に保存し、DynamoDB のフラグを更新します。

**機能**:

- DynamoDB から `embedding` が未設定/false の `video_id` を抽出
- S3 から `{video_id}_transcription.json` をダウンロード
- AWS Transcribe / Gladia 形式の JSON からテキストを抽出
- `ConversationVectorizer.process_monologue_bm25` でベクトル化し Zilliz Cloud (BM25 コレクション) に保存
- DynamoDB の `embedding` フラグと `embedding_updated_at` を更新
- ドライランモード・バッチサイズ指定・ログレベル指定に対応

**使用方法**:

```bash
# 1. 環境変数を確認
python scripts/generate_embeddings_with_vectorizer.py --dry-run --batch-size 3

# 2. 実際に 5 件処理
python scripts/generate_embeddings_with_vectorizer.py --batch-size 5

# 3. デバッグログを有効化
python scripts/generate_embeddings_with_vectorizer.py --log-level DEBUG
```

**必要な環境変数**:

- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `DYNAMO_TABLE_NAME`
- `S3_TRANSCRIPT_BUCKET` または `S3_BUCKET_NAME`
- `ZILLIZ_URI`, `ZILLIZ_TOKEN`

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
# 1. ドライランでプレビュー
python scripts/add_embedding_attribute.py --dry-run

# 2. 実際の更新実行
python scripts/add_embedding_attribute.py

# 3. カスタムテーブル名での実行
python scripts/add_embedding_attribute.py --table-name MyTable

# 4. デバッグモード
python scripts/add_embedding_attribute.py --log-level DEBUG
```

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

### 1. ドライラン実行

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

### 2. 実際の更新実行

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
