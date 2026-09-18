# Docker Configuration Guide for Flask Chat Server

## Overview

This project has two Docker deployment paths:

- **`aws/Dockerfile.production`** - Multi-stage production build (non-root user, CPU-only
  torch, security hardening) used for local `docker-compose` runs and ECS deployment
  (`aws/deploy-to-ecs.sh`, `aws/codebuild-infrastructure.yaml`).
- **`Dockerfile.hfspaces`** - Standalone build for Hugging Face Spaces (Docker SDK, CPU
  free tier). See `README_HUGGINGFACE.md` for that deployment path.
- **`docker-compose.chat.yml`** / **`docker-compose.yml`** - Local Docker Compose
  configurations that build `aws/Dockerfile.production`.

## Quick Start

```bash
# Build and run via docker-compose (uses aws/Dockerfile.production)
docker-compose -f docker-compose.chat.yml up -d --build chat-server-prod

# Or build/run directly with plain docker
docker build -f aws/Dockerfile.production -t transcribe-chat-server .
docker run -d --env-file .env -p 5000:5000 transcribe-chat-server
```

## `aws/Dockerfile.production`

- Multi-stage build for a smaller final image
- Installs the CPU-only torch wheel (the default PyPI build pulls in CUDA libraries,
  multiple GB larger and unused on CPU-only hosts like ECS/Fargate)
- Uses a virtual environment for dependency isolation
- Runs as a non-root user
- Health check hits `/health`
- Exposed port: 5000

## Environment Variables

Create a `.env` file with the following variables:

```env
# Zilliz Configuration (BM25 hybrid search)
ZILLIZ_URI=your-zilliz-uri
ZILLIZ_TOKEN=your-zilliz-token

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-3.5-turbo
OPENAI_MAX_TOKENS=1000
OPENAI_TEMPERATURE=0.7

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=false
FLASK_PORT=5000

# AWS Configuration (if using S3/DynamoDB-backed ingestion)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_DEFAULT_REGION=your-region
S3_BUCKET_NAME=your-bucket-name
```

## Docker Compose Commands

```bash
# Start
docker-compose -f docker-compose.chat.yml up -d chat-server-prod

# View logs
docker-compose -f docker-compose.chat.yml logs -f chat-server-prod

# Stop
docker-compose -f docker-compose.chat.yml down

# Rebuild and start
docker-compose -f docker-compose.chat.yml up -d --build chat-server-prod
```

`docker-compose.yml` (project root) defines an equivalent single `chat-server` service
for a standalone (non-dev) run.

## Health Check

- http://localhost:5000/health (docker-compose.yml `chat-server`)
- http://localhost:5001/health (docker-compose.chat.yml `chat-server-prod`, mapped to host port 5001)

## Volumes

- **chat-logs**: Persistent storage for application logs
- **chat-cache**: Persistent storage for cache data

## Security Features

1. **Non-root user**: container runs as a non-root user
2. **Multi-stage build**: reduces attack surface / image size
3. **Minimal base image**: Python slim
4. **Health check**: container monitoring
5. **Resource limits**: configurable via Docker Compose

## Troubleshooting

### Common Issues

1. **Port conflicts**: change the port mapping in `docker-compose.chat.yml` / `docker-compose.yml`
2. **Build failures**: try building with `--no-cache`
3. **`ModuleNotFoundError: No module named 'models'`**: make sure `PYTHONPATH=/app/src`
   is set (already baked into `aws/Dockerfile.production`) - `python api/chat_server.py`
   only adds its own directory to `sys.path`, not the working directory, so the
   `models`/`services`/`core` packages under `src/` need `PYTHONPATH` to resolve.

### Debug Commands

```bash
# Check container status
docker ps

# View detailed logs
docker logs <container-name>

# Execute shell in container
docker exec -it <container-name> /bin/bash

# Check health status
docker inspect <container-name> | grep Health -A 10
```

## Deployment

For production deployment on AWS, see `aws/README.md`-equivalent tooling:

- `aws/cloudformation-infrastructure.yaml` - ECS/VPC/IAM infrastructure
- `aws/codebuild-infrastructure.yaml` - CodeBuild CI/CD project (inline buildspec builds `aws/Dockerfile.production`)
- `aws/deploy-to-ecs.sh` - deploy a built image to ECS
- `aws/setup-codebuild.sh` - one-time CodeBuild/ECR/SSM setup

For Hugging Face Spaces, see `README_HUGGINGFACE.md`.
