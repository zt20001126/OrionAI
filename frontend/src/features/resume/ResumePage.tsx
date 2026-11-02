import { useEffect, useMemo, useRef, useState } from "react";

import { useToast } from "../../components/ToastProvider";
import { getSafeErrorDetail } from "../../utils/safeErrorMessage";
import { PlatformIcon } from "../platform/PlatformIcon";
import type { PlatformRoute } from "../platform/platformData";
import { ResumeAssistantPanel } from "./components/ResumeAssistantPanel";
import { ResumeEditor } from "./components/ResumeEditor";
import { ResumePreview } from "./components/ResumePreview";
import { ResumeSectionTabs } from "./components/ResumeSectionTabs";
import {
  deleteStagedResumePhoto,
  downloadResumePdf,
  getResume,
  saveResume,
  uploadResumePhoto,
} from "./resumeApi";
import {
  EMPTY_RESUME,
  type ResumeDraft,
  type ResumeResponse,
  type ResumeSection,
} from "./model/types";
import "./resume.css";
import { t } from "../../i18n/localeStore";

export function ResumePage({
  onNavigate,
  onDirtyChange,
}: {
  onNavigate: (path: PlatformRoute) => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const { confirm, showToast } = useToast();
  const [section, setSection] = useState<ResumeSection>("basic");
  const [draft, setDraft] = useState<ResumeDraft>(() => clone(EMPTY_RESUME));
  const [baseline, setBaseline] = useState(() => JSON.stringify(EMPTY_RESUME));
  const [resumeVersion, setResumeVersion] = useState<string | null>(null);
  const [exists, setExists] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [uploadedPhotoUrl, setUploadedPhotoUrl] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(
    () => !window.matchMedia("(max-width: 800px)").matches,
  );
  const [assistantConversationId, setAssistantConversationId] = useState<string | null>(null);
  const assistantToggleRef = useRef<HTMLButtonElement>(null);

  const dirty = useMemo(() => JSON.stringify(draft) !== baseline, [baseline, draft]);
  const photoPreviewUrl =
    uploadedPhotoUrl ??
    (draft.content.basic_info.photo_id
      ? `/api/resume/photo?v=${encodeURIComponent(resumeVersion ?? "saved")}`
      : null);

  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);

  useEffect(() => {
    let active = true;
    void getResume()
      .then((response) => {
        if (!active) return;
        applyLoadedResume(response, setDraft, setBaseline, setExists, setResumeVersion);
        setError(null);
      })
      .catch((requestError: unknown) => {
        if (active) setError(messageOf(requestError, t("简历暂时无法加载。")));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(
    () => () => {
      if (uploadedPhotoUrl) URL.revokeObjectURL(uploadedPhotoUrl);
    },
    [uploadedPhotoUrl],
  );

  function updateDraft(update: (current: ResumeDraft) => ResumeDraft) {
    setDraft((current) => update(current));
    setError(null);
  }

  async function saveCurrent(notifySuccess = true): Promise<boolean> {
    setError(null);
    setSaving(true);
    try {
      const response = await saveResume(draft, resumeVersion);
      applyLoadedResume(response, setDraft, setBaseline, setExists, setResumeVersion);
      setUploadedPhotoUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return null;
      });
      if (notifySuccess) showToast("success", t("简历已保存。"));
      return true;
    } catch (requestError) {
      const message = messageOf(requestError, t("简历保存失败，请稍后重试。"));
      if (message.includes("其他位置更新") || message.includes(t("其他位置更新")) || message.includes("版本冲突")) setError(message);
      else showToast("error", message);
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function handlePhotoUpload(file: File) {
    setPhotoError(null);
    if (file.size > 5 * 1024 * 1024) {
      setPhotoError(t("照片不能超过 5 MiB。"));
      return;
    }
    if (!new Set(["image/png", "image/jpeg"]).has(file.type)) {
      setPhotoError(t("请选择 PNG 或 JPEG 图片。"));
      return;
    }
    setUploading(true);
    const previousPhotoId = draft.content.basic_info.photo_id;
    if (previousPhotoId && previousPhotoId !== getPhotoId(baseline)) {
      void deleteStagedResumePhoto(previousPhotoId).catch(() => undefined);
    }
    try {
      const { photo_id: photoId } = await uploadResumePhoto(file);
      const objectUrl = URL.createObjectURL(file);
      setUploadedPhotoUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return objectUrl;
      });
      updateDraft((current) => ({
        ...current,
        content: {
          ...current.content,
          basic_info: { ...current.content.basic_info, photo_id: photoId },
        },
      }));
    } catch (requestError) {
      showToast("error", messageOf(requestError, t("照片上传失败，请稍后重试。")));
    } finally {
      setUploading(false);
    }
  }

  async function handleSave() {
    await saveCurrent();
  }

  async function handleExport() {
    if (dirty) {
      const confirmed = await confirm({
        title: t("导出前保存简历？"),
        description: t("当前简历有未保存的修改。保存成功后将继续导出 PDF。"),
        cancelLabel: t("继续编辑"),
        confirmLabel: t("保存并导出"),
        tone: "warning",
        onConfirm: () => saveCurrent(false),
      });
      if (!confirmed) return;
    }
    setExporting(true);
    try {
      await downloadResumePdf();
      showToast("success", t("PDF 已开始下载。"));
    } catch (requestError) {
      showToast("error", messageOf(requestError, t("PDF 导出失败，请稍后重试。")));
    } finally {
      setExporting(false);
    }
  }

  async function handleAssistantResumeSaved() {
    setError(null);
    try {
      const response = await getResume();
      if (dirty) {
        const useAssistantVersion = await confirm({
          title: t("简历已被助手更新"),
          description:
            t("你的本地草稿有未保存修改。载入助手版本将丢弃本地草稿；保留本地草稿后，可在之后保存并覆盖助手版本。"),
          cancelLabel: t("保留本地草稿"),
          confirmLabel: t("载入助手版本"),
          tone: "danger",
          onConfirm: () => {
            applyLoadedResume(response, setDraft, setBaseline, setExists, setResumeVersion);
            showToast("success", t("已载入助手保存的最新版本。"));
          },
        });
        if (!useAssistantVersion) {
          setResumeVersion(response.updated_at);
          showToast(
            "info",
            t("已保留本地草稿。简历助手的修改已保存；保存草稿时会以本地内容覆盖该版本。"),
          );
        }
        return;
      }
      applyLoadedResume(response, setDraft, setBaseline, setExists, setResumeVersion);
      showToast("success", t("简历助手的修改已保存，预览已同步。"));
    } catch (requestError) {
      showToast(
        "error",
        t("简历助手已完成保存，但最新版本暂时无法同步：{message}", {
          message: messageOf(requestError, t("请稍后重试。")),
        }),
      );
    }
  }

  function closeAssistant() {
    setAssistantOpen(false);
    window.requestAnimationFrame(() => assistantToggleRef.current?.focus());
  }

  async function reloadAfterConflict() {
    setLoading(true);
    try {
      const response = await getResume();
      applyLoadedResume(response, setDraft, setBaseline, setExists, setResumeVersion);
      setError(null);
    } catch (requestError) {
      showToast("error", messageOf(requestError, t("重新加载简历失败，请稍后重试。")));
    } finally {
      setLoading(false);
    }
  }

  function removePhoto() {
    const photoId = draft.content.basic_info.photo_id;
    if (photoId && photoId !== getPhotoId(baseline)) {
      void deleteStagedResumePhoto(photoId).catch(() => undefined);
    }
    if (uploadedPhotoUrl) URL.revokeObjectURL(uploadedPhotoUrl);
    setUploadedPhotoUrl(null);
    updateDraft((current) => ({
      ...current,
      content: {
        ...current.content,
        basic_info: { ...current.content.basic_info, photo_id: null },
      },
    }));
  }

  return (
    <main className="resume-page" aria-labelledby="resume-page-title">
      <header className="resume-page__header">
        <div>
          <h1 id="resume-page-title">{t("简历助手")}</h1>
          <p>{t("整理经历，实时预览并导出一份清晰的简历。")}</p>
        </div>
        <div className="resume-page__actions">
          <span aria-live="polite" className={`resume-save-state${dirty ? " is-dirty" : ""}`}>
            <span aria-hidden="true" />
            {loading
              ? t("正在加载")
              : saving
                ? t("正在保存")
                : dirty
                  ? t("有未保存的修改")
                  : exists
                    ? t("已保存")
                    : t("尚未保存")}
          </span>
          <button
            aria-expanded={assistantOpen}
            aria-label={assistantOpen ? t("收起 AI 简历助手") : t("展开 AI 简历助手")}
            className="button button--outline resume-assistant-toggle"
            onClick={() => setAssistantOpen((open) => !open)}
            ref={assistantToggleRef}
            type="button"
          >
            <PlatformIcon name="assistant" size={16} />
            {t("AI 助手")}
          </button>
          <button
            className="button button--outline resume-mobile-preview-toggle"
            onClick={() => setShowPreview((value) => !value)}
            type="button"
          >
            {showPreview ? t("返回编辑") : t("预览")}
          </button>
          <button
            className="button button--outline"
            disabled={loading || saving || uploading || exporting || !exists}
            onClick={() => void handleExport()}
            type="button"
          >
            {exporting ? t("正在导出…") : t("导出 PDF")}
          </button>
          <button
            className="button button--primary"
            disabled={loading || saving || uploading || exporting || !dirty}
            onClick={() => void handleSave()}
            type="button"
          >
            {saving ? t("保存中…") : t("保存简历")}
          </button>
        </div>
      </header>

      {error && (
        <div className="resume-alert" role="alert">
          <span>{error}</span>
          {(error.includes("其他位置更新") || error.includes(t("其他位置更新"))) && (
            <button
              className="resume-text-button"
              onClick={() => void reloadAfterConflict()}
              type="button"
            >
              {t("重新加载最新版本")}
            </button>
          )}
          <button
            aria-label={t("关闭错误提示")}
            className="resume-alert__close"
            onClick={() => setError(null)}
            type="button"
          >
            ×
          </button>
        </div>
      )}
      <ResumeSectionTabs
        active={section}
        onChange={(next) => {
          setSection(next);
          setShowPreview(false);
        }}
      />

      <div
        className={`resume-workbench${assistantOpen ? " has-assistant-open" : " is-assistant-collapsed"}${showPreview ? " is-previewing" : ""}`}
      >
        <div className="resume-workbench__editor">
          {loading ? (
            <div className="resume-workbench__loading" role="status">
              {t("正在读取已保存简历…")}
            </div>
          ) : (
            <ResumeEditor
              draft={draft}
              disabled={saving || uploading}
              onPhotoUpload={(file) => void handlePhotoUpload(file)}
              onRemovePhoto={removePhoto}
              onUpdate={updateDraft}
              photoError={photoError}
              photoPreviewUrl={photoPreviewUrl}
              section={section}
            />
          )}
        </div>
        <ResumePreview draft={draft} photoUrl={photoPreviewUrl} />
        <ResumeAssistantPanel
          conversationId={assistantConversationId}
          isOpen={assistantOpen}
          onCollapse={closeAssistant}
          onConversationIdChange={setAssistantConversationId}
          onNavigate={onNavigate}
          onResumeSaved={handleAssistantResumeSaved}
        />
      </div>
    </main>
  );
}

function applyLoadedResume(
  response: ResumeResponse,
  setDraft: (draft: ResumeDraft) => void,
  setBaseline: (baseline: string) => void,
  setExists: (exists: boolean) => void,
  setVersion: (version: string | null) => void,
) {
  const next = { content: response.content, style_config: response.style_config };
  setDraft(next);
  setBaseline(JSON.stringify(next));
  setExists(response.exists);
  setVersion(response.updated_at);
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function getPhotoId(baseline: string): string | null {
  try {
    const value = JSON.parse(baseline) as ResumeDraft;
    return value.content.basic_info.photo_id;
  } catch {
    return null;
  }
}

function messageOf(error: unknown, fallback: string): string {
  if (error instanceof TypeError) return t("网络连接异常，请检查网络后重试。");
  if (!(error instanceof Error)) return fallback;
  return getSafeErrorDetail(error.message, fallback);
}
