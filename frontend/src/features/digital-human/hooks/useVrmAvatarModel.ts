import { useEffect, useState } from "react";
import type { VRM } from "@pixiv/three-vrm";

import { disposeVrmAvatar, downloadVrmAvatar, parseVrmAvatar } from "../vrm/vrmAvatarLoader";

interface VrmAvatarModelState {
  error: Error | null;
  isLoading: boolean;
  vrm: VRM | null;
  phase: "loading" | "initializing" | "error";
  progress: number | null;
  retry: () => void;
}

let modelAssetPromise: Promise<ArrayBuffer> | null = null;
let modelController: AbortController | null = null;
let modelConsumers = 0;
let sharedPhase: "loading" | "initializing" = "loading";
let sharedProgress: number | null = null;
const listeners = new Set<() => void>();
let releaseTimer: ReturnType<typeof setTimeout> | null = null;

function acquireModel(): {
  promise: Promise<ArrayBuffer>;
  release: (consumerModel: VRM | null) => void;
} {
  if (releaseTimer) {
    clearTimeout(releaseTimer);
    releaseTimer = null;
  }
  modelConsumers += 1;

  if (!modelAssetPromise) {
    const controller = new AbortController();
    modelController = controller;
    sharedPhase = "loading";
    sharedProgress = null;
    const notify = () => listeners.forEach((listener) => listener());
    const sharedPromise = downloadVrmAvatar(controller.signal, (progress) => {
      if (sharedProgress !== progress) {
        sharedProgress = progress;
        notify();
      }
    }).catch((error: unknown) => {
      if (modelAssetPromise === sharedPromise) {
        modelAssetPromise = null;
        modelController = null;
      }
      throw error;
    });
    modelAssetPromise = sharedPromise;
  }

  let released = false;
  return {
    promise: modelAssetPromise,
    release: (consumerModel) => {
      if (released) return;
      released = true;
      if (consumerModel) disposeVrmAvatar(consumerModel);
      modelConsumers = Math.max(0, modelConsumers - 1);
      if (modelConsumers > 0) return;

      // 延迟到当前 React 提交周期之后释放，避免 StrictMode 重挂载触发重复下载。
      releaseTimer = setTimeout(() => {
        releaseTimer = null;
        if (modelConsumers > 0) return;
        modelController?.abort();
        modelController = null;
        modelAssetPromise = null;
      }, 0);
    },
  };
}

/** 多个 Canvas 共用文件下载、独立解析场景；最后一个使用者卸载后释放缓存和 GPU 资源。 */
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
    let consumerModel: VRM | null = null;
    const model = acquireModel();
    const updateProgress = () => {
      if (mounted)
        setState((current) => ({ ...current, phase: sharedPhase, progress: sharedProgress }));
    };
    listeners.add(updateProgress);
    updateProgress();

    void model.promise
      .then(async (modelAsset) => {
        if (!mounted) return;
        const vrm = await parseVrmAvatar(modelAsset, () => {
          sharedPhase = "initializing";
          listeners.forEach((listener) => listener());
        });
        if (!mounted) {
          disposeVrmAvatar(vrm);
          return;
        }
        consumerModel = vrm;
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
      model.release(consumerModel);
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
