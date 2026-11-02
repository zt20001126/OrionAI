import { PlatformIcon } from "../../platform/PlatformIcon";
import { formatDate, getRemainingDays } from "../membershipUtils";
import type { MembershipPeriod } from "../types";

export function MembershipInfo({
  period,
  onRenew,
}: {
  period: MembershipPeriod;
  onRenew: () => void;
}) {
  return (
    <section aria-labelledby="membership-info-title" className="membership-info panel-card">
      <div className="membership-section-heading">
        <div>
          <h2 id="membership-info-title">当前会员信息</h2>
          <p>有效期和续费排期以账户记录为准</p>
        </div>
        <button
          className="button button--outline membership-info__renew"
          onClick={onRenew}
          type="button"
        >
          <PlatformIcon name="history" size={16} />
          续费
        </button>
      </div>
      <dl className="membership-info__grid">
        <div>
          <dt>当前套餐</dt>
          <dd>{period.plan_name}</dd>
        </div>
        <div>
          <dt>有效期至</dt>
          <dd>{formatDate(period.expires_at)}</dd>
        </div>
        <div>
          <dt>剩余天数</dt>
          <dd>{getRemainingDays(period.expires_at)} 天</dd>
        </div>
        <div>
          <dt>最近开通时间</dt>
          <dd>{formatDate(period.starts_at)}</dd>
        </div>
      </dl>
    </section>
  );
}
