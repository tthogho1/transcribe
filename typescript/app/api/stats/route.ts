import { NextResponse } from 'next/server';
import { YouTubeDynamoClient } from '../../../src/dynamoClient';

const tableName = process.env.YOUTUBE_DYNAMODB_TABLE || 'youtube_videos';
const client = new YouTubeDynamoClient(tableName);

export async function GET() {
  try {
    console.log('Fetching video statistics');
    const stats = await client.getStats();
    console.log('Video statistics fetched successfully' + stats);

    return NextResponse.json({ stats, timestamp: new Date().toISOString() });
  } catch (e: any) {
    return NextResponse.json({ error: e.message || String(e) }, { status: 500 });
  }
}
