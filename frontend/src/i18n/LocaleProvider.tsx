import { useEffect, useSyncExternalStore, type ReactNode } from "react";

import { getLocale, getLocaleTag, subscribeLocale } from "./localeStore";

interface LocaleProviderProps {
  children: ReactNode;
}

export function LocaleProvider({ children }: LocaleProviderProps) {
  const locale = useLocale();

  useEffect(() => {
    document.documentElement.lang = getLocaleTag(locale);
    const description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (description) {
      description.content =
        locale === "en"
          ? "An enterprise platform for AI agents."
          : "OrionAI 企业级 AI 智能体应用平台基础骨架";
    }
  }, [locale]);

  return children;
}

export function useLocale() {
  return useSyncExternalStore(subscribeLocale, getLocale, getLocale);
}
