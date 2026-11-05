import { lazy, Suspense, useEffect, useRef, useState } from "react";

import type { VrmLookTarget } from "../digital-human/hooks/useVrmAvatarAnimation";

import "./home-digital-human.css";

const LazyDigitalHumanAvatar3D = lazy(() =>
  import("../digital-human/components/DigitalHumanAvatar3D").then((module) => ({
    default: module.DigitalHumanAvatar3D,
  })),
);

const ignoreModelError = () => undefined;

/** 首页仅展示 VRM；首屏绘制后的空闲时段才加载模型与渲染模块。 */
export function HomeDigitalHuman() {
  const [isWideViewport, setIsWideViewport] = useState(() => window.innerWidth > 980);
  const [isReady, setIsReady] = useState(false);
  const lookTargetRef = useRef<VrmLookTarget | null>(null);

  useEffect(() => {
    const updateViewport = () => setIsWideViewport(window.innerWidth > 980);
    window.addEventListener("resize", updateViewport);

    return () => window.removeEventListener("resize", updateViewport);
  }, []);

  useEffect(() => {
    if (!isWideViewport) return;

    let idleHandle: number | null = null;
    let timeoutHandle: number | null = null;

    if (window.requestIdleCallback) {
      idleHandle = window.requestIdleCallback(() => setIsReady(true), { timeout: 1400 });
    } else {
      timeoutHandle = window.setTimeout(() => setIsReady(true), 500);
    }

    return () => {
      if (idleHandle !== null) window.cancelIdleCallback(idleHandle);
      if (timeoutHandle !== null) window.clearTimeout(timeoutHandle);
    };
  }, [isWideViewport]);

  useEffect(() => {
    const updateLookTarget = (event: PointerEvent) => {
      lookTargetRef.current = {
        x: (event.clientX / window.innerWidth) * 2 - 1,
        y: 1 - (event.clientY / window.innerHeight) * 2,
        updatedAt: performance.now(),
      };
    };

    window.addEventListener("pointermove", updateLookTarget, { passive: true });
    return () => window.removeEventListener("pointermove", updateLookTarget);
  }, []);

  return (
    <div aria-hidden="true" className="auth-digital-human">
      {isWideViewport && isReady && (
        <Suspense fallback={null}>
          <LazyDigitalHumanAvatar3D
            lookTargetRef={lookTargetRef}
            mouthOpen={0}
            onLoadError={ignoreModelError}
            presentation="home"
            status="idle"
          />
        </Suspense>
      )}
    </div>
  );
}
