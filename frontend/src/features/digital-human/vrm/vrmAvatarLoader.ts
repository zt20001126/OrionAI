import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js";
import { Mesh } from "three";
import type { VRM } from "@pixiv/three-vrm";

export const VRM_MODEL_URL = "/models/orion.vrm";

/** 下载 VRM 文件字节；调用方可在多个独立场景解析同一份缓存数据。 */
export async function downloadVrmAvatar(
  signal: AbortSignal,
  onProgress: (progress: number | null) => void,
): Promise<ArrayBuffer> {
  const response = await fetch(VRM_MODEL_URL, { signal });
  if (!response.ok) throw new Error("数字人模型暂时无法加载。");

  // 压缩传输的 Content-Length 不代表浏览器解压后的字节数，不能用于进度计算。
  const total = response.headers.get("content-encoding")
    ? 0
    : Number(response.headers.get("content-length"));
  const reader = response.body?.getReader();
  let modelData: ArrayBuffer;
  if (reader) {
    const chunks: Uint8Array[] = [];
    let loaded = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      loaded += value.byteLength;
      onProgress(total > 0 ? Math.min(100, Math.floor((loaded / total) * 100)) : null);
    }
    const bytes = new Uint8Array(loaded);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    modelData = bytes.buffer;
  } else {
    modelData = await response.arrayBuffer();
  }
  signal.throwIfAborted();

  return modelData;
}

/** 从共享文件数据创建独立 VRM 场景，供不同 Canvas 安全呈现。 */
export async function parseVrmAvatar(
  modelData: ArrayBuffer,
  onInitializing: () => void,
): Promise<VRM> {
  onInitializing();

  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  const gltf = await parseModel(loader, modelData.slice(0));

  const vrm = gltf.userData.vrm as VRM | undefined;
  if (!vrm) {
    VRMUtils.deepDispose(gltf.scene);
    throw new Error("模型文件不包含有效的 VRM 数字人数据。");
  }

  try {
    // VRM 0.0 的正面方向与 Three.js 场景约定相反；VRM 1.0 已由加载器按规范处理。
    if (vrm.meta.metaVersion === "0") VRMUtils.rotateVRM0(vrm);
    VRMUtils.removeUnnecessaryVertices(gltf.scene);
    VRMUtils.combineSkeletons(gltf.scene);
    VRMUtils.combineMorphs(vrm);
    vrm.scene.traverse((node) => {
      if (node instanceof Mesh) node.frustumCulled = false;
    });

    return vrm;
  } catch (error) {
    VRMUtils.deepDispose(vrm.scene);
    throw error;
  }
}

export function disposeVrmAvatar(vrm: VRM): void {
  VRMUtils.deepDispose(vrm.scene);
}

function parseModel(loader: GLTFLoader, data: ArrayBuffer): Promise<GLTF> {
  return new Promise((resolve, reject) => {
    loader.parse(data, "", resolve, reject);
  });
}
