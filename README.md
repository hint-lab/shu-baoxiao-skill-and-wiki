# 上海大学报销 Wiki & Skill

查规则、核对材料、理解退回意见。在你已有的 AI 工具里使用，不需要启动报销应用、配置另一套模型或登录学校系统。

来自 [HINT Lab](https://www.hintlab.cn)。本项目为社区整理，学校原文是证据来源；资料覆盖和时效状态会明确标出。

## 直接使用

- **看指南**：[Wiki 首页](wiki/Home.md)，按差旅、版面费、专家咨询费、采购等场景进入。
- **整理材料**：[学校资料总览](wiki/材料整理.md)、[表格入口与常用空白表格副本](wiki/空白表格.md)、[待补资料](wiki/待补资料.md)、[需要协助取得的资料](wiki/需要协助.md)。个人每笔报销按 [事项包方法](wiki/个人材料整理.md) 留在本地。
- **Codex**：下载 [Codex 技能包](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-reimbursement-codex.zip)，把解压后的 `shu-reimbursement` 整个文件夹复制到 `~/.agents/skills/`，调用 `$shu-reimbursement`。也可使用环境中的技能安装器从本仓库安装 `skills/shu-reimbursement`。
- **WorkBuddy**：下载 [WorkBuddy 技能包](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-reimbursement-workbuddy.zip)，在“添加技能 → 上传技能”中导入 ZIP。该包按官方技能元数据格式生成，实际客户端导入和对话效果仍需验收。
- **豆包及普通聊天工具**：下载 [场景资料包](https://github.com/hint-lab/shu-baoxiao-skill-and-wiki/releases/latest/download/shu-reimbursement-chat.zip)，选择对应场景的文本，结合 [通用对话用法](wiki/使用方法.md) 使用。这里不假定豆包支持安装或执行本 Skill。

例如：

> 用上大报销技能检查这个文件夹里的版面费材料。先确认适用场景，再查学校原文，列出已有、缺少和待确认的内容，每项附依据。

> 财务退回说“缺付款依据”，请结合我已有的材料解释怎么补，不要编写不存在的证明。

## Skill 怎样工作

1. 确认报销事项、经费类型、人员身份、业务日期等会改变判断的条件。
2. 检索并阅读学校资料，核对原文上下文、附件状态与时效。
3. 使用当前 AI 工具的文件读取能力检查用户授权的材料。
4. 返回材料核对结果、补齐步骤、来源和仍待确认的问题。

Skill 不保存用户材料，不代替真实性签字或审批，不自动提交学校系统。材料无法读取时标记“未识别/待查看”，不能直接判为缺失。没有明确依据的要求不能写成“学校必须”。

## 本地查资料

只需 Python 3.10+ 标准库，不需要安装依赖或启动服务：

```bash
python3 skills/shu-reimbursement/scripts/knowledge.py search "外币 版面费"
python3 skills/shu-reimbursement/scripts/knowledge.py search "专家咨询费"
python3 skills/shu-reimbursement/scripts/knowledge.py status
```

检索结果带有文档 ID。用 `read 文档ID` 阅读全文，或者加 `--query 关键词` 定位段落。`--json` 返回结构化证据。检索本身不联网、不调用其他大模型。

需要核对本机 Word 时，可运行 `python3 skills/shu-reimbursement/scripts/word_to_markdown.py 文件.docx --json`，保留表格合并关系。旧版 `.doc` 需要本机 LibreOffice；解析警告会明确列出无法提取的对象。

## 维护与发布

```bash
# 更新公开官方页面快照；附件未解析时保留状态。
python3 tools/maintain.py refresh https://cwc.shu.edu.cn/info/1113/4276.htm

# 将人工核对、提取的附件文字关联回官方入口。
python3 tools/maintain.py import-text --url '<官方附件URL>' --title '<资料标题>' --text '<UTF-8文本文件>'

# 维护者可调用自己授权的 P330 MinerU 网关；凭据留在服务器。
python3 tools/mineru_p330.py '<文件.pdf>' --ssh-host '<SSH别名>' --output tmp/mineru-result --tier basic

# 重建 Wiki 阅读页、资料目录、技能包和普通聊天场景包。
python3 tools/build.py
python3 -m unittest discover -s tests -v
python3 tools/build.py --check
```

维护流程是“发现变化 → 核对原文与适用条件 → 更新资料 → 构建并发布”。仓库更新不会自动更新别人已经安装的技能包；发布新版本后需要重新安装或由使用方显式同步。具体见 [资料维护](wiki/维护方法.md)。

## 仓库结构

```text
wiki/                         给人阅读的指南与资料目录
skills/shu-reimbursement/      可独立复制、安装的技能
  SKILL.md                    AI 工作流程
  references/                 场景路由、资料快照与原文阅读页
  scripts/knowledge.py         无外部依赖的检索、原文读取
tools/                        维护和打包脚本
tests/                        检索、搬迁、数据与打包验证
```

不包含独立前后端、桌面客户端、邮箱轮询、学校登录、自动代填或个人报销数据库。旧版应用和本机资料已在迁移时另行保存，旧实现也保留在 Git 历史中。

## 来源与使用条件

程序和原创指南采用 [Apache-2.0](LICENSE)。学校文件及其摘录保持原有权利归属，不因本仓库代码许可证而重新授权；使用时保留官方链接、标题和版本信息。未取得的附件、失效状态与时效不明会如实列出。详见 [来源说明](NOTICE.md)。
