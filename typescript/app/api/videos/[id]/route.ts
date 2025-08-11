import { NextRequest, NextResponse } from 'next/server';
import { YouTubeDynamoClient } from '../../../../src/dynamoClient';

const tableName = process.env.YOUTUBE_DYNAMODB_TABLE || 'youtube_videos';
const client = new YouTubeDynamoClient(tableName);

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  try {
    const video = await client.getVideoById(params.id);
    if (!video) return NextResponse.json({ error: 'Video not found' }, { status: 404 });
    return NextResponse.json({ video, video_id: params.id });
  } catch (e: any) {
    return NextResponse.json({ error: e.message || String(e) }, { status: 500 });
  }
}
