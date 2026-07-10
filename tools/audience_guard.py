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
    r"\b(?:window\.)?location\.(?:assign|replace|reload)\s*\(|"
    r"\bwindow\.open\s*\()",
    re.IGNORECASE,
)
UNSAFE_HISTORY_METHODS = {"back", "forward", "go", "pushState"}
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
    return candidate


def _javascript_tokens(source):
    """Tokenize executable JavaScript while skipping comments and string bodies."""
    tokens = []
    length = len(source)

    def scan(index, stop_on_closing_brace=False):
        brace_depth = 0
        while index < length:
            char = source[index]
            if stop_on_closing_brace and char == "}" and brace_depth == 0:
                return index + 1
            if char.isspace():
                index += 1
                continue
            if source.startswith("//", index):
                newline = source.find("\n", index + 2)
                index = length if newline == -1 else newline + 1
                continue
            if source.startswith("/*", index):
                closing = source.find("*/", index + 2)
                if closing == -1:
                    raise AudienceBoundaryError("unterminated JavaScript block comment")
                index = closing + 2
                continue
            if char in {"'", '"'}:
                quote = char
                index += 1
                value = []
                escaped = False
                while index < length:
                    current = source[index]
                    if current == "\\":
                        escaped = True
                        value.append(current)
                        index += 1
                        if index < length:
                            value.append(source[index])
                            index += 1
                        continue
                    if current == quote:
                        index += 1
                        break
                    value.append(current)
                    index += 1
                else:
                    raise AudienceBoundaryError("unterminated JavaScript string")
                tokens.append(("string", "".join(value), escaped))
                continue
            if char == "`":
                index += 1
                while index < length:
                    current = source[index]
                    if current == "\\":
                        index += 2
                        continue
                    if current == "`":
                        index += 1
                        break
                    if source.startswith("${", index):
                        tokens.append(("template", "", False))
                        index = scan(index + 2, stop_on_closing_brace=True)
                        continue
                    index += 1
                else:
                    raise AudienceBoundaryError("unterminated JavaScript template")
                continue
            if char.isalpha() or char in {"_", "$"}:
                end = index + 1
                while end < length and (
                    source[end].isalnum() or source[end] in {"_", "$"}
                ):
                    end += 1
                tokens.append(("identifier", source[index:end], False))
                index = end
                continue
            if char == "{":
                brace_depth += 1
            elif char == "}" and brace_depth:
                brace_depth -= 1
            tokens.append(("punctuation", char, False))
            index += 1
        if stop_on_closing_brace:
            raise AudienceBoundaryError("unterminated JavaScript template interpolation")
        return index

    scan(0)
    return tokens


def _call_arguments(tokens, opening_index):
    arguments = []
    current = []
    depth = 0
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = set(pairs.values())
    for index in range(opening_index, len(tokens)):
        value = tokens[index][1]
        if value in pairs:
            depth += 1
            if depth > 1:
                current.append(tokens[index])
            continue
        if value in closing:
            depth -= 1
            if depth == 0:
                if current or not arguments:
                    arguments.append(current)
                return arguments, index
            current.append(tokens[index])
            continue
        if value == "," and depth == 1:
            arguments.append(current)
            current = []
            continue
        current.append(tokens[index])
    raise AudienceBoundaryError("unterminated JavaScript function call")


def _safe_replace_state_argument(argument):
    if len(argument) == 1 and argument[0][0] == "string":
        value = argument[0][1]
        escaped = argument[0][2]
        return not escaped and (not value or value.startswith(("?", "#")))
    values = [token[1] for token in argument]
    expected = [
        "(",
        "selected",
        "=",
        "=",
        "=",
        "details",
        "?",
        "?view=details",
        ":",
        "",
        ")",
        "+",
        "window",
        ".",
        "location",
        ".",
        "hash",
    ]
    string_positions = {5, 7, 9}
    return values == expected and all(
        argument[index][0] == "string" and not argument[index][2]
        for index in string_positions
    )


def _validate_script_tokens(tokens, script_name):
    values = [token[1] for token in tokens]
    for index, token in enumerate(tokens):
        kind, value, _ = token
        next_value = values[index + 1] if index + 1 < len(values) else None
        if kind == "identifier" and value == "import":
            raise AudienceBoundaryError(
                f"imports are not allowed in self-contained local script: {script_name}"
            )
        if kind == "identifier" and value == "fetch" and next_value == "(":
            raise AudienceBoundaryError(f"fetch is not allowed in local script: {script_name}")
        if kind == "identifier" and value == "export":
            following = values[index + 1 :]
            if following and following[0] == "*":
                if "from" in following[: following.index(";") if ";" in following else None]:
                    raise AudienceBoundaryError(
                        f"re-exports are not allowed in local script: {script_name}"
                    )
            elif following and following[0] == "{":
                depth = 0
                closing_index = None
                for offset, candidate in enumerate(following):
                    if candidate == "{":
                        depth += 1
                    elif candidate == "}":
                        depth -= 1
                        if depth == 0:
                            closing_index = offset
                            break
                if closing_index is not None and following[closing_index + 1 : closing_index + 2] == ["from"]:
                    raise AudienceBoundaryError(
                        f"re-exports are not allowed in local script: {script_name}"
                    )
        if kind == "identifier" and value == "window":
            if values[index : index + 4] == ["window", ".", "open", "("]:
                raise AudienceBoundaryError(
                    f"script redirect or navigation code is not allowed: {script_name}"
                )
        if kind == "identifier" and value == "location":
            if next_value == "=":
                raise AudienceBoundaryError(
                    f"script redirect or navigation code is not allowed: {script_name}"
                )
            if values[index + 1 : index + 4] in (
                [".", "assign", "("],
                [".", "replace", "("],
                [".", "reload", "("],
            ):
                raise AudienceBoundaryError(
                    f"script redirect or navigation code is not allowed: {script_name}"
                )
            if values[index + 1 : index + 4] == [".", "href", "="]:
                raise AudienceBoundaryError(
                    f"script redirect or navigation code is not allowed: {script_name}"
                )
        if kind == "identifier" and value == "history":
            if (
                values[index + 1 : index + 2] == ["."]
                and values[index + 2 : index + 3]
                and values[index + 2] in UNSAFE_HISTORY_METHODS
            ):
                raise AudienceBoundaryError(
                    f"history navigation is not allowed in local script: {script_name}"
                )
        if kind == "identifier" and value == "replaceState":
            if next_value != "(":
                raise AudienceBoundaryError(
                    f"indirect history replacement is not allowed: {script_name}"
                )
            arguments, _ = _call_arguments(tokens, index + 1)
            if len(arguments) != 3 or not _safe_replace_state_argument(arguments[2]):
                raise AudienceBoundaryError(
                    f"history.replaceState must use a same-page query or hash: {script_name}"
                )


def _validate_local_script(path, asset_root, inspected=None):
    """Read every referenced local module and reject network/navigation capabilities."""
    inspected = inspected if inspected is not None else set()
    path = Path(path).resolve()
    if path in inspected:
        return
    inspected.add(path)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AudienceBoundaryError(f"could not read local script {path.name}: {exc}") from exc

    if _absolute_urls(source):
        raise AudienceBoundaryError(f"absolute URL is not allowed in local script: {path.name}")
    _validate_script_tokens(_javascript_tokens(source), path.name)


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
    inspected_scripts = set()
    for kind, value, context in parser.references:
        if kind == "resource":
            candidate = _validate_local_resource(value, context, asset_root)
            if candidate and candidate.suffix.lower() in {".js", ".mjs"}:
                _validate_local_script(candidate, asset_root, inspected=inspected_scripts)
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
