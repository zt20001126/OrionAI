import { useEffect, useState } from "react";

import { useToast } from "../../components/ToastProvider";
import { SkillCard } from "../platform/SkillCard";
import { SkillDetailsDialog } from "../platform/SkillDetailsDialog";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { getConversationErrorMessage } from "../conversations/conversationApi";
import {
  listMySkills,
  removeSkillFromMySkills,
  type MarketSkill,
  type MySkill,
} from "../platform/skillApi";
import { canLaunchSkill, ensureSkillMembership, launchSkill } from "../platform/skillUsage";
import { t } from "../../i18n/localeStore";

interface MySkillsPageProps {
  onNavigate: (path: PlatformRoute) => void;
}

type MySkillsLoadState =
  | { requestVersion: number; status: "loading" }
  | { items: MySkill[]; requestVersion: number; status: "success" }
  | { error: string; requestVersion: number; status: "error" };

const EMPTY_MY_SKILLS: MySkill[] = [];

/** 当前用户的技能页，只展示已添加且仍可用的技能。 */
export function MySkillsPage({ onNavigate }: MySkillsPageProps) {
  const { confirm, showToast } = useToast();
  const [reloadVersion, setReloadVersion] = useState(0);
  const [removingSkillIds, setRemovingSkillIds] = useState<Set<string>>(() => new Set());
  const [startingSkillIds, setStartingSkillIds] = useState<Set<string>>(() => new Set());
  const [selectedSkill, setSelectedSkill] = useState<MarketSkill | null>(null);
  const [loadState, setLoadState] = useState<MySkillsLoadState>({
    requestVersion: 0,
    status: "loading",
  });

  useEffect(() => {
    const controller = new AbortController();

    listMySkills(controller.signal)
      .then((items) => setLoadState({ items, requestVersion: reloadVersion, status: "success" }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setLoadState({
          error: error instanceof Error ? error.message : t("我的技能加载失败，请稍后重试。"),
          requestVersion: reloadVersion,
          status: "error",
        });
      });

    return () => controller.abort();
  }, [reloadVersion]);

  const isLoading = loadState.requestVersion !== reloadVersion || loadState.status === "loading";
  const loadError = !isLoading && loadState.status === "error" ? loadState.error : null;
  const skills = !isLoading && loadState.status === "success" ? loadState.items : EMPTY_MY_SKILLS;

  async function handleRemoveSkill(skill: MySkill) {
    setRemovingSkillIds((current) => new Set(current).add(skill.id));
    try {
      await removeSkillFromMySkills(skill.id);
      setLoadState((current) => {
        if (current.status !== "success" || current.requestVersion !== reloadVersion) {
          return current;
        }
        return {
          ...current,
          items: current.items.filter((item) => item.id !== skill.id),
        };
      });
      showToast("success", t("已从我的技能移除「{name}」。", { name: skill.name }));
    } catch (error) {
      showToast(
        "error",
        error instanceof Error && error.message === t("网络连接异常，请检查网络后重试。")
          ? t("网络连接异常，请检查网络后重试。")
          : t("移除技能失败，请稍后重试。"),
      );
    } finally {
      setRemovingSkillIds((current) => {
        const next = new Set(current);
        next.delete(skill.id);
        return next;
      });
    }
  }

  async function handleUseSkill(skill: MySkill) {
    setStartingSkillIds((current) => new Set(current).add(skill.id));
    try {
      if (
        !(await ensureSkillMembership(onNavigate, confirm, (message) =>
          showToast("error", message),
        ))
      )
        return;
      await launchSkill(skill, onNavigate);
    } catch (error) {
      showToast("error", getConversationErrorMessage(error));
    } finally {
      setStartingSkillIds((current) => {
        const next = new Set(current);
        next.delete(skill.id);
        return next;
      });
    }
  }

  return (
    <div className="market-page">
      <section className="market-header" aria-labelledby="my-skills-title">
        <div>
          <h1 id="my-skills-title">{t("我的技能")}</h1>
          <p>{t("已添加的技能会显示在这里；从技能市场添加后即可使用可运行的技能。")}</p>
        </div>
      </section>

      <section className="market-section" aria-labelledby="my-skills-list-title">
        <div className="market-section__heading">
          <div>
            <h2 id="my-skills-list-title">{t("已添加技能")}</h2>
          </div>
          <span className="skill-count">
            {isLoading ? t("加载中") : loadError ? t("加载失败") : `${skills.length} 项技能`}
          </span>
        </div>

        {isLoading ? (
          <div className="market-no-results" role="status">
            {t("正在加载我的技能…")}
          </div>
        ) : loadError ? (
          <div className="market-no-results" role="alert">
            <strong>{t("我的技能加载失败")}</strong>
            <span>{loadError}</span>
            <button
              className="button button--outline"
              onClick={() => setReloadVersion((version) => version + 1)}
              type="button"
            >
              {t("重试")}
            </button>
          </div>
        ) : skills.length > 0 ? (
          <div className="skill-grid">
            {skills.map((skill) => (
              <SkillCard
                actions={
                  <>
                    <button
                      className="button button--outline"
                      disabled={removingSkillIds.has(skill.id)}
                      onClick={() => void handleRemoveSkill(skill)}
                      type="button"
                    >
                      {removingSkillIds.has(skill.id) ? t("移除中…") : t("移除")}
                    </button>
                    <button
                      className="button button--primary"
                      disabled={startingSkillIds.has(skill.id) || !canLaunchSkill(skill.code)}
                      onClick={() => void handleUseSkill(skill)}
                      type="button"
                    >
                      {startingSkillIds.has(skill.id)
                        ? t("正在启动…")
                        : canLaunchSkill(skill.code)
                          ? t("使用")
                          : t("运行入口未接入")}
                    </button>
                  </>
                }
                key={skill.id}
                onView={setSelectedSkill}
                skill={skill}
              />
            ))}
          </div>
        ) : (
          <div className="market-no-results" role="status">
            <strong>{t("还没有添加技能")}</strong>
            <span>{t("前往技能市场添加已发布的技能，再从这里使用。")}</span>
            <button
              className="button button--primary"
              onClick={() => onNavigate(platformPaths.market)}
              type="button"
            >
              {t("浏览技能市场")}
            </button>
          </div>
        )}
      </section>

      {selectedSkill && (
        <SkillDetailsDialog onClose={() => setSelectedSkill(null)} skill={selectedSkill} />
      )}
    </div>
  );
}
