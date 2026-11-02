import { getEnglishMessage } from "./messages";

export type Locale = "zh-CN" | "en";

const LOCALE_STORAGE_KEY = "orionai:locale";
const listeners = new Set<() => void>();

let currentLocale = readInitialLocale();

function readInitialLocale(): Locale {
  if (typeof window === "undefined") return "zh-CN";

  try {
    const storedLocale = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    return storedLocale === "en" || storedLocale === "zh-CN" ? storedLocale : "zh-CN";
  } catch {
    return "zh-CN";
  }
}

export function getLocale(): Locale {
  return currentLocale;
}

export function subscribeLocale(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setLocale(locale: Locale): void {
  if (locale !== "en" && locale !== "zh-CN") return;

  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    } catch {
      // Keep language switching available for this session when storage is blocked.
    }
  }

  if (currentLocale === locale) return;
  currentLocale = locale;
  for (const listener of listeners) listener();
}

export function t(source: string, values?: Record<string, string | number>): string {
  const translated = currentLocale === "en" ? (getEnglishMessage(source) ?? source) : source;
  if (!values) return translated;

  return translated.replace(/\{(\w+)\}/g, (placeholder, key: string) => {
    const value = values[key];
    return value === undefined ? placeholder : String(value);
  });
}

export function getLocaleTag(locale: Locale = currentLocale): string {
  return locale === "en" ? "en-US" : "zh-CN";
}
