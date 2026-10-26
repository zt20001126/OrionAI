import { useEffect, useState } from "react";

type ApiStatus = "checking" | "online" | "offline";

export default function App() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");

  useEffect(() => {
    let isActive = true;

    void fetch("/api/health")
      .then((response) => {
        if (!response.ok) {
          throw new Error("健康检查请求失败");
        }
        return response.json();
      })
      .then(() => {
        if (isActive) {
          setApiStatus("online");
        }
      })
      .catch(() => {
        if (isActive) {
          setApiStatus("offline");
        }
      });

    return () => {
      isActive = false;
    };
  }, []);

  const statusText = {
    checking: "正在检查后端连接",
    online: "API 服务正常",
    offline: "API 暂不可用",
  }[apiStatus];

  return (
    <main className="page-shell">
      <section className="welcome-card" aria-labelledby="page-title">
        <div className="brand-mark" aria-hidden="true">
          O
        </div>
        <p className="eyebrow">ORIONAI PLATFORM</p>
        <h1 id="page-title">OrionAI</h1>
        <p className="intro">企业级 AI 智能体应用平台基础骨架</p>
        <p className="status" data-state={apiStatus} role="status">
          <span className="status-indicator" aria-hidden="true" />
          {statusText}
        </p>
        <p className="footnote">前端与 API 已接通，业务模块将在后续迭代中逐步建设。</p>
      </section>
    </main>
  );
}
