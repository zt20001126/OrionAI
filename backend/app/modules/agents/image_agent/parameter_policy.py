"""从用户明确文本中提取图片尺寸和可验证的 TokenHub 参数。"""

import re
from typing import Any

from app.modules.agents.image_agent.schemas import ImageGenerationOptions

SIZE_CHOICES = {
    "1:1 方图（1024×1024）": {"size": "1024x1024"},
    "3:4 竖图（1024×1365）": {"size": "1024x1365"},
    "4:3 横图（1365×1024）": {"size": "1365x1024"},
    "16:9 横图（1536×864）": {"size": "1536x864"},
}
SIZE_QUESTION_OPTIONS = [
    {"label": label, "description": description}
    for label, description in (
        ("1:1 方图（1024×1024）", "适合商品缩略图和方形主图。"),
        ("3:4 竖图（1024×1365）", "适合竖版商品展示和手机端页面。"),
        ("4:3 横图（1365×1024）", "适合横向构图并展示商品与环境。"),
        ("16:9 横图（1536×864）", "适合宽幅场景图或横向详情图。"),
    )
]
_DIMENSION_PATTERN = re.compile(r"(?<!\d)(\d{3,5})\s*[xX×]\s*(\d{3,5})(?!\d)")


def extract_image_options(request: str) -> dict[str, Any]:
    """读取显式宽高、比例、像素档位、水印和随机种子。"""
    options: dict[str, Any] = {}
    dimension = _DIMENSION_PATTERN.search(request)
    if dimension:
        try:
            options["size"] = ImageGenerationOptions(
                size=f"{dimension.group(1)}x{dimension.group(2)}"
            ).size
        except ValueError:
            pass
    else:
        ratio_sizes = {
            "1:1": "1024x1024",
            "3:4": "1024x1365",
            "4:3": "1365x1024",
            "16:9": "1536x864",
            "9:16": "864x1536",
        }
        ratio = re.search(r"(?<!\d)(1:1|3:4|4:3|16:9|9:16)(?!\d)", request.replace("：", ":"))
        if ratio:
            options["size"] = ratio_sizes[ratio.group(1)]
        elif re.search(r"4\s*K|4k", request, re.IGNORECASE):
            options["size"] = "4096x4096"
        elif re.search(r"2\s*K|2k", request, re.IGNORECASE):
            options["generate_max_pixels"] = 4_194_304
        elif re.search(r"1\s*K|1k", request, re.IGNORECASE):
            options["generate_max_pixels"] = 1_048_576

    seed = re.search(r"\bseed\s*[:：=]?\s*(\d{1,19})\b", request, re.IGNORECASE)
    if seed and int(seed.group(1)) <= 9_223_372_036_854_775_807:
        options["seed"] = int(seed.group(1))
    footnote = re.search(r"(?:水印|脚注)(?:文字|内容)?\s*[:：]\s*([^\n，。；]{1,16})", request)
    if footnote:
        options["footnote"] = footnote.group(1).strip()
    options["use_search_tool"] = any(
        term in request for term in ("联网搜索", "外部搜索", "搜索最新")
    )
    return options


def apply_size_answer(options: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    """把已通过共享题卡校验的画幅答案转换为 TokenHub 参数。"""
    resolved = dict(options)
    size_choice = SIZE_CHOICES.get(str(answers.get("image_size", "")))
    if size_choice:
        resolved.pop("size", None)
        resolved.pop("generate_max_pixels", None)
        resolved.update(size_choice)
    return ImageGenerationOptions(**resolved).validate_exclusivity().model_dump(exclude_none=True)
