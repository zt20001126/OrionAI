import { renderHook, waitFor } from "@testing-library/react";
import { Object3D } from "three";
import type { VRM } from "@pixiv/three-vrm";
import { afterEach, describe, expect, it, vi } from "vitest";

const loaderMocks = vi.hoisted(() => ({
  download: vi.fn(),
  parse: vi.fn(),
  dispose: vi.fn(),
}));

vi.mock("../vrm/vrmAvatarLoader", () => ({
  downloadVrmAvatar: loaderMocks.download,
  parseVrmAvatar: loaderMocks.parse,
  disposeVrmAvatar: loaderMocks.dispose,
}));

import { useVrmAvatarModel } from "./useVrmAvatarModel";

afterEach(() => {
  vi.clearAllMocks();
});

describe("useVrmAvatarModel", () => {
  it("shares one model download while creating and disposing independent VRM scenes", async () => {
    const modelAsset = new ArrayBuffer(8);
    const firstVrm = { scene: new Object3D() } as VRM;
    const secondVrm = { scene: new Object3D() } as VRM;
    loaderMocks.download.mockResolvedValue(modelAsset);
    loaderMocks.parse.mockResolvedValueOnce(firstVrm).mockResolvedValueOnce(secondVrm);

    const firstConsumer = renderHook(() => useVrmAvatarModel());
    const secondConsumer = renderHook(() => useVrmAvatarModel());

    await waitFor(() => {
      expect(firstConsumer.result.current.vrm).toBe(firstVrm);
      expect(secondConsumer.result.current.vrm).toBe(secondVrm);
    });

    expect(loaderMocks.download).toHaveBeenCalledOnce();
    expect(loaderMocks.parse).toHaveBeenCalledTimes(2);
    expect(loaderMocks.parse.mock.calls[0]?.[0]).toBe(modelAsset);
    expect(loaderMocks.parse.mock.calls[1]?.[0]).toBe(modelAsset);

    firstConsumer.unmount();
    expect(loaderMocks.dispose).toHaveBeenCalledWith(firstVrm);
    secondConsumer.unmount();
    expect(loaderMocks.dispose).toHaveBeenCalledWith(secondVrm);
  });
});
