import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

import { setLocale, t, type Locale } from "./localeStore";
import { useLocale } from "./LocaleProvider";

interface LanguageSwitcherProps {
  variant?: "button" | "menu-item";
  className?: string;
  icon?: ReactNode;
}

const languageOptions: { locale: Locale; label: string; flag: string }[] = [
  { locale: "zh-CN", label: "中文", flag: "🇨🇳" },
  { locale: "en", label: "English", flag: "🇬🇧" },
];

export function LanguageSwitcher({
  variant = "button",
  className = "",
  icon,
}: LanguageSwitcherProps) {
  if (variant === "menu-item") {
    return <ProfileMenuLanguageSwitcher className={className} icon={icon} />;
  }

  return <AuthLanguageSwitcher className={className} />;
}

function ProfileMenuLanguageSwitcher({ className, icon }: LanguageSwitcherProps) {
  const locale = useLocale();
  const nextLocale: Locale = locale === "zh-CN" ? "en" : "zh-CN";

  return (
    <button
      aria-label={t(nextLocale === "en" ? "切换到英文" : "切换到简体中文")}
      className={`profile-menu__item language-switcher language-switcher--menu-item${className ? ` ${className}` : ""}`}
      onClick={() => setLocale(nextLocale)}
      role="menuitem"
      type="button"
    >
      {icon}
      {t(locale === "zh-CN" ? "简体中文" : "English")}
    </button>
  );
}

function AuthLanguageSwitcher({ className }: { className: string }) {
  const locale = useLocale();
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const initialFocusIndexRef = useRef<number | null>(null);
  const menuId = useId();
  const selectedIndex = locale === "zh-CN" ? 0 : 1;

  const closeMenu = useCallback((restoreFocus = false) => {
    setIsOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    function closeOnOutsidePointer(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && !rootRef.current?.contains(target)) closeMenu();
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeMenu(true);
    }

    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [closeMenu, isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const focusIndex = initialFocusIndexRef.current ?? selectedIndex;
    initialFocusIndexRef.current = null;
    const frame = window.requestAnimationFrame(() => optionRefs.current[focusIndex]?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [isOpen, selectedIndex]);

  function openMenu(focusIndex = selectedIndex) {
    initialFocusIndexRef.current = focusIndex;
    setIsOpen(true);
  }

  function handleTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      openMenu(event.key === "ArrowUp" ? languageOptions.length - 1 : selectedIndex);
    }
  }

  function handleOptionKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === "Tab") {
      window.setTimeout(() => closeMenu(), 0);
      return;
    }

    let nextIndex: number | null = null;
    if (event.key === "ArrowDown") nextIndex = (index + 1) % languageOptions.length;
    if (event.key === "ArrowUp") {
      nextIndex = (index - 1 + languageOptions.length) % languageOptions.length;
    }
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = languageOptions.length - 1;

    if (nextIndex !== null) {
      event.preventDefault();
      optionRefs.current[nextIndex]?.focus();
    }
  }

  function chooseLocale(nextLocale: Locale) {
    if (locale !== nextLocale) setLocale(nextLocale);
    closeMenu(true);
  }

  return (
    <div
      className={`auth-language-switcher${className ? ` ${className}` : ""}`}
      ref={rootRef}
    >
      <button
        aria-controls={isOpen ? menuId : undefined}
        aria-expanded={isOpen}
        aria-haspopup="menu"
        aria-label={t("切换语言")}
        className="button button--outline language-switcher auth-language-switcher__trigger"
        onClick={() => (isOpen ? closeMenu() : openMenu())}
        onKeyDown={handleTriggerKeyDown}
        ref={triggerRef}
        type="button"
      >
        <GlobeIcon />
        <span>{locale === "zh-CN" ? "中文" : "English"}</span>
        <ChevronDownIcon isOpen={isOpen} />
      </button>

      {isOpen && (
        <div
          aria-label={t("切换语言")}
          className="auth-language-switcher__menu"
          id={menuId}
          role="menu"
        >
          {languageOptions.map((option, index) => {
            const isSelected = locale === option.locale;

            return (
              <button
                aria-checked={isSelected}
                className="auth-language-switcher__option"
                key={option.locale}
                onClick={() => chooseLocale(option.locale)}
                onKeyDown={(event) => handleOptionKeyDown(event, index)}
                ref={(element) => {
                  optionRefs.current[index] = element;
                }}
                role="menuitemradio"
                tabIndex={-1}
                type="button"
              >
                <span aria-hidden="true" className="auth-language-switcher__flag">
                  {option.flag}
                </span>
                <span>{option.label}</span>
                {isSelected && <CheckIcon />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function GlobeIcon() {
  return (
    <svg
      aria-hidden="true"
      className="auth-language-switcher__globe"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M3.5 12h17M12 3c2.2 2.4 3.2 5.4 3.2 9s-1 6.6-3.2 9c-2.2-2.4-3.2-5.4-3.2-9S9.8 5.4 12 3Z" />
    </svg>
  );
}

function ChevronDownIcon({ isOpen }: { isOpen: boolean }) {
  return (
    <svg
      aria-hidden="true"
      className={`auth-language-switcher__chevron${isOpen ? " is-open" : ""}`}
      fill="none"
      viewBox="0 0 24 24"
    >
      <path d="m7 10 5 5 5-5" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      aria-hidden="true"
      className="auth-language-switcher__check"
      fill="none"
      viewBox="0 0 24 24"
    >
      <path d="m5 12.5 4.2 4.2L19 7" />
    </svg>
  );
}
