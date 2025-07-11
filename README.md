# Audio Transcription and Vectorization System

A comprehensive Python system for processing audio files through Amazon Transcribe and vectorizing the resulting text for semantic search using Zilliz Cloud.

## Overview

This system provides an end-to-end solution for:

- Monitoring AWS SQS for audio file notifications
- Automatically triggering Amazon Transcribe jobs
- Extracting text from transcription results stored in S3
- Converting text into semantic vectors for similarity search
- Storing and querying vectorized content in Zilliz Cloud

## Features

### 🎵 Audio Processing

- **Automatic Transcription**: Monitors SQS queue for new audio files
- **AWS Integration**: Seamless integration with Amazon Transcribe
- **Format Support**: Supports MP4 and other audio formats
- **Japanese Language**: Optimized for Japanese audio transcription

### 📄 Text Extraction

- **S3 JSON Reader**: Extracts text from JSON files stored in S3
- **Smart Detection**: Automatically detects Amazon Transcribe result format
- **Generic JSON Support**: Can extract text from any JSON structure
- **Batch Processing**: Process multiple files simultaneously

### 🔍 Vector Search

- **Semantic Search**: Advanced similarity search using sentence transformers
- **Japanese Text Processing**: Optimized for Japanese text vectorization
- **Chunking**: Intelligent text chunking for better search granularity
- **Zilliz Cloud Integration**: Scalable vector database storage

## Architecture

```
[Audio Files] → [SQS Queue] → [Amazon Transcribe] → [S3 JSON Results]
                                                           ↓
[Zilliz Cloud] ← [Vector Database] ← [Text Chunking] ← [Text Extraction]
```

## Installation

### Prerequisites

- Python 3.8+
- AWS Account with appropriate permissions
- Zilliz Cloud account

### Setup

1. **Clone the repository**

```bash
git clone <repository-url>
cd Transcribe
```

2. **Create virtual environment**

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Configure environment variables**
   Create a `.env` file in the `src/` directory:

```env
# AWS Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-northeast-1
SQS_QUEUE_URL=https://sqs.region.amazonaws.com/account/queue-name
TRANSCRIBE_OUTPUT_BUCKET=your-output-bucket

# S3 Configuration
S3_BUCKET_NAME=your-transcribe-results-bucket

# Zilliz Cloud Configuration
ZILLIZ_URI=https://your-zilliz-endpoint
ZILLIZ_TOKEN=your_zilliz_token
```

## Usage

### Local Development

#### 1. Audio Transcription Service

Start the transcription service to monitor SQS for new audio files:

```bash
cd src
python AmazonTranscribe.py
```

This service will:

- Monitor the configured SQS queue
- Automatically start transcription jobs for new audio files
- Process messages continuously

### 2. Text Extraction from S3

Extract text from JSON files stored in S3:

```python
from extract_text_fromS3 import S3JsonTextExtractor

# Initialize extractor
extractor = S3JsonTextExtractor()

# Extract from single file
result = extractor.extract_text_from_s3_json(
    bucket_name="your-bucket",
    object_key="path/to/file.json"
)

# Batch processing
results = extractor.batch_extract_texts(
    bucket_name="your-bucket",
    prefix="transcribe-output/"
)
```

### 3. Text Vectorization and Search

Process extracted text and enable semantic search:

```python
from conversation_vectorization import ConversationVectorizer
import os

# Initialize vectorizer
vectorizer = ConversationVectorizer(
    zilliz_uri=os.getenv("ZILLIZ_URI"),
    zilliz_token=os.getenv("ZILLIZ_TOKEN")
)

# Process text
chunks = vectorizer.process_monologue(extracted_text)

# Search similar content
results = vectorizer.search_similar("営業について", limit=5)
for result in results:
    print(f"Text: {result['text'][:100]}...")
    print(f"Score: {result['score']:.3f}\n")
```

### 4. AI Chat Server

Start the intelligent chat server that combines Zilliz search with OpenAI:

```bash
cd src
python chat_server.py
```

The chat server provides:

- **Web Interface**: Access at `http://localhost:5000`
- **REST API**: `/api/chat` and `/api/search` endpoints
- **WebSocket**: Real-time chat functionality
- **RAG System**: Retrieval-Augmented Generation using past conversations

#### Chat Server Features

- 🔍 **Semantic Search**: Find relevant conversations using vector similarity
- 🤖 **AI Responses**: Generate contextual answers with OpenAI
- 💬 **Real-time Chat**: WebSocket-based chat interface
- 📚 **Source Citations**: Show which conversations informed the answer
- 🌐 **Multi-interface**: Web UI, REST API, and WebSocket support

#### API Usage Examples

**Search for conversations:**

```bash
curl -X POST http://localhost:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "営業について", "limit": 5}'
```

**Chat with AI:**

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "AIの活用方法を教えて"}'
```

#### Test the Chat Server

```bash
# Run comprehensive tests
python src/test_chat_server.py

# Test specific functionality
python -c "
import requests
response = requests.post('http://localhost:5000/api/search',
    json={'query': 'test', 'limit': 3})
print(response.json())
"
```

### 5. Complete Pipeline

Run the complete pipeline for processing transcription results:

```bash
cd src
python conversation_vectorization.py
```

## Project Structure

```
Transcribe/
├── src/
│   ├── .env                           # Environment configuration
│   ├── AmazonTranscribe.py           # SQS monitoring and transcription
│   ├── extract_text_fromS3.py       # S3 JSON text extraction
│   └── conversation_vectorization.py # Text vectorization and search
├── requirements.txt                   # Python dependencies
└── README.md                         # This file
```

## Key Components

### AmazonTranscribe.py

- **Purpose**: Monitors SQS queue for audio file notifications
- **Features**: Automatic transcription job creation, error handling
- **Output**: Transcribed results stored in specified S3 bucket

### extract_text_fromS3.py

- **Purpose**: Extracts text content from JSON files in S3
- **Features**: Auto-detection of Transcribe format, generic JSON support
- **Methods**: Single file and batch processing capabilities

### conversation_vectorization.py

- **Purpose**: Converts text to vectors and enables semantic search
- **Features**: Text chunking, Japanese language optimization, similarity search
- **Integration**: Zilliz Cloud for scalable vector storage

## Configuration

### AWS Permissions Required

Your AWS user/role needs the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "transcribe:StartTranscriptionJob",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:PutObject"
      ],
      "Resource": "*"
    }
  ]
}
```

### Zilliz Cloud Setup

1. Create a Zilliz Cloud account
2. Create a new cluster
3. Obtain the connection URI and token
4. Configure in your `.env` file

## Monitoring and Logging

The system includes comprehensive logging:

- **INFO**: Processing status and progress
- **ERROR**: Failed operations and exceptions
- **DEBUG**: Detailed operation information

Logs are output to console with timestamps and severity levels.

## Troubleshooting

### Common Issues

1. **SQS Connection Issues**

   - Verify AWS credentials and region
   - Check SQS queue URL format
   - Ensure proper IAM permissions

2. **Transcribe Job Failures**

   - Verify audio file format (MP4 supported)
   - Check S3 bucket permissions
   - Ensure file is accessible to Transcribe service

3. **Zilliz Connection Issues**

   - Verify URI and token format
   - Check network connectivity
   - Ensure cluster is running

4. **Text Extraction Issues**
   - Verify S3 bucket access permissions
   - Check JSON file format
   - Ensure proper file encoding (UTF-8)

## Performance Considerations

- **Batch Processing**: Use batch operations for multiple files
- **Chunk Size**: Adjust chunk size based on your search requirements
- **Vector Dimensions**: Consider model dimensions for storage optimization
- **Connection Pooling**: Reuse AWS clients when possible

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:

1. Check the troubleshooting section
2. Review logs for error details
3. Create an issue in the repository

## Dependencies

Key dependencies include:

- `boto3`: AWS SDK for Python
- `sentence-transformers`: Text embedding models
- `pymilvus`: Zilliz/Milvus vector database client
- `langchain`: Text processing utilities
- `python-dotenv`: Environment variable management

See `requirements.txt` for complete dependency list.

## Docker and ECS Deployment

### Docker Build and Run

#### Build Docker Image

```bash
# Build the Docker image
docker build -t transcribe-service:latest .

# Run locally with Docker
docker run -d \
  --name transcribe-service \
  --env-file src/.env \
  transcribe-service:latest

# Run with docker-compose
docker-compose up -d
```

#### Docker Commands

```bash
# View logs
docker logs transcribe-service -f

# Stop container
docker stop transcribe-service

# Remove container
docker rm transcribe-service
```

### ECS Deployment

#### Prerequisites

- AWS CLI configured with appropriate permissions
- Docker installed
- ECR repository created

#### Infrastructure Setup

1. **Deploy infrastructure using CloudFormation:**

```bash
aws cloudformation deploy \
  --template-file cloudformation-infrastructure.yaml \
  --stack-name transcribe-infrastructure \
  --parameter-overrides \
    Environment=production \
    S3BucketName=your-transcribe-bucket \
    SQSQueueName=your-audio-queue \
  --capabilities CAPABILITY_NAMED_IAM
```

2. **Store secrets in AWS Systems Manager Parameter Store:**

```bash
# Store AWS credentials
aws ssm put-parameter \
  --name "/transcribe/aws_access_key_id" \
  --value "YOUR_ACCESS_KEY" \
  --type "SecureString"

aws ssm put-parameter \
  --name "/transcribe/aws_secret_access_key" \
  --value "YOUR_SECRET_KEY" \
  --type "SecureString"

# Store other configuration
aws ssm put-parameter \
  --name "/transcribe/sqs_queue_url" \
  --value "https://sqs.region.amazonaws.com/account/queue-name" \
  --type "String"

aws ssm put-parameter \
  --name "/transcribe/zilliz_uri" \
  --value "https://your-zilliz-endpoint" \
  --type "String"

aws ssm put-parameter \
  --name "/transcribe/zilliz_token" \
  --value "YOUR_ZILLIZ_TOKEN" \
  --type "SecureString"
```

#### Deploy to ECS

1. **Make the deployment script executable:**

```bash
chmod +x deploy-to-ecs.sh
```

2. **Run the deployment:**

```bash
./deploy-to-ecs.sh production ap-northeast-1
```

#### ECS Service Configuration

- **CPU**: 1024 (1 vCPU)
- **Memory**: 2048 MB (2 GB)
- **Network**: Fargate with public subnets
- **Auto Scaling**: Can be configured based on CPU/memory usage
- **Health Checks**: Built-in application health checks

#### Monitoring

```bash
# View service status
aws ecs describe-services \
  --cluster transcribe-cluster \
  --services transcribe-service

# View logs
aws logs tail /ecs/transcribe-service --follow

# View task details
aws ecs describe-tasks \
  --cluster transcribe-cluster \
  --tasks TASK_ARN
```

### Container Resource Requirements

| Component          | CPU    | Memory | Description                       |
| ------------------ | ------ | ------ | --------------------------------- |
| Transcribe Service | 1 vCPU | 2 GB   | SQS monitoring and job creation   |
| Vector Service     | 2 vCPU | 4 GB   | Text processing and vectorization |

### Environment Variables for ECS

The following environment variables are configured via AWS Systems Manager Parameter Store:

| Variable                   | Description           | Type         |
| -------------------------- | --------------------- | ------------ |
| `AWS_ACCESS_KEY_ID`        | AWS Access Key        | SecureString |
| `AWS_SECRET_ACCESS_KEY`    | AWS Secret Key        | SecureString |
| `AWS_REGION`               | AWS Region            | String       |
| `SQS_QUEUE_URL`            | SQS Queue URL         | String       |
| `TRANSCRIBE_OUTPUT_BUCKET` | S3 Output Bucket      | String       |
| `S3_BUCKET_NAME`           | S3 Bucket for Results | String       |
| `ZILLIZ_URI`               | Zilliz Cloud URI      | String       |
| `ZILLIZ_TOKEN`             | Zilliz Cloud Token    | SecureString |

## AWS CodeBuild CI/CD Pipeline

### Overview

This project includes a complete CI/CD pipeline using AWS CodeBuild that automatically builds Docker images and deploys them to ECS when code is pushed to the repository.

### Pipeline Features

- **Automatic Builds**: Triggered on git push to specified branch
- **Multi-stage Docker Builds**: Optimized for production
- **ECR Integration**: Automatic image pushing to Amazon ECR
- **ECS Deployment**: Seamless updates to ECS services
- **Security Scanning**: Built-in container vulnerability scanning
- **Artifact Management**: Automated cleanup of old images

### Setup CodeBuild Pipeline

#### 1. Quick Setup (Automated)

```bash
# Make the setup script executable
chmod +x setup-codebuild.sh

# Run the setup script
./setup-codebuild.sh
```

#### 2. Manual Setup

**Deploy CodeBuild Infrastructure:**

```bash
aws cloudformation deploy \
  --template-file codebuild-infrastructure.yaml \
  --stack-name transcribe-codebuild \
  --parameter-overrides \
    ProjectName=transcribe-service \
    Environment=production \
    GitHubRepo=https://github.com/your-username/transcribe.git \
    GitHubBranch=main \
  --capabilities CAPABILITY_NAMED_IAM
```

**Create ECR Repository:**

```bash
aws ecr create-repository \
  --repository-name transcribe-service \
  --image-scanning-configuration scanOnPush=true
```

**Set up Parameters in Parameter Store:**

```bash
# Core AWS settings
aws ssm put-parameter \
  --name "/transcribe/aws_access_key_id" \
  --value "YOUR_ACCESS_KEY" \
  --type "SecureString"

aws ssm put-parameter \
  --name "/transcribe/aws_secret_access_key" \
  --value "YOUR_SECRET_KEY" \
  --type "SecureString"

# Application settings
aws ssm put-parameter \
  --name "/transcribe/sqs_queue_url" \
  --value "https://sqs.region.amazonaws.com/account/queue" \
  --type "String"

aws ssm put-parameter \
  --name "/transcribe/zilliz_uri" \
  --value "https://your-zilliz-endpoint" \
  --type "String"

aws ssm put-parameter \
  --name "/transcribe/zilliz_token" \
  --value "YOUR_ZILLIZ_TOKEN" \
  --type "SecureString"
```

### Build Specifications

The project includes two buildspec files:

#### `buildspec.yml` (Basic)

- Simple Docker build and push
- Suitable for basic CI/CD needs
- Minimal configuration required

#### `buildspec-advanced.yml` (Production)

- Comprehensive build with security scanning
- Multi-tag strategy (latest, commit hash, build number, timestamp)
- Advanced error handling and logging
- Production-ready configuration

### Build Process

1. **Pre-build Phase**

   - ECR login and repository validation
   - Build environment setup
   - Variable configuration

2. **Build Phase**

   - Docker image building with caching
   - Security vulnerability scanning
   - Image testing and validation

3. **Post-build Phase**
   - Multi-tag image pushing to ECR
   - ECS task definition updates
   - Deployment artifact creation

### Monitoring and Management

#### View Build Status

```bash
# List recent builds
aws codebuild list-builds-for-project \
  --project-name transcribe-service

# Get build details
aws codebuild batch-get-builds \
  --ids BUILD_ID
```

#### Monitor Build Logs

```bash
# Tail build logs in real-time
aws logs tail /aws/codebuild/transcribe-service --follow

# View specific log stream
aws logs get-log-events \
  --log-group-name /aws/codebuild/transcribe-service \
  --log-stream-name LOG_STREAM_NAME
```

#### Trigger Manual Builds

```bash
# Start a build from the main branch
aws codebuild start-build \
  --project-name transcribe-service

# Start a build from a specific branch
aws codebuild start-build \
  --project-name transcribe-service \
  --source-version feature-branch
```

### Build Artifacts

Each successful build produces:

- `imagedefinitions.json`: ECS container image definitions
- `ecs-task-definition-final.json`: Updated ECS task definition
- `deployment-summary.json`: Build and deployment metadata

### Environment Variables

| Variable             | Source            | Description               |
| -------------------- | ----------------- | ------------------------- |
| `AWS_DEFAULT_REGION` | Build Environment | AWS region for deployment |
| `AWS_ACCOUNT_ID`     | Parameter Store   | AWS account ID            |
| `IMAGE_REPO_NAME`    | Build Environment | ECR repository name       |
| `ECS_CLUSTER_NAME`   | Parameter Store   | Target ECS cluster        |
| `ECS_SERVICE_NAME`   | Parameter Store   | Target ECS service        |

### Security Features

- **Container Scanning**: Trivy security scanner integration
- **IAM Least Privilege**: Minimal required permissions
- **Secrets Management**: Parameter Store for sensitive data
- **Image Signing**: Optional container image signing
- **Vulnerability Reports**: Security scan results in CodeBuild reports

### Cost Optimization

- **Build Caching**: Docker layer and pip package caching
- **Lifecycle Policies**: Automatic cleanup of old ECR images
- **Compute Optimization**: Right-sized build instances
- **Artifact Retention**: 30-day artifact lifecycle

### Troubleshooting

#### Common Issues

1. **Build Fails with ECR Login Error**

   ```bash
   # Check IAM permissions for ECR
   aws ecr get-login-password --region us-east-1
   ```

2. **Parameter Store Access Denied**

   ```bash
   # Verify parameter exists and permissions
   aws ssm get-parameter --name "/transcribe/parameter-name"
   ```

3. **Docker Build Out of Space**

   - Enable Docker layer caching in buildspec
   - Use multi-stage builds to reduce image size

4. **ECS Deployment Fails**
   - Check ECS service and task definition compatibility
   - Verify IAM roles for ECS tasks

#### Debug Commands

```bash
# Check CodeBuild project configuration
aws codebuild batch-get-projects --names transcribe-service

# View parameter store values
aws ssm get-parameters-by-path --path "/transcribe" --recursive

# Check ECR repository
aws ecr describe-repositories --repository-names transcribe-service

# View ECS service status
aws ecs describe-services --cluster transcribe-cluster --services transcribe-service
```
