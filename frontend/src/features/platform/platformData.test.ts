import { describe, expect, it } from "vitest";

import { isDigitalHumanPath, isPlatformPath, platformPaths } from "./platformData";

describe("digital human routes", () => {
  it("recognizes the assistant root and existing conversation routes", () => {
    expect(isPlatformPath(platformPaths.digitalHuman)).toBe(true);
    expect(isPlatformPath(`${platformPaths.digitalHuman}/42`)).toBe(true);
    expect(isDigitalHumanPath(`${platformPaths.digitalHuman}/42`)).toBe(true);
    expect(isDigitalHumanPath(platformPaths.sessions)).toBe(false);
  });
});
