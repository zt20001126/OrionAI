/** 管理记忆训练五阶段交互、刷新恢复、倒计时和题目轮询。 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  createTrainingSession,
  getTrainingPreparation,
  getTrainingQuestions,
  getTrainingResult,
  getTrainingStatus,
  startTrainingObservation,
  submitTrainingAnswers,
  type Preparation,
  type PublicQuestion,
  type TrainingResult,
  type TrainingStatus,
} from "../api/memoryTrainingApi";

const SESSION_STORAGE_KEY = "orionai.memory-training.session";
const ANSWER_STORAGE_PREFIX = "orionai.memory-training.answers:";
const COUNTDOWN_REFRESH_MS = 100;
const STATUS_POLL_MS = 1000;

async function loadImageAndStartObservation(sessionId: string, imageUrl: string) {
  const image = new Image();
  image.src = imageUrl;
  await image.decode();
  return startTrainingObservation(sessionId);
}

export type MemoryTrainingPhase =
  | "loading"
  | "prepare"
  | "image_loading"
  | "observing"
  | "waiting_questions"
  | "answering"
  | "completed"
  | "generation_failed"
  | "error";

export interface MemoryTrainingSession {
  phase: MemoryTrainingPhase;
  preparation: Preparation | null;
  sessionId: string | null;
  imageUrl: string | null;
  remainingMs: number;
  questions: PublicQuestion[];
  answers: Record<string, string>;
  currentQuestionIndex: number;
  result: TrainingResult | null;
  error: string | null;
  busy: boolean;
}

const INITIAL_STATE: MemoryTrainingSession = {
  phase: "loading",
  preparation: null,
  sessionId: null,
  imageUrl: null,
  remainingMs: 0,
  questions: [],
  answers: {},
  currentQuestionIndex: 0,
  result: null,
  error: null,
  busy: false,
};

/** 将浏览器阶段与 Redis 权威会话状态同步。 */
export function useMemoryTrainingSession() {
  const [session, setSession] = useState<MemoryTrainingSession>(INITIAL_STATE);
  const deadlineRef = useRef<number | null>(null);

  const loadQuestions = useCallback(async (sessionId: string) => {
    const questions = await getTrainingQuestions(sessionId);
    let answers: Record<string, string> = {};
    try {
      const storedAnswers = sessionStorage.getItem(`${ANSWER_STORAGE_PREFIX}${sessionId}`);
      answers = storedAnswers ? (JSON.parse(storedAnswers) as Record<string, string>) : {};
    } catch {
      sessionStorage.removeItem(`${ANSWER_STORAGE_PREFIX}${sessionId}`);
    }
    setSession((current) => ({
      ...current,
      phase: "answering",
      questions,
      answers,
      currentQuestionIndex: Math.min(current.currentQuestionIndex, questions.length - 1),
      imageUrl: null,
      remainingMs: 0,
      error: null,
    }));
  }, []);

  const applyStatus = useCallback(
    async (status: TrainingStatus) => {
      if (status.state === "image_loading") {
        setSession((current) => ({
          ...current,
          phase: "image_loading",
          imageUrl: status.image_url,
          remainingMs: 0,
        }));
        return;
      }
      if (status.state === "observing") {
        deadlineRef.current = performance.now() + status.remaining_ms;
        setSession((current) => ({
          ...current,
          phase: "observing",
          imageUrl: status.image_url,
          remainingMs: status.remaining_ms,
        }));
        return;
      }
      if (status.state === "waiting_questions") {
        deadlineRef.current = null;
        setSession((current) => ({
          ...current,
          phase: "waiting_questions",
          imageUrl: null,
          remainingMs: 0,
        }));
        return;
      }
      if (status.state === "answering") {
        deadlineRef.current = null;
        await loadQuestions(status.session_id);
        return;
      }
      if (status.state === "completed") {
        deadlineRef.current = null;
        const result = await getTrainingResult(status.session_id);
        setSession((current) => ({ ...current, phase: "completed", imageUrl: null, result }));
        return;
      }
      if (status.state === "generation_failed") {
        deadlineRef.current = null;
        setSession((current) => ({
          ...current,
          phase: "generation_failed",
          imageUrl: null,
          remainingMs: 0,
          error: "题目准备失败，请重新开始训练。",
        }));
      }
    },
    [loadQuestions],
  );

  const restore = useCallback(async () => {
    setSession((current) => ({ ...current, phase: "loading", error: null }));
    try {
      const preparation = await getTrainingPreparation();
      const sessionId = sessionStorage.getItem(SESSION_STORAGE_KEY);
      if (!sessionId) {
        setSession({ ...INITIAL_STATE, phase: "prepare", preparation });
        return;
      }
      setSession((current) => ({ ...current, preparation, sessionId }));
      try {
        const status = await getTrainingStatus(sessionId);
        if (status.state === "image_loading" && status.image_url) {
          try {
            const started = await loadImageAndStartObservation(sessionId, status.image_url);
            deadlineRef.current = performance.now() + started.remaining_ms;
            setSession((current) => ({
              ...current,
              phase: "observing",
              preparation,
              sessionId,
              imageUrl: status.image_url,
              remainingMs: started.remaining_ms,
              error: null,
            }));
          } catch {
            setSession((current) => ({
              ...current,
              phase: "image_loading",
              preparation,
              sessionId,
              imageUrl: status.image_url,
              error: "图片加载失败，请检查网络后重试。",
            }));
          }
        } else {
          await applyStatus(status);
        }
      } catch (error) {
        sessionStorage.removeItem(SESSION_STORAGE_KEY);
        setSession({
          ...INITIAL_STATE,
          phase: "prepare",
          preparation,
          error: error instanceof Error ? "上次训练已过期，请重新开始。" : null,
        });
      }
    } catch (error) {
      setSession((current) => ({
        ...current,
        phase: "error",
        error: error instanceof Error ? error.message : "训练信息加载失败，请稍后重试。",
      }));
    }
  }, [applyStatus]);

  useEffect(() => {
    void restore();
  }, [restore]);

  const beginObservation = useCallback(
    async (sessionId: string, imageUrl: string) => {
      try {
        const started = await loadImageAndStartObservation(sessionId, imageUrl);
        deadlineRef.current = performance.now() + started.remaining_ms;
        setSession((current) => ({
          ...current,
          phase: "observing",
          sessionId,
          imageUrl,
          remainingMs: started.remaining_ms,
          busy: false,
          error: null,
        }));
      } catch {
        setSession((current) => ({
          ...current,
          phase: "image_loading",
          imageUrl,
          busy: false,
          error: "图片加载失败，请检查网络后重试。",
        }));
      }
    },
    [],
  );

  const startTraining = useCallback(async () => {
    setSession((current) => ({ ...current, busy: true, error: null }));
    try {
      const created = await createTrainingSession();
      sessionStorage.setItem(SESSION_STORAGE_KEY, created.session_id);
      setSession((current) => ({
        ...current,
        phase: "image_loading",
        sessionId: created.session_id,
        imageUrl: created.image_url,
      }));
      await beginObservation(created.session_id, created.image_url);
    } catch (error) {
      setSession((current) => ({
        ...current,
        phase: "prepare",
        busy: false,
        error: error instanceof Error ? error.message : "无法开始训练，请稍后重试。",
      }));
    }
  }, [beginObservation]);

  const retryImageLoading = useCallback(async () => {
    if (!session.sessionId || !session.imageUrl) {
      await startTraining();
      return;
    }
    setSession((current) => ({ ...current, busy: true, error: null }));
    await beginObservation(session.sessionId, session.imageUrl);
  }, [beginObservation, session.imageUrl, session.sessionId, startTraining]);

  const chooseAnswer = useCallback((questionId: string, optionId: string) => {
    setSession((current) => {
      const answers = { ...current.answers, [questionId]: optionId };
      if (current.sessionId) {
        sessionStorage.setItem(
          `${ANSWER_STORAGE_PREFIX}${current.sessionId}`,
          JSON.stringify(answers),
        );
      }
      return { ...current, answers };
    });
  }, []);

  const submitAnswers = useCallback(async () => {
    if (!session.sessionId || session.questions.length !== 5) return;
    setSession((current) => ({ ...current, busy: true, error: null }));
    try {
      await submitTrainingAnswers(session.sessionId, session.answers);
      sessionStorage.removeItem(`${ANSWER_STORAGE_PREFIX}${session.sessionId}`);
      const result = await getTrainingResult(session.sessionId);
      setSession((current) => ({ ...current, phase: "completed", result, busy: false }));
    } catch (error) {
      setSession((current) => ({
        ...current,
        busy: false,
        error: error instanceof Error ? error.message : "答案提交失败，请重试。",
      }));
    }
  }, [session.answers, session.questions.length, session.sessionId]);

  const startAgain = useCallback(async () => {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
    if (session.sessionId) sessionStorage.removeItem(`${ANSWER_STORAGE_PREFIX}${session.sessionId}`);
    deadlineRef.current = null;
    setSession((current) => ({
      ...current,
      phase: "prepare",
      sessionId: null,
      imageUrl: null,
      questions: [],
      answers: {},
      result: null,
      error: null,
    }));
  }, [session.sessionId]);

  useEffect(() => {
    if (session.phase !== "observing") return;
    const timer = window.setInterval(() => {
      const remainingMs = Math.max(0, (deadlineRef.current ?? performance.now()) - performance.now());
      setSession((current) => ({ ...current, remainingMs }));
      if (remainingMs === 0) {
        deadlineRef.current = null;
        setSession((current) => ({ ...current, phase: "waiting_questions", imageUrl: null }));
      }
    }, COUNTDOWN_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [session.phase]);

  useEffect(() => {
    if (!session.sessionId || !["observing", "waiting_questions"].includes(session.phase)) return;
    let active = true;
    const poll = async () => {
      try {
        const status = await getTrainingStatus(session.sessionId as string);
        if (active) await applyStatus(status);
      } catch (error) {
        if (active && error instanceof Error && error.message.includes("过期")) {
          sessionStorage.removeItem(SESSION_STORAGE_KEY);
          setSession((current) => ({
            ...current,
            phase: "error",
            imageUrl: null,
            error: "训练已过期，请重新开始。",
          }));
        }
      }
    };
    const timer = window.setInterval(() => void poll(), STATUS_POLL_MS);
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      if (deadlineRef.current !== null && performance.now() >= deadlineRef.current) {
        deadlineRef.current = null;
        setSession((current) => ({ ...current, phase: "waiting_questions", imageUrl: null }));
      }
      void poll();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [applyStatus, session.phase, session.sessionId]);

  const moveToQuestion = useCallback((index: number) => {
    setSession((current) => ({
      ...current,
      currentQuestionIndex: Math.max(0, Math.min(index, current.questions.length - 1)),
    }));
  }, []);

  return {
    session,
    restore,
    startTraining,
    retryImageLoading,
    startAgain,
    chooseAnswer,
    submitAnswers,
    moveToQuestion,
  };
}
