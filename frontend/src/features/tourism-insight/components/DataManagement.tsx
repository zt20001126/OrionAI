import { useRef, useState } from "react";
import {
  uploadTourismFile,
  type TourismImportResponse,
  type TourismSummary,
} from "../api/tourismInsightApi";

interface Props {
  summary: TourismSummary | null;
  onUpdated: () => void;
  confirm: (options: {
    title: string;
    description: string;
    confirmLabel?: string;
    tone?: "warning";
  }) => Promise<boolean>;
  showToast: (type: "success" | "error", message: string) => void;
}

export function DataManagement({ summary, onUpdated, confirm, showToast }: Props) {
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState<TourismImportResponse | null>(null);
  const [commentLimit, setCommentLimit] = useState(50);
  const [fileNames, setFileNames] = useState<{ rules?: string; comments?: string }>({});
  const rulesInput = useRef<HTMLInputElement>(null);
  const commentsInput = useRef<HTMLInputElement>(null);

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
      setFileNames((current) => ({ ...current, [kind]: file.name }));
      setLastResult(result);
      showToast("success", `导入 ${result.imported_count} 条，跳过 ${result.skipped_count} 条。`);
      onUpdated();
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "文件导入失败。");
    } finally {
      setBusy(false);
      if (kind === "rules" && rulesInput.current) rulesInput.current.value = "";
      if (kind === "comments" && commentsInput.current) commentsInput.current.value = "";
    }
  }

  return (
    <section className="tourism-data">
      <div className="tourism-upload-grid">
        <article className="tourism-upload">
          <div className="tourism-upload__heading">
            <span className="tourism-file-icon tourism-file-icon--excel" aria-hidden="true">
              X
            </span>
            <div>
              <h2>评分规则 (Excel)</h2>
              <p>导入景区评分指标标准（T6-评分大表）</p>
            </div>
          </div>
          <p
            className={
              summary?.rules_ready ? "tourism-upload__state tourism-ready" : "tourism-upload__state"
            }
          >
            {summary?.rules_ready
              ? `✓ 已导入${fileNames.rules ? `：${fileNames.rules}` : "评分规则"}`
              : "尚未导入评分规则"}
          </p>
          <p className="tourism-upload__meta">评分子项：{summary?.rules_count ?? "—"} 条</p>
          <input
            ref={rulesInput}
            className="tourism-file-input"
            aria-label="上传评分规则 Excel"
            accept=".xlsx"
            disabled={busy}
            onChange={(event) => void upload("rules", event.target.files?.[0])}
            type="file"
          />
          <button
            className="button button--primary"
            disabled={busy}
            onClick={() => rulesInput.current?.click()}
            type="button"
          >
            {summary?.rules_ready ? "重新上传" : "上传文件"}
          </button>
        </article>
        <article className="tourism-upload">
          <div className="tourism-upload__heading">
            <span className="tourism-file-icon tourism-file-icon--csv" aria-hidden="true">
              CSV
            </span>
            <div>
              <h2>UGC 评论 (CSV)</h2>
              <p>导入游客评论、笔记等数据</p>
            </div>
          </div>
          <p
            className={
              summary?.comments_count
                ? "tourism-upload__state tourism-ready"
                : "tourism-upload__state"
            }
          >
            {summary?.comments_count
              ? `✓ 已导入${fileNames.comments ? `：${fileNames.comments}` : "评论数据"}`
              : "尚未导入评论数据"}
          </p>
          <div className="tourism-upload__meta">
            <span>评论总数：{summary?.comments_count ?? "—"} 条</span>
            <label>
              本次导入数量{" "}
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
            </label>
          </div>
          <input
            ref={commentsInput}
            className="tourism-file-input"
            aria-label="上传 UGC 评论 CSV"
            accept=".csv,text/csv"
            disabled={busy}
            onChange={(event) => void upload("comments", event.target.files?.[0])}
            type="file"
          />
          <button
            className="button button--primary"
            disabled={busy}
            onClick={() => commentsInput.current?.click()}
            type="button"
          >
            {summary?.comments_count ? "重新上传" : "上传文件"}
          </button>
        </article>
      </div>
      <section className="tourism-overview" aria-label="数据概览">
        <h2>数据概览</h2>
        <dl className="tourism-summary">
          <div>
            <dt>评分子项</dt>
            <dd>{summary?.rules_count ?? "—"}</dd>
          </div>
          <div>
            <dt>UGC 评论</dt>
            <dd>{summary?.comments_count ?? "—"}</dd>
          </div>
          <div>
            <dt>已分析评论</dt>
            <dd>{summary?.analyzed_count ?? "—"}</dd>
          </div>
        </dl>
      </section>
      {busy && <p role="status">正在解析并保存文件…</p>}
      {lastResult && (
        <p role="status">
          最近导入：成功 {lastResult.imported_count} 条，跳过 {lastResult.skipped_count} 条，失败{" "}
          {lastResult.failed_count} 条。
        </p>
      )}
      {lastResult?.errors.map((error) => (
        <p className="tourism-error" key={error}>
          {error}
        </p>
      ))}
    </section>
  );
}
