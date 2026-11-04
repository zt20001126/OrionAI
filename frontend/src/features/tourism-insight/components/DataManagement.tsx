import { useState } from "react";

import { uploadTourismFile, type TourismImportResponse, type TourismSummary } from "../api/tourismInsightApi";

interface DataManagementProps {
  summary: TourismSummary | null;
  onUpdated: () => void;
  confirm: (options: { title: string; description: string; confirmLabel?: string; tone?: "warning" }) => Promise<boolean>;
  showToast: (type: "success" | "error", message: string) => void;
}

/** 文旅数据管理页的文件导入控件与结果摘要。 */
export function DataManagement({ summary, onUpdated, confirm, showToast }: DataManagementProps) {
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState<TourismImportResponse | null>(null);
  const [commentLimit, setCommentLimit] = useState(50);

  async function upload(kind: "rules" | "comments", file?: File) {
    if (!file) return;
    let replace = false;
    if (kind === "rules" && (summary?.rules_count ?? 0) > 0) {
      replace = await confirm({
        title: "替换当前评分规则？",
        description: "成功导入后将清空旧匹配结果，保留评论。你可以按新规则重新分析。",
        confirmLabel: "替换规则",
        tone: "warning",
      });
      if (!replace) return;
    }
    setBusy(true);
    try {
      const result = await uploadTourismFile(kind, file, { replace, limit: commentLimit });
      setLastResult(result);
      showToast("success", `导入 ${result.imported_count} 条，跳过 ${result.skipped_count} 条。`);
      onUpdated();
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "文件导入失败。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="tourism-data">
      <div className="tourism-upload-grid">
        <label className="tourism-upload">
          <strong>评分规则 Excel</strong>
          <span>读取 T6-评分大表，支持 .xlsx</span>
          <input accept=".xlsx" disabled={busy} onChange={(event) => void upload("rules", event.target.files?.[0])} type="file" />
        </label>
        <label className="tourism-upload">
          <strong>UGC 评论 CSV</strong>
          <span>选择本次导入的有效评论数量，上限 100 条</span>
          <input
            aria-label="本次导入评论数量"
            className="tourism-limit-input"
            disabled={busy}
            max={100}
            min={1}
            onChange={(event) => setCommentLimit(Number(event.target.value))}
            type="number"
            value={commentLimit}
          />
          <input accept=".csv,text/csv" disabled={busy} onChange={(event) => void upload("comments", event.target.files?.[0])} type="file" />
        </label>
      </div>
      <dl className="tourism-summary">
        <div><dt>评分子项</dt><dd>{summary?.rules_count ?? "—"}</dd></div>
        <div><dt>UGC 评论</dt><dd>{summary?.comments_count ?? "—"}</dd></div>
        <div><dt>已分析评论</dt><dd>{summary?.analyzed_count ?? "—"}</dd></div>
      </dl>
      {busy && <p role="status">正在解析并保存文件…</p>}
      {lastResult && <p role="status">最近导入：成功 {lastResult.imported_count} 条，跳过 {lastResult.skipped_count} 条，失败 {lastResult.failed_count} 条。</p>}
      {lastResult?.errors.map((error) => <p className="tourism-error" key={error}>{error}</p>)}
    </section>
  );
}
