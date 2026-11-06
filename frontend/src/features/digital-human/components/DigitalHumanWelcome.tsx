import { t } from "../../../i18n/localeStore";
import { PlatformIcon, type PlatformIconName } from "../../platform/PlatformIcon";

const suggestions: { title: string; prompt: string; icon: PlatformIconName }[] = [
  { title: "生成图片", prompt: "帮我生成一张图片", icon: "camera" },
  { title: "发送邮件", prompt: "帮我发送一封邮件", icon: "send" },
  { title: "设置提醒", prompt: "提醒我明天下午开会", icon: "bell" },
  { title: "查询股票数据", prompt: "帮我查询 A 股指数", icon: "data" },
  { title: "互动聊天", prompt: "陪我聊聊天", icon: "message" },
  { title: "了解我的能力", prompt: "你都有哪些能力？", icon: "assistant" },
];

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
              onClick={() => onSelect(t(prompt))}
              type="button"
            >
              <span className="digital-human-welcome__icon">
                <PlatformIcon name={icon} size={22} />
              </span>
              <span className="digital-human-welcome__text">
                <strong>{t(title)}</strong>
                <span>{t(prompt)}</span>
              </span>
              <PlatformIcon name="chevron" size={18} />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
