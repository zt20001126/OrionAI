import { useCallback, useEffect, useState } from "react";

import { useToast } from "../../../components/ToastProvider";
import { t } from "../../../i18n/localeStore";
import { getTourismSummary, type TourismSummary } from "../api/tourismInsightApi";
import { AnalysisResults } from "../components/AnalysisResults";
import { CommentAnalysis } from "../components/CommentAnalysis";
import { DataManagement } from "../components/DataManagement";
import { TourismChat } from "../components/TourismChat";
import "../tourism-insight.css";

interface TourismInsightPageProps {
  conversationId: string;
}

type TabId = "data" | "analysis" | "results";
const TABS: Array<{ id: TabId; label: string }> = [
  { id: "data", label: "数据管理" },
  { id: "analysis", label: "智能分析" },
  { id: "results", label: "分析结果" },
];

/** 文旅洞察技能专属工作台，组织数据管理、对话分析和结果查看。 */
export function TourismInsightPage({ conversationId }: TourismInsightPageProps) {
  const { confirm, showToast } = useToast();
  const [activeTab, setActiveTab] = useState<TabId>("data");
  const [summary, setSummary] = useState<TourismSummary | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const refresh = useCallback(() => setReloadVersion((current) => current + 1), []);

  useEffect(() => {
    let active = true;
    void getTourismSummary().then((value) => {
      if (active) setSummary(value);
    }).catch((error: unknown) => {
      if (active) showToast("error", error instanceof Error ? error.message : "文旅数据加载失败。");
    });
    return () => { active = false; };
  }, [reloadVersion, showToast]);

  return (
    <main className="tourism-page">
      <header className="tourism-page__header">
        <div><h1>{t("文旅洞察")}</h1><p>{t("导入游客评价并依据景区评分规则完成匹配分析。")}</p></div>
        {summary && <p className={summary.rules_ready ? "tourism-ready" : "tourism-notice"} role="status">
          {summary.rules_ready ? t("评分规则已就绪") : t("请先导入评分规则")}
        </p>}
      </header>
      <nav className="tourism-tabs" aria-label={t("文旅洞察功能") }>
        {TABS.map((tab) => <button
          aria-current={activeTab === tab.id ? "page" : undefined}
          className={activeTab === tab.id ? "tourism-tabs__tab is-active" : "tourism-tabs__tab"}
          key={tab.id}
          onClick={() => setActiveTab(tab.id)}
          type="button"
        >{t(tab.label)}</button>)}
      </nav>
      {activeTab === "data" && <DataManagement confirm={confirm} onUpdated={refresh} showToast={showToast} summary={summary} />}
      {activeTab === "analysis" && <div className="tourism-analysis-layout">
        <CommentAnalysis onResults={refresh} showToast={showToast} summary={summary} />
        <TourismChat conversationId={conversationId} enabled={Boolean(summary?.rules_ready)} onResults={refresh} />
      </div>}
      {activeTab === "results" && <AnalysisResults reloadVersion={reloadVersion} showToast={showToast} />}
    </main>
  );
}
