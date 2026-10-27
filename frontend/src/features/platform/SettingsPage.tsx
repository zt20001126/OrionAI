import { useEffect, useState } from "react";

import { platformPaths, type PlatformRoute } from "./platformData";
import type { UserProfile } from "./profileApi";
import { ProfileSettingsPage } from "./ProfileSettingsPage";
import { SecuritySettingsPage } from "./SecuritySettingsPage";

interface SettingsPageProps {
  account: string;
  onNavigate: (path: PlatformRoute) => void;
  onDirtyChange: (isDirty: boolean) => void;
  onPasswordChanged: (message: string) => void;
  onProfileUpdated: (profile: UserProfile) => void;
  pathname: PlatformRoute;
}

/** 设置页外壳，个人和安全设置在同一应用页面内切换。 */
export function SettingsPage({
  account,
  onNavigate,
  onDirtyChange,
  onPasswordChanged,
  onProfileUpdated,
  pathname,
}: SettingsPageProps) {
  const [profileDirty, setProfileDirty] = useState(false);
  const [securityDirty, setSecurityDirty] = useState(false);
  const isSecuritySettings = pathname === platformPaths.securitySettings;

  useEffect(() => {
    onDirtyChange(profileDirty || securityDirty);
  }, [onDirtyChange, profileDirty, securityDirty]);

  function selectTab(path: PlatformRoute) {
    if (path === pathname) return;
    onNavigate(path);
  }

  return (
    <section aria-label="用户设置" className="account-settings-layout">
      <nav aria-label="设置导航" className="account-settings-nav">
        <button
          aria-current={!isSecuritySettings ? "page" : undefined}
          className={`account-settings-nav__item${!isSecuritySettings ? " is-active" : ""}`}
          onClick={() => selectTab(platformPaths.settings)}
          type="button"
        >
          个人设置
        </button>
        <button
          aria-current={isSecuritySettings ? "page" : undefined}
          className={`account-settings-nav__item${isSecuritySettings ? " is-active" : ""}`}
          onClick={() => selectTab(platformPaths.securitySettings)}
          type="button"
        >
          安全设置
        </button>
      </nav>

      <div className="account-settings-content">
        <ProfileSettingsPage
          hidden={isSecuritySettings}
          onDirtyChange={setProfileDirty}
          onProfileUpdated={onProfileUpdated}
        />
        <SecuritySettingsPage
          account={account}
          hidden={!isSecuritySettings}
          onDirtyChange={setSecurityDirty}
          onPasswordChanged={onPasswordChanged}
        />
      </div>
    </section>
  );
}
