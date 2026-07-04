import React from "react";
import { createRoot } from "react-dom/client";
import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  Checkbox,
  Col,
  ConfigProvider,
  Dropdown,
  Form,
  Input,
  Layout,
  Menu,
  Modal,
  Row,
  Space,
  Statistic,
  Table,
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
  FolderOpenOutlined,
  HomeOutlined,
  InfoCircleOutlined,
  LoginOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  UserOutlined,
} from "@ant-design/icons";
import "antd/dist/reset.css";

const e = React.createElement;
const App = AntdApp;
  const data = window.__PACKAGE_DATA__ || {};
  const pkg = data.package || {};
  const Dragger = Upload.Dragger;
  const { Content, Sider } = Layout;
  const { Title, Text, Paragraph } = Typography;
  const AGREEMENT_VERSION = "2026-06-30";
  const AGREEMENT_STORAGE_KEY = `shu-reimbursement-agent.agreement.${AGREEMENT_VERSION}`;
  const statusLabels = {
    collecting: ["default", "资料归集中"],
    needs_materials: ["red", "待补材料"],
    ready_for_review: ["blue", "待本人复核"],
    ready_for_school: ["geekblue", "等待代填"],
    submitted_by_user: ["gold", "已提交"],
    returned: ["orange", "已退回"],
    reimbursed: ["green", "已报销"],
  };
  const responsibilityConfirmations = [
    ["funding_project", "经费项目已经本人确认"],
    ["payment_account", "收款账号或对公账户已经本人确认"],
    ["invoice_truth", "票据和附件真实、合法、与业务相关"],
    ["no_auto_submit", "我知道 Agent 不会自动提交学校系统"],
    ["review_before_submit", "进入学校系统后提交前仍由本人最终复核"],
  ];
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

  function packageMissingCount(packageData) {
    return (packageData.checklist || []).filter((item) => item.status === "missing").length;
  }

  function icon(IconComponent) {
    return e(IconComponent);
  }

  async function startShuAuthLogin() {
    const response = await fetch("/api/shu-auth/login", { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "启动扫码登录窗口失败");
    }
    return payload;
  }

  function authTone(status) {
    if (status === "ready") return "ready";
    if (status === "needs_scan" || status === "needs_renew") return "warn";
    if (status === "error") return "error";
    return "idle";
  }

  function authLabel(user) {
    if (user.auth_status === "ready") return "已连接";
    if (user.auth_status === "needs_scan") return "需要扫码";
    if (user.auth_status === "needs_renew") return "待续登";
    if (user.auth_status === "error") return "检查失败";
    return user.subtitle || "本机模式";
  }

  function Sidebar({ collapsed, onToggleCollapsed }) {
    const selectedKey = packageMissingCount(pkg) > 0 ? "collection" : "waiting";
    const user = data.user || {};
    const accountName = user.display_name || "未绑定工号";
    const avatarTone = authTone(user.auth_status);
    const statusLabel = authLabel(user);
    const items = [
      { key: "home", icon: icon(HomeOutlined), label: "报销助手" },
      { key: "knowledge", icon: icon(DatabaseOutlined), label: "报销知识" },
      { key: "waiting", icon: icon(ClockCircleOutlined), label: "待办报销" },
      { key: "collection", icon: icon(FolderOpenOutlined), label: "资料归集" },
      { key: "reimbursed", icon: icon(CheckCircleOutlined), label: "报销记录" },
    ];
    const userMenuItems = [
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
            statusLabel
          )
        ),
        disabled: true,
      },
      { type: "divider" },
      { key: "auth", icon: icon(LoginOutlined), label: "扫码登录" },
      { key: "settings", icon: icon(SettingOutlined), label: "系统设置" },
      { key: "about", icon: icon(InfoCircleOutlined), label: "说明" },
    ];
    const menuProps = {
      items: userMenuItems,
      onClick: ({ key }) => {
        if (key === "about") window.location.href = "/?about=1#home";
        else window.location.href = "/#" + key;
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
        selectedKeys: [selectedKey],
        items,
        onClick: ({ key }) => {
          window.location.href = "/#" + key;
        },
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
            menu: menuProps,
          },
          e(
            "button",
            {
              className: `sidebar-user sidebar-user--${avatarTone}`,
              type: "button",
              title: collapsed ? accountName : undefined,
            },
            e("span", { className: "sidebar-user-avatar" }, e(UserOutlined)),
            !collapsed &&
              e(
                "span",
                { className: "sidebar-user-meta" },
                e("span", { className: "sidebar-user-name" }, accountName),
                e(
                  "span",
                  { className: "sidebar-user-status" },
                  e("i", { className: `sidebar-user-status-dot sidebar-user-status-dot--${avatarTone}` }),
                  statusLabel
                )
              ),
            !collapsed && e("span", { className: "sidebar-user-chevron" }, "⌃")
          )
        )
      )
    );
  }

  function statusTag(status) {
    const map = {
      ready: ["green", "已就绪"],
      missing: ["red", "缺材料"],
      optional: ["gold", "可选"],
    };
    const [color, label] = map[status] || ["default", status || "未知"];
    return e(Tag, { color }, label);
  }

  function workflowTag(status) {
    const [color, label] = statusLabels[status] || ["default", status || "未知状态"];
    return e(Tag, { color }, label);
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
    const [checked, setChecked] = React.useState(false);
    function confirmAgreement() {
      localStorage.setItem(AGREEMENT_STORAGE_KEY, "accepted");
      setAccepted(true);
      message.success("已确认用户协议和用户须知");
    }
    return e(
      React.Fragment,
      null,
      children,
      e(
        Modal,
        {
          title: "用户协议与用户须知",
          open: !accepted,
          centered: true,
          width: 760,
          closable: false,
          maskClosable: false,
          keyboard: false,
          footer: e(
            Space,
            { className: "agreement-footer" },
            e(Checkbox, { checked, onChange: (event) => setChecked(event.target.checked) }, "我已阅读并同意以上用户协议和用户须知"),
            e(Button, { type: "primary", disabled: !checked, onClick: confirmAgreement }, "同意并进入")
          ),
        },
        e(AgreementContent)
      )
    );
  }

  function StatusPanel({ missing }) {
    const [submitting, setSubmitting] = React.useState("");
    const [confirmedItems, setConfirmedItems] = React.useState([]);
    const current = pkg.workflow_status || (missing ? "needs_materials" : "ready_for_review");
    const events = data.status_events || [];
    const readyConfirmDone = confirmedItems.length === responsibilityConfirmations.length;
    async function updateStatus(status, note) {
      const body = new FormData();
      body.append("status", status);
      body.append("note", note || "");
      if (status === "ready_for_school") {
        confirmedItems.forEach((item) => body.append("confirm_items", item));
      }
      setSubmitting(status);
      try {
        const response = await fetch(`/packages/${encodeURIComponent(data.package_id)}/status`, { method: "POST", body, redirect: "follow" });
        window.location.href = response.url || window.location.href;
      } catch (error) {
        message.error("更新状态失败");
        setSubmitting("");
      }
    }
    const actions = [
      ["ready_for_review", "标记待复核", "本人需要继续核对材料"],
      ["ready_for_school", "确认可代填", "本人已确认材料完整，准备进入上海大学财务系统"],
      ["submitted_by_user", "标记已提交", "本人已在上海大学财务系统提交"],
      ["returned", "标记已退回", "上海大学财务系统已退回，等待补材料或诊断"],
      ["reimbursed", "标记已报销", "本人确认学校系统已报销或已支付"],
    ];
    return e(
      Card,
      { className: "work-card", title: "报销状态" },
      e(
        Space,
        { direction: "vertical", size: 12, className: "full" },
        e(
          Space,
          { wrap: true },
          e(Text, { strong: true }, "当前状态"),
          workflowTag(current),
          pkg.workflow_updated_at ? e(Text, { type: "secondary" }, `更新于 ${pkg.workflow_updated_at}`) : null
        ),
        pkg.workflow_note ? e(Alert, { type: "info", showIcon: true, message: pkg.workflow_note }) : null,
        e(
          Space,
          { wrap: true },
          actions.map(([status, label, note]) =>
            e(
              Button,
              {
                key: status,
                type: status === "ready_for_school" ? "primary" : "default",
                loading: submitting === status,
                disabled: current === status || (status === "ready_for_school" && (missing > 0 || !readyConfirmDone)),
                onClick: () => updateStatus(status, note),
              },
              label
            )
          )
        ),
        missing > 0
          ? e(Alert, { type: "warning", showIcon: true, message: "材料未齐时不能确认可代填", description: "先补齐必需材料，再进入学校财务系统辅助录入。" })
          : null,
        current !== "ready_for_school" && current !== "reimbursed"
          ? e(
              "div",
              { className: "responsibility-confirm-box" },
              e(Text, { strong: true }, "确认可代填前必须逐项确认"),
              e(Checkbox.Group, {
                className: "responsibility-confirm-list",
                value: confirmedItems,
                options: responsibilityConfirmations.map(([value, label]) => ({ value, label })),
                onChange: setConfirmedItems,
              })
            )
          : null,
        events.length
          ? e(
              "div",
              { className: "status-history" },
              events.slice(0, 5).map((event, index) =>
                e(
                  "div",
                  { key: index, className: "status-history-row" },
                  workflowTag(event.new_status),
                  e(Text, { type: "secondary" }, event.note || "状态更新"),
                  e(Text, { type: "secondary" }, event.created_at)
                )
              )
            )
          : null
      )
    );
  }

  function FillAgentPanel({ missing }) {
    const current = pkg.workflow_status || (missing ? "needs_materials" : "ready_for_review");
    const canRun = current === "ready_for_school" && missing === 0;
    const report = data.fill_report;
    const schoolGate = data.school_fill_gate || {};
    const schoolBlockers = (schoolGate.blockers || []).map((item) => item.message || item).filter(Boolean);
    const canRunSchool = Boolean(schoolGate.can_start);
    const schoolReport = data.school_fill_report;
    const filledEntries = report ? Object.entries(report.filled || {}) : [];
    return e(
      Card,
      { className: "work-card", title: "受控代填 Agent" },
      e(
        Space,
        { direction: "vertical", size: 12, className: "full" },
        e(Alert, {
          type: canRunSchool ? "info" : "warning",
          showIcon: true,
          message: canRunSchool ? "可以启动学校系统代填" : "学校系统代填还未就绪",
          description: canRunSchool
            ? "Agent 会复用第一次统一登录后的专用浏览器会话，进入学校日常报销页面填写草稿，并在提交前停下。"
            : schoolBlockers.length
              ? `当前还差：${schoolBlockers.join("；")}`
              : "需要材料、项目、余额、登录态和学校字段适配都就绪后才能启动。",
        }),
        e(
          "form",
          { action: data.school_fill_url, method: "post" },
          e(Button, { type: "primary", htmlType: "submit", disabled: !canRunSchool }, "启动学校系统代填")
        ),
        schoolReport
          ? e(Alert, {
              type: schoolReport.ok ? "success" : schoolReport.status === "error" ? "error" : "warning",
              showIcon: true,
              message: schoolReport.ok ? "最近一次学校代填已生成草稿" : "最近一次学校代填未启动",
              description: schoolReport.message || "可以查看报告了解具体门禁原因。",
            })
          : null,
        schoolReport
          ? e(
              Space,
              { wrap: true },
              e(Button, { href: data.school_fill_report_url }, "查看学校代填报告"),
              schoolReport.ok ? e(Button, { href: data.school_fill_screenshot_url }, "查看学校代填截图") : null
            )
          : null,
        e(Alert, {
          type: canRun ? "info" : "warning",
          showIcon: true,
          message: canRun ? "可以启动本地演示" : "本地演示启动前需要本人确认",
          description: canRun
            ? "本地演示会打开模拟上海大学财务系统，按代填计划填写草稿，并验证提交按钮仍被拦截。"
            : "必须先补齐必需材料，并在报销状态中点击“确认可代填”。真实系统登录、验证码、经费项目、账号和提交动作都必须人工处理。",
        }),
        e(
          "form",
          { action: data.fill_demo_url, method: "post" },
          e(Button, { type: "primary", htmlType: "submit", disabled: !canRun }, "启动本地代填演示")
        ),
        report
          ? e(
              Alert,
              {
                type: report.verified_stop_before_submission ? "success" : "error",
                showIcon: true,
                message: report.verified_stop_before_submission ? "最近一次演示已停在提交前" : "最近一次演示未通过提交保护",
                description: `已填字段 ${Object.keys(report.filled || {}).length} 项，附件 ${report.attachment_count || 0} 份，暂停点 ${report.pause_count || 0} 个。`,
              }
            )
          : null,
        report
          ? e(
              Space,
              { wrap: true },
              e(Button, { href: data.fill_report_url }, "查看报告 JSON"),
              e(Button, { href: data.fill_screenshot_url }, "查看截图")
            )
          : null,
        report
          ? e(
              "div",
              { className: "fill-evidence" },
              e(
                "div",
                { className: "fill-evidence-block" },
                e(Text, { strong: true }, "字段快照"),
                filledEntries.length
                  ? e(
                      "dl",
                      { className: "field-snapshot" },
                      filledEntries.map(([key, value]) =>
                        e(
                          React.Fragment,
                          { key },
                          e("dt", null, key),
                          e("dd", null, String(value || ""))
                        )
                      )
                    )
                  : e(Text, { type: "secondary" }, "没有记录到已填字段")
              ),
              e(
                "div",
                { className: "fill-evidence-block" },
                e(Text, { strong: true }, "操作日志"),
                e(
                  Space,
                  { direction: "vertical", size: 6, className: "full" },
                  e(Text, null, `适配器 ${report.adapter_id || "unknown"}`),
                  e(Text, null, `附件 ${report.attachment_count || 0} 份`),
                  e(Text, null, `暂停确认点 ${report.pause_count || 0} 个`),
                  e(Text, null, report.verified_stop_before_submission ? "已验证停在提交前" : "未验证提交保护"),
                  e(Text, { type: "secondary" }, report.agent_boundary || "提交动作必须本人确认")
                )
              ),
              e(
                "div",
                { className: "fill-evidence-block fill-evidence-image" },
                e(Text, { strong: true }, "截图证据"),
                e("a", { href: data.fill_screenshot_url, target: "_blank", rel: "noreferrer" }, e("img", { src: data.fill_screenshot_url, alt: "代填演示截图" }))
              )
            )
          : null
      )
    );
  }

  function formatAmount(value, currency = "CNY") {
    return typeof value === "number" ? `${currency} ${value.toFixed(2)}` : "待识别";
  }

  function FillPlanPanel() {
    const [authLaunching, setAuthLaunching] = React.useState(false);
    const plan = data.playwright_plan || {};
    const fill = plan.school_fill || {};
    const readiness = fill.readiness || {};
    const project = fill.project || {};
    const invoice = fill.invoice_state || {};
    const lines = fill.expense_lines || [];
    const blockers = readiness.blockers || [];
    const user = data.user || {};
    async function openSchoolLogin() {
      setAuthLaunching(true);
      try {
        const payload = await startShuAuthLogin();
        if (payload.started) {
          message.success(payload.message || "已打开统一登录窗口");
        } else {
          message.info(payload.message || "登录窗口已在运行");
        }
      } catch (error) {
        message.error(error && error.message ? error.message : "启动统一登录窗口失败");
      } finally {
        setAuthLaunching(false);
      }
    }
    const columns = [
      { title: "费用类型", dataIndex: "school_fee_item", width: 120 },
      { title: "金额", dataIndex: "amount", width: 130, render: (value, record) => formatAmount(value, record.currency || "CNY") },
      { title: "商户", dataIndex: "merchant", ellipsis: true },
      { title: "日期", dataIndex: "occurred_on", width: 120 },
      { title: "凭据", dataIndex: "source_file_name", ellipsis: true },
    ];
    return e(
      Card,
      { className: "work-card", title: "学校代填计划" },
      plan.package_id
        ? e(
            Space,
            { direction: "vertical", size: 12, className: "full" },
            e(Alert, {
              type: readiness.can_start_school_fill ? "info" : "warning",
              showIcon: true,
              message: readiness.can_start_school_fill ? "材料和项目已具备代填条件" : "还不能进入学校系统代填",
              description: blockers.length ? `当前还差：${blockers.join("、")}` : "进入学校系统后仍会在提交前停下，等待本人复核。",
            }),
            e(
              Space,
              { wrap: true },
              e(Tag, { color: invoice.status === "ready" ? "green" : "red" }, invoice.status === "ready" ? "发票已就绪" : "发票待补"),
              e(Tag, { color: project.status === "confirmed_by_user" ? "green" : "gold" }, project.status === "confirmed_by_user" ? `项目 ${project.name_or_code || "已确认"}` : "项目待确认"),
              e(Tag, { color: project.balance_status === "confirmed_sufficient" ? "green" : "gold" }, project.balance_status === "confirmed_sufficient" ? "余额已确认" : "余额待确认"),
              e(Tag, { color: user.auth_status === "ready" ? "green" : "gold" }, user.auth_status === "ready" ? "学校登录已连接" : "学校登录待续登"),
              fill.amount_total ? e(Tag, { color: "blue" }, `合计 ${formatAmount(fill.amount_total, fill.currency || "CNY")}`) : null
            ),
            lines.length
              ? e(Table, { rowKey: "source_document_id", size: "small", pagination: false, columns, dataSource: lines })
              : e(Text, { type: "secondary" }, "暂无可代填费用明细。"),
            invoice.status === "missing" && data.invoice_request_exists
              ? e(
                  Space,
                  { wrap: true },
                  e(Button, { type: "primary", href: data.invoice_request_url }, "查看索票说明"),
                  e(Text, { type: "secondary" }, "先补正式发票，拿到后直接发回聊天。")
                )
              : null,
            project.status !== "confirmed_by_user" || project.balance_status !== "confirmed_sufficient"
              ? e(
                  "form",
                  { action: `/packages/${encodeURIComponent(data.package_id)}/project-confirmation`, method: "post" },
                  e(
                    Space,
                    { wrap: true },
                    e(
                      "select",
                      { name: "fund_context", defaultValue: "horizontal_research", "aria-label": "经费类型" },
                      e("option", { value: "horizontal_research" }, "横向科研经费"),
                      e("option", { value: "maintenance_meal" }, "维持性经费工作用餐")
                    ),
                    e(Input, { name: "project", placeholder: "项目号或项目名称", required: true, style: { width: 220 } }),
                    e(
                      "select",
                      { name: "balance_status", defaultValue: "sufficient", "aria-label": "余额状态" },
                      e("option", { value: "sufficient" }, "余额足够"),
                      e("option", { value: "insufficient" }, "余额不足")
                    ),
                    e(Button, { type: "primary", htmlType: "submit" }, "记录项目与余额")
                  )
                )
              : null,
            fill.official_reception
              ? e(Alert, { type: "info", showIcon: true, message: "餐饮接待规则判断", description: fill.official_reception.known_rule_hint })
              : null,
            e(
              Space,
              { wrap: true },
              user.auth_status === "ready"
                ? null
                : e(Button, { icon: icon(LoginOutlined), loading: authLaunching, onClick: openSchoolLogin }, "打开统一登录"),
              e(Button, { href: data.playwright_plan_url }, "查看完整计划 JSON")
            )
          )
        : e(Text, { type: "secondary" }, "尚未生成代填计划。")
    );
  }

  function fieldTags(fields) {
    const items = [];
    if (fields.buyer_name) items.push(["购买方", fields.buyer_name, "blue"]);
    if (fields.seller_name) items.push(["销售方", fields.seller_name, "cyan"]);
    if (fields.item_name) items.push(["项目", fields.item_name, "geekblue"]);
    if (fields.invoice_no) items.push(["发票号", fields.invoice_no, "purple"]);
    if (fields.amount_total) items.push(["金额", `${fields.currency || "CNY"} ${fields.amount_total}`, "green"]);
    if (fields.invoice_date) items.push(["日期", fields.invoice_date, "default"]);
    if (fields.title_valid === true) items.push(["抬头", "有效", "green"]);
    if (fields.title_valid === false) items.push(["抬头", "待处理", "red"]);
    return e(
      Space,
      { size: [4, 6], wrap: true },
      items.length
        ? items.map(([label, value, color]) => e(Tag, { color, key: label + value }, `${label} ${value}`))
        : e(Text, { type: "secondary" }, "未识别关键字段")
    );
  }

  function MissingChecklist() {
    const columns = [
      {
        title: "检查项",
        dataIndex: "name",
        render: (value, record) =>
          e(Space, { direction: "vertical", size: 2 }, e(Text, { strong: true }, value), e(Text, { type: "secondary" }, record.why || "")),
      },
      { title: "状态", dataIndex: "status", width: 110, render: statusTag },
      {
        title: "匹配材料",
        dataIndex: "matched_documents",
        width: 180,
        render: (items) => (items && items.length ? items.map((item) => e(Tag, { key: item }, item)) : e(Text, { type: "secondary" }, "-")),
      },
      {
        title: "依据",
        dataIndex: "evidence",
        width: 260,
        render: (evidence) =>
          evidence ? e("a", { href: evidence.url, target: "_blank", rel: "noreferrer" }, evidence.title) : e(Text, { type: "secondary" }, "-"),
      },
    ];
    return e(Card, { title: "缺漏检查", className: "work-card" }, e(Table, { rowKey: "id", columns, dataSource: pkg.checklist || [], pagination: false }));
  }

  function DocumentsTable() {
    const columns = [
      { title: "文件", dataIndex: "file_name", width: 240 },
      {
        title: "识别类型",
        dataIndex: "document_type",
        width: 140,
        render: (value) => e(Tag, { color: value === "invoice" ? "blue" : value === "payment_record" ? "green" : "default" }, value),
      },
      { title: "置信度", dataIndex: "confidence", width: 100 },
      { title: "关键字段", dataIndex: "extracted_fields", render: (fields) => fieldTags(fields || {}) },
    ];
    return e(Card, { title: "材料识别", className: "work-card" }, e(Table, { rowKey: "id", columns, dataSource: pkg.documents || [], pagination: false, scroll: { x: 860 } }));
  }

  function ReturnDiagnosisForm() {
    const [submitting, setSubmitting] = React.useState(false);
    async function submit(values) {
      const body = new FormData();
      body.append("reason", values.reason || "");
      setSubmitting(true);
      try {
        const response = await fetch(`/packages/${encodeURIComponent(data.package_id)}/return-diagnosis`, { method: "POST", body, redirect: "follow" });
        window.location.href = response.url || data.return_diagnosis_url;
      } catch (error) {
        message.error("生成退回诊断失败");
        setSubmitting(false);
      }
    }
    return e(
      Card,
      { title: "退回诊断", className: "work-card" },
      e(
        Space,
        { direction: "vertical", size: 12, className: "full" },
        e(
          Form,
          { layout: "vertical", onFinish: submit },
          e(
            Form.Item,
            { label: "财务系统退回意见", name: "reason", rules: [{ required: true, message: "请粘贴退回意见" }] },
            e(Input.TextArea, { rows: 4, placeholder: "例如：请补充公务卡支付记录，并上传包含品名、单价、数量的明细清单。" })
          ),
          e(Button, { type: "primary", htmlType: "submit", loading: submitting }, "生成退回诊断")
        ),
        data.return_diagnosis ? e(Button, { href: data.return_diagnosis_url }, "查看最近一次退回诊断") : null
      )
    );
  }

  function missingChecklistItems() {
    return (pkg.checklist || []).filter((item) => item.status === "missing");
  }

  function SupplementForm() {
    const [fileLists, setFileLists] = React.useState({});
    const [submitting, setSubmitting] = React.useState("");
    async function submit(values) {
      const fileList = fileLists[values.missing_item_id] || [];
      if (!fileList.length) {
        message.warning("请先选择补充材料");
        return;
      }
      const body = new FormData();
      body.append("note", values.note || "");
      body.append("missing_item_id", values.missing_item_id || "");
      body.append("missing_item_name", values.missing_item_name || "");
      fileList.forEach((file) => body.append("files", file.originFileObj || file));
      setSubmitting(values.missing_item_id || "supplement");
      try {
        const response = await fetch(`/packages/${encodeURIComponent(data.package_id)}/supplement`, { method: "POST", body, redirect: "follow" });
        window.location.href = response.url || window.location.href;
      } catch (error) {
        message.error("补充材料失败");
        setSubmitting("");
      }
    }
    const missingItems = missingChecklistItems();
    if (!missingItems.length) {
      return e(
        Card,
        { title: "待补材料", className: "work-card supplement-card" },
        e(Alert, {
          type: "success",
          showIcon: true,
          message: "当前没有必需材料缺漏",
          description: "系统已经把材料整理到可复核状态。你只需要核对票据真实性、经费项目和收款信息。",
        })
      );
    }
    return e(
      Card,
      { title: `待补材料 ${missingItems.length} 项`, className: "work-card supplement-card" },
      e(
        Space,
        { direction: "vertical", size: 14, className: "full" },
        e(Alert, {
          type: "warning",
          showIcon: true,
          message: "只需要按缺项补材料",
          description: "系统已经完成分类、清单检查和草稿生成。你不用重新整理，只要在下面对应缺项上传文件或写一句说明。",
        }),
        missingItems.map((item) =>
          e(
            "section",
            { key: item.id, className: "missing-supplement-item" },
            e(
              "div",
              { className: "missing-supplement-head" },
              e("div", null, e(Text, { strong: true }, item.name), item.why ? e(Text, { type: "secondary" }, item.why) : null),
              statusTag(item.status)
            ),
            item.evidence
              ? e(
                  "a",
                  { className: "missing-supplement-evidence", href: item.evidence.url, target: "_blank", rel: "noreferrer" },
                  item.evidence.title
                )
              : null,
            e(
              Form,
              { layout: "vertical", onFinish: submit, className: "missing-supplement-form" },
              e(Form.Item, { name: "missing_item_id", initialValue: item.id, hidden: true }, e(Input)),
              e(Form.Item, { name: "missing_item_name", initialValue: item.name, hidden: true }, e(Input)),
              e(Form.Item, { label: "补充说明", name: "note" }, e(Input.TextArea, { rows: 2, placeholder: `补充 ${item.name} 的说明，可留空` })),
              e(
                Form.Item,
                { label: "上传材料" },
                e(
                  Dragger,
                  {
                    multiple: true,
                    beforeUpload: () => false,
                    fileList: fileLists[item.id] || [],
                    onChange: ({ fileList: next }) => setFileLists((current) => ({ ...current, [item.id]: next })),
                  },
                  e("p", { className: "upload-symbol" }, "↑"),
                  e("p", { className: "ant-upload-text" }, `上传 ${item.name}`),
                  e("p", { className: "ant-upload-hint" }, "系统会自动合并到这个报销包，并重新检查缺漏。")
                )
              ),
              e(Button, { type: "primary", htmlType: "submit", loading: submitting === item.id }, "补充并重新检查")
            )
          )
        )
      )
    );
  }

  function WorkflowAlert({ missing }) {
    const current = pkg.workflow_status || (missing ? "needs_materials" : "ready_for_review");
    if (current === "returned") {
      return e(Alert, {
        className: "page-alert",
        type: "warning",
        showIcon: true,
        message: "上海大学财务系统已退回",
        description: "先查看退回诊断或粘贴退回意见，再补充材料并重新整理。",
      });
    }
    if (current === "submitted_by_user") {
      return e(Alert, {
        className: "page-alert",
        type: "info",
        showIcon: true,
        message: "已在上海大学财务系统提交",
        description: "等待学校预审、支付或回写结果。只有确认支付完成后才能标记已报销。",
      });
    }
    if (current === "reimbursed") {
      return e(Alert, {
        className: "page-alert",
        type: "success",
        showIcon: true,
        message: "已标记报销完成",
        description: "该事项只在已报销工作区展示，可继续保留材料和状态记录。",
      });
    }
    if (current === "ready_for_school") {
      return e(Alert, {
        className: "page-alert",
        type: "info",
        showIcon: true,
        message: "本人已确认可进入学校系统",
        description: "代填 Agent 只能辅助填写草稿，真实登录、验证码、经费项目和提交动作必须人工处理。",
      });
    }
    if (missing > 0) {
      return e(Alert, { className: "page-alert", type: "warning", showIcon: true, message: "提交前仍需补材料", description: `当前还有 ${missing} 项必需材料未就绪。` });
    }
    return e(Alert, { className: "page-alert", type: "success", showIcon: true, message: "材料已进入可复核状态", description: "仍需本人确认票据真实性、经费项目、收款账号和提交动作。" });
  }

  function PackagePage() {
    const missing = packageMissingCount(pkg);
    const ready = (pkg.checklist || []).filter((item) => item.status === "ready").length;
    const [sidebarCollapsed, setSidebarCollapsed] = React.useState(() => localStorage.getItem("reimbursement.sidebar.collapsed") === "true");
    function toggleSidebarCollapsed() {
      setSidebarCollapsed((current) => {
        const next = !current;
        localStorage.setItem("reimbursement.sidebar.collapsed", String(next));
        return next;
      });
    }
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
            e(Sidebar, { collapsed: sidebarCollapsed, onToggleCollapsed: toggleSidebarCollapsed }),
            e(
              Layout,
              { className: "main-layout" },
              e(
                Content,
                { className: "antd-content package-detail-content" },
            e(
              "div",
              { className: "page-head" },
              e(
                "div",
                null,
                e(Title, { level: 2 }, pkg.title),
                e(
                  Space,
                  { size: 8, wrap: true },
                  e(Text, { type: "secondary" }, `${pkg.reimbursement_type_name} · 推荐入口：${pkg.school_form_hint} · ${data.file_count} 份原始材料`),
                  workflowTag(pkg.workflow_status)
                )
              ),
              e(
                Space,
                { wrap: true },
                e(Button, { href: "/" }, "继续上传"),
                e(Button, { href: data.markdown_url }, "Markdown"),
                e(Button, { href: data.json_url }, "JSON"),
                e(Button, { href: data.playwright_plan_url }, "代填计划")
              )
            ),
            e(
              Row,
              { gutter: [16, 16], className: "metric-row" },
              e(Col, { xs: 24, md: 8 }, e(Card, null, e(Statistic, { title: "分类置信度", value: pkg.confidence }))),
              e(Col, { xs: 24, md: 8 }, e(Card, null, e(Statistic, { title: "已就绪检查项", value: ready, suffix: "项" }))),
              e(Col, { xs: 24, md: 8 }, e(Card, null, e(Statistic, { title: "待补缺漏", value: missing, suffix: "项" })))
            ),
            e(
              Card,
              { className: "work-card", title: "报销事由草稿" },
              e(Paragraph, { className: "reason-text" }, pkg.reason_draft)
            ),
            e(WorkflowAlert, { missing }),
            e(SupplementForm),
            e(StatusPanel, { missing }),
            e(FillPlanPanel),
            e(FillAgentPanel, { missing }),
            e(
              Card,
              { className: "work-card", title: "风险提示" },
              pkg.risk_flags && pkg.risk_flags.length
                ? e(Space, { direction: "vertical", className: "full" }, pkg.risk_flags.map((flag, index) => e(Alert, { key: index, type: "warning", showIcon: true, message: flag })))
                : e(Alert, { type: "success", showIcon: true, message: "暂无高优先级风险", description: "提交前仍需人工核对。" })
            ),
            e(
              Card,
              { className: "work-card", title: "提交前必须确认" },
              e(
                Space,
                { wrap: true },
                ["经费项目", "收款账号", "票据真实性", "提交预审", "提交审批"].map((item) => e(Tag, { key: item, color: "red" }, item))
              )
            ),
            e(Row, { gutter: [16, 16] }, e(Col, { xs: 24, lg: 12 }, e(ReturnDiagnosisForm))),
            e(MissingChecklist),
            e(DocumentsTable)
              )
            )
          )
        )
      )
    );
  }

  createRoot(document.getElementById("root")).render(e(PackagePage));
