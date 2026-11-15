# ZenStory 运行须知（开跑前读）

本文件仅交代环境入口、访问方式、账号策略与安全红线，不剧透工作台内部设计。产品定位、功能布局、完整套餐权益与刻意的产品策略见 [zenstory-facts.md](zenstory-facts.md)，**必须在第一轮盲测全部结束后才打开**。下文列出的免费消息条数仅用于开跑前排任务预算；第一轮评估「额度与升级」体验时，仍只按页面实际展示的信息做判断。

---

## 1. 环境与到达路径

| 环境 | 官网地址 | 应用地址 | 运行说明 |
|---|---|---|---|
| `production` | `https://zenstory.ai` | `https://app.zenstory.ai` | 线上真实环境，**必须获操作者明确授权后方可运行** |
| `staging` | `https://geo-preview.zenstory.ai` | `https://app-preview.zenstory.ai` | 均受 Vercel Deployment Protection 保护；禁用真实付费模型、OAuth 与真实支付 |

- **两条到达入口都要测**：先从官网点进应用（核对官网宣传承诺与进入应用后的衔接），再单独打开应用未登录首页做五秒测试（若 `staging` 只获授权测应用端，在报告「假设与范围」中注明）。
- **`staging` 覆盖边界**：按 `zenstory` 仓库规范，`staging` 禁用真实大模型调用以免产生测试账单，且闲置时拆书后台 worker 可能处于暂停状态。因此 `staging` 只测到达、注册验证、引导动线、界面交互与移动端布局；真实创作产出质量须在获授权的 `production` 环境评测，无授权时将核心创作质量标为「未覆盖：staging 未启用真实模型」。

---

## 2. 访问受保护的 `staging` 环境

直接访问预览域名会跳往 Vercel 登录拦截页。使用以下方式注入短期 OIDC 访问头，**严禁在终端打印、日志或截图中暴露令牌**：

- 接口探活与排障：用 `vercel curl` 代替裸 `curl`。
- 浏览器会话：在已关联正确 Vercel 项目的 `zenstory/apps/web` 目录下（未关联时请维护者提供项目配置，不擅自新建或改绑项目），用 `vc env run` 为对应源注入 `x-vercel-trusted-oidc-idp-token` 请求头（注意请求头按域名源隔离，分别测 `geo-preview` 与 `app-preview` 时需对各自源执行，且头名称不可误写为 `x-vercel-oidc-token`）：

```bash
vc env run -- sh -c \
  'test -n "$VERCEL_OIDC_TOKEN" && agent-browser --session "$2" open "$1" \
     --headers "{\"x-vercel-trusted-oidc-idp-token\":\"$VERCEL_OIDC_TOKEN\"}"' \
  sh https://app-preview.zenstory.ai novelist
```

随后在同一 `--session <persona>` 下继续后续命令；若中途令牌过期重回拦截页，重新执行上式刷新即可。

---

## 3. 账号、免费配额预算与安全边界

- **注册与测试号**：`production` 优先按 [disposable-inbox.md](disposable-inbox.md) 用一次性邮箱真实注册（验证方式为 6 位数字邮件验证码）。部分一次性邮箱域名可能命中环境配置的注册拦截名单（返回 400 并提示更换邮箱）——此时记录页面提示语是否清楚，然后改用其他可用域名或操作者提供的测试邮箱，不把拦截策略本身记为缺陷。若注册页出现邀请码输入框，记录是否必填与说明清晰度，不向他人索要邀请码。`staging` 可直接使用操作者提供的预验证测试账号文件（权限 `0600`），此时将「注册与验证」标为「未覆盖」。
- **命名标记**：账号昵称统一为 `audit-<persona>-<YYYYMMDD>`，新建项目名称统一加 `[audit]` 前缀。
- **免费配额排期红线**：
  - 免费版单账号每北京时间自然日限 **3 条 AI 消息**（右侧对话发送消息与编辑器内选中文字点**「去 AI 味」**均计入这 3 条额度）；
  - 同一客户端公网 IP（IPv6 按 `/64`）每北京时间自然日跨免费账号共享上限为 **最多 3 个免费账号、合计 9 条 AI 消息**。
  - 单 persona 当日 3 条用尽即停，绝不靠换号绕过单号上限（多角色同日同机开跑时，总免费角色数不超过 3 个）。
- **零支付、零打扰与收尾清理**：走到支付页前即停，绝不扫码或付款；不向页面内的「反馈 / 联系我们 / 客服邮箱」发送测试信息；结束时删除 `[audit]` 测试项目（或保留并在报告附录逐一列出）。
