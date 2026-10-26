# 报告数据格式

这是给AI的内部格式，用户提供抖音主页或已有评论即可；浏览器采集及原材料整理都由AI映射为下列字段。所有分析使用本次账号材料；没有证据时允许少类、少建议或空列表，不填假示例。说明缺口放在`material_note`，不阻塞可以完成的分析。

根对象包含：

- `account`：`name`（必填），`handle`（可空）。
- `summary`：本次核心发现。
- `material_note`：简短说明实际输入范围、博主内容领域和关键缺口；详细口径与处理写入可选的`processing_notes`字符串数组，网页末尾折叠展示。
- `contents`：`[{id,title,note}]`。`id`用字母、数字、下划线或短横线，`note`可空，记录单篇背景或采集范围。没有真实URL不编造；报告用本地来源锚点。
- `comments`：如下。
- `perceptions`：`[{title,explanation,evidence_ids}]`，第一部分的判断与评论ID。证据不足可为空，或在`material_note`说明只有主页自述。
- `topics`：`[{id,title,short_title,placement,discussion,keywords,summary,need,signal,comment_ids,representative_ids}]`。`title`简短写大家在聊的事情；`short_title`可选，供紧凑场景使用的更短名称，不丢掉讨论对象；`placement`必填为`main`或`additional`，表示主要讨论或补充追问，按主题与问题价值判断，不硬切前几名；`discussion`用一两句说明具体对象、场景与主要说法，展示在选中分类的详情中；`summary`进一步归纳讨论。`need`可空，有明确困惑或期待时才填，不能把观点改成求助。关键词是主题提炼，不冒充词频；`signal`描述具体认同或分歧，可空。每条`professional`评论只能归一个主要话题，所有此类评论均需纳入；逐条判断回复，不默认继承父评论或笔记的分类。`representative_ids`选本类1—3条具体表达，直接显示原话；有主要分歧时选取不同立场。
- `opportunities`：`[{title,topic_id,evidence_ids,signals,situation,connection,example,product,illustration}]`。每项指回已有主题，`evidence_ids`选择本类1—3条直接支持该延伸的具体评论，在展开的选题详情中展示。`signals`是非空、不重复的数组，可选`debate`（有不同看法）、`question`（有人明确提问）、`emotion`（有情绪共鸣），可以共存；标签必须能回到所引原话，不靠关键词机械判定。主题只有一条评论时，脚本另加“单条线索”。`situation`是一句具体处境，用于卡片快速浏览，不冒充原话。`connection`简短解释从原话到建议的连接，`example`给具体场景与内容做法；`product`可省略。`illustration`可省略，是AI选的卡片装饰枚举：`goal`目标、`dialogue`沟通、`work`工作、`growth`成长、`bridge`关系联结、`boundary`边界、`balance`取舍、`heart`情感、`compass`方向；不匹配时使用默认图案，无需用户填写。没有可用建议时为空，不强行产品化，不给首推。
- `word_candidates`：从专业相关评论中选择的原词字符串数组，通常10—30个；过滤虚词、无关人名，保留确实有讨论意义的人物或事件词。缺少原词时允许为空。不要照搬示例账号词表。脚本去重，未出现的词不显示。

## 评论字段

```json
{
  "id": "n1-c1",
  "content_id": "n1",
  "text": "完整原文，不放采集工具概括或AI改写",
  "likes": null,
  "parent_id": null,
  "is_author": false,
  "scope": "professional",
  "expression": "substantive",
  "reason": "与该账号专业议题相关；原文仍单独保留"
}
```

`likes`未知用null；`parent_id`是父评论ID，一级用null，回复保留完整关系且父评论必须存在于同一篇。缺少父评论时不编造原文，可把已知回复作为独立片段记录并在`reason`注明层级不可恢复；`material_note`同步说明。`is_author`仅按材料标注，无法独立核验时说明。

`scope`四选一：

- `professional`：观众关于该博主专业/内容领域的问题、经历、期望、认同和分歧，进入第二部分及词频。
- `perception`：仅用于第一部分的观众认知，如非穿搭博主的造型评价。
- `context`：作者回复、机器人回复等上下文；不计观众需求和词频。作者留言必须用此范围或exclude。
- `exclude`：无关、空白、刷屏、重复导出等；保留简短`reason`，不参与分析。

`professional`不等于付费需求等级。回复中的有效观众声音同样保留；页面分别展示一级与回复条数，卡片条数和横条长度表示两者合计。词频表示包含原词的专业相关观众评论条数，每条同一词只计一次；不是词汇出现总次数，也不是独立人数。词频数据由脚本生成。

## 区分讨论与简短反应（1.1）

每条`professional`评论需要`expression`字段，由AI结合上下文判断：

- `substantive`：带具体意思的观点、情绪、经历、提问、愿望或行动；“画饼不如给钱”虽然短，仍是具体表达，不因情绪强烈或没有提问就降级。
- `reaction`：只附和或反应，没有增加具体意思，如回复中的“赞同”“哈哈哈”。能确定对象才进入对应话题；对象不清时按`perception`或`exclude`处理并说明原因。

等大话题卡片的条数和细横条长度对应相关讨论总数，横条以本次最多的一类为参照；选中后的详情同时显示“具体表达X条 · 简短附和/反应Y条”；两者相加等于总数。具体表达包含观点与情绪，不等于求助数量。至少有一条具体表达才能建立独立分类，只有附和而缺少对象的材料不凑成主题。

例如类名“对某次访谈的不同理解”，总览解释“有人觉得博主说中了受访者的问题，有人认为分析过头，还有人听不懂举例”。不要提前写成“如何提升深度思考能力”，也不要把所有评论概括为想学思考方法。

旧版分析JSON升级时需要补齐字段并复核归类；1.3新增`placement`、选题`signals`与`situation`，不要让用户填写这些内部字段。脚本会提示缺失，不替AI猜测分类或直接选择最高赞作为代表。

## 运行与产物

```sh
python3 /实际位置/susu-insight/scripts/render_report.py /输出目录/analysis.json /输出目录
```

生成带账号名称的HTML和一份包含计算统计的JSON，存在同名文件时追加序号。不要把私人说明书、前一个账号的答案、测试数据或本机专用路径放进分享包。

网页第二部分将main分类集中为等大话题卡片，桌面左侧展示完整类名、条数与横条，右侧展示所选分类详情与关键词；点击不跳动整页，右侧独立滚动。窄屏上下排列，卡片显示最多三个关键词；additional保存在可展开的补充追问区。第三部分按同一placement分组，默认展示3:4知识卡片封面（编号、线条插画、标题、依据标签），点击展开处境、原话及具体讲法。PDF展开全部分类和建议，避免只保留网页当时选中的内容。

可选保留`profile_note`（主页资料说明）、评论`source_line`（原材料行号）与`observed_like_values`（重复导出时观察到的点赞值）。点赞冲突时`likes`保持null，页面展示冲突值而不擅自取最大值。
