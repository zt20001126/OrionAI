import { useCallback, useEffect, useRef, useState } from "react";

/** 分析实际播放音频的音量包络，并负责 AudioContext / Blob URL 生命周期。 */
export function useAssistantAudio() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const playbackResolverRef = useRef<(() => void) | null>(null);
  const [mouthOpen, setMouthOpen] = useState(0);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const stopAudio = useCallback(() => {
    if (animationRef.current !== null) {
      window.cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
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
    setMouthOpen(0);
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

      let analyser = analyserRef.current;
      if (typeof AudioContext !== "undefined") {
        const context = contextRef.current ?? new AudioContext();
        contextRef.current = context;
        if (!sourceRef.current) {
          sourceRef.current = context.createMediaElementSource(audio);
          analyser = context.createAnalyser();
          analyser.fftSize = 256;
          analyser.smoothingTimeConstant = 0.72;
          sourceRef.current.connect(analyser);
          analyser.connect(context.destination);
          analyserRef.current = analyser;
        } else {
          analyser = analyserRef.current;
        }
        await context.resume();
      }

      const finished = new Promise<void>((resolve, reject) => {
        playbackResolverRef.current = resolve;
        audio.onended = () => resolve();
        audio.onerror = () => reject(new Error("音频播放失败。"));
      });
      try {
        await audio.play();
        setIsSpeaking(true);
        if (analyser) {
          const buffer = new Uint8Array(analyser.fftSize);
          const sample = () => {
            analyser?.getByteTimeDomainData(buffer);
            let sum = 0;
            for (const value of buffer) {
              const normalized = (value - 128) / 128;
              sum += normalized * normalized;
            }
            const rms = Math.sqrt(sum / buffer.length);
            const level = Math.min(1, Math.max(0, (rms - 0.025) * 5));
            setMouthOpen((current) => current * 0.45 + level * 0.55);
            if (!audio.paused && !audio.ended) {
              animationRef.current = window.requestAnimationFrame(sample);
            }
          };
          animationRef.current = window.requestAnimationFrame(sample);
        }
        await finished;
      } catch (error) {
        void finished.catch(() => undefined);
        throw error;
      } finally {
        playbackResolverRef.current = null;
        if (animationRef.current !== null) {
          window.cancelAnimationFrame(animationRef.current);
          animationRef.current = null;
        }
        if (objectUrlRef.current === objectUrl) {
          URL.revokeObjectURL(objectUrl);
          objectUrlRef.current = null;
        }
        audio.onended = null;
        audio.onerror = null;
        setMouthOpen(0);
        setIsSpeaking(false);
      }
    },
    [stopAudio],
  );

  useEffect(
    () => () => {
      stopAudio();
      void contextRef.current?.close();
      contextRef.current = null;
      sourceRef.current = null;
      analyserRef.current = null;
    },
    [stopAudio],
  );

  return { audioRef, mouthOpen, isSpeaking, playAudio, stopAudio };
}
