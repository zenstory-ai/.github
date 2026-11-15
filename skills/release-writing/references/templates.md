# CHANGELOG 与 Release Notes 骨架模板

供撰写或迁移版本记录时直接复制使用。

---

## 1. 六类英文小节词表

小节名固定用英文并按以下顺序排列，没有内容的小节直接省略，不留空标题；正文语言跟随仓库 `README` 主语言，同一仓库内列表或段落体例保持统一：

| 小节名 | 归类边界 |
|---|---|
| `Added` | 新功能、新能力、新增可选项 |
| `Changed` | 既有行为调整；**凡收紧校验导致旧输入/旧配置被拒的改动必须归入此类** |
| `Deprecated` | 标记后续版本移除、当前仍可用的接口或参数 |
| `Removed` | 已删除的公开接口、命令或配置项 |
| `Fixed` | 修复缺陷、放宽过严限制、修正文档与实际实现偏差 |
| `Security` | 安全漏洞或权限边界修补 |

---

## 2. 新建 `CHANGELOG.md` 头部模板

中文仓库：
```markdown
# Changelog

本文件记录本项目所有值得注意的变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]
```

英文仓库：
```markdown
# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
```

---

## 3. 单版本 `CHANGELOG` 小节与底部 Compare 链接示例

```markdown
## [0.4.0] - 2026-07-27

<2–4 行导语：概括本版重心及是否需要迁移操作；含破坏性变更时在此首句点明。>

### Added

**支持 Windows 原生环境**。目录访问改为双后端实现，并在打开前后核对文件身份。

### Changed

**任务准备强制核验来源条目**。`prepare` 现要求传入 `source_entry` 指向对应标题并比对正文，任一不一致即拒绝执行。

*升级*：旧版创建的任务若缺少 `source_entry` 将无法继续运行，补齐该字段并保持两处正文一致即可。

### Fixed

**修复长文档面板无法纵向滚动**。补齐正文容器收缩属性，消除长段落撑出的页面横向滚动条。
```

文件末尾必须同步维护方括号引用链接（每次发版新增一行，并将 `[Unreleased]` 起点推进到最新 tag；若早期历史版本标题未加方括号，只维护新版即可）：

```markdown
[Unreleased]: https://github.com/<owner>/<repo>/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/<owner>/<repo>/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/<owner>/<repo>/compare/v0.3.2...v0.3.3
```

---

## 4. GitHub Release Notes 骨架（全文 ≤ 20 行）

标题格式：`vX.Y.Z — 三到八个字的主题`

````markdown
<一两句交代本版重点，以及升级是否需要手动迁移。>

### 主要变化

- **加粗要点标题**。一句话写清用户可感知的变化与适用边界。

### 升级提示

<无破坏性变更时整节省掉；有迁移要求时直写用户操作步骤。>

```bash
<最新命名空间下的安装或升级命令>
```

完整变更见 [CHANGELOG](https://github.com/<owner>/<repo>/blob/vX.Y.Z/CHANGELOG.md#xyz---yyyy-mm-dd)。
````

锚点拼法：`## [0.4.0] - 2026-07-27` 对应 `#040---2026-07-27`（去掉方括号与小数点，空格与短横线保留为连字符；发版后务必点开链接实测一次）。

---

## 5. 高频踩坑速查

- **把收紧校验塞进 `Fixed`**：导致用户按无感补丁升级后在线上被拒。
- **安装命令残留改名前的旧仓库名**：改名后往期 Release 不会自动刷新，必须跑改名清理脚本替换。
- **Release 正文照搬整节 CHANGELOG 或不写主题标题**：几百行流水账失去摘要意义，纯版本号列表无法检索重点。
- **CHANGELOG 链接写成 `/blob/main/CHANGELOG.md`**：后续合入新内容后行号与上下文漂移，必须固定链向 `/blob/vX.Y.Z/CHANGELOG.md#...`。
