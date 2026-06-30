# 上海大学自助报销 Agent

一个面向上海大学老师和学生的本地财务工作台：用聊天入口完成政策查询、票据归集、报销包生成、退回诊断和受控代填，把重复搬运数据的工作交给机器，把最终责任和确认留给本人。

本项目来自 [HINT Lab](http://www.hintlab.cn)。完整产品设计见 [PRODUCT_SPEC.md](PRODUCT_SPEC.md)，阶段路线图见 [PRODUCT_PLAN.md](PRODUCT_PLAN.md)。

## 为什么做

现有高校财务系统主要为合规、审计和支付设计，不是为前端填报体验设计。老师和学生常常要在政策文件、散落票据、邮件附件、报销网页和退回意见之间来回切换，把大量精力消耗在低价值操作上。

自助报销 Agent 不替代学校财务系统，也不绕过审批流程。它做的是在合规边界内建立一个本地个人财务工作台：规则前置、材料先整理、表单先生成草稿，最后由本人登录、确认经费项目、确认资金责任并提交。

核心边界：

- 人机隔离：Agent 只整理材料、查政策、生成草稿、辅助代填；登录、验证码、经费项目选择、真实性承诺和最终提交必须由本人完成。
- 本地优先：发票、邮件、报销记录和浏览器会话默认保存在本机，密钥和邮箱授权码不回显到前端。
- 规则前置：提交前先对照财务处公开口径生成缺漏清单和风险提示，减少“提交后等退回”的盲盒感。

## 当前能力

- 单一聊天首页：直接输入“版面费需要哪些材料”或“6 月北京会议差旅，报销高铁酒店”，系统自动判断是查政策、记录待报销事项，还是生成报销包。
- 上海大学财务知识库：抓取并整理财务处公开网页、附件入口、本地 PDF 和操作手册，支持 BM25 + 关键词召回，以及 DeepSeek、豆包/火山方舟或 OpenAI 兼容接口的带引用 RAG 回答。
- 材料归集：支持网页上传、`.eml` 邮件导入、IMAP 邮箱收票、聊天随手记和未归类材料池。
- 报销包生成：导出结构化报销包、缺漏清单、政策依据、事由草稿和 Playwright 代填计划。
- 报销状态流：待补材料、待本人复核、可代填、已提交、已退回、已报销等状态在本地 SQLite 中记录。
- 退回诊断：输入财务系统退回意见后，系统根据报销类型和已整理材料给出补材料建议。
- 受控代填：Playwright 可辅助打开网页、选择类型、填写事由、上传附件，但会在经费项目、资金确认和最终提交前停下。
- 设置页：配置工号、学校扫码登录保持、知识库大模型、IMAP 邮箱收票，并查看本地资料库状态。
- 已覆盖报销类型：国内差旅、版面费/出版费、办公用品/耗材、材料费、测试化验加工费、公务接待费、信息服务费。

## 技术结构

- 后端：FastAPI + SQLite，本地状态和配置默认放在 `data/`。
- 前端：Vite + React + Ant Design，构建产物由 FastAPI 服务。
- 桌面端：Tauri 作为本机窗口壳，可复用或拉起 `127.0.0.1:8765` 的 FastAPI 服务。
- 自动化：Playwright 用于本地模拟系统和真实系统人工登录后的辅助填写。
- 知识库：`data/cwc/index.json` 作为主要检索索引，处理后 JSONL 可在首次启动时导入 SQLite。

## 快速启动

安装依赖：

```bash
pip install -r requirements.txt
npm install
```

构建前端：

```bash
npm run build:frontend
```

启动本地网页工作台：

```bash
./start_dev.sh
```

`start_dev.sh` 会构建前端、初始化处理后的知识库 JSONL 到 SQLite，并启动 FastAPI。默认端口为 `8765`，可以用 `PORT=8888 ./start_dev.sh` 指定端口。

打开：

```text
http://127.0.0.1:8765/
```

桌面开发模式：

```bash
npm run tauri:dev
```

Tauri 会先检查 `http://127.0.0.1:8765/api/settings/status`。如果本地服务已经运行，桌面端会直接复用；否则会从项目根目录启动 FastAPI 服务。

## 常用配置

所有敏感配置都建议在设置页填写，本地文件会被 `.gitignore` 忽略。

### 知识库大模型

设置页路径：`/#settings` 的“知识库大模型配置”。

支持：

- DeepSeek
- 豆包/火山方舟
- 自定义 OpenAI 兼容接口

本地配置文件：

```text
data/settings/rag_llm.json
```

状态接口只返回 `has_api_key`，不会把 API Key 返回给前端。

### 邮箱收票

设置页路径：`/#settings` 的“邮箱收票”。

需要填写：

- IMAP 服务器
- 端口，默认 `993`
- 邮箱账号
- IMAP 授权码或应用专用密码
- 邮箱文件夹，默认 `INBOX`
- 是否拉取后标记已读

本地配置文件：

```text
data/settings/imap.json
```

手动轮询：

```bash
python3 tools/poll_imap.py --limit 10
```

系统会记录已处理邮件，避免同一封邮件重复生成报销包。

### 上海大学扫码登录保持

设置页路径：`/#settings` 的“上海大学扫码登录保持”。

系统使用本机专用浏览器 profile 保存财务系统业务会话，不保存统一身份认证密码，不保存 OAuth `code`，不绕过验证码或二次认证。

首次建立或续登时，在设置页点击“打开扫码登录窗口”。后台会启动专用浏览器窗口，用户在学校统一认证页扫码即可。

命令行检查：

```bash
python3 tools/shu_auth_session.py check
python3 tools/shu_auth_session.py saved-status
```

清除本机保存的浏览器会话：

```bash
python3 tools/shu_auth_session.py clear
```

会话文件位置：

```text
data/browser_profiles/shu-finance/
data/auth_sessions/shu_finance_session.json
```

## 知识库维护

刷新财务处公开资料：

```bash
python3 tools/crawl_cwc.py --max-pages 260 --max-attachments 160 --delay 0.12
```

追加本地 PDF：

```bash
python3 tools/ingest_local_pdfs.py
```

重建索引：

```bash
python3 tools/build_cwc_index.py
```

生成安装种子语料并导入 SQLite：

```bash
python3 tools/knowledge_seed.py --build --import-db
```

生成文件：

- `data/cwc/processed_documents.jsonl`
- `data/cwc/processed_chunks.jsonl`
- `data/cwc/processed_manifest.json`

首次启动会幂等导入 `data/app.db` 的知识库表。用户安装版应随包携带处理后的 JSONL，不要求用户重新爬取财务处网站。

## 报销包命令行

从本地材料生成报销包：

```bash
python3 tools/build_reimbursement_package.py samples/domestic_travel \
  --note "6 月去北京参加高校人工智能学术会议，报销高铁和酒店费用，走张老师科研项目" \
  --title "北京会议差旅报销包"
```

补充材料并重建同一报销包：

```bash
python3 tools/supplement_package.py \
  "办公用品报销包" \
  samples/office_supplies/03-公务卡支付记录.txt \
  --note "根据退回意见补充公务卡支付记录"
```

从 `.eml` 邮件导入：

```bash
python3 tools/ingest_eml.py samples/emails/office_supplies_forward.eml \
  --title "邮件导入办公用品报销包"
```

每个报销包会输出：

- `package.json`：结构化报销包。
- `package.md`：可读报告。
- `playwright_plan.json`：代填计划。
- `return_diagnosis.json/md`：退回诊断结果。

## Playwright 代填

本地 mock 演示：

```bash
python3 tools/playwright_fill_adapter.py \
  --plan output/packages/论文版面费报销包/playwright_plan.json \
  --adapter data/adapters/mock_school.json \
  --allow-auto-login
```

适配器：

- `data/adapters/mock_school.json`：本地模拟上海大学财务系统。
- `data/adapters/shu_finance.template.json`：真实上海大学财务系统适配模板。

真实系统只做人工登录后的辅助填写和上传，不自动提交，不绕过验证码，不代替本人作真实性承诺。

## 验证

核心验证：

```bash
python3 tools/verify_mvp.py
python3 tools/verify_web_rag.py
python3 tools/verify_frontend_render.py
python3 tools/verify_home_chat_policy_query.py
python3 tools/verify_settings_status.py
python3 tools/verify_status_flow.py
python3 tools/verify_playwright_demo.py
```

邮箱、退回和补材料验证：

```bash
python3 tools/verify_email_ingest.py
python3 tools/verify_web_email_upload.py
python3 tools/verify_mail_poll_settings.py
python3 tools/verify_return_diagnosis.py
python3 tools/verify_supplement_flow.py
```

## 数据目录

- `data/app.db`：本地 SQLite 状态库。
- `data/cwc/`：财务处知识库语料、索引和处理后种子。
- `data/settings/`：本机设置，包含大模型、邮箱、用户工号等。
- `data/uploads/`：网页上传暂存。
- `data/mail_inbox/`：邮箱轮询缓存。
- `data/auth_sessions/`：学校财务系统会话状态。
- `data/browser_profiles/`：专用浏览器 profile。
- `data/adapters/`：Playwright 页面适配器。
- `output/packages/`：生成的报销包。
- `web/static/dist/`：Vite 构建产物。

## 当前边界

- 本项目不是上海大学官方系统，最终口径以学校财务处、财务系统预审和人工审核为准。
- 对需要验证码的附件，只记录入口和状态，不绕过下载。
- RAG 回答必须带来源引用；模型回答不能替代财务处正式解释。
- 当前发票识别以文本、规则、可选 OCR 和可选大模型增强为主，OFD、复杂扫描 PDF 和权威发票验真仍需继续接入。
- 邮箱收票依赖用户提供允许 IMAP 的邮箱或中转邮箱。
- 真实财务系统代填需要继续补齐页面适配器；任何提交动作必须由本人手动完成。

## 协议

本项目采用 [Apache License 2.0](LICENSE)。

Copyright 2026 HINT Lab.

使用、修改和分发本项目时，必须保留版权声明和许可证文本。Apache 2.0 同时包含专利授权与免责声明；它允许商用和二次分发，但要求遵守许可证中的署名、变更声明和再分发条件。

## 关于我们

本项目来自 [HINT Lab](http://www.hintlab.cn)。

在我们实验室，我们始终在追问和关注一个命题：到底应该是技术服务于人，还是让人沦为系统的附庸？

现有的许多流程（比如繁琐的报销），本质上是在无形中剥削人的认知。它把原本应该专注于创造的人，异化成了在死板规则和难用网页之间机械搬运数据的“生物接口”。

我们不愿看到人被系统这样消耗。但打破这种现状，不能仅靠在云端的高谈阔论，而是必须有人愿意把双手插进泥土里，去写下那几万行抵抗枯燥的代码，去一点点修补现实的粗糙。

这个 Agent，就是我们用泥土的双手给出的答案：把脏活累活交还给机器，让人回归为真正的人。

如果你也认同这样的技术观，欢迎访问 [HINT 实验室主页](http://www.hintlab.cn)，和我们一起去重塑人与系统的边界。
