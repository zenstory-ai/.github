---
name: new-user-product-audit
description: 新用户产品诊断：Agent 扮演第一次来的新用户，亲手操作真实浏览器使用 ZenStory AI 的 Web 产品（以 AI 写作类产品为主），站在用户视角判断产品动线和指引是否清晰、会不会用、有没有继续用下去的欲望；再以 AI 内容创作者身份按内容类型真实完成创作任务（写一篇完整短篇、长篇写满 5 章、短剧大纲加前 3 集、改写/续写/去 AI 味），记录过程中产品展示的一切信息、bug 与输出质量，产出带证据的中文诊断报告。当有人说“模拟新用户”“新用户视角试用”“产品动线诊断”“首次体验评测”“像新用户一样把产品用一遍”“first-run audit”“new-user walkthrough”“onboarding audit”时使用。
license: MIT
---

# 新用户产品诊断

先以**零内部知识的新用户**身份从官网进入，走完注册、建项与创作，记录每一步的困惑、惊喜与离开意愿（首轮结束前严禁读源码或产品事实文档）；再以**真实创作者**身份按体裁写完作品，核对产品说明与产出质量，交付可直接排期的中文诊断报告。

产品专属运行方式与事实分别放在 `references/<产品>.md` 与 `references/<产品>-facts.md`，本文只定通用流程：

| 文件 | 何时读 |
|---|---|
| [references/zenstory.md](references/zenstory.md) | 开跑前读：环境地址、访问保护头、账号、配额与安全边界 |
| [references/zenstory-facts.md](references/zenstory-facts.md) | **首轮体验全部结束后才读**（提前读会让首轮盲测失真） |
| [references/scenario-library.md](references/scenario-library.md) | 挑选各 persona 主副创作任务、排消息预算时读 |
| [references/disposable-inbox.md](references/disposable-inbox.md) | 用一次性邮箱真实注册、收验证码或验证链接时读 |
| [references/fiction-quality-rubric.md](references/fiction-quality-rubric.md) | 对 AI 产出逐维打分并摘录证据时读 |
| [references/report-template.md](references/report-template.md) | 撰写 `$RUN/report.md` 报告时读 |

---

## 1. 开跑前确认

未指定项按默认值执行，并写进报告「假设与范围」：

| 项 | 确认内容 | 默认 |
|---|---|---|
| 目标环境 | 产品 URL、`staging` 或 `production` | `staging` |
| 线上授权 | **`production` 须获操作者明确授权**（如「可以在线上跑」），写进报告 | 无授权只跑 `staging` |
| 诊断角色 | 1–3 个 persona（身份、想写什么、熟练度、桌面/手机） | 小白短篇作者、连载网文作者、短剧编剧 |
| 创作任务 | 每 persona 从 [scenario-library.md](references/scenario-library.md) 选一个主任务 | 每种项目类型各一 |
| 账号来源 | 一次性邮箱真实注册，或操作者提供的预验证测试账号 | `staging` 可用测试号；`production` 真实注册 |
| 消耗预算 | 每 persona 的 AI 消息上限、总耗时 | 免费额度内（不够时按场景库缩减方案）；每 persona ≤ 90 分钟 |
| 操作禁区 | 不付款、不碰他人数据、不灌客服、不用真实个人信息及操作者额外禁令 | 本文全部安全红线 |

预算耗尽即停，报告写「未完成，原因：预算耗尽」，绝不超额或私自换号凑额度。

---

## 2. 无状态浏览器操作

首选 `agent-browser` CLI（**首次使用先跑 `agent-browser skills get core --full`**，按 `snapshot → @eN ref → 页面变化重拍 snapshot` 循环操作）；无此工具时用 Playwright 或内置浏览器工具，隔离与取证规则相同。

**每次 Bash 工具调用都是独立的新 shell，`export` 与 `cd` 下一条命令即失效。** 开跑只建一次运行目录（放在任何仓库之外），把字面路径写入 `env.sh` 并打印：

```bash
RUN=~/audit-runs/$(date +%Y%m%d-%H%M)-zenstory-staging   # 末尾换成 <产品>-<环境>
mkdir -p "$RUN"/shots "$RUN"/logs && chmod 700 "$RUN"
printf 'RUN=%s\nPRODUCT=zenstory\nTARGET=staging\n' "$RUN" > "$RUN/env.sh"
echo "$RUN"                                              # 后续每条命令直接引用此字面路径
```

之后**每条命令先加载 `env.sh` 字面路径**，并显式传 `--session <persona>`（禁用 `export AGENT_BROWSER_SESSION`，避免回落默认会话串 cookie；并行时只关自己的会话）：

```bash
. ~/audit-runs/20261008-1400-zenstory-staging/env.sh
agent-browser --session novelist open "https://app.example.com"
agent-browser --session novelist snapshot -i
agent-browser --session novelist screenshot "$RUN/shots/novelist-01-landing.png"
agent-browser --session novelist console > "$RUN/logs/novelist-console.txt"
agent-browser --session novelist errors  > "$RUN/logs/novelist-errors.txt"
agent-browser --session novelist network requests --status 400-599 > "$RUN/logs/novelist-failed.txt"
agent-browser --session novelist set viewport 390 844 2   # 移动端检查（或 set device "iPhone 15 Pro"）
agent-browser --session novelist close                    # 当前 persona 结束时关闭
```

- **随走随记**：关键步骤当场存图 `<persona>-<序号>-<步骤>.png` 并追加日志，不留到结尾凭记忆补；每阶段结束各收一次 `console`、`errors` 与 4xx/5xx 请求。
- **真实等待生成**：发消息或点局部改写后每 10–20 秒 `snapshot` 或 `wait --text` 一次，等到完成或报错信号，记首字与完成耗时；不连点、不重发同一消息。
- **严防凭据外泄**：报错只记状态码、接口路径与提示语，绝不把 token、cookie、验证码或验证链接写入日志；预览环境访问令牌不打印到终端。

---

## 3. 两轮盲测纪律与账号边界

1. **第一轮盲测**：体验结束前不读源码、产品文档与 `references/<产品>-facts.md`，只凭界面所见判断；页面没讲清就当新用户不知道。为每个 persona 立好人设（如手机端没耐心看教程的小白短篇作者、看重设定连贯的日更网文作者、赶制竖屏剧本的短剧编剧），用第一人称写 `$RUN/journal-<persona>.md`：
   ```text
   14:02 [到达] 首页看懂是写小说的，但「Agent」指什么？先点「免费开始」。 friction=1
   14:05 [注册] 60 秒收到验证码，填完进了引导页，挺顺。 friction=0
   ```
   每步打**摩擦分**（`0` 顺畅 / `1` 小停顿 / `2` 明显困惑但自行解决 / `3` 卡住需盲猜或求助 / `4` 放弃），标出**惊喜时刻**与**流失时刻**。
2. **第二轮事实核对**：首轮跑完再读 `references/<产品>-facts.md`，区分「设计如此但页面未讲清」与「真实功能缺陷」，记入报告「事实与观点」。
3. **账号与付费墙**：优先按 [disposable-inbox.md](references/disposable-inbox.md) 真实注册（`staging` 用预验证测试号时，「注册与验证」标为 `未覆盖`）。昵称用 `audit-<persona>-<YYYYMMDD>`，项目名加 `[audit]` 前缀，严禁使用真实客户或私人账号。凭据存仓库与运行目录外的 `~/.config/product-audit/<产品>-<环境>.json`（权限 `0600`，按 persona 分键合并写入；报告只写邮箱）。撞到额度或付费墙时，先记清拦截文案、剩余额度一致性、升级步数、价格透明度与能否退回编辑，然后**停在支付前，绝不付真钱**；仅操作者提供测试升级时才继续并注明。被拦功能标 `未覆盖`；相近免费功能分开记录，不冒充付费能力已测。

---

## 4. 九步体验旅程与观察维度

按序走完九步，每步至少一图一日志：
1. **到达（官网 → 应用）**：做首屏五秒测试（做什么的、给谁用、点哪里），核对首屏承诺与实测一致性及跳转顺畅度。
2. **注册与验证**：字段数量、报错是否说人话、验证邮件耗时与可用性、验证后落地页、有无令人费解的必填项。
3. **首项与引导**：空状态指引、项目类型区分度、引导能否跳过与找回、1 分钟内能否看懂工作区各分栏职责。
4. **核心创作**：按场景库自然提需求写到交付标准，统计 AI 消息消耗与返工轮次。
5. **AI 交互与容错**：流式进度与动作可见性、首字/完成耗时、停止与断点续写可靠性；有无复读、反复重读文件、写错文件位置或无视给定设定/约束；报错能否自然恢复且不丢稿；界面「下一步」提示是否贴合真实进度。
6. **编辑与局部精修**：手动编辑与自动保存可靠性；局部改写/续写/去 AI 味是否落回原位、可否对比撤回、是否扣额度。
7. **额度与升级**：剩余额度是否随时可见、各处数字是否一致、受限说明与升级路径是否清楚。
8. **离开重返与导出**：刷新、重开标签、重新登录后内容与选中文件是否真还在（以重进实见为准，不信表面「已保存」）；版本历史回滚与导出文件内容是否完整可用。
9. **移动端**：切手机视口走「首页 → 登录 → 开项目 → 读正文 → 发消息」，查溢出、遮挡、点不到与键盘顶走输入框。

全程记录八个维度：**动线指引**、**留存动机**（惊喜/流失点）、**可学性**（二次操作是否变快）、**信息展示**（原始 i18n 键、内部黑话、数字矛盾、中英混杂）、**Bug**（控制台错、4xx/5xx、白屏、失步）、**作品质量**（按 [fiction-quality-rubric.md](references/fiction-quality-rubric.md) 打分摘录）、**Agent 行为**（循环、漏读、越界改文）与**资源消耗**。

---

## 5. 定级、证据口径与收尾交付

- **严重度**：**P0 阻断**（无法注册/建项/完成核心创作、丢数据、越权泄露）/ **P1 严重**（主路径通但极易流失：刺眼报错、产出不可用、额度计费错）/ **P2 一般**（困惑或返工，能自行绕过）/ **P3 轻微**（文案与视觉细节）。
- **证据与状态**：每条问题备齐**复现步骤、截图相对路径、期望 vs 实际、用户后果**及脱敏日志。难复现标 `偶现（n 次里 m 次）`（不拔高定级凑数）；专程核验未重现标 `本轮未复现（n 次里 0 次）`（写进「假设与范围」，禁写「已修复」）；未定性问题标 `观察`（最高 P2）。客观事实与 persona 感受分列，标明首轮盲测或第二轮核对；既定策略与个人口味不作缺陷。测试工具自身掉线、串会话、邮箱或本机网络异常不算产品问题，标明受影响步骤，补测不了归入 `未覆盖`；产品界面里弹出的报错仍按体验问题记录（提示语写了什么、能否恢复），同一时段集中出现的合并记一条，无需深挖后端根因。
- **清理与交付自查**：不向客服/反馈入口灌测试内容（确需测反馈只发一条注明「产品诊断测试」）；清理或保留带 `[audit]` 标注的项目并列入附录；`production` 账号能删则删，不能删则在附录列邮箱提醒团队从增长/留存指标剔除。按 [report-template.md](references/report-template.md) 写出 `$RUN/report.md` 后核对：
  - [ ] P0/P1 均有截图与复现步骤；每项质量评分均附 50–150 字原文摘录。
  - [ ] 报告与日志检索过 `password`、`token`、`Bearer`、`cookie` 及验证码/验证链接确认零泄露，敏感截图已打码。
  - [ ] 继续用意愿分与流失时刻吻合；`本轮未复现`、`未覆盖` 未误写为「已修复」，工具侧故障已剥离。
