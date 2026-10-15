---
name: release-writing
description: ZenStory AI 的发布标准与发布流程：切版本、写 CHANGELOG 与 GitHub release notes、修订往期发布、仓库改名后清理失效链接。当有人说“发个 release”“切 0.x.y”“整理 CHANGELOG”“release notes 怎么写”“把往期发布说明改一下”时使用。它规定本组织的格式与发布动作顺序；动作顺序只适用于以 vX.Y.Z tag 发版的源码与技能仓库，zenstory 产品仓库（prod-v*、cli-v*）等自有发布流程的仓库只沿用格式部分。条目本身的起草可以借助任何 changelog 生成器。
license: MIT
---

# 发布写作

统一本组织的 **CHANGELOG 与 release notes 格式**，以及**发布顺序与验收**。条目可以借助生成器起草，再按仓库实际行为核对分类与升级影响。

格式骨架与模板见 [references/templates.md](references/templates.md)。

## 1. 组织标准

| 项目 | 标准 |
|---|---|
| 小节名 | 英文，Keep a Changelog 六类：`Added` `Changed` `Deprecated` `Removed` `Fixed` `Security` |
| 小节顺序 | 按上表，没有内容的省略 |
| 正文语言 | 跟随该仓库 README 的主语言 |
| 版本标题 | `## [X.Y.Z] - YYYY-MM-DD` |
| 待发布节 | `## [Unreleased]` |
| 底部链接 | 每个版本一行 compare 链接，必须维护 |
| 版本号 | Semantic Versioning |
| release 标题 | `vX.Y.Z — 三到八个字的主题` |
| release 正文 | 20 行以内，末尾链到该 tag 的 CHANGELOG 锚点 |

英文小节配中文正文是刻意的：六个类别是语义标签，英文让它们跨仓库可比；正文是给人读的。
一个仓库内部保持一致即可。

仓库若有自己的**分级细则**（例如区分「可阻断的约束」与「可覆盖的默认做法」），保留——那是
对分类判据的细化，与六个类别不冲突。

## 2. 发布流程

本节适用于以 `vX.Y.Z` tag 发版的源码与技能仓库（组织 `.github` 仓库、各公开技能包、oh-story-dsh）。
zenstory 产品仓库不打 `vX.Y.Z`：生产发布走 `prod-v*` tag、CLI 走 `cli-vX.Y.Z`，流程以该仓库的
`docs/ops/release-ci-cd.md` 为准，只沿用第 1、3 节的格式与取舍。仓库自有发布文档（如 oh-story-dsh
的 `docs/RELEASING.md`）与本节冲突时，以仓库文档为准。

### 阶段一：确认可以发

```bash
git checkout main && git pull --ff-only
git status --porcelain                  # 必须为空
SHA=$(git rev-parse HEAD)
gh run list --commit "$SHA" --workflow <CI 工作流文件> --event push \
  --json workflowName,status,conclusion  # 每个 CI 工作流都要有这个提交的 completed / success
```

CI 工作流看 `.release/policy.json` 的 `ciWorkflows`；没有这个文件就看 `.github/workflows/` 里
push 到 main 触发的校验工作流，逐个查。不要用 `--branch main --limit 1`：它返回 main 上最近
一次任意工作流（定时巡检、发布任务），不一定是这个提交的 CI。

跑仓库自己定义的发布检查（`CONTRIBUTING.md` 里通常有），不要只跑单元测试。

**先确认测试结果，再 push。** 两步分开运行，避免用分号或无条件后续命令在测试失败后继续推送。

### 阶段二：写 CHANGELOG

起草可借助生成器，再按 [第 1 节](#1-组织标准) 校格式：把 `## [Unreleased]` 切成
`## [X.Y.Z] - YYYY-MM-DD`、补底部 compare 链接、在上方留一个新的空 Unreleased 节。

**版本号与 CHANGELOG 同一提交改齐。** 仓库有 `.release/policy.json` 时，把其 `versionFiles` 列出的
每一处（文本文件整份内容，或 JSON 文件里 `pointer` 指向的字段）都改成 `X.Y.Z`。漏改或改错，tag 推上去
后发布工作流会拒发（多处不一致报 `repository version metadata disagrees`，全部未改报
`stable tag does not equal repository version`），而已推的 tag 不能删改。
没有这个文件的仓库按其发布文档改版本（如 oh-story-dsh 改根与包版本）。

### 阶段三：走 PR，不要直接推 main

```bash
git checkout -b release/vX.Y.Z
git add CHANGELOG.md <versionFiles 里的每个文件> && git commit -m "release: X.Y.Z"
python3 <组织 .github 仓库>/scripts/source_release.py check --root . --sha "$(git rev-parse HEAD)" \
  --tag vX.Y.Z --repository <owner>/<repo>  # 有 .release/policy.json 时自检：版本、tag、CHANGELOG 标题须一致
git push -u origin release/vX.Y.Z
gh pr create --base main --title "release: X.Y.Z" --body "<要点与升级影响>"
gh pr checks <PR>                       # 全部 SUCCESS 再合
gh pr merge <PR> --squash --delete-branch
```

发布提交走同一条路径，分支保护、CI 和评审才仍然生效。

### 阶段四：打 tag

tag **必须打在已合并的 main 上**，否则它指向一个不在主线上的提交。打之前按阶段一的命令确认
这个合并提交（`git rev-parse HEAD`）的 CI 全绿：发布工作流只认这个 SHA 的 CI，不会退回更早的成功记录。

```bash
git checkout main && git pull --ff-only
git tag -a vX.Y.Z -m "vX.Y.Z"           # 带注释的 tag，不用轻量 tag
git push origin vX.Y.Z
```

### 阶段五：建 release

先看 `.github/workflows/` 里有没有推 `v*` tag 就触发的发布工作流（`grep -l 'tags:' .github/workflows/*`；
技能包仓库与 oh-story-dsh 都是 `release.yml`）。

**有**：不要 `gh release create`。工作流会自己建 Release（标题不带主题，正文是自动生成的）并上传附件，
手建要么报已存在，要么与它抢跑。等它成功跑完，再改标题和正文：

```bash
gh run list --commit "$(git rev-parse 'vX.Y.Z^{commit}')" --workflow release.yml \
  --json status,conclusion               # 等到 completed / success；失败就停下排查，不要手建 Release
gh release edit vX.Y.Z --title "vX.Y.Z — <主题>" --notes-file notes.md   # notes.md 按 references/templates.md 骨架写
```

**没有**（如组织 `.github` 仓库）：自己建。

```bash
gh release create vX.Y.Z --title "vX.Y.Z — <主题>" --notes "$(cat <<'EOF'
<骨架见 references/templates.md>
EOF
)"
```

### 阶段六：发完验收

```bash
OWNER=<owner>; REPO=<repo>; V=X.Y.Z
git ls-remote --tags origin "refs/tags/v$V"
gh release view "v$V" --repo "$OWNER/$REPO" --json body --jq '.body' | wc -l   # ≤20
gh release view "v$V" --repo "$OWNER/$REPO" --json assets --jq '.assets[].name' # 有发布工作流时，它上传的附件都在
```

实际统计正文行数，超过 20 行就精简背景与根因叙述，保留用户可见变化和升级动作。

再手点一次正文里的 CHANGELOG 锚点和安装命令：锚点拼错、命令指向旧命名空间，是发完立刻
能看出来的两处。

### 出问题了

**已发布的 tag 不要删改**，往前修：release notes 用 `gh release edit` 直接改；代码问题发
补丁版本并在新版导语里说明规避方式；`gh release delete` 只在发布后极短时间内、确认无人
取用时考虑。

## 3. 哪些内容不进对外产物

读者一种在决定要不要用，一种在判断升级会不会弄坏东西。**判据是：读者需不需要据此采取行动。**

需要，就必须写——破坏性变更、升级步骤、能力退化，一条都不能省，隐瞒才是真问题。

不需要的，不要写：

- **「已知缺口」清单**。发布前实跑发现的问题，先核实（相当一部分是误读，读一遍那条规则或
  跑一次 `--help` 就能排除），**站得住的在发布前修掉**，而不是写成章节。这类问题通常改动
  很小；真正大到修不动的，单独开 issue 并在发布中提一句。
- 与竞品的对比；内部质量发现（工具与产物不匹配、文档自相矛盾）——那些是 issue 的内容。
- 自我批评的语气（「一直在空转」「此前零覆盖」）。同一件事总能只陈述结果：写「补齐了 X」，
  而不是「X 一直是坏的」。

**版本号与内容矛盾时要明说。** 补丁号不传达破坏性变更，这一版若有 `Changed`，导语要把它说清楚。
**别用固定套话开场**——「补丁号不传达这一点，故在此明说」这类句子把读者第一眼看到的位置浪费在
谈版本号上。第一句写读者要做的动作，第二句写为什么：

```markdown
升级后必须重新生成配置，旧配置会被拒绝。本版收紧了 X，补丁号不代表可以无脑升级。
```

判据是这一句能不能直接照着做。做不到就是还没写清楚。

## 4. 修订往期与改名清理

往期 release 页长期被人读到，可以修订：保留**实际做了什么**和**升级影响**，删掉取证叙事
与自我批评，压到 20 行内。**CHANGELOG 的历史小节不要回头改写**——release notes 是展示面，
CHANGELOG 是账本；改名导致的链接失效属于例外，那是修复失效引用。

仓库或组织改名后，往期 release notes 不会自动更新，安装命令会继续指向旧名字。`OLD` 与 `NEW`
都写完整命名空间，查找和替换用同一对，正文没变就不回写：

```bash
OWNER=<owner>; REPO=<repo>
OLD=<旧owner>/<旧repo>; NEW=$OWNER/$REPO   # 只改了组织名时：OLD=<旧owner>; NEW=$OWNER
OLD_RE=$(printf '%s' "$OLD" | sed 's/[].[*^$\\]/\\&/g')   # 转义正则元字符
# 两侧须是名字以外的字符，oh-story-dsh、goldorg 这类同前缀的名字才不会被误改
RE="s#(^|[^A-Za-z0-9_.-])${OLD_RE}([^A-Za-z0-9_-]|\$)#\1${NEW}\2#g"
for t in $(gh release list --repo "$OWNER/$REPO" --limit 100 --json tagName --jq '.[].tagName'); do
  gh release view "$t" --repo "$OWNER/$REPO" --json body --jq '.body' > /tmp/b.txt
  sed -E -e "$RE" -e "$RE" /tmp/b.txt > /tmp/n.txt   # 跑两遍：只隔一个字符的相邻两处，第一遍会漏掉后一处
  cmp -s /tmp/b.txt /tmp/n.txt || { gh release edit "$t" --repo "$OWNER/$REPO" --notes-file /tmp/n.txt \
    && echo "$t 已修正"; }
done
```

顺带查标题：

```bash
gh release list --repo "$OWNER/$REPO" --limit 100 --json tagName,name \
  --jq '.[] | select((.name | contains("—")) | not) | "无主题: \(.tagName)"'
```

## 5. 把一个仓库迁到本标准

**不重写历史，从下一次发版开始切**，一次到位，不要分几版慢慢改。

1. CHANGELOG 头部补 Keep a Changelog 与 Semantic Versioning 声明（模板见 references）
2. 待发布节统一为 `## [Unreleased]`
3. 新版本节按 `## [X.Y.Z] - YYYY-MM-DD`、英文小节名写；历史小节保持原样
4. 补底部链接引用；历史版本标题没有方括号时，只补新版本的
5. 往期 release 标题补主题，跑第 4 节的改名审计

**compare 链接按实际 tag 相邻关系生成，不是按 CHANGELOG 标题相邻**——两者可能不一致
（曾遇到某版本有 tag、有 release，却没有 CHANGELOG 小节，按标题生成会跨掉一个版本）。
