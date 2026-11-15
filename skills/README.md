# 共享 Skills ｜ Shared skills

组织内多个仓库通用的 Agent skill。与具体业务耦合的 skill 放在它服务的那个仓库里，
只有跨仓库通用的才放这里。

Skills shared across ZenStory AI repositories. A skill coupled to one project
belongs in that project's own repository; only cross-repository skills live here.

| Skill | 用途 |
|---|---|
| [`release-writing`](release-writing/) | 组织统一的发布写作标准：CHANGELOG 条目、切版本、GitHub release notes |
| [`new-user-product-audit`](new-user-product-audit/) | 新用户产品诊断：扮演新用户操作真实浏览器试用产品、按内容类型真实创作，产出动线/指引/bug/产出质量诊断报告 |
| [`no-black-box`](no-black-box/) | 不留黑箱的交接讲解：Agent 独立完成一段复杂工作后，按五段线性结构把业务背景、材料底账、逐项算账对比、验证结果与待拍板事项讲透，产出一份可自读也可投屏转发的讲解文档，按需配套确认单，并在对话里单独交付沟通口径与内部细节 |
| [`prose-gap-polish`](prose-gap-polish/) | 文案与方案精修：合并短碎句、去除自造词与防御性赘述、消除歧义，补齐信息断点并修复逻辑断点 |
| [`skill-polish`](skill-polish/) | Skill 精简与重构：消除跨节跳转与重复板块，收敛碎片参考文件，砍掉低信号说教并回查守住硬性操作约束，清理直译黑话与模板污染，校准门禁脚本与真实代码事实 |

## 安装 ｜ Install

ClawHub 发布后可以按需安装单个 skill，例如：

```bash
clawhub install @worldwonderer/prose-gap-polish --version 1.0.0
```

也可以克隆本仓库，按你使用的 Agent 工具链接到对应的 skills 目录，例如：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD/skills/release-writing" "${CODEX_HOME:-$HOME/.codex}/skills/release-writing"
```

五个共享 skill 的版本、文件清单和发布入口见 [`.clawhub/`](../.clawhub/)。
