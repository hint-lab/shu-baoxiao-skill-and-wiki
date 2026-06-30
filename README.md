# 上海大学财务处本地 RAG

这个工作区用于把上海大学财务处公开网站内容整理成本地可检索资料库，先服务于自助报销材料准备和人工核对。

完整产品规格见：[PRODUCT_SPEC.md](PRODUCT_SPEC.md)。

阶段路线图见：[PRODUCT_PLAN.md](PRODUCT_PLAN.md)。

## 当前能力

- 抓取 `https://cwc.shu.edu.cn/` 公开页面正文。
- 记录页面中的附件入口。
- 识别需要验证码的附件下载页，不绕过验证码。
- 提取可直接下载 PDF 的文本。
- 追加本地已有 PDF，例如智能报销操作手册和 2018 常见业务费报销指南。
- 构建本地 BM25 检索索引。
- 用命令行按问题返回来源、片段和分数。
- 本地网页工作台可以直接查询财务处资料库，并展示来源链接和原文片段。
- 本地网页工作台已改为 Ant Design 风格的 React 前端。
- 本地 SQLite 记录报销包工作流状态，支持在详情页手动标记待复核、可代填、已提交和已报销。
- 资料归集支持聊天随手记：先保存一句备注，后续再转成待补材料报销包。
- 主页 Chat 会自动分流：报销规则问题进入知识库检索，事项描述进入资料归集，带附件则生成报销包。
- 导入本地报销材料，生成报销包、缺漏清单、政策依据和事由草稿。
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
```

验证报销状态流和已报销工作区：

```bash
python3 tools/verify_status_flow.py
```

验证聊天随手记资料归集：

```bash
python3 tools/verify_inbox_note_flow.py
```

验证主页 Chat 报销问题分流：

```bash
python3 tools/verify_home_chat_policy_query.py
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

首页也可以直接问财务处资料库，例如“版面费报销需要哪些材料”。当前返回的是检索式答复、来源链接和原文片段，不替代财务处最终口径。

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

## 数据位置

- 语料：`data/cwc/documents.jsonl`
- 索引：`data/cwc/index.json`
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
- 当前问答是检索式，不调用大模型生成最终口径；提交报销前仍要以财务处系统预审和最新通知为准。
- 当前报销包生成器是本地规则 + 检索依据版本，已支持文本型发票字段解析、可选图片 OCR 和可选豆包字段增强；OFD、复杂扫描 PDF 和权威发票验真还未接入。
- 邮箱收票已有 `.eml` 导入和 IMAP 轮询原型，真实使用前需要配置学校允许的邮箱或中转邮箱。
- Playwright 代填目前已完成本地模拟上海大学财务系统演示和通用适配器配置；真实上海大学财务系统需要老师人工登录后补齐页面适配器。
- 退回诊断目前覆盖国内差旅、版面费/出版费、办公用品/耗材的常见退回原因；其他类型未匹配时会保留原退回意见并要求人工核对。
- 后续可以接入模型做带引用的生成回答，但必须保留来源链接和原文片段。
