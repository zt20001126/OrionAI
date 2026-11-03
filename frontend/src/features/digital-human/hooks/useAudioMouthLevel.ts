import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

/** 从已有播放器读取音量包络，和语音合成及 3D 渲染保持解耦。 */
export function useAudioMouthLevel(
  audioRef: RefObject<HTMLAudioElement | null>,
  isSpeaking: boolean,
): number {
  const contextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);
  const [mouthOpen, setMouthOpen] = useState(0);

  useEffect(() => {
    if (!isSpeaking) return;

    const audio = audioRef.current;
    if (!audio || typeof AudioContext === "undefined") return;

    let cancelled = false;
    let context = contextRef.current;
    try {
      context ??= new AudioContext();
      contextRef.current = context;

      if (!analyserRef.current) {
        const source = context.createMediaElementSource(audio);
        const analyser = context.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.72;
        source.connect(analyser);
        analyser.connect(context.destination);
        sourceRef.current = source;
        analyserRef.current = analyser;
      }
    } catch {
      return;
    }

    const analyser = analyserRef.current;
    if (!analyser) return;

    const buffer = new Uint8Array(analyser.fftSize);
    let lastMouthUpdate = 0;
    const sample = (timestamp: number) => {
      if (cancelled) return;
      analyser.getByteTimeDomainData(buffer);
      let sum = 0;
      for (const value of buffer) {
        const normalized = (value - 128) / 128;
        sum += normalized * normalized;
      }
      const rms = Math.sqrt(sum / buffer.length);
      const level = Math.min(1, Math.max(0, (rms - 0.025) * 5));
      if (timestamp - lastMouthUpdate >= 40) {
        setMouthOpen((current) => current * 0.45 + level * 0.55);
        lastMouthUpdate = timestamp;
      }

      if (!audio.paused && !audio.ended) {
        animationRef.current = window.requestAnimationFrame(sample);
      } else {
        setMouthOpen(0);
      }
    };

    void context
      .resume()
      .then(() => {
        if (!cancelled) animationRef.current = window.requestAnimationFrame(sample);
      })
      .catch(() => {
        setMouthOpen(0);
      });

    return () => {
      cancelled = true;
      if (animationRef.current !== null) {
        window.cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
    };
  }, [audioRef, isSpeaking]);

  useEffect(
    () => () => {
      if (animationRef.current !== null) window.cancelAnimationFrame(animationRef.current);
      sourceRef.current?.disconnect();
      analyserRef.current?.disconnect();
      void contextRef.current?.close();
      contextRef.current = null;
      sourceRef.current = null;
      analyserRef.current = null;
    },
    [],
  );

  return isSpeaking ? mouthOpen : 0;
}
