# YouTube Video Management API (Next.js)

This folder contains a Next.js 14 app (App Router) that exposes API routes for YouTube video data stored in DynamoDB and transcription files in S3. It replaces the previous Express server and keeps endpoint compatibility with the Flask version.

## Endpoints

- GET /api/videos
- GET /api/videos/[id]
- GET /api/videos/[id]/transcription
- GET /api/videos/transcribed
- GET /api/videos/untranscribed
- GET /api/search?q=...
- GET /api/stats
- GET /api/health

Query params and response shapes match the Python server (including `next_page_key`).

## Environment

Set the following variables via .env.local or your system environment:

- YOUTUBE_DYNAMODB_TABLE: DynamoDB table name (default: youtube_videos)
- S3_BUCKET_NAME: S3 bucket containing transcription files (object key is `${video_id}.json`)

AWS credentials are resolved by the AWS SDK default chain (env vars, shared config/credentials, IAM role, etc.).

Example `.env.local`:

YOUTUBE_DYNAMODB_TABLE=youtube_videos
S3_BUCKET_NAME=your-transcription-bucket

## Develop

Run the dev server (port 3000 by default):

npm run dev

Optionally run on a specific port (e.g., 5001):

$env:PORT=5001; npm run dev

## Build and Start

npm run build
npm start

## Project structure

- app/: Next.js App Router pages and API routes
- src/: shared server-side code (AWS clients, Dynamo client, normalization)

## Notes

- The old Express entry `src/server.ts` has been migrated to Next.js API routes and is no longer used.
