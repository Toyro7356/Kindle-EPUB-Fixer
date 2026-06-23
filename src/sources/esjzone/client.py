"""HTTP client for ESJZone."""

from __future__ import annotations

import http.client
import re
import ssl
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, build_opener

import lxml.etree as etree
import lxml.html as lxml_html

from .html_utils import _text


ESJZONE_BASE_URL = "https://www.esjzone.cc"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
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


class EsjzoneClient:
    def __init__(
        self,
        base_url: str = ESJZONE_BASE_URL,
        cookie: str = "",
        timeout: int = 30,
        throttle_seconds: float = 0.25,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie = _clean_cookie_header(cookie)
        self.timeout = timeout
        self.throttle_seconds = throttle_seconds
        self._opener = build_opener()
        self._last_request = 0.0
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
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
            "Connection": "close",
        }
        if referer:
            headers["Referer"] = _quote_request_url(self.absolute_url(referer))
        if self.cookie:
            headers["Cookie"] = self.cookie

        last_error: Exception | None = None
        for attempt in range(max(0, retries) + 1):
            with self._throttle_lock:
                now = time.monotonic()
                elapsed = now - self._last_request
                if elapsed < self.throttle_seconds:
                    time.sleep(self.throttle_seconds - elapsed)
                self._last_request = time.monotonic()

            request = Request(request_url, headers=headers)
            try:
                with self._opener.open(request, timeout=request_timeout) as response:
                    return response.read()
            except HTTPError as exc:
                raise RuntimeError(f"ESJZone request failed: HTTP {exc.code} {absolute}") from exc
            except (URLError, ssl.SSLError, http.client.RemoteDisconnected, ConnectionError) as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                break

        raise RuntimeError(f"ESJZone request failed: {absolute}: {last_error}") from last_error

    def get_text(self, url: str, *, referer: str = "", timeout: float | None = None, retries: int = 2) -> str:
        data = self.get_bytes(url, referer=referer, timeout=timeout, retries=retries)
        for encoding in ("utf-8", "utf-8-sig", "big5", "gb18030"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def get_document(self, url: str, *, referer: str = "", timeout: float | None = None, retries: int = 2) -> etree._Element:
        return lxml_html.fromstring(self.get_text(url, referer=referer, timeout=timeout, retries=retries))

    def is_logged_in(self) -> bool:
        doc = self.get_document("/my/profile.html")
        body_text = _text(doc.text_content()).lower()
        if "login" in body_text or "登入" in body_text or "登录" in body_text:
            return False
        return bool(doc.xpath("//a[contains(@href, '/my/logout') or contains(@href, 'logout')]")) or "/my/profile" in body_text
