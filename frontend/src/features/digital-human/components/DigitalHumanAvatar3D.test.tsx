import { cleanup, render, screen } from "@testing-library/react";
import { Children, isValidElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { VRM } from "@pixiv/three-vrm";
import type { ReactElement, ReactNode } from "react";

import { useVrmAvatarModel } from "../hooks/useVrmAvatarModel";
import { DigitalHumanAvatar3D } from "./DigitalHumanAvatar3D";

const canvasMockState = vi.hoisted(() => ({
  clickInteractionValues: [] as boolean[],
  throws: false,
}));

vi.mock("@react-three/fiber", () => ({
  Canvas: ({ children, fallback }: { children: ReactNode; fallback?: ReactNode }) => {
    if (canvasMockState.throws) throw new Error("Error creating WebGL context");

    const inspectChildren = (node: ReactNode) => {
      Children.forEach(node, (child) => {
        if (!isValidElement(child)) return;
        const element = child as ReactElement<{
          children?: ReactNode;
          enableClickInteraction?: boolean;
        }>;
        if (typeof child.type === "function" && child.type.name === "VrmAvatarScene") {
          canvasMockState.clickInteractionValues.push(
            element.props.enableClickInteraction ?? false,
          );
        }
        inspectChildren(element.props.children);
      });
    };

    inspectChildren(children);
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
  canvasMockState.clickInteractionValues = [];
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

  it("renders the canvas without model credits when a VRM model is available", () => {
    const vrm = {
      meta: { author: "JustAPal", metaVersion: "0", title: "Mal 14.16 Optimized" },
    } as unknown as VRM;
    vi.mocked(useVrmAvatarModel).mockReturnValue({ error: null, isLoading: false, vrm });

    const onLoadError = vi.fn();
    render(<DigitalHumanAvatar3D mouthOpen={0.6} onLoadError={onLoadError} status="speaking" />);

    expect(screen.getByTestId("avatar-canvas")).toBeInTheDocument();
    expect(screen.queryByText("Mal 14.16 Optimized · JustAPal")).not.toBeInTheDocument();
    expect(onLoadError).not.toHaveBeenCalled();
    expect(screen.getByText("当前模型不包含嘴型表情，语音口型同步不可用。")).toBeInTheDocument();
  });

  it("renders a silent home presentation without assistant status text", () => {
    const vrm = {
      meta: { author: "OrionAI", metaVersion: "1", title: "Orion" },
    } as unknown as VRM;
    vi.mocked(useVrmAvatarModel).mockReturnValue({ error: null, isLoading: false, vrm });

    render(
      <DigitalHumanAvatar3D
        mouthOpen={0}
        onLoadError={vi.fn()}
        presentation="home"
        status="idle"
      />,
    );

    expect(screen.getByTestId("avatar-canvas")).toBeInTheDocument();
    expect(document.querySelector(".digital-human-avatar--home")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps click interactions disabled by default and supports an explicit opt in", () => {
    const vrm = {
      meta: { author: "OrionAI", metaVersion: "1", title: "Orion" },
    } as unknown as VRM;
    vi.mocked(useVrmAvatarModel).mockReturnValue({ error: null, isLoading: false, vrm });

    const homeRender = render(
      <DigitalHumanAvatar3D
        mouthOpen={0}
        onLoadError={vi.fn()}
        presentation="home"
        status="idle"
      />,
    );
    expect(canvasMockState.clickInteractionValues).toEqual([false]);

    homeRender.unmount();
    render(
      <DigitalHumanAvatar3D
        enableClickInteraction
        mouthOpen={0}
        onLoadError={vi.fn()}
        presentation="home"
        status="idle"
      />,
    );

    expect(canvasMockState.clickInteractionValues).toEqual([false, true]);
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
