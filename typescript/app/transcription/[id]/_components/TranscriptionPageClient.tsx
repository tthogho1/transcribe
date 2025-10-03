'use client';

import { useState } from 'react';
import EditableArea from '../../_components/EditableArea';
import YouTubePlayer from './YouTubePlayer';

interface TranscriptionPageClientProps {
  id: string;
  transcription: string;
}

export default function TranscriptionPageClient({
  id,
  transcription,
}: TranscriptionPageClientProps) {
  const [showPlayer, setShowPlayer] = useState(false);

  return (
    <div className="container-max">
      <div className="flex items-center justify-between py-6">
        <h1 className="text-2xl font-semibold">Transcription Editor</h1>
        <button onClick={() => setShowPlayer(!showPlayer)} className="btn btn-outline">
          {showPlayer ? 'Close YouTube' : 'Open YouTube'}
        </button>
      </div>

      {showPlayer && (
        <div className="mb-4">
          <YouTubePlayer videoId={id} onClose={() => setShowPlayer(false)} />
        </div>
      )}

      <div className="card p-4">
        <div className="mb-3 text-sm text-gray-500">Video ID: {id}</div>
        <EditableArea id={id} initialValue={transcription} />
      </div>
    </div>
  );
}
