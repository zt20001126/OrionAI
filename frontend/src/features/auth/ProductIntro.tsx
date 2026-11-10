import { t } from "../../i18n/localeStore";

interface ProductIntroProps {
  onLogoClick: () => void;
}

/** 展示认证页品牌组合；输入：Logo 点击回调；输出：可点击品牌标识和标题；调用方：认证页。 */
export function ProductIntro({ onLogoClick }: ProductIntroProps) {
  return (
    <aside aria-labelledby="product-title" className="product-panel">
      <div className="product-content">
        <button
          aria-label={t("显示测试账号")}
          className="brand-lockup brand-lockup-button"
          onClick={onLogoClick}
          type="button"
        >
          <span className="brand-lockup-icon">
            <BrandMark />
          </span>
          <span>OrionAI</span>
          <svg aria-hidden="true" className="brand-lockup-sparkle" viewBox="0 0 12 12">
            <path d="M6 0.5 7.35 4.65 11.5 6 7.35 7.35 6 11.5 4.65 7.35.5 6 4.65 4.65 6 .5Z" />
          </svg>
        </button>

        <h1 className="product-title" id="product-title">
          {t("探索 AI 的更多可能")}
        </h1>
      </div>
    </aside>
  );
}

export function BrandMark() {
  return <img className="brand-mark" src="/logo/orionai-logo-512.png" alt="" aria-hidden="true" />;
}
