#!/usr/bin/env python3
"""Enforce the standalone PS5/TV audience boundary on generated outputs."""
import argparse
import html
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "deals.json"
HTML_PATH = ROOT / "index.html"
EMAIL_PATH = ROOT / "out" / "latest-email.json"
DEFAULT_DASHBOARD_URL = "https://lukestambaugh75-hue.github.io/ps5-tv-deal-tracker-r0/"
EXPECTED_RECIPIENTS = ["lukestambaugh75@gmail.com", "devin.mullen89@gmail.com"]

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
CSS_IMPORT_RE = re.compile(
    r"@import\s+(?:url\(\s*)?(['\"])(.*?)\1\s*\)?", re.IGNORECASE | re.DOTALL
)
ABSOLUTE_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
SCRIPT_NAVIGATION_RE = re.compile(
    r"(?:\b(?:window\.)?location(?:\.href)?\s*=|"
    r"\b(?:window\.)?location\.(?:assign|replace)\s*\(|"
    r"\bwindow\.open\s*\()",
    re.IGNORECASE,
)
FORBIDDEN_VISIBLE_NAV = (
    "Main Dashboard",
    "Deal Trackers",
    "Kegerator",
    "Kegerators",
    "Ford Raptor",
    "Raptor",
)
INTERACTIVE_TEXT_TAGS = {"a", "button", "menu", "nav", "option", "summary"}
INTERACTIVE_ROLES = {"button", "link", "menu", "menuitem", "navigation", "tab"}
SVG_RESOURCE_TAGS = {"feimage", "image", "use"}


class AudienceBoundaryError(ValueError):
    """Raised when generated output crosses the PS5/TV audience boundary."""


def allowed_output_urls(data):
    """Return the exact outbound URLs allowed in the generated PS5/TV outputs."""
    allowed = {DEFAULT_DASHBOARD_URL}
    for item in data.get("items", []):
        value = str(item.get("url") or "").strip()
        if value:
            allowed.add(value)
    return frozenset(allowed)


def _css_references(css_text, context):
    references = []
    for match in CSS_URL_RE.finditer(css_text or ""):
        references.append(("resource", html.unescape(match.group(2).strip()), context))
    for match in CSS_IMPORT_RE.finditer(css_text or ""):
        references.append(("resource", html.unescape(match.group(2).strip()), context))
    return references


class _ActiveUrlParser(HTMLParser):
    """Collect active URL references and visible text from generated HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references = []
        self.navigation_label_chunks = []
        self.completed_navigation_labels = []
        self._interactive_stack = []
        self._style_depth = 0
        self._script_depth = 0

    def _handle_tag(self, tag, attrs):
        attrs_by_name = {str(name).lower(): value for name, value in attrs}
        if tag == "base":
            raise AudienceBoundaryError("base URL elements are not allowed")
        if tag == "style":
            self._style_depth += 1
        if tag == "script":
            self._script_depth += 1

        role = str(attrs_by_name.get("role") or "").strip().lower()
        is_interactive = tag in INTERACTIVE_TEXT_TAGS or role in INTERACTIVE_ROLES

        for name, value in attrs:
            name = str(name).lower()
            value = html.unescape(str(value or "").strip())
            if name.startswith("on"):
                raise AudienceBoundaryError(
                    f"inline event handler attributes are not allowed: <{tag}> {name}"
                )
            if name in {"srcdoc", "ping"}:
                raise AudienceBoundaryError(
                    f"active uninspected attribute is not allowed: <{tag}> {name}"
                )
            if not value:
                continue
            context = f"<{tag}> {name}"
            if is_interactive and name in {"aria-label", "title", "value"}:
                self.navigation_label_chunks.append(value)
            if name == "style":
                self.references.extend(_css_references(value, context))
            elif name == "srcset":
                for candidate in value.split(","):
                    resource = candidate.strip().split()[0] if candidate.strip() else ""
                    if resource:
                        self.references.append(("resource", resource, context))
            elif name in {"src", "poster", "background", "data", "xlink:href"}:
                self.references.append(("resource", value, context))
            elif name == "href":
                kind = "resource" if tag == "link" or tag in SVG_RESOURCE_TAGS else "navigation"
                self.references.append((kind, value, context))
            elif name in {"action", "formaction", "cite"}:
                self.references.append(("navigation", value, context))

        if tag == "meta" and str(attrs_by_name.get("http-equiv") or "").lower() == "refresh":
            content = str(attrs_by_name.get("content") or "")
            match = re.search(r"url\s*=\s*(.+)$", content, flags=re.IGNORECASE)
            if match:
                self.references.append(
                    ("navigation", match.group(1).strip(" \t\"'"), "<meta> refresh")
                )
        return is_interactive

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self._handle_tag(tag, attrs):
            self._interactive_stack.append({"tag": tag, "parts": []})

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        self._handle_tag(tag, attrs)
        if tag == "style":
            self._style_depth -= 1
        if tag == "script":
            self._script_depth -= 1

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "style" and self._style_depth:
            self._style_depth -= 1
        if tag == "script" and self._script_depth:
            self._script_depth -= 1
        for index in range(len(self._interactive_stack) - 1, -1, -1):
            if self._interactive_stack[index]["tag"] == tag:
                for element in self._interactive_stack[index:]:
                    label = " ".join(element["parts"]).strip()
                    if label:
                        self.completed_navigation_labels.append(label)
                del self._interactive_stack[index:]
                break

    def handle_data(self, data):
        if self._style_depth:
            self.references.extend(_css_references(data, "<style>"))
            return
        if self._script_depth:
            if SCRIPT_NAVIGATION_RE.search(data):
                raise AudienceBoundaryError("script redirect or navigation code is not allowed")
            for value in ABSOLUTE_URL_RE.findall(data):
                self.references.append(("navigation", value.rstrip(".,;"), "<script> URL"))
            return
        text = data.strip()
        if text and self._interactive_stack:
            self.navigation_label_chunks.append(text)
            for element in self._interactive_stack:
                element["parts"].append(text)

    def navigation_labels(self):
        labels = self.navigation_label_chunks + self.completed_navigation_labels
        labels.extend(
            " ".join(element["parts"]).strip()
            for element in self._interactive_stack
            if element["parts"]
        )
        return labels


def _validate_local_resource(value, context, asset_root):
    if not value or value.startswith("#"):
        return
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith("//"):
        raise AudienceBoundaryError(f"external resource is not allowed in {context}: {value}")
    path_text = parsed.path.replace("\\", "/")
    if path_text.startswith("/") or not path_text.startswith("assets/"):
        raise AudienceBoundaryError(f"resource must be a local assets/ file in {context}: {value}")
    root = Path(asset_root).resolve()
    candidate = (root / path_text).resolve()
    try:
        candidate.relative_to(root / "assets")
    except ValueError as exc:
        raise AudienceBoundaryError(f"resource escapes assets/ in {context}: {value}") from exc
    if not candidate.is_file():
        raise AudienceBoundaryError(f"local resource does not exist in {context}: {value}")


def _validate_navigation(value, context, allowed_urls):
    value = html.unescape(str(value or "").strip()).rstrip(".,;")
    if not value or value.startswith("#"):
        return
    parsed = urlsplit(value)
    if parsed.scheme not in {"https"} or not parsed.netloc:
        raise AudienceBoundaryError(f"navigation must use an exact allowed HTTPS URL in {context}: {value}")
    if value not in allowed_urls:
        raise AudienceBoundaryError(f"URL is outside the PS5/TV allowlist in {context}: {value}")


def _validate_visible_navigation(parser):
    forbidden = {
        re.sub(r"\s+", " ", label).strip(" \t\r\n:|›→-").casefold(): label
        for label in FORBIDDEN_VISIBLE_NAV
    }
    for candidate in parser.navigation_labels():
        normalized = re.sub(r"\s+", " ", candidate).strip(" \t\r\n:|›→-").casefold()
        if normalized in forbidden:
            raise AudienceBoundaryError(
                f"forbidden cross-dashboard navigation text: {forbidden[normalized]}"
            )


def _parse_html(html_text):
    parser = _ActiveUrlParser()
    try:
        parser.feed(html_text)
        parser.close()
    except AudienceBoundaryError:
        raise
    except Exception as exc:
        raise AudienceBoundaryError(f"could not parse generated HTML: {exc}") from exc
    return parser


def validate_dashboard_html(html_text, data, asset_root=ROOT):
    """Validate active URLs and visible navigation in the generated dashboard."""
    allowed_urls = allowed_output_urls(data)
    parser = _parse_html(html_text)
    for kind, value, context in parser.references:
        if kind == "resource":
            _validate_local_resource(value, context, asset_root)
        else:
            _validate_navigation(value, context, allowed_urls)
    _validate_visible_navigation(parser)
    return allowed_urls


def _absolute_urls(text):
    return {
        html.unescape(value).rstrip(".,;")
        for value in ABSOLUTE_URL_RE.findall(str(text or ""))
    }


def validate_email_payload(payload, data):
    """Validate recipients and every URL-bearing field in the generated email."""
    if payload.get("to") != EXPECTED_RECIPIENTS:
        raise AudienceBoundaryError(
            f"email recipients must be exactly {EXPECTED_RECIPIENTS}; got {payload.get('to')}"
        )
    if payload.get("cc") != [] or payload.get("bcc") != []:
        raise AudienceBoundaryError("email CC and BCC recipients must remain empty")
    if payload.get("dashboard_url") != DEFAULT_DASHBOARD_URL:
        raise AudienceBoundaryError(
            f"email dashboard_url must be exactly {DEFAULT_DASHBOARD_URL}"
        )

    allowed_urls = allowed_output_urls(data)
    html_body = str(payload.get("body_html") or "")
    parser = _parse_html(html_body)
    for kind, value, context in parser.references:
        if kind == "resource":
            raise AudienceBoundaryError(f"email resource loading is not allowed in {context}: {value}")
        _validate_navigation(value, f"email {context}", allowed_urls)
    _validate_visible_navigation(parser)

    fields = {
        "dashboard_url": payload.get("dashboard_url"),
        "body_text": payload.get("body_text"),
        "body_html": html_body,
    }
    for field, value in fields.items():
        for url in _absolute_urls(value):
            _validate_navigation(url, f"email {field}", allowed_urls)
    return allowed_urls


def validate_outputs(html_text, payload, data, asset_root=ROOT):
    """Validate the generated dashboard and email as one audience-boundary gate."""
    validate_dashboard_html(html_text, data, asset_root=asset_root)
    validate_email_payload(payload, data)


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", default=os.fspath(HTML_PATH))
    parser.add_argument("--data", default=os.fspath(DATA_PATH))
    parser.add_argument("--email", default=os.fspath(EMAIL_PATH))
    args = parser.parse_args()
    try:
        with open(args.html, encoding="utf-8") as f:
            html_text = f.read()
        data = _read_json(args.data)
        payload = _read_json(args.email)
        validate_outputs(html_text, payload, data, asset_root=ROOT)
    except Exception as exc:
        print(f"audience boundary violation: {exc}", file=sys.stderr)
        return 1
    print("audience boundary passed: standalone PS5/TV page and exact Luke + Devin email")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
