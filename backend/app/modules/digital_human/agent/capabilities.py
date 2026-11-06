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
        "创建提醒",
        "根据用户要求创建单次或周期提醒",
        frozenset({"create_reminder", "get_current_date", "ask_user_questions"}),
        "仅在用户明确要求创建提醒时调用 create_reminder。先提取标题、内容、重复类型、"
        "日期和时间；信息缺失或有歧义时用 ask_user_questions 追问。相对日期先调用 "
        "get_current_date。默认时区 Asia/Shanghai，用户指定时使用有效 IANA 时区。"
        "单次 once 使用 date；每天 daily、每周 weekly、每月 monthly 使用 start_date，"
        "可选 end_date；每周星期和每月日期由 start_date 决定。时间 local_time 使用 HH:MM，"
        "首次执行必须在未来。参数齐全后创建，只根据工具结果报告成功或失败。",
    ),
    DigitalHumanCapability(
        "查询提醒",
        "查询当前用户提醒列表、状态和单条详情",
        frozenset({"list_reminders", "get_reminder", "ask_user_questions"}),
        "查询提醒列表时调用 list_reminders；不传 status 表示查询全部状态，"
        "状态只能使用 active、paused、cancelled、completed。按工具返回的 total、offset、"
        "has_more 说明分页；用户要求查看全部时逐页查询，不得把未读取页面说成已列出。"
        "详情查询调用 get_reminder，reminder_id 只能来自当前用户的列表结果或用户明确提供的 ID。"
        "列表按标题查找时若有多个匹配，使用 ask_user_questions 让用户选择；"
        "未查完所有页面时不得声称没有匹配。只根据工具结果回答，不泄露或猜测其他用户数据。",
    ),
    DigitalHumanCapability(
        "互动提问", "使用题卡收集选择或文字输入", frozenset({"ask_user_questions"})
    ),
    DigitalHumanCapability(
        "图片生成",
        "根据用户的文字描述生成一张图片并展示在对话中",
        frozenset({"generate_image"}),
        "仅在用户明确要求生成图片时调用 generate_image。提示词应忠实保留用户指定的主体、"
        "场景、风格和画幅；没有明确要求时不额外询问画幅。模型使用默认图片尺寸，"
        "不传尺寸参数。生图前澄清必要信息；每轮只调用一次，成功后直接回复，"
        "失败时如实说明，不声称图片已生成。",
    ),
    DigitalHumanCapability(
        "视频生成",
        "根据用户的文字描述生成并播放视频",
        frozenset({"generate_video"}),
        "仅在用户明确要求生成视频时调用 generate_video，忠实保留画面、动作和风格。"
        "缺少必要描述时先询问，不主动要求画幅或时长。每轮只调用一次，"
        "成功后直接回复，失败时如实说明，不得声称视频已生成。",
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
        "新闻查询",
        "查询中文新闻头条和关键词资讯",
        frozenset({"get_news"}),
        "查询新闻时调用 get_news；用户问今天时设置 today_only。"
        "根据工具返回的标题、来源、北京时间和原文链接回答，不编造新闻或声称实时；"
        "无结果时说明接口返回的新闻中没有符合条件的结果，新闻数据可能延迟。",
    ),
    DigitalHumanCapability(
        "发送邮件",
        "使用项目邮箱向指定收件人发送邮件",
        frozenset({"prepare_email"}),
        "用户要求发邮件时，收集收件地址、主题和正文，用户自己的邮箱可写入正文；"
        "调用 prepare_email 生成确认题卡，必须单独调用，不得声称已发送。"
        "用户确认后的发送结果由系统提供，只依据该结果回复，不把 SMTP 接受称为送达。",
    ),
    DigitalHumanCapability(
        "A 股指数行情查询",
        "查询上证指数、深证成指、创业板指等沪深重要指数的行情",
        frozenset({"get_index_quote", "ask_user_questions"}),
        "查询指数时调用 `get_index_quote`，包括上证指数、深证成指、创业板指等；"
        "多个指数分别查询，缺少名称或代码时使用 Text 题卡询问，存在歧义时请用户确认。"
        "指数代码可能与股票代码相同，应根据用户意图区分指数和个股；意图不明确时询问。"
        "仅依据工具结果回答指数点位和涨跌幅；行情时间或延迟未知时明确说明，"
        "不称为实时行情，不把查询时间当作行情时间，不编造数据。",
    ),
    DigitalHumanCapability(
        "A 股行情查询",
        "根据股票名称或代码查询 A 股行情",
        frozenset({"get_stock_quote", "ask_user_questions"}),
        "查询单只 A 股股票行情时调用 `get_stock_quote`；缺少股票名称或代码时使用 Text 题卡询问，"
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
