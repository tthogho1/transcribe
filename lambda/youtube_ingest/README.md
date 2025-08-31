# YouTube Ingest Lambda (Ruby)

This Lambda fetches YouTube video metadata via the YouTube Data API and inserts a record into DynamoDB. It does not download media files.

## Environment variables

- `DYNAMO_TABLE_NAME` (required): DynamoDB table name
- `YOUTUBE_API_KEY` (required): YouTube Data API key
- `CHANNEL_ID` (required): YouTube channel ID
- `DOWNLOAD_DIR` (optional): Download directory path
- `AWS_ACCESS_KEY_ID` (required): AWS access key
- `AWS_SECRET_ACCESS_KEY` (required): AWS secret key
- `AWS_REGION` (required): AWS region

## Handler

- Ruby handler: `handler.handler`
- Entry file: `handler.rb`

## Local test

```
ruby handler.rb "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## Deployment notes

- Package with Bundler in a Lambda-compatible environment, or use AWS SAM/Serverless Framework.
- Ensure the Lambda execution role has `dynamodb:PutItem` on your table.
