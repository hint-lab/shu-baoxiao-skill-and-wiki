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
  const Dragger = Upload.Dragger;
  const { Content, Sider } = Layout;
  const { Title, Text, Paragraph } = Typography;
  const NAV_KEYS = ["home", "knowledge", "collection", "waiting", "reimbursed", "settings"];

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

  function Sidebar({ activeKey, onSelect }) {
    const pending = waitingPackages(allPackages).length;
    const collecting = allPackages.filter(needsMaterials).length;
    const finished = reimbursedPackages(allPackages).length;
    const items = [
      { key: "home", label: "主页" },
      { key: "knowledge", label: "报销知识库" },
      { key: "waiting", label: menuLabel("等待报销", pending) },
      { key: "collection", label: menuLabel("资料归集", collecting) },
      { key: "reimbursed", label: menuLabel("已报销", finished) },
      { key: "settings", label: "设置" },
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

  function RagPanel() {
    const [query, setQuery] = React.useState(data.q || "");
    const result = data.rag_result;
    function search() {
      const value = query.trim();
      if (!value) {
        message.warning("请输入报销问题");
        return;
      }
      window.location.href = "/?q=" + encodeURIComponent(value) + "#knowledge";
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
        e(Button, { type: "primary", onClick: search }, "查依据"),
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

  function HomeView() {
    const packages = allPackages;
    const pending = waitingPackages(packages);
    const missingPackages = packages.filter(needsMaterials);
    const finished = reimbursedPackages(packages);
    return e(
      React.Fragment,
      null,
      e(
        "div",
        { className: "page-head" },
        e(
          "div",
          null,
          e(Title, { level: 2 }, "上海大学报销工作台"),
          e(Text, { type: "secondary" }, "收票、整理、问依据、生成报销包，进入上海大学财务系统前先把材料理清。")
        ),
        e(Button, { href: "/package-output" }, "报销包文件")
      ),
      e(
        Row,
        { gutter: [16, 16], className: "metric-row" },
        e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "本地报销包", value: packages.length, suffix: "个" }))),
        e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "等待报销", value: pending.length, suffix: "个" }))),
        e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "待补材料", value: missingPackages.length, suffix: "个" }))),
        e(Col, { xs: 24, md: 6 }, e(Card, null, e(Statistic, { title: "已标记报销", value: finished.length, suffix: "个" })))
      ),
      e(
        Row,
        { gutter: [16, 16], align: "top" },
        e(Col, { xs: 24, lg: 13 }, e(UploadWorkbench)),
        e(Col, { xs: 24, lg: 11 }, e(RagPanel))
      ),
      e(PackageList, {
        title: "最近报销包",
        packages: packages.slice(0, 8),
        emptyDescription: "还没有本地报销包。先上传发票、邮件或审批材料生成第一个。",
      })
    );
  }

  function KnowledgeView() {
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
      e(RagPanel),
      e(
        Card,
        { className: "work-card", title: "当前支持的报销类别" },
        e(Space, { wrap: true }, supported.map((item) => e(Tag, { key: item, color: "blue" }, item)))
      )
    );
  }

  function CollectionView() {
    const collecting = allPackages.filter(needsMaterials);
    return e(
      React.Fragment,
      null,
      e("div", { className: "page-head" }, e("div", null, e(Title, { level: 2 }, "资料归集"), e(Text, { type: "secondary" }, "先把发票、附件、邮件和随口备注收齐，再决定是否进入学校系统。"))),
      e(UploadWorkbench),
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
    return e(
      React.Fragment,
      null,
      e("div", { className: "page-head" }, e("div", null, e(Title, { level: 2 }, "设置"), e(Text, { type: "secondary" }, "本地服务只展示配置说明，不把邮箱或大模型密钥暴露到前端页面。"))),
      e(
        Card,
        { className: "work-card", title: "可接入能力" },
        e(
          Space,
          { direction: "vertical", size: 10, className: "full" },
          e(Alert, { type: "info", showIcon: true, message: "Doubao 识别", description: "后端通过 DOUBAO_EXTRACT_ENABLED 和 DOUBAO_API_KEY 控制，可用于发票金额、抬头、明细字段识别。" }),
          e(Alert, { type: "info", showIcon: true, message: "邮箱归集", description: "后端通过 IMAP 配置接收发票邮件，整理附件后生成本地报销包。" }),
          e(Alert, { type: "warning", showIcon: true, message: "学校系统代填", description: "Playwright 只负责辅助录入，最终提交、经费项目和账号仍必须由本人确认。" })
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
