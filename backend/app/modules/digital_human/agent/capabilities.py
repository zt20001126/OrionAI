"""维护数字人的用户能力及其工具依赖，供图构造提示词使用。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DigitalHumanCapability:
    """描述一项用户能力、所需工具和相关调用规则。"""

    name: str
    description: str
    required_tools: frozenset[str] = frozenset()
    instructions: str = ""


DIGITAL_HUMAN_CAPABILITIES = (
    DigitalHumanCapability("日常交流", "聊天、回答问题、写作和整理想法"),
    DigitalHumanCapability(
        "互动提问", "使用题卡收集选择或文字输入", frozenset({"ask_user_questions"})
    ),
    DigitalHumanCapability(
        "日期查询",
        "查询北京时间的日期和星期",
        frozenset({"get_current_date"}),
        "回答依赖当前日期的问题时，先调用 `get_current_date` 获取北京时间，不要猜测日期；"
        "与当前日期无关的问题无需调用。",
    ),
    DigitalHumanCapability(
        "天气查询",
        "根据地点查询当前天气",
        frozenset({"get_current_date", "get_current_weather", "ask_user_questions"}),
        "查询当前天气时，先单独调用 `get_current_date`；缺少所在地时，调用 "
        "`ask_user_questions` 的 Text 题卡询问城市及必要的省份或国家，等待答复后调用 "
        "`get_current_weather`。地点有歧义时用 Text 题卡请用户确认。根据天气工具返回的"
        "当地时间和数据作答，不编造天气或把北京时间当作所在地时间。",
    ),
    DigitalHumanCapability(
        "A 股行情查询",
        "根据股票名称或代码查询 A 股行情",
        frozenset({"get_stock_quote", "ask_user_questions"}),
        "查询 A 股行情时调用 `get_stock_quote`；缺少股票名称或代码时使用 Text 题卡询问，"
        "多个候选时列出候选并请用户确认代码。仅依据工具结果回答价格、涨跌幅、币种和行情时间；"
        "时间或延迟未知时明确说明，不称为实时行情，不把查询时间当作行情时间，"
        "不推断停牌或编造价格。",
    ),
)


def build_capabilities_prompt(registered_tool_names: frozenset[str]) -> str:
    """按已注册工具生成能力说明；输入工具名称集合，输出提示词；调用方：数字人图。"""
    available = [
        capability
        for capability in DIGITAL_HUMAN_CAPABILITIES
        if capability.required_tools <= registered_tool_names
    ]
    descriptions = "\n".join(
        f"- {capability.name}：{capability.description}。" for capability in available
    )
    instructions = "\n".join(
        f"- {capability.instructions}" for capability in available if capability.instructions
    )
    prompt = (
        "## 当前可用能力\n\n"
        "用户询问能力时，根据以下清单简洁介绍，不声称具备清单之外的能力；"
        "工具运行失败时如实说明。\n\n"
        f"{descriptions}"
    )
    if instructions:
        prompt += f"\n\n## 能力使用规则\n\n{instructions}"
    return prompt
