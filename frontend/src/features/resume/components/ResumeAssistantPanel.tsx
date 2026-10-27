import { ConversationPage } from "../../conversations/ConversationPage";
import type { PlatformRoute } from "../../platform/platformData";

interface ResumeAssistantPanelProps {
  conversationId: string | null;
  isOpen: boolean;
  onCollapse: () => void;
  onConversationIdChange: (conversationId: string | null) => void;
  onNavigate: (path: PlatformRoute) => void;
  onResumeSaved: () => void | Promise<void>;
}

export function ResumeAssistantPanel({
  conversationId,
  isOpen,
  onCollapse,
  onConversationIdChange,
  onNavigate,
  onResumeSaved,
}: ResumeAssistantPanelProps) {
  return (
    <div
      aria-hidden={!isOpen}
      className={`resume-workbench__assistant${isOpen ? " is-open" : " is-collapsed"}`}
    >
      <ConversationPage
        conversationId={conversationId}
        embedded
        onCollapsePanel={onCollapse}
        onConversationIdChange={onConversationIdChange}
        onNavigate={onNavigate}
        onResumeSaved={onResumeSaved}
        panelOpen={isOpen}
      />
    </div>
  );
}
