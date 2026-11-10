import { useEffect, useRef, useState, type CSSProperties } from "react";
import { PlatformIcon } from "../../platform/PlatformIcon";
import { t } from "../../../i18n/localeStore";

const capabilities = [
  {
    title: "多智能体协作",
    description: "灵活组合不同能力\n处理更复杂的任务",
    icon: "layers",
    decoration: "layers",
  },
  {
    title: "工具调用",
    description: "连接丰富的第三方工具\n获取实时数据与服务",
    icon: "wrench",
    decoration: "tools",
  },
  {
    title: "语音交互",
    description: "与数字人自然对话\n支持语音输入与播报",
    icon: "microphone",
    decoration: "waveform",
  },
  {
    title: "长期记忆",
    description: "记住你的偏好与上下文\n提供更个性化的服务",
    icon: "brain",
    decoration: "brain",
  },
  {
    title: "任务自动化",
    description: "通过工作流编排\n让重复任务自动完成",
    icon: "workflow",
    decoration: "workflow",
  },
  {
    title: "丰富的应用场景",
    description: "覆盖学习、办公、求职\n创作、生活等多种场景",
    icon: "sparkles",
    decoration: "cube",
  },
] as const;

interface HomeCapabilitiesSectionProps {
  onRequireAuth: () => void;
}

/** 展示首页第三屏的核心能力和登录引导；由认证首页在数字人体验屏后调用。 */
export function HomeCapabilitiesSection({ onRequireAuth }: HomeCapabilitiesSectionProps) {
  const sectionRef = useRef<HTMLElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;
    if (typeof IntersectionObserver === "undefined") {
      setIsVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setIsVisible(true);
        observer.disconnect();
      },
      { threshold: 0.12 },
    );
    observer.observe(section);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      aria-labelledby="home-capabilities-title"
      className={`home-capabilities-section${isVisible ? " is-visible" : ""}`}
      ref={sectionRef}
    >
      <div aria-hidden="true" className="capabilities-background">
        <span className="capabilities-star capabilities-star--one" />
        <span className="capabilities-star capabilities-star--two" />
        <span className="capabilities-star capabilities-star--three" />
      </div>

      <div className="capabilities-content">
        <header className="capabilities-header">
          <div aria-label="Why OrionAI" className="capabilities-eyebrow">
            <span>WHY ORIONAI</span>
          </div>
          <h2 id="home-capabilities-title">
            不止于对话，让 <span className="capabilities-ai">AI</span> 真正完成任务
          </h2>
          <p>从智能交互到工具执行，探索更高效的 AI 工作方式</p>
        </header>

        <div className="capabilities-grid">
          {capabilities.map((capability, index) => (
            <article
              className="capability-card"
              key={capability.title}
              style={{ "--capability-index": index } as CSSProperties}
            >
              <span
                aria-hidden="true"
                className={`capability-icon capability-icon--${capability.icon}`}
              >
                <FeatureIcon name={capability.icon} />
              </span>
              <div className="capability-copy">
                <h3>{t(capability.title)}</h3>
                <p>{t(capability.description)}</p>
              </div>
              <FeatureDecoration name={capability.decoration} />
            </article>
          ))}
        </div>

        <footer className="capabilities-footer">
          <button className="capabilities-cta" onClick={onRequireAuth} type="button">
            <span>开启你的 AI 探索之旅</span>
            <PlatformIcon name="arrow" size={22} />
          </button>
          <p>从一次对话开始，体验更多可能</p>
        </footer>
      </div>

      <div aria-hidden="true" className="capabilities-horizon">
        <svg preserveAspectRatio="none" viewBox="0 0 1440 190">
          <defs>
            <linearGradient id="capabilities-horizon-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#ffffff" stopOpacity="0.74" />
              <stop offset="0.12" stopColor="#c9d5ff" stopOpacity="0.38" />
              <stop offset="1" stopColor="#b9c9ff" stopOpacity="0.05" />
            </linearGradient>
            <linearGradient id="capabilities-horizon-line" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" stopColor="#ffffff" stopOpacity="0" />
              <stop offset="0.5" stopColor="#ffffff" stopOpacity="0.96" />
              <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d="M0 150 Q720 -45 1440 150 V190 H0Z" fill="url(#capabilities-horizon-fill)" />
          <path
            d="M0 150 Q720 -45 1440 150"
            fill="none"
            stroke="url(#capabilities-horizon-line)"
            strokeWidth="3"
          />
          <path d="M0 158 Q720 -35 1440 158" fill="none" stroke="#c5caff" strokeOpacity="0.34" />
        </svg>
      </div>
    </section>
  );
}

function FeatureIcon({ name }: { name: (typeof capabilities)[number]["icon"] }) {
  if (name === "microphone") return <PlatformIcon name="microphone" size={30} />;

  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 32 32">
      {name === "layers" && <path d="m16 5 12 7-12 7L4 12l12-7Zm-12 12 12 7 12-7M4 22l12 7 12-7" />}
      {name === "wrench" && (
        <path d="M19.5 5.5a8 8 0 0 0-9.8 10L4 21.2a3.4 3.4 0 1 0 4.8 4.8l5.7-5.7a8 8 0 0 0 10-9.8l-5.2 5.2-5-5 5.2-5.2Z" />
      )}
      {name === "brain" && (
        <path d="M16 5a5 5 0 0 0-8.8 3.2 5 5 0 0 0-2 8.2 5 5 0 0 0 4.6 8.3A5 5 0 0 0 16 27V5Zm0 0a5 5 0 0 1 8.8 3.2 5 5 0 0 1 2 8.2 5 5 0 0 1-4.6 8.3A5 5 0 0 1 16 27V5Zm-5 5v2m0 5v2m10-9v2m0 5v2M11 16h5m5 0h-5" />
      )}
      {name === "sparkles" && (
        <path d="m15 4 2.2 7.8L25 14l-7.8 2.2L15 24l-2.2-7.8L5 14l7.8-2.2L15 4Zm11 15 .9 3.1L30 23l-3.1.9L26 27l-.9-3.1L22 23l3.1-.9L26 19Z" />
      )}
      {name === "workflow" && (
        <>
          <path d="M16 10v7m0 0-8 6m8-6 8 6" />
          <rect x="12" y="3" width="8" height="8" rx="2" />
          <rect x="3" y="22" width="9" height="8" rx="2" />
          <rect x="20" y="22" width="9" height="8" rx="2" />
        </>
      )}
    </svg>
  );
}

function FeatureDecoration({ name }: { name: (typeof capabilities)[number]["decoration"] }) {
  return (
    <svg
      aria-hidden="true"
      className={`capability-art capability-art--${name}`}
      viewBox="0 0 150 110"
    >
      <defs>
        <linearGradient id={`art-${name}-a`} x1="0" x2="1" y1="0" y2="1">
          <stop stopColor="#ffffff" stopOpacity="0.92" />
          <stop offset="0.52" stopColor="#b9caff" stopOpacity="0.78" />
          <stop offset="1" stopColor="#9b83ff" stopOpacity="0.62" />
        </linearGradient>
        <linearGradient id={`art-${name}-b`} x1="0" x2="1" y1="0" y2="1">
          <stop stopColor="#dceaff" stopOpacity="0.8" />
          <stop offset="1" stopColor="#8b78f6" stopOpacity="0.48" />
        </linearGradient>
      </defs>
      {name === "layers" && (
        <>
          <path
            d="m75 13 49 24-49 25-49-25 49-24Z"
            fill="url(#art-layers-a)"
            stroke="#fff"
            strokeOpacity=".8"
          />
          <path
            d="m26 51 49 25 49-25v13L75 91 26 64V51Z"
            fill="url(#art-layers-b)"
            stroke="#fff"
            strokeOpacity=".68"
          />
          <path d="m26 69 49 25 49-25v9L75 104 26 78v-9Z" fill="url(#art-layers-a)" opacity=".56" />
        </>
      )}
      {name === "tools" && (
        <>
          <path
            d="m29 28 94-12-9 67-94 12 9-67Z"
            fill="url(#art-tools-a)"
            stroke="#fff"
            strokeWidth="2"
          />
          <path d="m29 28 94-12-3 18-94 12 3-18Z" fill="#8a72f4" fillOpacity=".58" />
          <circle cx="41" cy="34" r="2" fill="#fff" />
          <circle cx="49" cy="33" r="2" fill="#fff" />
          <path
            d="m58 56 12-10m-12 10 12 10m31-20L89 56l12 10M81 48l-9 17"
            fill="none"
            stroke="#fff"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="4"
          />
        </>
      )}
      {name === "waveform" && (
        <g fill="none" stroke="url(#art-waveform-a)" strokeLinecap="round" strokeWidth="8">
          <path d="M22 54v3M40 39v34M58 29v54M76 46v26M94 22v65M112 37v38M130 49v14" />
        </g>
      )}
      {name === "brain" && (
        <>
          <path
            d="M75 19c-9-12-26-7-27 7-14-2-20 13-12 22-11 9-5 24 7 25-2 15 13 23 25 14 3 8 16 8 19 0 12 9 27 1 25-14 12-1 18-16 7-25 8-9 2-24-12-22-1-14-18-19-27-7-9-12-26-7-27 7Z"
            fill="url(#art-brain-a)"
            stroke="#fff"
            strokeOpacity=".9"
            strokeWidth="2"
          />
          <path
            d="M75 23v65M56 36c9 2 10 11 5 16m-15 5c10-1 15 6 12 15m37-36c-9 2-10 11-5 16m15 5c-10-1-15 6-12 15"
            fill="none"
            stroke="#fff"
            strokeOpacity=".85"
            strokeWidth="2"
          />
        </>
      )}
      {name === "workflow" && (
        <>
          <path d="M75 31v28M75 59 43 82m32-23 32 23" stroke="#b8bbff" strokeWidth="4" />
          <rect x="60" y="12" width="30" height="30" rx="9" fill="url(#art-workflow-a)" />
          <rect x="23" y="68" width="34" height="29" rx="9" fill="url(#art-workflow-b)" />
          <rect x="93" y="68" width="34" height="29" rx="9" fill="url(#art-workflow-a)" />
          <circle cx="75" cy="27" r="4" fill="#fff" fillOpacity=".85" />
        </>
      )}
      {name === "cube" && (
        <>
          <path d="m46 25 56-8 20 14-6 61-57 8-20-14 7-61Z" fill="url(#art-cube-b)" opacity=".5" />
          <path
            d="m30 36 57-8 20 14-7 58-56 7-20-15 6-56Z"
            fill="url(#art-cube-a)"
            stroke="#fff"
            strokeOpacity=".82"
            strokeWidth="2"
          />
          <path
            d="m59 48 22-3 10 8-3 24-22 3-10-8 3-24Zm0 0 10 8 22-3m-22 3-3 24m13-27v23"
            fill="none"
            stroke="#fff"
            strokeLinejoin="round"
            strokeWidth="2.5"
          />
        </>
      )}
    </svg>
  );
}
