import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient } from '@aws-sdk/lib-dynamodb';
import { S3Client } from '@aws-sdk/client-s3';

export const dynamo = new DynamoDBClient({});
export const ddb = DynamoDBDocumentClient.from(dynamo);
export const s3 = new S3Client({});
