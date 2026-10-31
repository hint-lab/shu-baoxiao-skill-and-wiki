# shu-baoxiao · 上海大学报销助手

查学校依据、核对已有材料、理解退回意见，让每笔报销的下一步更清楚。

`shu-baoxiao` 由 [HINT Lab](https://www.hintlab.cn) 维护，提供上海大学报销资料 Wiki、可安装的 AI 技能和可直接用于对话的场景资料包。你可以自己阅读资料，也可以让已有的 AI 工具结合学校原文检查材料。

本项目为社区整理。具体要求需结合业务日期、经费类型和人员身份核对学校原文；尚未读到的附件、未经核验的时效和需要人工确认的事项会明确标出。

## 选一种方式开始

| 你的使用方式 | 从这里开始 |
| --- | --- |
| 直接阅读指南与资料 | 打开 [Wiki 首页](wiki/Home.md)，按报销事项查找学校依据 |
| 在 Codex 中使用技能 | 下载 [Codex 技能包](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-baoxiao-codex.zip)，安装后调用 `$shu-baoxiao` |
| 在 WorkBuddy 中导入技能 | 下载 [WorkBuddy 技能包](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-baoxiao-workbuddy.zip)，导入步骤见 [使用方法](wiki/使用方法.md#workbuddy)；客户端实际导入与对话效果仍待验收 |
| 在豆包或其他聊天工具中使用 | 下载 [场景资料包](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-baoxiao-chat.zip)，把对应场景的 TXT 与问题一起交给 AI |
| 实际办理不一致、被退回或遇到使用问题 | 打开[免登录匿名反馈表单](https://tcnrkcsneh6s.feishu.cn/share/base/form/shrcn1OtilSVxBkMSeYIFA7fcNg)，也可让有浏览器能力的AI代填；见[反馈说明](wiki/反馈与纠错.md) |

Codex 安装时，将 ZIP 中完整的 `shu-baoxiao` 文件夹放入 `~/.agents/skills/`。也可通过环境中的技能安装器安装本仓库的 `skills/shu-baoxiao`。升级时请替换旧版报销技能目录，避免同时加载两套技能。

技能内置的资料检索在本地运行，返回原文与来源，由当前 AI 完成分析和回答，无需另配大模型 API Key。普通聊天工具使用资料包即可，具体步骤见 [完整使用说明](wiki/使用方法.md)。

## 把你的具体问题交给 AI

Skill 内置[常用材料清单](wiki/报销材料清单.md)，按已核对的来源、适用条件和核对日期维护。常规事项先复用对应清单，来源变化、到复核日期或出现新情况时再查原文。每笔事项的核对状态保存在授权的本地目录，补件后继续更新。

用户明确补充的[学院执行口径](wiki/学院执行口径.md)单独记录来源和范围，在相关检索及清单中显示；与官方书面依据存在差异时一并说明。

安装技能后，可以这样开始：

> 使用 $shu-baoxiao 检查我提供的版面费报销材料。先确认经费类型、币种和业务日期，再查学校原文。请说明已有材料、确实缺少的材料、条件成立才需要的材料和待确认事项，并给出补齐步骤与官方来源。

也可以针对退回意见继续询问：

> 财务退回说“缺付款依据”。请结合我已有的文件和学校原文解释怎么补。无法读取的材料请标记待查看，不要直接判缺失，也不要编写不存在的证明。

检查个人材料时，请向所用 AI 工具提供文件或授权相应目录，并说明本次事项、业务日期和经费情况。个人材料按宿主工具的权限与数据处理方式使用，不写入本项目的共享知识库。需要在本地归档一笔报销时，可参考 [个人材料整理](wiki/个人材料整理.md)。

## 按报销事项查资料

| 事项 | 事项 |
| --- | --- |
| [国内差旅](wiki/travel.md) | [出国境与外汇](wiki/international.md) |
| [版面费与出版费](wiki/publication.md) | [测试化验加工费](wiki/testing.md) |
| [专家咨询费](wiki/consultation.md) | [劳务费](wiki/labor.md) |
| [会议费](wiki/meeting.md) | [公务接待与工作用餐](wiki/reception.md) |
| [办公耗材与设备采购](wiki/procurement.md) | [系统操作与通用问题](wiki/general.md) |

找文件和表格，可从 [学校资料总览](wiki/材料整理.md)、[全部资料目录](wiki/资料目录.md) 或 [表格入口与空白表格副本](wiki/空白表格.md) 进入。

## 怎样看待资料和核对结果

资料库保留学校公开页面、附件入口、已提取文字和部分空白表格副本。初始资料来自 2026-06-30 快照，后续补充的资料分别记录获取时间；具体覆盖情况见 [资料目录](wiki/资料目录.md)。网页发布日期、文件版本年份和抓取时间都不等于规则生效日期。

- **有正文**：可以阅读提取内容；涉及金额、期限、身份条件或例外时，仍需核对原件及适用版本。
- **只有入口或访问受阻**：只能说明找到了资料线索，不能据此声称已读附件或确认具体要求。见 [待补资料](wiki/待补资料.md) 和 [需要协助取得的资料](wiki/需要协助.md)。
- **扫描件机器识别**：用于检索和定位，数字、表格、否定条件需对照原件。见 [机器识别待核对资料](wiki/待核对资料.md)。

AI 的核对结果用于准备材料和人工复核。材料存在、内容可读、信息匹配、审批通过与实际付款是不同状态，需要分别确认。

## 本地检索

检索工具只需 Python 3.10+ 标准库，无需安装依赖或启动服务。在仓库根目录运行：

```bash
# 查看资料快照、覆盖情况与完整性。
python3 skills/shu-baoxiao/scripts/knowledge.py status --json

# 搜索学校依据，取得文档 ID 与官方来源。
python3 skills/shu-baoxiao/scripts/knowledge.py search "外币 版面费" --limit 6 --json

# 将下面的文档 ID 替换为搜索结果中的 ID，阅读正文。
python3 skills/shu-baoxiao/scripts/knowledge.py read '<文档ID>' --json
```

复制整个 `skills/shu-baoxiao/` 目录后，也可从其他工作目录运行其中的脚本；路径以实际安装位置为准。检索本身不联网、不调用大模型。核对当前标准时，需要另外查看学校后续文件。

## 维护与共建

知识源位于 `skills/shu-baoxiao/references/knowledge/documents.jsonl`，场景索引位于 `skills/shu-baoxiao/references/scenarios.json`。Wiki 目录和原文阅读页从知识源生成，更新后统一构建：

```bash
python3 tools/build.py
python3 -m unittest discover -s tests -v
python3 tools/build.py --check
```

构建会同步 Wiki 与技能参考资料，并在 `dist/` 生成 Codex、WorkBuddy 和聊天资料包及校验值。GitHub Actions 会验证并生成构建产物；发布后的技能更新需要使用者重新安装或显式同步。公开来源更新、附件导入、Word/PDF 提取和版本发布步骤见 [维护方法](wiki/维护方法.md)。

纠错或补充资料时，请附官方来源、对应段落及适用条件。真实发票、人员名单、账户、签名、登录信息和个人报销案例原件请留在授权的本地环境，不要提交到仓库或公开 Issue。

反馈首选[飞书匿名表单](https://tcnrkcsneh6s.feishu.cn/share/base/form/shrcn1OtilSVxBkMSeYIFA7fcNg)，不需要飞书或GitHub账号，内容由维护者在专用收件箱查看。2026-10-29已验证未登录提交及测试记录实际入表。有浏览器能力的AI可在使用者明确请求后代填并核对成功页；无此能力则提供脱敏草稿和链接。现阶段使用匿名表单，API暂不部署，表单URL不能直接POST；[GitHub Issues](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/issues)保留为可选公开渠道。详见[反馈与纠错](wiki/反馈与纠错.md)。

```text
wiki/                         阅读指南、场景入口与资料目录
skills/shu-baoxiao/            可独立安装和复制的技能
  SKILL.md                    材料核对与证据使用流程
  references/                 知识源、场景索引和原文阅读页
  scripts/                    本地检索与 Word 结构提取
  assets/                     事项清单和可公开的资料副本
tools/                        公开来源维护、提取与打包工具
tests/                        数据、检索、链接和独立运行检查
```

本仓库维护 Wiki、技能和轻量资料工具，不包含学校登录、自动代填、提交审批或个人报销数据库。

## 来源与许可

学校官方入口：[上海大学财务处](https://cwc.shu.edu.cn/)。程序和原创指南采用 [Apache-2.0](LICENSE)；学校文件及摘录的权利属于原权利人，使用时请保留官方链接、标题和版本信息。详见 [来源说明](NOTICE.md)。
