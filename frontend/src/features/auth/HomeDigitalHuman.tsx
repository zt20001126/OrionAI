import { lazy, Suspense, useEffect, useState } from "react";

import { useVrmPointerLookTarget } from "../digital-human/hooks/useVrmPointerLookTarget";

import "./home-digital-human.css";

const LazyDigitalHumanAvatar3D = lazy(() =>
  import("../digital-human/components/DigitalHumanAvatar3D").then((module) => ({
    default: module.DigitalHumanAvatar3D,
  })),
);

const ignoreModelError = () => undefined;

/** 在认证首页展示可交互的数字人；首屏绘制后的空闲时段加载模型与渲染模块。 */
export function HomeDigitalHuman() {
  const [isWideViewport, setIsWideViewport] = useState(() => window.innerWidth > 980);
  const [isReady, setIsReady] = useState(false);
  const lookTargetRef = useVrmPointerLookTarget();

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

  return (
    <div aria-hidden="true" className="auth-digital-human">
      {isWideViewport && isReady && (
        <Suspense fallback={null}>
          <LazyDigitalHumanAvatar3D
            enableClickInteraction
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
