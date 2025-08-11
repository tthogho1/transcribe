import { NextResponse } from 'next/server';
import { YouTubeDynamoClient } from '../../../src/dynamoClient';

const tableName = process.env.YOUTUBE_DYNAMODB_TABLE || 'youtube_videos';
const client = new YouTubeDynamoClient(tableName);

export async function GET() {
  try {
    const ok = await client.testConnection();
    return NextResponse.json({
      status: ok ? 'healthy' : 'degraded',
      timestamp: new Date().toISOString(),
      services: { dynamodb: ok ? 'connected' : 'disconnected', table_name: tableName },
      version: '1.0.0',
    });
  } catch (e: any) {
    return NextResponse.json(
      { status: 'unhealthy', error: e.message || String(e) },
      { status: 500 }
    );
  }
}
