# Docker Configuration Guide for Flask Chat Server

## Overview

This project includes multiple Docker configurations optimized for different use cases:

- **`Dockerfile`** - Main production-ready Dockerfile with multi-stage build
- **`Dockerfile.production`** - Optimized production build with security hardening
- **`Dockerfile.dev`** - Development build with debugging tools and hot reload
- **`docker-compose.chat.yml`** - Docker Compose configuration for both environments

## Quick Start

### Development Environment

```bash
# Using PowerShell (Windows)
.\docker-build.ps1

# Using Bash (Linux/Mac)
./docker-build.sh

# Or manually with Docker Compose
docker-compose -f docker-compose.chat.yml up -d chat-server
```

### Production Environment

```bash
# Using PowerShell (Windows)
.\docker-build.ps1 -Environment production

# Using Bash (Linux/Mac)
./docker-build.sh -e production

# Or manually with Docker Compose
docker-compose -f docker-compose.chat.yml --profile production up -d chat-server-prod
```

## Docker Images

### 1. Main Dockerfile (Production)

- Multi-stage build for optimized image size
- Uses virtual environment for dependency isolation
- Non-root user for security
- Health check for container monitoring
- Exposed port: 5000

### 2. Development Dockerfile

- Single-stage build with development tools
- Includes debugging and formatting tools (pytest, black, flake8)
- Volume mounts for hot reload
- Development-friendly configuration

### 3. Production Dockerfile

- Highly optimized for production deployment
- Minimal attack surface
- Security hardening with non-root user
- Optimized layer caching

## Environment Variables

Create a `.env` file with the following variables:

```env
# Zilliz Configuration
ZILLIZ_URI=your-zilliz-uri
ZILLIZ_TOKEN=your-zilliz-token

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-3.5-turbo
OPENAI_MAX_TOKENS=1000
OPENAI_TEMPERATURE=0.7

# Cohere Configuration (optional)
COHERE_API_KEY=your-cohere-api-key

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=false
FLASK_PORT=5000

# Reranking Configuration
RERANK_METHOD=cross_encoder
CROSS_ENCODER_DEVICE=auto
CROSS_ENCODER_BATCH_SIZE=8
CROSS_ENCODER_MAX_LENGTH=512
INITIAL_SEARCH_MULTIPLIER=3

# AWS Configuration (if needed)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_DEFAULT_REGION=your-region
S3_BUCKET_NAME=your-bucket-name
```

## Build Scripts

### PowerShell Script (Windows)

```powershell
# Development build and run
.\docker-build.ps1

# Production build and run
.\docker-build.ps1 -Environment production

# Build only without running
.\docker-build.ps1 -BuildOnly

# Build without cache
.\docker-build.ps1 -NoCache

# Show help
.\docker-build.ps1 -Help
```

### Bash Script (Linux/Mac)

```bash
# Development build and run
./docker-build.sh

# Production build and run
./docker-build.sh -e production

# Build only without running
./docker-build.sh -b

# Build without cache
./docker-build.sh -n

# Show help
./docker-build.sh -h
```

## Docker Compose Commands

### Development

```bash
# Start development environment
docker-compose -f docker-compose.chat.yml up -d chat-server

# View logs
docker-compose -f docker-compose.chat.yml logs -f chat-server

# Stop services
docker-compose -f docker-compose.chat.yml down

# Rebuild and start
docker-compose -f docker-compose.chat.yml up -d --build chat-server
```

### Production

```bash
# Start production environment
docker-compose -f docker-compose.chat.yml --profile production up -d chat-server-prod

# View logs
docker-compose -f docker-compose.chat.yml logs -f chat-server-prod

# Stop services
docker-compose -f docker-compose.chat.yml --profile production down
```

## Health Checks

All containers include health checks:

- **Development**: http://localhost:5000/health
- **Production**: http://localhost:5001/health

## Volumes

- **chat-logs**: Persistent storage for application logs
- **chat-cache**: Persistent storage for cache data
- **Source code mounts** (development only): For hot reload

## Security Features

1. **Non-root user**: All containers run as non-root user
2. **Multi-stage builds**: Reduce attack surface
3. **Minimal base images**: Python slim images
4. **Health checks**: Container monitoring
5. **Resource limits**: Configurable via Docker Compose

## Troubleshooting

### Common Issues

1. **Port conflicts**: Change ports in docker-compose.chat.yml
2. **Permission issues**: Ensure proper volume permissions
3. **Memory issues**: Adjust Cross Encoder batch size in environment variables
4. **Build failures**: Try building with --no-cache

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

## Performance Optimization

1. **Production builds**: Use multi-stage Dockerfiles
2. **Cache optimization**: Proper layer ordering
3. **Resource limits**: Set appropriate CPU and memory limits
4. **Model optimization**: Configure Cross Encoder batch size based on available resources

## Deployment

For production deployment, consider:

- Using a container registry (ECR, Docker Hub)
- Container orchestration (ECS, Kubernetes)
- Load balancing and auto-scaling
- Monitoring and logging integration
- Secrets management for environment variables
