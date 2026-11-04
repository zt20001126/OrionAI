"""验证文旅洞察的 Excel 与 CSV 文件解析边界。"""

import csv
import io

from openpyxl import Workbook

from app.modules.tourism_insight.service.parsers import parse_scoring_rules, parse_ugc_csv


def _scoring_workbook() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "T6-评分大表"
    worksheet.append(
        [
            "大项",
            "分项",
            "指标编号",
            "指标名称",
            "子项序号",
            "子项名称",
            "评分口径(国标)",
            "简要说明",
            "数据源(细分)",
        ]
    )
    row = ["环境", "卫生", "A1", "公共卫生", "1", "厕所清洁", "厕所应保持干净", "卫生", "游客反馈"]
    worksheet.append(row)
    worksheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_parse_scoring_rules_keeps_full_rule_and_skips_duplicate() -> None:
    rules, skipped, errors = parse_scoring_rules(_scoring_workbook())

    assert len(rules) == 1
    assert rules[0]["subitem_name"] == "厕所清洁"
    assert skipped == 1
    assert errors == []


def test_parse_ugc_csv_skips_empty_and_merchant_replies() -> None:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["序号ID", "用户昵称", "类型", "来源", "标题", "内容", "发布时间"],
    )
    writer.writeheader()
    writer.writerow(
        {"序号ID": "1", "用户昵称": "游客", "类型": "评论", "来源": "携程", "内容": "指引清楚"}
    )
    writer.writerow({"序号ID": "2", "类型": "评论", "来源": "携程", "内容": "  "})
    writer.writerow({"序号ID": "3", "类型": "商家回复", "来源": "携程", "内容": "欢迎下次光临"})

    comments, skipped, errors = parse_ugc_csv(output.getvalue().encode("utf-8-sig"))

    assert len(comments) == 1
    assert comments[0]["content"] == "指引清楚"
    assert comments[0]["source_type"] == "csv"
    assert skipped == 2
    assert errors == []
