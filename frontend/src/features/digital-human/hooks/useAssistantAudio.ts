import { useCallback, useEffect, useRef, useState } from "react";

/** 负责合成音频播放及临时 Blob URL 生命周期。 */
export function useAssistantAudio() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const objectUrlRef = useRef<string | null>(null);
  const playbackResolverRef = useRef<(() => void) | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const stopAudio = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    playbackResolverRef.current?.();
    playbackResolverRef.current = null;
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setIsSpeaking(false);
  }, []);

  const playAudio = useCallback(
    async (audioBlob: Blob) => {
      stopAudio();
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
        setIsSpeaking(true);
        await finished;
      } catch (error) {
        void finished.catch(() => undefined);
        throw error;
      } finally {
        playbackResolverRef.current = null;
        if (objectUrlRef.current === objectUrl) {
          URL.revokeObjectURL(objectUrl);
          objectUrlRef.current = null;
        }
        audio.onended = null;
        audio.onerror = null;
        setIsSpeaking(false);
      }
    },
    [stopAudio],
  );

  useEffect(
    () => () => {
      stopAudio();
    },
    [stopAudio],
  );

  return { audioRef, isSpeaking, playAudio, stopAudio };
}
