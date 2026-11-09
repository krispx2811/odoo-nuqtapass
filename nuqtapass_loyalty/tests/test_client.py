from unittest.mock import MagicMock, patch

import requests

from odoo.tests import TransactionCase, tagged

from odoo.addons.nuqtapass_loyalty.lib import client as client_mod
from odoo.addons.nuqtapass_loyalty.lib.client import DEFAULT_BASE_URL, NuqtaPassClient


def fake_response(status, payload=None, text_only=False):
    resp = MagicMock()
    resp.status_code = status
    if text_only:
        resp.json.side_effect = ValueError("not json")
    else:
        resp.json.return_value = payload
    return resp


@tagged("post_install", "-at_install", "nuqtapass")
class TestClient(TransactionCase):
    def setUp(self):
        super().setUp()
        self.client = NuqtaPassClient("sip_test_key")
        patcher = patch.object(client_mod.requests, "request")
        self.request = patcher.start()
        self.addCleanup(patcher.stop)

    def test_sale_sends_bearer_json_to_sale(self):
        self.request.return_value = fake_response(201, {"success": True, "data": {"status": "OK"}})
        body = {"source": "odoo", "channel": "till", "orderRef": "Shop/0001", "phone": "+96891234567",
                "amount": 2.5, "paidAt": "2026-11-09T10:00:00Z"}
        result = self.client.sale(body)
        self.assertTrue(result.ok)
        self.assertEqual(result.data, {"status": "OK"})
        method, url = self.request.call_args.args
        kwargs = self.request.call_args.kwargs
        self.assertEqual((method, url), ("POST", DEFAULT_BASE_URL + "/sale"))
        self.assertEqual(kwargs["json"], body)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sip_test_key")
        self.assertIn("timeout", kwargs)

    def test_customer_uses_query_param(self):
        self.request.return_value = fake_response(200, {"success": True, "data": {"cards": []}})
        self.client.customer("+96891234567")
        self.assertEqual(self.request.call_args.args, ("GET", DEFAULT_BASE_URL + "/customer"))
        self.assertEqual(self.request.call_args.kwargs["params"], {"phone": "+96891234567"})

    def test_customer_by_card_uses_the_card_param(self):
        self.request.return_value = fake_response(200, {"success": True, "data": {"cards": []}})
        self.client.customer_by_card("cccccccc-1111-4111-8111-111111111111")
        self.assertEqual(self.request.call_args.args, ("GET", DEFAULT_BASE_URL + "/customer"))
        self.assertEqual(self.request.call_args.kwargs["params"], {"card": "cccccccc-1111-4111-8111-111111111111"})

    def test_network_error_is_retryable(self):
        self.request.side_effect = requests.exceptions.ConnectTimeout("boom")
        result = self.client.ping()
        self.assertFalse(result.ok)
        self.assertTrue(result.retryable)
        self.assertIsNone(result.status)
        self.assertEqual(result.code, "NETWORK")

    def test_server_error_is_retryable(self):
        self.request.return_value = fake_response(502, text_only=True)
        result = self.client.refund({})
        self.assertTrue(result.retryable)
        self.assertEqual(result.error, "HTTP 502")

    def test_plan_below_business_is_retryable_and_keeps_code(self):
        self.request.return_value = fake_response(
            403, {"success": False, "error": "Upgrade to Business to use the Odoo integration.",
                  "code": "PLAN_UPGRADE_REQUIRED", "feature": "odoo", "minPlan": "business"})
        result = self.client.sale({})
        self.assertTrue(result.retryable)
        self.assertEqual(result.code, "PLAN_UPGRADE_REQUIRED")
        self.assertEqual(result.error, "Upgrade to Business to use the Odoo integration.")

    def test_full_card_and_in_progress_are_retryable(self):
        self.request.return_value = fake_response(
            422, {"success": False, "error": "Card is full or no longer active", "code": "CARD_FULL",
                  "details": {"transactionId": "t1"}})
        self.assertTrue(self.client.sale({}).retryable)
        self.request.return_value = fake_response(
            409, {"success": False, "error": "This order was taken over by another attempt", "code": "IN_PROGRESS"})
        self.assertTrue(self.client.sale({}).retryable)

    def test_unexpected_server_failure_is_retryable(self):
        # Part 1 answers an unexpected error on /sale or /refund as 422 POS_FAILED (services/posClaim.ts).
        self.request.return_value = fake_response(
            422, {"success": False, "error": "Something went wrong", "code": "POS_FAILED",
                  "details": {"transactionId": "t1"}})
        self.assertTrue(self.client.refund({}).retryable)

    def test_inactive_card_is_final(self):
        self.request.return_value = fake_response(
            422, {"success": False, "error": "Card is full or no longer active", "code": "CARD_INACTIVE"})
        self.assertFalse(self.client.sale({}).retryable)

    def test_bad_request_is_final(self):
        self.request.return_value = fake_response(
            400, {"success": False, "error": "phone must be E.164 format, e.g. +96891234567", "code": "INVALID_PHONE"})
        result = self.client.sale({})
        self.assertFalse(result.retryable)
        self.assertEqual(result.code, "INVALID_PHONE")

    def test_success_false_in_2xx_is_failure(self):
        self.request.return_value = fake_response(200, {"success": False, "error": "nope"})
        self.assertFalse(self.client.ping().ok)

    def test_key_never_in_error(self):
        self.request.side_effect = requests.exceptions.ConnectionError("sip_test_key leaked?")
        self.assertNotIn("sip_test_key", self.client.ping().error)

    def test_requires_https_and_key(self):
        with self.assertRaises(ValueError):
            NuqtaPassClient("sip_x", "http://example.com/api/pos")
        with self.assertRaises(ValueError):
            NuqtaPassClient("")
