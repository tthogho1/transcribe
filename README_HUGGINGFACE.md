---
title: Higma Chat RAG
emoji: 💬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
---

# 🤗 Hugging Face Spaces デプロイガイド（CPU 無料版最適化）

この README は、Chat Server を Hugging Face Spaces（Docker CPU Free Tier）にデプロイする手順を説明します。

## 📋 前提条件

- Hugging Face アカウント
- Zilliz Cloud アカウント（ベクトルデータベース）
- OpenAI API キー
- （オプション）Cohere API キー（リランキング用）

## ⚠️ CPU 無料版の制約

Hugging Face Spaces の CPU 無料版では以下の制約があります：

- **CPU のみ**（GPU 不可）
- **メモリ**: 約 16GB
- **ストレージ**: 限定的
- **ビルド時間**: 制限あり
- **初回起動**: モデルダウンロードで 2-5 分

**最適化内容**:

- PyTorch CPU 版を使用（~1.8GB 削減）
- バッチサイズを小さく設定（メモリ削減）
- 並列処理を制限（CPU 負荷軽減）

## 🚀 デプロイ手順

### 1. Hugging Face Space の作成

1. [Hugging Face Spaces](https://huggingface.co/spaces)にアクセス
2. "Create new Space"をクリック
3. 以下の設定を選択:
   - **Space name**: 任意の名前（例: `conversation-chat-rag`）
   - **License**: MIT
   - **Space SDK**: **Docker**（重要！）
   - **Space hardware**: **CPU basic（無料）** ← これを選択

### 2. 必須ファイルの準備

以下のファイルを Space のリポジトリにアップロード:

```
transcribe/
├── Dockerfile              # Dockerfile.hfspaces をリネーム
├── requirements.txt        # requirements.hf.txt をリネーム（CPU最適化版）
├── .dockerignore           # ビルドサイズ削減用
├── src/
│   ├── api/
│   │   └── chat_server.py
│   ├── core/
│   ├── services/
│   ├── models/
│   └── templates/
└── artifacts/
    └── tfidf_vectorizer.joblib
```

**重要**: 以下のファイル名を変更してアップロード

- `Dockerfile.hfspaces` → `Dockerfile`
- `requirements.hf.txt` → `requirements.txt`

### 3. 環境変数の設定

Hugging Face Spaces の設定画面で以下のシークレットを追加:

#### 必須の環境変数

| 変数名           | 説明                        | 例                                             |
| ---------------- | --------------------------- | ---------------------------------------------- |
| `ZILLIZ_URI`     | Zilliz Cloud エンドポイント | `https://xxx.api.gcp-us-west1.zillizcloud.com` |
| `ZILLIZ_TOKEN`   | Zilliz Cloud 認証トークン   | `xxxxxxxxxxxxxxxx`                             |
| `OPENAI_API_KEY` | OpenAI API キー             | `sk-xxxxxxxxxxxxxxxx`                          |

#### オプションの環境変数

| 変数名                     | 説明                              | デフォルト値    |
| -------------------------- | --------------------------------- | --------------- |
| `OPENAI_MODEL`             | 使用する OpenAI モデル            | `gpt-3.5-turbo` |
| `OPENAI_MAX_TOKENS`        | 最大トークン数                    | `2000`          |
| `OPENAI_TEMPERATURE`       | 温度パラメータ                    | `0.7`           |
| `COHERE_API_KEY`           | Cohere API キー（リランキング用） | -               |
| `RERANK_METHOD`            | リランキング方法                  | `cross_encoder` |
| `CROSS_ENCODER_DEVICE`     | デバイス設定                      | `cpu`           |
| `CROSS_ENCODER_BATCH_SIZE` | バッチサイズ                      | `4`             |
| `FLASK_PORT`               | ポート番号                        | `7860`          |
| `FLASK_DEBUG`              | デバッグモード                    | `False`         |

### 4. デプロイ

1. ファイルをアップロードまたは Git push でデプロイ
2. Hugging Face Spaces が自動的に Docker イメージをビルド
3. 初回ビルドには 5-10 分程度かかります（依存パッケージとモデルのダウンロード）

### 5. 動作確認

デプロイ完了後、以下のエンドポイントにアクセス:

- **チャット UI**: `https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME`
- **ヘルスチェック**: `https://YOUR_USERNAME-YOUR_SPACE_NAME.hf.space/health`
- **API**: `https://YOUR_USERNAME-YOUR_SPACE_NAME.hf.space/api/chat`

## 📝 使用方法

### REST API

```bash
# チャット
curl -X POST https://YOUR_SPACE_URL/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "質問内容"}'

# 検索のみ
curl -X POST https://YOUR_SPACE_URL/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "検索クエリ", "limit": 5}'
```

### WebSocket (Socket.IO)

```javascript
const socket = io('https://YOUR_SPACE_URL');

socket.on('connect', () => {
  console.log('Connected');
});

socket.emit('chat_message', { query: '質問内容' });

socket.on('chat_response', data => {
  console.log('Answer:', data.answer);
  console.log('Sources:', data.sources);
});
```

## ⚙️ CPU 無料版向けパフォーマンス最適化

### 環境変数の推奨設定（CPU 無料版）

CPU 無料版では以下の設定を**強く推奨**します：

```env
# CPU最適化（必須）
CROSS_ENCODER_DEVICE=cpu
CROSS_ENCODER_BATCH_SIZE=4
CROSS_ENCODER_MAX_LENGTH=256

# 検索最適化（メモリ削減）
INITIAL_SEARCH_MULTIPLIER=2

# スレッド制限（CPU負荷軽減）
OMP_NUM_THREADS=2
MKL_NUM_THREADS=2
TOKENIZERS_PARALLELISM=false
```

これらの設定は `Dockerfile.hfspaces` に既に含まれています。

### 応答速度を上げる追加設定

CPU 無料版で応答を高速化したい場合：

1. **リランキングを無効化**: `RERANK_METHOD=`（空文字列）

   - 応答速度: 2-3 秒 → 1-2 秒
   - 精度: わずかに低下

2. **検索結果数を削減**: API 呼び出し時に `limit=3` を指定

   - デフォルトの 5 件から 3 件に削減

3. **OpenAI モデルを変更**: `OPENAI_MODEL=gpt-3.5-turbo`（既定）
   - GPT-4 を使用している場合は 3.5-turbo に変更

### メモリ不足エラーの対処

もしメモリ不足エラーが発生する場合：

```env
CROSS_ENCODER_BATCH_SIZE=2  # さらに削減
INITIAL_SEARCH_MULTIPLIER=1  # 検索倍率を最小に
```

## 🐛 トラブルシューティング

### ビルドが失敗する

**症状**: Docker イメージのビルドが途中で失敗
**原因**: ビルド時間制限超過またはメモリ不足
**対処**:

- `requirements.hf.txt` が使用されているか確認（CPU 最適化版）
- `.dockerignore` が正しく設定されているか確認
- 不要なファイル（`typescript/`, `downloads/`等）を削除

### 起動が遅い・タイムアウトする

**症状**: アプリケーションの起動に 5 分以上かかる
**原因**: モデルの初回ダウンロード
**対処**:

- **正常な動作です**。初回は 2-5 分かかります
- 2 回目以降はキャッシュされ、30 秒程度で起動します
- Hugging Face Spaces のログで進捗を確認できます

### 応答が非常に遅い（10 秒以上）

**症状**: チャット応答に 10 秒以上かかる
**原因**: CPU でのリランキング処理
**対処**:

- リランキングを無効化: `RERANK_METHOD=`
- バッチサイズを削減: `CROSS_ENCODER_BATCH_SIZE=2`
- 検索結果数を削減: `limit=3` を指定

### MeCab エラー

**症状**: MeCab 関連のエラーメッセージ
**原因**: システムパッケージ未インストール
**対処**:

- `Dockerfile.hfspaces` を使用しているか確認
- Dockerfile に `mecab`、`libmecab-dev`、`mecab-ipadic-utf8` が含まれているか確認
- **フォールバック機能**: コードには既に MeCab 不要時のフォールバック処理が実装されています

### 接続エラー / Zilliz エラー

**症状**: `Connection failed` または `Authentication failed`
**原因**: 環境変数の設定ミス
**対処**:

1. Hugging Face Spaces の「Settings」→「Repository secrets」を確認
2. 必須変数が設定されているか確認:
   - `ZILLIZ_URI`
   - `ZILLIZ_TOKEN`
   - `OPENAI_API_KEY`
3. `/health` エンドポイントで各サービスの状態を確認

### Space がスリープ状態になる

**症状**: しばらくアクセスしないと応答しなくなる
**原因**: CPU 無料版は一定時間非アクティブでスリープ
**対処**:

- **正常な動作です**。再アクセス時に自動的に起動します（~30 秒）
- 有料プラン（CPU upgrade）でスリープを回避可能

## 📦 含まれるコンポーネント

- **Flask**: Web サーバー
- **Socket.IO**: リアルタイム双方向通信
- **Sentence Transformers**: 日本語埋め込みモデル（CPU 最適化）
- **Cross Encoder**: リランキング（CPU 最適化済み、バッチサイズ削減）
- **MeCab**: 日本語形態素解析（フォールバック機能付き）
- **OpenAI GPT**: 回答生成
- **Zilliz Cloud**: ベクトルデータベース（密＋疎ハイブリッド検索）

## 🔒 セキュリティ

- API キーは必ず Hugging Face Spaces のシークレット機能を使用
- `.env`ファイルは`.gitignore`に追加（リポジトリにコミットしない）
- 本番環境では`FLASK_DEBUG=False`を設定

## 📄 ライセンス

このプロジェクトのライセンスに従います。

## 🆘 サポート

問題が発生した場合は、Issues セクションで報告してください。
