const capabilities = [
  { icon: "flow", label: "可视化智能体编排" },
  { icon: "knowledge", label: "RAG 知识库与企业数据接入" },
  { icon: "tools", label: "丰富工具调用与生态集成" },
  { icon: "memory", label: "会话状态与长期记忆" },
  { icon: "deploy", label: "工程化与高效部署" },
] as const;

export function BrandMark() {
  return (
    <img className="brand-mark" src="/logo/orionai-logo-512.png" alt="" aria-hidden="true" />
  );
}

export function ProductIntro() {
  return (
    <aside className="product-panel" aria-labelledby="product-title">
      <div className="product-content">
        <div className="brand-lockup">
          <BrandMark />
          <span>OrionAI</span>
        </div>

        <div className="product-copy">
          <p className="product-kicker">AI AGENT PLATFORM</p>
          <h1 id="product-title">
            一体化 <span>AI 智能体</span>
            <br />
            开发平台
          </h1>
          <p className="product-description">
            快速构建、编排、部署与管理企业级智能体，让 AI 真正融入业务场景。
          </p>
        </div>

        <ul className="capability-list" aria-label="平台能力">
          {capabilities.map(({ icon, label }) => (
            <li className="capability-item" key={label}>
              <CapabilityIcon kind={icon} />
              <span>{label}</span>
            </li>
          ))}
        </ul>

        <WorkflowShowcase />
        <p className="product-footer">构建、编排与运行 AI 工作流</p>
      </div>
    </aside>
  );
}

type CapabilityIconKind = (typeof capabilities)[number]["icon"];

function CapabilityIcon({ kind }: { kind: CapabilityIconKind }) {
  return (
    <svg className="capability-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      {kind === "flow" && (
        <>
          <rect x="3.5" y="4" width="6" height="6" rx="1.5" />
          <rect x="14.5" y="14" width="6" height="6" rx="1.5" />
          <path d="M6.5 10v3.5a2 2 0 0 0 2 2h6M17.5 14v-1.5a2 2 0 0 0-2-2h-6" />
        </>
      )}
      {kind === "knowledge" && (
        <>
          <ellipse cx="12" cy="5.5" rx="7.5" ry="3" />
          <path d="M4.5 5.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6M4.5 11.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
        </>
      )}
      {kind === "tools" && (
        <>
          <path d="M14 6.2a5 5 0 0 0-6.3 6.3l-4.1 4.1a2 2 0 0 0 2.8 2.8l4.1-4.1A5 5 0 0 0 16.8 9l-3 3-2.8-2.8 3-3Z" />
          <path d="m16.5 15.5 3.7 3.7" />
        </>
      )}
      {kind === "memory" && (
        <>
          <path d="M5 5.5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-7l-5 3v-3H5a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2Z" />
          <path d="M8 10h8M8 13.5h5" />
        </>
      )}
      {kind === "deploy" && (
        <>
          <path d="M12 15V4m0 0L8 8m4-4 4 4" />
          <path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" />
        </>
      )}
    </svg>
  );
}

function WorkflowShowcase() {
  return (
    <figure className="workflow-visual">
      <figcaption className="workflow-heading">
        <span className="workflow-heading__eyebrow">WORKFLOW STUDIO</span>
        <span className="workflow-heading__label">
          <span className="workflow-live-dot" aria-hidden="true" />
          工作流示意
        </span>
      </figcaption>
      <svg
        className="workflow-diagram"
        viewBox="0 0 660 224"
        role="img"
        aria-labelledby="workflow-title workflow-description"
      >
        <title id="workflow-title">AI 智能体工作流</title>
        <desc id="workflow-description">Agent 节点连接到 LLM、Tools 和 Knowledge Base。</desc>
        <path className="workflow-connector" d="M330 81v28H105v30m225-30v30m0-30h225v30" />
        <circle className="workflow-connector-dot" cx="105" cy="139" r="3" />
        <circle className="workflow-connector-dot" cx="330" cy="139" r="3" />
        <circle className="workflow-connector-dot" cx="555" cy="139" r="3" />

        <g className="workflow-node workflow-node--agent">
          <rect x="245" y="19" width="170" height="62" rx="14" />
          <rect className="workflow-node__icon-bg" x="260" y="32" width="36" height="36" rx="11" />
          <path className="workflow-node__icon" d="M271 50h14m-7-7v14m-5-14 10 14m0-14-10 14" />
          <text className="workflow-node__title" x="307" y="47">
            Agent
          </text>
          <text className="workflow-node__caption" x="307" y="64">
            智能体编排
          </text>
        </g>

        <g className="workflow-node">
          <rect x="23" y="141" width="164" height="64" rx="13" />
          <rect className="workflow-node__icon-bg" x="36" y="155" width="34" height="34" rx="10" />
          <path className="workflow-node__icon" d="M47 166h12m-12 5h12m-12 5h8" />
          <text className="workflow-node__title" x="79" y="168">
            LLM
          </text>
          <text className="workflow-node__caption" x="79" y="185">
            语言模型
          </text>
        </g>

        <g className="workflow-node">
          <rect x="248" y="141" width="164" height="64" rx="13" />
          <rect className="workflow-node__icon-bg" x="261" y="155" width="34" height="34" rx="10" />
          <path className="workflow-node__icon" d="m272 177 12-12m-9 0h9v9" />
          <text className="workflow-node__title" x="304" y="168">
            Tools
          </text>
          <text className="workflow-node__caption" x="304" y="185">
            工具调用
          </text>
        </g>

        <g className="workflow-node">
          <rect x="473" y="141" width="164" height="64" rx="13" />
          <rect className="workflow-node__icon-bg" x="486" y="155" width="34" height="34" rx="10" />
          <ellipse className="workflow-node__icon" cx="503" cy="163" rx="9" ry="3.5" />
          <path className="workflow-node__icon" d="M494 163v11c0 2 4 3.5 9 3.5s9-1.5 9-3.5v-11" />
          <text className="workflow-node__title" x="529" y="168">
            Knowledge Base
          </text>
          <text className="workflow-node__caption" x="529" y="185">
            知识检索
          </text>
        </g>
      </svg>
    </figure>
  );
}
