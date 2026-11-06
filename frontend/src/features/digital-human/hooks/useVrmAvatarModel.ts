import { useEffect, useState } from "react";
import type { VRM } from "@pixiv/three-vrm";

import { disposeVrmAvatar, loadVrmAvatar } from "../vrm/vrmAvatarLoader";

interface VrmAvatarModelState {
  error: Error | null;
  isLoading: boolean;
  vrm: VRM | null;
  phase: "loading" | "initializing" | "error";
  progress: number | null;
  retry: () => void;
}

let modelPromise: Promise<VRM> | null = null;
let loadedModel: VRM | null = null;
let modelController: AbortController | null = null;
let modelConsumers = 0;
let sharedPhase: "loading" | "initializing" = "loading";
let sharedProgress: number | null = null;
const listeners = new Set<() => void>();
let releaseTimer: ReturnType<typeof setTimeout> | null = null;

function acquireModel(): { promise: Promise<VRM>; release: () => void } {
  if (releaseTimer) {
    clearTimeout(releaseTimer);
    releaseTimer = null;
  }
  modelConsumers += 1;

  if (!modelPromise) {
    const controller = new AbortController();
    modelController = controller;
    sharedPhase = "loading";
    sharedProgress = null;
    const notify = () => listeners.forEach((listener) => listener());
    const sharedPromise = loadVrmAvatar(
      controller.signal,
      (progress) => {
        if (sharedProgress !== progress) {
          sharedProgress = progress;
          notify();
        }
      },
      () => {
        sharedPhase = "initializing";
        notify();
      },
    )
      .then((vrm) => {
        if (modelPromise === sharedPromise) loadedModel = vrm;
        return vrm;
      })
      .catch((error: unknown) => {
        if (modelPromise === sharedPromise) {
          modelPromise = null;
          modelController = null;
        }
        throw error;
      });
    modelPromise = sharedPromise;
  }

  let released = false;
  return {
    promise: modelPromise,
    release: () => {
      if (released) return;
      released = true;
      modelConsumers = Math.max(0, modelConsumers - 1);
      if (modelConsumers > 0) return;

      // 延迟到当前 React 提交周期之后释放，避免 StrictMode 重挂载触发重复下载。
      releaseTimer = setTimeout(() => {
        releaseTimer = null;
        if (modelConsumers > 0) return;
        modelController?.abort();
        modelController = null;
        modelPromise = null;
        if (loadedModel) disposeVrmAvatar(loadedModel);
        loadedModel = null;
      }, 0);
    },
  };
}

/** 多个渲染周期共享一次下载，最后一个使用者卸载后释放 GPU 资源。 */
export function useVrmAvatarModel(): VrmAvatarModelState {
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<Omit<VrmAvatarModelState, "retry">>({
    error: null,
    isLoading: true,
    vrm: null,
    phase: "loading",
    progress: null,
  });

  useEffect(() => {
    let mounted = true;
    const model = acquireModel();
    const updateProgress = () => {
      if (mounted)
        setState((current) => ({ ...current, phase: sharedPhase, progress: sharedProgress }));
    };
    listeners.add(updateProgress);
    updateProgress();

    void model.promise
      .then((vrm) => {
        if (mounted)
          setState({
            error: null,
            isLoading: false,
            vrm,
            phase: "initializing",
            progress: sharedProgress,
          });
      })
      .catch((loadError: unknown) => {
        if (!mounted) return;
        setState({
          error: loadError instanceof Error ? loadError : new Error("数字人模型暂时无法加载。"),
          isLoading: false,
          vrm: null,
          phase: "error",
          progress: null,
        });
      });

    return () => {
      mounted = false;
      listeners.delete(updateProgress);
      model.release();
    };
  }, [version]);

  return {
    ...state,
    retry: () => {
      setState({ error: null, isLoading: true, vrm: null, phase: "loading", progress: null });
      setVersion((value) => value + 1);
    },
  };
}
