export function ProductIntro() {
  return (
    <aside aria-labelledby="product-title" className="product-panel">
      <div className="product-content">
        <div className="brand-lockup">
          <BrandMark />
          <span>OrionAI</span>
        </div>
        <div className="product-copy">
          <h1 id="product-title">企业级 AI 智能体平台</h1>
          <p>将模型、知识与工具组合成贴合业务流程的智能体应用。</p>
        </div>
      </div>
    </aside>
  );
}

export function BrandMark() {
  return <img className="brand-mark" src="/logo/orionai-logo-512.png" alt="" aria-hidden="true" />;
}
