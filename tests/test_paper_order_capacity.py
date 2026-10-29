import unittest
from types import SimpleNamespace

from ai_henge_fund.paper_trading.order_capacity import PaperOrderCapacity


def lifecycle(order_id, action="PENDING", status="SUBMITTED", filled=False):
    return SimpleNamespace(broker_order_id=order_id, action=action, broker_status=status,
                           trade=object() if filled else None)


class CapacityTests(unittest.TestCase):
    def test_repeated_pending_same_order_reserves_once(self):
        capacity = PaperOrderCapacity()
        capacity.observe(lifecycle("123"))
        capacity.observe(lifecycle("123"))
        self.assertEqual(capacity.used, 1)

    def test_confirmed_zero_fill_cancellation_releases(self):
        capacity = PaperOrderCapacity()
        capacity.observe(lifecycle("123"))
        monitor = SimpleNamespace(get=lambda order_id: SimpleNamespace(status="CANCELLED_ALL", filled_quantity=0))
        capacity.reconcile(monitor)
        self.assertEqual(capacity.used, 0)

    def test_partial_fill_retains_slot_even_if_cancelled(self):
        capacity = PaperOrderCapacity()
        capacity.observe(lifecycle("123"))
        monitor = SimpleNamespace(get=lambda order_id: SimpleNamespace(status="CANCELLED_ALL", filled_quantity=2))
        capacity.reconcile(monitor)
        self.assertEqual(capacity.used, 1)
        capacity.reconcile(monitor)
        self.assertEqual(capacity.used, 1)

    def test_unavailable_reconciliation_fails_closed(self):
        capacity = PaperOrderCapacity()
        capacity.observe(lifecycle("123"))
        def fail(_):
            raise ConnectionError("offline")
        capacity.reconcile(SimpleNamespace(get=fail))
        self.assertEqual(capacity.used, 1)

    def test_filled_order_is_not_released(self):
        capacity = PaperOrderCapacity()
        capacity.observe(lifecycle("123", action="OPEN", filled=True))
        capacity.reconcile(SimpleNamespace(get=lambda _: None))
        self.assertEqual(capacity.used, 1)


if __name__ == "__main__":
    unittest.main()
