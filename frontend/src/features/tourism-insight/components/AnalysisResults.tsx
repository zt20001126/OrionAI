import { useEffect, useState } from "react";
import {
  listTourismResults,
  type TourismResultGroup,
  type TourismSentiment,
} from "../api/tourismInsightApi";

interface Props {
  reloadVersion: number;
  showToast: (type: "success" | "error", message: string) => void;
}

const SENTIMENT_LABELS: Record<TourismSentiment, string> = {
  positive: "正向",
  negative: "负向",
  objective: "客观",
};

/** 展示每条匹配结果对应的情感分类。 */
export function AnalysisResults({ reloadVersion, showToast }: Props) {
  const [items, setItems] = useState<TourismResultGroup[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  useEffect(() => {
    void listTourismResults()
      .then((result) => {
        setItems(result.items);
        setSelectedId((current) =>
          result.items.some((item) => item.comment.id === current)
            ? current
            : (result.items[0]?.comment.id ?? null),
        );
      })
      .catch((error: unknown) =>
        showToast("error", error instanceof Error ? error.message : "分析结果加载失败。"),
      );
  }, [reloadVersion, showToast]);
  const selected = items.find((item) => item.comment.id === selectedId);
  if (!items.length)
    return (
      <section className="tourism-results tourism-results--empty">
        <p className="tourism-empty">完成评论分析后，结果会显示在这里。</p>
      </section>
    );
  return (
    <section className="tourism-results">
      <aside className="tourism-results__list">
        <h2>分析结果列表 ({items.length})</h2>
        <div className="tourism-results__items">
          {items.map((group) => (
            <button
              className={
                group.comment.id === selectedId
                  ? "tourism-results__item is-active"
                  : "tourism-results__item"
              }
              key={group.comment.id}
              onClick={() => setSelectedId(group.comment.id)}
              type="button"
            >
              <span className="tourism-results__item-top">
                <strong>{group.comment.nickname || "游客"}</strong>
                <span className="tourism-status tourism-status--matched">
                  已匹配 ({group.matches.filter((match) => match.status === "matched").length})
                </span>
              </span>
              <span className="tourism-results__excerpt">{group.comment.content}</span>
              <small>{group.comment.analyzed ? "已分析" : "分析中"}</small>
            </button>
          ))}
        </div>
      </aside>
      <div className="tourism-results__detail">
        {selected && (
          <>
            <div className="tourism-results__comment-meta">
              {selected.comment.nickname || "游客"} · {selected.comment.platform || "未知来源"} ·{" "}
              {selected.comment.published_at?.slice(0, 10) || ""}
            </div>
            <div className="tourism-results__original">
              <strong>原始评论</strong>
              <p>{selected.comment.content}</p>
            </div>
            <h2>匹配结果 ({selected.matches.length})</h2>
            <div className="tourism-results__matches">
              {selected.matches.map((match, index) => (
                <article className="tourism-result__match" key={`${selected.comment.id}-${index}`}>
                  <header>
                    <strong>{match.rule?.subitem_name || "未匹配评分子项"}</strong>
                    <div className="tourism-result__match-badges">
                      {match.sentiment && (
                        <span
                          className={`tourism-sentiment tourism-sentiment--${match.sentiment}`}
                        >
                          {SENTIMENT_LABELS[match.sentiment]}
                        </span>
                      )}
                      <span className={`tourism-status tourism-status--${match.status}`}>
                        {match.status === "matched"
                          ? "已匹配"
                          : match.status === "review"
                            ? "待核验"
                            : "未匹配"}
                      </span>
                    </div>
                  </header>
                  <dl>
                    {[
                      ["大项", match.rule?.major_item],
                      ["分项", match.rule?.minor_item],
                      ["指标编号", match.rule?.indicator_code],
                      ["指标名称", match.rule?.indicator_name],
                      ["子项序号", match.rule?.subitem_number],
                      ["子项名称", match.rule?.subitem_name],
                      ["评分口径", match.rule?.scoring_criterion],
                      ["简要说明", match.rule?.description],
                      ["原文证据", match.evidence],
                      ["匹配依据", match.reason],
                      [
                        "匹配状态",
                        match.status === "matched"
                          ? "已匹配"
                          : match.status === "review"
                            ? "待核验"
                            : "未匹配",
                      ],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <dt>{label}</dt>
                        <dd>{value || "—"}</dd>
                      </div>
                    ))}
                  </dl>
                </article>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
