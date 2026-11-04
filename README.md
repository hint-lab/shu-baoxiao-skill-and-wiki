<p align="center">
  <img src="assets/brand/readme-banner.svg" alt="上大报销助手 shu-baoxiao：查依据、对材料、找表格" width="920">
</p>

<p align="center">
  <strong>先弄清报销要求，再把材料备齐。</strong><br>
  面向上海大学师生的报销资料库，也能装进你常用的 AI。
</p>

<p align="center">
  <a href="wiki/Home.md">查看报销指南</a> &nbsp;·&nbsp;
  <a href="#让-ai-帮你检查材料">安装 AI 助手</a> &nbsp;·&nbsp;
  <a href="wiki/空白表格.md">查找表格</a> &nbsp;·&nbsp;
  <a href="wiki/反馈与纠错.md">反馈问题</a>
</p>

---

## 报销前，先把这几件事弄清楚

| 你遇到的问题 | 这里能帮你做什么 |
| --- | --- |
| 这笔费用要准备哪些材料？ | 按差旅、版面费、专家咨询、劳务、采购等事项，查找材料要求和学校依据。 |
| 文件都在手里，还是怕漏东西。 | 让 AI 对照学校资料检查已有文件，列出缺项、需要确认的情况和补齐办法。 |
| 财务退回了，看不懂该怎么补。 | 结合退回意见和已有材料，解释问题对应哪份文件、下一步怎么处理。 |
| 申请表、意见表、审批单去哪里找？ | 找到学校下载入口，以及已收录的空白表格副本。 |

每项具体要求都应能追溯到学校来源。没有读到的附件、没有确认的适用条件，会保留为待确认。

## 从这里开始

**只想查要求：** 打开[报销指南](wiki/Home.md)，选择自己的事项，再看[常用材料清单](wiki/报销材料清单.md)。直接阅读即可，无需安装。

**想让 AI 检查文件：** 按下面的说明，把助手安装到你正在使用的 AI，再提供本次事项和已有材料。

**AI 没有技能安装入口：** 下载[场景资料包](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-baoxiao-chat.zip)，解压后把对应事项的 TXT 文件与问题一起交给 AI。[查看具体用法](wiki/使用方法.md#普通聊天工具)。

## 让 AI 帮你检查材料

这里的 **Skill（技能）**，就是一套给 AI 使用的报销工作说明和参考资料。安装后，AI 可以按这套流程查依据、对材料；你继续使用自己的 AI，无需为本助手另配大模型 API Key。

选你已经在用的工具，点击名称查看下载和安装步骤：

| 你使用的 AI | 安装包 | 安装后怎样开始 |
| --- | --- | --- |
| [Codex](wiki/使用方法.md#codex) | [下载](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-baoxiao-codex.zip) | 输入 `$shu-baoxiao`，再描述本次报销事项。 |
| [WorkBuddy](wiki/使用方法.md#workbuddy) | [下载](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-baoxiao-workbuddy.zip) | 上传专用技能包，再让它使用“上大报销助手”。 |
| [豆包桌面版](wiki/使用方法.md#豆包桌面版) | [下载](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-baoxiao-doubao.zip) | 在工作任务模式上传技能，在对话中选中后使用。 |
| [Kimi CLI](wiki/使用方法.md#kimi-cli) | [下载](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-baoxiao-kimi-cli.zip) | 安装到技能目录后，输入 `/skill:shu-baoxiao`。 |
| [DeepSeek Harness](wiki/使用方法.md#deepseek-harness) | [下载](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-baoxiao-deepseek-harness.zip) | 安装到技能目录后，让它使用 `shu-baoxiao` 检查材料。 |

安装包可在[下载页](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest)获取。各工具的安装位置、升级方法和[已验证范围](wiki/使用方法.md#安装后的检查)见使用说明；包检查通过与实际对话效果分别确认。

装好后，把已有文件提供给 AI，直接说：

> 请用上大报销助手检查这笔版面费报销材料。先问清会影响判断的情况，再列出已有、缺少和待确认的材料，告诉我怎么补，并附学校依据。

被退回时，可以接着说：

> 财务退回说“缺付款依据”。请结合这些文件解释该怎么补。看不清的文件请标出来，不要直接当成缺失。

涉及个人文件时，只向自己信任并授权的 AI 提供材料。需要在电脑里整理和保存本次核对结果，可参考[个人材料整理](wiki/个人材料整理.md)。

## 按你的事项查资料

| 报销事项 | 报销事项 |
| --- | --- |
| [国内差旅](wiki/travel.md) | [出国境与外汇](wiki/international.md) |
| [版面费与出版费](wiki/publication.md) | [测试化验加工费](wiki/testing.md) |
| [专家咨询费](wiki/consultation.md) | [劳务费](wiki/labor.md) |
| [会议费](wiki/meeting.md) | [公务接待与工作用餐](wiki/reception.md) |
| [办公耗材与设备采购](wiki/procurement.md) | [系统操作与通用问题](wiki/general.md) |

也可以直接查看[全部资料](wiki/资料目录.md)、[空白表格](wiki/空白表格.md)和[用户提供的学院执行口径](wiki/学院执行口径.md)。学院口径单独标注来源、范围和未核验状态，与学校原文分开呈现。

横向项目结题、结余一次性奖励和绩效支取可查看[横向项目空白表格](skills/shu-baoxiao/references/horizontal-project.md)；对应来源页和表格目录也提供原表直接下载。

学校原件、空白表格和原页预览保存在 GitHub，下载与查看需要联网；技能内保留可在本地检索的规则正文和来源链接。[查看资料保留方式](wiki/资料保留方式.md)。

## 使用时，请留意

- **这是社区整理的助手。** 由 [HINT Lab](https://www.hintlab.cn) 维护，帮助准备和核对材料；具体办理仍以学校要求和财务审核为准。
- **收录了文件，不等于确认它今天仍然适用。** 使用时需结合业务日期、经费类型、人员身份和后续文件。仅有附件入口、扫描识别未核对等情况，在资料页中另有标注。[查看资料覆盖情况](wiki/材料整理.md)。
- **个人材料不要放进公开仓库。** 真实发票、账户、人员名单、签名和完整聊天记录，请留在授权环境内；反馈时只提交脱敏后的问题。

## 有问题，告诉我们

发现清单与实际办理不一致、资料过时，或安装使用遇到问题，可填写[免登录反馈表单](https://tcnrkcsneh6s.feishu.cn/share/base/form/shrcn1OtilSVxBkMSeYIFA7fcNg)，内容由维护者查看。也可以让有浏览器能力的 AI 帮你整理脱敏反馈，并在你明确要求后提交。[反馈说明](wiki/反馈与纠错.md)

愿意补充公开资料或修正内容，也欢迎通过 [GitHub Issues](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/issues) 或 Pull Request 参与。请附学校来源和具体差异；个人办理经历会保留为待核实线索。

<details>
<summary>维护者与开发者：资料更新、本地检索和构建</summary>

知识源保存在 `skills/shu-baoxiao/references/knowledge/documents.jsonl`。Wiki 阅读页、清单入口和安装包由同一份资料生成；更新后重新构建，不手工修改生成页。各平台共用一份报销技能，WorkBuddy 包另补充市场元数据。

本地检索使用 Python 3.10+ 标准库，无需启动服务：

```bash
python3 skills/shu-baoxiao/scripts/knowledge.py status --json
python3 skills/shu-baoxiao/scripts/knowledge.py search "外币 版面费" --json
```

更新与检查：

```bash
python3 tools/build.py
python3 -m unittest discover -s tests -v
python3 tools/build.py --check
```

构建产物位于 `dist/`，包括五种平台技能包、聊天资料包和 SHA-256 校验清单。发布到下载页后，使用者仍需更新自己安装的技能。

详见[维护方法](wiki/维护方法.md)。本仓库维护资料、技能和轻量工具；学校登录、自动代填与审批提交不在项目范围内。

</details>

---

由 [HINT Lab](https://www.hintlab.cn) 维护 · [Apache-2.0](LICENSE) · [学校资料来源与权利说明](NOTICE.md)
