# paper-ai-audit

面向中文、英文论文及文章的 AI 写作信号复核技能，优先减少人工文本误报。

它将本地分类器、共同文本片段分析、文风解释和有标签校准组织成一个可执行流程。**当前未证明它比单个模型更准确，也不提供经过验证的“真实 AI 生成百分比”。** 没有适用校准时，保留原始信号和不确定结果。

[技能入口](SKILL.md) · [方法与输出含义](references/methods.md) · [校准评测](references/evaluation.md) · [20 个来源及采用状态](references/sources.json)

## 能做什么

- 只读分析 DOCX、UTF-8 TXT 和 Markdown，保存逐段排除原因及原件 SHA-256。
- 中文使用 AIGC Detector V3 与 Chinese AI Detector BERT，对相同字符片段评分；英文目前使用 V3 单模型。
- 保留各模型的分数、实验窗口份额、模型分歧、短片段和缺失范围。
- 用中文学术文风规则解释具体表达问题，提供短引文和位置。
- 校准时检查来源分组、重复文本、训练重叠及独立测试误报率上界。
- 可选计算 Qwen 参考模型下的概率统计；不自动下载或调用外部评审服务。

模型缺失不计为人工，文风问题不直接换算成 AI 率。Unicode 格式字符只是来源线索，不等于统计水印。DOCX 不做图片 OCR，表格、参考文献及其后内容等不参与正文分类，具体范围保存在报告中。

## 安装依赖

推荐 Python 3.12；以下命令中的 `python` 应指向安装了依赖的解释器。

```bash
git clone https://github.com/Crzame/paper-ai-audit.git
cd paper-ai-audit
python -m venv .venv
```

激活虚拟环境：Windows PowerShell 使用 `.venv/Scripts/Activate.ps1`，macOS/Linux 使用 `source .venv/bin/activate`。

```bash
python -m pip install -r requirements.txt
```

PyTorch 需与自己的硬件匹配；本项目验证使用 CPU 推理。若按 PyTorch 官方说明另外安装了兼容版本，再安装其余依赖。完整模型推理比单元测试需要更多内存和运行时间。

## 准备模型

模型权重不包含在仓库内。公开清单 [assets/models.example.json](assets/models.example.json) 固定了模型 revision、类别映射和文件 SHA-256。生成的本机配置 `assets/models.local.json` 已被 Git 忽略。

显式下载官方 checkpoint 并核对文件：

```bash
python scripts/setup_models.py --download --cache-dir .model-cache
```

只使用已存在的 Hugging Face 缓存，禁止联网下载：

```bash
python scripts/setup_models.py --cache-dir .model-cache
```

已有三个模型目录时，把它们分别放在一个目录下的 `v3_en`、`v3_zh`、`bert_zh` 子目录中，然后执行：

```bash
python scripts/setup_models.py --model-root /path/to/checkpoints
```

脚本会验证清单要求的全部文件。也可复制公开清单为 `assets/models.local.json`，自行填写各 checkpoint 的 `local_path`。不要提交本机配置、文稿或权重。

使用的模型：

| checkpoint | 用途 |
|---|---|
| [yuchuantian/AIGC_detector_env3](https://huggingface.co/yuchuantian/AIGC_detector_env3) | 英文 V3 |
| [yuchuantian/AIGC_detector_zhv3](https://huggingface.co/yuchuantian/AIGC_detector_zhv3) | 中文 V3 |
| [AnxForever/chinese-ai-detector-bert](https://huggingface.co/AnxForever/chinese-ai-detector-bert) | 中文 BERT |

## 分析文稿

```bash
python scripts/audit.py --input paper.docx --output outputs/run-001
```

`--input` 也可以是包含 DOCX/TXT/MD 的文件夹；`--registry` 可指定另一份本机模型配置。脚本不覆盖原稿，推理阶段仅加载本地权重。

输出包括汇总 `summary.json` 和各文稿的 `result.json`、`report.md`。重点查看：

| 字段 | 含义 |
|---|---|
| `raw_mean_scores` | 模型类分数的字符加权均值 |
| `raw_flagged_shares_at_0_5` | 分数达到 0.5 的窗口覆盖字符份额 |
| `model_coverage` | 各模型对纳入文本的覆盖率 |
| `agreement_high_signal_share` | 共同有效、非短片段范围内的双方高分候选份额 |
| `final_ai_rate` | 当前默认 `null`；不把上述数值冒充真实生成比例 |

候选阈值 0.95 未经目标域校准，不是低误报保证。共同分母在 `candidate_denominator_characters` 中明示。完整解释见 [methods.md](references/methods.md)。

## 作为 Agent Skill 使用

将仓库目录安装到支持 Agent Skills 的工具所使用的技能目录中，保持 `SKILL.md` 位于根目录。模型推理仍需可用的 Python 环境和本地权重。

示例请求：

> 使用 paper-ai-audit 分析这篇论文的 AI 写作信号，优先少误报，并指出具体位置。

仅阅读技能说明不等于已经运行分类器；报告应说明哪些方法实际执行、哪些仅作参考。

## 评测与局限

少误报必须同时报告漏检代价。校准与测试按原稿、作者或提示家族隔离；重复来源不能制造独立样本量。没有来源标签就不计算准确率或误报率。

初步 QA 对照使用 HC3-Chinese 的 144 条公开答案，独立测试部分为人工 36 条、AI 36 条。该小样本上 V3 误报 2 条、BERT 误报 0 条；**没有显示融合优于 BERT 单模型**。0/36 误报的单侧 95% 上界仍约 7.98%，且样本非论文域、训练重叠未知，不足以支持低于 1% 的论文误报声明。详见 [校准评测说明](references/evaluation.md)。

复现该研究性对照：

```bash
python benchmarks/fetch_hc3_pilot.py
python benchmarks/run_pilot.py
```

第一个命令显式下载公开数据；第二个仅本地推理。生成数据和结果位于 `benchmarks/`，不会被 Git 跟踪。该数据适用 CC-BY-SA-4.0，不随仓库分发。

## 测试

轻量测试不下载模型、不上传文稿，也不需要 PyTorch：

```bash
python -m pip install defusedxml==0.7.1
python -X utf8 -B -m unittest discover -s tests -v
```

测试检查覆盖、只读 DOCX、缺失/短文本、分组去重和校准边界，不能证明检测准确度。

## 许可证与来源

本仓库代码采用 [MIT License](LICENSE)。外部权重、数据和参考项目适用各自许可，见 [第三方说明](THIRD_PARTY_NOTICES.md) 与 [来源注册表](references/sources.json)。来源注册表中的 `reference_only` 不表示这些检测器已经执行或集成。
