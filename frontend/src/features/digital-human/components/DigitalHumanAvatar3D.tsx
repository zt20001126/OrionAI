import { Component, Suspense, useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { Canvas } from "@react-three/fiber";
import { PerspectiveCamera } from "@react-three/drei";
import type { PerspectiveCamera as ThreePerspectiveCamera } from "three";

import { t } from "../../../i18n/localeStore";
import { useVrmAvatarModel } from "../hooks/useVrmAvatarModel";
import type { DigitalHumanStatus } from "../types";
import { hasVrmMouthExpression } from "../vrm/vrmAvatarCapabilities";
import { VrmAvatarScene } from "./VrmAvatarScene";

interface DigitalHumanAvatar3DProps {
  mouthOpen: number;
  onLoadError: (error: Error) => void;
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
  mouthOpen,
  onLoadError,
  status,
}: DigitalHumanAvatar3DProps) {
  const { error, isLoading, vrm } = useVrmAvatarModel();
  const reportedErrorRef = useRef<Error | null>(null);
  const cameraRef = useRef<ThreePerspectiveCamera>(null);

  useEffect(() => {
    if (error && reportedErrorRef.current !== error) {
      reportedErrorRef.current = error;
      onLoadError(error);
    }
  }, [error, onLoadError]);

  return (
    <div aria-busy={isLoading} className="digital-human-avatar">
      <div aria-hidden="true" className="digital-human-stage__glow" />

      {vrm && !error && (
        <AvatarCanvasErrorBoundary onError={onLoadError}>
          <div className="digital-human-avatar__canvas">
            <Canvas
              aria-label={t("3D数字人形象")}
              dpr={getRenderPixelRatio()}
              fallback={null}
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
                  mouthOpen={mouthOpen}
                  status={status}
                  vrm={vrm}
                />
              </Suspense>
            </Canvas>
          </div>
        </AvatarCanvasErrorBoundary>
      )}

      {isLoading && (
        <div className="digital-human-avatar__model-message" role="status">
          <span aria-hidden="true" className="digital-human-avatar__loader" />
          <span>{t("正在加载数字人模型…")}</span>
        </div>
      )}
      {error && !isLoading && (
        <div className="digital-human-avatar__model-message" role="status">
          <span>{t("3D数字人暂时无法显示")}</span>
        </div>
      )}
      {vrm && !hasVrmMouthExpression(vrm) && (
        <p className="digital-human-avatar__compatibility" role="status">
          {t("当前模型不包含嘴型表情，语音口型同步不可用。")}
        </p>
      )}
      <span
        aria-live="polite"
        className={`digital-human-avatar__status digital-human-avatar__status--${status}`}
        role="status"
      >
        {t(STATUS_LABELS[status])}
      </span>
    </div>
  );
}

interface AvatarCanvasErrorBoundaryProps {
  children: ReactNode;
  onError: (error: Error) => void;
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
  return Math.min(window.devicePixelRatio || 1, isMobile ? 1.25 : 1.6);
}
