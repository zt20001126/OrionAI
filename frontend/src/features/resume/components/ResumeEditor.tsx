import type {
  EducationItem,
  ProjectItem,
  ResumeDraft,
  ResumeSection,
  WorkItem,
} from "../model/types";
import { documentFromText } from "../model/types";
import { ResumeParagraphEditor } from "./ResumeParagraphEditor";

type UpdateDraft = (update: (current: ResumeDraft) => ResumeDraft) => void;

export function ResumeEditor({
  draft,
  section,
  disabled,
  photoPreviewUrl,
  onUpdate,
  onPhotoUpload,
  onRemovePhoto,
  photoError,
}: {
  draft: ResumeDraft;
  section: ResumeSection;
  disabled: boolean;
  photoPreviewUrl: string | null;
  onUpdate: UpdateDraft;
  onPhotoUpload: (file: File) => void;
  onRemovePhoto: () => void;
  photoError: string | null;
}) {
  const info = draft.content.basic_info;

  function updateBasic<K extends keyof typeof info>(field: K, value: (typeof info)[K]) {
    onUpdate((current) => ({
      ...current,
      content: {
        ...current.content,
        basic_info: { ...current.content.basic_info, [field]: value },
      },
    }));
  }

  if (section === "basic") {
    return (
      <section aria-labelledby="resume-editor-title" className="resume-editor">
        <h2 id="resume-editor-title">基本信息</h2>
        <div className="resume-form-grid">
          <Field
            disabled={disabled}
            label="姓名"
            required
            value={info.name}
            onChange={(value) => updateBasic("name", value)}
          />
          <Field
            disabled={disabled}
            label="电话"
            required
            value={info.phone}
            onChange={(value) => updateBasic("phone", value)}
          />
          <Field
            disabled={disabled}
            label="邮箱"
            required
            type="email"
            value={info.email}
            onChange={(value) => updateBasic("email", value)}
          />
          <Field
            disabled={disabled}
            label="求职意向"
            value={info.intended_position}
            onChange={(value) => updateBasic("intended_position", value)}
          />
          <label className="resume-field">
            <span>工作年限</span>
            <input
              className="form-input"
              disabled={disabled}
              max={80}
              min={0}
              onChange={(event) =>
                updateBasic(
                  "work_experience_years",
                  event.target.value ? Number(event.target.value) : null,
                )
              }
              type="number"
              value={info.work_experience_years ?? ""}
            />
          </label>
          <div className="resume-field resume-photo-field">
            <span>证件照</span>
            <div className="resume-photo-field__row">
              {photoPreviewUrl ? (
                <img alt="简历证件照预览" src={photoPreviewUrl} />
              ) : (
                <span className="resume-photo-placeholder">未添加</span>
              )}
              <label className="button button--outline resume-photo-upload">
                上传照片
                <input
                  accept="image/png,image/jpeg"
                  disabled={disabled}
                  onChange={(event) => {
                    const file = event.currentTarget.files?.[0];
                    if (file) onPhotoUpload(file);
                    event.currentTarget.value = "";
                  }}
                  type="file"
                />
              </label>
              {info.photo_id && (
                <button
                  className="button button--outline"
                  disabled={disabled}
                  onClick={onRemovePhoto}
                  type="button"
                >
                  移除
                </button>
              )}
            </div>
            <small>支持 PNG 或 JPEG，最大 5 MiB。</small>
            {photoError && (
              <small className="resume-error-text" role="alert">
                {photoError}
              </small>
            )}
          </div>
        </div>
      </section>
    );
  }

  if (section === "education") {
    const items = draft.content.educations;
    return (
      <section aria-labelledby="resume-editor-title" className="resume-editor">
        <EditorHeading
          title="教育经历"
          action="添加教育经历"
          onAction={() =>
            onUpdate((current) => ({
              ...current,
              content: {
                ...current.content,
                educations: [
                  ...current.content.educations,
                  {
                    id: crypto.randomUUID(),
                    school: "",
                    major: "",
                    degree: "",
                    start_month: "2020-09",
                    end_month: "2024-06",
                  },
                ],
              },
            }))
          }
        />
        {items.length === 0 ? (
          <EmptySection text="还没有填写教育经历。" />
        ) : (
          items.map((item, index) => (
            <EducationForm
              key={item.id}
              item={item}
              disabled={disabled}
              onChange={(next) => updateItem(onUpdate, "educations", index, next)}
              onMove={(direction) => moveItem(onUpdate, "educations", index, direction)}
              onRemove={() => removeItem(onUpdate, "educations", index)}
              index={index}
              length={items.length}
            />
          ))
        )}
      </section>
    );
  }

  if (section === "skills") {
    return (
      <section aria-labelledby="resume-editor-title" className="resume-editor">
        <h2 id="resume-editor-title">专业技能</h2>
        <p className="resume-editor__intro">按主题或熟练度分行填写，预览会保持相同段落顺序。</p>
        <ResumeParagraphEditor
          disabled={disabled}
          label="技能内容"
          onChange={(skills) =>
            onUpdate((current) => ({ ...current, content: { ...current.content, skills } }))
          }
          value={draft.content.skills}
        />
      </section>
    );
  }

  if (section === "work") {
    const items = draft.content.works;
    return (
      <section aria-labelledby="resume-editor-title" className="resume-editor">
        <EditorHeading
          title="工作经历"
          action="添加工作经历"
          onAction={() =>
            onUpdate((current) => ({
              ...current,
              content: {
                ...current.content,
                works: [
                  ...current.content.works,
                  {
                    id: crypto.randomUUID(),
                    company: "",
                    position: "",
                    start_month: "2022-01",
                    end_month: "2024-01",
                    content: documentFromText(""),
                  },
                ],
              },
            }))
          }
        />
        {items.length === 0 ? (
          <EmptySection text="还没有填写工作经历。" />
        ) : (
          items.map((item, index) => (
            <ExperienceForm
              key={item.id}
              item={item}
              kind="work"
              disabled={disabled}
              onChange={(next) => updateItem(onUpdate, "works", index, next)}
              onMove={(direction) => moveItem(onUpdate, "works", index, direction)}
              onRemove={() => removeItem(onUpdate, "works", index)}
              index={index}
              length={items.length}
            />
          ))
        )}
      </section>
    );
  }

  if (section === "projects") {
    const items = draft.content.projects;
    return (
      <section aria-labelledby="resume-editor-title" className="resume-editor">
        <EditorHeading
          title="项目经历"
          action="添加项目经历"
          onAction={() =>
            onUpdate((current) => ({
              ...current,
              content: {
                ...current.content,
                projects: [
                  ...current.content.projects,
                  {
                    id: crypto.randomUUID(),
                    name: "",
                    role: "",
                    technology_stack: "",
                    start_month: "2022-01",
                    end_month: "2024-01",
                    content: documentFromText(""),
                  },
                ],
              },
            }))
          }
        />
        {items.length === 0 ? (
          <EmptySection text="还没有填写项目经历。" />
        ) : (
          items.map((item, index) => (
            <ExperienceForm
              key={item.id}
              item={item}
              kind="project"
              disabled={disabled}
              onChange={(next) => updateItem(onUpdate, "projects", index, next)}
              onMove={(direction) => moveItem(onUpdate, "projects", index, direction)}
              onRemove={() => removeItem(onUpdate, "projects", index)}
              index={index}
              length={items.length}
            />
          ))
        )}
      </section>
    );
  }

  return (
    <section aria-labelledby="resume-editor-title" className="resume-editor">
      <h2 id="resume-editor-title">排版设置</h2>
      <div className="resume-form-grid">
        <label className="resume-field">
          <span>正文字号（磅）</span>
          <input
            className="form-input"
            disabled={disabled}
            max={14}
            min={8}
            onChange={(event) =>
              onUpdate((current) => ({
                ...current,
                style_config: { ...current.style_config, font_size_pt: Number(event.target.value) },
              }))
            }
            type="number"
            value={draft.style_config.font_size_pt}
          />
        </label>
        <label className="resume-field">
          <span>行距</span>
          <input
            className="form-input"
            disabled={disabled}
            max={2}
            min={1}
            onChange={(event) =>
              onUpdate((current) => ({
                ...current,
                style_config: { ...current.style_config, line_height: Number(event.target.value) },
              }))
            }
            step={0.1}
            type="number"
            value={draft.style_config.line_height}
          />
        </label>
        <label className="resume-field">
          <span>章节间距（磅）</span>
          <input
            className="form-input"
            disabled={disabled}
            max={24}
            min={4}
            onChange={(event) =>
              onUpdate((current) => ({
                ...current,
                style_config: {
                  ...current.style_config,
                  section_spacing_pt: Number(event.target.value),
                },
              }))
            }
            type="number"
            value={draft.style_config.section_spacing_pt}
          />
        </label>
        <label className="resume-field">
          <span>页边距（毫米）</span>
          <input
            className="form-input"
            disabled={disabled}
            max={30}
            min={5}
            onChange={(event) => {
              const margin = Number(event.target.value);
              onUpdate((current) => ({
                ...current,
                style_config: {
                  ...current.style_config,
                  page_margin_mm: { top: margin, right: margin, bottom: margin, left: margin },
                },
              }));
            }}
            type="number"
            value={draft.style_config.page_margin_mm.top}
          />
        </label>
        <label className="resume-field">
          <span>标题颜色</span>
          <input
            className="resume-color-input"
            disabled={disabled}
            onChange={(event) =>
              onUpdate((current) => ({
                ...current,
                style_config: { ...current.style_config, heading_color: event.target.value },
              }))
            }
            type="color"
            value={draft.style_config.heading_color}
          />
        </label>
      </div>
      <p className="resume-editor__intro">调整后可在右侧预览中即时查看排版效果。</p>
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  required = false,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  disabled?: boolean;
}) {
  return (
    <label className="resume-field">
      <span>
        {label}
        {required && <em>必填</em>}
      </span>
      <input
        className="form-input"
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        type={type}
        value={value}
      />
    </label>
  );
}

function EditorHeading({
  title,
  action,
  onAction,
}: {
  title: string;
  action: string;
  onAction: () => void;
}) {
  return (
    <header className="resume-editor__heading">
      <h2 id="resume-editor-title">{title}</h2>
      <button className="button button--outline" onClick={onAction} type="button">
        + {action}
      </button>
    </header>
  );
}

function EmptySection({ text }: { text: string }) {
  return <p className="resume-empty-section">{text}</p>;
}

function EducationForm({
  item,
  disabled,
  onChange,
  onMove,
  onRemove,
  index,
  length,
}: {
  item: EducationItem;
  disabled: boolean;
  onChange: (item: EducationItem) => void;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
  index: number;
  length: number;
}) {
  return (
    <article className="resume-entry-editor">
      <EntryActions
        index={index}
        length={length}
        onMove={onMove}
        onRemove={onRemove}
        disabled={disabled}
      />
      <div className="resume-form-grid">
        <Field
          disabled={disabled}
          label="学校"
          required
          value={item.school}
          onChange={(school) => onChange({ ...item, school })}
        />
        <Field
          disabled={disabled}
          label="专业"
          value={item.major}
          onChange={(major) => onChange({ ...item, major })}
        />
        <Field
          disabled={disabled}
          label="学历 / 学位"
          value={item.degree}
          onChange={(degree) => onChange({ ...item, degree })}
        />
        <MonthField
          disabled={disabled}
          label="开始月份"
          value={item.start_month}
          onChange={(start_month) => onChange({ ...item, start_month })}
        />
        <MonthField
          disabled={disabled}
          label="结束月份"
          value={item.end_month}
          onChange={(end_month) => onChange({ ...item, end_month })}
        />
      </div>
    </article>
  );
}

function ExperienceForm({
  item,
  kind,
  disabled,
  onChange,
  onMove,
  onRemove,
  index,
  length,
}: {
  item: WorkItem | ProjectItem;
  kind: "work" | "project";
  disabled: boolean;
  onChange: (item: WorkItem | ProjectItem) => void;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
  index: number;
  length: number;
}) {
  const isWork = kind === "work";
  return (
    <article className="resume-entry-editor">
      <EntryActions
        index={index}
        length={length}
        onMove={onMove}
        onRemove={onRemove}
        disabled={disabled}
      />
      <div className="resume-form-grid">
        <Field
          disabled={disabled}
          label={isWork ? "公司" : "项目名称"}
          required
          value={isWork ? (item as WorkItem).company : (item as ProjectItem).name}
          onChange={(value) =>
            onChange(
              isWork
                ? { ...(item as WorkItem), company: value }
                : { ...(item as ProjectItem), name: value },
            )
          }
        />
        <Field
          disabled={disabled}
          label={isWork ? "职位" : "项目角色"}
          required={isWork}
          value={isWork ? (item as WorkItem).position : (item as ProjectItem).role}
          onChange={(value) =>
            onChange(
              isWork
                ? { ...(item as WorkItem), position: value }
                : { ...(item as ProjectItem), role: value },
            )
          }
        />
        {!isWork && (
          <Field
            disabled={disabled}
            label="技术栈"
            value={(item as ProjectItem).technology_stack}
            onChange={(technology_stack) =>
              onChange({ ...(item as ProjectItem), technology_stack })
            }
          />
        )}
        <MonthField
          disabled={disabled}
          label="开始月份"
          value={item.start_month}
          onChange={(start_month) => onChange({ ...item, start_month })}
        />
        <MonthField
          disabled={disabled}
          label="结束月份"
          value={item.end_month}
          onChange={(end_month) => onChange({ ...item, end_month })}
        />
        <ResumeParagraphEditor
          disabled={disabled}
          label="工作内容"
          value={item.content}
          onChange={(content) => onChange({ ...item, content })}
        />
      </div>
    </article>
  );
}

function MonthField({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  return (
    <label className="resume-field">
      <span>{label}</span>
      <input
        className="form-input"
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        type="month"
        value={value}
      />
    </label>
  );
}

function EntryActions({
  index,
  length,
  onMove,
  onRemove,
  disabled,
}: {
  index: number;
  length: number;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
  disabled: boolean;
}) {
  return (
    <div className="resume-entry-actions">
      <span>条目 {index + 1}</span>
      <button
        aria-label="上移条目"
        className="resume-text-button"
        disabled={disabled || index === 0}
        onClick={() => onMove(-1)}
        type="button"
      >
        上移
      </button>
      <button
        aria-label="下移条目"
        className="resume-text-button"
        disabled={disabled || index === length - 1}
        onClick={() => onMove(1)}
        type="button"
      >
        下移
      </button>
      <button
        className="resume-text-button resume-text-button--danger"
        disabled={disabled}
        onClick={onRemove}
        type="button"
      >
        删除
      </button>
    </div>
  );
}

function updateItem<
  K extends "educations" | "works" | "projects",
  T extends EducationItem | WorkItem | ProjectItem,
>(update: UpdateDraft, field: K, index: number, item: T) {
  update((current) => {
    const items = [...current.content[field]] as T[];
    items[index] = item;
    return { ...current, content: { ...current.content, [field]: items } };
  });
}

function removeItem(
  update: UpdateDraft,
  field: "educations" | "works" | "projects",
  index: number,
) {
  update((current) => ({
    ...current,
    content: {
      ...current.content,
      [field]: current.content[field].filter((_, itemIndex) => itemIndex !== index),
    },
  }));
}

function moveItem(
  update: UpdateDraft,
  field: "educations" | "works" | "projects",
  index: number,
  direction: -1 | 1,
) {
  update((current) => {
    const items = [...current.content[field]];
    const target = index + direction;
    if (target < 0 || target >= items.length) return current;
    [items[index], items[target]] = [items[target], items[index]];
    return { ...current, content: { ...current.content, [field]: items } };
  });
}
