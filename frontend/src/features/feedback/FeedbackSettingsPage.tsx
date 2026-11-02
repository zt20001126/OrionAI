/** 将问题反馈表单嵌入设置页右侧内容区域。 */

import { FeedbackForm } from "./FeedbackForm";
import "./feedback.css";

interface FeedbackSettingsPageProps {
  hidden?: boolean;
  onDirtyChange?: (isDirty: boolean) => void;
}

/** 设置页内的反馈卡片复用头像菜单弹窗使用的表单组件。 */
export function FeedbackSettingsPage({ hidden = false, onDirtyChange }: FeedbackSettingsPageProps) {
  return (
    <section
      aria-labelledby="feedback-settings-title"
      className="profile-settings-page feedback-settings-page"
      hidden={hidden}
    >
      <div className="profile-settings feedback-settings">
        <FeedbackForm onDirtyChange={onDirtyChange} variant="settings" />
      </div>
    </section>
  );
}
