import { createConversation } from "../conversations/conversationApi";
import { platformPaths, type PlatformRoute } from "./platformData";
import type { MarketSkill } from "./skillApi";

const RUNNABLE_SKILL_CODES = new Set(["general_chat", "image_agent", "resume_assistant"]);

/** 当前前端已接入使用入口的技能编码。 */
export function canLaunchSkill(skillCode: string): boolean {
  return RUNNABLE_SKILL_CODES.has(skillCode);
}

/** 按现有技能入口规则打开技能；普通技能通过新会话运行。 */
export async function launchSkill(
  skill: Pick<MarketSkill, "code">,
  onNavigate: (path: PlatformRoute) => void,
): Promise<void> {
  if (skill.code === "general_chat") {
    onNavigate(platformPaths.chat);
    return;
  }
  if (skill.code === "resume_assistant") {
    onNavigate(platformPaths.resume);
    return;
  }

  const conversation = await createConversation(skill.code);
  onNavigate(`${platformPaths.chat}/${conversation.id}`);
}
