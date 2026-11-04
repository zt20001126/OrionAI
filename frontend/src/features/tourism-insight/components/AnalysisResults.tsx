import { useEffect, useState } from "react";

import { listTourismResults, type TourismResultGroup } from "../api/tourismInsightApi";

interface AnalysisResultsProps {
  reloadVersion: number;
  showToast: (type: "success" | "error", message: string) => void;
}

/** 展示评论分组结果及服务端补齐的评分指标层级。 */
export function AnalysisResults({ reloadVersion, showToast }: AnalysisResultsProps) {
  const [items, setItems] = useState<TourismResultGroup[]>([]);
  useEffect(() => {
    void listTourismResults().then((result) => setItems(result.items)).catch((error: unknown) => {
      showToast("error", error instanceof Error ? error.message : "分析结果加载失败。");
    });
  }, [reloadVersion, showToast]);
  if (!items.length) return <p className="tourism-empty">完成评论分析后，结果会显示在这里。</p>;
  return <section className="tourism-results">{items.map((group) => (
    <article className="tourism-result" key={group.comment.id}>
      <p className="tourism-result__comment">{group.comment.content}</p>
      {group.matches.map((match, index) => (
        <div className="tourism-result__match" key={`${group.comment.id}-${index}`}>
          <span className={`tourism-status tourism-status--${match.status}`}>{match.status === "matched" ? "已匹配" : match.status === "review" ? "待核验" : "未匹配"}</span>
          {match.rule && <h3>{match.rule.major_item} → {match.rule.minor_item} → {match.rule.indicator_code} {match.rule.indicator_name} → {match.rule.subitem_number} {match.rule.subitem_name}</h3>}
          {match.rule && <p><strong>评分口径：</strong>{match.rule.scoring_criterion}</p>}
          {match.rule?.description && <p><strong>简要说明：</strong>{match.rule.description}</p>}
          {match.evidence && <blockquote><strong>原文证据：</strong>{match.evidence}</blockquote>}
          {match.reason && <p><strong>匹配依据：</strong>{match.reason}</p>}
        </div>
      ))}
    </article>
  ))}</section>;
}
