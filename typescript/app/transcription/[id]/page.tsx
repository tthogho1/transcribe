import { notFound } from 'next/navigation';
import EditableArea from '../_components/EditableArea';

async function fetchTranscription(id: string): Promise<string | null> {
  // サーバーサイドfetchは絶対パス推奨
  const base =
    process.env.NEXT_PUBLIC_BASE_URL ||
    (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : 'http://localhost:3000');
  try {
    const res = await fetch(`${base}/api/videos/${id}/transcription`, {
      cache: 'no-store',
    });
    if (!res.ok) return null;
    // Try JSON first
    try {
      const data = await res.json();
      if (typeof data === 'string') return data;
      if (data && typeof data.transcription === 'string') return data.transcription;
    } catch {
      // ignore
    }
    // Fallback to text
    try {
      const txt = await res.text();
      return txt || null;
    } catch {}
    return null;
  } catch {
    return null;
  }
}

export default async function TranscriptionPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const transcription = await fetchTranscription(id);
  if (transcription == null) return notFound();

  return (
    <div className="container-max">
      <div className="flex items-center justify-between py-6">
        <h1 className="text-2xl font-semibold">Transcription Editor</h1>
        <a
          href={`https://www.youtube.com/watch?v=${id}`}
          target="_blank"
          rel="noreferrer"
          className="btn btn-outline"
        >
          Open YouTube
        </a>
      </div>

      <div className="card p-4">
        <div className="mb-3 text-sm text-gray-500">Video ID: {id}</div>
        <EditableArea id={id} initialValue={transcription} />
      </div>
    </div>
  );
}
