import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { VrmModelPreviewPage } from "./VrmModelPreviewPage";
import "../styles/global.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("找不到 VRM 预览页面挂载节点。");
}

createRoot(rootElement).render(
  <StrictMode>
    <VrmModelPreviewPage />
  </StrictMode>,
);
