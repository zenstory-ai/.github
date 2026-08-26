---
name: release-writing
description: 写 CHANGELOG 条目、切版本、写与修订 GitHub release notes。当有人说“发个 release”“切 0.x.y”“整理 CHANGELOG”“这条算破坏性变更还是修复”“release notes 怎么写”“把往期发布说明改一下”，或仓库改名后要清理旧链接时使用。它决定一条改动归入哪个小节、写多长、以及哪些内容该出现在对外产物里；不替代目标仓库自己的贡献规则与测试要求。
license: MIT
---

# 发布写作

CHANGELOG 与 release notes 往往是一个仓库**唯一面向陌生读者**的产物。读者有两种：一种正在
决定要不要用这个项目，一种已经在用、需要判断这次升级会不会弄坏他的东西。

两种人要的东西不同，但都不是你的取证过程。

## 目录

1. [组织标准](#1-组织标准)
2. [发布流程](#2-发布流程)
3. [判断这条改动的分级](#3-判断这条改动的分级)
4. [写 CHANGELOG 条目](#4-写-changelog-条目)
5. [切版本](#5-切版本)
6. [写 release notes](#6-写-release-notes)
7. [发布前检查](#7-发布前检查)
8. [修订往期 release 与改名清理](#8-修订往期-release-与改名清理)
9. [把一个仓库迁到本标准](#9-把一个仓库迁到本标准)

格式骨架、小节词表与新建 CHANGELOG 的模板见
[references/templates.md](references/templates.md)。

## 1. 组织标准

ZenStory AI 的仓库此前各写各的：小节名有中有英、有的整版没有小节，版本标题两种格式并存，
方括号标题缺底部链接，release 标题有的只有版本号。读者跨仓库看不出这是同一个组织的项目。

**新写的发布一律按下面这套。** 已有仓库不必回头重写历史，但**下一次发版就切过来**，
迁移步骤见 [第 8 节](#9-把一个仓库迁到本标准)。

| 项目 | 标准 |
|---|---|
| 小节名 | 英文，Keep a Changelog 六类：`Added` `Changed` `Deprecated` `Removed` `Fixed` `Security` |
| 小节顺序 | 按上表顺序，没有内容的省略 |
| 正文语言 | 跟随该仓库 README 的主语言（多数仓库是中文） |
| 版本标题 | `## [X.Y.Z] - YYYY-MM-DD` |
| 待发布节 | `## [Unreleased]` |
| 底部链接 | 每个版本一行 `compare` 链接，必须维护 |
| 版本号 | Semantic Versioning |
| release 标题 | `vX.Y.Z — 三到八个字的主题` |
| release 正文 | 10–20 行，末尾链到该 tag 的 CHANGELOG 锚点 |

**小节名用英文、正文用中文不是不一致**，是刻意的：六个类别是语义标签，英文让它们跨仓库
可比、可被工具识别；正文是写给人读的，用哪种语言取决于读者是谁。一个仓库内部保持一致即可。

仓库若有自己的**分级细则**（例如区分「可阻断的约束」与「可覆盖的默认做法」），保留——那是
对下一节判据的细化，不冲突。冲突的只有格式，格式按上表统一。

## 2. 发布流程

发布是一串**有顺序、可中断、可回滚**的动作。下面是标准流程；每一步的写作细节在后面章节。

### 阶段一：确认可以发

```bash
git checkout main && git pull --ff-only
git status --porcelain          # 必须为空
gh run list --branch main --limit 1   # main 上最近一次 CI 必须绿
```

在干净的 main 上跑一遍仓库自己定义的发布检查（`CONTRIBUTING.md` 里通常有），不要只跑单元
测试。要求端到端实跑的仓库，见 [第 7 节](#7-发布前检查)。

**测试和 push 不要串在一条命令里。** 失败时后面照样执行；分开跑，亲眼确认输出再继续。

### 阶段二：定版本与写 CHANGELOG

1. 按 [第 3 节](#3-判断这条改动的分级) 给每条改动分级，按 [第 4 节](#4-写-changelog-条目) 写条目
2. 按 [第 5 节](#5-切版本) 定版本号，把 `## [Unreleased]` 切成 `## [X.Y.Z] - YYYY-MM-DD`
3. 补底部 compare 链接，并在上方留一个空的 `## [Unreleased]`

### 阶段三：走 PR，不要直接推 main

```bash
git checkout -b release/vX.Y.Z
git add CHANGELOG.md && git commit -m "release: X.Y.Z"
git push -u origin release/vX.Y.Z
gh pr create --base main --title "release: X.Y.Z" --body "<本次发布的要点与升级影响>"
```

等 CI 全绿再合并。发布提交和普通改动走同一条路径，这样分支保护、CI 和评审都仍然生效。

```bash
gh pr checks <PR>          # 全部 SUCCESS 再往下
gh pr merge <PR> --squash --delete-branch
```

### 阶段四：打 tag

tag **必须打在已合并的 main 上**，不是本地分支——否则 tag 指向一个不在主线上的提交。

```bash
git checkout main && git pull --ff-only
git tag -a vX.Y.Z -m "vX.Y.Z"      # 用带注释的 tag，不用轻量 tag
git push origin vX.Y.Z
```

### 阶段五：建 release

```bash
gh release create vX.Y.Z --title "vX.Y.Z — <主题>" --notes "$(cat <<'EOF'
<按第 6 节的骨架写>
EOF
)"
```

正文写法见 [第 6 节](#6-写-release-notes)。

### 阶段六：发完再看一眼

```bash
OWNER=<owner>; REPO=<repo>; V=X.Y.Z
git ls-remote --tags origin "refs/tags/v$V"                    # tag 已推上去
gh release view "v$V" --repo "$OWNER/$REPO" --json name,tagName,isDraft
gh release view "v$V" --repo "$OWNER/$REPO" --json body --jq '.body' | wc -l   # 10–20 行
```

再手点一次正文里的 CHANGELOG 锚点链接和安装命令——锚点拼错和命令指向旧命名空间是最常见的
两处，发完立刻能看出来。

### 出问题了怎么办

**已发布的 tag 不要删改**——别人可能已经拉取。做法是**往前修**：

- release notes 写错：`gh release edit` 直接改，正文可以随时更新。
- CHANGELOG 写错但版本已发：在下一版修正，或直接改该版本节的措辞（**内容事实不要改写**，
  见 [第 8 节](#8-修订往期-release-与改名清理)）。
- 代码有严重问题：发一个补丁版本，并在新版的导语里说明上一版的问题与规避方式。撤回旧
  release（`gh release delete`）只在发布后极短时间内、确认无人取用时才考虑。

## 3. 判断这条改动的分级

判据只有一句：**这条改动会不会让此前能通过的东西现在通不过？**

| 情况 | 小节 |
|---|---|
| 收紧校验、新增必填字段、可选改必填、改变默认行为使旧输入被拒 | **Changed**（可能阻断既有产物） |
| 移除公开接口、命令、配置项 | **Removed** |
| 标记为将来移除但仍可用 | **Deprecated** |
| 新能力、新平台支持、新的可选项 | **Added** |
| 修 bug、放宽过严的限制、补齐文档与实现的不一致 | **Fixed** |
| 修补安全问题 | **Security** |

顺序固定：**Added → Changed → Deprecated → Removed → Fixed → Security**，没有内容的省略。

不确定时用一个具体动作检验：**拿一个上一版做出来的产物，跑一遍受影响的命令**。它被拒绝了，
就是 Changed。这比读代码推断可靠得多。

判错的代价是不对称的：把修复错记成 Changed 只是让人多看一眼；反过来，会让人在生产环境里撞墙。
**拿不准时按 Changed 写。**

## 4. 写 CHANGELOG 条目

### 长度

**一条 3–6 行。** 说清「变了什么」和「对使用者意味着什么」就停。

取证过程、实测数字、根因推理、你是怎么发现的——这些有价值，但它们的位置是 **commit message
和 PR 描述**，那里的读者是审阅代码的人。CHANGELOG 的读者在做升级决定，多余的细节只会稀释他
真正需要的那一句。

判断方法：删掉某一句，读者的**决定**会不会改变？不会，就删掉。

也不要把一整版写成一段没有小节的长文。读者需要扫描——他想知道有没有影响到自己，而不是从头
读到尾。分小节、每条加粗开头，是为了让人能跳着看。

### 写法

用**加粗一句话**点明变化，再补必要的边界与影响。Changed 条目要多一段升级说明，写清
**用户要做什么**——不是描述问题，是给动作：

```markdown
**校验器不再用固定词表阻断交付**。命中即返回非零，但它执行的是一条可覆盖的默认规则，不该
阻断。结构性检查保留，写法是否合适改由审查环节按证据处理。

**任务必须点名来源条目**。`prepare` 现在要求 `source_entry` 指向对应标题并核对正文，任一
漂移都 fail closed。

*升级*：旧版本建立的任务若缺 `source_entry` 会被拒绝。补上该字段并让两处正文一致即可，
内容本身无需重写。
```

同步上游依赖时，写清**上游版本号与提交**，让人能定位：

```markdown
- 同步 Upstream 0.7.6（`9d0bd5f`），更新统计口径与目录契约。
```

### 不要写进 CHANGELOG 的

- **「已知缺口」清单**。见 [发布前检查](#7-发布前检查)，它们应该被修掉。
- 与竞品的对比。
- 内部质量发现：工具与产物不匹配、文档自相矛盾、某处一直没人发现。这些是 issue 的内容。
- 自我批评的语气（「一直在空转」「此前零覆盖」「只能编」「静默烂了好几个版本」）。同一件事
  总能只陈述结果：写「补齐了 X」，而不是「X 一直是坏的」。

这不是粉饰。**会影响使用者的事必须照常写清楚**——破坏性变更、升级步骤、能力退化，一条都不能
省，隐瞒才是真问题。区分标准是：**读者需不需要据此采取行动**。需要就写；不需要，那就是在让
一个还没决定用不用的人读你的内部账本。

## 5. 切版本

`0.x` 阶段：有新能力或改变输出行为走 minor，纯修复走 patch。`1.0` 之后按 Semantic Versioning。

**版本号选定后，检查它和内容是否矛盾。** 补丁号不传达破坏性变更；如果这一版有 Changed 小节，
就在开头一段明说：

```markdown
**补丁号不传达这一点，故在此明说**：本版含一处会阻断既有产物的收紧，见 Changed。
```

维护者可能出于发布节奏选择保守的版本号，那是他的决定；你的职责是不让读者因此被埋伏。

切 CHANGELOG 的四步（打 tag 与建 release 见 [第 2 节](#2-发布流程) 的阶段四、五）：

1. `## [Unreleased]` 改成 `## [X.Y.Z] - YYYY-MM-DD`，日期取最后一个提交的日期
2. 在它上面补一个新的空 Unreleased 节
3. 底部链接引用加一行 `[X.Y.Z]: <repo>/compare/vPREV...vX.Y.Z`，并把 Unreleased 那行的起点
   改成新版本。**用了方括号标题就必须有这一步**，否则标题里那对括号不指向任何东西
4. 版本节开头写 2–4 行导语：这一版主要在做什么，需不需要迁移

## 6. 写 release notes

**目标长度 10–20 行。** Release 页是概览，不是 CHANGELOG 的副本——CHANGELOG 就链在下面，
需要细节的人会点进去。几十上百行的 release notes 等于没有摘要。

固定结构：

```markdown
<一到两句：这一版是什么性质，要不要迁移>

### 主要变化

- **加粗标题**。一句话说明，必要时补一句边界。（3–6 条，只留最重要的）

### 升级提示

<仅当有 Changed 时出现。写用户要做的动作，含安装或升级命令。>

完整变更见 [CHANGELOG](<repo>/blob/vX.Y.Z/CHANGELOG.md#xyz---yyyy-mm-dd)。
```

release notes 的小节名跟随正文语言（中文仓库写「主要变化」「升级提示」，英文仓库写
`Highlights`、`Upgrading`）——它们是给人读的标题，不是 CHANGELOG 那六个语义类别。

两个细节容易漏：

- **标题写成 `vX.Y.Z — 三到八个字的主题`**，让人在 release 列表里扫一眼就知道这版干了什么。
  只有版本号的标题等于没有标题。
- **CHANGELOG 链接带上版本锚点**（`#040---2026-07-27`），并**指向 tag 而不是 main**——指向
  main 的链接在下一版就失效了。

CHANGELOG 里十几条，release notes 里可能只留五条——**选择是你的工作**。挑使用者会因此改变
行为的那几条，其余的交给 CHANGELOG。

## 7. 发布前检查

先跑目标仓库自己定义的发布检查（`CONTRIBUTING.md` 或 `evaluations/`、`docs/` 里通常有），
不要只跑单元测试。有的仓库还要求一次**端到端实跑**：把代码钉在一个提交上，从零走一遍真实
流程，看哪一步需要人替系统解决问题、哪个检查器报错、文档说的做法能不能走通。

### 实跑发现问题时：修，不要写进 release

**第一步，核实它是不是真的。** 实跑报告里的「不一致」经常是误读——某条规则本来就那么要求，
某个 CLI 参数本来就存在。核实成本很低（读那条规则、跑 `--help`），而未经核实就写进对外产物
的代价很高：你会公开一个并不存在的缺陷。经验上，几条候选里能站住的往往只有一条。

**第二步，站得住的就修掉。** 确定的已知问题应该在发布前修复，而不是记进 release notes。
「已知缺口」章节会让读者把项目读成有结构性问题，而这类问题通常改动很小；真正大到修不动的，
才值得单独开 issue，并在发布中提一句。

修不动又必须让用户知道的（比如能力退化），写进升级提示，用中性陈述：说清现在的行为是什么、
影响什么，不复盘它为什么曾经不对。

### 内容层收尾

发布动作本身的收尾在 [第 2 节](#2-发布流程) 阶段六；这里只看内容：

- 每个用户可见的提交是否都在 CHANGELOG 有对应条目（纯内部重构可以合并或省略）
- 方括号版本标题是否都有底部链接引用
- 关键条目是否在压缩过程中丢失
- 安装命令、仓库链接、徽章是否仍然有效（见 [第 8 节](#8-修订往期-release-与改名清理)）

## 8. 修订往期 release 与改名清理

往期 release 页会长期被人读到，可以修订，判据与新写一致：保留每一版**实际做了什么**和
**升级影响**，删掉取证叙事与自我批评，压到 10–20 行。

```bash
gh release edit vX.Y.Z --repo <owner>/<repo> --title "vX.Y.Z — 主题" --notes "$(cat <<'EOF'
...
EOF
)"
```

**仓库或组织改名后，往期 release notes 不会自动更新。** 里面的安装命令、克隆地址和文档链接
会继续指向旧名字——GitHub 虽然重定向，但用户复制到的是错误的命名。发布新版时顺手审计一遍：

```bash
OWNER=<owner>; REPO=<repo>; OLD=<旧命名空间>
for t in $(gh release list --repo "$OWNER/$REPO" --limit 100 --json tagName --jq '.[].tagName'); do
  n=$(gh release view "$t" --repo "$OWNER/$REPO" --json body --jq '.body' | grep -c "$OLD" || true)
  [ "$n" != "0" ] && echo "$t: $n 处旧命名空间"
done
```

顺带核对长度：

```bash
for t in $(gh release list --repo "$OWNER/$REPO" --limit 100 --json tagName --jq '.[].tagName'); do
  printf "%-10s %3d 行\n" "$t" "$(gh release view "$t" --repo "$OWNER/$REPO" --json body --jq '.body' | wc -l)"
done
```

**CHANGELOG 的历史小节是另一回事：不要回头改写。** release notes 是展示面，可以随认识更新；
CHANGELOG 是账本，改了就失去了它的作用。改名导致 CHANGELOG 里链接失效属于例外——那是修复
失效引用，不是改写历史。

## 9. 把一个仓库迁到本标准

不重写历史，**从下一次发版开始切**。一次到位，不要分几版慢慢改，否则同一个文件里会长期
并存两种格式。

1. **CHANGELOG 头部**：补上 Keep a Changelog 与 Semantic Versioning 的链接（模板见
   [references/templates.md](references/templates.md)）。仓库自己的分级细则保留在这段之后。
2. **待发布节**：统一为 `## [Unreleased]`。
3. **新版本节**：按 `## [X.Y.Z] - YYYY-MM-DD` 写，小节名用英文六类。
   历史小节保持原样——它们是账本。
4. **底部链接引用**：若此前没有，一次性补齐全部历史版本的 `compare` 链接；若历史版本标题
   没有方括号，只补新版本的即可。
5. **release 标题**：本次及以后写成 `vX.Y.Z — 主题`。往期标题可按
   [第 7 节](#8-修订往期-release-与改名清理) 顺手补主题。
6. **改名清理**：跑第 7 节的审计脚本，把往期 release notes 里的旧命名空间换掉。

迁移完成后自查：

```bash
OWNER=<owner>; REPO=<repo>
# 版本标题格式是否统一
gh api "repos/$OWNER/$REPO/contents/CHANGELOG.md" --jq '.content' | base64 -d | grep -E "^## " | head
# 方括号标题是否都有底部链接
gh api "repos/$OWNER/$REPO/contents/CHANGELOG.md" --jq '.content' | base64 -d | grep -cE "^\[.*\]: https"
# release 标题是否都带主题
gh release list --repo "$OWNER/$REPO" --limit 100 --json tagName,name \
  --jq '.[] | select((.name | contains("—")) | not) | "无主题: \(.tagName)"'
```
