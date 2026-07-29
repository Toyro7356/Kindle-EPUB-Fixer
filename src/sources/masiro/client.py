"""Authenticated HTTP client for Masiro."""

from __future__ import annotations

import http.client
import json
import re
import ssl
import threading
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, build_opener

import lxml.etree as etree
import lxml.html as lxml_html


MASIRO_BASE_URL = "https://masiro.me"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)
DEFAULT_RATE_LIMIT_DELAY = 10.0
MAX_RATE_LIMIT_RETRIES = 2


class MasiroRateLimitError(RuntimeError):
    def __init__(self, retry_after_seconds: float, url: str) -> None:
        self.retry_after_seconds = retry_after_seconds
        self.url = url
        super().__init__(
            f"Masiro rate limit persisted after cooldown; retry after {retry_after_seconds:g}s: {url}"
        )


def _clean_cookie_header(value: str) -> str:
    value = value.replace("\ufeff", "").replace("\u200b", "").strip()
    value = re.sub(r"[\r\n\t]+", "", value)
    return "; ".join(part.strip() for part in value.split(";") if part.strip())


def _read_cookie(cookie: Optional[str], cookie_file: Optional[str]) -> str:
    if cookie:
        return _clean_cookie_header(cookie)
    if cookie_file:
        return _clean_cookie_header(Path(cookie_file).read_text(encoding="utf-8-sig"))
    return ""


def _quote_request_url(url: str) -> str:
    parts = urlsplit(url)
    path = quote(parts.path, safe="/%:@!$&'()*+,;=")
    query = quote(parts.query, safe="/%:@!$&'()*+,;=?")
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


class MasiroClient:
    def __init__(
        self,
        base_url: str = MASIRO_BASE_URL,
        cookie: str = "",
        user_agent: str = "",
        timeout: int = 30,
        throttle_seconds: float = 1.25,
        rate_limit_callback: Callable[[float], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie = _clean_cookie_header(cookie)
        self.user_agent = user_agent.strip() or DEFAULT_USER_AGENT
        self.timeout = timeout
        self.throttle_seconds = throttle_seconds
        self.rate_limit_callback = rate_limit_callback
        self._opener = build_opener()
        self._last_request = 0.0
        self._blocked_until = 0.0
        self._throttle_lock = threading.Lock()

    def absolute_url(self, url: str) -> str:
        if not url:
            return ""
        return urljoin(self.base_url + "/", url)

    def get_bytes(self, url: str, *, referer: str = "", timeout: float | None = None, retries: int = 2) -> bytes:
        absolute = self.absolute_url(url)
        request_url = _quote_request_url(absolute)
        request_timeout = timeout or self.timeout
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
            "Connection": "close",
        }
        if referer:
            headers["Referer"] = _quote_request_url(self.absolute_url(referer))
        if self.cookie:
            headers["Cookie"] = self.cookie

        last_error: Exception | None = None
        transport_attempt = 0
        rate_limit_attempt = 0
        while True:
            self._wait_for_request_slot()

            request = Request(request_url, headers=headers)
            try:
                with self._opener.open(request, timeout=request_timeout) as response:
                    return response.read()
            except HTTPError as exc:
                try:
                    if exc.code == 403:
                        raise RuntimeError(
                            "Masiro request was rejected (HTTP 403). Open 登录 / 刷新, choose 重新登录, "
                            "and sign in again to replace the old Cookie and browser User-Agent."
                        ) from exc
                    if exc.code == 429:
                        retry_after = self._rate_limit_delay(exc, rate_limit_attempt)
                        if self.rate_limit_callback is not None:
                            self.rate_limit_callback(retry_after)
                        self._defer_requests(retry_after)
                        if rate_limit_attempt < MAX_RATE_LIMIT_RETRIES:
                            rate_limit_attempt += 1
                            continue
                        raise MasiroRateLimitError(retry_after, absolute) from exc
                    raise RuntimeError(f"Masiro request failed: HTTP {exc.code} {absolute}") from exc
                finally:
                    exc.close()
            except (URLError, ssl.SSLError, http.client.RemoteDisconnected, ConnectionError) as exc:
                last_error = exc
                if transport_attempt < max(0, retries):
                    transport_attempt += 1
                    time.sleep(0.8 * transport_attempt)
                    continue
                break

        raise RuntimeError(f"Masiro request failed: {absolute}: {last_error}") from last_error

    def get_text(self, url: str, *, referer: str = "", timeout: float | None = None, retries: int = 2) -> str:
        data = self.get_bytes(url, referer=referer, timeout=timeout, retries=retries)
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def get_document(self, url: str, *, referer: str = "", timeout: float | None = None, retries: int = 2) -> etree._Element:
        return lxml_html.fromstring(self.get_text(url, referer=referer, timeout=timeout, retries=retries))

    def post_form_json(
        self,
        url: str,
        data: dict[str, object],
        *,
        csrf_token: str,
        referer: str = "",
        timeout: float | None = None,
    ) -> dict:
        absolute = self.absolute_url(url)
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-CSRF-TOKEN": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "close",
        }
        if referer:
            headers["Referer"] = _quote_request_url(self.absolute_url(referer))
        if self.cookie:
            headers["Cookie"] = self.cookie

        self._wait_for_request_slot()
        request = Request(
            _quote_request_url(absolute),
            data=urlencode(data).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=timeout or self.timeout) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            try:
                if exc.code == 429:
                    retry_after = self._rate_limit_delay(exc, 0)
                    if self.rate_limit_callback is not None:
                        self.rate_limit_callback(retry_after)
                    self._defer_requests(retry_after)
                    raise MasiroRateLimitError(retry_after, absolute) from exc
                raise RuntimeError(f"Masiro purchase failed: HTTP {exc.code}") from exc
            finally:
                exc.close()
        except (URLError, ssl.SSLError, http.client.RemoteDisconnected, ConnectionError) as exc:
            raise RuntimeError(f"Masiro purchase result is unknown: {exc}") from exc

        try:
            result = json.loads(payload)
        except ValueError as exc:
            raise RuntimeError("Masiro purchase returned an invalid response") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Masiro purchase returned an invalid response")
        return result

    def _wait_for_request_slot(self) -> None:
        with self._throttle_lock:
            now = time.monotonic()
            next_request = max(self._last_request + self.throttle_seconds, self._blocked_until)
            if now < next_request:
                time.sleep(next_request - now)
            self._last_request = time.monotonic()

    def _defer_requests(self, seconds: float) -> None:
        with self._throttle_lock:
            self._blocked_until = max(self._blocked_until, time.monotonic() + max(0.0, seconds))

    @staticmethod
    def _rate_limit_delay(error: HTTPError, attempt: int) -> float:
        retry_after = error.headers.get("Retry-After") if error.headers else None
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_time = parsedate_to_datetime(retry_after).timestamp()
                    return max(0.0, retry_time - time.time())
                except (TypeError, ValueError, OverflowError):
                    pass
        return DEFAULT_RATE_LIMIT_DELAY * (attempt + 1)
