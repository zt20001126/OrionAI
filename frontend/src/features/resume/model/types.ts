export interface TextNode {
  type: "text";
  text: string;
}

export interface ParagraphNode {
  type: "paragraph";
  content: TextNode[];
}

export interface TiptapDocument {
  type: "doc";
  content: ParagraphNode[];
}

export interface BasicInfo {
  name: string;
  phone: string;
  email: string;
  intended_position: string;
  work_experience_years: number | null;
  photo_id: string | null;
}

export interface EducationItem {
  id: string;
  school: string;
  major: string;
  degree: string;
  start_month: string;
  end_month: string;
}

export interface WorkItem {
  id: string;
  company: string;
  position: string;
  start_month: string;
  end_month: string;
  content: TiptapDocument;
}

export interface ProjectItem {
  id: string;
  name: string;
  role: string;
  technology_stack: string;
  start_month: string;
  end_month: string;
  content: TiptapDocument;
}

export interface ResumeContent {
  basic_info: BasicInfo;
  educations: EducationItem[];
  skills: TiptapDocument;
  works: WorkItem[];
  projects: ProjectItem[];
}

export interface ResumeStyleConfig {
  font_size_pt: number;
  line_height: number;
  section_spacing_pt: number;
  page_margin_mm: { top: number; right: number; bottom: number; left: number };
  heading_color: string;
}

export interface ResumeResponse {
  exists: boolean;
  content: ResumeContent;
  style_config: ResumeStyleConfig;
  created_at: string | null;
  updated_at: string | null;
}

export interface ResumeDraft {
  content: ResumeContent;
  style_config: ResumeStyleConfig;
}

export type ResumeSection = "basic" | "education" | "skills" | "work" | "projects" | "style";

export const EMPTY_DOCUMENT: TiptapDocument = {
  type: "doc",
  content: [{ type: "paragraph", content: [] }],
};

export const EMPTY_RESUME: ResumeDraft = {
  content: {
    basic_info: {
      name: "",
      phone: "",
      email: "",
      intended_position: "",
      work_experience_years: null,
      photo_id: null,
    },
    educations: [],
    skills: EMPTY_DOCUMENT,
    works: [],
    projects: [],
  },
  style_config: {
    font_size_pt: 10,
    line_height: 1.4,
    section_spacing_pt: 12,
    page_margin_mm: { top: 14, right: 14, bottom: 14, left: 14 },
    heading_color: "#2563eb",
  },
};

export function documentFromText(text: string): TiptapDocument {
  const lines = text.split(/\r?\n/).slice(0, 100);
  return {
    type: "doc",
    content: lines.length
      ? lines.map((line) => ({
          type: "paragraph",
          content: line ? [{ type: "text", text: line }] : [],
        }))
      : [{ type: "paragraph", content: [] }],
  };
}

export function documentToText(document: TiptapDocument): string {
  return document.content
    .map((paragraph) => paragraph.content.map((node) => node.text).join(""))
    .join("\n");
}
