import { PlatformIcon } from "../../platform/PlatformIcon";
import { formatDuration } from "../membershipUtils";
import type { MembershipPlan } from "../types";

interface MembershipPlanCardProps {
  plan: MembershipPlan;
  isCurrent: boolean;
  isRecommended: boolean;
  onSelect: () => void;
}

export function MembershipPlanCard({
  plan,
  isCurrent,
  isRecommended,
  onSelect,
}: MembershipPlanCardProps) {
  return (
    <article
      className={
        "membership-plan-card" +
        (isRecommended ? " membership-plan-card--recommended" : "") +
        (isCurrent ? " membership-plan-card--current" : "")
      }
    >
      <div className="membership-plan-card__labels">
        {isRecommended && <span className="membership-plan-card__recommend">推荐</span>}
        {isCurrent && <span className="membership-plan-card__current">当前套餐</span>}
      </div>
      <h3>{plan.name}</h3>
      <p className="membership-plan-card__duration">{formatDuration(plan.duration_days)}</p>
      <p className="membership-plan-card__price">
        <span>¥</span>
        {plan.price}
      </p>
      <p className="membership-plan-card__note">所有套餐享受相同的会员身份</p>
      <button
        className="button button--primary membership-plan-card__action"
        onClick={onSelect}
        type="button"
      >
        {isCurrent ? "续费此套餐" : "立即开通"}
        <PlatformIcon name="arrow" size={16} />
      </button>
    </article>
  );
}
