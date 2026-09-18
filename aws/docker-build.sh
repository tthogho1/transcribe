#!/bin/bash

# Build and run script for Flask Chat Server Docker container (aws/Dockerfile.production)

set -e

# This script lives in aws/, but the Dockerfile, docker-compose.chat.yml,
# .env and the build context (".") are all at the repo root - cd there
# regardless of the caller's current directory.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

BUILD_ONLY=false
NO_CACHE=false

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -b, --build-only         Build only, don't run containers"
    echo "  -n, --no-cache           Build without using cache"
    echo "  -h, --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Build and run"
    echo "  $0 -b -n                             # Build only with no cache"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--build-only)
            BUILD_ONLY=true
            shift
            ;;
        -n|--no-cache)
            NO_CACHE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

echo -e "${BLUE}🐳 Flask Chat Server Docker Build Script${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "Build only: ${YELLOW}$BUILD_ONLY${NC}"
echo -e "No cache: ${YELLOW}$NO_CACHE${NC}"
echo ""

# Check if .env file exists
if [[ ! -f ".env" ]]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found. Make sure to create one with your configuration.${NC}"
    echo ""
fi

# Set Docker build args
BUILD_ARGS=""
if [[ "$NO_CACHE" == "true" ]]; then
    BUILD_ARGS="--no-cache"
fi

echo -e "${GREEN}🚀 Building image (aws/Dockerfile.production)...${NC}"
docker build $BUILD_ARGS -f aws/Dockerfile.production -t transcribe-chat:prod .

if [[ "$BUILD_ONLY" == "false" ]]; then
    echo -e "${BLUE}Starting environment...${NC}"
    docker-compose -f docker-compose.chat.yml up -d chat-server-prod

    echo -e "${GREEN}✅ Environment started!${NC}"
    echo -e "${YELLOW}📊 Chat Server: http://localhost:5001${NC}"
    echo -e "${YELLOW}🏥 Health Check: http://localhost:5001/health${NC}"
    echo ""
    echo -e "${BLUE}To view logs: docker-compose -f docker-compose.chat.yml logs -f chat-server-prod${NC}"
    echo -e "${BLUE}To stop: docker-compose -f docker-compose.chat.yml down${NC}"
fi

if [[ "$BUILD_ONLY" == "true" ]]; then
    echo -e "${GREEN}✅ Build completed successfully!${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Done!${NC}"
