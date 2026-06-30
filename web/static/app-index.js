(function () {
  const e = React.createElement;
  const {
    Alert,
    App,
    Button,
    Card,
    Col,
    ConfigProvider,
    Empty,
    Form,
    Input,
    Layout,
    List,
    Menu,
    Row,
    Select,
    Space,
    Statistic,
    Tag,
    Typography,
    Upload,
    message,
    theme,
  } = antd;

  const data = window.__REIMBURSEMENT_DATA__ || {};
  const allPackages = data.packages || data.recent || [];
  const inboxItems = data.inbox_items || [];
  const Dragger = Upload.Dragger;
  const { Content, Sider } = Layout;
  const { Title, Text, Paragraph } = Typography;
  const Icons = window.icons || window.AntDesignIcons || {};
  const {
    CheckCircleOutlined,
    ClockCircleOutlined,
    DatabaseOutlined,
    FolderOpenOutlined,
    HomeOutlined,
    InboxOutlined,
    MessageOutlined,
    PaperClipOutlined,
    SearchOutlined,
    SendOutlined,
    SettingOutlined,
  } = Icons;
  const NAV_KEYS = ["home", "knowledge", "collection", "waiting", "reimbursed", "settings"];

  function icon(IconComponent) {
    return IconComponent ? e(IconComponent) : null;
  }

  function normalizeKey(value) {
    const key = String(value || "").replace("#", "");
    return NAV_KEYS.includes(key) ? key : "home";
  }

  function missingCount(pkg) {
    return (pkg.checklist || []).filter((item) => item.status === "missing").length;
  }

  function packageStatus(pkg) {
    return String(pkg.reimbursement_status || pkg.workflow_status || pkg.status || "").toLowerCase();
  }

  function isReimbursed(pkg) {
    return packageStatus(pkg) === "reimbursed";
  }

  function needsMaterials(pkg) {
    const status = packageStatus(pkg);
    return !isReimbursed(pkg) && (status === "collecting" || status === "needs_materials" || missingCount(pkg) > 0);
  }

  function waitingPackages(packages) {
    return packages.filter((pkg) => !isReimbursed(pkg));
  }

  function reimbursedPackages(packages) {
    return packages.filter(isReimbursed);
  }

  function typeColor(type) {
    const map = {
      domestic_travel: "geekblue",
      publication_fee: "purple",
      office_supplies: "green",
      materials_fee: "volcano",
      testing_processing_fee: "cyan",
      official_reception: "red",
      information_service_fee: "gold",
    };
    return map[type] || "blue";
  }

  function statusSummary(pkg) {
    const labels = {
      collecting: ["default", "资料归集中"],
      needs_materials: ["red", "待补材料"],
      ready_for_review: ["blue", "待本人复核"],
      ready_for_school: ["geekblue", "等待代填"],
      submitted_by_user: ["gold", "已提交"],
      reimbursed: ["green", "已报销"],
    };
    const status = packageStatus(pkg);
    if (labels[status]) {
      const [color, label] = labels[status];
      return e(Tag, { color }, label);
    }
    const missing = missingCount(pkg);
    if (missing) return e(Tag, { color: "red" }, `${missing} 项缺漏`);
    return e(Tag, { color: "blue" }, "待本人复核");
  }

  function menuLabel(label, count) {
    return count === undefined ? label : `${label} ${count}`;
  }

  function reloadCollection() {
    window.location.href = "/?refresh=" + Date.now() + "#collection";
  }

  function isPolicyQuestion(text) {
    const value = String(text || "").trim();
    if (!value) return false;
    if (/[?？]/.test(value)) return true;
    if (/^(怎么|如何|为什么|哪些|什么|能否|能不能|可不可以|是否)/.test(value)) return true;
    if (/需要.*(什么|哪些|材料|附件|手续)/.test(value)) return true;
    if (/(报销|发票).*(要求|规定|标准|流程|材料|附件|依据)/.test(value)) return true;
    return false;
  }

  function Sidebar({ activeKey, onSelect }) {
    const pending = waitingPackages(allPackages).length;
    const collecting = allPackages.filter(needsMaterials).length + inboxItems.length;
    const finished = reimbursedPackages(allPackages).length;
    const items = [
      { key: "home", icon: icon(HomeOutlined), label: "主页" },
      { key: "knowledge", icon: icon(DatabaseOutlined), label: "报销知识库" },
      { key: "waiting", icon: icon(ClockCircleOutlined), label: menuLabel("等待报销", pending) },
      { key: "collection", icon: icon(FolderOpenOutlined), label: menuLabel("资料归集", collecting) },
      { key: "reimbursed", icon: icon(CheckCircleOutlined), label: menuLabel("已报销", finished) },
      { key: "settings", icon: icon(SettingOutlined), label: "设置" },
    ];
    return e(
      Sider,
      { width: 224, className: "app-sider", breakpoint: "lg", collapsedWidth: 0 },
      e(
        "a",
        { className: "brand-block", href: "/#home" },
        e("strong", null, "上海大学"),
        e("span", null, "自助报销 Agent")
      ),
      e(Menu, {
        theme: "dark",
        mode: "inline",
        selectedKeys: [activeKey],
        items,
        onClick: ({ key }) => onSelect(key),
      })
    );
  }

  function UploadWorkbench() {
    const [form] = Form.useForm();
    const [fileList, setFileList] = React.useState([]);
    const [submitting, setSubmitting] = React.useState(false);

    async function submit(values) {
      if (!fileList.length) {
        message.warning("请先选择发票或附件材料");
        return;
      }
      const body = new FormData();
      body.append("title", values.title || "");
      body.append("note", values.note || "");
      fileList.forEach((file) => body.append("files", file.originFileObj || file));
      setSubmitting(true);
      try {
        const response = await fetch("/packages", { method: "POST", body, redirect: "follow" });
        window.location.href = response.url || "/";
      } catch (error) {
        message.error("生成报销包失败，请检查材料后重试");
        setSubmitting(false);
      }
    }

    return e(
      Card,
      { className: "work-card", title: "整理报销材料" },
      e(
        Form,
        { form, layout: "vertical", onFinish: submit },
        e(Form.Item, { label: "报销事项名称", name: "title" }, e(Input, { placeholder: "例如：北京会议差旅报销包" })),
        e(
          Form.Item,
          { label: "一句话备注", name: "note" },
          e(Input.TextArea, {
            rows: 4,
            placeholder: "例如：6 月去北京参加高校人工智能学术会议，报销高铁和酒店费用，走张老师科研项目",
          })
        ),
        e(
          Form.Item,
          { label: "材料" },
          e(
            Dragger,
            {
              multiple: true,
              beforeUpload: () => false,
              fileList,
              onChange: ({ fileList: next }) => setFileList(next),
            },
            e("p", { className: "upload-symbol" }, "↑"),
            e("p", { className: "ant-upload-text" }, "拖入或选择发票、通知、支付记录、审批材料"),
            e("p", { className: "ant-upload-hint" }, "支持 PDF、Word、文本、截图和 .eml 邮件文件；邮件会自动抽取正文和附件。")
          )
        ),
        e(Button, { type: "primary", htmlType: "submit", loading: submitting }, "生成报销包")
      )
    );
  }

  function HomeAssistantChat() {
    const [form] = Form.useForm();
    const [fileList, setFileList] = React.useState([]);
    const [submitting, setSubmitting] = React.useState(false);
    const noteValue = Form.useWatch("note", form) || "";
    const shouldAskPolicy = !fileList.length && isPolicyQuestion(noteValue);

    async function submit(values) {
      const currentValues = form.getFieldsValue();
      const note = (values.note || currentValues.note || noteValue || "").trim();
      const title = (values.title || currentValues.title || "").trim();
      if (!note && !fileList.length) {
        message.warning("写一句报销事项，或者上传发票和附件");
        return;
      }
      if (!fileList.length && isPolicyQuestion(note)) {
        window.location.href = "/?q=" + encodeURIComponent(note) + "#knowledge";
        return;
      }
      const body = new FormData();
      body.append("title", title);
      body.append("note", note);
      fileList.forEach((file) => body.append("files", file.originFileObj || file));
      setSubmitting(true);
      try {
        const url = fileList.length ? "/packages" : "/inbox-items";
        const response = await fetch(url, { method: "POST", body, redirect: "follow" });
        if (fileList.length) {
          window.location.href = response.url || "/";
        } else {
          reloadCollection();
        }
      } catch (error) {
        message.error("处理失败，请检查材料后重试");
        setSubmitting(false);
      }
    }

    return e(
      "div",
      { className: "home-chat-wrap" },
      e(
        "div",
        { className: "home-chat-head" },
        e("div", { className: "assistant-mark" }, icon(MessageOutlined)),
        e(Title, { level: 1 }, "上海大学报销助手"),
        e(Text, { type: "secondary" }, "直接问报销规则，或说一句要报什么并拖入发票、邮件、附件。")
      ),
      e(
        Card,
        { className: "home-chat-card" },
        e(
          Form,
          { form, layout: "vertical", onFinish: submit },
          e(Form.Item, { label: "事项名称", name: "title" }, e(Input, { placeholder: "例如：北京会议差旅 / 材料采购 / 信息服务费" })),
          e(
            Form.Item,
            { label: "报销助手", name: "note" },
            e(Input.TextArea, {
              rows: 7,
              placeholder: "例如：版面费报销需要哪些材料？\n或者：6 月去北京参加高校人工智能会议，报销高铁、酒店和会务相关费用，走张老师科研项目。",
            })
          ),
          e(
            Dragger,
            {
              className: "chat-upload",
              multiple: true,
              beforeUpload: () => false,
              fileList,
              onChange: ({ fileList: next }) => setFileList(next),
            },
            e("p", { className: "upload-symbol" }, icon(PaperClipOutlined) || "↑"),
            e("p", { className: "ant-upload-text" }, "拖入发票、支付记录、合同、通知或 .eml 邮件"),
            e("p", { className: "ant-upload-hint" }, "带附件会直接整理成报销包；只有文字会先进入资料归集。")
          ),
          e(
            "div",
            { className: "chat-actions" },
            e(Button, { href: "/#knowledge", icon: icon(SearchOutlined) }, "查报销依据"),
            e(
              Button,
              { type: "primary", htmlType: "submit", loading: submitting, icon: icon(shouldAskPolicy ? SearchOutlined : fileList.length ? InboxOutlined : SendOutlined) },
              shouldAskPolicy ? "查询依据" : fileList.length ? "生成报销包" : "存入资料归集"
            )
          )
        )
      )
    );
  }

  function QuickNoteInbox() {
    const [form] = Form.useForm();
    const [submitting, setSubmitting] = React.useState(false);
    async function submit(values) {
      const note = (values.note || "").trim();
      if (!note) {
        message.warning("先写一句随手备注");
        return;
      }
      const body = new FormData();
      body.append("title", values.title || "");
      body.append("note", note);
      setSubmitting(true);
      try {
        await fetch("/inbox-items", { method: "POST", body, redirect: "follow" });
        reloadCollection();
      } catch (error) {
        message.error("保存随手记失败");
        setSubmitting(false);
      }
    }
    return e(
      Card,
      { className: "work-card", title: "聊天随手记" },
      e(
        Form,
        { form, layout: "vertical", onFinish: submit },
        e(Form.Item, { label: "事项名称", name: "title" }, e(Input, { placeholder: "例如：6 月北京会议酒店票" })),
        e(
          Form.Item,
          { label: "随手备注", name: "note", rules: [{ required: true, message: "请写一句备注" }] },
          e(Input.TextArea, { rows: 4, placeholder: "例如：这张酒店发票是 6 月去北京开会，住宿两晚，后面再补会议通知和支付记录。" })
        ),
        e(Button, { type: "primary", htmlType: "submit", loading: submitting }, "存入资料归集")
      )
    );
  }

  function RagPanel() {
    const [query, setQuery] = React.useState(data.q || "");
    const [sourceType, setSourceType] = React.useState(data.source_type || "");
    const result = data.rag_result;
    function search() {
      const value = query.trim();
      if (!value) {
        message.warning("请输入报销问题");
        return;
      }
      const params = new URLSearchParams({ q: value });
      if (sourceType) params.set("source_type", sourceType);
      window.location.href = "/?" + params.toString() + "#knowledge";
    }
    return e(
      Card,
      { className: "work-card rag-card", title: "问财务处资料库" },
      e(
        Space,
        { direction: "vertical", size: 14, className: "full" },
        e(Input.TextArea, {
          value: query,
          rows: 3,
          onChange: (event) => setQuery(event.target.value),
          onPressEnter: (event) => {
            if ((event.metaKey || event.ctrlKey) && query.trim()) search();
          },
          placeholder: "例如：版面费报销需要哪些材料",
        }),
        e(
          Space,
          { wrap: true },
          e(Select, {
            value: sourceType,
            style: { width: 180 },
            onChange: setSourceType,
            options: [
              { value: "", label: "全部来源" },
              { value: "page", label: "财务处网页" },
              { value: "attachment", label: "附件入口" },
              { value: "local_pdf", label: "本地 PDF" },
            ],
          }),
          e(Button, { type: "primary", onClick: search }, "查依据")
        ),
        result
          ? e(Alert, {
              type: result.hits && result.hits.length ? "success" : "warning",
              showIcon: true,
              message: "检索式答复",
              description: result.answer,
            })
          : e(Alert, {
              type: "info",
              showIcon: true,
              message: "可追溯回答",
              description: "输入问题后返回财务处网页或本地 PDF 来源，不替代财务处最终口径。",
            }),
        result && result.hits && result.hits.length
          ? e(List, {
              className: "source-list-ant",
              itemLayout: "vertical",
              dataSource: result.hits,
              renderItem: (hit) =>
                e(
                  List.Item,
                  {
                    key: hit.rank,
                    extra: e(Tag, { color: hit.source_type === "local_pdf" ? "purple" : "blue" }, hit.source_type),
                  },
                  e(List.Item.Meta, {
                    title: e("a", { href: hit.url, target: "_blank", rel: "noreferrer" }, `${hit.rank}. ${hit.title}`),
                    description: hit.published_date ? `日期 ${hit.published_date} · 分数 ${hit.score}` : `分数 ${hit.score}`,
                  }),
                  e(Paragraph, { ellipsis: { rows: 4, expandable: true, symbol: "展开" } }, hit.snippet)
                ),
            })
          : null
      )
    );
  }

  function PackageList({ title, packages, emptyDescription }) {
    return e(
      Card,
      { className: "work-card", title },
      packages.length
        ? e(List, {
            itemLayout: "horizontal",
            dataSource: packages,
            renderItem: (pkg) =>
              e(
                List.Item,
                {
                  actions: [e("a", { key: "view", href: `/packages/${encodeURIComponent(pkg.id)}/view` }, "查看")],
                },
                e(List.Item.Meta, {
                  title: e(
                    Space,
                    { size: 8, wrap: true },
                    e("a", { href: `/packages/${encodeURIComponent(pkg.id)}/view` }, pkg.title),
                    e(Tag, { color: typeColor(pkg.reimbursement_type) }, pkg.reimbursement_type_name),
                    statusSummary(pkg)
                  ),
                  description: `${(pkg.documents || []).length} 份材料 · 推荐入口：${pkg.school_form_hint || "待识别"}`,
                })
              ),
          })
        : e(Empty, { image: Empty.PRESENTED_IMAGE_SIMPLE, description: emptyDescription })
    );
  }

  function InboxList() {
    return e(
      Card,
      { className: "work-card", title: "未处理随手记" },
      inboxItems.length
        ? e(List, {
            itemLayout: "vertical",
            dataSource: inboxItems,
            renderItem: (item) =>
              e(
                List.Item,
                {
                  actions: [
                    e(
                      "form",
                      { key: "package", action: `/inbox-items/${encodeURIComponent(item.id)}/package`, method: "post" },
                      e(Button, { htmlType: "submit", type: "primary" }, "生成报销包")
                    ),
                  ],
                },
                e(List.Item.Meta, {
                  title: e(
                    Space,
                    { size: 8, wrap: true },
                    e(Text, { strong: true }, item.title || "未命名随手记"),
                    e(Tag, { color: "default" }, item.source === "chat" ? "聊天备注" : item.source),
                    e(Tag, { color: "red" }, "未归类")
                  ),
                  description: item.created_at,
                }),
                e(Paragraph, { ellipsis: { rows: 3, expandable: true, symbol: "展开" } }, item.note)
              ),
          })
        : e(Empty, { image: Empty.PRESENTED_IMAGE_SIMPLE, description: "当前没有未处理随手记。" })
    );
  }

  function HomeView() {
    return e(HomeAssistantChat);
  }

  function KnowledgeView() {
    const [kbStatus, setKbStatus] = React.useState(null);
    React.useEffect(() => {
      let mounted = true;
      fetch("/api/knowledge/status")
        .then((response) => response.json())
        .then((payload) => {
          if (mounted) setKbStatus(payload);
        })
        .catch(() => {
          if (mounted) setKbStatus({ index_exists: false, source_types: {}, manifest: {} });
        });
      return () => {
        mounted = false;
      };
    }, []);
    const supported = [
      "差旅费",
      "版面费",
      "办公用品费",
      "材料费",
      "测试化验加工费",
      "公务接待费",
      "信息服务费",
    ];
    return e(
      React.Fragment,
      null,
      e("div", { className: "page-head" }, e("div", null, e(Title, { level: 2 }, "报销知识库"), e(Text, { type: "secondary" }, "基于财务处公开网页和本地指南检索，回答必须能追溯来源。"))),
      kbStatus
        ? e(
            Row,
            { gutter: [16, 16], className: "metric-row" },
            e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "索引片段", value: kbStatus.chunk_count || 0, suffix: "条" }))),
            e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "财务处网页", value: (kbStatus.source_types || {}).page || 0, suffix: "条" }))),
            e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "附件入口", value: (kbStatus.source_types || {}).attachment || 0, suffix: "条" }))),
            e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "本地 PDF", value: (kbStatus.source_types || {}).local_pdf || 0, suffix: "条" })))
          )
        : null,
      e(RagPanel),
      e(
        Card,
        { className: "work-card", title: "当前支持的报销类别" },
        e(
          Space,
          { direction: "vertical", className: "full", size: 10 },
          e(Space, { wrap: true }, supported.map((item) => e(Tag, { key: item, color: "blue" }, item))),
          kbStatus && kbStatus.manifest
            ? e(
                Text,
                { type: "secondary" },
                kbStatus.manifest.created_at
                  ? `最近抓取：${kbStatus.manifest.created_at} · 页面 ${kbStatus.manifest.page_count || 0} · 附件 ${kbStatus.manifest.attachment_count || 0}`
                  : "未找到抓取清单"
              )
            : null
        )
      )
    );
  }

  function CollectionView() {
    const collecting = allPackages.filter(needsMaterials);
    return e(
      React.Fragment,
      null,
      e("div", { className: "page-head" }, e("div", null, e(Title, { level: 2 }, "资料归集"), e(Text, { type: "secondary" }, "先把发票、附件、邮件和随口备注收齐，再决定是否进入学校系统。"))),
      e(
        Row,
        { gutter: [16, 16], align: "top" },
        e(Col, { xs: 24, lg: 12 }, e(QuickNoteInbox)),
        e(Col, { xs: 24, lg: 12 }, e(UploadWorkbench))
      ),
      e(InboxList),
      e(PackageList, {
        title: "待补材料",
        packages: collecting,
        emptyDescription: "当前没有检测到缺必需材料的报销包。",
      })
    );
  }

  function WaitingView() {
    return e(
      React.Fragment,
      null,
      e("div", { className: "page-head" }, e("div", null, e(Title, { level: 2 }, "等待报销"), e(Text, { type: "secondary" }, "这里展示还没有被标记为已报销的本地报销包，提交动作必须由本人确认。"))),
      e(PackageList, {
        title: "等待处理",
        packages: waitingPackages(allPackages),
        emptyDescription: "当前没有等待报销的事项。",
      })
    );
  }

  function ReimbursedView() {
    return e(
      React.Fragment,
      null,
      e("div", { className: "page-head" }, e("div", null, e(Title, { level: 2 }, "已报销"), e(Text, { type: "secondary" }, "只展示明确标记为已报销或已完成的事项，不把材料齐全自动当作已报销。"))),
      e(PackageList, {
        title: "已完成事项",
        packages: reimbursedPackages(allPackages),
        emptyDescription: "目前没有已标记完成的报销事项。",
      })
    );
  }

  function SettingsView() {
    const [status, setStatus] = React.useState(null);
    const [error, setError] = React.useState("");
    React.useEffect(() => {
      let mounted = true;
      fetch("/api/settings/status")
        .then((response) => response.json())
        .then((payload) => {
          if (mounted) setStatus(payload);
        })
        .catch(() => {
          if (mounted) setError("读取本地配置状态失败");
        });
      return () => {
        mounted = false;
      };
    }, []);

    function stateTag(ok, readyText, pendingText) {
      return e(Tag, { color: ok ? "green" : "gold" }, ok ? readyText : pendingText);
    }

    function ConfigRow({ title, description, ok, readyText, pendingText, extra }) {
      return e(
        "div",
        { className: "settings-row" },
        e(
          "div",
          null,
          e(Text, { strong: true }, title),
          e(Paragraph, { type: "secondary", className: "settings-desc" }, description)
        ),
        e(
          Space,
          { wrap: true },
          stateTag(ok, readyText, pendingText),
          extra ? e(Text, { type: "secondary" }, extra) : null
        )
      );
    }

    const doubao = status && status.doubao;
    const imap = status && status.imap;
    const kb = status && status.knowledge_base;
    const playwright = status && status.playwright;
    return e(
      React.Fragment,
      null,
      e("div", { className: "page-head" }, e("div", null, e(Title, { level: 2 }, "设置"), e(Text, { type: "secondary" }, "本地服务只展示配置说明，不把邮箱或大模型密钥暴露到前端页面。"))),
      e(
        Card,
        { className: "work-card", title: "接入状态" },
        e(
          Space,
          { direction: "vertical", size: 0, className: "full" },
          error ? e(Alert, { type: "error", showIcon: true, message: error }) : null,
          !status ? e(Alert, { type: "info", showIcon: true, message: "正在读取本地配置状态" }) : null,
          status
            ? e(
                React.Fragment,
                null,
                e(ConfigRow, {
                  title: "Doubao 票据识别",
                  description: "用于补充本地规则没有识别出的金额、抬头、发票号、日期和支付信息。",
                  ok: doubao.enabled && doubao.has_model,
                  readyText: "已启用",
                  pendingText: doubao.has_api_key ? "缺模型或未启用" : "未配置",
                  extra: doubao.model ? `模型 ${doubao.model}` : "密钥不会显示在前端",
                }),
                e(ConfigRow, {
                  title: "邮箱归集",
                  description: "通过 IMAP 拉取发票邮件和附件，去重后生成本地报销包。",
                  ok: imap.configured,
                  readyText: "已配置",
                  pendingText: "未配置完整",
                  extra: `邮箱目录 ${imap.mailbox}`,
                }),
                e(ConfigRow, {
                  title: "报销知识库",
                  description: "基于财务处公开网页和本地 PDF 的 BM25 检索索引。",
                  ok: kb.index_exists && kb.documents_exists,
                  readyText: "索引可用",
                  pendingText: "索引缺失",
                  extra: kb.index_exists ? `${Math.round(kb.index_size_bytes / 1024 / 1024)} MB` : "",
                }),
                e(ConfigRow, {
                  title: "上海大学财务系统适配器",
                  description: "真实系统适配器必须由老师本人登录后补充页面选择器，不能绕过验证码或二次认证。",
                  ok: playwright.shu_adapter_configured,
                  readyText: "真实适配已配置",
                  pendingText: playwright.shu_adapter_exists ? "模板待配置" : "模板缺失",
                  extra: playwright.mock_adapter_exists ? "本地 mock 可用" : "本地 mock 缺失",
                })
              )
            : null
        )
      )
    );
  }

  function Workspace() {
    const [activeKey, setActiveKey] = React.useState(normalizeKey(window.location.hash));
    React.useEffect(() => {
      function onHashChange() {
        setActiveKey(normalizeKey(window.location.hash));
      }
      window.addEventListener("hashchange", onHashChange);
      return () => window.removeEventListener("hashchange", onHashChange);
    }, []);

    function selectKey(key) {
      const next = normalizeKey(key);
      setActiveKey(next);
      if (window.location.hash !== "#" + next) {
        window.location.hash = next;
      }
    }

    const views = {
      home: e(HomeView),
      knowledge: e(KnowledgeView),
      collection: e(CollectionView),
      waiting: e(WaitingView),
      reimbursed: e(ReimbursedView),
      settings: e(SettingsView),
    };

    return e(
      ConfigProvider,
      {
        theme: {
          algorithm: theme.defaultAlgorithm,
          token: {
            colorPrimary: "#1677ff",
            borderRadius: 0,
            borderRadiusLG: 0,
            borderRadiusSM: 0,
            borderRadiusXS: 0,
            fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif",
          },
        },
      },
      e(
        App,
        null,
        e(
          Layout,
          { className: "antd-shell app-frame" },
          e(Sidebar, { activeKey, onSelect: selectKey }),
          e(Layout, { className: "main-layout" }, e(Content, { className: "antd-content" }, views[activeKey] || views.home))
        )
      )
    );
  }

  ReactDOM.createRoot(document.getElementById("root")).render(e(Workspace));
})();
