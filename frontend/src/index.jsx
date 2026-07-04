import React from "react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  Checkbox,
  Col,
  ConfigProvider,
  Dropdown,
  Empty,
  Form,
  Input,
  Layout,
  List,
  Menu,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
  theme,
} from "antd";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  FileAddOutlined,
  FolderOpenOutlined,
  HomeOutlined,
  InboxOutlined,
  InfoCircleOutlined,
  LoginOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  PaperClipOutlined,
  ReloadOutlined,
  SearchOutlined,
  SendOutlined,
  SettingOutlined,
  SyncOutlined,
  UserOutlined,
} from "@ant-design/icons";
import "antd/dist/reset.css";

const e = React.createElement;
const App = AntdApp;
  const data = window.__REIMBURSEMENT_DATA__ || {};
  const allPackages = data.packages || data.recent || [];
  const inboxItems = data.inbox_items || [];
  const materialItems = data.material_items || [];
  const Dragger = Upload.Dragger;
  const { Content, Sider } = Layout;
  const { Title, Text, Paragraph } = Typography;
  const NAV_KEYS = ["home", "knowledge", "collection", "waiting", "reimbursed", "settings"];
  const AGREEMENT_VERSION = "2026-06-30";
  const AGREEMENT_STORAGE_KEY = `shu-reimbursement-agent.agreement.${AGREEMENT_VERSION}`;
  const agreementSections = [
    {
      title: "工具定位",
      items: [
        "本工具只用于上海大学报销材料整理、政策依据检索、草稿生成和本地代填辅助，不替代本人判断，也不代表学校财务处最终审核意见。",
        "财务处公开网页、指南、RAG 检索和大模型生成内容均为辅助信息；如与学校系统、财务处通知或人工审核不一致，以学校正式口径为准。",
      ],
    },
    {
      title: "登录与自动化边界",
      items: [
        "学校统一身份认证、扫码、验证码、滑块、二次确认和最终提交必须由本人完成。",
        "本工具不保存统一身份认证密码，不保存 OAuth code，不绕过验证码或二次认证。",
        "为实现登录保持，本工具会在本机保存专用浏览器 profile，其中可能包含 cookies、localStorage、sessionStorage 等登录态数据。",
      ],
    },
    {
      title: "材料与隐私",
      items: [
        "上传的发票、邮件、附件、报销备注可能包含个人、项目、财务和单位信息；默认只在本机处理和保存。",
        "如启用大模型或邮箱接入，用户应确认本机配置、服务商和数据发送范围符合自己的安全要求。",
        "用户可在设置或本机目录中清理浏览器会话、报销材料、邮件缓存和生成文件。",
      ],
    },
    {
      title: "用户责任",
      items: [
        "用户应确认票据真实合法、业务真实发生、经费项目准确、收款账号无误、附件完整合规。",
        "Agent 只能辅助填写草稿和整理材料，不会自动点击学校财务系统的最终提交按钮。",
        "提交前必须由本人复核学校系统页面、附件、金额、项目、账号和审批流。",
      ],
    },
  ];
  const DEEPSEEK_MODEL_OPTIONS = [
    { value: "deepseek-v4-pro", label: "deepseek-v4-pro" },
    { value: "deepseek-v4-flash", label: "deepseek-v4-flash" },
  ];

  function icon(IconComponent) {
    return IconComponent ? e(IconComponent) : null;
  }

  async function startShuAuthLogin() {
    const response = await fetch("/api/shu-auth/login", { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "启动扫码登录窗口失败");
    }
    return payload;
  }

  function AgreementContent() {
    return e(
      "div",
      { className: "agreement-content" },
      e(Alert, {
        type: "warning",
        showIcon: true,
        message: "请先确认使用边界",
        description: "这个工具会处理报销材料，并可能保存本机浏览器登录态。学校登录、验证码、二次确认和最终提交必须由本人完成。",
      }),
      agreementSections.map((section) =>
        e(
          "section",
          { key: section.title, className: "agreement-section" },
          e(Title, { level: 5 }, section.title),
          e(
            "ul",
            null,
            section.items.map((item) => e("li", { key: item }, item))
          )
        )
      ),
      e(Paragraph, { type: "secondary" }, `协议版本：${AGREEMENT_VERSION}`)
    );
  }

  function UserAgreementGate({ children }) {
    const [accepted, setAccepted] = React.useState(() => localStorage.getItem(AGREEMENT_STORAGE_KEY) === "accepted");
    const [viewerOpen, setViewerOpen] = React.useState(false);
    const [checked, setChecked] = React.useState(false);
    React.useEffect(() => {
      function openAgreement() {
        setViewerOpen(true);
      }
      window.addEventListener("open-user-agreement", openAgreement);
      return () => window.removeEventListener("open-user-agreement", openAgreement);
    }, []);
    const open = !accepted || viewerOpen;
    const canAccept = accepted || checked;
    function confirmAgreement() {
      if (!accepted) {
        localStorage.setItem(AGREEMENT_STORAGE_KEY, "accepted");
        setAccepted(true);
        message.success("已确认用户协议和用户须知");
      }
      setViewerOpen(false);
    }
    return e(
      React.Fragment,
      null,
      children,
      e(
        Modal,
        {
          title: "用户协议与用户须知",
          open,
          centered: true,
          width: 760,
          closable: accepted,
          maskClosable: accepted,
          keyboard: accepted,
          onCancel: () => setViewerOpen(false),
          footer: e(
            Space,
            { className: "agreement-footer" },
            accepted
              ? e(Button, { onClick: () => setViewerOpen(false) }, "关闭")
              : e(Checkbox, { checked, onChange: (event) => setChecked(event.target.checked) }, "我已阅读并同意以上用户协议和用户须知"),
            e(Button, { type: "primary", disabled: !canAccept, onClick: confirmAgreement }, accepted ? "我知道了" : "同意并进入")
          ),
        },
        e(AgreementContent)
      )
    );
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

  function authActionInfo(authStatus) {
    switch (authStatus) {
      case "ready":
        return { label: "已连接", tone: "ready", action: "续登", icon: ReloadOutlined };
      case "needs_renew":
        return { label: "待续登", tone: "warn", action: "立即续登", icon: ReloadOutlined };
      case "needs_scan":
        return { label: "待登录", tone: "warn", action: "去扫码登录", icon: LoginOutlined };
      case "error":
        return { label: "需检查", tone: "error", action: "重新登录", icon: LoginOutlined };
      case "not_checked":
      default:
        return { label: "本机模式", tone: "idle", action: "登录学校账号", icon: LoginOutlined };
    }
  }

  function formatSettingsTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    const pad = (num) => String(num).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function Sidebar({ activeKey, onSelect, collapsed, onToggleCollapsed, onOpenAbout, onLaunchAuth }) {
    const user = data.user || {};
    const items = [
      { key: "home", icon: icon(HomeOutlined), label: "报销助手" },
      { key: "knowledge", icon: icon(DatabaseOutlined), label: "报销知识" },
      { key: "waiting", icon: icon(ClockCircleOutlined), label: "待办报销" },
      { key: "collection", icon: icon(FolderOpenOutlined), label: "资料归集" },
      { key: "reimbursed", icon: icon(CheckCircleOutlined), label: "报销记录" },
    ];
    const authInfo = authActionInfo(user.auth_status);
    const authActionIcon = authInfo.icon;
    const avatarTone = authInfo.tone;
    const rawAccountName = String(user.display_name || "").trim();
    const accountName = rawAccountName && rawAccountName !== "工号未识别" ? rawAccountName : "未绑定工号";
    const userMenu = {
      items: [
        {
          key: "user-header",
          type: "group",
          label: e(
            "div",
            { className: "user-menu-header" },
            e("div", { className: "user-menu-name" }, accountName),
            e(
              "div",
              { className: `user-menu-status user-menu-status--${avatarTone}` },
              e("i", { className: "user-menu-status-dot" }),
              user.subtitle || "本机模式"
            )
          ),
          disabled: true,
        },
        { type: "divider" },
        {
          key: "auth-action",
          icon: e(authActionIcon),
          label: "扫码登录",
        },
        {
          key: "settings",
          icon: e(SettingOutlined),
          label: "系统设置",
        },
        {
          key: "about",
          icon: e(InfoCircleOutlined),
          label: "说明",
        },
      ],
      onClick: ({ key }) => {
        if (key === "settings") onSelect("settings");
        else if (key === "auth-action") onLaunchAuth();
        else if (key === "about") onOpenAbout();
      },
    };
    return e(
      Sider,
      { width: 224, collapsedWidth: 72, collapsed, collapsible: false, className: "app-sider" },
      e(
        "div",
        { className: "brand-block" },
        e(
          "button",
          {
            className: "brand-logo",
            type: "button",
            onClick: () => collapsed && onToggleCollapsed(),
            title: collapsed ? "展开侧边栏" : undefined,
            "aria-label": "上海大学财务助手",
            tabIndex: collapsed ? 0 : -1,
          },
          e("img", { src: "/logo.png", alt: "上海大学财务助手" })
        ),
        e(
          "div",
          { className: "brand-text" },
          e("strong", null, "上海大学"),
          e(
            "button",
            {
              className: "brand-collapse-btn",
              type: "button",
              onClick: onToggleCollapsed,
              title: collapsed ? "展开侧边栏" : "收起侧边栏",
              "aria-label": collapsed ? "展开侧边栏" : "收起侧边栏",
            },
            e(collapsed ? MenuUnfoldOutlined : MenuFoldOutlined)
          ),
          e("small", null, "自助报销 Agent")
        )
      ),
      e(Menu, {
        className: "sidebar-main-menu",
        theme: "dark",
        mode: "inline",
        inlineCollapsed: collapsed,
        selectedKeys: activeKey === "settings" ? [] : [activeKey],
        items,
        onClick: ({ key }) => onSelect(key),
      }),
      e(
        "div",
        { className: "sidebar-bottom" },
        e(
          Dropdown,
          {
            trigger: ["click"],
            placement: "topLeft",
            overlayClassName: "sidebar-user-dropdown",
            menu: userMenu,
          },
          e(
            "button",
            {
              className: `sidebar-user sidebar-user--${avatarTone}`,
              type: "button",
              title: collapsed ? accountName : undefined,
            },
            e(
              "span",
              { className: "sidebar-user-avatar" },
              e(UserOutlined)
            ),
            !collapsed &&
              e(
                "span",
                { className: "sidebar-user-meta" },
                e("span", { className: "sidebar-user-name" }, accountName),
                e(
                  "span",
                  { className: "sidebar-user-status" },
                  e("i", { className: `sidebar-user-status-dot sidebar-user-status-dot--${avatarTone}` }),
                  authInfo.label
                )
              ),
            !collapsed && e("span", { className: "sidebar-user-chevron" }, "⌃")
          )
        )
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

  const markdownComponents = {
    a({ node, ...props }) {
      return e("a", { ...props, target: "_blank", rel: "noreferrer" });
    },
  };

  function MarkdownMessage({ text }) {
    return e(
      "div",
      { className: "chat-markdown" },
      e(
        ReactMarkdown,
        {
          remarkPlugins: [remarkGfm],
          components: markdownComponents,
        },
        text || ""
      )
    );
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

  function renderChatMessage(item, index, user, onAction) {
    if (item && item.thinking) {
      const roleLabel = "报销 Agent · " + (item.title || "正在思考");
      return e(
        "div",
        { key: "thinking-" + (item.planId || index), className: "chat-message chat-message--assistant chat-message--thinking" },
        e("img", { className: "chat-message-avatar chat-message-avatar--assistant", src: "/static/icons/agent-transparent.png", alt: "报销 Agent" }),
        e(
          "div",
          { className: "chat-message-body" },
          e("div", { className: "chat-message-role" }, roleLabel),
          e(
            "div",
            { className: "chat-message-text chat-thinking" },
            e("span", { className: "chat-thinking-dots", "aria-hidden": "true" }, e("i"), e("i"), e("i")),
            e("span", { className: "chat-thinking-step", key: item.step || index }, item.step || "")
          )
        )
      );
    }
    const isAssistant = item.role === "assistant";
    const avatar = isAssistant
      ? e("img", { className: "chat-message-avatar chat-message-avatar--assistant", src: "/static/icons/agent-transparent.png", alt: "报销 Agent" })
      : e(
          "span",
          { className: "chat-message-avatar chat-message-avatar--user" },
          String((user && user.display_name) || "本").slice(0, 1).toUpperCase()
        );
    const messageContent =
      item.streaming && !item.text
        ? e(
            "div",
            { className: "chat-thinking" },
            e("span", { className: "chat-thinking-dots", "aria-hidden": "true" }, e("i"), e("i"), e("i")),
            e("span", { className: "chat-thinking-step" }, item.streamStatus || "正在处理")
          )
        : isAssistant
          ? e(MarkdownMessage, { text: item.text })
          : item.text;
    return e(
      "div",
      { key: item.role + "-" + index, className: "chat-message chat-message--" + item.role },
      avatar,
      e(
        "div",
        { className: "chat-message-body" },
        e("div", { className: "chat-message-role" }, item.role === "user" ? "你" : "报销 Agent"),
        e(
          "div",
          { className: `chat-message-text${item.streaming ? " chat-message-text--streaming" : ""}` },
          messageContent,
          item.sources && item.sources.length
            ? e(
                "div",
                { className: "chat-source-list" },
                item.sources.map((source) =>
                  e(
                    "a",
                    { key: source.rank, href: source.url, target: "_blank", rel: "noreferrer" },
                    source.rank + ". " + source.title
                  )
                )
              )
            : null,
          item.link ? e(Button, { className: "chat-message-action", type: "primary", href: item.link.href }, item.link.label) : null,
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
                      onClick: action.href ? undefined : () => onAction(action),
                    },
                    action.label
                  )
                )
              )
            : null
        )
      )
    );
  }

  function HomeAssistantChat() {
    const [form] = Form.useForm();
    const [fileList, setFileList] = React.useState([]);
    const [submitting, setSubmitting] = React.useState(false);
    const [chatActive, setChatActive] = React.useState(false);
    const [messages, setMessages] = React.useState([]);
    const threadRef = React.useRef(null);
    const thinkingTimerRef = React.useRef(null);
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

    function scrollThreadToBottom() {
      const node = threadRef.current;
      if (!node) return;
      requestAnimationFrame(() => {
        node.scrollTop = node.scrollHeight + 16;
      });
    }

    React.useEffect(() => {
      return () => {
        if (thinkingTimerRef.current) {
          clearInterval(thinkingTimerRef.current);
          thinkingTimerRef.current = null;
        }
      };
    }, []);

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

    function buildThinkingPlan(note, hasFiles) {
      const isPolicy = isPolicyQuestion(note);
      if (hasFiles) {
        return {
          title: "正在解析材料",
          steps: [
            "正在读取发票和附件内容…",
            "正在识别金额、抬头、发票号和日期…",
            "正在匹配报销类别和必需材料…",
            "正在整理报销包草稿…",
          ],
        };
      }
      if (isPolicy) {
        return {
          title: "正在查阅资料",
          steps: [
            "正在理解你的报销问题…",
            "正在检索上海大学财务处资料库…",
            "正在比对政策文件和指南…",
            "正在整理可追溯的回答和引用…",
          ],
        };
      }
      return {
        title: "正在分析意图",
        steps: [
          "正在判断你是查政策、记一笔，还是整理报销包…",
          "正在匹配最合适的处理方式…",
          "正在准备回复…",
        ],
      };
    }

    function startThinkingAnimation(plan) {
      let index = 0;
      setMessages((current) => {
        const next = current.slice();
        next.push({
          role: "assistant",
          thinking: true,
          step: plan.steps[0],
          title: plan.title,
          planId: Date.now(),
        });
        return next;
      });
      scrollThreadToBottom();
      if (thinkingTimerRef.current) {
        clearInterval(thinkingTimerRef.current);
        thinkingTimerRef.current = null;
      }
      thinkingTimerRef.current = setInterval(() => {
        index = (index + 1) % plan.steps.length;
        setMessages((current) => {
          let updated = false;
          const next = current.map((msg) => {
            if (msg.thinking) {
              updated = true;
              return { ...msg, step: plan.steps[index] };
            }
            return msg;
          });
          return updated ? next : current;
        });
      }, 1600);
    }

    function stopThinkingAnimation() {
      if (thinkingTimerRef.current) {
        clearInterval(thinkingTimerRef.current);
        thinkingTimerRef.current = null;
      }
      setMessages((current) => current.filter((msg) => !msg.thinking));
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
          text: payload.message || `已生成报销工作单。\n\n材料 ${payload.package.document_count || 0} 份；待补 ${payload.package.missing_count || 0} 项。`,
          link: payload.package.url ? { href: payload.package.url, label: "查看工作单" } : null,
          actions: payload.actions || [],
        };
      }
      if (payload.action === "project_confirmation" && payload.package) {
        return {
          role: "assistant",
          text: payload.message || "我已记录项目和余额确认。",
          link: payload.package.url ? { href: payload.package.url, label: "查看工作单" } : null,
          actions: payload.actions || [],
        };
      }
      if (payload.action === "supplement_package" && payload.package) {
        return {
          role: "assistant",
          text: payload.message || "我已合并补充材料并重新检查。",
          link: payload.package.url ? { href: payload.package.url, label: "查看工作单" } : null,
          actions: payload.actions || [],
        };
      }
      if (
        [
          "school_flow_blocked",
          "school_flow_confirm",
          "school_login_required",
          "school_fill_ready",
          "school_fill_blocked",
          "catering_reimbursement_confirmed",
          "invoice_help",
          "invoice_upload_prompt",
        ].includes(payload.action) &&
        payload.package
      ) {
        return {
          role: "assistant",
          text: payload.message || "我会继续处理这笔报销。",
          link: payload.package.url ? { href: payload.package.url, label: "查看工作单" } : null,
          actions: payload.actions || [],
        };
      }
      if (payload.action === "create_inbox" && payload.item) {
        return {
          role: "assistant",
          text: payload.message || "已放进资料归集，后面补材料后再生成报销包。",
          link: { href: payload.item.url, label: "查看资料归集" },
        };
      }
      return {
        role: "assistant",
        text: payload.message || "你是想查政策依据、记录一个待报销事项，还是整理已有发票？",
        actions: payload.actions || [],
      };
    }

    function updateStreamMessage(streamId, patch) {
      setMessages((current) =>
        current.map((item) => (item.streamId === streamId ? { ...item, ...patch } : item))
      );
      requestAnimationFrame(() => scrollThreadToBottom());
    }

    function readSseBlock(block) {
      const event = { type: "message", data: {} };
      const dataLines = [];
      block.split(/\r?\n/).forEach((line) => {
        if (line.startsWith("event:")) {
          event.type = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trimStart());
        }
      });
      if (dataLines.length) {
        try {
          event.data = JSON.parse(dataLines.join("\n"));
        } catch (error) {
          event.data = {};
        }
      }
      return event;
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
        setMessages((current) => [
          ...current,
          { role: "user", text: note },
          typoMessage,
        ]);
        form.setFieldsValue({ title: "", note: "" });
        requestAnimationFrame(() => scrollThreadToBottom());
        return;
      }
      const body = new FormData();
      body.append("title", title);
      body.append("note", note);
      body.append(
        "history",
        JSON.stringify(
          messages
            .filter((item) => !item.thinking && !item.streaming && !item.suggestionOnly && item.text)
            .slice(-8)
            .map((item) => ({ role: item.role, text: item.text }))
        )
      );
      fileList.forEach((file) => body.append("files", file.originFileObj || file));
      const userMessage = note || `上传了 ${fileList.length} 份材料`;
      const streamId = `assistant-stream-${Date.now()}`;
      setMessages((current) => [
        ...current,
        { role: "user", text: userMessage },
        { role: "assistant", text: "", streaming: true, streamId, streamStatus: "正在连接报销助手" },
      ]);
      form.setFieldsValue({ title: "", note: "" });
      setSubmitting(true);
      let streamedText = "";
      let completedPayload = null;
      try {
        const response = await fetch("/api/home/assistant/stream", { method: "POST", body });
        if (!response.ok || !response.body) {
          throw new Error("流式接口不可用");
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split(/\n\n/);
          buffer = blocks.pop() || "";
          for (const block of blocks) {
            if (!block.trim()) continue;
            const event = readSseBlock(block);
            if (event.type === "status") {
              updateStreamMessage(streamId, { streamStatus: event.data.message || "正在处理" });
            } else if (event.type === "delta") {
              streamedText += event.data.text || "";
              updateStreamMessage(streamId, { text: streamedText, streamStatus: "" });
            } else if (event.type === "done") {
              completedPayload = event.data.payload || null;
            } else if (event.type === "error") {
              throw new Error(event.data.error || "处理失败");
            }
          }
        }
        if (!completedPayload) {
          throw new Error("流式响应未完成");
        }
        const finalMessage = assistantMessageFrom(completedPayload);
        updateStreamMessage(streamId, {
          ...finalMessage,
          text: streamedText || finalMessage.text,
          streaming: false,
          streamStatus: "",
          streamId,
        });
        if (!completedPayload.ok) {
          message.error(completedPayload.error || "处理失败");
          return;
        }
        setFileList([]);
      } catch (error) {
        updateStreamMessage(streamId, { streamStatus: "流式连接异常，正在切换普通接口" });
        try {
          const fallbackResponse = await fetch("/api/home/assistant", { method: "POST", body });
          const fallbackPayload = await fallbackResponse.json();
          if (!fallbackResponse.ok || !fallbackPayload.ok) {
            throw new Error(fallbackPayload.error || "处理失败");
          }
          const finalMessage = assistantMessageFrom(fallbackPayload);
          updateStreamMessage(streamId, { ...finalMessage, streaming: false, streamStatus: "", streamId });
          setFileList([]);
        } catch (fallbackError) {
          const errorText = fallbackError && fallbackError.message ? fallbackError.message : error && error.message ? error.message : "处理失败，请检查材料后重试";
          message.error(errorText);
          updateStreamMessage(streamId, {
            text: errorText || "处理失败，请检查本地服务、大模型配置或网络后重试。",
            streaming: false,
            streamStatus: "",
          });
        }
      } finally {
        setSubmitting(false);
        requestAnimationFrame(() => scrollThreadToBottom());
      }
    }

    async function handleMessageAction(action) {
      if (!action) return;
      if (action.href) {
        window.location.href = action.href;
        return;
      }
      if (action.type === "login") {
        try {
          const payload = await startShuAuthLogin();
          message.success(payload.message || "已打开统一登录窗口");
          setMessages((current) => [
            ...current,
            {
              role: "assistant",
              text: "我已打开统一登录窗口。你只需要在窗口里完成学校登录；完成后回到这里点“我已完成登录”，我会继续检查并推进代填。",
              actions: [
                {
                  type: "ask",
                  label: "我已完成登录",
                  query: "我已完成统一登录，继续这笔报销。",
                },
              ],
            },
          ]);
        } catch (error) {
          const errorText = error && error.message ? error.message : "启动统一登录窗口失败";
          message.error(errorText);
          setMessages((current) => [
            ...current,
            {
              role: "assistant",
              text: `${errorText}。你不用去终端执行命令；可以稍后再点“打开统一登录”，或者到设置页检查登录状态。`,
            },
          ]);
        }
        return;
      }
      if (action.type === "school_fill" && action.package_id) {
        try {
          const response = await fetch(`/packages/${encodeURIComponent(action.package_id)}/school-fill`, { method: "POST", redirect: "follow" });
          message.info("已检查学校代填条件");
          window.location.href = response.url || `/packages/${encodeURIComponent(action.package_id)}/view`;
        } catch (error) {
          message.error("启动学校代填失败");
        }
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
          { className: "home-chat-subtitle" },
          e(Text, { type: "secondary" }, "一个入口处理政策查询、材料归集和报销包生成。")
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
                { className: "chat-thread", ref: threadRef },
                messages.map((item, index) => renderChatMessage(item, index, user, handleMessageAction))
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
                  if (!submitting) {
                    form.submit();
                  }
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
              message: result.answer_mode === "llm_rag" ? "RAG 生成答复" : "检索式答复",
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
      e("div", { className: "page-head" }, e("div", null, e(Title, { level: 2 }, "报销知识库"), e(Text, { type: "secondary" }, "基于最新的财务处公开网页和本地指南检索。"))),
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

  function SettingsView() {
    const [status, setStatus] = React.useState(null);
    const [knowledgeStatus, setKnowledgeStatus] = React.useState(null);
    const [error, setError] = React.useState("");
    const [mailPolling, setMailPolling] = React.useState(false);
    const [mailPollResult, setMailPollResult] = React.useState(null);
    const [mailSaving, setMailSaving] = React.useState(false);
    const [imapEnabled, setImapEnabled] = React.useState(false);
    const [imapHost, setImapHost] = React.useState("");
    const [imapPort, setImapPort] = React.useState("993");
    const [imapUsername, setImapUsername] = React.useState("");
    const [imapMailbox, setImapMailbox] = React.useState("INBOX");
    const [imapMarkSeen, setImapMarkSeen] = React.useState(false);
    const [imapClearPassword, setImapClearPassword] = React.useState(false);
    const [authLaunching, setAuthLaunching] = React.useState(false);
    const [authChecking, setAuthChecking] = React.useState(false);
    const [financeObserving, setFinanceObserving] = React.useState(false);
    const [userWorkId, setUserWorkId] = React.useState("");
    const [userSaving, setUserSaving] = React.useState(false);
    const [llmSaving, setLlmSaving] = React.useState(false);
    const [llmProvider, setLlmProvider] = React.useState("deepseek");
    const [llmBaseUrl, setLlmBaseUrl] = React.useState("https://api.deepseek.com");
    const [llmModel, setLlmModel] = React.useState("deepseek-v4-pro");
    const [llmEnabled, setLlmEnabled] = React.useState(false);
    const [llmClearKey, setLlmClearKey] = React.useState(false);

    const llmDefaults = {
      deepseek: { base_url: "https://api.deepseek.com", model: "deepseek-v4-pro" },
      doubao: { base_url: "https://ark.cn-beijing.volces.com/api/v3", model: "" },
      custom: { base_url: "", model: "" },
    };

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

    React.useEffect(() => {
      if (!status || !status.rag_llm) return;
      setLlmProvider(status.rag_llm.provider || "deepseek");
      setLlmBaseUrl(status.rag_llm.base_url || llmDefaults[status.rag_llm.provider || "deepseek"].base_url);
      setLlmModel(status.rag_llm.model || llmDefaults[status.rag_llm.provider || "deepseek"].model);
      setLlmEnabled(Boolean(status.rag_llm.enabled));
      setLlmClearKey(false);
    }, [status && status.rag_llm && status.rag_llm.provider, status && status.rag_llm && status.rag_llm.model]);

    React.useEffect(() => {
      if (!status || !status.imap) return;
      setImapEnabled(Boolean(status.imap.enabled));
      setImapHost(status.imap.host || "");
      setImapPort(String(status.imap.port || "993"));
      setImapUsername(status.imap.username || "");
      setImapMailbox(status.imap.mailbox || "INBOX");
      setImapMarkSeen(Boolean(status.imap.mark_seen));
      setImapClearPassword(false);
    }, [status && status.imap && status.imap.host, status && status.imap && status.imap.username, status && status.imap && status.imap.mailbox]);

    React.useEffect(() => {
      if (!status || !status.user) return;
      setUserWorkId(status.user.work_id || "");
    }, [status && status.user && status.user.work_id]);

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

    async function launchShuAuth() {
      setAuthLaunching(true);
      try {
        const payload = await startShuAuthLogin();
        if (payload.started) {
          message.success("已打开扫码登录窗口");
        } else {
          message.info(payload.message || "扫码登录窗口已在运行");
        }
        refreshStatus(() => true);
        window.setTimeout(() => refreshStatus(() => true), 1500);
        window.setTimeout(() => refreshStatus(() => true), 5000);
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

    async function observeFinanceForm() {
      setFinanceObserving(true);
      try {
        const response = await fetch("/api/shu-finance/observe", { method: "POST" });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || "观察学校表单失败");
        }
        const saved = payload.saved || {};
        if (saved.status === "form_ready") {
          message.success("已生成学校表单观察草稿");
        } else {
          message.info(saved.message || "未观察到日常报销单，请先完成统一登录");
        }
        refreshStatus(() => true);
      } catch (observeError) {
        message.error(observeError.message || "观察学校表单失败");
      } finally {
        setFinanceObserving(false);
      }
    }

    async function saveUserProfile() {
      setUserSaving(true);
      try {
        const body = new FormData();
        body.append("work_id", userWorkId);
        const response = await fetch("/api/settings/user-profile", { method: "POST", body });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          message.error("保存工号失败");
          return;
        }
        message.success("已保存工号");
        window.location.href = "/?refresh=" + Date.now() + "#settings";
      } catch {
        message.error("保存工号失败");
      } finally {
        setUserSaving(false);
      }
    }

    async function saveRagLlm() {
      setLlmSaving(true);
      try {
        const body = new FormData();
        body.append("provider", llmProvider);
        body.append("base_url", llmBaseUrl);
        body.append("model", llmModel);
        body.append("api_key", document.getElementById("rag-llm-api-key")?.value || "");
        body.append("enabled", llmEnabled ? "true" : "false");
        body.append("clear_key", llmClearKey ? "true" : "false");
        const response = await fetch("/api/settings/rag-llm", { method: "POST", body });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          message.error("保存大模型配置失败");
          return;
        }
        message.success("已保存知识库大模型配置");
        const input = document.getElementById("rag-llm-api-key");
        if (input) input.value = "";
        setLlmClearKey(false);
        refreshStatus(() => true);
      } catch {
        message.error("保存大模型配置失败");
      } finally {
        setLlmSaving(false);
      }
    }

    async function saveImap() {
      setMailSaving(true);
      try {
        const body = new FormData();
        body.append("host", imapHost);
        body.append("port", imapPort);
        body.append("username", imapUsername);
        body.append("password", document.getElementById("imap-password")?.value || "");
        body.append("mailbox", imapMailbox);
        body.append("enabled", imapEnabled ? "true" : "false");
        body.append("mark_seen", imapMarkSeen ? "true" : "false");
        body.append("clear_password", imapClearPassword ? "true" : "false");
        const response = await fetch("/api/settings/imap", { method: "POST", body });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          message.error("保存邮箱配置失败");
          return;
        }
        message.success("已保存邮箱收票配置");
        const input = document.getElementById("imap-password");
        if (input) input.value = "";
        setImapClearPassword(false);
        refreshStatus(() => true);
      } catch {
        message.error("保存邮箱配置失败");
      } finally {
        setMailSaving(false);
      }
    }

    const ragLlm = (status && status.rag_llm) || { ready: false, has_api_key: false, provider_label: "未配置", model: "" };
    const settingsUser = (status && status.user) || { display_name: "未绑定工号", work_id: "" };
    const imap = (status && status.imap) || { configured: false, mailbox: "INBOX", processed_count: 0 };
    const kb = (status && status.knowledge_base) || { index_exists: false, documents_exists: false, index_size_bytes: 0 };
    const playwright = (status && status.playwright) || { shu_adapter_configured: false, shu_adapter_message: "" };
    const financeObservation = playwright.shu_observation || {};
    const kbReport = (knowledgeStatus && knowledgeStatus.corpus_report) || {};
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
      e("div", { className: "page-head" }, e("div", null, e(Title, { level: 2 }, "设置"), e(Text, { type: "secondary" }, "管理学校登录、知识库问答和邮箱收票。密钥不会显示在页面上。"))),
      error ? e(Alert, { className: "settings-inline-alert", type: "error", showIcon: true, message: error }) : null,
      !status ? e(Alert, { className: "settings-inline-alert", type: "info", showIcon: true, message: "正在读取本地配置状态" }) : null,
      e(
        Row,
        { gutter: [16, 16], align: "top" },
        e(
          Col,
          { xs: 24, lg: 12 },
          e(
            Card,
            { className: "work-card settings-school-card", title: "学校账号" },
            e(
              Space,
              { direction: "vertical", size: 14, className: "full" },
              e(
                "div",
                { className: "settings-card-top" },
                e(
                  "div",
                  { className: "settings-status-line" },
                  (() => {
                    const label = authStatusLabel(shuAuth);
                    return e(Tag, { color: label[0] }, label[1]);
                  })(),
                  e(Text, { type: "secondary" }, shuAuth && shuAuth.status === "ready" ? "财务系统业务会话可用" : "扫码后建立本机会话")
                ),
                shuAuth && shuAuth.checked_at
                  ? e(Text, { type: "secondary", className: "settings-card-time" }, `上次检测 ${formatSettingsTime(shuAuth.checked_at)}`)
                  : null
              ),
              e(Text, { type: "secondary", className: "settings-desc" }, "用于进入上海大学财务系统。扫码、验证码和最终提交仍由本人完成。"),
              e(
                "div",
                { className: "settings-account-grid" },
                e(
                  "div",
                  { className: "settings-field-panel" },
                  e("div", { className: "settings-field-label" }, "工号"),
                  e(Input, {
                    value: userWorkId,
                    onChange: (event) => setUserWorkId(event.target.value),
                    placeholder: "输入本人学校工号",
                  })
                ),
                e(
                  "div",
                  { className: "settings-field-panel" },
                  e("div", { className: "settings-field-label" }, "当前显示"),
                  e("div", { className: "settings-account-preview" }, settingsUser.display_name || "未绑定工号")
                )
              ),
              e(
                Space,
                { wrap: true, className: "settings-button-row" },
                e(
                  Button,
                  {
                    icon: icon(LoginOutlined),
                    loading: authLaunching || Boolean(shuAuth && shuAuth.login_running),
                    onClick: launchShuAuth,
                  },
                  shuAuth && shuAuth.login_running ? "登录窗口已打开" : "打开扫码登录"
                ),
                e(Button, { loading: authChecking, disabled: Boolean(shuAuth && shuAuth.login_running), onClick: checkShuAuth }, "实时检查"),
                e(Button, { type: "primary", loading: userSaving, onClick: saveUserProfile }, "保存工号"),
                e(Button, { onClick: () => window.dispatchEvent(new Event("open-user-agreement")) }, "用户须知")
              ),
              shuAuth && shuAuth.message
                ? e(Alert, {
                    className: "settings-session-alert",
                    type: shuAuth.status === "ready" ? "success" : "info",
                    showIcon: true,
                    message: shuAuth.message,
                  })
                : null
            )
          )
        ),
        e(
          Col,
          { xs: 24, lg: 12 },
          e(
            Card,
            { className: "work-card", title: "学校系统代填" },
            e(
              Space,
              { direction: "vertical", size: 12, className: "full" },
              e(
                Space,
                { wrap: true },
                e(Tag, { color: playwright.shu_adapter_configured ? "green" : "gold" }, playwright.shu_adapter_configured ? "真实适配已配置" : "真实适配待配置"),
                e(Tag, { color: playwright.mock_adapter_exists ? "blue" : "default" }, playwright.mock_adapter_exists ? "本地演示可用" : "本地演示缺失")
              ),
              e(Text, { type: "secondary" }, "材料、项目、余额和一次统一登录都就绪后，Agent 才会进入学校财务系统代填草稿。"),
              e(Alert, {
                type: playwright.shu_adapter_configured ? "success" : "info",
                showIcon: true,
                message: playwright.shu_adapter_message || "真实学校系统字段适配尚未配置，只能生成代填计划和本地演示。",
              }),
              e(
                Space,
                { wrap: true },
                e(
                  Button,
                  {
                    icon: icon(SearchOutlined),
                    loading: financeObserving,
                    disabled: Boolean(shuAuth && shuAuth.login_running),
                    onClick: observeFinanceForm,
                  },
                  "观察学校表单"
                ),
                financeObservation.adapter_draft_exists
                  ? e(Button, { href: "/playwright-output/shu_finance_adapter_draft.json" }, "查看适配草稿")
                  : null
              ),
              financeObservation.report_exists
                ? e(Text, { type: "secondary" }, `最近观察：${financeObservation.message || financeObservation.status || "未识别"}；字段 ${financeObservation.field_count || 0} 个，人工暂停点 ${financeObservation.manual_action_count || 0} 个。`)
                : e(Text, { type: "secondary" }, "登录后观察一次学校表单，系统会生成真实字段适配草稿。")
            )
          )
        ),
        e(
          Col,
          { xs: 24, lg: 12 },
          e(
            Card,
            { className: "work-card", title: "邮箱收票" },
            e(
              Space,
              { direction: "vertical", size: 12, className: "full" },
              e(
                Space,
                { wrap: true },
                e(Tag, { color: imap.configured ? "green" : "gold" }, imap.configured ? "已配置" : "未配置"),
                e(Text, { type: "secondary" }, `已处理 ${imap.processed_count || 0} 封`)
              ),
              e(Text, { type: "secondary" }, imap.configured ? `从 ${imap.mailbox || "INBOX"} 拉取发票邮件和附件。` : "配置邮箱后，可以一键整理发票邮件。"),
              e(
                Row,
                { gutter: [12, 12] },
                e(
                  Col,
                  { xs: 24, md: 14 },
                  e(Text, { strong: true }, "IMAP 服务器"),
                  e(Input, { value: imapHost, onChange: (event) => setImapHost(event.target.value), placeholder: "例如 imap.exmail.qq.com" })
                ),
                e(
                  Col,
                  { xs: 24, md: 10 },
                  e(Text, { strong: true }, "端口"),
                  e(Input, { value: imapPort, onChange: (event) => setImapPort(event.target.value), placeholder: "993" })
                ),
                e(
                  Col,
                  { xs: 24 },
                  e(Text, { strong: true }, "邮箱账号"),
                  e(Input, { value: imapUsername, onChange: (event) => setImapUsername(event.target.value), placeholder: "name@example.com" })
                ),
                e(
                  Col,
                  { xs: 24 },
                  e(Text, { strong: true }, "授权码 / 密码"),
                  e(Input.Password, { id: "imap-password", placeholder: imap.has_password ? "已保存授权码；留空则不变" : "输入邮箱 IMAP 授权码或密码" })
                ),
                e(
                  Col,
                  { xs: 24, md: 12 },
                  e(Text, { strong: true }, "邮箱文件夹"),
                  e(Input, { value: imapMailbox, onChange: (event) => setImapMailbox(event.target.value), placeholder: "INBOX" })
                )
              ),
              e(
                Space,
                { wrap: true },
                e(Space, null, e(Text, null, "启用"), e(Switch, { checked: imapEnabled, onChange: setImapEnabled })),
                e(Space, null, e(Text, null, "拉取后标记已读"), e(Switch, { checked: imapMarkSeen, onChange: setImapMarkSeen })),
                imap.has_password
                  ? e(Space, null, e(Text, null, "清除授权码"), e(Switch, { checked: imapClearPassword, onChange: setImapClearPassword }))
                  : null,
                e(Button, { type: "primary", loading: mailSaving, onClick: saveImap }, "保存配置")
              ),
              e(
                Space,
                { wrap: true },
                e(
                  Button,
                  {
                    icon: icon(SyncOutlined),
                    loading: mailPolling,
                    disabled: !imap.configured,
                    onClick: pollMailbox,
                  },
                  "立即拉取邮箱"
                )
              ),
              mailPollResult
                ? e(Alert, {
                    type: mailPollResult.ok ? "success" : "warning",
                    showIcon: true,
                    message: mailPollResult.ok ? `完成：${mailPollResult.count || 0} 封新邮件` : "邮箱拉取未完成",
                    description: mailPollResult.ok
                      ? (mailPollResult.count || 0) > 0
                        ? e(Button, { href: "/?refresh=" + Date.now() + "#waiting", type: "primary" }, "查看等待报销")
                        : "没有新的未读发票邮件。"
                      : mailPollResult.error || "请检查本机邮箱配置。",
                  })
                : null
            )
          )
        ),
        e(
          Col,
          { xs: 24, lg: 12 },
          e(
            Card,
            { className: "work-card", title: "知识库问答" },
            e(
              Space,
              { direction: "vertical", size: 12, className: "full" },
              e(
                Space,
                { wrap: true },
                e(Tag, { color: ragLlm && ragLlm.ready ? "green" : "gold" }, ragLlm && ragLlm.ready ? "已启用" : "未启用"),
                e(Text, { type: "secondary" }, ragLlm.model ? `${ragLlm.provider_label} · ${ragLlm.model}` : ragLlm.provider_label)
              ),
              e(Alert, {
                type: ragLlm && ragLlm.ready ? "success" : "info",
                showIcon: true,
                message: ragLlm && ragLlm.ready ? "可以生成带引用的回答" : "未启用时只返回检索片段",
              }),
              e(
                Row,
                { gutter: [12, 12] },
                e(
                  Col,
                  { xs: 24, md: 12 },
                  e(Text, { strong: true }, "服务商"),
                  e(Select, {
                    value: llmProvider,
                    className: "full",
                    onChange: (value) => {
                      setLlmProvider(value);
                      setLlmBaseUrl(llmDefaults[value].base_url);
                      setLlmModel(llmDefaults[value].model);
                    },
                    options: [
                      { value: "deepseek", label: "DeepSeek" },
                      { value: "doubao", label: "豆包/火山方舟" },
                      { value: "custom", label: "自定义接口" },
                    ],
                  })
                ),
                e(
                  Col,
                  { xs: 24, md: 12 },
                  e(Text, { strong: true }, "模型"),
                  llmProvider === "deepseek"
                    ? e(Select, { value: llmModel || "deepseek-v4-pro", className: "full", onChange: setLlmModel, options: DEEPSEEK_MODEL_OPTIONS })
                    : e(Input, { value: llmModel, onChange: (event) => setLlmModel(event.target.value), placeholder: llmProvider === "doubao" ? "ep-xxxxxxxx" : "输入模型名" })
                ),
                llmProvider === "custom"
                  ? e(
                      Col,
                      { xs: 24 },
                      e(Text, { strong: true }, "接口地址"),
                      e(Input, { value: llmBaseUrl, onChange: (event) => setLlmBaseUrl(event.target.value), placeholder: "https://api.example.com/v1" })
                    )
                  : null
              ),
              e(Input.Password, { id: "rag-llm-api-key", placeholder: ragLlm && ragLlm.has_api_key ? "已保存密钥；留空则不变" : "输入 API Key" }),
              e(
                Space,
                { wrap: true },
                e(Space, null, e(Text, null, "启用"), e(Switch, { checked: llmEnabled, onChange: setLlmEnabled })),
                ragLlm && ragLlm.has_api_key
                  ? e(Space, null, e(Text, null, "清除密钥"), e(Switch, { checked: llmClearKey, onChange: setLlmClearKey }))
                  : null,
                e(Button, { type: "primary", loading: llmSaving, onClick: saveRagLlm }, "保存")
              )
            )
          )
        ),
        e(
          Col,
          { xs: 24, lg: 12 },
          e(
            Card,
            { className: "work-card", title: "本地资料库" },
            e(
              Space,
              { direction: "vertical", size: 12, className: "full" },
              e(
                Space,
                { wrap: true },
                e(Tag, { color: kb.index_exists && kb.documents_exists ? "green" : "gold" }, kb.index_exists && kb.documents_exists ? "可用" : "缺失"),
                kb.index_exists ? e(Text, { type: "secondary" }, `${Math.round(kb.index_size_bytes / 1024 / 1024)} MB`) : null
              ),
              e(Text, { type: "secondary" }, "用于回答报销政策问题，来源是财务处网页和本地整理文档。"),
              knowledgeStatus
                ? e(Text, null, `已整理 ${kbReport.document_count || 0} 份文档，${knowledgeStatus.chunk_count || 0} 条片段。`)
                : e(Text, { type: "secondary" }, "正在读取资料库状态")
            )
          )
        )
      )
    );
  }

  function Workspace() {
    const [activeKey, setActiveKey] = React.useState(normalizeKey(window.location.hash));
    const [sidebarCollapsed, setSidebarCollapsed] = React.useState(() => localStorage.getItem("reimbursement.sidebar.collapsed") === "true");
    const [aboutOpen, setAboutOpen] = React.useState(() => {
      const params = new URLSearchParams(window.location.search);
      return params.get("about") === "1";
    });
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
      const next = normalizeKey(key);
      setActiveKey(next);
      if (window.location.hash !== "#" + next) {
        window.location.hash = next;
      }
    }

    async function launchAuthLogin() {
      try {
        const payload = await startShuAuthLogin();
        if (payload.started) {
          message.success("已打开扫码登录窗口");
        } else {
          message.info(payload.message || "扫码登录窗口已在运行");
        }
        selectKey("settings");
      } catch (authError) {
        message.error(authError.message || "启动扫码登录窗口失败");
        selectKey("settings");
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
          UserAgreementGate,
          null,
          e(
            Layout,
            { className: "antd-shell app-frame" },
            e(Sidebar, {
              activeKey,
              onSelect: selectKey,
              collapsed: sidebarCollapsed,
              onToggleCollapsed: toggleSidebar,
              onOpenAbout: () => setAboutOpen(true),
              onLaunchAuth: launchAuthLogin,
            }),
            e(
              Layout,
              { className: "main-layout" },
              e(Content, { className: "antd-content" }, views[activeKey] || views.home),
              e(
                Modal,
                {
                  title: null,
                  open: aboutOpen,
                  className: "about-modal",
                  width: 760,
                  centered: true,
                  footer: e(Button, { type: "primary", onClick: () => setAboutOpen(false) }, "关闭"),
                  onCancel: () => setAboutOpen(false),
                },
                e(AboutSoftwareSection)
              )
            )
          )
        )
      )
    );
  }

  createRoot(document.getElementById("root")).render(e(Workspace));
