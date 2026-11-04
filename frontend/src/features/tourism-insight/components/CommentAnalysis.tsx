import { useCallback, useEffect, useState } from "react";

import {
  analyzeTourismComments,
  listTourismComments,
  type TourismComment,
  type TourismSummary,
} from "../api/tourismInsightApi";

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
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState("");
  const [status, setStatus] = useState("");
  const visibleItems = items.filter(
    (item) =>
      (!query ||
        `${item.content} ${item.nickname ?? ""}`.toLowerCase().includes(query.toLowerCase())) &&
      (!platform || (item.platform ?? "") === platform) &&
      (!status || (status === "analyzed") === item.analyzed),
  );
  const platforms = [
    ...new Set(
      items.map((item) => item.platform).filter((value): value is string => Boolean(value)),
    ),
  ];

  const load = useCallback(
    async (nextOffset = 0) => {
      try {
        const page = await listTourismComments(nextOffset);
        setItems(page.items);
        setTotal(page.total_count);
        setOffset(page.offset);
      } catch (error) {
        showToast("error", error instanceof Error ? error.message : "评论列表加载失败。");
      }
    },
    [showToast],
  );
  useEffect(() => {
    let active = true;
    void listTourismComments(0)
      .then((page) => {
        if (!active) return;
        setItems(page.items);
        setTotal(page.total_count);
        setOffset(page.offset);
      })
      .catch((error: unknown) => {
        if (active)
          showToast("error", error instanceof Error ? error.message : "评论列表加载失败。");
      });
    return () => {
      active = false;
    };
  }, [showToast]);

  async function analyze() {
    setBusy(true);
    try {
      const result = await analyzeTourismComments(Array.from(selected));
      const failed = result.items.filter((item) => item.status === "failed").length;
      showToast(
        failed ? "error" : "success",
        failed ? `${failed} 条评论分析失败。` : "所选评论分析完成。",
      );
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
      {!summary?.rules_ready && (
        <p className="tourism-notice" role="status">
          请先在“数据管理”导入评分规则。
        </p>
      )}
      <div className="tourism-analysis__filters">
        <input
          aria-label="搜索评论"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索评论内容、用户昵称"
          type="search"
          value={query}
        />
        <label>
          来源平台{" "}
          <select onChange={(event) => setPlatform(event.target.value)} value={platform}>
            <option value="">全部</option>
            {platforms.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label>
          分析状态{" "}
          <select onChange={(event) => setStatus(event.target.value)} value={status}>
            <option value="">全部</option>
            <option value="analyzed">已分析</option>
            <option value="pending">未分析</option>
          </select>
        </label>
      </div>
      <div className="tourism-table-scroll">
        <table className="tourism-comment-table">
          <thead>
            <tr>
              <th>选择</th>
              <th>用户昵称</th>
              <th>来源</th>
              <th>评论内容</th>
              <th>发布时间</th>
              <th>分析状态</th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.map((comment) => (
              <tr key={comment.id}>
                <td>
                  <input
                    aria-label={`选择 ${comment.nickname || "游客"} 的评论`}
                    checked={selected.has(comment.id)}
                    disabled={!summary?.rules_ready || busy}
                    onChange={() =>
                      setSelected((current) => {
                        const next = new Set(current);
                        if (next.has(comment.id)) next.delete(comment.id);
                        else next.add(comment.id);
                        return next;
                      })
                    }
                    type="checkbox"
                  />
                </td>
                <td>{comment.nickname || "游客"}</td>
                <td>{comment.platform || "—"}</td>
                <td>
                  <span className="tourism-comment__excerpt" title={comment.content}>
                    {comment.content}
                  </span>
                </td>
                <td>{comment.published_at?.slice(0, 10) || "—"}</td>
                <td>
                  <span
                    className={
                      comment.analyzed ? "tourism-status tourism-status--matched" : "tourism-status"
                    }
                  >
                    {comment.analyzed ? "已分析" : "未分析"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!visibleItems.length && (
          <p className="tourism-empty">
            {items.length
              ? "没有符合条件的评论。"
              : "尚无评论，可在“数据管理”导入 CSV，或直接在对话框输入评价。"}
          </p>
        )}
      </div>
      <div className="tourism-pagination">
        <button
          className="button button--outline"
          disabled={offset === 0}
          onClick={() => void load(Math.max(0, offset - 20))}
        >
          上一页
        </button>
        <span>
          {total ? `${offset + 1}–${Math.min(offset + items.length, total)} / ${total}` : "0 条"}
        </span>
        <button
          className="button button--outline"
          disabled={offset + items.length >= total}
          onClick={() => void load(offset + 20)}
        >
          下一页
        </button>
      </div>
      <div className="tourism-analysis__actions">
        <span>已选择 {selected.size} 条（每批最多 10 条）</span>
        <button
          className="button button--primary"
          disabled={!summary?.rules_ready || !selected.size || selected.size > 10 || busy}
          onClick={() => void analyze()}
        >
          {busy ? "分析中…" : "开始智能分析"}
        </button>
      </div>
    </section>
  );
}
