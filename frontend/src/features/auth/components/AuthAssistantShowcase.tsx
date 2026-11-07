import { lazy, Suspense, useState } from "react";
import { PlatformIcon, type PlatformIconName } from "../../platform/PlatformIcon";
import { t } from "../../../i18n/localeStore";
import { useVrmPointerLookTarget } from "../../digital-human/hooks/useVrmPointerLookTarget";

import "./auth-assistant-showcase.css";

const LazyDigitalHumanAvatar3D = lazy(() =>
  import("../../digital-human/components/DigitalHumanAvatar3D").then((module) => ({
    default: module.DigitalHumanAvatar3D,
  })),
);

interface AssistantFeature {
  id: string;
  title: string;
  description: string;
  example: string;
  icon: PlatformIconName;
}

const assistantFeatures: AssistantFeature[] = [
  {
    id: "image",
    title: "生成图片",
    description: "把想法变成一张图片",
    example: "帮我生成一张晴天海边的插画",
    icon: "camera",
  },
  {
    id: "email",
    title: "发送邮件",
    description: "快速起草并发送邮件",
    example: "帮我给团队发送本周进度邮件",
    icon: "send",
  },
  {
    id: "reminder",
    title: "设置提醒",
    description: "重要安排准时提醒",
    example: "提醒我明天下午三点开会",
    icon: "bell",
  },
  {
    id: "stocks",
    title: "查询股票数据",
    description: "获取市场与股票信息",
    example: "查询今天沪深 300 指数表现",
    icon: "data",
  },
  {
    id: "resume",
    title: "简历修改",
    description: "让简历表达更清楚",
    example: "帮我优化这段项目经历",
    icon: "document",
  },
  {
    id: "video",
    title: "生成视频",
    description: "将创意整理成短视频",
    example: "为这段产品介绍生成一个短视频",
    icon: "camera",
  },
  {
    id: "literature",
    title: "查询文献",
    description: "查找并梳理相关研究",
    example: "查找大模型智能体的相关论文",
    icon: "search",
  },
  {
    id: "weather",
    title: "查询天气",
    description: "了解城市天气与预报",
    example: "查一下明天北京的天气",
    icon: "cloud",
  },
  {
    id: "products",
    title: "查询商品",
    description: "给我查找商品 男款羽绒服",
    example: "给我查找商品 男款羽绒服",
    icon: "taobao",
  },
  {
    id: "product-detail",
    title: "商品详情",
    description: "查询商品 2205695 的详情",
    example: "查询商品 2205695 的详情",
    icon: "package",
  },
  {
    id: "chat",
    title: "互动聊天",
    description: "随时开启自然对话",
    example: "和我聊聊最近的学习计划",
    icon: "sessions",
  },
  {
    id: "capabilities",
    title: "了解我的能力",
    description: "探索 Orion 助手能做什么",
    example: "你可以帮我完成哪些事情？",
    icon: "assistant",
  },
];

interface AuthAssistantShowcaseProps {
  onRequireAuth: () => void;
}

const ignoreAvatarError = () => undefined;

/** 展示未登录可浏览的 Orion 能力；所有执行入口只引导回登录页。 */
export function AuthAssistantShowcase({ onRequireAuth }: AuthAssistantShowcaseProps) {
  const [expandedFeature, setExpandedFeature] = useState<string | null>(null);
  const [showFeatures, setShowFeatures] = useState(true);
  const lookTargetRef = useVrmPointerLookTarget();

  return (
    <section
      aria-label={t("Orion 助手功能展示")}
      className="auth-assistant-screen"
      id="auth-assistant-screen"
    >
      <div aria-hidden="true" className="auth-assistant-background" />
      <div className="auth-assistant-layout">
        <div aria-hidden="true" className="auth-assistant-avatar">
          <div className="auth-assistant-avatar__glow" />
          <Suspense fallback={<div className="auth-assistant-avatar__loading" />}>
            <LazyDigitalHumanAvatar3D
              cameraFraming="assistant"
              enableClickInteraction
              lookTargetRef={lookTargetRef}
              mouthOpen={0}
              onLoadError={ignoreAvatarError}
              presentation="home"
              status="idle"
            />
          </Suspense>
        </div>

        <div className="auth-assistant-content">
          <header className="auth-assistant-heading">
            <div>
              <h2>{t("你好，我是 Orion 助手")}</h2>
              <p>{t("选择一个能力，试着和我聊聊")}</p>
            </div>
            <button
              aria-controls="auth-assistant-features"
              aria-expanded={showFeatures}
              className="auth-assistant-skip"
              onClick={() => setShowFeatures((visible) => !visible)}
              type="button"
            >
              {t(showFeatures ? "跳过引导" : "重新显示能力")}
            </button>
          </header>

          {showFeatures && (
            <div className="auth-assistant-feature-grid" id="auth-assistant-features">
              {assistantFeatures.map((feature) => {
                const isExpanded = expandedFeature === feature.id;
                const detailsId = `auth-assistant-feature-${feature.id}`;
                return (
                  <article
                    className={`auth-assistant-feature${isExpanded ? " is-expanded" : ""}`}
                    key={feature.id}
                  >
                    <button
                      aria-expanded={isExpanded}
                      className="auth-assistant-feature__toggle"
                      onClick={() => setExpandedFeature(isExpanded ? null : feature.id)}
                      type="button"
                    >
                      <span className="auth-assistant-feature__icon">
                        <PlatformIcon name={feature.icon} size={20} />
                      </span>
                      <span className="auth-assistant-feature__copy">
                        <strong>{t(feature.title)}</strong>
                        <span>{t(feature.description)}</span>
                      </span>
                      <span className="auth-assistant-feature__chevron">
                        <PlatformIcon name="chevron" size={17} />
                      </span>
                    </button>
                    {isExpanded && (
                      <div className="auth-assistant-feature__details" id={detailsId}>
                        <p>
                          {t("例如：")}「{t(feature.example)}」
                        </p>
                        <button onClick={onRequireAuth} type="button">
                          {t("登录后体验")}
                        </button>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}

          <div className="auth-assistant-composer">
            <span className="auth-assistant-composer__lock">
              <PlatformIcon name="lock" size={19} />
            </span>
            <input
              aria-label={t("请先登录后开始对话")}
              onClick={onRequireAuth}
              onKeyDown={(event) => {
                if (event.key === "Enter") onRequireAuth();
              }}
              placeholder={t("请先登录后开始对话")}
              readOnly
              type="text"
            />
            <button
              aria-label={t("登录后使用语音")}
              className="auth-assistant-composer__action"
              onClick={onRequireAuth}
              type="button"
            >
              <PlatformIcon name="microphone" size={19} />
            </button>
            <button
              aria-label={t("登录后发送消息")}
              className="auth-assistant-composer__send"
              onClick={onRequireAuth}
              type="button"
            >
              <PlatformIcon name="arrow" size={19} />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
