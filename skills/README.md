# 共享 Skills ｜ Shared skills

组织内多个仓库通用的 Agent skill。与具体业务耦合的 skill 放在它服务的那个仓库里，
只有跨仓库通用的才放这里。

Skills shared across ZenStory AI repositories. A skill coupled to one project
belongs in that project's own repository; only cross-repository skills live here.

| Skill | 用途 |
|---|---|
| [`release-writing`](release-writing/) | 组织统一的发布写作标准：CHANGELOG 条目、切版本、GitHub release notes |

## 安装 ｜ Install

按你使用的 Agent 工具链接到对应的 skills 目录，例如：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD/skills/release-writing" "${CODEX_HOME:-$HOME/.codex}/skills/release-writing"
```
