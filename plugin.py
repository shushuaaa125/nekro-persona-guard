"""人设哨兵 - 插件定义与配置

统计「她说话像不像本人」：人机味、设定冲突、称呼密度等，
超阈值时主动提醒。只统计，不干预回复。
"""

from typing import Literal

from nekro_agent.api.plugin import ConfigBase, NekroPlugin
from pydantic import Field

plugin = NekroPlugin(
    name="人设哨兵",
    module_name="persona_guard",
    description="统计角色扮演时的「人机味」与设定冲突次数，超过阈值主动提醒",
    version="1.0.0",
    author="shushu",
    url="",
    webui_path="/panel",
)


DEFAULT_RULES = """{"ai_phrases": ["我在这儿听着", "有事就说", "早点睡吧", "那就好", "太生硬", "脑子.{0,4}(还没)?转不过", "硬憋", "我这不是", "作为一个", "总而言之", "希望能帮到你", "还有什么可以帮", "你的意思我明白", "(这话|这句(话)?)我(记|认|不接|收|留)", "(这话|这句(话)?)(说得|有点重|重了|稳|漂亮)", "这句话我", "我记(下|住|牢|着|一下)", "这个账我记着", "记住了", "记着呢", "我盯着|盯着呢|我守着|我听着|我拿笔记|我听见了|我看见了|我看到了", "收下了|我收下|收着点", "我听你的|都听你的|听你的", "没敢", "——\\\\s*我", "睡吧[，,]?我守着", "问别人.{0,6}问自己", "还是问自己", "行[，,]?我认", "我认了", "认这个", "认得实", "认下来", "认住该认", "就是认了", "比刚才(稳|重|轻|平)", "比之前(都)?(重|轻|稳|平)", "声音没抖", "很平", "挺稳", "我不拦", "我不催", "不催你", "你自己掂量", "你掂量", "这个.{0,3}我先不接", "没接你那句", "话我留着", "收不回去", "什么心思都写着", "比谁都响", "你往下讲", "回去睡", "接的漂亮", "有什么(可以|能)(帮|为)(您|你)的?(吗|么|呢)?", "希望对(您|你)有(所)?帮助", "很高兴(为|能|可以)(您|你)", "请问(还)?有(什么|其他)(需要|可以)", "如有(任何)?(问题|疑问)", "感谢(您|你)的(理解|耐心|反馈|支持)", "非常抱歉(给|为)(您|你)", "让(您|你)久等了", "请(您|你)稍等", "总的来说", "综上所述", "值得注意的是", "需要注意的是", "这是一个(很好|复杂|重要)的问题", "我可以(帮|为)(您|你)", "建议(您|你)(可以|不妨)", "需要我(帮|为)(您|你)", "作为(一个)?(AI|人工智能|助手|语言模型)", "我(只)?是一个(程序|模型|助手)", "如果(您|你)(还)?有(需要|疑问)", "希望(这|以上)(对|能)", "下面(我)?(来|将)(介绍|说明)", "首先[，,].{0,12}其次"], "conflict_patterns": ["我是AI", "我是个语言模型"], "address_words": []}"""


@plugin.mount_config()
class GuardConfig(ConfigBase):
    """人设哨兵配置。改完即时生效。"""

    ENABLED: bool = Field(
        default=True,
        title="启用统计",
        description="关掉后不再扫描新消息，但历史数据仍保留。",
    )
    RULES_JSON: str = Field(
        default=DEFAULT_RULES,
        title="规则（JSON）",
        description=(
            "三段规则：ai_phrases（人机味词句）、conflict_patterns（设定冲突正则）、"
            "address_words（称呼词）。可以在 WebUI 面板里直接改。"
        ),
    )
    SCAN_SECONDS: int = Field(
        default=120,
        title="扫描间隔（秒）",
        description="每隔多久扫一次她新发的消息。",
        ge=30,
        le=1800,
    )
    ALERT_THRESHOLD: int = Field(
        default=10,
        title="提醒阈值（次/天）",
        description="当天人机味命中达到这个次数，主动发一条提醒。",
        ge=1,
        le=1000,
    )
    CONFLICT_CONTEXT_EXEMPT: str = Field(
        default="你说,你刚才说,意思是,引用,她说,他说,原话,更正,口误",
        title="冲突语境豁免词",
        description="只豁免明确的「转述」信号；不要放「本来就是家」这类，那本身就是冲突句的一部分。",
    )
    FACT_ANCHORS: str = Field(
        default="[]",
        title="事实锚点（确定性检查）",
        description=(
            "出现 reject 里的说法就直接记为设定冲突，不靠模型。"
            "每项 {topic, reject:[...]}。"
        ),
    )
    CHATCHECK_ENABLED: bool = Field(
        default=True,
        title="聊天事实抽检",
        description="每天用模型抽查她最近的发言，对照人设硬事实找矛盾。",
    )
    CHATCHECK_PATTERNS: str = Field(
        default="[]",
        title="聊天校验规则",
        description='JSON 数组，形如 [["正则","原因"]]；留空则不跑规则层。',
    )
    CHATCHECK_AGE: str = Field(
        default="",
        title="年龄判定（可选）",
        description='JSON：{"current":16,"entry":15,"entry_words":["进学院"]}；留空则按普通模式。',
    )
    CHATCHECK_LIMIT: int = Field(
        default=40,
        title="抽检条数",
        description="每次最多送多少条发言给模型。",
    )
    USE_LLM_CHECK: bool = Field(
        default=True,
        title="附加语义检查",
        description="在锚点检查之外，再让模型做一次语义比对（更细但可能保守）。",
    )
    COMPLAINT_DEBUG: bool = Field(
        default=True,
        title="记录判定日志",
        description="把每条被检查的消息与判定结果记到 complaint_log.jsonl，便于确认真的在监测。",
    )
    COMPLAINT_ENABLED: bool = Field(
        default=True,
        title="被说人机时自动日报",
        description="有人在群里说她「人机」时，立刻补扫一次并发日报给你。",
    )
    COMPLAINT_NAMES: str = Field(
        default="",
        title="她被人叫什么",
        description="消息里出现这些名字，且带骂人机的词，才算在说她。",
    )
    COMPLAINT_POSITIVE: str = Field(
        default="聪明,比…强,比…好,进步,好多了,不像人机,真人,自然,变好,厉害了,不错,挺好的,很有感觉",
        title="正向词（不报警）",
        description="出现这些词的「人机」多半是在夸，不触发。",
    )
    COMPLAINT_SCAN_SECONDS: int = Field(
        default=15,
        title="投诉轮询间隔（秒）",
        description="只扫用户消息的轻量轮询，越小越及时。",
        ge=5,
        le=300,
    )
    COMPLAINT_GROUP_CHAT_KEYS: str = Field(
        default="",
        title="允许群内回执的会话",
        description=(
            "逗号分隔的 chat_key。即使「同时在群里回一份」是关的，"
            "这里列出的群也会收到一条简短回执 + 日报卡。"
        ),
    )
    COMPLAINT_GROUP_TEXT: str = Field(
        default="",
        title="群内回执措辞（可选，随机挑一句）",
        description="用 | 分隔多句；留空则只发卡片不回话。",
    )
    COMPLAINT_GROUP_TAIL: str = Field(
        default="（{time}）今天 {ai} 次",
        title="群内回执尾巴",
        description="接在候选句后面的数据行。占位符：{time} / {ai} / {conflict}。",
    )
    COMPLAINT_GROUP_REPLY: bool = Field(
        default=False,
        title="同时在群里回一份",
        description="在出事那个群也发一条简短说明 + 日报卡。",
    )
    COMPLAINT_WORDS: str = Field(
        default="人机,入机,机器人,AI味,ai味,像AI,像ai,不像人,太假",
        title="人机判定词",
        description="逗号分隔。",
    )
    COMPLAINT_TECH_WORDS: str = Field(
        default="关键词,检测,发送,接口,API,api,脚本,插件,框架,程序,代码,部署,配置,节点,代理,风控,验证码,逻辑,触发",
        title="技术语境词（不当作投诉）",
        description="消息里同时出现「机器人/bot」和这些词时，多半在聊技术，不报警。",
    )
    COMPLAINT_EXCLUDE: str = Field(
        default="打人机,人机模式,人机局,人机队友,王者,匹配,人机对战",
        title="排除词（防误伤）",
        description="出现这些就不算——游戏语境、别人的人机等。",
    )
    COMPLAINT_COOLDOWN_MINUTES: int = Field(
        default=30,
        title="同一会话冷却（分钟）",
        description="防止被连续说人机时刷屏。",
        ge=0,
        le=1440,
    )
    COMPLAINT_ALERT_CHAT_KEYS: str = Field(
        default="",
        title="投诉日报发到哪",
        description="留空则依次用「日报发到哪」「提醒发到哪」。",
    )
    HABIT_ENABLED: bool = Field(
        default=True,
        title="启用「角色习惯」白名单",
        description=(
            "把角色平时就在说的短语排除出人机味统计。"
            "比如她本来爱说「好呀」，那就不该算模型腔。"
        ),
    )
    BASELINE_FROM: str = Field(
        default="",
        title="信任期开始（YYYY-MM-DD）",
        description="只从这段你确认过的时间算口癖；留空则用「基线统计天数」。",
    )
    BASELINE_TO: str = Field(
        default="",
        title="信任期结束（YYYY-MM-DD）",
        description="留空则到今天。设了信任期后，基线不会随新消息变化。",
    )
    BASELINE_DAYS: int = Field(
        default=7,
        title="基线统计天数",
        description="用过去多少天的说话习惯判断哪些短语是她自己的口癖。",
        ge=1,
        le=60,
    )
    HABIT_MIN_HITS: int = Field(
        default=5,
        title="判为习惯的最少出现次数",
        description="基线期内出现次数 ≥ 这个值，就当作她的口癖，不计入人机味。",
        ge=1,
        le=200,
    )
    EXTRA_SOURCES: str = Field(
        default="",
        title="额外比对来源",
        description=(
            "一致性检查除人格记忆外，还要比对的其它插件数据。"
            "填文件路径或 glob，一行一个，例如："
            "plugin_data/xiaojiu.private_companion/state.json"
        ),
    )
    MIN_SAMPLE: int = Field(
        default=20,
        title="匹配度最少样本",
        description="当天消息少于此数时不算匹配分（样本太少会乱跳）。",
        ge=5,
        le=500,
    )
    CARD_TITLE_FONT: str = Field(
        default="kuaile",
        title="标题字体",
        description="smiley = 得意黑（有设计感）/ noto = 思源黑体粗体（端正）。",
    )
    CARD_LAYOUT: str = Field(
        default="mobile",
        title="卡片版式",
        description="mobile（440 宽，手机直接看）/ desktop（760 宽，桌面详细版）。",
    )
    CARD_THEME: str = Field(
        default="auto",
        title="卡片主题",
        description="dark / light / auto（6-18 点用浅色，其余深色）。两套配色都能看清。",
    )
    AVATAR_URL: str = Field(
        default="",
        title="卡片头像地址",
        description="留空则不显示头像；填 URL 会缓存到 plugin_data 下。",
    )
    TARGET_LEN: int = Field(
        default=24,
        title="目标句长",
        description="人设希望的单条消息平均字数，用于算「句式贴合度」。",
        ge=8,
        le=80,
    )
    TARGET_PARTICLE_MODE: str = Field(
        default="auto",
        title="语气词目标来源",
        description="auto = 用信任期基线里的真实语气词率；fixed = 用下面的固定值。",
    )
    TARGET_PARTICLE_RATE: float = Field(
        default=0.28,
        title="目标语气词率",
        description="人设希望带「呀/呢/啦/哦/~/……/>.<」的消息占比（0-1）。",
        ge=0.0,
        le=1.0,
    )
    VIBE_MODEL_GROUP: str = Field(
        default="",
        title="语感抽检模型组",
        description="做「像不像真人」判定的模型组；留空用全局。default 一般是 Gemini。",
    )
    MODEL_GROUP: str = Field(
        default="auto",
        title="模型组",
        description=(
            "auto = 跟随 NA 的「全局模型组」以及每个频道的单独覆盖；"
            "也可以写死一个 MODEL_GROUPS 里的组名。"
        ),
    )
    MODEL_RULES_JSON: str = Field(
        default="""{"qwen":["以下是","根据您","建议您","希望对您有帮助","如有其他问题","欢迎随时提问","需要注意的是","如果你需要","我可以为您","您的","总的来说","首先[，,]","其次[，,]"],"deepseek":["这话我记","这话我认","这话我不接","这话我收","这话我留","我记(下|住|牢|着)","认下来","我守着","比刚才","我不拦"],"doubao":["好呀好呀","当然啦","可以呀","没问题呀","宝子","亲~","让我想想哈","我懂你的意思啦","你放心好啦","首先呢","然后呢","最后呀","要不我们","我们可以这样","希望(可以|能)帮到你呀","还有什么(问题|需要)随时(问我|找我)哦?","随时找我呀"],"glm":["以下是","需要注意的是","希望对您有帮助","如果您需要","我将","我们可以","您的","总的来说","首先[，,]","其次[，,]","值得一提的是"],"gemini":["当然可以","希望这能","希望对你(有)?帮助","需要注意的是","让我来","以下(是|几点)","如果你愿意","这是一个很好的问题","让我们","首先[，,]","其次[，,]","最后[，,]","总的来说","值得注意的是","我理解你的意思","你可以试试","建议你","简单来说","换句话说","如有需要","需要我(帮|为)","还有什么(可以|需要)","很高兴(能|为)","我建议"],"generic":["作为AI","希望能帮到你","我来帮你"],"gpt":["作为一个AI","作为一个语言模型","以下是","总结一下","需要注意的是","值得一提的是","更重要的是","希望对你有帮助","如果你需要","让我为你","我可以帮你","总的来说","首先[，,]","其次[，,]","最后[，,]","简单来说","换句话说","我无法","抱歉[，,]"],"claude":["某种程度上","或许","也许","似乎","我觉得","我理解","我明白","让我(想|想想)","不妨","这让我想到","真正的问题是","重要的是","说到底","归根结底","不仅.{0,12}而且","这意味着","从某种意义","一方面.{0,20}另一方面","坦率地说","说实话","诚然","我注意到","你可能(会)?发现","我倾向于"],"kimi":["让我(来)?(帮|为)你(梳理|整理)","可以这样理解","先(给|说)结论","分成(几|以下)点","简单来说","以下(是|有)","希望(对你|对你有)帮助","我来(帮|为)你(总结|分析)","这样(安排|理解)(是否)?可以"],"grok":["哈哈","说实话","老实说","直说吧","开个玩笑","别担心","不(妨|如)直接(说|讲)","我(可以)?直接(说|告诉)"],"ernie":["根据我的了解","据我所知","为您解答","下面(我)?(将|来)(介绍|说明|解答)","希望以上(回答|内容)","如果您还(有|需要)","总的来说","需要注意的是"],"hunyuan":["有什么可以帮(你|您)","请(告诉我|随时告诉我)","我会(尽力|尽量)","希望对(你|您)有帮助","需要我(帮|为)(你|您)","随时(可以)?(问我|找我)"],"spark":["我是讯飞星火","请问有什么可以帮(您|你)","为您提供","希望对(您|你)有帮助","如(需|有)帮助","您还(有|需要)","我可以帮(您|你)(解答|解决)"],"o1":["让我(先)?(仔细)?(分析|思考)一下","首先[，,].{0,10}我们需要","从逻辑上","可以推导出","因此[，,].{0,8}得出结论","综上所述","让我(分步|逐步)"]}""",



        title="模型特征词",
        description=(
            "按模型族补的「AI 味」词表，JSON：族名 → 词/正则列表，"
            "会自动和主规则里的 ai_phrases 合并。族名按模型名里的关键字自动判定。"
        ),
        en_title="Model-specific Phrases",
        en_desc="Model-specific phrases",
    )
    AUTO_REPORT_ENABLED: bool = Field(
        default=True,
        title="启用每日日报",
        description="每天固定时间生成一张日报卡片（按群统计），发到下面的会话。",
    )
    REPORT_HOUR: int = Field(
        default=23,
        title="日报时间（0-23 点）",
        description="每天这个点之后第一次检查时发日报，间隔按 24 小时算。",
        ge=0,
        le=23,
    )
    REPORT_CHAT_KEYS: str = Field(
        default="",
        title="日报发到哪",
        description="逗号分隔的 chat_key；留空则沿用「提醒发到哪」。",
    )
    ALERT_CHAT_KEYS: str = Field(
        default="",
        title="提醒发到哪",
        description="逗号分隔的 chat_key（通常是你的私聊），留空则只在 WebUI 显示。",
    )
    ALERT_ONCE_PER_DAY: bool = Field(
        default=True,
        title="每天只提醒一次",
        description="开启后，同一天只在首次超过阈值时提醒一次。",
    )
    KEEP_DAYS: int = Field(
        default=30,
        title="统计数据保留天数",
        description="超过这个天数的日统计会被清掉。",
        ge=1,
        le=365,
    )
    MAX_RECENT: int = Field(
        default=300,
        title="保留多少条命中样本",
        description="命中样本用于面板展示，超出后丢弃最旧的。",
        ge=20,
        le=2000,
    )


def get_config() -> GuardConfig:
    return plugin.get_config(GuardConfig)
