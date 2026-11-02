import type { ReactNode } from "react";

import { setLocale, t, type Locale } from "./localeStore";
import { useLocale } from "./LocaleProvider";

interface LanguageSwitcherProps {
  variant?: "button" | "menu-item";
  className?: string;
  icon?: ReactNode;
}

export function LanguageSwitcher({
  variant = "button",
  className = "",
  icon,
}: LanguageSwitcherProps) {
  const locale = useLocale();
  const nextLocale: Locale = locale === "zh-CN" ? "en" : "zh-CN";

  return (
    <button
      aria-label={t(nextLocale === "en" ? "切换到英文" : "切换到简体中文")}
      className={`${variant === "menu-item" ? "profile-menu__item language-switcher language-switcher--menu-item" : "button button--outline language-switcher"}${className ? ` ${className}` : ""}`}
      onClick={() => setLocale(nextLocale)}
      role={variant === "menu-item" ? "menuitem" : undefined}
      type="button"
    >
      {icon}
      {locale === "zh-CN" ? "EN" : t("中文")}
    </button>
  );
}
