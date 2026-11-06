# 方法与输出约定

## 当前可执行部分

| 层 | 实现 | 边界 |
|---|---|---|
| 文档解析 | `docx_extract.py`；复用正文规则并补上无样式引言标题排除（prose-v3） | 无 OCR、无版面复原；参考文献之后的内容也排除；逐段排除理由保存 |
| 中文分类 | AIGC V3 中文 + AnxForever BERT | 共同字符窗口；分别保留分数；训练和领域误差仍存在 |
| 英文分类 | AIGC V3 英文 | 单模型参考，不伪造中文 BERT 的英文能力 |
| 文风解释 | 本技能的语境复核指引 + 字面线索辅助 | 模型执行脚本仅列聊天残留、句长等可复核信息，不自动计算作者身份分数 |
| 来源线索 | 只读 Unicode 格式字符候选扫描 | 不等于统计水印；不改变分类分数 |
| 校准评测 | 有标签、分组隔离的 `calibrate.py` | 独立测试后单侧精确误报率上界；领域、单位和指纹必须匹配 |

V3 checkpoint 类别0=Human、1=AI，已按作者演示源码核实。BERT 类别0=human-written、1=AI-generated，按模型卡使用 `softmax(logits/0.8165)` 和256总token。正温度不改变0.5二分类边界。

各中文段落先按220字符均衡、不重叠地切分，再递归二分到所有可用 tokenizer 都能在推荐容量内完整处理；英文使用1600字符上限后同样核查容量。不会截掉尾部，也不跨段落拼接不同语言。原文每个纳入分析的字符恰好有一个窗口。混合语言路由是启发式，需要核查。

## 输出字段

- `raw_mean_scores`：类 softmax 的字符加权均分，不是“作者使用AI的概率”。
- `raw_flagged_shares_at_0_5`：分数≥0.5的窗口覆盖字符份额，不是逐字符确认AI来源。
- `model_coverage`：各模型对合格文本字符的覆盖率，不能用已评分分母掩盖未评分部分。
- `agreement_high_signal_share`：至少两模型可用、且非短片段窗口中，所有分数≥0.95的字符份额。0.95只是显示候选的未校准参数；并非经过验证的低误报阈值。分母由 `candidate_denominator_characters` 明示，不能当全文份额。
- `disagreement_share`：共同有效范围内，模型在0.5两侧冲突的字符份额。全部缺失时为null，不是0。
- `final_ai_rate`：本版本为null；没有经过目标域区段标签校准的真实AI比例估计器。
- `document_prediction`：仅有可适用校准档时的文档分类；`NOT_FLAGGED`不确认人工。文档标签不能换算区段比例。

## 可选概率统计

`probability_signals.py` 可加载本地 Qwen Base/Instruct 计算 NLL、PPL、Fast-DetectGPT analytic raw、Binoculars-style 比值。它只做 token 前向概率，不进行通用LLM评审。

这是小模型适配，既不是官方Falcon组合的数值复现，也不复用它的阈值。Fast-DetectGPT最新官方仓库还讨论其他参考模型组合；更换参考模型、分词和上下文都需要新校准。PPL/句长稳定不能直接等于AI，肉眼不能计算真正的PPL。

```powershell
python scripts/probability_signals.py --text eligible.txt --models qwen-models.json --output probability.json
```

模型JSON格式为含 `id`、`revision`、`folder` 的两个本地缓存记录，按 Base、Instruct 排序。权重不自动下载。原始量与分类器结果分开呈现，不平均或投票凑百分比。

## 已研究但未执行集成的路线

DetectGPT扰动、Ghostbuster概率特征训练、MarkLLM、SynthID、RAID/M4/DetectRL基准等见来源注册表。未运行不能声称“检测通过”。Ghostbuster使用弱参考模型特征，不需要目标生成模型的概率，不等于完全不需要模型概率。统计水印仍要匹配生成配置，不使用任意默认key试探作者身份。

外部数据集/模型许可证与代码仓库许可证分别核查。DetectRL-X存在GitHub与HF声明不一致，本包不复制其数据。GPL/未声明许可的参考项目不复制源代码入本技能。
