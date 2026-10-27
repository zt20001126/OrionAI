import type { ResumeSection } from "../model/types";

const SECTIONS: { id: ResumeSection; label: string }[] = [
  { id: "basic", label: "基本信息" },
  { id: "education", label: "教育经历" },
  { id: "skills", label: "专业技能" },
  { id: "work", label: "工作经历" },
  { id: "projects", label: "项目经历" },
  { id: "style", label: "排版设置" },
];

export function ResumeSectionTabs({
  active,
  onChange,
}: {
  active: ResumeSection;
  onChange: (section: ResumeSection) => void;
}) {
  return (
    <nav aria-label="简历章节" className="resume-tabs">
      {SECTIONS.map((section) => (
        <button
          aria-current={active === section.id ? "step" : undefined}
          className={`resume-tabs__item${active === section.id ? " is-active" : ""}`}
          key={section.id}
          onClick={() => onChange(section.id)}
          type="button"
        >
          {section.label}
        </button>
      ))}
    </nav>
  );
}
