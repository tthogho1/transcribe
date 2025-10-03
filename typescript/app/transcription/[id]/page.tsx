import { notFound } from 'next/navigation';
import EditableArea from '../_components/EditableArea';
import TranscriptionPageClient from './_components/TranscriptionPageClient';

async function fetchTranscription(id: string): Promise<string | null> {
  // サーバーサイドfetchは絶対パス推奨
  const base =
    process.env.NEXT_PUBLIC_BASE_URL ||
    (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : 'http://localhost:3000');
  console.log('test:' + base);
  try {
    const res = await fetch(`${base}/api/videos/${id}/transcription`, {
      cache: 'no-store',
    });
    if (!res.ok) {
      console.error('error' + res);
      return null;
    }
    // Try JSON first
    try {
      const data = await res.json();
      if (typeof data === 'string') return data;
      if (data && typeof data.transcription === 'string') return data.transcription;
    } catch (e) {
      // ignore
      console.error('error:', e);
    }
    // Fallback to text
    try {
      const txt = await res.text();
      return txt || null;
    } catch (e2) {
      console.error('error text:', e2);
    }
    return null;
  } catch {
    return null;
  }
}

export default async function TranscriptionPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const transcription = await fetchTranscription(id);
  if (transcription == null) {
    console.log('not found');
    return notFound();
  } else {
    console.log('found');
  }

  return <TranscriptionPageClient id={id} transcription={transcription} />;
}
