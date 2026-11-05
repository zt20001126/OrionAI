import { Component, Suspense, useEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import { Canvas } from "@react-three/fiber";
import { PerspectiveCamera } from "@react-three/drei";
import type { PerspectiveCamera as ThreePerspectiveCamera } from "three";

import { t } from "../../../i18n/localeStore";
import { useVrmAvatarModel } from "../hooks/useVrmAvatarModel";
import type { VrmLookTarget } from "../hooks/useVrmAvatarAnimation";
import type { DigitalHumanStatus } from "../types";
import { hasVrmMouthExpression } from "../vrm/vrmAvatarCapabilities";
import { VrmAvatarScene } from "./VrmAvatarScene";

interface DigitalHumanAvatar3DProps {
  lookTargetRef?: RefObject<VrmLookTarget | null>;
  mouthOpen: number;
  onLoadError: (error: Error) => void;
  presentation?: "assistant" | "home";
  status: DigitalHumanStatus;
}

const STATUS_LABELS: Record<DigitalHumanStatus, string> = {
  idle: "待机中",
  listening: "正在聆听",
  thinking: "正在思考",
  speaking: "正在说话",
};

/** VRM 展示组件只负责模型呈现和状态扩展，不处理对话或音频业务。 */
export function DigitalHumanAvatar3D({
  lookTargetRef,
  mouthOpen,
  onLoadError,
  presentation = "assistant",
  status,
}: DigitalHumanAvatar3DProps) {
  const { error, isLoading, vrm } = useVrmAvatarModel();
  const reportedErrorRef = useRef<Error | null>(null);
  const cameraRef = useRef<ThreePerspectiveCamera>(null);
  const [isDocumentVisible, setIsDocumentVisible] = useState(
    () => typeof document === "undefined" || document.visibilityState === "visible",
  );

  useEffect(() => {
    const updateVisibility = () => setIsDocumentVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", updateVisibility);
    return () => document.removeEventListener("visibilitychange", updateVisibility);
  }, []);

  useEffect(() => {
    if (error && reportedErrorRef.current !== error) {
      reportedErrorRef.current = error;
      onLoadError(error);
    }
  }, [error, onLoadError]);

  return (
    <div
      aria-busy={presentation === "assistant" ? isLoading : undefined}
      className={`digital-human-avatar${presentation === "home" ? " digital-human-avatar--home" : ""}`}
    >
      {presentation === "assistant" && (
        <div aria-hidden="true" className="digital-human-stage__glow" />
      )}

      {vrm && !error && (
        <AvatarCanvasErrorBoundary onError={onLoadError} presentation={presentation}>
          <div className="digital-human-avatar__canvas">
            <Canvas
              aria-label={t("3D数字人形象")}
              dpr={getRenderPixelRatio()}
              fallback={null}
              frameloop={isDocumentVisible ? "always" : "never"}
              gl={{ alpha: true, antialias: false, powerPreference: "low-power" }}
            >
              <ambientLight intensity={1.2} />
              <hemisphereLight args={["#ffffff", "#e8e7f2", 0.8]} />
              <directionalLight intensity={1.25} position={[2, 2.5, 3]} />
              <directionalLight intensity={0.45} position={[-2, 1.4, 2]} />
              <PerspectiveCamera
                fov={25}
                makeDefault
                position={[0, 1.2, 3.05]}
                near={0.1}
                far={20}
                ref={cameraRef}
              />
              <Suspense fallback={null}>
                <VrmAvatarScene
                  cameraRef={cameraRef}
                  lookTargetRef={lookTargetRef}
                  mouthOpen={mouthOpen}
                  presentation={presentation}
                  status={status}
                  vrm={vrm}
                />
              </Suspense>
            </Canvas>
          </div>
        </AvatarCanvasErrorBoundary>
      )}

      {presentation === "assistant" && isLoading && (
        <div className="digital-human-avatar__model-message" role="status">
          <span aria-hidden="true" className="digital-human-avatar__loader" />
          <span>{t("正在加载数字人模型…")}</span>
        </div>
      )}
      {presentation === "assistant" && error && !isLoading && (
        <div className="digital-human-avatar__model-message" role="status">
          <span>{t("3D数字人暂时无法显示")}</span>
        </div>
      )}
      {presentation === "assistant" && vrm && !hasVrmMouthExpression(vrm) && (
        <p className="digital-human-avatar__compatibility" role="status">
          {t("当前模型不包含嘴型表情，语音口型同步不可用。")}
        </p>
      )}
      {presentation === "assistant" && (
        <span
          aria-live="polite"
          className={`digital-human-avatar__status digital-human-avatar__status--${status}`}
          role="status"
        >
          {t(STATUS_LABELS[status])}
        </span>
      )}
    </div>
  );
}

interface AvatarCanvasErrorBoundaryProps {
  children: ReactNode;
  onError: (error: Error) => void;
  presentation: "assistant" | "home";
}

interface AvatarCanvasErrorBoundaryState {
  error: Error | null;
}

class AvatarCanvasErrorBoundary extends Component<
  AvatarCanvasErrorBoundaryProps,
  AvatarCanvasErrorBoundaryState
> {
  state: AvatarCanvasErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): AvatarCanvasErrorBoundaryState {
    return { error: toAvatarCanvasError(error) };
  }

  componentDidCatch(error: Error) {
    this.props.onError(toAvatarCanvasError(error));
  }

  render() {
    if (this.state.error && this.props.presentation === "home") return null;
    if (this.state.error) {
      return (
        <div className="digital-human-avatar__model-message" role="status">
          <span>{t("当前浏览器无法启用 3D 渲染。")}</span>
        </div>
      );
    }

    return this.props.children;
  }
}

function toAvatarCanvasError(error: Error): Error {
  const message = /webgl|context|graphics/i.test(error.message)
    ? t("当前浏览器无法启用 3D 渲染。")
    : t("3D数字人暂时无法显示。");
  return new Error(message);
}

function getRenderPixelRatio(): number {
  if (typeof window === "undefined") return 1;
  const isMobile = window.matchMedia?.("(max-width: 800px)").matches ?? false;
  const hasLimitedCpu = navigator.hardwareConcurrency > 0 && navigator.hardwareConcurrency <= 4;
  const pixelRatioLimit = hasLimitedCpu ? 1 : isMobile ? 1.15 : 1.5;
  return Math.min(window.devicePixelRatio || 1, pixelRatioLimit);
}
