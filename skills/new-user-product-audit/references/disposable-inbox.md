# 一次性邮箱：真实注册与收信脚本

用一次性邮箱 API 为每个真实注册的 persona 建独立收件箱。下文以 [mail.tm](https://docs.mail.tm) 为例；该服务无 SLA，取不到域名、收信超时或域名被产品注册黑名单拦截时，先记录页面提示语是否清晰，再换同类服务或操作者提供的测试邮箱。

## 1. 规则与接口速查（`https://api.mail.tm`）

- 一人一箱，不跨 persona 复用；凭据按 persona 分键**合并写入** `~/.config/product-audit/<产品>-<环境>.json`（`0600`），严禁整文件覆盖冲掉前序角色密码。
- 验证邮件保存到凭据目录下的私有临时文件，验完即删；6 位验证码、验证链接、密码和 token 绝不打印到终端或写入日志、报告。

| 步骤 | 请求 | 说明 |
|---|---|---|
| 1 取域名 | `GET /domains` | 从 `hydra:member[]` 取 `isActive` 的 `domain` |
| 2 建邮箱 | `POST /accounts` `{"address","password"}` | `Content-Type: application/json`，201 成功（422 重名换后缀） |
| 3 取令牌 | `POST /token` `{"address","password"}` | 返回 `{"token"}`，后续带 `Authorization: Bearer <token>` |
| 4 列邮件 | `GET /messages` | 每 5–10 秒查一次，最多 5 分钟，记录收信耗时 |
| 5 读邮件 | `GET /messages/{id}` | 含 `text` 与 `html`（数组）；纯 HTML 邮件 `text` 为空，须回退读 `html` |

## 2. 无状态单条执行脚本

每次 Bash 工具调用不保留变量，以下两段各自作为一条独立 `bash <<'SH' … SH` 执行，开头加载开跑时生成的 `env.sh` 字面路径。

**第一段：创建收件箱并合并写入凭据**

```bash
bash <<'SH'
set -euo pipefail
umask 077
. ~/audit-runs/20261008-1400-zenstory-staging/env.sh
PERSONA=novelist
CRED=~/.config/product-audit/$PRODUCT-$TARGET.json
API=https://api.mail.tm
mkdir -p "$(dirname "$CRED")"
[ -f "$CRED" ] || echo '{}' > "$CRED"
if jq -e --arg p "$PERSONA" 'has($p)' "$CRED" >/dev/null; then
  echo "凭据已有 ${PERSONA}，请换名或确认旧号停用后删该键" >&2; exit 1
fi
DOMAIN=$(curl -fsS "$API/domains" | jq -r '[.["hydra:member"][] | select(.isActive)][0].domain')
ADDR="audit-$PERSONA-$(date +%Y%m%d)-$RANDOM@$DOMAIN"
MAILPW=$(openssl rand -base64 18)
APPPW="Au$(openssl rand -hex 8)!9"
curl -fsS -X POST "$API/accounts" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg a "$ADDR" --arg p "$MAILPW" '{address:$a,password:$p}')" >/dev/null
jq --arg p "$PERSONA" --arg a "$ADDR" --arg m "$MAILPW" --arg w "$APPPW" \
  '. + {($p): {email:$a, mail_password:$m, app_password:$w}}' "$CRED" > "$CRED.tmp"
mv "$CRED.tmp" "$CRED" && chmod 600 "$CRED"
echo "注册邮箱: $ADDR"
SH
```

**第二段：浏览器提交注册后轮询收信（兼容纯文本与纯 HTML 邮件）**

```bash
bash <<'SH'
set -euo pipefail
umask 077
. ~/audit-runs/20261008-1400-zenstory-staging/env.sh
PERSONA=novelist; FROM_HINT=zenstory
CRED=~/.config/product-audit/$PRODUCT-$TARGET.json
API=https://api.mail.tm
ADDR=$(jq -r --arg p "$PERSONA" '.[$p].email' "$CRED")
MAILPW=$(jq -r --arg p "$PERSONA" '.[$p].mail_password' "$CRED")
TOKEN=$(curl -fsS -X POST "$API/token" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg a "$ADDR" --arg p "$MAILPW" '{address:$a,password:$p}')" | jq -r .token)
ID=""
for i in $(seq 1 30); do
  ID=$(curl -fsS "$API/messages" -H "Authorization: Bearer $TOKEN" | jq -r --arg h "$FROM_HINT" '
    [.["hydra:member"][]
     | select(((.from.address // "") + " " + (.from.name // "") + " " + (.subject // ""))
              | ascii_downcase | contains($h | ascii_downcase))]
    | sort_by(.createdAt) | last | .id // empty')
  [ -n "$ID" ] && break
  sleep 10
done
if [ -z "$ID" ]; then
  echo "5 分钟内未收到含 ${FROM_HINT} 的验证邮件，记入报告" >&2; exit 2
fi
VERIFY_MAIL="${CRED%.json}-$PERSONA-verify-mail.txt"
curl -fsS "$API/messages/$ID" -H "Authorization: Bearer $TOKEN" \
  | jq -r 'if (.text // "") != "" then .text else ((.html // []) | if type == "array" then join("\n") else tostring end) end' \
  > "$VERIFY_MAIL"
echo "已存私有文件（禁打印内容）：$VERIFY_MAIL"
SH
```

## 3. 验证与清理

- 在**同一 `--session <persona>` 浏览器页面**里填入 6 位验证码（如 ZenStory `/verify-email`）或打开验证链接，不直接用 `curl` 调接口跳过前端落地页。
- 顺带评估发件人可信度、标题清晰度、语言一致性与有效期说明（注明一次性邮箱无法测垃圾箱率），验证后立即 `rm -f` 删除 `*-verify-mail.txt`。
