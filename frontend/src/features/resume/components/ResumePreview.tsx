import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { documentToText, type ResumeDraft } from "../model/types";

const A4_WIDTH_PX = 794;
const A4_HEIGHT_PX = 1123;

export function ResumePreview({
  draft,
  photoUrl,
}: {
  draft: ResumeDraft;
  photoUrl: string | null;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const paperRef = useRef<HTMLElement>(null);
  const [scale, setScale] = useState(1);
  const [contentHeight, setContentHeight] = useState(A4_HEIGHT_PX);
  const { basic_info: info } = draft.content;

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const updateMeasurements = () => {
      setScale(Math.min(1, viewport.clientWidth / A4_WIDTH_PX));
      setContentHeight(Math.max(A4_HEIGHT_PX, paperRef.current?.scrollHeight ?? A4_HEIGHT_PX));
    };
    updateMeasurements();

    const observer = new ResizeObserver(updateMeasurements);
    observer.observe(viewport);
    if (paperRef.current) observer.observe(paperRef.current);
    return () => observer.disconnect();
  }, []);

  const paperHeight = contentHeight * scale;

  return (
    <aside aria-label="简历预览" className="resume-preview-panel">
      <div className="resume-preview-panel__heading">
        <h2>简历预览</h2>
        <span>A4</span>
      </div>
      <div className="resume-preview-panel__scroll">
        <div
          className="resume-paper-viewport"
          ref={viewportRef}
          style={{ height: `${paperHeight}px` }}
        >
          <article
            className="resume-paper"
            ref={paperRef}
            style={{
              color: "var(--color-text)",
              fontSize: `${draft.style_config.font_size_pt}pt`,
              lineHeight: draft.style_config.line_height,
              padding: `${draft.style_config.page_margin_mm.top}mm ${draft.style_config.page_margin_mm.right}mm ${draft.style_config.page_margin_mm.bottom}mm ${draft.style_config.page_margin_mm.left}mm`,
              transform: `scale(${scale})`,
              ["--resume-heading-color" as string]: draft.style_config.heading_color,
              ["--resume-section-spacing" as string]: `${draft.style_config.section_spacing_pt}pt`,
            }}
          >
            <header className="resume-paper__header">
              <div>
                <h1>{info.name || "你的姓名"}</h1>
                {info.intended_position && (
                  <p className="resume-paper__position">{info.intended_position}</p>
                )}
                <p>{[info.phone, info.email].filter(Boolean).join("　") || "电话 · 邮箱"}</p>
                {info.work_experience_years !== null && (
                  <p>{info.work_experience_years} 年工作经验</p>
                )}
              </div>
              {photoUrl && <img alt="证件照" src={photoUrl} />}
            </header>
            {draft.content.educations.length > 0 && (
              <PreviewSection title="教育经历">
                {draft.content.educations.map((item) => (
                  <div className="resume-paper__row" key={item.id}>
                    <strong>{item.school || "学校名称"}</strong>
                    <span>{[item.major, item.degree].filter(Boolean).join(" · ")}</span>
                    <time>
                      {item.start_month} — {item.end_month}
                    </time>
                  </div>
                ))}
              </PreviewSection>
            )}
            {documentToText(draft.content.skills).trim() && (
              <PreviewSection title="专业技能">
                {renderText(documentToText(draft.content.skills))}
              </PreviewSection>
            )}
            {draft.content.works.length > 0 && (
              <PreviewSection title="工作经历">
                {draft.content.works.map((item) => (
                  <div className="resume-paper__entry" key={item.id}>
                    <div className="resume-paper__row">
                      <strong>
                        {[item.company, item.position].filter(Boolean).join(" · ") || "公司 · 职位"}
                      </strong>
                      <time>
                        {item.start_month} — {item.end_month}
                      </time>
                    </div>
                    {renderText(documentToText(item.content))}
                  </div>
                ))}
              </PreviewSection>
            )}
            {draft.content.projects.length > 0 && (
              <PreviewSection title="项目经历">
                {draft.content.projects.map((item) => (
                  <div className="resume-paper__entry" key={item.id}>
                    <div className="resume-paper__row">
                      <strong>{item.name || "项目名称"}</strong>
                      <time>
                        {item.start_month} — {item.end_month}
                      </time>
                    </div>
                    <p>{[item.role, item.technology_stack].filter(Boolean).join(" · ")}</p>
                    {renderText(documentToText(item.content))}
                  </div>
                ))}
              </PreviewSection>
            )}
          </article>
        </div>
      </div>
    </aside>
  );
}

function PreviewSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="resume-paper__section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function renderText(text: string) {
  return text
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line, index) => <p key={`${index}-${line.slice(0, 16)}`}>{line}</p>);
}
