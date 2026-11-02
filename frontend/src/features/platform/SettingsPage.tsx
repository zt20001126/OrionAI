import { useCallback, useEffect, useState } from "react";

import { platformPaths, type PlatformRoute } from "./platformData";
import type { UserProfile } from "./profileApi";
import { ProfileSettingsPage } from "./ProfileSettingsPage";
import { SecuritySettingsPage } from "./SecuritySettingsPage";
import { PlatformIcon } from "./PlatformIcon";
import { FeedbackSettingsPage } from "../feedback/FeedbackSettingsPage";

interface SettingsPageProps {
  account: string;
  isGuest?: boolean;
  onNavigate: (path: PlatformRoute) => void;
  onDirtyChange: (isDirty: boolean) => void;
  onPasswordChanged: (message: string) => void;
  onProfileUpdated: (profile: UserProfile) => void;
  pathname: PlatformRoute;
}

/** 设置页外壳，个人和安全设置在同一应用页面内切换。 */
export function SettingsPage({
  account,
  isGuest = false,
  onNavigate,
  onDirtyChange,
  onPasswordChanged,
  onProfileUpdated,
  pathname,
}: SettingsPageProps) {
  const [profileDirty, setProfileDirty] = useState(false);
  const [securityDirty, setSecurityDirty] = useState(false);
  const [feedbackDirty, setFeedbackDirty] = useState(false);
  const isSecuritySettings = !isGuest && pathname === platformPaths.securitySettings;
  const isFeedbackSettings = pathname === platformPaths.feedbackSettings;
  const isProfileSettings = !isSecuritySettings && !isFeedbackSettings;
  const handleFeedbackDirtyChange = useCallback(
    (isDirty: boolean) => {
      setFeedbackDirty(isDirty);
      onDirtyChange(profileDirty || securityDirty || isDirty);
    },
    [onDirtyChange, profileDirty, securityDirty],
  );

  useEffect(() => {
    onDirtyChange(profileDirty || securityDirty || feedbackDirty);
  }, [feedbackDirty, onDirtyChange, profileDirty, securityDirty]);

  function selectTab(path: PlatformRoute) {
    if (path === pathname) return;
    onNavigate(path);
  }

  return (
    <section aria-label="用户设置" className="account-settings-layout">
      <nav aria-label="设置导航" className="account-settings-nav">
        <button
          aria-current={isProfileSettings ? "page" : undefined}
          className={`account-settings-nav__item${isProfileSettings ? " is-active" : ""}`}
          onClick={() => selectTab(platformPaths.settings)}
          type="button"
        >
          <PlatformIcon name="user" size={17} />
          个人设置
        </button>
        {!isGuest && (
          <button
            aria-current={isSecuritySettings ? "page" : undefined}
            className={`account-settings-nav__item${isSecuritySettings ? " is-active" : ""}`}
            onClick={() => selectTab(platformPaths.securitySettings)}
            type="button"
          >
            <PlatformIcon name="settings" size={17} />
            安全设置
          </button>
        )}
        <button
          aria-current={isFeedbackSettings ? "page" : undefined}
          className={`account-settings-nav__item${isFeedbackSettings ? " is-active" : ""}`}
          onClick={() => selectTab(platformPaths.feedbackSettings)}
          type="button"
        >
          <PlatformIcon name="message" size={17} />
          问题反馈
        </button>
      </nav>

      <div className="account-settings-content">
        <ProfileSettingsPage
          hidden={!isProfileSettings}
          onDirtyChange={setProfileDirty}
          onProfileUpdated={onProfileUpdated}
        />
        {!isGuest && (
          <SecuritySettingsPage
            account={account}
            hidden={!isSecuritySettings}
            onDirtyChange={setSecurityDirty}
            onPasswordChanged={onPasswordChanged}
          />
        )}
        <FeedbackSettingsPage
          hidden={!isFeedbackSettings}
          onDirtyChange={handleFeedbackDirtyChange}
        />
      </div>
    </section>
  );
}
