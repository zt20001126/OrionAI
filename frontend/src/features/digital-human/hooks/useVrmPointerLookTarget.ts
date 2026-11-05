import { useEffect, useRef } from "react";
import type { RefObject } from "react";

export interface VrmLookTarget {
  x: number;
  y: number;
  updatedAt: number;
}

/** Track pointer position once for the shared VRM head-follow animation. */
export function useVrmPointerLookTarget(): RefObject<VrmLookTarget | null> {
  const lookTargetRef = useRef<VrmLookTarget | null>(null);

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

  return lookTargetRef;
}
