#!/usr/bin/env python3
"""Deterministic structural and prose-hygiene checker for Agent Skills.

Python 3.9+ standard library only. Read-only static analysis: checks SKILL.md
frontmatter, self-contained relative links, Markdown/HTML heading anchors,
file reachability (orphan detection), machine-local path leaks, character/line
attention budgets, cross-section jump phrases, and mechanical contrast density.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BLOCK_SCALAR_RE = re.compile(r"^[|>][+-]?(?:\d+)?\s*(?:#.*)?$")
EXTERNAL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"(`+)([^`]*?)\1")
HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
MD_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_ATTR_RE = re.compile(r"""\b(?:href|src)\s*=\s*["']([^"']+)["']""", re.I)
BACKTICK_PATH_RE = re.compile(
    r"`((?:(?:\.\./)+|(?:references|scripts|assets|templates|examples)/)[A-Za-z0-9_./-]+)`"
)
HEADING_RE = re.compile(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$")
LOCAL_USER_PATH_RE = re.compile(
    r"(?:/Users/(?!<|your\b|username\b|user\b)[A-Za-z0-9._-]+/"
    r"|/home/(?!<|your\b|username\b|user\b)[A-Za-z0-9._-]+/"
    r"|[A-Za-z]:[/\\]Users[/\\](?!<|your\b|username\b|user\b)[A-Za-z0-9._-]+[/\\])"
)
JUMP_RE = re.compile(
    r"(?:见第\s*[0-9一二三四五六七八九十]+\s*[节章步段部分]"
    r"|按第\s*[0-9一二三四五六七八九十]+\s*[节章步段部分]"
    r"|详见(?:上文|下文|前文|后文)"
    r"|见(?:上文|下文|前文|后文)"
    r"|如前所述"
    r"|(?:格式|字段)同上表)"
)
NOT_IS_RE = re.compile(r"(?:不是|并非)[^。！？；\n]{1,40}而是")
AI_TELL_RE = re.compile(r"(?:值得注意的是|需要注意的是|总而言之|综上所述|不难发现|众所周知|毋庸置疑)")
ANTI_EXAMPLE_MARKER_RE = re.compile(
    r"(?:❌|错误示例|反例写法|Bad\b|(?:^|[\s>*+-])(?:反例|改前|禁止句式|机械对比)[:：—\s*])"
)
PROHIBITION_LINE_RE = re.compile(r"(?:严禁|禁止)(?:写|使用|引用)")
SCARE_QUOTE_PAIR_RE = re.compile(r"“[^”\n]*”")


class HtmlIdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        for key, val in attrs:
            if not val:
                continue
            k = key.lower()
            if k in {"id", "name"}:
                self.ids.add(val)
            if k in {"href", "src"}:
                self.links.append((line, val.strip()))


def _is_cjk(ch: str) -> bool:
    return (
        ("\u4e00" <= ch <= "\u9fff")
        or ("\u3400" <= ch <= "\u4dbf")
        or ("\u3040" <= ch <= "\u30ff")
        or ("\uac00" <= ch <= "\ud7af")
    )


def github_slug(heading: str) -> str:
    text = INLINE_CODE_RE.sub(r"\2", heading)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip().lower()
    cleaned: list[str] = []
    for ch in text:
        if (ch.isascii() and ch.isalnum()) or ch in {"-", "_"} or _is_cjk(ch):
            cleaned.append(ch)
        elif ch.isspace():
            cleaned.append("-")
    return "".join(cleaned).strip("-")


def collect_md_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    in_fence = False
    fence_marker = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        m_fence = FENCE_RE.match(raw)
        if m_fence:
            marker = m_fence.group(2)
            if not in_fence:
                in_fence = True
                fence_marker = marker[0] * len(marker)
            elif raw.lstrip().startswith(fence_marker[0] * len(fence_marker)):
                in_fence = False
            continue
        if in_fence:
            continue
        m_head = HEADING_RE.match(raw)
        if m_head:
            base = github_slug(m_head.group(1))
            if not base:
                continue
            idx = counts.get(base, 0)
            counts[base] = idx + 1
            anchors.add(base if idx == 0 else f"{base}-{idx}")
    return anchors


def strip_fences(lines: list[str]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    for lineno, raw in enumerate(lines, start=1):
        m = FENCE_RE.match(raw)
        if m:
            marker = m.group(2)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                in_fence = False
            continue
        if not in_fence:
            out.append((lineno, raw))
    return out


def parse_frontmatter(skill_md: Path) -> tuple[dict[str, str], list[str], int]:
    errors: list[str] = []
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, ["SKILL.md:1 missing opening YAML frontmatter '---'"], 0
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}, ["SKILL.md:1 unclosed YAML frontmatter (missing closing '---')"], 0

    fields: dict[str, str] = {}
    current_key: str | None = None
    multiline_keys: set[str] = set()
    for lineno, raw in enumerate(lines[1:end_idx], start=2):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[0].isspace():
            if current_key:
                multiline_keys.add(current_key)
                fields[current_key] = (fields[current_key] + " " + raw.strip()).strip()
            continue
        if ":" not in raw:
            errors.append(f"SKILL.md:{lineno} malformed frontmatter line: {raw!r}")
            continue
        key, val = raw.split(":", 1)
        key = key.strip()
        val = val.strip()
        current_key = key
        if BLOCK_SCALAR_RE.match(val):
            errors.append(
                f"SKILL.md:{lineno} '{key}' uses YAML block scalar ({val}); "
                "use a single-line string for cross-host compatibility"
            )
            fields[key] = ""
        else:
            if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
                val = val[1:-1]
            fields[key] = val

    if "description" in multiline_keys:
        errors.append(
            "SKILL.md frontmatter 'description' spans multiple lines; keep it single-line (<= 1024 chars)"
        )
    return fields, errors, end_idx + 1


def clean_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    elif " " in target:
        target = target.split(" ", 1)[0].strip()
    return target


def strip_html_comments_preserve_lines(text: str) -> str:
    return HTML_COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def extract_md_references(path: Path) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    text = strip_html_comments_preserve_lines(path.read_text(encoding="utf-8"))
    lines = text.splitlines()
    links: list[tuple[int, str]] = []
    backtick_paths: list[tuple[int, str]] = []
    for lineno, raw in strip_fences(lines):
        is_anti_or_ban = bool(ANTI_EXAMPLE_MARKER_RE.search(raw) or PROHIBITION_LINE_RE.search(raw))
        if not is_anti_or_ban:
            for m in BACKTICK_PATH_RE.finditer(raw):
                candidate = m.group(1).rstrip(".,;:)")
                if (
                    "<" not in candidate
                    and ">" not in candidate
                    and "{" not in candidate
                    and "}" not in candidate
                    and "*" not in candidate
                    and "..." not in candidate
                ):
                    backtick_paths.append((lineno, candidate))
        no_code = INLINE_CODE_RE.sub("", raw)
        for m in MD_LINK_RE.finditer(no_code):
            links.append((lineno, clean_link_target(m.group(1))))
        for m in HTML_ATTR_RE.finditer(no_code):
            links.append((lineno, m.group(1).strip()))
    return links, backtick_paths


def check_skill(skill_dir: Path) -> dict[str, object]:
    skill_dir = skill_dir.resolve()
    errors: list[str] = []
    advisories: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return {
            "skill": skill_dir.name,
            "path": str(skill_dir),
            "ok": False,
            "errors": ["missing SKILL.md"],
            "advisories": [],
            "metrics": {},
        }

    fm, fm_errors, fm_end_line = parse_frontmatter(skill_md)
    errors.extend(fm_errors)
    name = fm.get("name", "")
    if not name:
        errors.append("SKILL.md frontmatter missing 'name'")
    else:
        if not SLUG_RE.fullmatch(name):
            errors.append(f"SKILL.md frontmatter name {name!r} must match ^[a-z0-9]+(-[a-z0-9]+)*$")
        if name != skill_dir.name:
            errors.append(f"SKILL.md frontmatter name {name!r} != directory name {skill_dir.name!r}")

    desc = fm.get("description", "")
    if not desc:
        errors.append("SKILL.md frontmatter missing non-empty 'description'")
    elif len(desc) > 1024:
        errors.append(f"SKILL.md frontmatter 'description' is {len(desc)} chars (limit 1024)")

    all_files: dict[str, Path] = {}
    for p in sorted(skill_dir.rglob("*")):
        if p.is_dir():
            continue
        rel_parts = p.relative_to(skill_dir).parts
        if any(part.startswith(".") or part in {"__pycache__", "node_modules"} for part in rel_parts):
            continue
        if p.suffix.lower() in {".pyc", ".pyo"}:
            continue
        all_files[p.relative_to(skill_dir).as_posix()] = p

    md_anchor_cache: dict[Path, set[str]] = {}
    html_cache: dict[Path, HtmlIdCollector] = {}

    def get_md_anchors(target_path: Path) -> set[str]:
        if target_path not in md_anchor_cache:
            md_anchor_cache[target_path] = collect_md_anchors(target_path)
        return md_anchor_cache[target_path]

    def get_html_info(target_path: Path) -> HtmlIdCollector:
        if target_path not in html_cache:
            parser = HtmlIdCollector()
            parser.feed(target_path.read_text(encoding="utf-8"))
            html_cache[target_path] = parser
        return html_cache[target_path]

    adj: dict[str, set[str]] = {rel: set() for rel in all_files}

    def validate_target(src_rel: str, src_path: Path, lineno: int, raw_target: str) -> None:
        if not raw_target or EXTERNAL_SCHEME_RE.match(raw_target):
            return
        if any(tok in raw_target for tok in ("<", ">", "{", "}", "*")):
            return
        path_part, sep, frag = raw_target.partition("#")
        frag = unquote(frag) if sep else ""
        if not path_part:
            target_file = src_path
        else:
            decoded_path = unquote(path_part.split("?", 1)[0])
            candidate = (src_path.parent / decoded_path).resolve()
            if not candidate.is_relative_to(skill_dir):
                errors.append(
                    f"{src_rel}:{lineno} link {raw_target!r} escapes skill directory (cross-skill path leak)"
                )
                return
            if not candidate.exists():
                errors.append(f"{src_rel}:{lineno} broken relative link {raw_target!r}")
                return
            if candidate.is_dir():
                index_md = candidate / "SKILL.md"
                if index_md.is_file():
                    target_file = index_md
                else:
                    return
            else:
                target_file = candidate
            target_rel = target_file.relative_to(skill_dir).as_posix()
            if target_rel in adj:
                adj.setdefault(src_rel, set()).add(target_rel)

        if frag:
            suffix = target_file.suffix.lower()
            if suffix == ".md":
                anchors = get_md_anchors(target_file)
                if github_slug(frag) not in anchors and frag.lower() not in anchors:
                    errors.append(
                        f"{src_rel}:{lineno} broken Markdown anchor '#{frag}' in {target_file.relative_to(skill_dir).as_posix()}"
                    )
            elif suffix in {".html", ".htm"}:
                info = get_html_info(target_file)
                if frag not in info.ids:
                    errors.append(
                        f"{src_rel}:{lineno} broken HTML id '#{frag}' in {target_file.relative_to(skill_dir).as_posix()}"
                    )

    file_metrics: list[dict[str, object]] = []
    total_md_non_ws_chars = 0
    jump_hits: list[str] = []
    not_is_hits: list[str] = []
    ai_tell_hits: list[str] = []
    total_scare_quotes = 0

    for rel, path in all_files.items():
        suffix = path.suffix.lower()
        if suffix in {".md", ".html", ".htm", ".py", ".js", ".sh", ".json", ".yaml", ".yml"}:
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if LOCAL_USER_PATH_RE.search(line):
                    errors.append(f"{rel}:{lineno} contains machine-local user path: {line.strip()[:100]}")
        if suffix == ".md":
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            non_ws = len(re.sub(r"\s+", "", text))
            total_md_non_ws_chars += non_ws
            file_metrics.append({"path": rel, "lines": len(lines), "nonWsChars": non_ws})

            if rel == "SKILL.md":
                if len(lines) > 500:
                    errors.append(f"SKILL.md has {len(lines)} lines (hard ceiling 500)")
                elif len(lines) > 320:
                    advisories.append(f"SKILL.md has {len(lines)} lines; check if conditional details belong in references/")

            links, bt_paths = extract_md_references(path)
            for lineno, target in links:
                validate_target(rel, path, lineno, target)
            for bt_lineno, bt in bt_paths:
                if bt.startswith("../"):
                    cand = (path.parent / bt).resolve()
                    if not cand.is_relative_to(skill_dir):
                        errors.append(
                            f"{rel}:{bt_lineno} backticked path {bt!r} escapes skill directory (cross-skill path leak)"
                        )
                        continue
                    resolved_bt = cand
                else:
                    local_cand = (path.parent / bt).resolve()
                    root_cand = (skill_dir / bt).resolve()
                    resolved_bt = local_cand if (local_cand.is_relative_to(skill_dir) and local_cand.exists()) else root_cand
                if not resolved_bt.is_relative_to(skill_dir):
                    errors.append(
                        f"{rel}:{bt_lineno} backticked path {bt!r} escapes skill directory (cross-skill path leak)"
                    )
                elif not resolved_bt.exists():
                    errors.append(f"{rel}:{bt_lineno} broken backticked path {bt!r}")
                elif resolved_bt.is_file():
                    bt_rel = resolved_bt.relative_to(skill_dir).as_posix()
                    if bt_rel in adj:
                        adj.setdefault(rel, set()).add(bt_rel)

            clean_lines = strip_html_comments_preserve_lines(text).splitlines()
            last_was_anti = False
            for lineno, raw in strip_fences(clean_lines):
                if rel == "SKILL.md" and lineno <= fm_end_line:
                    continue
                stripped = raw.lstrip()
                if not stripped:
                    continue
                is_bq = stripped.startswith(">")
                line_has_anti = bool(ANTI_EXAMPLE_MARKER_RE.search(raw))
                if is_bq:
                    if last_was_anti or line_has_anti:
                        last_was_anti = True
                        continue
                else:
                    last_was_anti = line_has_anti
                    if line_has_anti:
                        continue

                prose_raw = re.sub(r"^(?:\s*>\s*)+", "", raw) if is_bq else raw
                no_code = INLINE_CODE_RE.sub("", prose_raw)
                if JUMP_RE.search(no_code):
                    jump_hits.append(f"{rel}:{lineno}")
                if NOT_IS_RE.search(no_code):
                    not_is_hits.append(f"{rel}:{lineno}")
                if AI_TELL_RE.search(no_code):
                    ai_tell_hits.append(f"{rel}:{lineno}")
                total_scare_quotes += len(SCARE_QUOTE_PAIR_RE.findall(no_code))

        elif suffix in {".html", ".htm"}:
            info = get_html_info(path)
            for lineno, target in info.links:
                validate_target(rel, path, lineno, target)

    # BFS reachability from SKILL.md (up to 2 hops for references, scripts, assets)
    visited: dict[str, int] = {"SKILL.md": 0}
    queue: deque[str] = deque(["SKILL.md"])
    while queue:
        cur = queue.popleft()
        depth = visited[cur]
        for nxt in adj.get(cur, set()):
            if nxt not in visited:
                visited[nxt] = depth + 1
                queue.append(nxt)

    for rel in sorted(all_files):
        if rel == "SKILL.md" or Path(rel).name.lower().startswith("license"):
            continue
        if rel not in visited:
            errors.append(f"orphan file {rel!r} is never linked or referenced from SKILL.md")
        elif visited[rel] > 2:
            advisories.append(f"{rel!r} is {visited[rel]} hops away from SKILL.md (prefer <= 2 hops)")

    if jump_hits:
        advisories.append(
            f"cross-section jump phrases ({len(jump_hits)}): {', '.join(jump_hits[:8])}"
            + (" ..." if len(jump_hits) > 8 else "")
        )
    if not_is_hits:
        advisories.append(
            f"mechanical '不是…而是…' contrast ({len(not_is_hits)}): {', '.join(not_is_hits[:8])}"
            + (" ..." if len(not_is_hits) > 8 else "")
        )
    if ai_tell_hits:
        advisories.append(
            f"AI-tell transition phrases ({len(ai_tell_hits)}): {', '.join(ai_tell_hits[:8])}"
            + (" ..." if len(ai_tell_hits) > 8 else "")
        )

    quote_per_k = round(total_scare_quotes * 1000.0 / max(1, total_md_non_ws_chars), 2)
    if quote_per_k > 3.0:
        advisories.append(
            f"curly double-quote density is {quote_per_k}/1k chars (> 3.0); check for unnecessary scare quotes"
        )

    skill_md_metric = next((m for m in file_metrics if m["path"] == "SKILL.md"), {"lines": 0, "nonWsChars": 0})
    return {
        "skill": skill_dir.name,
        "path": str(skill_dir),
        "ok": len(errors) == 0,
        "errors": errors,
        "advisories": advisories,
        "metrics": {
            "fileCount": len(all_files),
            "mdFileCount": len(file_metrics),
            "skillMdLines": skill_md_metric["lines"],
            "skillMdNonWsChars": skill_md_metric["nonWsChars"],
            "totalMdNonWsChars": total_md_non_ws_chars,
            "crossSectionJumps": len(jump_hits),
            "notIsHits": len(not_is_hits),
            "aiTellHits": len(ai_tell_hits),
            "scareQuotesPer1kChars": quote_per_k,
            "files": file_metrics,
        },
    }


def discover_skills(targets: list[str]) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for raw in targets:
        p = Path(raw).resolve()
        if not p.exists():
            raise SystemExit(f"path does not exist: {raw}")
        if (p / "SKILL.md").is_file():
            if p not in seen:
                seen.add(p)
                found.append(p)
            continue
        if p.is_file() and p.name == "SKILL.md":
            parent = p.parent
            if parent not in seen:
                seen.add(parent)
                found.append(parent)
            continue
        for marker in sorted(p.rglob("SKILL.md")):
            rel_parts = marker.relative_to(p).parts
            if any(part.startswith(".") for part in rel_parts):
                continue
            parent = marker.parent.resolve()
            if parent not in seen:
                seen.add(parent)
                found.append(parent)
    if not found:
        raise SystemExit("no skill directories containing SKILL.md found")
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Static structure and prose-hygiene check for Agent Skills.")
    ap.add_argument("paths", nargs="+", help="Skill directory or parent skills/ root to inspect")
    ap.add_argument("--json", action="store_true", help="Emit JSON report")
    args = ap.parse_args(argv)

    skills = discover_skills(args.paths)
    results = [check_skill(s) for s in skills]
    all_ok = all(bool(r["ok"]) for r in results)

    if args.json:
        print(json.dumps({"ok": all_ok, "skills": results}, ensure_ascii=False, indent=2))
        return 0 if all_ok else 1

    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        m = r["metrics"]
        print(
            f"[{status}] {r['skill']}  "
            f"(files={m.get('fileCount', 0)}, SKILL.md={m.get('skillMdLines', 0)}L/{m.get('skillMdNonWsChars', 0)}c, "
            f"total_md={m.get('totalMdNonWsChars', 0)}c, jumps={m.get('crossSectionJumps', 0)}, "
            f"not_is={m.get('notIsHits', 0)}, quotes/1k={m.get('scareQuotesPer1kChars', 0)})"
        )
        for err in r["errors"]:
            print(f"  ERROR: {err}")
        for adv in r["advisories"]:
            print(f"  WARN:  {adv}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
