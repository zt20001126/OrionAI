import { createConversation } from "../conversations/conversationApi";
import { checkMembershipAccess } from "../membership/membershipApi";
import { platformPaths, type PlatformRoute } from "./platformData";
import type { MarketSkill } from "./skillApi";
import type { ConfirmOptions } from "../../components/ConfirmationDialog";

const RUNNABLE_SKILL_CODES = new Set([
  "general_chat",
  "image_agent",
  "resume_assistant",
  "reminder",
  "memory_training",
]);

/** 当前前端已接入使用入口的技能编码。 */
export function canLaunchSkill(skillCode: string): boolean {
  return RUNNABLE_SKILL_CODES.has(skillCode);
}

/** 每次启动技能前检查会员状态，并为非会员提供充值或关闭选项。 */
export async function ensureSkillMembership(
  onNavigate: (path: PlatformRoute) => void,
  confirm: (options: ConfirmOptions) => Promise<boolean>,
  onCheckError: (message: string) => void,
): Promise<boolean> {
  let isMember: boolean;
  try {
    isMember = await checkMembershipAccess();
  } catch (error) {
    onCheckError(error instanceof Error ? error.message : "会员状态暂时无法确认，请稍后重试。");
    return false;
  }

  if (isMember) return true;

  const shouldRecharge = await confirm({
    title: "开通会员后即可使用",
    description: "此技能需要有效会员。你可以前往充值，或关闭此提示。",
    cancelLabel: "关闭",
    confirmLabel: "去充值",
    tone: "warning",
  });
  if (shouldRecharge) onNavigate(platformPaths.membership);
  return false;
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
  if (skill.code === "reminder") {
    onNavigate(platformPaths.reminders);
    return;
  }
  if (skill.code === "memory_training") {
    onNavigate(platformPaths.memoryTraining);
    return;
  }

  const conversation = await createConversation(skill.code);
  onNavigate(`${platformPaths.chat}/${conversation.id}`);
}
