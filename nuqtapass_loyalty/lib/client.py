"""The only place that talks HTTP to NuqtaPass. Never raises; never logs the key."""
from dataclasses import dataclass

import requests

DEFAULT_BASE_URL = "https://sipcard-production-b91a.up.railway.app/api/pos"
TIMEOUT = (5, 15)  # connect, read (seconds)
USER_AGENT = "nuqtapass-odoo/1.0"
# Temporary: may work later (rate limit; key or plan fixed by the shop).
RETRYABLE_STATUSES = {401, 403, 408, 425, 429}
# Part 1 codes that clear by themselves: a full stamp card (staff give the reward), an order another attempt
# holds, an unexpected server error on /sale or /refund (422 POS_FAILED).
RETRYABLE_CODES = {"CARD_FULL", "IN_PROGRESS", "POS_FAILED"}


@dataclass(frozen=True)
class ApiResult:
    ok: bool
    status: int | None
    data: dict | None
    error: str | None
    code: str | None
    retryable: bool


class NuqtaPassClient:
    def __init__(self, api_key, base_url=DEFAULT_BASE_URL):
        if not api_key:
            raise ValueError("NuqtaPass key is empty")
        if not (base_url or "").startswith("https://"):
            raise ValueError("NuqtaPass URL must use https")
        self._key = api_key
        self._base = base_url.rstrip("/")

    def ping(self):
        return self._call("GET", "/ping")

    def sale(self, body):
        return self._call("POST", "/sale", body=body)

    def refund(self, body):
        return self._call("POST", "/refund", body=body)

    def customer(self, phone):
        return self._call("GET", "/customer", params={"phone": phone})

    def redeem(self, body):
        return self._call("POST", "/redeem", body=body)

    def _call(self, method, path, params=None, body=None):
        try:
            resp = requests.request(
                method,
                self._base + path,
                params=params,
                json=body,
                timeout=TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
            )
        except requests.exceptions.RequestException as exc:
            # Only the exception class: its message can echo request details.
            return ApiResult(False, None, None, f"Could not reach NuqtaPass ({exc.__class__.__name__})",
                             "NETWORK", True)

        try:
            payload = resp.json()
        except ValueError:
            payload = None
        payload = payload if isinstance(payload, dict) else {}
        status = resp.status_code

        if 200 <= status < 300 and payload.get("success") is not False:
            data = payload.get("data")
            return ApiResult(True, status, data if isinstance(data, dict) else {}, None, None, False)

        error = str(payload.get("error") or f"HTTP {status}")[:500]
        code = payload.get("code")
        retryable = status >= 500 or status in RETRYABLE_STATUSES or code in RETRYABLE_CODES
        return ApiResult(False, status, None, error, code, retryable)
