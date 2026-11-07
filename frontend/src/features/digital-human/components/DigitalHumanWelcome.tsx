import type { MouseEvent } from "react";
import { t } from "../../../i18n/localeStore";
import { PlatformIcon, type PlatformIconName } from "../../platform/PlatformIcon";

const suggestions: { title: string; prompt: string; icon: PlatformIconName }[] = [
  { title: "生成图片", prompt: "帮我生成一张图片", icon: "camera" },
  { title: "发送邮件", prompt: "帮我发送一封邮件", icon: "send" },
  { title: "设置提醒", prompt: "提醒我明天下午开会", icon: "bell" },
  { title: "查询股票数据", prompt: "帮我查询 A 股指数", icon: "data" },
  { title: "简历修改", prompt: "帮我修改求职意向", icon: "document" },
  { title: "生成视频", prompt: "帮我生成一个视频", icon: "camera" },
  { title: "查询文献", prompt: "帮我查找关于目标检测的文献", icon: "search" },
  { title: "查询天气", prompt: "帮我查一下北京今天的天气", icon: "cloud" },
  { title: "查询商品", prompt: "给我查找商品 男款羽绒服", icon: "taobao" },
  { title: "商品详情", prompt: "查询商品 2205695 的详情", icon: "package" },
  { title: "互动聊天", prompt: "陪我聊聊天", icon: "message" },
  { title: "了解我的能力", prompt: "你都有哪些能力？", icon: "assistant" },
];

/** 在点击位置显示短暂波纹；输入：卡片点击事件；输出：无；调用方：能力引导卡片。 */
function showClickRipple(event: MouseEvent<HTMLButtonElement>) {
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

  const card = event.currentTarget;
  const bounds = card.getBoundingClientRect();
  const ripple = document.createElement("span");
  const diameter = Math.hypot(bounds.width, bounds.height) * 2;
  const x = event.detail === 0 ? bounds.width / 2 : event.clientX - bounds.left;
  const y = event.detail === 0 ? bounds.height / 2 : event.clientY - bounds.top;
  ripple.className = "digital-human-welcome__ripple";
  ripple.style.width = `${diameter}px`;
  ripple.style.height = `${diameter}px`;
  ripple.style.left = `${x}px`;
  ripple.style.top = `${y}px`;
  card.appendChild(ripple);
  ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
}

/** 展示新会话的能力示例；选择后填入提示词，调用方：数字人页面。 */
export function DigitalHumanWelcome({
  draft,
  onSelect,
  onSkip,
}: {
  draft: string;
  onSelect: (prompt: string) => void;
  onSkip: () => void;
}) {
  return (
    <div className="digital-human-welcome">
      <div className="digital-human-welcome__content">
        <header className="digital-human-welcome__header">
          <div>
            <h1>{t("你好，我是 Orion 助手")}</h1>
            <p>{t("选择一个能力，试着和我聊聊")}</p>
          </div>
          <button className="digital-human-welcome__skip" onClick={onSkip} type="button">
            {t("跳过引导")}
          </button>
        </header>
        <div className="digital-human-welcome__list">
          {suggestions.map(({ title, prompt, icon }) => (
            <button
              aria-pressed={draft === t(prompt)}
              className="digital-human-welcome__item"
              key={title}
              onClick={(event) => {
                showClickRipple(event);
                onSelect(t(prompt));
              }}
              type="button"
            >
              <span className="digital-human-welcome__icon">
                <PlatformIcon name={icon} size={22} />
              </span>
              <span className="digital-human-welcome__text">
                <strong>{t(title)}</strong>
                <span>{t(prompt)}</span>
              </span>
              <span className="digital-human-welcome__arrow" aria-hidden="true">
                <PlatformIcon name="chevron" size={18} />
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
