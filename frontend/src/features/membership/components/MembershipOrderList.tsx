import { PlatformIcon } from "../../platform/PlatformIcon";
import { formatDateTime, getOrderStatusClass, getOrderStatusLabel } from "../membershipUtils";
import type { MembershipOrder } from "../types";

interface MembershipOrderListProps {
  orders: MembershipOrder[];
  onOpenOrder: (orderId: string) => void;
  onViewAll?: () => void;
  showViewAll?: boolean;
}

export function MembershipOrderList({
  orders,
  onOpenOrder,
  onViewAll,
  showViewAll = true,
}: MembershipOrderListProps) {
  return (
    <section aria-labelledby="membership-orders-title" className="membership-orders panel-card">
      <div className="membership-section-heading">
        <div>
          <h2 id="membership-orders-title">我的订单</h2>
          <p>查看会员购买记录和支付状态</p>
        </div>
        {showViewAll && onViewAll && (
          <button className="membership-text-button" onClick={onViewAll} type="button">
            查看全部
            <PlatformIcon name="arrow" size={15} />
          </button>
        )}
      </div>
      {orders.length === 0 ? (
        <div className="membership-empty-state">暂无会员订单</div>
      ) : (
        <ul className="membership-order-list">
          {orders.map((order) => (
            <li key={order.order_id}>
              <button
                className="membership-order-row"
                onClick={() => onOpenOrder(order.order_id)}
                type="button"
              >
                <span className="membership-order-row__main">
                  <strong>{order.plan_name}</strong>
                  <small>订单号 {order.order_id}</small>
                  <small>{formatDateTime(order.created_at)}</small>
                </span>
                <span className="membership-order-row__amount">¥{order.amount}</span>
                <span
                  className={
                    "membership-order-status membership-order-status--" +
                    getOrderStatusClass(order.status)
                  }
                >
                  {getOrderStatusLabel(order.status)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
