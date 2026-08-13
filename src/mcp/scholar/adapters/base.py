import json
import time
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Optional, Dict

from ..cache import RequestCache
from ..rate_limiter import RateLimiter


@dataclass
class ScholarResult:
    success: bool
    data: Any = None
    source_api: str = ""
    rate_limit_remaining: str = "unknown"
    error: Optional[str] = None


class BaseAdapter:
    api_name: str = "base"
    base_url: str = ""

    _global_rate_limiter = RateLimiter(min_interval=1.0)
    _global_cache = RequestCache(default_ttl=3600, max_size=2000)

    def __init__(self):
        self._rate_limiter = self._global_rate_limiter
        self._cache = self._global_cache

    def _request(self, method: str, url: str, params: Optional[Dict] = None,
                 headers: Optional[Dict] = None, max_retries: int = 3,
                 timeout: int = 30, use_cache: bool = True) -> ScholarResult:
        if use_cache and method == "GET":
            cached = self._cache.get(method, url, params)
            if cached is not None:
                return ScholarResult(
                    success=True,
                    data=cached,
                    source_api=self.api_name,
                    rate_limit_remaining=self._rate_limiter.get_remaining(self.api_name),
                )

        self._rate_limiter.acquire(self.api_name)

        last_error = None
        for attempt in range(max_retries):
            try:
                full_url = url
                if params and method == "GET":
                    query_string = urllib.parse.urlencode(params, doseq=True)
                    separator = "&" if "?" in url else "?"
                    full_url = f"{url}{separator}{query_string}"

                req = urllib.request.Request(full_url, method=method)
                req.add_header("User-Agent", "ScholarMCP/1.0 (mailto:scholar-mcp@example.com)")
                req.add_header("Accept", "application/json")
                if headers:
                    for k, v in headers.items():
                        req.add_header(k, v)

                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    content_type = resp.headers.get("Content-Type", "")

                    if "application/json" in content_type:
                        data = json.loads(body)
                    elif "xml" in content_type:
                        data = self._parse_xml(body)
                    else:
                        try:
                            data = json.loads(body)
                        except json.JSONDecodeError:
                            data = {"raw": body}

                    rate_remaining = resp.headers.get("X-RateLimit-Remaining", "unknown")
                    self._rate_limiter.update_from_headers(self.api_name, dict(resp.headers))

                    if use_cache and method == "GET":
                        self._cache.set(method, url, params, data)

                    return ScholarResult(
                        success=True,
                        data=data,
                        source_api=self.api_name,
                        rate_limit_remaining=rate_remaining,
                    )

            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return ScholarResult(
                        success=False,
                        source_api=self.api_name,
                        error=f"Not Found (HTTP {e.code})",
                    )
                if e.code == 429:
                    wait = 2 ** attempt * 2
                    time.sleep(wait)
                    last_error = f"Rate limited (HTTP 429)"
                    continue
                if e.code >= 500:
                    wait = 2 ** attempt
                    time.sleep(wait)
                    last_error = f"Server error (HTTP {e.code})"
                    continue
                last_error = f"HTTP {e.code}: {e.reason}"
                break

            except urllib.error.URLError as e:
                wait = 2 ** attempt
                time.sleep(wait)
                last_error = f"URL Error: {e.reason}"
                continue

            except Exception as e:
                wait = 2 ** attempt
                time.sleep(wait)
                last_error = str(e)
                continue

        return ScholarResult(
            success=False,
            source_api=self.api_name,
            error=last_error or "Unknown error after retries",
        )

    def _parse_xml(self, xml_str: str) -> Dict:
        try:
            root = ET.fromstring(xml_str)
            return self._xml_to_dict(root)
        except ET.ParseError:
            return {"raw_xml": xml_str[:2000]}

    def _xml_to_dict(self, element: ET.Element) -> Dict:
        result = {}
        for child in element:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            child_data = self._xml_to_dict(child) if len(child) > 0 else (child.text or "").strip()
            if tag in result:
                if not isinstance(result[tag], list):
                    result[tag] = [result[tag]]
                result[tag].append(child_data)
            else:
                result[tag] = child_data
        return result
