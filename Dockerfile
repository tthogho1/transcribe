# Hugging Face Spaces (Docker CPU Free Tier) 最適化版 Dockerfile
FROM python:3.11-slim

# 作業ディレクトリ設定
WORKDIR /app

# ビルド時間短縮: システムパッケージを先にインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    mecab \
    libmecab-dev \
    mecab-ipadic-utf8 \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# CPU無料版最適化: pip設定
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# requirements.txtをコピー（キャッシュ活用）
COPY requirements.txt .

# 依存関係インストール - CPU版PyTorchを使用
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# fugashi/unidic の動作確認とセットアップ
RUN python -c "import fugashi; print('✅ fugashi imported successfully')" && \
    python -c "import unidic_lite; print('✅ unidic-lite available')" && \
    echo "✅ Japanese tokenization ready"

# アプリケーションファイルをコピー
COPY src/ ./src/

# TF-IDFモデルファイルをコピー（Git LFS経由）
COPY artifacts/ ./artifacts/

# Hugging Face Spaces用環境変数（CPU無料版最適化）
ENV FLASK_PORT=7860 \
    FLASK_DEBUG=False \
    CROSS_ENCODER_DEVICE=cpu \
    CROSS_ENCODER_BATCH_SIZE=4 \
    CROSS_ENCODER_MAX_LENGTH=256 \
    INITIAL_SEARCH_MULTIPLIER=2 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2

# ポート7860を公開
EXPOSE 7860

# ヘルスチェック（CPU負荷を考慮して間隔を長めに）
HEALTHCHECK --interval=60s --timeout=30s --start-period=120s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:7860/health', timeout=10)" || exit 1

# アプリケーション起動
CMD ["python", "src/api/chat_server.py"]
