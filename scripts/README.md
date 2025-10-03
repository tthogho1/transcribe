# Scripts Directory

このディレクトリには、DynamoDB データベースの管理とメンテナンス用スクリプトが含まれています。

## スクリプト一覧

### `generate_embeddings_with_vectorizer.py`

**目的**: DynamoDB で `embedding=false` の動画を対象に、S3 から転写 JSON を取得し、`ConversationVectorizer` を使ってエンベディングを生成・Zilliz に保存し、DynamoDB のフラグを更新します。

**機能**:

- DynamoDB から `embedding` が未設定/false の `video_id` を抽出
- S3 から `{video_id}_transcription.json` をダウンロード
- AWS Transcribe / Gladia 形式の JSON からテキストを抽出
- `ConversationVectorizer.process_monologue` でベクトル化し Zilliz Cloud に保存
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

### `fit_tfidf_from_s3.py`

目的: S3 上の転写 JSON ファイル群からテキストを収集し、`TfidfSparseVectorizer` をコーパス全体で fit して、joblib で保存します。

機能:

- `S3JsonTextExtractor` で JSON からテキスト抽出 (AWS Transcribe / Gladia / 汎用)
- `TextProcessor` でチャンク分割
- `TfidfSparseVectorizer.fit_transform` で語彙を学習し、`joblib.dump` で保存
- バケット/プレフィックス/最大ファイル数/チャンク設定/ログレベルの指定

使用例 (PowerShell):

```
# 環境変数を使う場合
$env:S3_BUCKET_NAME = "your-bucket"
$env:S3_TRANSCRIPT_PREFIX = "transcripts/"   # 任意
$env:TFIDF_MODEL_PATH = "artifacts/tfidf_vectorizer.joblib"  # 任意
python scripts/fit_tfidf_from_s3.py

# 直接引数で指定
python scripts/fit_tfidf_from_s3.py --bucket your-bucket --prefix transcripts/ --model-path artifacts/tfidf_vectorizer.joblib --chunk-size 300 --chunk-overlap 50 --max-files 0 --log-level INFO
```

注意:

- `joblib` が必要です (`pip install joblib`)
- モデルファイルには `TfidfSparseVectorizer` のインスタンスが保存されます
- 既存サービス側で `joblib.load` により読み込み、`transform` に利用できます

### `rebuild_sparse_vectors.py`

目的: 保存済み TF‑IDF モデル（`.env: TFIDF_MODEL_PATH`）を読み込み、Zilliz Cloud コレクション内の全レコードの `text` から `sparse_vector` を再計算し、上書きします。

前提:

- `.env` に `ZILLIZ_URI`, `ZILLIZ_TOKEN`, `TFIDF_MODEL_PATH` が設定されていること
- コレクション名は `ZILLIZ_COLLECTION`（未設定時は `conversation_chunks_hybrid`）

使用例 (PowerShell):

```
python scripts/rebuild_sparse_vectors.py
```

オプション:

- `SPARSE_REBUILD_BATCH` バッチサイズ（デフォルト 500）

注意:

- 環境によっては `query_iterator` か `offset` が使用できない場合があります。エラーが出た場合は PyMilvus/サーバーのバージョン更新をご検討ください。

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
