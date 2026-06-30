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
    Tabs,
    Tag,
    Typography,
    Upload,
    message,
    theme,
  } = antd;

  const data = window.__REIMBURSEMENT_DATA__ || {};
  const allPackages = data.packages || data.recent || [];
  const inboxItems = data.inbox_items || [];
  const materialItems = data.material_items || [];
  const Dragger = Upload.Dragger;
  const { Content, Sider } = Layout;
  const { Title, Text, Paragraph } = Typography;
  const Icons = window.icons || window.AntDesignIcons || {};
  const {
    CheckCircleOutlined,
    ClockCircleOutlined,
    DatabaseOutlined,
    DeleteOutlined,
    FileAddOutlined,
    FolderOpenOutlined,
    HomeOutlined,
    InboxOutlined,
    MessageOutlined,
    PaperClipOutlined,
    SearchOutlined,
    SendOutlined,
    SettingOutlined,
    SyncOutlined,
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
      returned: ["orange", "已退回"],
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

  function waitingGroupOf(pkg) {
    if (pkg.has_return_diagnosis) return "returned";
    const status = packageStatus(pkg);
    if (status === "returned") return "returned";
    if (status === "ready_for_school") return "ready_for_school";
    if (status === "ready_for_review") return "ready_for_review";
    if (status === "submitted_by_user") return "submitted";
    if (needsMaterials(pkg)) return "needs_materials";
    return "ready_for_review";
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
    const collecting = allPackages.filter(needsMaterials).length + inboxItems.length + materialItems.length;
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
        e("img", { src: "/logo.png", alt: "上海大学财务助手" }),
        e("span", null, e("strong", null, "上海大学"), e("small", null, "自助报销 Agent"))
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
      { className: "work-card", title: "直接生成报销包" },
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
        e(Text, { type: "secondary" }, "把问题、发票、邮件和附件丢进来，我先整理好，最后由本人确认。")
      ),
      e(
        Card,
        { className: "home-chat-card", bordered: false },
        e(
          Form,
          { form, layout: "vertical", onFinish: submit, className: "chat-form" },
          e(Form.Item, { name: "title", className: "chat-title-item" }, e(Input, { className: "chat-title-input", placeholder: "事项名称，可不填" })),
          e(
            Form.Item,
            { name: "note", className: "chat-note-item" },
            e(Input.TextArea, {
              autoSize: { minRows: 6, maxRows: 10 },
              placeholder: "问：版面费报销需要哪些材料？\n记：6 月北京人工智能会议，报销高铁、酒店和会务费，走张老师科研项目。",
            })
          ),
          fileList.length
            ? e(
                "div",
                { className: "chat-file-strip" },
                fileList.slice(0, 4).map((file) =>
                  e(
                    Tag,
                    { key: file.uid || file.name, icon: icon(PaperClipOutlined) },
                    file.name
                  )
                ),
                fileList.length > 4 ? e(Tag, null, `+${fileList.length - 4}`) : null
              )
            : null,
          e(
            "div",
            { className: "chat-toolbar" },
            e(
              Space,
              { wrap: true, size: 8 },
              e(
                Upload,
                {
                  multiple: true,
                  beforeUpload: () => false,
                  fileList,
                  showUploadList: false,
                  onChange: ({ fileList: next }) => setFileList(next),
                },
                e(Button, { icon: icon(PaperClipOutlined) || icon(FileAddOutlined) }, "附件")
              ),
              e(Button, { href: "/#knowledge", icon: icon(SearchOutlined) }, "知识库"),
              fileList.length
                ? e(Button, { danger: true, icon: icon(DeleteOutlined), onClick: () => setFileList([]) }, "清空")
                : null
            ),
            e(
              Button,
              {
                type: "primary",
                htmlType: "submit",
                loading: submitting,
                icon: icon(shouldAskPolicy ? SearchOutlined : fileList.length ? InboxOutlined : SendOutlined),
              },
              shouldAskPolicy ? "查询依据" : fileList.length ? "生成报销包" : "发送"
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

  function MaterialStashForm() {
    const [form] = Form.useForm();
    const [fileList, setFileList] = React.useState([]);
    const [submitting, setSubmitting] = React.useState(false);
    async function submit(values) {
      if (!fileList.length) {
        message.warning("请先选择要暂存的材料");
        return;
      }
      const body = new FormData();
      body.append("title", values.title || "");
      body.append("note", values.note || "");
      fileList.forEach((file) => body.append("files", file.originFileObj || file));
      setSubmitting(true);
      try {
        await fetch("/materials", { method: "POST", body, redirect: "follow" });
        reloadCollection();
      } catch (error) {
        message.error("暂存材料失败");
        setSubmitting(false);
      }
    }
    return e(
      Card,
      { className: "work-card", title: "暂存未归类材料" },
      e(
        Form,
        { form, layout: "vertical", onFinish: submit },
        e(Form.Item, { label: "材料组名称", name: "title" }, e(Input, { placeholder: "例如：李老师差旅票据一组" })),
        e(Form.Item, { label: "线索备注", name: "note" }, e(Input.TextArea, { rows: 3, placeholder: "例如：这些票据可能是 6 月北京会议，后面再补会议通知。" })),
        e(
          Form.Item,
          { label: "原始材料" },
          e(
            Dragger,
            {
              multiple: true,
              beforeUpload: () => false,
              fileList,
              onChange: ({ fileList: next }) => setFileList(next),
            },
            e("p", { className: "upload-symbol" }, "↑"),
            e("p", { className: "ant-upload-text" }, "先放进资料归集，不立刻生成报销包"),
            e("p", { className: "ant-upload-hint" }, "系统会保存原始文件、大小和 hash，后续再由你决定是否生成报销包。")
          )
        ),
        e(Button, { type: "primary", htmlType: "submit", loading: submitting }, "暂存到资料归集")
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
                    description: [
                      hit.published_date ? `日期 ${hit.published_date}` : "",
                      `综合 ${hit.score}`,
                      hit.bm25_score !== undefined ? `BM25 ${hit.bm25_score}` : "",
                      hit.keyword_score !== undefined ? `关键词 ${hit.keyword_score}` : "",
                    ]
                      .filter(Boolean)
                      .join(" · "),
                  }),
                  hit.matched_keywords && hit.matched_keywords.length
                    ? e(
                        Space,
                        { wrap: true, size: [4, 4], className: "hit-keywords" },
                        hit.matched_keywords.slice(0, 8).map((keyword) => e(Tag, { key: keyword }, keyword))
                      )
                    : null,
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
                    pkg.has_return_diagnosis ? e(Tag, { color: "orange" }, "有退回诊断") : null,
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

  function MaterialPoolList() {
    return e(
      Card,
      { className: "work-card", title: "未归类材料池" },
      materialItems.length
        ? e(List, {
            itemLayout: "vertical",
            dataSource: materialItems,
            renderItem: (item) =>
              e(
                List.Item,
                {
                  actions: [
                    e(
                      "form",
                      { key: "package", action: `/materials/${encodeURIComponent(item.id)}/package`, method: "post" },
                      e(Button, { htmlType: "submit", type: "primary" }, "生成报销包")
                    ),
                  ],
                },
                e(List.Item.Meta, {
                  title: e(
                    Space,
                    { size: 8, wrap: true },
                    e(Text, { strong: true }, item.title || "未命名材料组"),
                    e(Tag, { color: "default" }, item.source === "upload" ? "网页上传" : item.source),
                    e(Tag, { color: "red" }, "未归类"),
                    e(Tag, { color: "blue" }, `${item.file_count || 0} 份材料`)
                  ),
                  description: item.created_at,
                }),
                item.note ? e(Paragraph, { ellipsis: { rows: 2, expandable: true, symbol: "展开" } }, item.note) : null,
                e(
                  Space,
                  { wrap: true, size: [4, 6] },
                  (item.files || []).slice(0, 4).map((file) =>
                    e(Tag, { key: file.sha256 || file.file_name }, `${file.file_name} · ${Math.round((file.size || 0) / 1024)}KB`)
                  ),
                  (item.files || []).length > 4 ? e(Tag, null, `+${(item.files || []).length - 4}`) : null
                )
              ),
          })
        : e(Empty, { image: Empty.PRESENTED_IMAGE_SIMPLE, description: "当前没有暂存的未归类材料。" })
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
    const report = (kbStatus && kbStatus.corpus_report) || {};
    const emptyBySource = report.empty_text_by_source_type || {};
    return e(
      React.Fragment,
      null,
      e("div", { className: "page-head" }, e("div", null, e(Title, { level: 2 }, "报销知识库"), e(Text, { type: "secondary" }, "基于财务处公开网页和本地指南检索，回答必须能追溯来源。"))),
      kbStatus
        ? e(
            Row,
            { gutter: [16, 16], className: "metric-row" },
            e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "索引片段", value: kbStatus.chunk_count || 0, suffix: "条" }))),
            e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "已索引文档", value: report.indexed_document_count || 0, suffix: "份" }))),
            e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "文档总量", value: report.document_count || 0, suffix: "份" }))),
            e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "空文本附件", value: emptyBySource.attachment || 0, suffix: "个" })))
          )
        : null,
      report.warnings && report.warnings.length
        ? e(
            Alert,
            {
              className: "page-alert",
              type: "warning",
              showIcon: true,
              message: "入库校验提示",
              description: report.warnings.join("；"),
            }
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
          ,
          report.indexed_source_types
            ? e(
                Text,
                { type: "secondary" },
                `已索引来源：网页 ${(report.indexed_source_types || {}).page || 0} · 附件 ${(report.indexed_source_types || {}).attachment || 0} · 本地 PDF ${(report.indexed_source_types || {}).local_pdf || 0}`
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
        e(Col, { xs: 24, xl: 8 }, e(QuickNoteInbox)),
        e(Col, { xs: 24, xl: 8 }, e(MaterialStashForm)),
        e(Col, { xs: 24, xl: 8 }, e(UploadWorkbench))
      ),
      e(InboxList),
      e(MaterialPoolList),
      e(PackageList, {
        title: "待补材料",
        packages: collecting,
        emptyDescription: "当前没有检测到缺必需材料的报销包。",
      })
    );
  }

  function WaitingView() {
    const waiting = waitingPackages(allPackages);
    const groups = {
      needs_materials: waiting.filter((pkg) => waitingGroupOf(pkg) === "needs_materials"),
      ready_for_review: waiting.filter((pkg) => waitingGroupOf(pkg) === "ready_for_review"),
      ready_for_school: waiting.filter((pkg) => waitingGroupOf(pkg) === "ready_for_school"),
      submitted: waiting.filter((pkg) => waitingGroupOf(pkg) === "submitted"),
      returned: waiting.filter((pkg) => waitingGroupOf(pkg) === "returned"),
    };
    const items = [
      {
        key: "needs_materials",
        label: `缺材料 ${groups.needs_materials.length}`,
        children: e(PackageList, {
          title: "缺材料",
          packages: groups.needs_materials,
          emptyDescription: "当前没有缺必需材料的报销包。",
        }),
      },
      {
        key: "ready_for_review",
        label: `等待复核 ${groups.ready_for_review.length}`,
        children: e(PackageList, {
          title: "等待本人复核",
          packages: groups.ready_for_review,
          emptyDescription: "当前没有等待复核的报销包。",
        }),
      },
      {
        key: "ready_for_school",
        label: `可代填 ${groups.ready_for_school.length}`,
        children: e(PackageList, {
          title: "可进入上海大学财务系统",
          packages: groups.ready_for_school,
          emptyDescription: "当前没有已确认可代填的报销包。",
        }),
      },
      {
        key: "submitted",
        label: `已提交 ${groups.submitted.length}`,
        children: e(PackageList, {
          title: "已提交待回写",
          packages: groups.submitted,
          emptyDescription: "当前没有已提交但未标记报销的事项。",
        }),
      },
      {
        key: "returned",
        label: `退回待处理 ${groups.returned.length}`,
        children: e(PackageList, {
          title: "退回待处理",
          packages: groups.returned,
          emptyDescription: "当前没有带退回诊断的报销包。",
        }),
      },
    ];
    return e(
      React.Fragment,
      null,
      e("div", { className: "page-head" }, e("div", null, e(Title, { level: 2 }, "等待报销"), e(Text, { type: "secondary" }, "按真实状态分组：缺材料、等待复核、可代填、已提交和退回待处理。提交动作必须由本人确认。"))),
      waiting.length
        ? e(Tabs, { className: "work-tabs", defaultActiveKey: "needs_materials", items })
        : e(Card, { className: "work-card" }, e(Empty, { image: Empty.PRESENTED_IMAGE_SIMPLE, description: "当前没有等待报销的事项。" }))
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
    const [mailPolling, setMailPolling] = React.useState(false);
    const [mailPollResult, setMailPollResult] = React.useState(null);

    function refreshStatus(shouldUpdate = () => true) {
      fetch("/api/settings/status")
        .then((response) => response.json())
        .then((payload) => {
          if (shouldUpdate()) setStatus(payload);
        })
        .catch(() => {
          if (shouldUpdate()) setError("读取本地配置状态失败");
        });
    }

    React.useEffect(() => {
      let mounted = true;
      refreshStatus(() => mounted);
      return () => {
        mounted = false;
      };
    }, []);

    async function pollMailbox() {
      setMailPolling(true);
      setMailPollResult(null);
      try {
        const body = new FormData();
        body.append("limit", "10");
        const response = await fetch("/api/mail/poll", { method: "POST", body });
        const payload = await response.json();
        setMailPollResult(payload);
        if (!response.ok || !payload.ok) {
          message.error(payload.error || "拉取邮箱失败");
          return;
        }
        if (payload.count > 0) {
          message.success(`已整理 ${payload.count} 封邮件`);
        } else {
          message.info("没有新的未读发票邮件");
        }
        refreshStatus(() => true);
      } catch (mailError) {
        setMailPollResult({ ok: false, error: "拉取邮箱失败，请检查本地服务状态。" });
        message.error("拉取邮箱失败");
      } finally {
        setMailPolling(false);
      }
    }

    function stateTag(ok, readyText, pendingText) {
      return e(Tag, { color: ok ? "green" : "gold" }, ok ? readyText : pendingText);
    }

    function ConfigRow({ title, description, ok, readyText, pendingText, extra, action }) {
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
          extra ? e(Text, { type: "secondary" }, extra) : null,
          action || null
        )
      );
    }

    const doubao = status && status.doubao;
    const imap = status && status.imap;
    const kb = status && status.knowledge_base;
    const playwright = status && status.playwright;
    const shuAuth = status && status.shu_auth;
    function authStatusLabel(auth) {
      if (!auth || !auth.profile_exists) return ["gold", "未建立"];
      if (auth.status === "ready") return ["green", "会话可用"];
      if (auth.status === "needs_scan") return ["orange", "需要扫码"];
      if (auth.status === "needs_renew") return ["gold", "需要续登"];
      if (auth.status === "error") return ["red", "检查失败"];
      return ["blue", "待检测"];
    }
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
                  extra: `邮箱目录 ${imap.mailbox} · 已处理 ${imap.processed_count || 0} 封`,
                  action: e(
                    Button,
                    {
                      icon: icon(SyncOutlined),
                      loading: mailPolling,
                      disabled: !imap.configured,
                      onClick: pollMailbox,
                    },
                    "立即拉取邮箱"
                  ),
                }),
                mailPollResult
                  ? e(Alert, {
                      className: "settings-inline-alert",
                      type: mailPollResult.ok ? "success" : "warning",
                      showIcon: true,
                      message: mailPollResult.ok ? `邮箱拉取完成：${mailPollResult.count || 0} 封新邮件` : "邮箱拉取未完成",
                      description: mailPollResult.ok
                        ? (mailPollResult.count || 0) > 0
                          ? e(
                              Space,
                              { direction: "vertical", className: "full", size: 6 },
                              e(Text, null, "新邮件已整理为本地报销包。"),
                              e(Button, { href: "/?refresh=" + Date.now() + "#waiting", type: "primary" }, "查看等待报销")
                            )
                          : "没有新的未读发票邮件，历史邮件不会重复生成报销包。"
                        : mailPollResult.error || "请检查本机 IMAP 配置。",
                    })
                  : null,
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
                }),
                shuAuth
                  ? e(
                      "div",
                      { className: "settings-row" },
                      e(
                        "div",
                        null,
                        e(Text, { strong: true }, "上海大学扫码登录保持"),
                        e(
                          Paragraph,
                          { type: "secondary", className: "settings-desc" },
                          "使用本机专用浏览器 profile 保存 newsso 和财务系统登录态。过期后通过 ShuAuth 续登，统一认证也过期时再由本人扫码。"
                        ),
                        e(
                          Paragraph,
                          { className: "settings-desc" },
                          e("code", null, "python3 tools/shu_auth_session.py login")
                        )
                      ),
                      e(
                        Space,
                        { wrap: true },
                        (() => {
                          const label = authStatusLabel(shuAuth);
                          return e(Tag, { color: label[0] }, label[1]);
                        })(),
                        e(Text, { type: "secondary" }, shuAuth.checked_at ? `上次检测 ${shuAuth.checked_at}` : "尚未检测"),
                        e(Text, { type: "secondary" }, shuAuth.profile_exists ? "本机 profile 已存在" : "本机 profile 未建立")
                      )
                    )
                  : null,
                shuAuth && shuAuth.message
                  ? e(Alert, {
                      className: "settings-inline-alert",
                      type: shuAuth.status === "ready" ? "success" : "info",
                      showIcon: true,
                      message: "扫码登录保持状态",
                      description: shuAuth.message,
                    })
                  : null,
                shuAuth && shuAuth.url
                  ? e(Paragraph, { type: "secondary", className: "settings-desc" }, `最近页面：${shuAuth.url}`)
                  : null
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
