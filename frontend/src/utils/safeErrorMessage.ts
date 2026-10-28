const MAX_USER_FACING_MESSAGE_LENGTH = 180;
const TECHNICAL_ERROR_PATTERN = /(?:traceback|stack trace|exception|error:)/i;

/** 返回可展示给用户的简短错误信息，过滤异常堆栈和过长响应。 */
export function getSafeErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail !== "string") return fallback;

  const message = detail.trim();
  if (
    !message ||
    message.length > MAX_USER_FACING_MESSAGE_LENGTH ||
    /[\r\n]/.test(message) ||
    TECHNICAL_ERROR_PATTERN.test(message)
  ) {
    return fallback;
  }
  return message;
}
