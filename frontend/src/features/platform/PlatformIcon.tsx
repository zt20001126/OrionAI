export type PlatformIconName =
  | "market"
  | "agents"
  | "sessions"
  | "knowledge"
  | "tools"
  | "settings"
  | "logout"
  | "search"
  | "bell"
  | "more"
  | "chevron"
  | "arrow"
  | "close"
  | "assistant"
  | "document"
  | "data"
  | "camera"
  | "user"
  | "calendar"
  | "clock"
  | "history"
  | "plus"
  | "collapse"
  | "expand";

interface PlatformIconProps {
  name: PlatformIconName;
  size?: number;
}

export function PlatformIcon({ name, size = 20 }: PlatformIconProps) {
  return (
    <svg
      aria-hidden="true"
      className="platform-icon"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
    >
      {name === "market" && (
        <>
          <rect x="4" y="4" width="6" height="6" rx="1.5" />
          <rect x="14" y="4" width="6" height="6" rx="1.5" />
          <rect x="4" y="14" width="6" height="6" rx="1.5" />
          <rect x="14" y="14" width="6" height="6" rx="1.5" />
        </>
      )}
      {name === "agents" && (
        <>
          <path d="M12 3.5 13.6 9l5.4 1.5-5.4 1.6L12 17.5l-1.6-5.4L5 10.5 10.4 9 12 3.5Z" />
          <path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" />
        </>
      )}
      {name === "sessions" && (
        <>
          <path d="M20 11.5a7.8 7.8 0 0 1-8 7.5 8.4 8.4 0 0 1-3.7-.8L4 20l1.2-3.7A7.2 7.2 0 0 1 4 12c0-4.1 3.6-7.5 8-7.5s8 3.1 8 7Z" />
          <path d="M8 11h8M8 14h5" />
        </>
      )}
      {name === "knowledge" && (
        <>
          <path d="M4 5.5c2.8-1.3 5.5-1.3 8 0v14c-2.5-1.3-5.2-1.3-8 0v-14Z" />
          <path d="M20 5.5c-2.8-1.3-5.5-1.3-8 0v14c2.5-1.3 5.2-1.3 8 0v-14Z" />
        </>
      )}
      {name === "tools" && (
        <>
          <path d="M14.5 6.2a5 5 0 0 0-6.4 6.4l-4.2 4.2a2 2 0 0 0 2.8 2.8l4.2-4.2a5 5 0 0 0 6.4-6.4l-3.1 3.1-2.8-2.8 3.1-3.1Z" />
          <path d="m16.4 15.7 3.2 3.2" />
        </>
      )}
      {name === "settings" && (
        <>
          <path d="M12 8.2a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6Z" />
          <path d="m19.1 13.6 1.2.9-1.8 3.1-1.4-.6a8 8 0 0 1-1.6.9l-.2 1.5h-3.6l-.2-1.5a8 8 0 0 1-1.6-.9l-1.4.6-1.8-3.1 1.2-.9a7 7 0 0 1 0-1.8l-1.2-.9 1.8-3.1 1.4.6a8 8 0 0 1 1.6-.9l.2-1.5h3.6l.2 1.5a8 8 0 0 1 1.6.9l1.4-.6 1.8 3.1-1.2.9a7 7 0 0 1 0 1.8Z" />
        </>
      )}
      {name === "logout" && (
        <>
          <path d="M10 5H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h4" />
          <path d="M14 8l4 4-4 4M8 12h10" />
        </>
      )}
      {name === "search" && (
        <>
          <circle cx="10.8" cy="10.8" r="6.3" />
          <path d="m15.5 15.5 4.3 4.3" />
        </>
      )}
      {name === "bell" && (
        <>
          <path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Z" />
          <path d="M10 21h4" />
        </>
      )}
      {name === "more" && (
        <>
          <circle cx="5" cy="12" r="1" fill="currentColor" stroke="none" />
          <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
          <circle cx="19" cy="12" r="1" fill="currentColor" stroke="none" />
        </>
      )}
      {name === "chevron" && <path d="m7 10 5 5 5-5" />}
      {name === "arrow" && <path d="M5 12h14m-6-6 6 6-6 6" />}
      {name === "close" && <path d="m6 6 12 12M18 6 6 18" />}
      {name === "assistant" && (
        <>
          <rect x="4" y="7" width="16" height="12" rx="3" />
          <path d="M12 4v3M8 12h.01M16 12h.01M9 16h6" />
        </>
      )}
      {name === "document" && (
        <>
          <path d="M7 3.8h7l4 4v12.4H7a2 2 0 0 1-2-2V5.8a2 2 0 0 1 2-2Z" />
          <path d="M14 4v4h4M8.5 12h7M8.5 15.5h7" />
        </>
      )}
      {name === "data" && (
        <>
          <path d="M4 19.5h16M6.5 16V11m5 5V5m5 11V8" />
          <circle cx="6.5" cy="9" r="1.5" />
          <circle cx="11.5" cy="3.5" r="1.5" />
          <circle cx="16.5" cy="6.5" r="1.5" />
        </>
      )}
      {name === "camera" && (
        <>
          <path d="M4.5 8.5h3l1.5-2.2h7l1.5 2.2h2A1.5 1.5 0 0 1 21 10v8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18v-8a1.5 1.5 0 0 1 1.5-1.5Z" />
          <circle cx="12" cy="13.5" r="3.2" />
        </>
      )}
      {name === "user" && (
        <>
          <circle cx="12" cy="8" r="3.4" />
          <path d="M4.5 20c.7-3.2 3.6-5.2 7.5-5.2s6.8 2 7.5 5.2H4.5Z" />
        </>
      )}
      {name === "calendar" && (
        <>
          <rect x="4" y="5.5" width="16" height="15" rx="2" />
          <path d="M8 3.5v4M16 3.5v4M4 9.5h16M8 13h2" />
        </>
      )}
      {name === "clock" && (
        <>
          <circle cx="12" cy="12" r="8.5" />
          <path d="M12 7v5l3.5 2" />
        </>
      )}
      {name === "history" && (
        <>
          <path d="M4.5 8.5A8 8 0 1 1 4 13" />
          <path d="M4 4.5v4h4M12 7.5v5l3 1.8" />
        </>
      )}
      {name === "plus" && <path d="M12 5v14M5 12h14" />}
      {name === "collapse" && (
        <>
          <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
          <path d="M9 5v14m3-4 3-3-3-3" />
        </>
      )}
      {name === "expand" && (
        <>
          <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
          <path d="M9 5v14m6-4-3-3 3-3" />
        </>
      )}
    </svg>
  );
}
