#!/bin/bash

# Build and run script for Flask Chat Server Docker containers

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="development"
BUILD_ONLY=false
NO_CACHE=false

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -e, --env ENVIRONMENT    Set environment (development|production) [default: development]"
    echo "  -b, --build-only         Build only, don't run containers"
    echo "  -n, --no-cache           Build without using cache"
    echo "  -h, --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Build and run development environment"
    echo "  $0 -e production                     # Build and run production environment"
    echo "  $0 -b -n                             # Build only with no cache"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--env)
            ENVIRONMENT="$2"
            shift 2
            ;;
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

# Validate environment
if [[ "$ENVIRONMENT" != "development" && "$ENVIRONMENT" != "production" ]]; then
    echo -e "${RED}Error: Environment must be 'development' or 'production'${NC}"
    exit 1
fi

echo -e "${BLUE}🐳 Flask Chat Server Docker Build Script${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "Environment: ${YELLOW}$ENVIRONMENT${NC}"
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

# Build based on environment
if [[ "$ENVIRONMENT" == "development" ]]; then
    echo -e "${GREEN}🔧 Building development environment...${NC}"
    
    # Build development image
    echo -e "${BLUE}Building development image...${NC}"
    docker build $BUILD_ARGS -f Dockerfile.dev -t transcribe-chat:dev .
    
    if [[ "$BUILD_ONLY" == "false" ]]; then
        echo -e "${BLUE}Starting development environment...${NC}"
        docker-compose -f docker-compose.chat.yml up -d chat-server
        
        echo -e "${GREEN}✅ Development environment started!${NC}"
        echo -e "${YELLOW}📊 Chat Server: http://localhost:5000${NC}"
        echo -e "${YELLOW}🏥 Health Check: http://localhost:5000/health${NC}"
        echo ""
        echo -e "${BLUE}To view logs: docker-compose -f docker-compose.chat.yml logs -f chat-server${NC}"
        echo -e "${BLUE}To stop: docker-compose -f docker-compose.chat.yml down${NC}"
    fi
    
elif [[ "$ENVIRONMENT" == "production" ]]; then
    echo -e "${GREEN}🚀 Building production environment...${NC}"
    
    # Build production image
    echo -e "${BLUE}Building production image...${NC}"
    docker build $BUILD_ARGS -f Dockerfile.production -t transcribe-chat:prod .
    
    if [[ "$BUILD_ONLY" == "false" ]]; then
        echo -e "${BLUE}Starting production environment...${NC}"
        docker-compose -f docker-compose.chat.yml --profile production up -d chat-server-prod
        
        echo -e "${GREEN}✅ Production environment started!${NC}"
        echo -e "${YELLOW}📊 Chat Server: http://localhost:5001${NC}"
        echo -e "${YELLOW}🏥 Health Check: http://localhost:5001/health${NC}"
        echo ""
        echo -e "${BLUE}To view logs: docker-compose -f docker-compose.chat.yml logs -f chat-server-prod${NC}"
        echo -e "${BLUE}To stop: docker-compose -f docker-compose.chat.yml --profile production down${NC}"
    fi
fi

if [[ "$BUILD_ONLY" == "true" ]]; then
    echo -e "${GREEN}✅ Build completed successfully!${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Done!${NC}"
