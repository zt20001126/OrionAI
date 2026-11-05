import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls, PerspectiveCamera } from "@react-three/drei";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js";
import { Box3, Mesh, Vector3 } from "three";
import type { VRM } from "@pixiv/three-vrm";

import "./vrm-preview.css";

const REQUESTED_MODEL_URL = "/models/orion.vrm";

interface LoadedVrm {
  frameBounds: ModelFrameBounds;
  url: string;
  vrm: VRM;
}

interface ModelFrameBounds {
  center: [number, number, number];
  dimensions: [number, number, number];
  minY: number;
}

class ModelHttpError extends Error {
  constructor(
    readonly url: string,
    readonly status: number,
    statusText: string,
  ) {
    super(`HTTP ${status} ${statusText}，请求地址：${url}`);
    this.name = "ModelHttpError";
  }
}

export function VrmModelPreviewPage() {
  const [loadedModel, setLoadedModel] = useState<LoadedVrm | null>(null);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const currentModelRef = useRef<VRM | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    void loadPreviewModel(controller.signal)
      .then((model) => {
        if (controller.signal.aborted) {
          disposePreviewModel(model.vrm);
          return;
        }
        currentModelRef.current = model.vrm;
        setLoadedModel(model);
        setIsLoading(false);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const detail = error instanceof Error ? error : new Error(String(error));
        console.error("[VRM 预览] 模型加载失败，详细错误如下：", detail);
        setLoadError(detail);
        setIsLoading(false);
      });

    return () => {
      controller.abort();
      if (currentModelRef.current) {
        disposePreviewModel(currentModelRef.current);
        currentModelRef.current = null;
      }
    };
  }, []);

  return (
    <main className="vrm-preview">
      <header className="vrm-preview__header">
        <div>
          <h1>VRM 模型预览</h1>
          <p>独立检查 3D 模型加载、正面朝向和上半身构图。</p>
        </div>
        <p className="vrm-preview__controls">拖动旋转 · 滚轮缩放</p>
      </header>

      <section aria-busy={isLoading} className="vrm-preview__stage" aria-label="3D 模型预览区">
        {loadedModel && (
          <Canvas
            aria-label="可旋转和缩放的 VRM 模型"
            dpr={[1, 1.5]}
            fallback={
              <p className="vrm-preview__message" role="alert">
                当前浏览器无法创建 WebGL 渲染器，请检查浏览器的 WebGL 设置。
              </p>
            }
            gl={{ alpha: true, antialias: true, powerPreference: "low-power" }}
          >
            <ambientLight intensity={1.15} />
            <hemisphereLight args={["#ffffff", "#e8e7f2", 0.8]} />
            <directionalLight intensity={1.25} position={[2, 2.5, 3]} />
            <directionalLight intensity={0.55} position={[-2, 1.4, 2]} />
            <Suspense fallback={null}>
              <VrmPreviewScene bounds={loadedModel.frameBounds} vrm={loadedModel.vrm} />
            </Suspense>
          </Canvas>
        )}

        {isLoading && (
          <p className="vrm-preview__message" role="status">
            正在加载 VRM 模型…
          </p>
        )}
        {loadError && (
          <div className="vrm-preview__error" role="alert">
            <strong>模型加载失败</strong>
            <pre>{loadError.message}</pre>
          </div>
        )}
      </section>

      {loadedModel && (
        <footer className="vrm-preview__details" aria-live="polite">
          <span>当前模型：{loadedModel.url}</span>
        </footer>
      )}
    </main>
  );
}

function VrmPreviewScene({ bounds, vrm }: { bounds: ModelFrameBounds; vrm: VRM }) {
  const size = useThree((state) => state.size);
  const frame = useMemo(() => {
    const [width, height] = bounds.dimensions;
    const [centerX, , centerZ] = bounds.center;
    const verticalFov = (28 * Math.PI) / 180;
    const halfFovTangent = Math.tan(verticalFov / 2);
    const aspect = Math.max(size.width / Math.max(size.height, 1), 0.1);
    const upperBodyHeight = height * 0.7;
    const distanceByHeight = upperBodyHeight / (2 * halfFovTangent);
    const distanceByWidth = width / (2 * halfFovTangent * aspect);
    const distance = Math.max(distanceByHeight, distanceByWidth) * 1.08;
    const target: [number, number, number] = [centerX, bounds.minY + height * 0.72, centerZ];

    return {
      maxDistance: height * 4,
      minDistance: Math.max(height * 0.35, 0.25),
      position: [target[0], target[1], target[2] + distance] as [number, number, number],
      target,
    };
  }, [bounds, size.height, size.width]);

  return (
    <>
      <primitive object={vrm.scene} />
      <PerspectiveCamera
        makeDefault
        fov={28}
        far={100}
        near={0.01}
        position={frame.position}
      />
      <OrbitControls
        enableDamping={false}
        enablePan={false}
        maxDistance={frame.maxDistance}
        minDistance={frame.minDistance}
        target={frame.target}
      />
    </>
  );
}

async function loadPreviewModel(signal: AbortSignal): Promise<LoadedVrm> {
  const vrm = await loadVrmAtUrl(REQUESTED_MODEL_URL, signal);
  return {
    frameBounds: getModelFrameBounds(vrm),
    url: REQUESTED_MODEL_URL,
    vrm,
  };
}

async function loadVrmAtUrl(url: string, signal: AbortSignal): Promise<VRM> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new ModelHttpError(url, response.status, response.statusText);
  if (response.headers.get("content-type")?.includes("text/html")) {
    throw new ModelHttpError(url, 404, "该地址返回了 HTML 页面，没有找到 VRM 模型文件");
  }

  const modelData = await response.arrayBuffer();
  signal.throwIfAborted();

  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  const gltf = await parseModel(loader, modelData);
  const vrm = gltf.userData.vrm as VRM | undefined;
  if (!vrm) {
    VRMUtils.deepDispose(gltf.scene);
    throw new Error(`文件 ${url} 不包含有效的 VRM 数据。`);
  }

  try {
    signal.throwIfAborted();
    if (vrm.meta.metaVersion === "0") VRMUtils.rotateVRM0(vrm);
    VRMUtils.removeUnnecessaryVertices(gltf.scene);
    VRMUtils.combineSkeletons(gltf.scene);
    VRMUtils.combineMorphs(vrm);
    vrm.scene.traverse((node) => {
      if (node instanceof Mesh) node.frustumCulled = false;
    });
    vrm.scene.updateMatrixWorld(true);
    return vrm;
  } catch (error) {
    disposePreviewModel(vrm);
    throw error;
  }
}

function parseModel(loader: GLTFLoader, data: ArrayBuffer): Promise<GLTF> {
  return new Promise((resolve, reject) => {
    loader.parse(data, "", resolve, reject);
  });
}

function disposePreviewModel(vrm: VRM): void {
  VRMUtils.deepDispose(vrm.scene);
}

function getModelFrameBounds(vrm: VRM): ModelFrameBounds {
  const bounds = new Box3().setFromObject(vrm.scene);
  const center = bounds.getCenter(new Vector3());
  const dimensions = bounds.getSize(new Vector3());

  return {
    center: [center.x, center.y, center.z],
    dimensions: [dimensions.x, dimensions.y, dimensions.z],
    minY: bounds.min.y,
  };
}
