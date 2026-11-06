import { useEffect, useState } from "react";
import { AmbientBackground } from "../../components/AmbientBackground";
import { BrandMark } from "./ProductIntro";
import "./login-loading.css";
/** 会话恢复期间展示品牌加载画面；就绪后淡出，数字人不阻塞表单。 */
export function LoginLoadingScreen({ ready }: { ready: boolean }) {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    if (!ready) return;
    const timer = window.setTimeout(() => setVisible(false), 400);
    return () => window.clearTimeout(timer);
  }, [ready]);
  if (!visible) return null;
  return (
    <div
      className={`login-loading${ready ? " login-loading--ready" : ""}`}
      role="status"
      aria-hidden={ready || undefined}
    >
      <AmbientBackground mode="auth" />
      <div className="login-loading__waves" aria-hidden="true" />
      <div className="login-loading__content">
        <BrandMark />
        <strong>OrionAI</strong>
        <span>正在加载，请稍候...</span>
        <div className="login-loading__dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
      </div>
    </div>
  );
}
