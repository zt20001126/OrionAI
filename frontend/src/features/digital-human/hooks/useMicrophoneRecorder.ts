import { useCallback, useEffect, useRef, useState } from "react";

import { t } from "../../../i18n/localeStore";
import { recognizeSpeech } from "../digitalHumanApi";

const MAX_RECORDING_MS = 30_000;
const SUPPORTED_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/ogg;codecs=opus",
  "audio/mp4",
  "audio/mpeg",
  "audio/wav",
];

export type RecorderStatus = "idle" | "starting" | "listening" | "transcribing";

interface UseMicrophoneRecorderOptions {
  onTranscribed: (text: string) => void;
}

/** 管理一次性录音、轨道释放和 ASR 转写，不把音频写入浏览器持久存储。 */
export function useMicrophoneRecorder({ onTranscribed }: UseMicrophoneRecorderOptions) {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<number | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const startLockRef = useRef(false);
  const mountedRef = useRef(true);
  const transcribedRef = useRef(onTranscribed);

  useEffect(() => {
    transcribedRef.current = onTranscribed;
  }, [onTranscribed]);

  const releaseMicrophone = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  const stopRecording = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") {
      recorder.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
    }
  }, []);

  const startRecording = useCallback(async () => {
    if (startLockRef.current || recorderRef.current) return;
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError(t("当前浏览器不支持麦克风录音，请使用文字输入。"));
      return;
    }

    startLockRef.current = true;
    setStatus("starting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const mimeType = SUPPORTED_MIME_TYPES.find((candidate) =>
        MediaRecorder.isTypeSupported(candidate),
      );
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        if (mountedRef.current) setError(t("录音失败，请检查麦克风后重试。"));
        releaseMicrophone();
        if (mountedRef.current) setStatus("idle");
      };
      recorder.onstop = () => {
        const recording = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        chunksRef.current = [];
        releaseMicrophone();
        if (!mountedRef.current) return;
        if (recording.size === 0) {
          if (mountedRef.current) {
            setError(t("没有录到语音，请重试。"));
            setStatus("idle");
          }
          return;
        }
        const controller = new AbortController();
        requestRef.current = controller;
        if (mountedRef.current) setStatus("transcribing");
        void recognizeSpeech(recording, controller.signal)
          .then(({ text }) => {
            if (mountedRef.current) {
              transcribedRef.current(text);
              setStatus("idle");
            }
          })
          .catch((requestError: unknown) => {
            if (!controller.signal.aborted && mountedRef.current) {
              setError(
                requestError instanceof Error ? requestError.message : t("语音识别失败，请重试。"),
              );
              setStatus("idle");
            }
          })
          .finally(() => {
            if (requestRef.current === controller) requestRef.current = null;
          });
      };
      recorder.start();
      setStatus("listening");
      timerRef.current = window.setTimeout(stopRecording, MAX_RECORDING_MS);
    } catch {
      releaseMicrophone();
      setStatus("idle");
      setError(t("无法访问麦克风，请检查浏览器权限后重试。"));
    } finally {
      startLockRef.current = false;
    }
  }, [releaseMicrophone, stopRecording]);

  const clearError = useCallback(() => setError(null), []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestRef.current?.abort();
      stopRecording();
      releaseMicrophone();
    };
  }, [releaseMicrophone, stopRecording]);

  return { status, error, clearError, startRecording, stopRecording };
}
