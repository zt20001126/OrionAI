import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./app/App";
import { t } from "./i18n/localeStore";
import "./styles/global.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error(t("找不到应用挂载节点。"));
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
