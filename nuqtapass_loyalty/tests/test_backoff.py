from datetime import timedelta

from odoo.tests import TransactionCase, tagged

from odoo.addons.nuqtapass_loyalty.lib.backoff import MAX_ATTEMPTS, next_retry_delay


@tagged("post_install", "-at_install", "nuqtapass")
class TestBackoff(TransactionCase):
    def test_quick_steps(self):
        self.assertEqual(next_retry_delay(1), timedelta(minutes=1))
        self.assertEqual(next_retry_delay(2), timedelta(minutes=5))
        self.assertEqual(next_retry_delay(3), timedelta(minutes=15))
        self.assertEqual(next_retry_delay(4), timedelta(minutes=60))

    def test_every_six_hours_for_three_days(self):
        slow = [next_retry_delay(n) for n in range(5, 17)]
        self.assertTrue(all(d == timedelta(hours=6) for d in slow))
        self.assertEqual(sum(slow, timedelta()), timedelta(days=3))

    def test_then_give_up(self):
        self.assertIsNone(next_retry_delay(17))
        self.assertEqual(MAX_ATTEMPTS, 17)

    def test_rejects_zero(self):
        with self.assertRaises(ValueError):
            next_retry_delay(0)
