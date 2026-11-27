from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "skill-polish" / "scripts" / "skill_check.py"

spec = importlib.util.spec_from_file_location("skill_check", SCRIPT_PATH)
assert spec and spec.loader
skill_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skill_check)


class SkillCheckTests(unittest.TestCase):
    def test_all_shared_skills_pass_structural_checks(self) -> None:
        manifest = json.loads((REPO_ROOT / ".clawhub" / "publish.json").read_text(encoding="utf-8"))
        expected = sorted(Path(item["path"]).name for item in manifest["skills"])
        skills = skill_check.discover_skills([str(REPO_ROOT / "skills")])
        self.assertEqual([p.name for p in skills], expected)
        for sdir in skills:
            report = skill_check.check_skill(sdir)
            self.assertTrue(report["ok"], f"{sdir.name} errors: {report['errors']}")

    def test_guards_bite_on_common_skill_defects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sdir = Path(tmp) / "demo-skill"
            (sdir / "references").mkdir(parents=True)
            (sdir / "SKILL.md").write_text(
                "---\n"
                "name: demo-skill\n"
                "description: |\n"
                "  multiline block scalar\n"
                "---\n\n"
                "# Demo\n\n"
                "See [missing](references/missing.md), [bad anchor](references/ref.md#nope), "
                "[bad html](references/view.html#missing-id), and [escape](../outside.md).\n"
                "Local leak: /Users/alice/secret/project\n",
                encoding="utf-8",
            )
            (sdir / "references" / "ref.md").write_text("# Real Heading\n", encoding="utf-8")
            (sdir / "references" / "view.html").write_text(
                '<!doctype html><section id="present"></section>', encoding="utf-8"
            )
            (sdir / "references" / "orphan.md").write_text("# Unreferenced\n", encoding="utf-8")

            report = skill_check.check_skill(sdir)
            self.assertFalse(report["ok"])
            joined = "\n".join(report["errors"])
            self.assertIn("YAML block scalar", joined)
            self.assertIn("broken relative link 'references/missing.md'", joined)
            self.assertIn("broken Markdown anchor '#nope'", joined)
            self.assertIn("broken HTML id '#missing-id'", joined)
            self.assertIn("escapes skill directory", joined)
            self.assertIn("machine-local user path", joined)
            self.assertIn("orphan file 'references/orphan.md'", joined)

    def test_backtick_paths_slug_hyphens_and_html_comments(self) -> None:
        self.assertEqual(skill_check.github_slug("A - B"), "a---b")
        self.assertEqual(skill_check.github_slug("① 新版评分表"), "新版评分表")
        with tempfile.TemporaryDirectory() as tmp:
            sdir = Path(tmp) / "bt-check"
            (sdir / "references").mkdir(parents=True)
            (sdir / "SKILL.md").write_text(
                "---\n"
                "name: bt-check\n"
                "description: 单行说明。\n"
                "---\n\n"
                "# Title\n\n"
                "Valid anchor [ok](references/guide.md#a---b).\n"
                "Broken backtick `references/ghost.md` and escaping `../leak.md`.\n"
                "Windows forward-slash path C:/Users/bob/work/file.txt\n"
                "<!-- [commented broken link](references/ignored.md) -->\n",
                encoding="utf-8",
            )
            (sdir / "references" / "guide.md").write_text("## A - B\n", encoding="utf-8")
            report = skill_check.check_skill(sdir)
            self.assertFalse(report["ok"])
            joined = "\n".join(report["errors"])
            self.assertNotIn("guide.md#a---b", joined)
            self.assertNotIn("ignored.md", joined)
            self.assertIn("broken backticked path 'references/ghost.md'", joined)
            self.assertIn("backticked path '../leak.md' escapes skill directory", joined)
            self.assertIn("machine-local user path", joined)

    def test_prose_advisories_detect_jumps_and_not_is_outside_anti_examples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sdir = Path(tmp) / "clean-check"
            sdir.mkdir(parents=True)
            (sdir / "SKILL.md").write_text(
                "---\n"
                "name: clean-check\n"
                "description: 单行说明。\n"
                "---\n\n"
                "# 标题\n\n"
                "详细规则见第 4 节，输出字段同上表。对比改前改后可知，目标不是堆砌辞藻，而是讲清事实。\n"
                "> 普通引用块里也不是摆设，而是需要被正常扫描。\n\n"
                "- ❌ **改前**：\n"
                "  > 反例引用块里不是真正文，而是反面示范，详见上文。\n",
                encoding="utf-8",
            )
            report = skill_check.check_skill(sdir)
            self.assertTrue(report["ok"])
            self.assertEqual(report["metrics"]["crossSectionJumps"], 1)
            self.assertEqual(report["metrics"]["notIsHits"], 2)


if __name__ == "__main__":
    unittest.main()
