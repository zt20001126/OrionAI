import { useCallback, useEffect, useRef, useState } from "react";

const MAX_PENDING_SEGMENTS = 8;

/** 顺序播放音频并在中断或卸载时释放播放器和临时 URL。 */
export function useAssistantAudio() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const objectUrlRef = useRef<string | null>(null);
  const playbackResolverRef = useRef<(() => void) | null>(null);
  const generationRef = useRef(0);
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const pendingRef = useRef(0);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const stopAudio = useCallback(() => {
    generationRef.current += 1;
    queueRef.current = Promise.resolve();
    pendingRef.current = 0;
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.onended = null;
      audio.onerror = null;
      audio.removeAttribute("src");
      audio.load();
    }
    playbackResolverRef.current?.();
    playbackResolverRef.current = null;
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    objectUrlRef.current = null;
    setIsSpeaking(false);
  }, []);

  const playAudio = useCallback(
    async (audioBlob: Blob, onStart?: () => void, onEnd?: () => void) => {
      const generation = generationRef.current;
      const audio = audioRef.current;
      if (!audio) throw new Error("无法初始化音频播放器。");
      const objectUrl = URL.createObjectURL(audioBlob);
      objectUrlRef.current = objectUrl;
      audio.src = objectUrl;
      const finished = new Promise<void>((resolve, reject) => {
        playbackResolverRef.current = resolve;
        audio.onended = () => resolve();
        audio.onerror = () => reject(new Error("音频播放失败。"));
      });
      try {
        await audio.play();
        if (generation !== generationRef.current) return;
        setIsSpeaking(true);
        onStart?.();
        await finished;
        if (generation === generationRef.current) onEnd?.();
      } catch (error) {
        void finished.catch(() => undefined);
        throw error;
      } finally {
        if (generation === generationRef.current) {
          playbackResolverRef.current = null;
          if (objectUrlRef.current === objectUrl) {
            URL.revokeObjectURL(objectUrl);
            objectUrlRef.current = null;
          }
          audio.onended = null;
          audio.onerror = null;
          setIsSpeaking(false);
        }
      }
    },
    [],
  );

  const enqueueAudio = useCallback(
    (blob: Blob, onError: () => void, onStart?: () => void, onEnd?: () => void) => {
      const generation = generationRef.current;
      pendingRef.current += 1;
      queueRef.current = queueRef.current.then(async () => {
        if (generation !== generationRef.current) return;
        try {
          await playAudio(blob, onStart, onEnd);
        } catch {
          if (generation === generationRef.current) onError();
        } finally {
          if (generation === generationRef.current) pendingRef.current -= 1;
        }
      });
      // 暂停读取 SSE，直到积压片段被播放，避免浏览器无限缓存音频。
      return pendingRef.current >= MAX_PENDING_SEGMENTS ? queueRef.current : Promise.resolve();
    },
    [playAudio],
  );

  useEffect(
    () => () => {
      stopAudio();
    },
    [stopAudio],
  );
  return { audioRef, isSpeaking, playAudio, enqueueAudio, stopAudio };
}
