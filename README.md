# 人设哨兵 · persona_guard

一个**只统计、不干预**的人设监测插件：看她的说话有没有像 AI、有没有出戏、有没有偏离自己的人设。

- 不改写她的回复
- 不拦截、不纠正
- 只记录、出日报、在被说「人机」时通知你

> 适配 NekroAgent 2.4.x

---

## 它看什么

| 项目 | 说明 |
|---|---|
| **人机味** | 命中「AI 腔」规则（客服腔、确认腔、复述任务、元讨论…）的条数与原文 |
| **设定冲突** | 她说的话和人设卡/记忆矛盾（按你自己配置的事实锚点判定） |
| **记忆 ↔ 人设卡** | 记忆条目与人设卡自相矛盾的地方（含最近 7 天日记摘要） |
| **聊天事实抽检** | 她今天说的话里有没有说反设定（年龄、族、能力、家的位置…） |
| **人设匹配度** | 5 个维度合成一个分数 + 四条刻度 |
| **角色习惯白名单** | 她自己常用的句式，不计入人机味，避免误伤 |

---

## 内置预设

插件自带一套规则，装好就能用：

```
客服腔     有什么可以帮您的吗 / 希望对您有帮助 / 感谢您的理解 / 请稍等
助手腔     作为 AI / 我是一个模型 / 如果需要我 / 很高兴为您
结构腔     总的来说 / 综上所述 / 值得注意的是 / 首先…其次
确认腔     我记下了 / 记住了 / 我盯着 / 收下了 / 我听你的
模型腔     8 组：Gemini · Claude · GPT · Qwen · GLM · 豆包 · DeepSeek · 通用
```

- 全部可以在面板里增减，或直接改 `RULES_JSON` / `MODEL_RULES_JSON`
- 配置留空时自动回退到内置预设
- 内置预设只放通用腔调，不含任何特定角色的话

## 人设匹配度

总分 100，由五项加权：

```
句式贴合   0.20   句长是否接近她自己的常态
口头习惯   0.18   语气词密度是否接近常态（目标可自动从基线算）
去人机味   0.27   命中 AI 腔的比例
设定一致   0.20   是否出现设定冲突
对话感     0.15   少括号动作、少长旁白、少小说式描写词
```

阈值：`≥75` 好、`55~74` 注意、`<55` 差。

### 四条刻度

`对话感`、`活人感`、`句长`、`语气词` 都是**四段刻度 + 指针**，不是干巴巴的数字：

```
对话感   小说感 ← 偏小说感 ← 偏对话感 ← 对话感
活人感   人机味 ← 偏人机味 ← 偏活人感 ← 活人感
句长     太短 ← 偏短 ← 偏长 ← 太长      （带「她的常态」竖线）
语气词   太素 ← 偏素 ← 偏满 ← 太满      （带「她的常态」竖线）
```

---

## 安装

1. 把整个目录放到 `plugins/packages/persona_guard/`
2. 在 `configs/nekro-agent.yaml` 的 `PLUGIN_ENABLED` 里加一行：

```yaml
PLUGIN_ENABLED:
  - shushu.persona_guard
```

3. 重启 NA
4. 打开 `http://<你的NA>:8021/plugins/shushu.persona_guard/panel`

### 依赖

卡片是用 Pillow 画的，NA 官方镜像**默认不带**，要自己装一次：

```bash
docker exec -it nekro_agent /app/.venv/bin/pip install pillow
docker compose restart nekro_agent
```

没装的表现：日报/投诉卡生成失败，日志里出现 `ModuleNotFoundError: No module named 'PIL'`。

### 字体（可选）

卡片默认用插件目录下 `fonts/` 里的字体：

```
NotoSansCJK-Regular.ttc   正文字体（必需，缺失会回退到系统字体）
NotoSansCJK-Bold.ttc      粗体
ZCOOLKuaiLe-Regular.ttf   标题字体（快乐体）
SmileySans-Oblique.ttf    标题字体（得意黑）
HYNuoMiTuanW.ttf          标题字体（糯米团）
```

只放 Noto 也能跑；标题字体缺省会回退到 Noto。
系统里有 `msyh.ttc` / `wqy-microhei.ttc` / `NotoSansCJK` 时会自动用它们。

---

## 常用配置

| 配置 | 默认 | 说明 |
|---|---|---|
| `ENABLED` | true | 总开关 |
| `SCAN_SECONDS` | 120 | 统计轮询间隔（秒） |
| `ALERT_THRESHOLD` | 10 | 单日人机味达到多少条就提醒 |
| `ALERT_CHAT_KEYS` | 空 | 提醒发到哪个会话（留空不提醒） |
| `ALERT_ONCE_PER_DAY` | true | 每天只提醒一次 |
| `REPORT_HOUR` | 23 | 自动日报时间 |
| `REPORT_CHAT_KEYS` | 空 | 日报发到哪个会话 |
| `CARD_LAYOUT` | mobile | `mobile` 440px / `desktop` 760px |
| `CARD_THEME` | auto | `auto` 跟随时段 / `dark` / `light` |
| `CARD_TITLE_FONT` | kuaile | 标题字体：`kuaile` / `smiley` / `nuomi` |
| `AVATAR_URL` | 空 | 卡片头像，可填图片 URL 或本地路径 |
| `TARGET_PARTICLE_MODE` | auto | 语气词目标：`auto` 用她基线里的真实值 |
| `HABIT_ENABLED` | true | 角色习惯白名单开关 |
| `BASELINE_FROM` / `BASELINE_TO` | 空 | 用来算「她的常态」的日期区间 |
| `CHATCHECK_ENABLED` | true | 聊天事实抽检开关 |
| `COMPLAINT_ENABLED` | true | 被说「人机」时自动出日报 |
| `COMPLAINT_ALERT_CHAT_KEYS` | 空 | 投诉日报发到哪（留空回落到日报/提醒会话） |
| `COMPLAINT_GROUP_REPLY` | false | 是否在群里回一句 |
| `COMPLAINT_GROUP_CHAT_KEYS` | 空 | 允许回执的群白名单 |
| `COMPLAINT_COOLDOWN_MINUTES` | 30 | 同一会话的提醒冷却 |

完整配置项见插件面板。

---

## 指令

在聊天里发（**整句匹配**，不用 @）：

```
人设体检
人设体检 10-31
人设体检 2026-10-31
```

| 触发词 | 说明 |
|---|---|
| 人设体检 | 主词 |
| 哨兵日报 / 人设日报 / 人设报告 / 人设扫描 / 查人设 | 别名 |

支持日期写法：`10-31`、`2026-10-31`、`2026/10/31`、`10月31日`。

- 私聊里发：立刻出卡
- 群里发：靠 15 秒轮询兜底，不依赖「她是否被触发」
- 同一会话同一指令 30 秒内只响应一次

---

## 被说「人机」时的自动日报

判定链（依次排除）：

| 顺序 | 排除项 | 说明 |
|---|---|---|
| ① | 转发 / 卡片 / 超长 | `[合并转发`、`聊天记录：`、`[卡片消息]`、>300 字 —— 不算 |
| ② | 游戏语境 | 打人机 / 人机模式 / 人机局 / 王者 / 匹配 —— 不算 |
| ③ | 技术语境 | 「机器人/bot」＋ 检测/关键词/API/脚本/插件… —— 不算 |
| ④ | 正向词 | 聪明 / 进步 / 不像人机 / 好多了 —— 不算 |
| ⑤ | 指向 | 必须提到名字（`COMPLAINT_NAMES`）或直接 @她 |
| ⑥ | 通过 | 报警 + 私聊日报 + 日报卡 |

- ①②③④ 被排除的**不记日志**
- 只有 ⑤ 没通过的记成「疑似漏检」（日报卡底部会列出来）
- 私聊发你详细版：时间 / 群号 / 谁说的 / 原话 / 当日数据
- 群回执默认关，按 `COMPLAINT_GROUP_CHAT_KEYS` 白名单开启

---

## 聊天事实抽检

把她的实际发言对照人设硬事实，找说反/编造。

两层规则都可以自己配：

```
FACT_ANCHORS        事实锚点：[{"topic":"家的位置","reject":["家在学院"]}]
CHATCHECK_PATTERNS  句子模式：[["正则","原因"]]
```

两者默认都是空的，按你自己的角色写；`reject` 里放「不该出现」的说法。

结果写进日报卡的「聊天事实冲突」区块；没有冲突就不显示。

> 模型层（语义判断）在中转不稳时会自动跳过，规则层始终可用。

---

## 数据文件

都在 `plugin_data/shushu.persona_guard/`：

```
config.yaml          配置
stats.json           每日统计
hits.jsonl           命中明细
baseline.json        基线（她的常态：句长、语气词率）
habit_overrides.json 习惯白名单手工覆盖
shadow.jsonl         疑似漏检
chatcheck.json       聊天事实抽检结果
complaint_state.json 投诉提醒冷却
complaint_log.jsonl  判定日志
vibe.json            语感抽检（LLM）
consistency.json     记忆↔人设卡检查结果
report_*.png         生成的日报卡
```

---

## API

```
GET  /panel                      面板
GET  /api/stats?day=YYYY-MM-DD   当日统计
GET  /api/rules                  人机味规则
POST /api/rules                  保存规则
GET  /api/model-rules            模型腔规则
POST /api/scan                   立即扫一次
POST /api/backfill {"date":...}  补算某天
GET  /api/baseline               基线
POST /api/baseline/run           重算基线
GET  /api/report.png?day=&theme=&layout=&font=
POST /api/report/send {"chat_keys":"...","day":"..."}
POST /api/complaint/test {"text":"..."}
GET  /api/complaint/log?limit=
GET  /api/shadow?limit=
GET  /api/chatcheck              聊天事实抽检结果
POST /api/chatcheck/run {"days":1,"limit":200,"use_llm":false}
GET  /api/consistency            记忆↔人设卡
POST /api/consistency/run
```

---

## 常见问题

**装了没反应？**
检查 `PLUGIN_ENABLED` 是否加了 `shushu.persona_guard`，没加的话插件路由全是 404。

**日报卡是黑底？**
`CARD_THEME: auto` 会按时间切换；固定深色改 `dark`。

**口头习惯总是很低？**
把 `TARGET_PARTICLE_MODE` 设成 `auto`，它会用她基线里的真实语气词率当目标，而不是固定值。

**某个常用句被误判成人机味？**
面板里把它加进「角色习惯」，或在 `habit_overrides.json` 里手工加。

**规则怎么写？**
正则字符串数组，命中任意一条即算。例：

```json
{"ai_phrases": ["我在这儿听着", "记住了", "我盯着|盯着呢"], "conflict_patterns": ["两个妈"]}
```

---

## 许可

MIT，见 `LICENSE`。
