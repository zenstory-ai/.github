# 共享 Skills ｜ Shared skills

组织内多个仓库通用的 Agent skill。与具体业务耦合的 skill 放在它服务的那个仓库里，
只有跨仓库通用的才放这里。

Skills shared across ZenStory AI repositories. A skill coupled to one project
belongs in that project's own repository; only cross-repository skills live here.

| Skill | 用途 |
|---|---|
| [`release-writing`](release-writing/) | 组织统一的发布写作标准：CHANGELOG 条目、切版本、GitHub release notes |
| [`new-user-product-audit`](new-user-product-audit/) | 新用户产品诊断：扮演新用户操作真实浏览器试用产品、按内容类型真实创作，产出动线/指引/bug/产出质量诊断报告 |
| [`no-black-box`](no-black-box/) | 不留黑箱的交接讲解：Agent 独立做完一段工作后，按固定的八步节奏把需求背景、落地方案、验证结果和未决事项讲给使用人，产出白话的单文件 HTML（方案说明、原材料导读、确认单） |
| [`you-click-publish`](you-click-publish/) | 发帖辅助：按 x.com、linux.do 的习惯起草改写、做头图、算字数，在你已登录的浏览器里填好草稿；改稿和点发布始终由人来做，不是自动发帖 |

## 安装 ｜ Install

按你使用的 Agent 工具链接到对应的 skills 目录，例如：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD/skills/release-writing" "${CODEX_HOME:-$HOME/.codex}/skills/release-writing"
```
