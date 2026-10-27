"""把已校验简历转换为可下载的 A4 PDF。"""

import base64
import logging
import threading
from html import escape

from app.modules.resume.errors import ResumePdfError
from app.modules.resume.schemas import ResumeContent, ResumeStyleConfig, document_text

logger = logging.getLogger(__name__)
_RENDER_SEMAPHORE = threading.BoundedSemaphore(2)


class PlaywrightResumePdfRenderer:
    """使用本地 Chromium 渲染静态模板，不加载用户提供的远程资源。"""

    def render(
        self,
        content: ResumeContent,
        style: ResumeStyleConfig,
        *,
        photo: tuple[bytes, str] | None = None,
    ) -> bytes:
        if not _RENDER_SEMAPHORE.acquire(timeout=10):
            raise ResumePdfError from None
        try:
            from playwright.sync_api import sync_playwright

            html = _resume_html(content, style, photo)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(args=["--no-sandbox"])
                try:
                    page = browser.new_page()
                    page.set_content(html, wait_until="load", timeout=10_000)
                    return page.pdf(
                        format="A4",
                        print_background=True,
                        margin={
                            "top": f"{style.page_margin_mm.top}mm",
                            "right": f"{style.page_margin_mm.right}mm",
                            "bottom": f"{style.page_margin_mm.bottom}mm",
                            "left": f"{style.page_margin_mm.left}mm",
                        },
                    )
                finally:
                    browser.close()
        except Exception as error:
            logger.warning("resume_pdf_render_failed error_type=%s", type(error).__name__)
            raise ResumePdfError from None
        finally:
            _RENDER_SEMAPHORE.release()


def _resume_html(
    content: ResumeContent,
    style: ResumeStyleConfig,
    photo: tuple[bytes, str] | None,
) -> str:
    info = content.basic_info
    photo_html = ""
    if photo:
        data, mime_type = photo
        encoded = base64.b64encode(data).decode("ascii")
        photo_html = f'<img class="photo" src="data:{mime_type};base64,{encoded}" alt="证件照">'
    experience_years_html = ""
    if info.work_experience_years is not None:
        experience_years_html = f"<p>{info.work_experience_years} 年工作经验</p>"

    sections: list[str] = []
    if content.educations:
        items = "".join(
            f"<li><strong>{escape(item.school)}</strong>　{escape(item.major)}　"
            f"{escape(item.degree)}"
            f"<span>{escape(item.start_month)} – {escape(item.end_month)}</span></li>"
            for item in content.educations
        )
        sections.append(_section("教育经历", f"<ul>{items}</ul>"))
    if document_text(content.skills).strip():
        sections.append(_section("专业技能", _paragraphs(document_text(content.skills))))
    if content.works:
        items = "".join(
            f'<article><div class="entry-head"><strong>{escape(item.company)} · '
            f"{escape(item.position)}</strong><span>{escape(item.start_month)} – "
            f"{escape(item.end_month)}</span></div>{_paragraphs(document_text(item.content))}</article>"
            for item in content.works
        )
        sections.append(_section("工作经历", items))
    if content.projects:
        items = "".join(
            f'<article><div class="entry-head"><strong>{escape(item.name)}</strong>'
            f"<span>{escape(item.start_month)} – {escape(item.end_month)}</span></div>"
            f"<p>{_project_details(item.role, item.technology_stack)}</p>"
            f"{_paragraphs(document_text(item.content))}</article>"
            for item in content.projects
        )
        sections.append(_section("项目经历", items))

    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<style>
  @page {{ size: A4; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    color: #1f2937;
    font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
    font-size: {style.font_size_pt}pt;
    line-height: {style.line_height};
  }}
  h1 {{ margin: 0 0 4px; font-size: 1.8em; color: {style.heading_color}; }}
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 2px solid {style.heading_color};
    padding-bottom: 12px;
  }}
  .sub {{ color: #475569; }}
  .photo {{ width: 58px; height: 74px; object-fit: cover; }}
  h2 {{
    color: {style.heading_color};
    font-size: 1.2em;
    border-bottom: 1px solid #dbe2ea;
    padding-bottom: 3px;
    margin: {style.section_spacing_pt}pt 0 6pt;
  }}
  ul {{ margin: 0; padding: 0; list-style: none; }}
  li, .entry-head {{
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }}
  li {{ padding: 3px 0; }}
  li span, .entry-head span {{ color: #64748b; white-space: nowrap; }}
  article {{ margin: 0 0 8pt; }}
  article p {{ margin: 3px 0; color: #475569; }}
  .body p {{ margin: 3px 0; white-space: pre-wrap; }}
</style>
<body>
  <header class="header">
    <div>
      <h1>{escape(info.name)}</h1>
      <div class="sub">{escape(info.intended_position)}</div>
      <p>{escape(info.phone)}　{escape(info.email)}</p>
      {experience_years_html}
    </div>
    {photo_html}
  </header>
  {"".join(sections)}
</body>
</html>"""


def _section(title: str, body: str) -> str:
    return f'<section><h2>{title}</h2><div class="body">{body}</div></section>'


def _paragraphs(text: str) -> str:
    return "".join(f"<p>{escape(line)}</p>" for line in text.splitlines() if line.strip())


def _project_details(role: str, technology_stack: str) -> str:
    return escape(" · ".join(value for value in (role, technology_stack) if value))
