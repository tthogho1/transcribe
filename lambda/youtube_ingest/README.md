# YouTube Ingest Lambda (Ruby)

This Lambda fetches YouTube video metadata via the YouTube Data API and inserts a record into DynamoDB. It does not download media files.

## Environment variables
- `DDB_TABLE_NAME` (required): DynamoDB table name
- `YT_API_KEY` (required): YouTube Data API key

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
