# 上海大学财务处本地 RAG

这个工作区用于把上海大学财务处公开网站内容整理成本地可检索资料库，先服务于自助报销材料准备和人工核对。

完整产品规格见：[PRODUCT_SPEC.md](PRODUCT_SPEC.md)。

阶段路线图见：[PRODUCT_PLAN.md](PRODUCT_PLAN.md)。

## 关于本软件：我们为什么需要一个报销 Agent？

现有的高校财务系统，是为“合规、审计和支付”设计的，而不是为“方便前端填报”设计的。这导致老师和学生们每天面临着巨大的低价值劳动：反复查找政策依据、整理散落各处的票据、在难用的网页上重复搬运数据，以及面对被财务退回后从头再来的崩溃。

“自助报销 Agent”的初衷，不是去替代现有的财务系统，更不是去绕过学校的审批流程。它是在现有的合规边界内，为你建立一个本地的个人财务工作台。

为了绝对的安全与合规，本软件坚守以下边界：

1. 人机隔离：Agent 只负责整理材料、查阅政策、生成草稿和辅助代填；而账号登录、经费项目选择、资金确认与最终提交，必须由用户本人手动完成。
2. 本地优先：票据和数据默认在本地处理，最大程度保护个人财务隐私。
3. 把规则前置：改变“提交后等退回”的盲盒模式，在提交前系统就会自动对照财务处公开口径，生成“缺漏清单”和风险提示。

我们希望通过这个工具，把你从繁杂的材料整理和表单搬运中彻底解放出来。机器处理复杂流程，人类只需确认责任。

## 当前能力

- 抓取 `https://cwc.shu.edu.cn/` 公开页面正文。
- 记录页面中的附件入口。
- 识别需要验证码的附件下载页，不绕过验证码。
- 提取可直接下载 PDF 的文本。
- 追加本地已有 PDF，例如智能报销操作手册和 2018 常见业务费报销指南。
- 构建本地 BM25 + 关键词混合检索索引，并输出入库质量报告。
- 用命令行按问题返回来源、片段、BM25 分数、关键词分数和命中关键词。
- 本地网页工作台可以直接查询财务处资料库，并展示来源链接和原文片段。
- 本地网页工作台已改为 Ant Design 风格的 React 前端。
- 已接入 `logo.png` 作为上海大学财务助手品牌图标。
- 本地 SQLite 记录报销包工作流状态，支持在详情页手动标记待复核、可代填、已提交、已退回和已报销。
- 资料归集支持聊天随手记：先保存一句备注，后续再转成待补材料报销包。
- 资料归集支持未归类材料池：网页上传的散乱材料可先暂存，记录文件大小和 hash，后续再生成报销包。
- 主页是单一 Chat 入口，使用 Ant Design 图标按钮完成附件上传、知识库跳转和发送；报销规则问题进入知识库检索，事项描述进入资料归集，带附件则生成报销包。
- 等待报销页按真实状态分组：缺材料、等待复核、可代填、已提交和退回待处理。
- 设置页支持在 IMAP 配置完整后手动拉取发票邮件；未配置时按钮禁用，接口只返回缺失项，不暴露邮箱密钥。
- 导入本地报销材料，生成报销包、缺漏清单、政策依据和事由草稿。
- 报销包详情页支持受控代填演示：材料齐全且本人确认可代填后，运行 Playwright mock 代填并停在提交前。
- 确认可代填前必须逐项勾选经费项目、收款账号、票据真实性、不会自动提交和提交前复核；后端也会拦截未确认的直接请求。
- 代填演示完成后，详情页直接展示操作日志、字段快照和截图证据，不需要打开 JSON 才能核对。
- 设置页展示真实接入状态：豆包、IMAP 邮箱、知识库索引和 Playwright 适配器；不暴露密钥或邮箱密码。
- 报销知识库展示索引统计、入库文档数、空文本附件提示、抓取时间和来源类型，并支持按财务处网页、附件入口、本地 PDF 筛选检索结果。
- 文本型发票可提取购买方、销售方、项目、发票号、日期、金额和币种；图片材料在本机装有 tesseract 时会尝试 OCR。
- 可选接入豆包/火山方舟模型做票据和表单字段增强识别。
- 当前已覆盖国内差旅报销、版面费/出版费、办公用品/耗材报销、材料费、测试化验加工费、公务接待费、信息服务费。

## 使用

刷新公开网站资料：

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

生成带标签的安装种子语料，并导入本机 SQLite：

```bash
python3 tools/knowledge_seed.py --build --import-db
```

这一步会生成：

- `data/cwc/processed_documents.jsonl`：按文档打好标签的语料种子，包含来源、入库状态、关键词、报销类别标签和元数据。
- `data/cwc/processed_chunks.jsonl`：按检索片段打好标签的正文种子，包含片段文本、关键词和 BM25 长度。
- `data/cwc/processed_manifest.json`：种子语料清单和 hash。

应用启动时会自动检查这些处理后 JSONL，并幂等导入 `data/app.db` 的 `knowledge_documents`、`knowledge_chunks` 表。用户安装版应随包携带处理后的 JSONL；首次启动只做本机数据库初始化，不重新爬取财务处、不重新解析 PDF。正常检索优先使用随包携带的 `index.json`，如果索引文件缺失，也会从 SQLite 的 `knowledge_chunks` 临时构建 BM25 索引继续查询。

查询：

```bash
python3 tools/ask_cwc.py "版面费 外币支付 报销 需要什么材料" --top-k 5
```

生成报销包：

```bash
python3 tools/build_reimbursement_package.py samples/domestic_travel \
  --note "6 月去北京参加高校人工智能学术会议，报销高铁和酒店费用，走张老师科研项目" \
  --title "北京会议差旅报销包"
```

验证 MVP 样例：

```bash
python3 tools/verify_mvp.py
```

验证网页 RAG 问答：

```bash
python3 tools/verify_web_rag.py
python3 tools/verify_knowledge_filters.py
```

验证 Ant Design 前端渲染：

```bash
python3 tools/verify_frontend_render.py
python3 tools/verify_frontend_upload.py
```

验证发票结构化字段：

```bash
python3 tools/verify_structured_fields.py
```

验证 Playwright 代填演示：

```bash
python3 tools/verify_playwright_demo.py
python3 tools/verify_fill_demo_from_detail.py
python3 tools/verify_responsibility_confirmation_gate.py
```

验证报销状态流和已报销工作区：

```bash
python3 tools/verify_status_flow.py
python3 tools/verify_returned_status_flow.py
```

验证聊天随手记资料归集：

```bash
python3 tools/verify_inbox_note_flow.py
python3 tools/verify_material_pool_flow.py
```

验证主页 Chat 报销问题分流：

```bash
python3 tools/verify_home_chat_policy_query.py
```

验证设置页接入状态：

```bash
python3 tools/verify_settings_status.py
python3 tools/verify_mail_poll_settings.py
```

验证退回诊断：

```bash
python3 tools/verify_return_diagnosis.py
```

验证补充材料后重新整理：

```bash
python3 tools/verify_supplement_flow.py
```

验证邮件导入：

```bash
python3 tools/verify_imap_fixture.py
python3 tools/verify_email_ingest.py
python3 tools/verify_web_email_upload.py
```

启动本地网页工作台：

```bash
uvicorn app:app --host 127.0.0.1 --port 8765
```

打开后可以在浏览器上传材料、填写一句话备注，并查看生成的报销包、缺漏清单、事由草稿和来源依据。

前端已迁移为 Vite + React + Ant Design。首次运行前安装前端依赖：

```bash
npm install
```

构建前端产物：

```bash
npm run build:frontend
```

本地网页开发仍由 FastAPI 提供动态数据和 SQLite 状态：

```bash
npm run dev:web
```

桌面端使用 Tauri 作为本机窗口壳，当前开发模式加载同一个 `http://127.0.0.1:8765` 本地服务：

```bash
npm run tauri:dev
```

Tauri 主进程会先检查 `http://127.0.0.1:8765/api/settings/status`。如果 8765 端口已经有可用的本地服务，桌面端会直接复用；否则会从项目根目录启动 `python3 -m uvicorn app:app --host 127.0.0.1 --port 8765`。退出桌面窗口时，只会关闭由 Tauri 自己拉起的 FastAPI 子进程，不会杀掉你手动启动的服务。

设置页在桌面端会显示“桌面本地服务”状态，包括是否由 Tauri 托管、PID 和健康状态。当前桌面版已可本机运行；正式分发版还需要把 Python 运行时和 FastAPI/SQLite 服务打成 sidecar 或安装时托管的本机后台进程。

首页也可以直接问财务处资料库，例如“版面费报销需要哪些材料”。当前返回的是检索式答复、来源链接和原文片段，不替代财务处最终口径。

知识库支持完整 RAG 生成：先用 BM25 + 关键词从本地知识库召回来源片段，再调用设置页配置的 DeepSeek、豆包/火山方舟或自定义 OpenAI 兼容接口生成带引用编号的回答。未配置大模型时会自动退回到可追溯检索片段。

大模型配置入口：

- 网页设置页：`/#settings` 中的“知识库大模型配置”
- 本机配置文件：`data/settings/rag_llm.json`

配置文件会被 `.gitignore` 忽略；状态接口只返回 `has_api_key`，不会把密钥返回给前端。

网页上传支持 `.eml` 邮件文件。系统会自动抽取邮件正文作为备注，并把邮件附件作为报销材料。

每个报销包会导出：

- `package.json`：结构化报销包。
- `package.md`：可读报告。
- `playwright_plan.json`：后续 Playwright 代填使用的计划，包含推荐入口、事由、材料列表和必须暂停确认的节点。
- `return_diagnosis.json/md`：输入财务系统退回意见后生成的诊断结果。

材料表会展示已识别出的发票抬头、销售方、项目、发票号、金额和日期。国内发票购买方不是“上海大学”时会进入风险提示。

补充材料并重新生成同一报销包：

```bash
python3 tools/supplement_package.py \
  "办公用品报销包" \
  samples/office_supplies/03-公务卡支付记录.txt \
  --note "根据退回意见补充公务卡支付记录"
```

系统会把旧版报销包归档到当前报销包目录下的 `versions/`，再用原材料加补充材料重建 checklist、事由和 `playwright_plan.json`。

从邮件文件导入报销材料：

```bash
python3 tools/ingest_eml.py samples/emails/office_supplies_forward.eml \
  --title "邮件导入办公用品报销包"
```

轮询邮箱收票：

```bash
cp .env.example .env
# 按实际邮箱填写 .env 后，把变量加载进当前 shell
set -a
source .env
set +a

python3 tools/poll_imap.py --limit 10
```

本地 fixture 验证轮询逻辑：

```bash
python3 tools/poll_imap.py \
  --fixture-eml samples/emails/office_supplies_forward.eml \
  --state data/mail_inbox/test_state.json
```

IMAP 轮询会记录已处理邮件，避免同一封邮件重复生成报销包。不要把真实邮箱密码提交到仓库；建议使用邮箱服务提供的应用专用密码或 token。

启用豆包/火山方舟识别增强：

```bash
cp .env.example .env
# 填写 DOUBAO_API_KEY 和 DOUBAO_MODEL，并设置 DOUBAO_EXTRACT_ENABLED=true
set -a
source .env
set +a
```

豆包识别只作为字段补充层：本地规则先提取字段，模型只补本地没识别出的购买方、销售方、金额、发票号、日期等字段。未配置密钥时系统完全离线运行。

手动运行代填演示：

```bash
python3 tools/playwright_fill_adapter.py \
  --plan output/packages/论文版面费报销包/playwright_plan.json \
  --adapter data/adapters/mock_school.json \
  --allow-auto-login
```

Playwright 代填采用页面适配器配置：

- `data/adapters/mock_school.json`：本地模拟上海大学财务系统，用于验证代填闭环。
- `data/adapters/shu_finance.template.json`：真实上海大学财务系统适配模板，需要在老师本人完成登录后，补充真实 URL 和页面选择器。

真实系统适配只做人工登录后的辅助填写和上传，不保存统一身份认证密码，不绕过验证码或二次认证，不自动点击提交。

## 上海大学扫码登录保持

真实财务系统登录保持使用本机专用浏览器 profile。系统只保存扫码成功后的浏览器会话状态，不保存密码，不保存 OAuth `code`，也不绕过统一身份认证、验证码或二次认证。

首次建立或重新扫码：

```bash
python3 tools/shu_auth_session.py login
```

这个命令会打开专用浏览器，先访问上海大学财务系统首页；如果业务会话已过期，会进入 `#/Login/ShuAuth`，再由上海大学统一身份认证签发报销系统自己的登录态。统一认证也过期时，页面会停在“上海大学统一身份认证”，需要本人扫码。

检查当前业务会话：

```bash
python3 tools/shu_auth_session.py check
```

只查看本地保存的上次状态，不启动浏览器：

```bash
python3 tools/shu_auth_session.py saved-status
```

清除本机保存的专用浏览器会话：

```bash
python3 tools/shu_auth_session.py clear
```

会话文件放在本机忽略目录：

- `data/browser_profiles/shu-finance/`
- `data/auth_sessions/shu_finance_session.json`

启动本地网页工作台后，设置页会展示上次检测结果。每次真实代填前应先确认财务系统业务会话可用；如果只剩 `newsso.shu.edu.cn` 统一身份会话，重新运行 `python3 tools/shu_auth_session.py login` 通常可以自动续登到报销系统。

## 数据位置

- 语料：`data/cwc/documents.jsonl`
- 索引：`data/cwc/index.json`
- 处理后安装语料：`data/cwc/processed_documents.jsonl`、`data/cwc/processed_chunks.jsonl`、`data/cwc/processed_manifest.json`
- 原始 HTML：`data/cwc/raw/`
- 附件：`data/cwc/attachments/`
- 报销规则：`data/rules/reimbursement_rules.json`
- 本地状态库：`data/app.db`
- 报销包输出：`output/packages/`
- 样例材料：`samples/`
- 邮件导入材料：`data/mail_ingest/`
- 邮箱轮询缓存：`data/mail_inbox/`
- 测试输入：`data/test_inputs/`
- 网页上传暂存：`data/uploads/`
- Playwright 页面适配器：`data/adapters/`
- 前端脚本：`web/static/app-index.js`、`web/static/app-package.js`

## 当前边界

- 这是公开资料检索系统，不自动登录学校门户。
- 对需要验证码的附件，只记录入口和状态，不绕过下载。
- 当前问答是 BM25 + 关键词混合检索式，不调用大模型生成最终口径；提交报销前仍要以财务处系统预审和最新通知为准。
- 当前报销包生成器是本地规则 + 检索依据版本，已支持文本型发票字段解析、可选图片 OCR 和可选豆包字段增强；OFD、复杂扫描 PDF 和权威发票验真还未接入。
- 邮箱收票已有 `.eml` 导入和 IMAP 轮询原型，真实使用前需要配置学校允许的邮箱或中转邮箱。
- Playwright 代填目前已完成本地模拟上海大学财务系统演示和通用适配器配置；真实上海大学财务系统需要老师人工登录后补齐页面适配器。
- 退回诊断目前覆盖国内差旅、版面费/出版费、办公用品/耗材的常见退回原因；其他类型未匹配时会保留原退回意见并要求人工核对。
- 后续可以接入模型做带引用的生成回答，但必须保留来源链接和原文片段。
