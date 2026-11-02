import { PlatformIcon } from "../../platform/PlatformIcon";
import type { PaymentMethod } from "../types";

interface PaymentMethodSelectorProps {
  methods: PaymentMethod[];
  selectedCode: string | null;
  onSelect: (code: string) => void;
}

export function PaymentMethodSelector({
  methods,
  selectedCode,
  onSelect,
}: PaymentMethodSelectorProps) {
  return (
    <fieldset className="payment-methods">
      <legend>支付方式</legend>
      {methods.map((method) => {
        const selected = method.code === selectedCode;
        return (
          <label className={"payment-method" + (selected ? " is-selected" : "")} key={method.code}>
            <input
              checked={selected}
              name="payment-method"
              onChange={() => onSelect(method.code)}
              type="radio"
              value={method.code}
            />
            <span className="payment-method__copy">
              <strong>{method.name}</strong>
              {method.description && <small>{method.description}</small>}
            </span>
            <span aria-hidden="true" className="payment-method__check">
              {selected && <PlatformIcon name="check" size={15} />}
            </span>
          </label>
        );
      })}
      {methods.length === 0 && (
        <p className="membership-inline-message" role="status">
          当前没有可用的支付方式，请稍后再试。
        </p>
      )}
    </fieldset>
  );
}
