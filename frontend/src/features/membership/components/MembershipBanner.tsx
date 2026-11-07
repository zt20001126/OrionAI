import { PlatformIcon } from "../../platform/PlatformIcon";
import { t } from "../../../i18n/localeStore";

interface MembershipBannerProps {
  title: string;
  description: string;
  state?: "active" | "expired";
  onOrders: () => void;
}

export function MembershipBanner({ title, description, state, onOrders }: MembershipBannerProps) {
  return (
    <section className={"membership-banner" + (state ? " membership-banner--" + state : "")}>
      <div className="membership-banner__copy">
        <span className="membership-banner__icon">
          <PlatformIcon name="crown" size={22} />
        </span>
        <div>
          <div className="membership-banner__title-row">
            <h1>{title}</h1>
            {state === "active" && <span className="membership-vip-tag">VIP</span>}
          </div>
          <p>{description}</p>
        </div>
      </div>
      <button
        className="membership-banner__orders button button--secondary"
        onClick={onOrders}
        type="button"
      >
        <PlatformIcon name="document" size={18} />
        {t("我的订单")}
        <PlatformIcon name="arrow" size={16} />
      </button>
      <div aria-hidden="true" className="membership-banner__decoration">
        <PlatformIcon name="crown" size={90} />
      </div>
    </section>
  );
}
