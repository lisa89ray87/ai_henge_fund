"""Session-level accounting for paper entry orders.

An order ID reserves one slot until a confirmed zero-fill terminal state.
Filled orders continue to count for the remainder of the session.
"""
TERMINAL_ZERO_FILL = frozenset({"CANCELLED_ALL", "FAILED", "DELETED", "DISABLED", "FILL_CANCELLED"})


class PaperOrderCapacity:
    def __init__(self):
        self._orders = {}  # broker order ID -> "PENDING" or "FILLED"

    @property
    def used(self):
        return len(self._orders)

    def observe(self, lifecycle):
        order_id = lifecycle.broker_order_id
        if not order_id:
            return
        order_id = str(order_id)
        if lifecycle.trade is not None or lifecycle.action == "OPEN":
            self._orders[order_id] = "FILLED"
        elif lifecycle.action == "PENDING":
            if lifecycle.broker_status in TERMINAL_ZERO_FILL and lifecycle.trade is None:
                # A cancelled order may still have a partial fill; only broker
                # reconciliation can establish that it was truly zero-fill.
                return
            self._orders.setdefault(order_id, "PENDING")

    def reconcile(self, monitor):
        for order_id, state in list(self._orders.items()):
            if state == "FILLED":
                continue
            try:
                status = monitor.get(order_id)
            except Exception as exc:
                print(f"ORDER CAPACITY {order_id}: reconciliation unavailable ({exc}); slot retained")
                continue
            if float(status.filled_quantity or 0) > 0:
                self._orders[order_id] = "FILLED"
            elif status.status in TERMINAL_ZERO_FILL:
                del self._orders[order_id]
                print(f"ORDER CAPACITY {order_id}: confirmed zero-fill terminal; slot released")
