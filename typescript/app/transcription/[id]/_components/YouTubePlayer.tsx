'use client';

import { useEffect, useRef, useState } from 'react';

interface Utterance {
  start: number;
  end: number;
  text: string;
}

interface TranscriptData {
  result: {
    transcription: {
      utterances: Utterance[];
    };
  };
}

interface YouTubePlayerProps {
  videoId: string;
  onClose: () => void;
}

declare global {
  interface Window {
    YT: any;
    onYouTubeIframeAPIReady: () => void;
  }
}

export default function YouTubePlayer({ videoId, onClose }: YouTubePlayerProps) {
  const playerRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [player, setPlayer] = useState<any>(null);
  const [transcriptData, setTranscriptData] = useState<TranscriptData | null>(null);
  const [currentSubtitle, setCurrentSubtitle] = useState<string>('');
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [duration, setDuration] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const updateIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // YouTube API読み込み
  useEffect(() => {
    if (window.YT && window.YT.Player) {
      initPlayer();
    } else {
      const tag = document.createElement('script');
      tag.src = 'https://www.youtube.com/iframe_api';
      const firstScriptTag = document.getElementsByTagName('script')[0];
      firstScriptTag.parentNode?.insertBefore(tag, firstScriptTag);

      window.onYouTubeIframeAPIReady = () => {
        initPlayer();
      };
    }

    return () => {
      if (updateIntervalRef.current) {
        clearInterval(updateIntervalRef.current);
      }
      if (player) {
        player.destroy();
      }
    };
  }, []);

  // トランスクリプト読み込み
  useEffect(() => {
    loadTranscript();
  }, [videoId]);

  // 字幕更新ループ
  useEffect(() => {
    if (!player || !isPlaying) return;

    updateIntervalRef.current = setInterval(() => {
      if (player && player.getCurrentTime) {
        const time = player.getCurrentTime();
        setCurrentTime(time);
        updateSubtitles(time);
      }
    }, 100);

    return () => {
      if (updateIntervalRef.current) {
        clearInterval(updateIntervalRef.current);
      }
    };
  }, [player, isPlaying, transcriptData]);

  const loadTranscript = async () => {
    try {
      const response = await fetch(`/api/videos/${videoId}/download`);
      if (response.ok) {
        const data = await response.json();
        setTranscriptData(data);
        console.log('Transcript loaded:', data);
      }
    } catch (error) {
      console.error('Failed to load transcript:', error);
    }
  };

  const initPlayer = () => {
    if (!containerRef.current) return;

    const ytPlayer = new window.YT.Player(playerRef.current, {
      height: '500',
      width: '100%',
      videoId: videoId,
      playerVars: {
        playsinline: 1,
        controls: 0,
        rel: 0,
        showinfo: 0,
      },
      events: {
        onReady: (event: any) => {
          setPlayer(event.target);
          setDuration(event.target.getDuration());
        },
        onStateChange: (event: any) => {
          if (event.data === window.YT.PlayerState.PLAYING) {
            setIsPlaying(true);
          } else {
            setIsPlaying(false);
          }
        },
      },
    });
  };

  const updateSubtitles = (time: number) => {
    if (!transcriptData?.result?.transcription?.utterances) return;

    const currentUtterance = transcriptData.result.transcription.utterances.find(
      utterance => time >= utterance.start && time <= utterance.end
    );

    if (currentUtterance) {
      setCurrentSubtitle(currentUtterance.text);
    } else {
      setCurrentSubtitle('');
    }
  };

  const play = () => {
    if (player) {
      player.playVideo();
    }
  };

  const pause = () => {
    if (player) {
      player.pauseVideo();
    }
  };

  const stop = () => {
    if (player) {
      player.stopVideo();
      player.seekTo(0);
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (player && duration > 0) {
      const seekTime = (Number(e.target.value) / 100) * duration;
      player.seekTo(seekTime);
    }
  };

  const formatTime = (seconds: number): string => {
    if (isNaN(seconds) || seconds < 0) return '0:00';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-75 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-6xl max-h-[90vh] overflow-auto">
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold">YouTube Player with Subtitles</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="p-6">
          {/* Video Container */}
          <div ref={containerRef} className="relative bg-black rounded-lg overflow-hidden mb-6">
            <div ref={playerRef} className="w-full h-[500px]"></div>
            {currentSubtitle && (
              <div className="absolute bottom-16 left-1/2 transform -translate-x-1/2 bg-black bg-opacity-80 text-white px-5 py-3 rounded text-lg font-bold text-center max-w-[80%] shadow-lg">
                {currentSubtitle}
              </div>
            )}
          </div>

          {/* Controls */}
          <div className="bg-gray-50 rounded-lg p-4 mb-6">
            <div className="flex items-center gap-4 mb-3">
              <button
                onClick={play}
                className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition"
              >
                再生
              </button>
              <button
                onClick={pause}
                className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition"
              >
                一時停止
              </button>
              <button
                onClick={stop}
                className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition"
              >
                停止
              </button>
              <span className="ml-auto text-sm text-gray-600">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={duration > 0 ? (currentTime / duration) * 100 : 0}
              onChange={handleSeek}
              className="w-full h-2 bg-gray-300 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
          </div>

          {/* Info */}
          <div className="text-sm text-gray-600">
            <p>Video ID: {videoId}</p>
            {transcriptData && (
              <p className="mt-1">
                Loaded {transcriptData.result.transcription.utterances.length} subtitles
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
