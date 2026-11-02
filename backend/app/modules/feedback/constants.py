"""集中管理问题反馈限流、邮件时间和 Redis 原子操作参数。"""

from zoneinfo import ZoneInfo

FEEDBACK_RATE_LIMIT_SECONDS = 60
FEEDBACK_RATE_LIMIT_KEY_PREFIX = "orionai:feedback:rate:user"
FEEDBACK_TIMEZONE = ZoneInfo("Asia/Shanghai")
RELEASE_FEEDBACK_LIMIT_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""
