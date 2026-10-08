# 一次性邮箱：真实注册与收验证邮件

用一次性邮箱 API 给每个 persona 注册一个全新账号，收验证邮件。下面以 [mail.tm](https://docs.mail.tm)
为例；它没有官方 SLA，取不到域名或收不到信时换同类服务（方法相同），并在报告里注明。

## 规则

- 一个 persona 一个邮箱，不复用。地址前缀带 `audit`，例如 `audit-novelist-20261008`。
- 邮箱密码与产品密码都随机生成，存 `~/.config/product-audit/<产品>-<环境>.json`，权限 `0600`，
  不进任何仓库、不进报告。
- 一次性邮箱是公开服务：**验证邮件里的链接/验证码只用于本次注册**，不要贴进报告或日志。
- 有的产品会拦截一次性邮箱域名——这本身就是一条发现（记录拦截文案是否清楚），然后改用操作者
  提供的测试邮箱。
- 轮询收件箱：每 5–10 秒一次，最多 5 分钟；记录从提交注册到收到邮件的耗时。

## mail.tm 接口

基地址 `https://api.mail.tm`，JSON 请求需带 `Content-Type: application/json`。

| 步骤 | 请求 | 说明 |
|---|---|---|
| 1 取域名 | `GET /domains` | 返回 `hydra:member[]`，取一个 `isActive` 的 `domain` |
| 2 建邮箱 | `POST /accounts` `{"address","password"}` | 成功 201；地址被占用返回 422，换前缀重试 |
| 3 取令牌 | `POST /token` `{"address","password"}` | 返回 `{"token"}`，后续请求带 `Authorization: Bearer <token>` |
| 4 列邮件 | `GET /messages` | 返回 `hydra:member[]`，含 `id`、`from`、`subject`、`createdAt` |
| 5 读邮件 | `GET /messages/{id}` | 含 `text` 与 `html`；从中提取验证链接或验证码 |

## 示例脚本

```bash
set -euo pipefail
umask 077
CRED=~/.config/product-audit/zenstory-production.json   # 运行目录与仓库之外
mkdir -p "$(dirname "$CRED")"
API=https://api.mail.tm
PERSONA=novelist
DOMAIN=$(curl -fsS "$API/domains" | jq -r '[.["hydra:member"][] | select(.isActive)][0].domain')
ADDR="audit-$PERSONA-$(date +%Y%m%d)-$RANDOM@$DOMAIN"
MAILPW=$(openssl rand -base64 18)
APPPW="Au$(openssl rand -hex 8)!9"                         # 满足常见密码规则
curl -fsS -X POST "$API/accounts" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg a "$ADDR" --arg p "$MAILPW" '{address:$a,password:$p}')" >/dev/null
jq -n --arg p "$PERSONA" --arg a "$ADDR" --arg m "$MAILPW" --arg w "$APPPW" \
  '{($p): {email:$a, mail_password:$m, app_password:$w}}' > "$CRED"
chmod 600 "$CRED"
echo "注册邮箱: $ADDR"                                       # 只打印邮箱，不打印密码
```

在浏览器里用该邮箱和 `app_password` 完成注册后，收信（新开的 shell 里先从凭据文件读回变量，
不要回显）：

```bash
API=https://api.mail.tm; PERSONA=novelist; CRED=~/.config/product-audit/zenstory-production.json
ADDR=$(jq -r --arg p "$PERSONA" '.[$p].email' "$CRED")
MAILPW=$(jq -r --arg p "$PERSONA" '.[$p].mail_password' "$CRED")
TOKEN=$(curl -fsS -X POST "$API/token" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg a "$ADDR" --arg p "$MAILPW" '{address:$a,password:$p}')" | jq -r .token)
for i in $(seq 1 30); do
  ID=$(curl -fsS "$API/messages" -H "Authorization: Bearer $TOKEN" | jq -r '.["hydra:member"][0].id // empty')
  [ -n "$ID" ] && break
  sleep 10
done
curl -fsS "$API/messages/$ID" -H "Authorization: Bearer $TOKEN" \
  | jq -r '.text' > "$RUN/logs/verify-mail.txt"             # 检查完内容后删除此文件
```

从邮件中取出验证链接，在**同一个 persona 的浏览器 session** 里打开（`AGENT_BROWSER_SESSION=<persona> agent-browser open <链接>`），
而不是用 curl 访问——验证后的落地页也是体验的一部分。

邮件本身也要评估：发件人名称是否可信、标题是否说清用途、正文语言是否与注册时一致、链接是否
可点、有效期是否说明、会不会进垃圾箱（一次性邮箱无法判断这一点，报告中注明）。

收尾：报告附录只写邮箱地址；运行结束后删除 `verify-mail.txt`。
