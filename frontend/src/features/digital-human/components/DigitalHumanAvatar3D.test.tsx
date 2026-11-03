import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { VRM } from "@pixiv/three-vrm";
import type { ReactNode } from "react";

import { useVrmAvatarModel } from "../hooks/useVrmAvatarModel";
import { DigitalHumanAvatar3D } from "./DigitalHumanAvatar3D";

const canvasMockState = vi.hoisted(() => ({ throws: false }));

vi.mock("@react-three/fiber", () => ({
  Canvas: ({ fallback }: { fallback?: ReactNode }) => {
    if (canvasMockState.throws) throw new Error("Error creating WebGL context");
    return <div data-testid="avatar-canvas">{fallback}</div>;
  },
}));

vi.mock("@react-three/drei", () => ({
  PerspectiveCamera: () => null,
}));

vi.mock("../hooks/useVrmAvatarModel", () => ({
  useVrmAvatarModel: vi.fn(),
}));

afterEach(() => cleanup());

beforeEach(() => {
  canvasMockState.throws = false;
  vi.mocked(useVrmAvatarModel).mockReturnValue({ error: null, isLoading: false, vrm: null });
});

describe("DigitalHumanAvatar3D", () => {
  it.each([
    ["idle", "待机中"],
    ["listening", "正在聆听"],
    ["thinking", "正在思考"],
    ["speaking", "正在说话"],
  ] as const)("announces the %s state", (status, label) => {
    render(<DigitalHumanAvatar3D mouthOpen={0} onLoadError={vi.fn()} status={status} />);

    expect(screen.getByRole("status")).toHaveTextContent(label);
  });

  it("shows a short loading message while the VRM model loads", () => {
    vi.mocked(useVrmAvatarModel).mockReturnValue({ error: null, isLoading: true, vrm: null });

    render(<DigitalHumanAvatar3D mouthOpen={0} onLoadError={vi.fn()} status="idle" />);

    expect(screen.getByText("正在加载数字人模型…")).toBeInTheDocument();
    expect(screen.queryByTestId("avatar-canvas")).not.toBeInTheDocument();
  });

  it("renders the canvas when a VRM model is available", () => {
    const vrm = {
      meta: { author: "JustAPal", metaVersion: "0", title: "Mal 14.16 Optimized" },
    } as unknown as VRM;
    vi.mocked(useVrmAvatarModel).mockReturnValue({ error: null, isLoading: false, vrm });

    const onLoadError = vi.fn();
    render(<DigitalHumanAvatar3D mouthOpen={0.6} onLoadError={onLoadError} status="speaking" />);

    expect(screen.getByTestId("avatar-canvas")).toBeInTheDocument();
    expect(screen.getByText("Mal 14.16 Optimized · JustAPal")).toBeInTheDocument();
    expect(onLoadError).not.toHaveBeenCalled();
    expect(screen.getByText("当前模型不包含嘴型表情，语音口型同步不可用。")).toBeInTheDocument();
  });

  it("reports model load failures through the provided error handler", () => {
    const error = new Error("model fetch failed");
    const onLoadError = vi.fn();
    vi.mocked(useVrmAvatarModel).mockReturnValue({ error, isLoading: false, vrm: null });

    render(<DigitalHumanAvatar3D mouthOpen={0} onLoadError={onLoadError} status="idle" />);

    expect(screen.getByText("3D数字人暂时无法显示")).toBeInTheDocument();
    expect(onLoadError).toHaveBeenCalledWith(error);
  });

  it("reports a real WebGL initialization error without a false success-path toast", () => {
    canvasMockState.throws = true;
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const onLoadError = vi.fn();
    const vrm = {
      meta: { author: "JustAPal", metaVersion: "0", title: "Mal 14.16 Optimized" },
    } as unknown as VRM;
    vi.mocked(useVrmAvatarModel).mockReturnValue({ error: null, isLoading: false, vrm });

    render(<DigitalHumanAvatar3D mouthOpen={0} onLoadError={onLoadError} status="idle" />);

    expect(screen.getByText("当前浏览器无法启用 3D 渲染。")).toBeInTheDocument();
    expect(onLoadError).toHaveBeenCalledWith(
      expect.objectContaining({
        message: "当前浏览器无法启用 3D 渲染。",
      }),
    );
  });
});
