"use client";

import { useEffect, useRef, useState } from "react";
import { extractYoutubeVideoId, looksLikeDirectVideoFile } from "@/lib/utils/youtube";
import type { ProgressUpdateInput, ResourceProgress } from "@/lib/types/progress";

interface VideoProgressPlayerProps {
  sourceUrl: string;
  initialProgress: ResourceProgress;
  onSave: (payload: ProgressUpdateInput, options?: { immediate?: boolean }) => void;
  onFlush: () => void;
}

const POLL_INTERVAL_MS = 5000;

/** Embeds a playable video and tracks its position -- YouTube via the
 * IFrame Player API (matches the video IDs the backend can already fetch
 * transcripts for, see lib/utils/youtube.ts), or a native <video> tag for a
 * direct file URL. Any other video source (e.g. a Vimeo page) can't be
 * embedded/tracked here -- the caller falls back to the plain external link
 * it already renders, plus the manual "Mark as complete" action. */
export function VideoProgressPlayer({
  sourceUrl,
  initialProgress,
  onSave,
  onFlush,
}: VideoProgressPlayerProps) {
  const youtubeId = extractYoutubeVideoId(sourceUrl);
  if (youtubeId) {
    return (
      <YoutubePlayer
        videoId={youtubeId}
        initialProgress={initialProgress}
        onSave={onSave}
        onFlush={onFlush}
      />
    );
  }
  if (looksLikeDirectVideoFile(sourceUrl)) {
    return (
      <NativeVideoPlayer
        sourceUrl={sourceUrl}
        initialProgress={initialProgress}
        onSave={onSave}
        onFlush={onFlush}
      />
    );
  }
  return null;
}

// --- YouTube (IFrame Player API) ---------------------------------------

interface YTPlayerLike {
  getCurrentTime: () => number;
  getDuration: () => number;
  getIframe: () => HTMLIFrameElement;
  destroy: () => void;
}

let youtubeApiPromise: Promise<any> | null = null;

/** Loads the YouTube IFrame API script at most once per page, however many
 * VideoProgressPlayers mount -- subsequent calls reuse the same promise. */
function loadYoutubeApi(): Promise<any> {
  const w = window as any;
  if (w.YT?.Player) return Promise.resolve(w.YT);
  if (youtubeApiPromise) return youtubeApiPromise;
  youtubeApiPromise = new Promise((resolve) => {
    const previousCallback = w.onYouTubeIframeAPIReady;
    w.onYouTubeIframeAPIReady = () => {
      previousCallback?.();
      resolve(w.YT);
    };
    if (!document.querySelector('script[src="https://www.youtube.com/iframe_api"]')) {
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(script);
    }
  });
  return youtubeApiPromise;
}

function YoutubePlayer({
  videoId,
  initialProgress,
  onSave,
  onFlush,
}: {
  videoId: string;
  initialProgress: ResourceProgress;
  onSave: VideoProgressPlayerProps["onSave"];
  onFlush: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YTPlayerLike | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    loadYoutubeApi().then((YT) => {
      if (cancelled || !containerRef.current) return;

      const stopPolling = () => {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      };

      const saveCurrentPosition = (options?: { immediate?: boolean }) => {
        const player = playerRef.current;
        if (!player) return;
        const duration = player.getDuration();
        const position = player.getCurrentTime();
        if (duration > 0) {
          onSave({ positionSeconds: position, durationSeconds: duration }, options);
        }
      };

      const player = new YT.Player(containerRef.current, {
        videoId,
        playerVars: { start: Math.floor(initialProgress.positionSeconds ?? 0) },
        events: {
          onReady: (event: any) => {
            const iframe = event.target.getIframe();
            iframe?.classList.add("absolute", "inset-0", "h-full", "w-full");
          },
          onStateChange: (event: any) => {
            if (event.data === YT.PlayerState.PLAYING) {
              stopPolling();
              pollRef.current = setInterval(saveCurrentPosition, POLL_INTERVAL_MS);
            } else if (event.data === YT.PlayerState.ENDED) {
              stopPolling();
              const duration = playerRef.current?.getDuration() ?? 0;
              if (duration > 0) {
                onSave({ positionSeconds: duration, durationSeconds: duration }, { immediate: true });
              }
            } else {
              // Paused, buffering, cued, etc. -- stop polling and flush the
              // last known position immediately rather than waiting for the
              // next 5s tick.
              stopPolling();
              saveCurrentPosition({ immediate: true });
            }
          },
        },
      }) as YTPlayerLike;
      playerRef.current = player;
    });

    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
      onFlush();
      playerRef.current?.destroy?.();
      playerRef.current = null;
    };
    // Intentionally only re-run if the video itself changes -- initialProgress/onSave/onFlush
    // identity churn shouldn't tear down and recreate the embedded player.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-base-border bg-black">
      <div ref={containerRef} />
    </div>
  );
}

// --- Direct video file (native <video>) ---------------------------------

function NativeVideoPlayer({
  sourceUrl,
  initialProgress,
  onSave,
  onFlush,
}: {
  sourceUrl: string;
  initialProgress: ResourceProgress;
  onSave: VideoProgressPlayerProps["onSave"];
  onFlush: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const restoredRef = useRef(false);

  useEffect(() => {
    return () => onFlush();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleLoadedMetadata() {
    const video = videoRef.current;
    if (!video || restoredRef.current) return;
    restoredRef.current = true;
    const saved = initialProgress.positionSeconds ?? 0;
    if (saved > 0 && saved < video.duration) {
      video.currentTime = saved;
    }
  }

  function handleTimeUpdate() {
    const video = videoRef.current;
    if (!video || !video.duration) return;
    onSave({ positionSeconds: video.currentTime, durationSeconds: video.duration });
  }

  function handlePauseOrEnded() {
    const video = videoRef.current;
    if (!video || !video.duration) return;
    onSave({ positionSeconds: video.currentTime, durationSeconds: video.duration }, { immediate: true });
  }

  return (
    <video
      ref={videoRef}
      src={sourceUrl}
      controls
      className="aspect-video w-full rounded-xl border border-base-border bg-black"
      onLoadedMetadata={handleLoadedMetadata}
      onTimeUpdate={handleTimeUpdate}
      onPause={handlePauseOrEnded}
      onEnded={handlePauseOrEnded}
    />
  );
}
