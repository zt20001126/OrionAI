import { useCallback, useEffect, useState } from "react";

import { analyzeTourismComments, listTourismComments, type TourismComment, type TourismSummary } from "../api/tourismInsightApi";

interface CommentAnalysisProps {
  summary: TourismSummary | null;
  onResults: () => void;
  showToast: (type: "success" | "error", message: string) => void;
}

/** 提供评论分页、多选和批量分析操作。 */
export function CommentAnalysis({ summary, onResults, showToast }: CommentAnalysisProps) {
  const [items, setItems] = useState<TourismComment[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (nextOffset = 0) => {
    try {
      const page = await listTourismComments(nextOffset);
      setItems(page.items);
      setTotal(page.total_count);
      setOffset(page.offset);
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "评论列表加载失败。");
    }
  }, [showToast]);
  useEffect(() => {
    let active = true;
    void listTourismComments(0).then((page) => {
      if (!active) return;
      setItems(page.items);
      setTotal(page.total_count);
      setOffset(page.offset);
    }).catch((error: unknown) => {
      if (active) showToast("error", error instanceof Error ? error.message : "评论列表加载失败。");
    });
    return () => { active = false; };
  }, [showToast]);

  async function analyze() {
    setBusy(true);
    try {
      const result = await analyzeTourismComments(Array.from(selected));
      const failed = result.items.filter((item) => item.status === "failed").length;
      showToast(failed ? "error" : "success", failed ? `${failed} 条评论分析失败。` : "所选评论分析完成。");
      setSelected(new Set());
      await load();
      onResults();
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "评论分析失败。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="tourism-analysis">
      {!summary?.rules_ready && <p className="tourism-notice" role="status">请先在“数据管理”导入评分规则。</p>}
      <div className="tourism-analysis__actions">
        <span>已选 {selected.size} 条（每批最多 10 条）</span>
        <button className="button button--primary" disabled={!summary?.rules_ready || !selected.size || selected.size > 10 || busy} onClick={() => void analyze()}>
          {busy ? "分析中…" : "分析所选评论"}
        </button>
      </div>
      {items.length ? <div className="tourism-comment-list">{items.map((comment) => (
        <label className="tourism-comment" key={comment.id}>
          <input checked={selected.has(comment.id)} disabled={!summary?.rules_ready || busy} onChange={() => setSelected((current) => {
            const next = new Set(current);
            if (next.has(comment.id)) next.delete(comment.id);
            else next.add(comment.id);
            return next;
          })} type="checkbox" />
          <span className="tourism-comment__body">
            <span className="tourism-comment__meta">{comment.nickname || "游客"} · {comment.platform || "未知来源"} · {comment.analyzed ? "已分析" : "未分析"}</span>
            {comment.title && <strong>{comment.title}</strong>}
            <span>{comment.content}</span>
          </span>
        </label>
      ))}</div> : <p className="tourism-empty">尚无评论，可在“数据管理”导入 CSV，或直接在对话框输入评价。</p>}
      <div className="tourism-pagination">
        <button className="button button--outline" disabled={offset === 0} onClick={() => void load(Math.max(0, offset - 20))}>上一页</button>
        <span>{total ? `${offset + 1}–${Math.min(offset + items.length, total)} / ${total}` : "0 条"}</span>
        <button className="button button--outline" disabled={offset + items.length >= total} onClick={() => void load(offset + 20)}>下一页</button>
      </div>
    </section>
  );
}
