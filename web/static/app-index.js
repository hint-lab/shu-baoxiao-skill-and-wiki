(function () {
  const e = React.createElement;
  const {
    Alert,
    App,
    Button,
    Card,
    Col,
    ConfigProvider,
    Dropdown,
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
    DownOutlined,
    FileAddOutlined,
    FolderOpenOutlined,
    HomeOutlined,
    InboxOutlined,
    LockOutlined,
    LoginOutlined,
    MessageOutlined,
    PaperClipOutlined,
    SearchOutlined,
    SendOutlined,
    SettingOutlined,
    SyncOutlined,
    UserOutlined,
  } = Icons;
  const NAV_KEYS = ["home", "knowledge", "collection", "waiting", "reimbursed", "settings", "auth"];

  function icon(IconComponent) {
    return IconComponent ? e(IconComponent) : null;
  }

  const TYPO_REPLACEMENTS = [
    ["财物处", "财务处"],
    ["财物系统", "财务系统"],
    ["报消", "报销"],
    ["抱销", "报销"],
    ["报帐", "报账"],
    ["抱账", "报账"],
    ["报章", "报账"],
    ["发飘", "发票"],
    ["发漂", "发票"],
    ["法票", "发票"],
    ["发片", "发票"],
    ["板面费", "版面费"],
    ["版免费", "版面费"],
    ["版面飞", "版面费"],
    ["差旅废", "差旅费"],
    ["差旅飞", "差旅费"],
    ["会物费", "会务费"],
    ["会义费", "会议费"],
    ["住缩", "住宿"],
    ["住宿飞", "住宿费"],
    ["高帖", "高铁"],
    ["工好", "工号"],
    ["项目好", "项目号"],
    ["扫吗", "扫码"],
    ["登路", "登录"],
    ["只识库", "知识库"],
    ["知识裤", "知识库"],
    ["邮香", "邮箱"],
    ["才料", "材料"],
    ["材聊", "材料"],
  ];
  const TYPO_TERMS = [
    "财务处",
    "财务系统",
    "报销",
    "报账",
    "发票",
    "版面费",
    "差旅费",
    "会议费",
    "会务费",
    "住宿费",
    "高铁",
    "工号",
    "项目号",
    "扫码",
    "登录",
    "知识库",
    "邮箱",
    "材料",
    "审批单",
    "支付记录",
  ];

  function shortLabel(text, max = 22) {
    return text && text.length > max ? `${text.slice(0, max)}...` : text;
  }

  function editDistance(a, b) {
    const dp = Array.from({ length: a.length + 1 }, () => Array(b.length + 1).fill(0));
    for (let i = 0; i <= a.length; i += 1) dp[i][0] = i;
    for (let j = 0; j <= b.length; j += 1) dp[0][j] = j;
    for (let i = 1; i <= a.length; i += 1) {
      for (let j = 1; j <= b.length; j += 1) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
      }
    }
    return dp[a.length][b.length];
  }

  function buildTypoCorrectionMessage(note) {
    const original = (note || "").trim();
    const compact = original.replace(/\s+/g, "");
    if (compact.length < 2) return null;
    const candidates = [];
    const seenQueries = new Set();
    const addCandidate = (query, label) => {
      const clean = (query || "").trim();
      if (!clean || clean === original || seenQueries.has(clean)) return;
      seenQueries.add(clean);
      candidates.push({ label, query: clean });
    };

    let combined = original;
    TYPO_REPLACEMENTS.forEach(([wrong, right]) => {
      if (combined.includes(wrong) && !combined.includes(right)) {
        combined = combined.split(wrong).join(right);
      }
    });
    addCandidate(combined, "按正确词问");

    TYPO_REPLACEMENTS.forEach(([wrong, right]) => {
      if (original.includes(wrong) && !original.includes(right)) {
        addCandidate(original.split(wrong).join(right), `改成「${right}」`);
      }
    });

    if (!candidates.length && compact.length <= 16) {
      TYPO_TERMS.forEach((term) => {
        if (term.length < 3) return;
        if (compact.includes(term)) return;
        const minLen = Math.max(2, term.length - 1);
        const maxLen = Math.min(compact.length, term.length + 1);
        for (let len = minLen; len <= maxLen; len += 1) {
          for (let start = 0; start <= compact.length - len; start += 1) {
            const fragment = compact.slice(start, start + len);
            const limit = term.length >= 4 ? 2 : 1;
            if (editDistance(fragment, term) <= limit) {
              addCandidate(original.replace(fragment, term), `可能是「${term}」`);
              return;
            }
          }
        }
      });
    }

    if (!candidates.length) return null;
    const actions = candidates.slice(0, 3).map((candidate, index) => ({
      type: "ask",
      primary: index === 0,
      label: `${candidate.label}：${shortLabel(candidate.query)}`,
      query: candidate.query,
    }));
    actions.push({ type: "ask", label: "仍按原文发送", query: original, skipTypoCheck: true });
    const routingText = `${original} ${candidates.map((candidate) => candidate.query).join(" ")}`;
    const settingsLike = /登录|扫码|工号|账号|账户|财务系统|财物系统|邮箱/.test(routingText);
    actions.push({
      type: "href",
      label: settingsLike ? "去设置检查" : "去知识库查",
      href: settingsLike ? "/#settings" : "/#knowledge",
    });
    return {
      role: "assistant",
      suggestionOnly: true,
      text: "是不是打错了？我猜你可能想问下面这些，也可以继续按原文发送。",
      actions,
    };
  }

  async function startShuAuthLogin() {
    const response = await fetch("/api/shu-auth/login", { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "启动扫码登录窗口失败");
    }
    return payload;
  }

  function normalizeKey(value) {
    const key = String(value || "").replace("#", "");
    if (!NAV_KEYS.includes(key)) return "home";
    return key === "auth" ? "settings" : key;
  }

  function rawHashKey() {
    return String(window.location.hash || "").replace("#", "");
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

  function reloadCollection() {
    window.location.href = "/?refresh=" + Date.now() + "#collection";
  }

  function isPolicyQuestion(text) {
    const value = String(text || "").trim();
    if (!value) return false;
    if (/[?？]/.test(value)) return true;
    if (/^(怎么|如何|为什么|哪些|什么|能否|能不能|可不可以|是否)/.test(value)) return true;
    if (/(怎么|如何).*(报销|办理|申请)|报销.*(怎么|如何)/.test(value)) return true;
    if (/需要.*(什么|哪些|材料|附件|手续)/.test(value)) return true;
    if (/(报销|发票).*(要求|规定|标准|流程|材料|附件|依据)/.test(value)) return true;
    return false;
  }

  function isMaterialCollectionNote(text) {
    const value = String(text || "").trim();
    if (!value) return false;
    if (/^(记|记一下|帮我记|先存|保存|整理|归集|待报销|我要报销|这张|这些)/.test(value)) return true;
    return /(发票|票据|报销|付款|支付|合同|会议|酒店|高铁|火车票|机票|差旅|住宿|版面费|出版费|邮费|快递费|邮寄费|材料费|测试化验|公务接待|信息服务|办公用品|耗材)/.test(value);
  }

  function Sidebar({ activeKey, onSelect, collapsed, onToggleCollapsed }) {
    const user = data.user || {};
    const items = [
      { key: "home", icon: icon(HomeOutlined), label: "报销首页" },
      { key: "knowledge", icon: icon(DatabaseOutlined), label: "报销知识" },
      { key: "waiting", icon: icon(ClockCircleOutlined), label: "待办报销" },
      { key: "collection", icon: icon(FolderOpenOutlined), label: "资料归集" },
      { key: "reimbursed", icon: icon(CheckCircleOutlined), label: "报销记录" },
    ];
    return e(
      Sider,
      { width: 224, collapsedWidth: 72, collapsed, collapsible: false, className: "app-sider" },
      e(
        "button",
        { className: "brand-block", type: "button", onClick: onToggleCollapsed, title: collapsed ? "展开侧边栏" : "收起侧边栏" },
        e("img", { src: "/logo.png", alt: "上海大学财务助手" }),
        e("span", null, e("strong", null, "上海大学"), e("small", null, "自助报销 Agent"))
      ),
      e(Menu, {
        className: "sidebar-main-menu",
        theme: "dark",
        mode: "inline",
        inlineCollapsed: collapsed,
        selectedKeys: activeKey === "settings" || activeKey === "auth" ? [] : [activeKey],
        items,
        onClick: ({ key }) => onSelect(key),
      }),
      e(
        "div",
        { className: "sidebar-bottom" },
        e(
          "div",
          { className: "sidebar-user", title: collapsed ? user.display_name || "未绑定工号" : undefined },
          e("div", { className: "sidebar-user-avatar" }, String(user.display_name || "未").slice(0, 1).toUpperCase()),
          e(
            "div",
            { className: "sidebar-user-meta" },
            e("strong", null, user.display_name || "未绑定工号"),
            e("span", null, user.subtitle || "本机模式")
          )
        ),
        e(Menu, {
          className: "sidebar-settings-menu",
          theme: "dark",
          mode: "inline",
          inlineCollapsed: collapsed,
          selectedKeys: activeKey === "settings" ? ["settings"] : [],
          items: [{ key: "settings", icon: icon(SettingOutlined), label: "系统设置" }],
          onClick: ({ key }) => onSelect(key),
        })
      )
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
        e(Form.Item, { label: "报销事项名称", name: "title" }, e(Input, { placeholder: "请输入这次报销事项的名称" })),
        e(
          Form.Item,
          { label: "一句话备注", name: "note" },
          e(Input.TextArea, {
            rows: 4,
            placeholder: "请描述业务事实、费用类型、发生时间、附件情况和经费项目",
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
    const [chatActive, setChatActive] = React.useState(false);
    const [messages, setMessages] = React.useState([]);
    const noteValue = Form.useWatch("note", form) || "";
    const user = data.user || {};

    function fileToUploadItem(file, source) {
      const extension = file.type === "image/png" ? "png" : file.type === "image/jpeg" ? "jpg" : "bin";
      const name = file.name || `${source || "clipboard"}-${Date.now()}.${extension}`;
      return {
        uid: `${source || "file"}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        name,
        status: "done",
        originFileObj: file,
      };
    }

    function addFilesToChat(files, source) {
      const nextFiles = Array.from(files || []).filter((file) => file && file.size > 0);
      if (!nextFiles.length) return false;
      activateChat();
      setFileList((current) => [...current, ...nextFiles.map((file) => fileToUploadItem(file, source))]);
      message.success(`已添加 ${nextFiles.length} 个附件`);
      return true;
    }

    function handlePaste(event) {
      const clipboard = event.clipboardData;
      if (!clipboard) return;
      const files = clipboard.files && clipboard.files.length ? Array.from(clipboard.files) : [];
      const itemFiles = Array.from(clipboard.items || [])
        .filter((item) => item.kind === "file")
        .map((item) => item.getAsFile())
        .filter(Boolean);
      const added = addFilesToChat(files.length ? files : itemFiles, "paste");
      if (added) {
        event.preventDefault();
      }
    }

    function handleDrop(event) {
      const files = event.dataTransfer && event.dataTransfer.files ? Array.from(event.dataTransfer.files) : [];
      const added = addFilesToChat(files, "drop");
      if (added) {
        event.preventDefault();
      }
    }

    function activateChat() {
      setChatActive(true);
      setMessages((current) =>
        current.length
          ? current
          : [
              {
                role: "assistant",
                text: "把报销问题、事项描述、发票或附件直接发给我。我会先判断你是要查政策、记录待报销事项，还是整理成报销包。",
              },
            ]
      );
    }

    function assistantMessageFrom(payload) {
      if (payload.action === "answer_policy") {
        const answer = payload.policy && payload.policy.answer ? payload.policy.answer : "没有检索到足够可靠的依据。";
        return {
          role: "assistant",
          text: `${payload.message || "我先查了财务处资料库。"}\n\n${answer}`,
          sources: (payload.policy && payload.policy.hits ? payload.policy.hits : []).slice(0, 5),
        };
      }
      if (payload.action === "create_package" && payload.package) {
        return {
          role: "assistant",
          text: `${payload.message || "已生成报销包。"}\n\n材料 ${payload.package.document_count || 0} 份；待补 ${payload.package.missing_count || 0} 项。`,
          link: { href: payload.package.url, label: "打开报销包" },
        };
      }
      if (payload.action === "create_inbox" && payload.item) {
        return {
          role: "assistant",
          text: payload.message || "已放进资料归集，后面补材料后再生成报销包。",
          link: { href: payload.item.url, label: "查看资料归集" },
        };
      }
      return { role: "assistant", text: payload.message || "你是想查政策依据、记录一个待报销事项，还是整理已有发票？" };
    }

    async function submit(values = {}, options = {}) {
      const currentValues = form.getFieldsValue();
      const note = (options.note || values.note || currentValues.note || noteValue || "").trim();
      const title = (values.title || currentValues.title || "").trim();
      if (!note && !fileList.length) {
        message.warning("写一句报销事项，或者上传发票和附件");
        return;
      }
      activateChat();
      const typoMessage = !options.skipTypoCheck && note ? buildTypoCorrectionMessage(note) : null;
      if (typoMessage) {
        setMessages((current) => [...current, { role: "user", text: note }, typoMessage]);
        form.setFieldsValue({ title: "", note: "" });
        return;
      }
      const body = new FormData();
      body.append("title", title);
      body.append("note", note);
      body.append(
        "history",
        JSON.stringify(
          messages
            .filter((item) => item.text && !item.suggestionOnly)
            .slice(-8)
            .map((item) => ({ role: item.role, text: item.text }))
        )
      );
      fileList.forEach((file) => body.append("files", file.originFileObj || file));
      setMessages((current) => [...current, { role: "user", text: note || `上传了 ${fileList.length} 份材料` }]);
      form.setFieldsValue({ title: "", note: "" });
      setSubmitting(true);
      try {
        const response = await fetch("/api/home/assistant", { method: "POST", body });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          message.error(payload.error || "处理失败");
          setMessages((current) => [...current, { role: "assistant", text: payload.error || "处理失败，请稍后重试。" }]);
          return;
        }
        setMessages((current) => [...current, assistantMessageFrom(payload)]);
        setFileList([]);
      } catch (error) {
        message.error("处理失败，请检查材料后重试");
        setMessages((current) => [...current, { role: "assistant", text: "处理失败，请检查本地服务、大模型配置或网络后重试。" }]);
      } finally {
        setSubmitting(false);
      }
    }

    function handleMessageAction(action) {
      if (!action) return;
      if (action.href) {
        window.location.href = action.href;
        return;
      }
      if (action.query) {
        submit({ note: action.query }, { note: action.query, skipTypoCheck: Boolean(action.skipTypoCheck) || action.type === "ask" });
      }
    }

    return e(
      "div",
      { className: `home-chat-wrap ${chatActive ? "home-chat-wrap--active" : "home-chat-wrap--welcome"}` },
      e(
        "div",
        { className: "home-chat-head" },
        e("img", { className: "assistant-mark", src: "/static/icons/chat.png", alt: "上海大学报销助手" }),
        e(
          "div",
          { className: "home-chat-title" },
          e(Title, { level: 1 }, "报销助手"),
          e(
            "div",
            { className: "home-chat-subtitle" },
            e(Text, { type: "secondary" }, "一个入口处理政策查询、材料归集和报销包生成。")
          )
        )
      ),
      e(
        Card,
        { className: "home-chat-card", bordered: false },
        e(
          Form,
          { form, layout: "vertical", onFinish: submit, className: "chat-form" },
          chatActive
            ? e(
                "div",
                { className: "chat-thread" },
                messages.map((item, index) =>
                  e(
                    "div",
                    { key: `${item.role}-${index}`, className: `chat-message chat-message--${item.role}` },
                    item.role === "assistant"
                      ? e("img", { className: "chat-message-avatar chat-message-avatar--assistant", src: "/static/icons/agent-transparent.png", alt: "报销 Agent" })
                      : e("span", { className: "chat-message-avatar chat-message-avatar--user" }, String(user.display_name || "本").slice(0, 1).toUpperCase()),
                    e(
                      "div",
                      { className: "chat-message-body" },
                      e("div", { className: "chat-message-role" }, item.role === "user" ? "你" : "报销 Agent"),
                      e(
                        "div",
                        { className: "chat-message-text" },
                        item.text,
                        item.sources && item.sources.length
                          ? e(
                              "div",
                              { className: "chat-source-list" },
                              item.sources.map((source) =>
                                e("a", { key: source.rank, href: source.url, target: "_blank", rel: "noreferrer" }, `${source.rank}. ${source.title}`)
                              )
                            )
                          : null,
                        item.link ? e(Button, { className: "chat-message-action", type: "primary", href: item.link.href }, item.link.label) : null
                        ,
                        item.actions && item.actions.length
                          ? e(
                              "div",
                              { className: "chat-suggestion-actions" },
                              item.actions.map((action, actionIndex) =>
                                e(
                                  Button,
                                  {
                                    key: `${action.label}-${actionIndex}`,
                                    size: "small",
                                    type: action.primary ? "primary" : "default",
                                    href: action.href,
                                    onClick: action.href ? undefined : () => handleMessageAction(action),
                                  },
                                  action.label
                                )
                              )
                            )
                          : null
                      )
                    )
                  )
                )
              )
            : null,
          e(
            Form.Item,
            { name: "note", className: "chat-note-item" },
            e(Input.TextArea, {
              autoSize: chatActive ? { minRows: 2, maxRows: 7 } : { minRows: 5, maxRows: 9 },
              placeholder: "直接输入报销问题、事项描述，或拖入发票和附件。",
              onFocus: activateChat,
              onPaste: handlePaste,
              onDrop: handleDrop,
              onPressEnter: (event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                }
                if (!event.shiftKey && !submitting) {
                  form.submit();
                }
              },
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
                  onChange: ({ fileList: next }) => {
                    activateChat();
                    setFileList(next.map((file) => (file.originFileObj ? file : { ...file, originFileObj: file.originFileObj || file })));
                  },
                },
                e(Button, { icon: icon(PaperClipOutlined) || icon(FileAddOutlined) }, "附件")
              ),
              e(Button, { href: "/#knowledge", icon: icon(SearchOutlined) }, "知识库"),
              fileList.length
                ? e(Button, { danger: true, icon: icon(DeleteOutlined), onClick: () => setFileList([]) }, "清空")
                : null
            ),
            e(
              "span",
              { className: "chat-hint" },
              "Enter 发送 · Shift+Enter 换行"
            ),
            e(
              Button,
              {
                type: "primary",
                htmlType: "submit",
                loading: submitting,
                icon: icon(SendOutlined),
              },
              "发送"
            )
          )
        )
      )
    );
  }

  function AboutSoftwareSection() {
    return e(
      "section",
      { className: "about-software-section" },
      e(Title, { level: 2 }, "关于本软件：我们为什么需要一个报销 Agent？"),
      e(
        Paragraph,
        null,
        "现有的高校财务系统，是为“合规、审计和支付”设计的，而不是为“方便前端填报”设计的。这导致老师和学生们每天面临着巨大的低价值劳动：反复查找政策依据、整理散落各处的票据、在难用的网页上重复搬运数据，以及面对被财务退回后从头再来的崩溃。"
      ),
      e(
        Paragraph,
        null,
        "“自助报销 Agent”的初衷，不是去替代现有的财务系统，更不是去绕过学校的审批流程。它是在现有的合规边界内，为你建立一个本地的个人财务工作台。"
      ),
      e(Text, { strong: true }, "为了绝对的安全与合规，本软件坚守以下边界："),
      e(
        "ol",
        null,
        e("li", null, e("strong", null, "人机隔离："), "Agent 只负责整理材料、查阅政策、生成草稿和辅助代填；而账号登录、经费项目选择、资金确认与最终提交，必须由用户本人手动完成。"),
        e("li", null, e("strong", null, "本地优先："), "票据和数据默认在本地处理，最大程度保护个人财务隐私。"),
        e("li", null, e("strong", null, "把规则前置："), "改变“提交后等退回”的盲盒模式，在提交前系统就会自动对照财务处公开口径，生成“缺漏清单”和风险提示。")
      ),
      e(
        Paragraph,
        { className: "about-software-closing" },
        "我们希望通过这个工具，把你从繁杂的材料整理和表单搬运中彻底解放出来。机器处理复杂流程，人类只需确认责任。"
      ),
      e(Title, { level: 3, className: "about-software-subtitle" }, "关于我们"),
      e(
        Paragraph,
        null,
        "本项目来自 ",
        e("a", { href: "http://www.hintlab.cn", target: "_blank", rel: "noreferrer" }, "HINT Lab"),
        "。在我们实验室，我们始终在追问和关注一个命题：到底应该是技术服务于人，还是让人沦为系统的附庸？"
      ),
      e(
        Paragraph,
        null,
        "现有的许多流程（比如繁琐的报销），本质上是在无形中剥削人的认知。它把原本应该专注于创造的人，异化成了在死板规则和难用网页之间机械搬运数据的“生物接口”。"
      ),
      e(
        Paragraph,
        null,
        "我们不愿看到人被系统这样消耗。但打破这种现状，不能仅靠在云端的高谈阔论，而是必须有人愿意把双手插进泥土里，去写下那几万行抵抗枯燥的代码，去一点点修补现实的粗糙。"
      ),
      e(
        Paragraph,
        null,
        "这个 Agent，就是我们用泥土的双手给出的答案：把脏活累活交还给机器，让人回归为真正的人。"
      ),
      e(
        Paragraph,
        { className: "about-software-closing" },
        "如果你也认同这样的技术观，期待你能访问 HINT 实验室主页 ",
        e("a", { href: "http://www.hintlab.cn", target: "_blank", rel: "noreferrer" }, "http://www.hintlab.cn"),
        " 认识我们，和我们一起去重塑人与系统的边界。"
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
        e(Form.Item, { label: "事项名称", name: "title" }, e(Input, { placeholder: "请输入待整理事项名称" })),
        e(
          Form.Item,
          { label: "随手备注", name: "note", rules: [{ required: true, message: "请写一句备注" }] },
          e(Input.TextArea, { rows: 4, placeholder: "请随手记录这张票据对应的业务、缺什么材料、准备走哪个经费项目。" })
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
        e(Form.Item, { label: "材料组名称", name: "title" }, e(Input, { placeholder: "请输入这组材料的名称" })),
        e(Form.Item, { label: "线索备注", name: "note" }, e(Input.TextArea, { rows: 3, placeholder: "记录这些材料可能对应的业务、缺失附件和后续处理线索。" })),
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
          placeholder: "输入要查询的报销政策或材料要求",
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
                    description: hit.published_date ? `日期 ${hit.published_date}` : "来源片段",
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
        e(
          Space,
          { direction: "vertical", className: "full", size: 10 },
          e(Space, { wrap: true }, supported.map((item) => e(Tag, { key: item, color: "blue" }, item)))
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

  function SettingsView({ focus }) {
    const [status, setStatus] = React.useState(null);
    const [knowledgeStatus, setKnowledgeStatus] = React.useState(null);
    const [error, setError] = React.useState("");
    const [mailPolling, setMailPolling] = React.useState(false);
    const [authLaunching, setAuthLaunching] = React.useState(false);
    const [authChecking, setAuthChecking] = React.useState(false);

    function refreshStatus() {
      fetch("/api/settings/status")
        .then((response) => response.json())
        .then((payload) => setStatus(payload))
        .catch(() => setError("读取配置失败"));
    }

    React.useEffect(() => {
      let mounted = true;
      fetch("/api/settings/status")
        .then((response) => response.json())
        .then((payload) => {
          if (mounted) setStatus(payload);
        })
        .catch(() => {
          if (mounted) setError("读取配置失败");
        });
      fetch("/api/knowledge/status")
        .then((response) => response.json())
        .then((payload) => {
          if (mounted) setKnowledgeStatus(payload);
        })
        .catch(() => {
          if (mounted) setKnowledgeStatus(null);
        });
      return () => {
        mounted = false;
      };
    }, []);

    async function launchShuAuth() {
      setAuthLaunching(true);
      try {
        const payload = await startShuAuthLogin();
        if (payload.started) {
          message.success("已打开扫码登录窗口");
        } else {
          message.info(payload.message || "扫码登录窗口已在运行");
        }
        refreshStatus();
        window.setTimeout(refreshStatus, 1500);
        window.setTimeout(refreshStatus, 5000);
      } catch (authError) {
        message.error(authError.message || "启动扫码登录窗口失败");
      } finally {
        setAuthLaunching(false);
      }
    }

    async function checkShuAuth() {
      setAuthChecking(true);
      try {
        const response = await fetch("/api/shu-auth/check", { method: "POST" });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || "实时检查财务系统会话失败");
        }
        setStatus((current) => {
          const base = current || {};
          return { ...base, shu_auth: payload.shu_auth };
        });
        if (payload.checked && payload.shu_auth && payload.shu_auth.status === "ready") {
          message.success("财务系统会话可用");
        } else {
          message.info((payload.shu_auth && payload.shu_auth.message) || "请完成登录后再检查");
        }
      } catch (authError) {
        message.error(authError.message || "实时检查财务系统会话失败");
      } finally {
        setAuthChecking(false);
      }
    }

    async function pollMailbox() {
      setMailPolling(true);
      try {
        const body = new FormData();
        body.append("limit", "10");
        const response = await fetch("/api/mail/poll", { method: "POST", body });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          message.error(payload.error || "拉取失败");
          return;
        }
        if (payload.count > 0) {
          message.success(`已整理 ${payload.count} 封邮件`);
          setTimeout(() => (window.location.href = "/?refresh=" + Date.now() + "#waiting"), 600);
        } else {
          message.info("没有新邮件");
        }
        fetch("/api/settings/status")
          .then((r) => r.json())
          .then((p) => setStatus(p))
          .catch(() => {});
      } catch (mailError) {
        message.error("拉取失败，请检查本机邮箱配置");
      } finally {
        setMailPolling(false);
      }
    }

    if (error) {
      return e(Card, { className: "work-card" }, e(Alert, { type: "error", showIcon: true, message: error }));
    }
    if (!status) {
      return e(Card, { className: "work-card" }, e(Alert, { type: "info", showIcon: true, message: "正在读取本地配置……" }));
    }

    const doubao = status.doubao || {};
    const imap = status.imap || {};
    const kb = status.knowledge_base || {};
    const kbReport = (knowledgeStatus && knowledgeStatus.corpus_report) || {};
    const kbEmptyBySource = kbReport.empty_text_by_source_type || {};
    const playwright = status.playwright || {};
    const shuAuth = status.shu_auth || {};

    const doubaoOk = doubao.enabled && doubao.has_model;
    const kbOk = kb.index_exists && kb.documents_exists;
    const adapterOk = playwright.shu_adapter_configured;

    function authLabel() {
      if (!shuAuth.profile_exists) return { color: "default", text: "未建立" };
      const map = {
        ready: ["green", "可用"],
        needs_scan: ["orange", "需扫码"],
        needs_renew: ["gold", "需续登"],
        error: ["red", "失败"],
      };
      return map[shuAuth.status] || ["default", "未检测"];
    }

    const cards = [
      {
        key: "doubao",
        title: "票据识别",
        icon: " scanned",
        ok: doubaoOk,
        statusText: doubaoOk ? "已启用" : doubao.has_api_key ? "未启用" : "未配置",
        meta: doubaoOk ? doubao.model || "" : "",
      },
      {
        key: "imap",
        title: "邮箱归集",
        icon: " mail",
        ok: imap.configured,
        statusText: imap.configured ? "已配置" : "未配置",
        meta: imap.configured ? `已处理 ${imap.processed_count || 0} 封` : "",
      },
      {
        key: "kb",
        title: "知识库",
        icon: " book",
        ok: kbOk,
        statusText: kbOk ? "可用" : "缺失",
        meta: kbOk && kb.index_size_bytes ? `${Math.round(kb.index_size_bytes / 1024 / 1024)} MB` : "",
      },
      {
        key: "adapter",
        title: "财务系统",
        icon: " link",
        ok: adapterOk,
        statusText: adapterOk ? "已配置" : playwright.shu_adapter_exists ? "待配置" : "未配置",
        meta: "",
      },
    ];

    return e(
      React.Fragment,
      null,
      e(AboutSoftwareSection),
      e(
        Row,
        { gutter: [12, 12], className: "settings-status-grid" },
        cards.map((item) =>
          e(
            Col,
            { xs: 12, md: 6, key: item.key },
            e(
              "div",
              { className: "status-mini" + (item.ok ? " is-ok" : "") },
              e("div", { className: "status-mini-head" }, e(Text, { type: "secondary" }, item.title)),
              e(
                "div",
                { className: "status-mini-body" },
                e(Tag, { color: item.ok ? "green" : "default" }, item.statusText),
                item.meta ? e(Text, { type: "secondary", className: "status-mini-meta" }, item.meta) : null
              )
            )
          )
        )
      ),
      knowledgeStatus
        ? e(
            Card,
            { className: "work-card", bordered: false, title: "知识库诊断" },
            e(
              Space,
              { direction: "vertical", size: 6, className: "full" },
              e(
                Text,
                null,
                `索引片段 ${knowledgeStatus.chunk_count || 0} 条；已索引文档 ${kbReport.indexed_document_count || 0} 份；文档总量 ${kbReport.document_count || 0} 份；空文本附件 ${kbEmptyBySource.attachment || 0} 个。`
              ),
              kbReport.warnings && kbReport.warnings.length
                ? e(Alert, { type: "warning", showIcon: true, message: "入库校验提示", description: kbReport.warnings.join("；") })
                : null
            )
          )
        : null,
      e(
        Card,
        {
          className: "work-card auth-card" + (focus === "auth" ? " auth-card-focused" : ""),
          bordered: false,
        },
        e(
          "div",
          { className: "auth-card-row" },
          e(
            "div",
            { className: "auth-card-info" },
            e(Text, { strong: true }, "上海大学登录"),
            e(
              "div",
              { className: "auth-card-sub" },
              e(Tag, { color: authLabel().color }, authLabel().text),
              shuAuth.checked_at
                ? e(Text, { type: "secondary" }, `上次检测 ${shuAuth.checked_at}`)
                : e(Text, { type: "secondary" }, shuAuth.profile_exists ? "本机已建立登录档案" : "尚未建立登录档案")
            ),
            shuAuth.message
              ? e(Text, { type: "secondary", className: "auth-card-msg" }, shuAuth.message)
              : null
          ),
          e(
            Space,
            { wrap: true },
            e(
              Button,
              {
                icon: icon(LoginOutlined),
                loading: authLaunching || Boolean(shuAuth.login_running),
                onClick: launchShuAuth,
              },
              shuAuth.login_running ? "登录窗口已打开" : "打开扫码登录窗口"
            ),
            e(Button, { loading: authChecking, disabled: Boolean(shuAuth.login_running), onClick: checkShuAuth }, "实时检查")
          )
        )
      ),
      imap.configured
        ? e(
            Card,
            { className: "work-card", bordered: false },
            e(
              "div",
              { className: "settings-action-bar" },
              e(Text, null, "邮箱里有新的发票邮件？"),
              e(
                Button,
                { icon: icon(SyncOutlined), loading: mailPolling, onClick: pollMailbox },
                "立即拉取"
              )
            )
          )
        : null,
      e(
        Card,
        { className: "work-card", bordered: false },
        e(
          "div",
          { className: "settings-foot" },
          e(Text, { type: "secondary" }, "密钥、邮箱密码等敏感信息只存本地，不会显示在这里。")
        )
      )
    );
  }

  function Workspace() {
    const [activeKey, setActiveKey] = React.useState(normalizeKey(window.location.hash));
    const [sidebarCollapsed, setSidebarCollapsed] = React.useState(() => localStorage.getItem("reimbursement.sidebar.collapsed") === "true");
    React.useEffect(() => {
      function onHashChange() {
        setActiveKey(normalizeKey(window.location.hash));
      }
      window.addEventListener("hashchange", onHashChange);
      return () => window.removeEventListener("hashchange", onHashChange);
    }, []);

    function toggleSidebar() {
      setSidebarCollapsed((value) => {
        const next = !value;
        localStorage.setItem("reimbursement.sidebar.collapsed", String(next));
        return next;
      });
    }

    function selectKey(key) {
      const raw = String(key || "");
      const view = normalizeKey(raw);
      setActiveKey(view);
      if (raw === "auth") {
        if (window.location.hash !== "#auth") window.location.hash = "auth";
        return;
      }
      if (window.location.hash !== "#" + view) {
        window.location.hash = view;
      }
    }

    const views = {
      home: e(HomeView),
      knowledge: e(KnowledgeView),
      collection: e(CollectionView),
      waiting: e(WaitingView),
      reimbursed: e(ReimbursedView),
      settings: e(SettingsView, { focus: rawHashKey() === "auth" ? "auth" : null }),
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
            e(Sidebar, { activeKey, onSelect: selectKey, collapsed: sidebarCollapsed, onToggleCollapsed: toggleSidebar }),
            e(Layout, { className: "main-layout" }, e(Content, { className: "antd-content" }, views[activeKey] || views.home))
          )
      )
    );
  }

  ReactDOM.createRoot(document.getElementById("root")).render(e(Workspace));
})();
