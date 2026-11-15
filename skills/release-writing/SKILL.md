---
name: release-writing
description: ZenStory AI 的发布标准与发布流程：切版本、写 CHANGELOG 与 GitHub release notes、修订往期发布、仓库改名后清理失效链接。当有人说“发个 release”“切 0.x.y”“整理 CHANGELOG”“release notes 怎么写”“把往期发布说明改一下”时使用。它规定本组织的格式与发布动作顺序；动作顺序只适用于以 vX.Y.Z tag 发版的源码与技能仓库，zenstory 产品仓库（prod-v*、cli-v*）等自有发布流程的仓库只沿用格式部分。条目本身的起草可以借助任何 changelog 生成器。
license: MIT
---

# 发布写作

统一本组织的 **CHANGELOG 与 GitHub release notes 格式**，以及 **`vX.Y.Z` 仓库的发布顺序与验收**。变更草稿可借助生成器起草，但上线前必须对照真实提交核准分类与升级影响。可直接复制的模板骨架见 [references/templates.md](references/templates.md)。

---

## 1. 组织格式标准

| 项目 | 统一标准 |
|---|---|
| 小节名与顺序 | 固定英文六类（无内容的小节直接省略）：`Added` → `Changed` → `Deprecated` → `Removed` → `Fixed` → `Security` |
| 正文语言 | 跟随该仓库 `README` 主语言（英文类别名保证跨仓语义可比，正文服务人类读者；同仓内部保持统一） |
| 版本与待发布标题 | 已发版 `## [X.Y.Z] - YYYY-MM-DD`（遵循 Semantic Versioning）；待发布 `## [Unreleased]` |
| 底部链接引用 | 文件末尾必须维护 `[Unreleased]` 与每个 `[X.Y.Z]` 的 compare 链接（按实际相邻 git tag 生成） |
| Release 标题与正文 | 标题 `vX.Y.Z — 三到八个字的主题`；正文控制在 **20 行以内**，末尾链向该 tag 的 `CHANGELOG.md` 版本锚点（禁止链向 `main`） |

核心分类红线：**凡收紧规则导致旧输入或旧配置被拒的改动一律归入 `Changed`**（绝不塞进 `Fixed` 误导用户无脑升级）；修 bug、放宽过严限制、对齐文档与实现归入 `Fixed`。仓库若另有细分约定（如区分阻断性约束与可覆盖默认做法），写在 `CHANGELOG.md` 顶部声明之后，不替代六个标准小节。

---

## 2. 六步发布流程（适用于 `vX.Y.Z` 源码与技能仓库）

本流程适用于组织 `.github` 仓库、各公开技能仓库及 `oh-story-dsh`。`zenstory` 产品仓库生产走 `prod-v*`、CLI 走 `cli-vX.Y.Z`，操作按其 `docs/ops/release-ci-cd.md` 执行，仅沿用本文的格式与内容取舍规则；其他仓库自有 `docs/RELEASING.md` 与下述步骤有差异时，以仓库自身文档为准。

### 阶段一：确认主干就绪
```bash
git checkout main && git pull --ff-only
git status --porcelain                  # 必须为空
SHA=$(git rev-parse HEAD)
gh run list --commit "$SHA" --workflow <CI 工作流文件名> --event push \
  --json workflowName,status,conclusion  # 每个必过工作流在该 SHA 上均须 completed / success
```
- 必查工作流以 `.release/policy.json` 的 `ciWorkflows` 为准；无此文件则逐个查 `.github/workflows/` 中监听 `main` push 的校验流。禁止用 `--branch main --limit 1`（会误取定时巡检等无关记录）。
- 完整跑通仓库自定的发布前检查（见 `CONTRIBUTING.md`），不只跑单测。**先看清检查通过，再执行推送**，两步拆开跑，不用分号连写以免失败后继续外推。

### 阶段二：同提交更新 CHANGELOG 与全部版本文件
1. 将 `## [Unreleased]` 切为 `## [X.Y.Z] - YYYY-MM-DD`，在其上方保留新的空 `## [Unreleased]`，并在文件末尾补齐该版本与 `Unreleased` 的 compare 链接。
2. **所有版本元数据必须在同一提交改齐**：
   - 有 `.release/policy.json` 时，将其 `versionFiles` 列出的每处（纯文本整文件内容或 JSON `pointer` 指向字段）全部改为 `X.Y.Z`（漏改或不一致会导致推 tag 后发布流硬拒发：多处不一报 `repository version metadata disagrees`，未改报 `stable tag does not equal repository version`，而已推 tag 不可删改）。
   - 含 `.clawhub/publish.json` 的技能仓库，若技能包内容或元数据相对上一版有改动，须同步递增对应技能 `version` 并运行 `clawhub_release.py lock` 刷新 `packageDigest`。

### 阶段三：提 PR 合入受保护 `main`
```bash
git checkout -b release/vX.Y.Z
git add CHANGELOG.md <所有同步更新的版本与锁文件> && git commit -m "release: X.Y.Z"
python3 <组织 .github 仓库>/scripts/source_release.py check --root . --sha "$(git rev-parse HEAD)" \
  --tag vX.Y.Z --repository <owner>/<repo>   # 含 .release/policy.json 的仓库必跑本地契约自检
git push -u origin release/vX.Y.Z
gh pr create --base main --title "release: X.Y.Z" --body "<核心变更与升级影响>"
gh pr checks <PR>                            # 确认全部 SUCCESS 后再合并
gh pr merge <PR> --squash --delete-branch
```

### 阶段四：在合并后的 `main` 上打带注释 tag
切回 `main` 拉取最新合并提交，先按阶段一命令确认**该合并提交自身 SHA** 的 CI 已全部成功（发布控制器只认当前 SHA 的 CI 证据，不回退认旧提交），再打带注释的 tag：
```bash
git checkout main && git pull --ff-only
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

### 阶段五：等待自动发版或手动创建 Release
先检查 `.github/workflows/` 是否配有监听 `v*` tag 的发布流（`grep -l 'tags:' .github/workflows/*`，技能仓与 `oh-story-dsh` 均为 `release.yml`）：
- **配有发布工作流**：**全程不要运行 `gh release create`**。等待工作流变为 `completed / success`、自动建好 Release 并传完附件后，再用 `gh release edit` 补上主题与精简正文；**若工作流失败，立即停下排查，严禁手动运行 `gh release create` 绕过门禁补建**：
  ```bash
  gh run list --commit "$(git rev-parse 'vX.Y.Z^{commit}')" --workflow release.yml --json status,conclusion
  # 确认 status=completed 且 conclusion=success；若失败则停下排查，不要手建 Release
  gh release edit vX.Y.Z --title "vX.Y.Z — <主题>" --notes-file notes.md
  ```
- **无自动发布流**（如 `.github` 仓库）：直接用 [references/templates.md](references/templates.md) 骨架运行 `gh release create vX.Y.Z --title "vX.Y.Z — <主题>" --notes-file notes.md`。

### 阶段六：发完实测验收与异常处理
```bash
OWNER=<owner>; REPO=<repo>; V=X.Y.Z
git ls-remote --tags origin "refs/tags/v$V"
gh release view "v$V" --repo "$OWNER/$REPO" --json body --jq '.body' | wc -l    # 必须 ≤ 20
gh release view "v$V" --repo "$OWNER/$REPO" --json assets --jq '.assets[].name' # 核对产物附件齐全
```
超出 20 行时砍掉背景铺垫与排查经过，只留用户感知得到的变化与升级动作；并亲手检查一次 CHANGELOG 锚点是否可跳达、安装命令是否指向最新命名空间。

**出错只往前修，绝不删改已推 tag**：文案问题直接 `gh release edit` 修正；代码缺陷切下一个补丁版并在新版导语交代规避方法（`gh release delete` 仅限刚发出极短时间内且确认无人拉取时慎重评估）。

---

## 3. 内容取舍判据

对外发布物只服务两类判断：**值不值得用、升级会不会踩坑**。凡需读者配合改配置、升依赖或调整调用方式的破坏性变更与退化，一条不漏写明；不需要读者行动的内部噪音一律剔除：

- **不列「已知缺口」章节**：发版前实测扫出的小问题先核对是否属误读，确属缺陷的当场修完再发；体量大到本版不修的，单开 Issue 跟踪并在正文中点一句即可。
- **不写竞品拉踩、内部排查流水账与自我检讨腔**：把「此前一直空转/零覆盖」改为平实陈述结果（「补齐了 X 校验」）。
- **补丁版含行为收紧时开门见山给动作**：不用「补丁号不传达此意，特此说明」之类的套话占首句；第一句直接写用户必须做什么，第二句写原因：
  ```markdown
  升级后请重新生成项目配置，缺少 `source_entry` 的旧配置将被拒绝执行。本版收紧了来源一致性校验。
  ```

---

## 4. 往期 Release 修订、改名清理与旧仓迁移

1. **往期修订边界**：往期 GitHub Release 页面可随时用 `gh release edit` 瘦身至 20 行内并补齐 `— 主题` 标题；**`CHANGELOG.md` 历史版本小节作为变更账本保持原样不重写**（仅修复仓库改名导致的死链除外）。
2. **仓库或组织改名后的批量清理脚本**（`OLD` 与 `NEW` 均用完整命名空间，两侧加字符边界防止误伤同前缀名称，连跑两遍 `sed` 覆盖仅隔单字符的相邻匹配，内容未变不触发回写）：
   ```bash
   OWNER=<owner>; REPO=<repo>
   OLD=<旧owner>/<旧repo>; NEW=$OWNER/$REPO   # 仅改组织名时：OLD=<旧owner>; NEW=$OWNER
   OLD_RE=$(printf '%s' "$OLD" | sed 's/[].[*^$\\]/\\&/g')
   RE="s#(^|[^A-Za-z0-9_.-])${OLD_RE}([^A-Za-z0-9_-]|\$)#\1${NEW}\2#g"
   for t in $(gh release list --repo "$OWNER/$REPO" --limit 100 --json tagName --jq '.[].tagName'); do
     gh release view "$t" --repo "$OWNER/$REPO" --json body --jq '.body' > /tmp/b.txt
     sed -E -e "$RE" -e "$RE" /tmp/b.txt > /tmp/n.txt
     cmp -s /tmp/b.txt /tmp/n.txt || { gh release edit "$t" --repo "$OWNER/$REPO" --notes-file /tmp/n.txt && echo "$t 已修正"; }
   done
   gh release list --repo "$OWNER/$REPO" --limit 100 --json tagName,name \
     --jq '.[] | select((.name | contains("—")) | not) | "缺主题: \(.tagName)"'
   ```
3. **旧仓一次性迁入本标准**：从下一版起一步切齐（不重写历史小节）——补齐 `CHANGELOG.md` 顶部声明与 `## [Unreleased]`，新版起用 `## [X.Y.Z] - YYYY-MM-DD` 与英文六类小节，在底部补齐新版 compare 链接（**严格按实际相邻 git tag 生成**——若某历史版本打过 tag 却漏写 CHANGELOG 小节，按标题拼接会漏掉中间版本），并跑一遍上方标题与改名巡检。
