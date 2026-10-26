import { useMemo, useState } from "react";

import { PlatformIcon } from "./PlatformIcon";
import { SkillCard } from "./SkillCard";
import { SkillDetailsDialog } from "./SkillDetailsDialog";
import { demoSkills, skillCategories, type DemoSkill, type SkillCategory } from "./platformData";

export function SkillMarketPage() {
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<SkillCategory>("全部");
  const [selectedSkill, setSelectedSkill] = useState<DemoSkill | null>(null);

  const visibleSkills = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return demoSkills.filter((skill) => {
      const matchesCategory = activeCategory === "全部" || skill.category === activeCategory;
      const searchContent = [skill.name, skill.description, skill.category, ...skill.keywords]
        .join(" ")
        .toLocaleLowerCase();
      return matchesCategory && (!query || searchContent.includes(query));
    });
  }, [activeCategory, search]);

  return (
    <div className="market-page">
      <section className="market-header" aria-labelledby="market-title">
        <div>
          <h1 id="market-title">探索 AI 技能，构建专属智能体</h1>
          <p>发现、使用和管理各类可复用的 AI 能力，快速搭建你的智能体应用。</p>
        </div>
      </section>

      <section className="market-search" aria-label="搜索技能">
        <PlatformIcon name="search" size={21} />
        <input
          aria-label="搜索技能"
          onChange={(event) => setSearch(event.target.value)}
          placeholder="搜索技能（如：RAG、文档分析、代码助手等）"
          type="search"
          value={search}
        />
      </section>

      <section className="market-section" aria-labelledby="category-title">
        <div className="market-section__heading market-section__heading--compact">
          <div>
            <h2 id="category-title">技能分类</h2>
          </div>
          <span className="market-section__hint">按场景探索可复用能力</span>
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

      <section className="market-section" aria-labelledby="popular-skills-title">
        <div className="market-section__heading">
          <div>
            <h2 id="popular-skills-title">热门技能</h2>
          </div>
          <span className="skill-count">{visibleSkills.length} 项演示技能</span>
        </div>

        {visibleSkills.length > 0 ? (
          <div className="skill-grid">
            {visibleSkills.map((skill) => (
              <SkillCard key={skill.id} onView={setSelectedSkill} skill={skill} />
            ))}
          </div>
        ) : (
          <div className="market-no-results" role="status">
            <span className="market-no-results__icon">
              <PlatformIcon name="search" size={20} />
            </span>
            <strong>暂未找到匹配技能</strong>
            <span>试试更换关键词或选择其他分类。</span>
          </div>
        )}
      </section>

      <section className="market-coming-soon" aria-labelledby="coming-soon-title">
        <div>
          <h2 id="coming-soon-title">技能市场正在建设中</h2>
          <p>更多实用技能即将上线，敬请期待</p>
        </div>
      </section>

      {selectedSkill && (
        <SkillDetailsDialog onClose={() => setSelectedSkill(null)} skill={selectedSkill} />
      )}
    </div>
  );
}
