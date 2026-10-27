import { useEffect, useMemo, useState } from "react";

import { PlatformIcon } from "./PlatformIcon";
import { SkillCard } from "./SkillCard";
import { SkillDetailsDialog } from "./SkillDetailsDialog";
import { addSkillToMySkills, listMarketSkills, type MarketSkill } from "./skillApi";
import { skillCategories, type SkillCategory } from "./platformData";

type MarketLoadState =
  | { requestVersion: number; status: "loading" }
  | { items: MarketSkill[]; requestVersion: number; status: "success" }
  | { error: string; requestVersion: number; status: "error" };

const EMPTY_SKILLS: MarketSkill[] = [];

/** 技能市场页面，负责加载数据库技能并协调搜索、分类和详情弹窗。 */
export function SkillMarketPage() {
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<SkillCategory>("全部");
  const [selectedSkill, setSelectedSkill] = useState<MarketSkill | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [addingSkillIds, setAddingSkillIds] = useState<Set<string>>(() => new Set());
  const [addError, setAddError] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<MarketLoadState>({
    requestVersion: 0,
    status: "loading",
  });

  useEffect(() => {
    const controller = new AbortController();

    listMarketSkills(controller.signal)
      .then((items) =>
        setLoadState({
          items,
          requestVersion: reloadVersion,
          status: "success",
        }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setLoadState({
          error: error instanceof Error ? error.message : "技能列表加载失败，请稍后重试。",
          requestVersion: reloadVersion,
          status: "error",
        });
      });

    return () => controller.abort();
  }, [reloadVersion]);

  const isLoading = loadState.requestVersion !== reloadVersion || loadState.status === "loading";
  const loadError = !isLoading && loadState.status === "error" ? loadState.error : null;
  const skills = !isLoading && loadState.status === "success" ? loadState.items : EMPTY_SKILLS;

  async function handleAddSkill(skill: MarketSkill) {
    if (skill.status !== "published" || skill.is_added) return;

    setAddError(null);
    setAddingSkillIds((current) => new Set(current).add(skill.id));
    try {
      await addSkillToMySkills(skill.id);
      setLoadState((current) => {
        if (current.status !== "success" || current.requestVersion !== reloadVersion) {
          return current;
        }
        return {
          ...current,
          items: current.items.map((item) =>
            item.id === skill.id ? { ...item, is_added: true } : item,
          ),
        };
      });
    } catch (error) {
      setAddError(error instanceof Error ? error.message : "添加技能失败，请稍后重试。");
    } finally {
      setAddingSkillIds((current) => {
        const next = new Set(current);
        next.delete(skill.id);
        return next;
      });
    }
  }

  const visibleSkills = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return skills.filter((skill) => {
      const category = skill.type === "agent" ? "智能体" : "工具";
      const matchesCategory = activeCategory === "全部" || category === activeCategory;
      const searchContent = [skill.name, skill.code, skill.description ?? ""]
        .join(" ")
        .toLocaleLowerCase();
      return matchesCategory && (!query || searchContent.includes(query));
    });
  }, [activeCategory, search, skills]);

  return (
    <div className="market-page">
      <section aria-labelledby="market-title" className="market-intro">
        <header className="market-header">
          <div>
            <h1 id="market-title">探索 AI 技能，构建专属智能体</h1>
            <p>发现、使用和管理各类可复用的 AI 能力，快速搭建你的智能体应用。</p>
          </div>
        </header>

        <section aria-label="搜索技能" className="market-search">
          <PlatformIcon name="search" size={21} />
          <input
            aria-label="搜索技能"
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索技能名称、说明或编码"
            type="search"
            value={search}
          />
        </section>
      </section>

      <section className="market-section" aria-labelledby="category-title">
        <div className="market-section__heading market-section__heading--compact">
          <div>
            <h2 id="category-title">技能分类</h2>
          </div>
          <span className="market-section__hint">按技能类型筛选</span>
        </div>
        <div aria-label="技能分类" className="category-list" role="group">
          {skillCategories.map((category) => (
            <button
              aria-pressed={activeCategory === category}
              className={`category-chip${activeCategory === category ? " is-active" : ""}`}
              key={category}
              onClick={() => setActiveCategory(category)}
              type="button"
            >
              {category}
            </button>
          ))}
        </div>
      </section>

      <section className="market-section" aria-labelledby="skill-list-title">
        <div className="market-section__heading">
          <div>
            <h2 id="skill-list-title">技能列表</h2>
          </div>
          <span className="skill-count">
            {isLoading ? "加载中" : loadError ? "加载失败" : `${visibleSkills.length} 项技能`}
          </span>
        </div>

        {addError && (
          <p className="platform-global-error" role="alert">
            {addError}
          </p>
        )}

        {isLoading ? (
          <div className="market-no-results" role="status">
            正在加载技能列表…
          </div>
        ) : loadError ? (
          <div className="market-no-results" role="alert">
            <strong>技能列表加载失败</strong>
            <span>{loadError}</span>
            <button
              className="button button--outline"
              onClick={() => setReloadVersion((version) => version + 1)}
              type="button"
            >
              重试
            </button>
          </div>
        ) : visibleSkills.length > 0 ? (
          <div className="skill-grid">
            {visibleSkills.map((skill) => (
              <SkillCard
                actions={
                  skill.status === "disabled" ? (
                    <button className="button button--secondary" disabled type="button">
                      暂不可添加
                    </button>
                  ) : skill.is_added ? (
                    <button className="button button--secondary" disabled type="button">
                      已在我的技能
                    </button>
                  ) : (
                    <button
                      className="button button--primary"
                      disabled={addingSkillIds.has(skill.id)}
                      onClick={() => void handleAddSkill(skill)}
                      type="button"
                    >
                      {addingSkillIds.has(skill.id) ? "添加中…" : "添加到我的技能"}
                    </button>
                  )
                }
                key={skill.id}
                onView={setSelectedSkill}
                skill={skill}
              />
            ))}
          </div>
        ) : (
          <div className="market-no-results" role="status">
            <span className="market-no-results__icon">
              <PlatformIcon name="search" size={20} />
            </span>
            <strong>{skills.length === 0 ? "暂无技能" : "暂未找到匹配技能"}</strong>
            <span>
              {skills.length === 0
                ? "技能目录中还没有可展示的内容。"
                : "试试更换关键词或选择其他分类。"}
            </span>
          </div>
        )}
      </section>

      {selectedSkill && (
        <SkillDetailsDialog onClose={() => setSelectedSkill(null)} skill={selectedSkill} />
      )}
    </div>
  );
}
