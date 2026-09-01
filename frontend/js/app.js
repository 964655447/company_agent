/* 公司管理智能体 · 前端逻辑（与 contracts/openapi.yaml 对齐） */
"use strict";

const API = (location.protocol === "file:") ? "http://127.0.0.1:8000" : "";
const TOKEN_KEY = "cm_token", USER_KEY = "cm_user";

const $ = (sel) => document.querySelector(sel);
const state = { user: null, rosterEditing: null, attPeriod: "week", adminAttPeriod: "week",
                attMonth: "", adminAttMonth: "",
                reimbPeriod: "month", reimbMonth: "",
                salaryPeriod: "month", salaryMonth: "",
                assessPeriod: "month", assessMonth: "",
                adminReimbPeriod: "month", adminReimbMonth: "",
                adminSalaryPeriod: "month", adminSalaryMonth: "",
                adminAssessPeriod: "month", adminAssessMonth: "",
                floatConvId: null, chatConvId: null,
                adminAttRows: [], adminAttPage: 1, adminAttPageSize: 10 };

/* 转义 HTML 后保留换行，便于展示多行回答 */
function renderText(s) {
  return esc(s).replace(/\n/g, "<br>");
}

/* ---------------- 工具 ---------------- */
async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
  }
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok) {
    const msg = (data && data.detail) || `请求失败（${res.status}）`;
    if (res.status === 401) { logout(true); }
    throw new Error(msg);
  }
  return data;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const fmtTime = (iso) => (iso || "").slice(11, 16);
const fmtDT = (iso) => (iso || "").replace("T", " ").slice(0, 16);
const money = (n) => Number(n || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const REIMB_STATUS = {
  draft: ["草稿", "tag-gray"], submitted: ["待审批", "tag-warn"], approving: ["审批中", "tag-warn"],
  approved: ["已通过", "tag-ok"], rejected: ["已驳回", "tag-danger"],
};

function setMsg(el, text, cls) {
  el.textContent = text || "";
  el.className = el.className.replace(/ (ok|err|late)/g, "") + (cls ? " " + cls : "");
}

/* ---------------- Toast / 确认弹窗 / 加载态 ---------------- */
const ICONS = {
  ok: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
  err: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16v-4M12 8h.01"/><circle cx="12" cy="12" r="9"/></svg>',
};
function toast(msg, type = "info", ms = 2600) {
  const wrap = $("#toast-wrap");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = (ICONS[type] || ICONS.info) + `<span>${esc(msg)}</span>`;
  wrap.appendChild(el);
  setTimeout(() => {
    el.classList.add("toast-hide");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, ms);
}
let _modalResolve = null;
function confirmModal(text, title = "确认操作") {
  return new Promise((resolve) => {
    _modalResolve = resolve;
    $("#modal-title").textContent = title;
    $("#modal-text").textContent = text;
    $("#modal-backdrop").classList.add("show");
    document.body.classList.add("no-scroll");
  });
}
function closeModal(val) {
  $("#modal-backdrop").classList.remove("show");
  document.body.classList.remove("no-scroll");
  if (_modalResolve) { _modalResolve(val); _modalResolve = null; }
}

/* ---------------- 材料信息预览（表格内摘要） ---------------- */
function matPreview(raw) {
  if (!raw) return '<span class="muted">—</span>';
  let obj;
  try { obj = JSON.parse(raw); } catch (e) { return esc(raw.length > 20 ? raw.slice(0, 20) + "…" : raw); }
  const parts = [];
  if (obj.category) parts.push(`<span class="tag tag-purple mat-tag-sm">${esc(obj.category)}</span>`);
  if (obj.amount != null) parts.push(`<span class="mat-preview-amt">¥${Number(obj.amount).toLocaleString("zh-CN")}</span>`);
  if (obj.files && Array.isArray(obj.files) && obj.files.length) parts.push(`📎${obj.files.length}`);
  if (!parts.length) return '<span class="muted">有材料</span>';
  return `<span class="mat-preview-inline">${parts.join(" ")}</span>`;
}

/* ---------------- 材料信息查看弹窗 ---------------- */
function openMaterialModal(record) {
  const raw = record?.ocr_raw || "";
  const [statusTxt] = REIMB_STATUS[record.status] || [record.status];
  $("#material-modal-title").textContent = `报销单 #${record.id} · 材料信息`;
  $("#material-modal-sub").textContent = `提交于 ${fmtDT(record.submit_time)} · 状态：${statusTxt}`;

  const body = $("#material-modal-body");
  if (!raw) {
    body.innerHTML = `<div class="material-empty">该报销单暂无材料信息（ocr_raw 为空）</div>`;
    $("#material-modal-backdrop").classList.add("show");
    document.body.classList.add("no-scroll");
    return;
  }

  let obj;
  try { obj = JSON.parse(raw); } catch (e) {
    body.innerHTML = `<pre class="material-raw">${esc(raw)}</pre>`;
    $("#material-modal-backdrop").classList.add("show");
    document.body.classList.add("no-scroll");
    return;
  }

  // 结构化渲染
  const fields = [];
  if (obj.category) {
    fields.push(`<div class="mat-field"><span class="mat-label">报销类目</span><span class="mat-value"><span class="tag tag-purple">${esc(obj.category)}</span></span></div>`);
  }
  if (obj.amount != null) {
    fields.push(`<div class="mat-field"><span class="mat-label">报销金额</span><span class="mat-value mat-amount">¥${Number(obj.amount).toLocaleString("zh-CN", {minimumFractionDigits: 2})}</span></div>`);
  }
  if (obj.desc != null) {
    fields.push(`<div class="mat-field"><span class="mat-label">备注说明</span><span class="mat-value">${esc(obj.desc) || "<span class='mat-placeholder'>无</span>"}</span></div>`);
  }
  if (obj.files && Array.isArray(obj.files) && obj.files.length) {
    const fileItems = obj.files.map(f =>
      `<div class="mat-file"><span class="mat-file-ico">📎</span><span class="mat-file-name">${esc(f)}</span></div>`
    ).join("");
    fields.push(`<div class="mat-field mat-field-files"><span class="mat-label">附件材料</span><span class="mat-value"><div class="mat-file-list">${fileItems}</div></span></div>`);
  }

  body.innerHTML = `<div class="mat-card">${fields.join("")}</div>`;

  $("#material-modal-backdrop").classList.add("show");
  document.body.classList.add("no-scroll");
}
function closeMaterialModal() {
  $("#material-modal-backdrop").classList.remove("show");
  document.body.classList.remove("no-scroll");
}
$("#material-modal-close").addEventListener("click", closeMaterialModal);
$("#material-modal-ok").addEventListener("click", closeMaterialModal);
$("#material-modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "material-modal-backdrop") closeMaterialModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("#material-modal-backdrop").classList.contains("show")) closeMaterialModal();
});
$("#modal-cancel").addEventListener("click", () => closeModal(false));
$("#modal-ok").addEventListener("click", () => closeModal(true));
$("#modal-backdrop").addEventListener("click", (e) => { if (e.target.id === "modal-backdrop") closeModal(false); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $("#modal-backdrop").classList.contains("show")) closeModal(false); });

function loading(btn, on, label) {
  if (!btn) return;
  if (on) { btn._html = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> ${label || "处理中…"}`; }
  else { btn.disabled = false; btn.innerHTML = btn._html || btn.innerHTML; }
}

function emptyHTML(text, sub) {
  return `<div class="empty-state">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7"/><path d="M3 7l9 6 9-6"/><path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2"/></svg>
    <p>${esc(text)}</p>${sub ? `<p style="font-size:12px;opacity:.7">${esc(sub)}</p>` : ""}</div>`;
}

/* ---------------- 登录 / 登出 ---------------- */
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const empId = $("#login-empid").value.trim();
  const pwd = $("#login-pwd").value;
  setMsg($("#login-err"), "");
  if (!empId || !pwd) return setMsg($("#login-err"), "请输入工号和密码");
  try {
    const data = await api("/api/auth/login", { method: "POST", json: { emp_id: Number(empId), password: pwd } });
    localStorage.setItem(TOKEN_KEY, data.token);
    localStorage.setItem(USER_KEY, JSON.stringify(data));
    enterApp(data);
  } catch (err) {
    setMsg($("#login-err"), err.message);
  }
});

function logout(expired) {
  localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY);
  if (expired) toast("登录已过期，请重新登录", "err", 2000);
  setTimeout(() => location.reload(), expired ? 1500 : 0);
}$("#logout-btn").addEventListener("click", () => logout(false));

/* ---------------- 移动端抽屉 ---------------- */
$("#hamburger").addEventListener("click", () => {
  const open = $("#sidebar").classList.toggle("open");
  $("#sidebar-backdrop").classList.toggle("show", open);
  document.body.classList.toggle("no-scroll", open);
  $("#hamburger").setAttribute("aria-expanded", String(open));
});
$("#sidebar-backdrop").addEventListener("click", () => {
  $("#sidebar").classList.remove("open");
  $("#sidebar-backdrop").classList.remove("show");
  document.body.classList.remove("no-scroll");
  $("#hamburger").setAttribute("aria-expanded", "false");
});
$("#topbar-avatar").addEventListener("click", () => logout(false));

/* ---------------- 应用骨架 ---------------- */
const I = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const NAV_ITEMS = [
  { id: "checkin", label: "考勤打卡", ico: I('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'), role: "all" },
  { id: "reimb", label: "费用报销", ico: I('<path d="M5 3h14v18l-2.3-1.7L14.4 21 12 19.3 9.6 21l-2.3-1.7L5 21z"/><path d="M9 8h6M9 12h6"/>'), role: "all" },
  { id: "salary", label: "工资核算", ico: I('<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10h18"/><path d="M16.5 14.5h.01"/>'), role: "all" },
  { id: "assess", label: "进阶考核", ico: I('<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'), role: "all" },
  { id: "chat", label: "智能助手", ico: I('<path d="M12 2l2.4 5.9L20.5 10l-6.1 2.1L12 18l-2.4-5.9L3.5 10l6.1-2.1z"/><path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z"/>'), role: "all" },
  { id: "admin", label: "管理看板", ico: I('<path d="M3 3v18h18"/><path d="M8 17v-5M13 17V7M18 17v-9"/>'), role: "manager", group: "管理" },
  { id: "roster", label: "花名册维护", ico: I('<path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M21 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'), role: "manager" },
];

function enterApp(user) {
  state.user = user;
  $("#login-page").classList.add("hidden");
  $("#app-page").classList.remove("hidden");
  $("#float-bubble").classList.remove("hidden");
  $("#user-name").textContent = `${user.name}（${user.role === "manager" ? "管理者" : "员工"}）`;
  $("#user-dept").textContent = `${user.department} · ${user.position}`;
  $("#user-avatar").textContent = user.name.slice(0, 1);
  $("#topbar-avatar").textContent = user.name.slice(0, 1);

  const nav = $("#nav");
  nav.innerHTML = "";
  NAV_ITEMS.filter((n) => n.role === "all" || user.role === "manager").forEach((n) => {
    if (n.group) {
      const g = document.createElement("div");
      g.className = "nav-group-label"; g.textContent = n.group;
      nav.appendChild(g);
    }
    const b = document.createElement("button");
    b.className = "nav-item"; b.dataset.view = n.id;
    b.innerHTML = `<span class="nav-ico">${n.ico}</span> ${n.label}`;
    b.addEventListener("click", () => switchView(n.id));
    nav.appendChild(b);
  });
  switchView(user.role === "manager" ? "admin" : "checkin");
  loadAIStatus();
  startClock();
}

const VIEW_TITLE = { checkin: "考勤打卡", reimb: "费用报销", salary: "工资核算", assess: "进阶考核", chat: "智能助手", admin: "管理看板", roster: "花名册维护" };

function switchView(id) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  const el = $(`#view-${id}`);
  if (el) el.classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === id));
  $("#topbar-title").textContent = VIEW_TITLE[id] || "公司管理智能体";
  // 移动端：切换页面后收起抽屉
  $("#sidebar").classList.remove("open");
  $("#sidebar-backdrop").classList.remove("show");
  document.body.classList.remove("no-scroll");
  $("#hamburger").setAttribute("aria-expanded", "false");
  const loaders = {
    checkin: loadMyAttendance, reimb: loadMyReimb, salary: loadMySalary,
    assess: loadMyScores, admin: () => loadAdminTab(currentAdminTab()), roster: loadRoster,
  };
  if (loaders[id]) loaders[id]();
  if (id === "chat") { openChatView(); }
}

async function loadAIStatus() {
  try {
    const { dify } = await api("/api/chat/status");
    const el = $("#ai-status");
    const on = !!(dify && dify.enabled);
    el.className = "ai-status" + (on ? " on" : "");
    el.textContent = on
      ? "智能助手已接入"
      : "智能助手接入中";
  } catch (e) { /* ignore */ }
}

/* ---------------- 时钟 ---------------- */
let clockTimer = null;
function startClock() {
  if (clockTimer) clearInterval(clockTimer);
  const tick = () => {
    const d = new Date();
    $("#clock").textContent = d.toLocaleTimeString("zh-CN", { hour12: false });
    $("#clock-date").textContent = d.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" });
  };
  tick(); clockTimer = setInterval(tick, 1000);
}

/* ---------------- 考勤 ---------------- */
document.querySelectorAll("[data-checkin]").forEach((btn) =>
  btn.addEventListener("click", async () => {
    const msgEl = $("#checkin-msg");
    setMsg(msgEl, "打卡中…");
    loading(btn, true);
    try {
      const r = await api("/api/attendance/checkin", { method: "POST", json: { type: btn.dataset.checkin } });
      setMsg(msgEl, `${fmtTime(r.time)} ${r.message}`, r.is_late ? "late" : "ok");
      loadMyAttendance();
    } catch (err) { setMsg(msgEl, err.message, "err"); }
    finally { loading(btn, false); }
  }));

$("#att-period").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn"); if (!btn) return;
  state.attPeriod = btn.dataset.p;
  state.attMonth = "";
  $("#att-month").value = "";
  $("#att-period").querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
  loadMyAttendance();
});

$("#att-month").addEventListener("change", (e) => {
  const v = e.target.value; if (!v) return;
  state.attPeriod = "specific";
  state.attMonth = v;
  $("#att-period").querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
  loadMyAttendance();
});

/* ---- 报销周期 ---- */
$("#reimb-period").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn"); if (!btn) return;
  state.reimbPeriod = btn.dataset.p; state.reimbMonth = "";
  $("#reimb-month").value = "";
  $("#reimb-period").querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
  loadMyReimb();
});
$("#reimb-month").addEventListener("change", (e) => {
  const v = e.target.value; if (!v) return;
  state.reimbPeriod = "specific"; state.reimbMonth = v;
  $("#reimb-period").querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
  loadMyReimb();
});

/* ---- 工资周期 ---- */
$("#salary-period").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn"); if (!btn) return;
  state.salaryPeriod = btn.dataset.p; state.salaryMonth = "";
  $("#salary-month").value = "";
  $("#salary-period").querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
  loadMySalary();
});
$("#salary-month").addEventListener("change", (e) => {
  const v = e.target.value; if (!v) return;
  state.salaryPeriod = "specific"; state.salaryMonth = v;
  $("#salary-period").querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
  loadMySalary();
});

/* ---- 考核周期（员工） ---- */
$("#assess-period").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn"); if (!btn) return;
  state.assessPeriod = btn.dataset.p; state.assessMonth = "";
  $("#assess-month").value = "";
  $("#assess-period").querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
  loadMyScores();
});
$("#assess-month").addEventListener("change", (e) => {
  const v = e.target.value; if (!v) return;
  state.assessPeriod = "specific"; state.assessMonth = v;
  $("#assess-period").querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
  loadMyScores();
});

/* ---- 管理看板：报销/工资/考核 周期 ---- */
["reimb", "salary", "assess"].forEach((mod) => {
  $(`#admin-${mod}-period`).addEventListener("click", (e) => {
    const btn = e.target.closest(".seg-btn"); if (!btn) return;
    state[`admin${mod.charAt(0).toUpperCase() + mod.slice(1)}Period`] = btn.dataset.p;
    state[`admin${mod.charAt(0).toUpperCase() + mod.slice(1)}Month`] = "";
    $(`#admin-${mod}-month`).value = "";
    $(`#admin-${mod}-period`).querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
    if (mod === "reimb") loadAdminReimb();
    else if (mod === "salary") loadAdminSalary();
    else { loadAdminAssess(); loadAllScores(); }
  });
  $(`#admin-${mod}-month`).addEventListener("change", (e) => {
    const v = e.target.value; if (!v) return;
    const cap = mod.charAt(0).toUpperCase() + mod.slice(1);
    state[`admin${cap}Period`] = "specific";
    state[`admin${cap}Month`] = v;
    $(`#admin-${mod}-period`).querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
    if (mod === "reimb") loadAdminReimb();
    else if (mod === "salary") loadAdminSalary();
    else { loadAdminAssess(); loadAllScores(); }
  });
});

async function loadMyAttendance() {
  let url = `/api/attendance/my?period=${state.attPeriod}`;
  if (state.attPeriod === "specific" && state.attMonth) url += `&target_month=${state.attMonth}`;
  const data = await api(url);
  const rows = data.records || [];
  renderPagedTable("myAtt", {
    rows,
    head: `<thead><tr><th>日期</th><th>类型</th><th>时间</th><th>状态</th></tr></thead>`,
    tableSel: "#att-table",
    pagerSel: "#my-att-pager",
    colspan: 4,
    emptyText: "暂无打卡记录",
    render: (r) => `<tr><td>${esc(r.work_date)}</td><td>${r.type === "clock_in" ? "上班" : "下班"}</td>
      <td>${fmtTime(r.checkin_time)}</td>
      <td>${r.is_late ? '<span class="tag tag-danger">迟到</span>' : '<span class="tag tag-ok">正常</span>'}</td></tr>`
  });
}

/* ---------------- 报销 ---------------- */
$("#reimb-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msgEl = $("#reimb-msg");
  const btn = $("#reimb-form button[type=submit]");
  const fd = new FormData();
  fd.append("category", $("#reimb-category").value);
  fd.append("amount", $("#reimb-amount").value || 0);
  fd.append("desc", $("#reimb-desc").value);
  fd.append("emp_id", state.user?.emp_id ?? "");
  [...$("#reimb-files").files].forEach((f) => fd.append("files", f));
  setMsg(msgEl, "提交中…");
  loading(btn, true, "提交中…");
  try {
    const r = await api("/api/reimbursement/submit", { method: "POST", body: fd });
    if (r.missing && r.missing.length) {
      setMsg(msgEl, `${r.message}：缺 ${r.missing.join("、")}`, "err");
    } else {
      setMsg(msgEl, r.message, "ok");
      e.target.reset();
    }
    loadMyReimb();
  } catch (err) { setMsg(msgEl, err.message, "err"); }
  finally { loading(btn, false); }
});

let lastMyReimbRows = [];
async function loadMyReimb() {
  let url = `/api/reimbursement/my?period=${state.reimbPeriod}&emp_id=${state.user?.emp_id ?? ""}`;
  if (state.reimbPeriod === "specific" && state.reimbMonth) url += `&target_month=${state.reimbMonth}`;
  const data = await api(url);
  const rows = data.records || [];
  lastMyReimbRows = rows;
  const range = data.range_end ? `${data.range_start} ~ ${data.range_end}` : "";
  $("#reimb-range").textContent = range ? `统计区间：${range}` : "";
  renderPagedTable("myReimb", {
    rows,
    head: `<thead><tr><th>单号</th><th>类目</th><th>金额(元)</th><th>状态</th><th>提交时间</th><th>材料信息</th></tr></thead>`,
    tableSel: "#reimb-table",
    pagerSel: "#my-reimb-pager",
    colspan: 6,
    emptyText: "暂无报销记录",
    render: (r) => {
      const [txt, cls] = REIMB_STATUS[r.status] || [r.status, "tag-gray"];
      const raw = r.ocr_raw || "";
      return `<tr><td>#${r.id}</td><td>${esc(r.category || "未填")}</td>
        <td style="text-align:right">${money(r.amount)}</td>
        <td><span class="tag ${cls}">${txt}</span></td>
        <td>${fmtDT(r.submit_time)}</td>
        <td><button class="link-btn" data-mat="${r.id}" title="点击查看完整材料信息">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>
          ${matPreview(raw)}
        </button></td></tr>`;
    }
  });
}

$("#reimb-table").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-mat]"); if (!btn) return;
  const id = Number(btn.dataset.mat);
  const rec = (lastMyReimbRows || []).find((x) => Number(x.id) === id);
  if (rec) openMaterialModal(rec);
});

/* ---------------- 工资 ---------------- */

function renderSlip(r) {
  $("#salary-result").innerHTML = `
    <div class="slip">
      <div class="slip-head"><b>${esc(r.name || "")} · ${esc(r.position || "")}</b><span style="color:var(--ink-3)">工号 ${esc(r.id)}</span></div>
      <div class="slip-rows">
        <div class="row"><span>基本工资</span><span>¥ ${money(r.base_salary)}</span></div>
        <div class="row"><span>绩效系数</span><span>${Number(r.performance_rating || 0).toFixed(2)}</span></div>
        <div class="row"><span>绩效奖金</span><span>¥ ${money(r.performance_bonus)}</span></div>
        <div class="row"><span>津贴</span><span>¥ ${money(r.allowance)}</span></div>
        <div class="row"><span>绩效评分</span><span>${r.performance_score ?? "-"} / 100</span></div>
      </div>
      <div class="slip-total"><span>应发合计</span><span class="val">¥ ${money(r.gross_salary)}</span></div>
      ${r.reasoning ? `<div class="slip-reason">AI 评语：${esc(r.reasoning)}</div>` : ""}
    </div>`;
}

async function loadMySalary() {
  let url = `/api/salary/my?period=${state.salaryPeriod}`;
  if (state.salaryPeriod === "specific" && state.salaryMonth) url += `&target_month=${state.salaryMonth}`;
  const data = await api(url);
  const rows = data.records || [];
  const range = data.range_end ? `${data.range_start} ~ ${data.range_end}` : "";
  $("#salary-range").textContent = range ? `统计区间：${range}` : "";
  renderPagedTable("mySalary", {
    rows,
    head: `<thead><tr><th>序号</th><th>工号</th><th>姓名</th><th>岗位</th><th>基本工资</th><th>系数</th><th>绩效奖金</th><th>津贴</th><th>应发合计</th></tr></thead>`,
    tableSel: "#salary-table",
    pagerSel: "#my-salary-pager",
    colspan: 9,
    emptyText: "暂无工资核算记录，提交绩效后生成",
    render: (r) => `<tr><td>${esc(r.no)}</td><td>${esc(r.id)}</td><td>${esc(r.name)}</td><td>${esc(r.position)}</td>
      <td style="text-align:right">${money(r.base_salary)}</td>
      <td style="text-align:center">${Number(r.performance_rating || 0).toFixed(2)}</td>
      <td style="text-align:right">${money(r.performance_bonus)}</td>
      <td style="text-align:right">${money(r.allowance)}</td>
      <td style="text-align:right"><b>${money(r.gross_salary)}</b></td></tr>`
  });
}

/* ---------------- 考核 ---------------- */
// 成绩分档：返回 {txt 标签, cls 颜色类, pct 进度条%}
function scoreBand(score) {
  if (score == null) return { txt: "无成绩", cls: "tag-gray", pct: 0 };
  if (score >= 90) return { txt: "优秀", cls: "tag-ok", pct: Math.min(100, score) };
  if (score >= 80) return { txt: "良好", cls: "tag-info", pct: Math.min(100, score) };
  if (score >= 60) return { txt: "合格", cls: "tag-warn", pct: Math.min(100, score) };
  return { txt: "待提升", cls: "tag-danger", pct: Math.min(100, score) };
}
// 查询岗位「实际关联」里我的成绩
function relMyScore(score) {
  if (score == null) return `<div class="assess-rel-num" style="font-size:14px">尚未参加过该岗位考核</div>
    <div class="assess-rel-label">可在下方参加本岗位考核</div>`;
  const b = scoreBand(score);
  return `<div class="assess-rel-num">${score}<small> 分</small></div>
    <div class="assess-rel-label">你对该岗位的历史成绩 · <span class="tag ${b.cls}">${b.txt}</span></div>`;
}

$("#assess-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const pos = $("#assess-position").value.trim();
  if (!pos) return;
  // 在查询岗位卡片内（form下方）显示结果
  const $card = $("#assess-form").closest(".card");
  let $result = $card.querySelector(".assess-inline-result");
  if (!$result) {
    $result = document.createElement("div");
    $result.className = "assess-inline-result";
    $card.appendChild($result);
  }
  $result.innerHTML = `<p style="color:var(--ink-3);padding:8px 0">查询中…</p>`;
  try {
    const r = await api("/api/assessment/query", { method: "POST", json: { position: pos } });
    const relHtml = `
      <div class="assess-sub">实际关联</div>
      <div class="assess-rel">
        <div class="assess-rel-item"><span class="assess-rel-ico">👥</span>
          <div><div class="assess-rel-num">${r.holders_count ?? 0}<small> 人</small></div>
          <div class="assess-rel-label">当前在岗人数</div></div></div>
        <div class="assess-rel-item"><span class="assess-rel-ico">🎯</span>
          <div>${relMyScore(r.my_score)}</div></div>
      </div>`;
    $result.innerHTML = `
      <div class="assess-sub" style="margin-top:12px">岗位介绍</div>
      <p style="font-size:13.5px;color:var(--ink-2);margin-bottom:10px">${esc(r.intro || "暂无介绍")}</p>
      <div class="assess-sub">核心能力要求</div>
      <div class="chip-row">${(r.skills || []).map((s) => `<span class="chip">${esc(s)}</span>`).join("") || "<span style='color:var(--ink-3)'>暂无</span>"}</div>
      <div class="assess-sub">管理能力要求</div>
      <div class="chip-row">${(r.management_abilities || []).map((s) => `<span class="chip alt">${esc(s)}</span>`).join("") || "<span style='color:var(--ink-3)'>暂无</span>"}</div>
      <div class="assess-sub">建议发展路径</div>
      <ol style="padding-left:20px;color:var(--ink-2);font-size:13.5px;margin-bottom:8px">${(r.suggested_path || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
      ${relHtml}`;
  } catch (err) {
    $result.innerHTML = `<p style="color:var(--danger);padding:8px 0">${esc(err.message)}</p>`;
  }
});

/* ---------------- 考核申请 / 答题 ---------------- */
let quizData = null;   // 当前试卷数据（含标准答案，不暴露给前端DOM）
let quizPage = 0;      // 当前页码（从0开始）
const QUIZ_PER_PAGE = 2; // 每页显示题数

$("#btn-start-quiz").addEventListener("click", async () => {
  const pos = $("#quiz-position").value.trim();
  if (!pos) { alert("请先选择目标岗位"); return; }

  $("#btn-start-quiz").disabled = true;
  $("#btn-start-quiz").textContent = "出题中…";
  $("#quiz-container").innerHTML = `<p class="form-tip">正在生成${esc(pos)}岗位考核试题…</p>`;
  $("#quiz-container").classList.remove("hidden");
  $("#quiz-result").classList.add("hidden");

  try {
    const r = await api("/api/assessment/generate", { method: "POST", json: { target_position: pos } });
    if (r.error) { throw new Error(r.error); }
    quizData = r;
    quizPage = 0;
    renderQuizPage();
  } catch (err) {
    $("#quiz-container").innerHTML = `<p style="color:var(--danger)">出题失败：${esc(err.message)}</p>`;
  } finally {
    $("#btn-start-quiz").disabled = false;
    $("#btn-start-quiz").textContent = "开始考核";
  }
});

function renderQuizPage() {
  const qs = quizData.questions || [];
  const totalPages = Math.ceil(qs.length / QUIZ_PER_PAGE);
  const startIdx = quizPage * QUIZ_PER_PAGE;
  const pageQs = qs.slice(startIdx, startIdx + QUIZ_PER_PAGE);

  let html = `
    <div class="quiz-header">
      <span><strong>${esc(quizData.target_position)}</strong> 岗位考核</span>
      <span class="quiz-progress">共 ${qs.length} 题 · 满分 ${quizData.max_score} 分 · 第 ${quizPage + 1}/${totalPages} 页</span>
    </div>
    <div class="quiz-body">`;

  pageQs.forEach((q, i) => {
    const globalIdx = startIdx + i;
    const typeLabel = q.type === "single" ? "单选题" : q.type === "multi" ? "多选题" : "判断题";
    const ptsLabel = `(${q.points}分)`;
    html += `
      <div class="quiz-q" data-qid="${q.id}" data-type="${q.type}">
        <div class="quiz-q-head"><span class="quiz-q-num">第${globalIdx + 1}题</span>
          <span class="quiz-q-type">${typeLabel}</span><span class="quiz-q-pts">${ptsLabel}</span>
        </div>
        <div class="quiz-q-text">${esc(q.question)}</div>
        <div class="quiz-q-opts">`;

    q.options.forEach((opt, oi) => {
      if (q.type === "multi") {
        html += `<label class="quiz-opt quiz-opt-multi"><input type="checkbox" name="q_${q.id}" value="${oi}"><span>${esc(opt)}</span></label>`;
      } else {
        html += `<label class="quiz-opt"><input type="radio" name="q_${q.id}" value="${oi}"><span>${esc(opt)}</span></label>`;
      }
    });

    html += `</div></div>`;
  });

  // 分页导航
  html += `
    </div>
    <div class="quiz-page-nav">
      <button class="btn-outline" id="quiz-prev-btn" ${quizPage === 0 ? "disabled" : ""}>上一页</button>
      <span class="quiz-page-dots">${_pageDots(totalPages)}</span>
      <button class="btn-primary" id="quiz-next-btn" ${quizPage >= totalPages - 1 ? "disabled" : ""}>下一页</button>
    </div>
    <div class="quiz-foot">
      <button class="btn-primary" id="btn-submit-quiz">提交答卷</button>
    </div>`;

  $("#quiz-container").innerHTML = html;
  $("#quiz-apply").classList.add("hidden");

  // 绑定翻页
  $("#quiz-prev-btn").addEventListener("click", () => { if (quizPage > 0) { quizPage--; renderQuizPage(); } });
  $("#quiz-next-btn").addEventListener("click", () => { if (quizPage < totalPages - 1) { quizPage++; renderQuizPage(); } });
  // 绑定提交
  $("#btn-submit-quiz").addEventListener("click", submitQuiz);
}

function _pageDots(total) {
  let dots = "";
  for (let i = 0; i < total; i++) {
    dots += `<span class="quiz-dot ${i === quizPage ? "active" : ""}" data-p="${i}"></span>`;
  }
  return dots;
}

async function submitQuiz() {
  if (!quizData || !quizData.questions.length) return;

  const answers = [];
  let allAnswered = true;

  for (const q of quizData.questions) {
    const el = document.querySelector(`.quiz-q[data-qid="${q.id}"]`);
    if (!el) continue;

    let userAns = [];
    if (q.type === "multi") {
      const cbs = el.querySelectorAll('input[type="checkbox"]:checked');
      cbs.forEach(cb => userAns.push(parseInt(cb.value)));
    } else {
      const rd = el.querySelector('input[type="radio"]:checked');
      if (rd) userAns.push(parseInt(rd.value));
    }

    if (userAns.length === 0) allAnswered = false;
    answers.push({ question_id: q.id, user_answer: userAns });
  }

  if (!allAnswered) {
    if (!confirm("有未完成的题目，确定提交吗？")) return;
  }

  $("#btn-submit-quiz").disabled = true;
  $("#btn-submit-quiz").textContent = "批改中…";

  try {
    const r = await api("/api/assessment/submit", {
      method: "POST",
      json: {
        target_position: quizData.target_position,
        original_position: state.user?.position || "",
        answers,
      },
    });

    renderQuizResult(r);
    // 刷新成绩列表
    loadMyScores();
  } catch (err) {
    alert("提交失败：" + err.message);
  } finally {
    $("#btn-submit-quiz").disabled = false;
    $("#btn-submit-quiz").textContent = "提交答卷";
  }
}

function renderQuizResult(r) {
  $("#quiz-container").classList.add("hidden");
  const resEl = $("#quiz-result");
  resEl.classList.remove("hidden");

  const bandCls = r.score >= 90 ? "tag-success" : r.score >= 80 ? "tag-info" : r.score >= 60 ? "tag-warn" : "tag-danger";

  let breakdownHtml = "";
  if (r.breakdown) {
    breakdownHtml = `<div class="quiz-bd"><table class="tbl">
      <thead><tr><th>题号</th><th>题型</th><th>你的答案</th><th>正确答案</th><th>得分</th></tr></thead><tbody>`;
    for (const b of r.breakdown) {
      const icon = b.is_correct ? "✅" : "❌";
      const correctOpts = (Array.isArray(b.correct_answer) ? b.correct_answer : [b.correct_answer])
        .map(i => String.fromCharCode(65 + i)).join(",");
      const userOpts = (b.user_answer || []).map(i => String.fromCharCode(65 + i)).join(",") || "未作答";
      breakdownHtml += `<tr style="${b.is_correct ? "" : "color:var(--danger)"}">
        <td>${icon} #${b.question_id}</td>
        <td>${b.type === "single" ? "单选" : b.type === "multi" ? "多选" : "判断"}</td>
        <td>${userOpts}</td><td>${correctOpts}</td><td><strong>${b.earned}/${b.points}</strong></td></tr>`;
    }
    breakdownHtml += `</tbody></table></div>`;
  }

  resEl.innerHTML = `
    <div class="quiz-score-card">
      <div class="quiz-score-big">${r.score}<small> / ${r.max_score}</small></div>
      <div class="quiz-score-band"><span class="tag ${bandCls}">${r.band}</span></div>
      <div class="quiz-score-sub">${esc(r.original_position)} → ${esc(r.target_position)} · ${r.test_time?.slice(0,16) || ""}</div>
    </div>
    <div class="quiz-score-detail">
      ${statCard("单选题", `${r.single_score ?? 0}/24`)}
      ${statCard("多选题", `${r.multi_score ?? 0}/52`)}
      ${statCard("判断题", `${r.judge_score ?? 0}/24`)}
    </div>
    ${breakdownHtml}
    <div style="margin-top:16px;text-align:center">
      <button class="btn-primary" id="btn-retake-quiz">重新考核</button>
    </div>`;

  // 重新考核按钮：回到选岗界面
  $("#btn-retake-quiz").addEventListener("click", () => {
    resEl.classList.add("hidden");
    $("#quiz-apply").classList.remove("hidden");
    quizData = null;
  });
}

/* ---------------- 考核成绩 ---------------- */
async function loadMyScores() {
  const wrap = $("#assess-scores-wrap");
  if (!wrap) return;
  try {
    let url = `/api/assessment/scores?period=${state.assessPeriod}`;
    if (state.assessPeriod === "specific" && state.assessMonth) url += `&target_month=${state.assessMonth}`;
    const r = await api(url);
    const list = r.scores || [];
    const range = r.range_end ? `${r.range_start} ~ ${r.range_end}` : "";
    $("#assess-range").textContent = range ? `统计区间：${range}` : "";
    if (!list.length) {
      wrap.innerHTML = `<p class="form-tip">暂无考核成绩记录。参加岗位考核后，这里会显示你的成绩与能力发展轨迹。</p>`;
      return;
    }
    // 概览统计（基于真实成绩）
    const scores = list.map((s) => s.score).filter((v) => v != null);
    const avg = scores.length ? (scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
    const max = scores.length ? Math.max(...scores) : 0;
    const pass = scores.filter((v) => v >= 60).length;
    const overview = `<div class="assess-overview">
      ${statCard("考核次数", list.length, "次")}
      ${statCard("平均分", avg.toFixed(1), "分")}
      ${statCard("最高分", max.toFixed(1), "分")}
      ${statCard("合格次数", `${pass}/${list.length}`)}
    </div>`;
    const cardRender = (s) => {
      const b = scoreBand(s.score);
      const pct = b.pct;
      return `<div class="score-card">
        <div class="score-card-route">${esc(s.original_position || "—")} <span class="score-arrow">→</span> ${esc(s.target_position || "—")}</div>
        <div class="score-card-body">
          <div class="score-card-num ${b.cls === "tag-danger" ? "is-low" : ""}">${s.score != null ? s.score : "—"}<small>分</small></div>
          <div class="score-card-meta">
            <span class="tag ${b.cls}">${b.txt}</span>
            <span class="score-card-date">${s.test_time ? s.test_time.slice(0, 10) : ""}</span>
          </div>
        </div>
        <div class="score-bar${b.cls === "tag-danger" ? " is-low" : ""}"><span style="width:${pct}%"></span></div>
      </div>`;
    };
    const ps = _pgState("my-scores");
    ps.rows = list;
    ps.render = cardRender;
    ps.mode = "cards";
    ps.wrapSel = "#assess-scores-wrap";
    ps.pagerSel = "#my-scores-pager";
    ps.overview = overview;
    ps.emptyText = "暂无考核成绩记录";
    ps.page = 1;
    if (!ps.size) ps.size = 10;
    _drawPagedTable("my-scores");
  } catch (err) {
    wrap.innerHTML = `<p style="color:var(--danger)">${esc(err.message)}</p>`;
  }
}

async function loadAllScores() {
  const el = $("#admin-scores-table");
  if (!el) return;
  const head = `<thead><tr><th>姓名</th><th>工号</th><th>原岗位</th><th>意向岗位</th><th>成绩</th><th>测试时间</th></tr></thead>`;
  try {
    let url = `/api/assessment/scores/all?period=${state.adminAssessPeriod}`;
    if (state.adminAssessPeriod === "specific" && state.adminAssessMonth) url += `&target_month=${state.adminAssessMonth}`;
    const r = await api(url);
    renderPagedTable("allScores", {
      rows: r.scores || [],
      head,
      tableSel: "#admin-scores-table",
      pagerSel: "#admin-scores-pager",
      colspan: 6,
      emptyText: "暂无考核成绩",
      render: (s) => `<tr><td>${esc(s.name || "-")}</td>
        <td>${s.employee_id}</td>
        <td>${esc(s.original_position || "-")}</td>
        <td>${esc(s.target_position || "-")}</td>
        <td>${s.score ?? "-"}</td>
        <td>${s.test_time ? s.test_time.slice(0, 10) : "-"}</td></tr>`
    });
  } catch (err) {
    el.innerHTML = head;
  }
}

/* ---------------- 管理看板 ---------------- */
function currentAdminTab() {
  const b = $("#admin-tabs .seg-btn.active");
  return b ? b.dataset.t : "att";
}

$("#admin-tabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn"); if (!btn) return;
  $("#admin-tabs").querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
  loadAdminTab(btn.dataset.t);
});

$("#admin-att-period").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn"); if (!btn) return;
  state.adminAttPeriod = btn.dataset.p;
  state.adminAttMonth = "";
  $("#admin-att-month").value = "";
  $("#admin-att-period").querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
  loadAdminAttendance();
});

$("#admin-att-month").addEventListener("change", (e) => {
  const v = e.target.value; if (!v) return;
  state.adminAttPeriod = "specific";
  state.adminAttMonth = v;
  $("#admin-att-period").querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
  loadAdminAttendance();
});

async function loadAdminTab(tab) {
  document.querySelectorAll(".admin-pane").forEach((p) => p.classList.add("hidden"));
  $(`#admin-${tab}`).classList.remove("hidden");
  if (tab === "att") loadAdminAttendance();
  if (tab === "reimb") loadAdminReimb();
  if (tab === "salary") loadAdminSalary();
  if (tab === "assess") { loadAdminAssess(); loadAllScores(); }
}

function statCard(label, value, sub) {
  return `<div class="stat-card"><div class="stat-label">${label}</div>
    <div class="stat-value">${value}${sub ? ` <small>${sub}</small>` : ""}</div></div>`;
}

async function loadAdminAttendance() {
  try {
    let url = `/api/attendance/report?period=${state.adminAttPeriod}`;
    if (state.adminAttPeriod === "specific" && state.adminAttMonth) url += `&target_month=${state.adminAttMonth}`;
    const r = await api(url);
    $("#admin-att-stats").innerHTML =
      statCard("考勤记录", r.stats.record_count, "人次") +
      statCard("迟到人次", `<span style="color:${r.stats.late_count ? "var(--danger)" : "var(--ok)"}">${r.stats.late_count}</span>`) +
      statCard("迟到最多", r.stats.late_top_str || "无");
    const range = r.range_end ? `${r.range_start} ~ ${r.range_end}` : (r.range_start || "");
    $("#admin-att-range").textContent = range ? `统计区间：${range}` : "";
    state.adminAttRows = r.rows || [];
    state.adminAttPage = 1;
    renderAdminAttTable();
  } catch (err) { console.error(err); }
}

/* 分页窗口：总页数 ≤7 全显示；否则显示 首/尾 + 当前页附近 ±2 + 省略号 */
function _pageWindow(cur, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const arr = [1];
  const s = Math.max(2, cur - 2), e = Math.min(total - 1, cur + 2);
  if (s > 2) arr.push("…");
  for (let i = s; i <= e; i++) arr.push(i);
  if (e < total - 1) arr.push("…");
  arr.push(total);
  return arr;
}

function renderAdminAttTable() {
  const rows = state.adminAttRows;
  const size = state.adminAttPageSize;
  const totalPages = Math.max(1, Math.ceil(rows.length / size));
  if (state.adminAttPage > totalPages) state.adminAttPage = totalPages;
  const start = (state.adminAttPage - 1) * size;
  const pageRows = rows.slice(start, start + size);

  const tbody = pageRows.length ? pageRows.map((row) => `
      <tr><td>${esc(row.employee_name)}</td><td>${esc(row.work_date)}</td>
      <td>${row.type === "clock_in" ? "上班" : "下班"}</td><td>${fmtTime(row.checkin_time)}</td>
      <td>${row.is_late ? '<span class="tag tag-danger">迟到</span>' : '<span class="tag tag-ok">正常</span>'}</td></tr>`).join("")
    : `<tr class="empty"><td colspan="5">${emptyHTML("暂无考勤数据")}</td></tr>`;
  $("#admin-att-table").innerHTML = `<thead><tr><th>员工</th><th>日期</th><th>类型</th><th>时间</th><th>状态</th></tr></thead><tbody>${tbody}</tbody>`;

  // 分页控件
  const total = rows.length;
  const pager = $("#admin-att-pager");
  if (total === 0) { pager.innerHTML = ""; return; }
  const cur = state.adminAttPage;
  const from = start + 1, to = Math.min(start + size, total);
  let html = `<button class="pg-btn" data-pg="prev" ${cur === 1 ? "disabled" : ""}>‹ 上一页</button>`;
  for (const p of _pageWindow(cur, totalPages)) {
    if (p === "…") html += `<span class="pg-ellipsis">…</span>`;
    else html += `<button class="pg-btn ${p === cur ? "active" : ""}" data-pg="${p}">${p}</button>`;
  }
  html += `<button class="pg-btn" data-pg="next" ${cur === totalPages ? "disabled" : ""}>下一页 ›</button>`;
  html += `<span class="pg-info">第 ${from}-${to} 条 / 共 ${total} 条</span>`;
  html += `<select class="pg-size" id="admin-att-pagesize">
      <option value="10" ${size === 10 ? "selected" : ""}>10/页</option><option value="20" ${size === 20 ? "selected" : ""}>20/页</option>
      <option value="50" ${size === 50 ? "selected" : ""}>50/页</option>
      <option value="100" ${size === 100 ? "selected" : ""}>100/页</option></select>`;
  pager.innerHTML = html;
}

/* 分页交互（事件委托，控件是动态生成的） */
$("#admin-att-pager").addEventListener("click", (e) => {
  const btn = e.target.closest(".pg-btn");
  if (!btn || btn.disabled) return;
  const pg = btn.dataset.pg;
  const totalPages = Math.max(1, Math.ceil(state.adminAttRows.length / state.adminAttPageSize));
  if (pg === "prev") state.adminAttPage = Math.max(1, state.adminAttPage - 1);
  else if (pg === "next") state.adminAttPage = Math.min(totalPages, state.adminAttPage + 1);
  else state.adminAttPage = parseInt(pg, 10);
  renderAdminAttTable();
});
$("#admin-att-pager").addEventListener("change", (e) => {
  if (e.target.id === "admin-att-pagesize") {
    state.adminAttPageSize = parseInt(e.target.value, 10);
    state.adminAttPage = 1;
    renderAdminAttTable();
  }
});

/* ---------------- 通用分页引擎（个人 / 管理多张表复用） ---------------- */
/* state._pg[key] = { page, size, rows, render(row), head, tableSel, pagerSel, colspan, emptyText } */
function _pgState(key) {
  if (!state._pg) state._pg = {};
  if (!state._pg[key]) state._pg[key] = { page: 1, size: 10, rows: [], render: null, head: "", tableSel: "", pagerSel: "", colspan: 1, emptyText: "暂无数据", mode: "table", wrapSel: "", overview: "" };
  return state._pg[key];
}

function renderPagedTable(key, opts) {
  const ps = _pgState(key);
  ps.rows = opts.rows || [];
  ps.render = opts.render;
  ps.head = opts.head;
  ps.tableSel = opts.tableSel;
  ps.pagerSel = opts.pagerSel;
  ps.colspan = opts.colspan || 1;
  ps.emptyText = opts.emptyText || "暂无数据";
  ps.page = 1;
  _drawPagedTable(key);
}

function _drawPagedTable(key) {
  const ps = state._pg[key];
  if (!ps) return;
  const total = ps.rows.length;
  const totalPages = Math.max(1, Math.ceil(total / ps.size));
  if (ps.page > totalPages) ps.page = totalPages;
  const start = (ps.page - 1) * ps.size;
  const pageRows = ps.rows.slice(start, start + ps.size);
  const cur = ps.page;
  const from = start + 1, to = Math.min(start + ps.size, total);
  // 通用分页器 HTML（表格与卡片模式共用）
  const pagerHTML = (() => {
    let h = `<button class="pg-btn" data-pg="prev" data-key="${key}" ${cur === 1 ? "disabled" : ""}>‹ 上一页</button>`;
    for (const p of _pageWindow(cur, totalPages)) {
      if (p === "…") h += `<span class="pg-ellipsis">…</span>`;
      else h += `<button class="pg-btn ${p === cur ? "active" : ""}" data-pg="${p}" data-key="${key}">${p}</button>`;
    }
    h += `<button class="pg-btn" data-pg="next" data-key="${key}" ${cur === totalPages ? "disabled" : ""}>下一页 ›</button>`;
    h += `<span class="pg-info">第 ${from}-${to} 条 / 共 ${total} 条</span>`;
    h += `<select class="pg-size" data-key="${key}">
      <option value="10" ${ps.size === 10 ? "selected" : ""}>10/页</option>
      <option value="20" ${ps.size === 20 ? "selected" : ""}>20/页</option>
      <option value="50" ${ps.size === 50 ? "selected" : ""}>50/页</option>
      <option value="100" ${ps.size === 100 ? "selected" : ""}>100/页</option></select>`;
    return h;
  })();
  if (ps.mode === "cards") {
    const cards = pageRows.length ? pageRows.map(ps.render).join("")
      : `<p class="form-tip">${emptyHTML(ps.emptyText)}</p>`;
    const wrap = $(ps.wrapSel);
    if (wrap) wrap.innerHTML = (ps.overview || "") + `<div class="score-cards">${cards}</div>`;
    const pager = $(ps.pagerSel);
    if (!pager) return;
    pager.innerHTML = total === 0 ? "" : pagerHTML;
    return;
  }
  const tbody = pageRows.length ? pageRows.map(ps.render).join("")
    : `<tr class="empty"><td colspan="${ps.colspan}">${emptyHTML(ps.emptyText)}</td></tr>`;
  const tbl = $(ps.tableSel);
  if (tbl) tbl.innerHTML = ps.head + `<tbody>${tbody}</tbody>`;
  const pager = $(ps.pagerSel);
  if (!pager) return;
  pager.innerHTML = total === 0 ? "" : pagerHTML;
}

/* 全局事件委托：处理带 data-key 的分页控件（admin-att 旧控件无 data-key，不受影响） */
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".pg-btn");
  if (!btn || btn.disabled) return;
  const key = btn.dataset.key;
  if (!key || !state._pg || !state._pg[key]) return;
  const ps = state._pg[key];
  const totalPages = Math.max(1, Math.ceil(ps.rows.length / ps.size));
  const pg = btn.dataset.pg;
  if (pg === "prev") ps.page = Math.max(1, ps.page - 1);
  else if (pg === "next") ps.page = Math.min(totalPages, ps.page + 1);
  else ps.page = parseInt(pg, 10);
  _drawPagedTable(key);
});
document.addEventListener("change", (e) => {
  const sel = e.target.closest(".pg-size[data-key]");
  if (!sel) return;
  const key = sel.dataset.key;
  const ps = state._pg && state._pg[key];
  if (!ps) return;
  ps.size = parseInt(sel.value, 10);
  ps.page = 1;
  _drawPagedTable(key);
});

let lastAdminReimbRows = [];
async function loadAdminReimb() {
  try {
    let url = `/api/reimbursement/report?period=${state.adminReimbPeriod}`;
    if (state.adminReimbPeriod === "specific" && state.adminReimbMonth) url += `&target_month=${state.adminReimbMonth}`;
    const r = await api(url);
    lastAdminReimbRows = r.rows || [];
    $("#admin-reimb-stats").innerHTML =
      statCard("报销笔数", r.stats.total_count) +
      statCard("待审批", `<span style="color:${r.stats.pending_count ? "var(--warn)" : "var(--ok)"}">${r.stats.pending_count}</span>`) +
      statCard("合计金额", money(r.stats.total_amount), "元") +
      statCard("单笔最高", money(r.stats.max_amount), "元");
    const range = r.range_end ? `${r.range_start} ~ ${r.range_end}` : "";
    $("#admin-reimb-range").textContent = range ? `统计区间：${range}` : "";
    renderPagedTable("adminReimb", {
      rows: r.rows || [],
      head: `<thead><tr><th>单号</th><th>员工</th><th>类目</th><th>金额(元)</th><th>状态</th><th>提交时间</th><th>材料信息</th><th>操作</th></tr></thead>`,
      tableSel: "#admin-reimb-table",
      pagerSel: "#admin-reimb-pager",
      colspan: 8,
      emptyText: "暂无数据",
      render: (row) => {
        const [txt, cls] = REIMB_STATUS[row.status] || [row.status, "tag-gray"];
        const raw = row.ocr_raw || "";
        const act = ["submitted", "approving"].includes(row.status)
          ? `<div class="review-actions">
             <button class="btn-ok" data-review="${row.id}" data-action="approve">通过</button>
             <button class="btn-reject" data-review="${row.id}" data-action="reject">驳回</button>
           </div>` : "";
        return `<tr><td>#${row.id}</td><td>${esc(row.employee_name)}</td><td>${esc(row.category || "未填")}</td>
          <td style="text-align:right">${money(row.amount)}</td>
          <td><span class="tag ${cls}">${txt}</span></td><td>${fmtDT(row.submit_time)}</td>
          <td><button class="link-btn" data-mat="${row.id}" title="点击查看完整材料信息">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>
            ${matPreview(raw)}
          </button></td>
          <td>${act}</td></tr>`;
      }
    });
  } catch (err) { console.error(err); }
}

$("#admin-reimb-table").addEventListener("click", async (e) => {
  const matBtn = e.target.closest("[data-mat]");
  if (matBtn && !e.target.closest("[data-review]")) {
    const id = Number(matBtn.dataset.mat);
    const rec = (lastAdminReimbRows || []).find((x) => Number(x.id) === id);
    if (rec) openMaterialModal(rec);
    return;
  }
  const btn = e.target.closest("[data-review]"); if (!btn) return;
  const ok = await confirmModal(`确认${btn.dataset.action === "approve" ? "通过" : "驳回"}该报销单？`, "审批操作");
  if (!ok) return;
  loading(btn, true, "处理中");
  try {
    await api(`/api/reimbursement/${btn.dataset.review}/review`, { method: "POST", json: { action: btn.dataset.action } });
    toast("已更新报销单状态", "ok");
    loadAdminReimb();
  } catch (err) { toast(err.message, "err"); loading(btn, false); }
});

let lastSalaryRows = [];
async function loadAdminSalary() {
  try {
    let url = `/api/salary/report?period=${state.adminSalaryPeriod}`;
    if (state.adminSalaryPeriod === "specific" && state.adminSalaryMonth) url += `&target_month=${state.adminSalaryMonth}`;
    const r = await api(url);
    lastSalaryRows = r.rows || [];
    $("#admin-salary-stats").innerHTML =
      statCard("工资条数", r.stats.slip_count) +
      statCard("工资总额", money(r.stats.total_payroll), "元") +
      statCard("平均工资", money(r.stats.avg_pay), "元");
    const range = r.range_end ? `${r.range_start} ~ ${r.range_end}` : "";
    $("#admin-salary-range").textContent = range ? `统计区间：${range}` : "";
    renderPagedTable("adminSalary", {
      rows: r.rows || [],
      head: `<thead><tr><th>序号</th><th>工号</th><th>姓名</th><th>岗位</th><th>基本工资</th><th>系数</th><th>绩效奖金</th><th>津贴</th><th>应发合计</th><th>操作</th></tr></thead>`,
      tableSel: "#admin-salary-table",
      pagerSel: "#admin-salary-pager",
      colspan: 10,
      emptyText: "暂无工资数据",
      render: (row) => `
      <tr data-id="${esc(row.id)}">
        <td>${esc(row.no)}</td><td>${esc(row.id)}</td><td>${esc(row.name)}</td><td>${esc(row.position || "")}</td>
        <td style="text-align:right">${money(row.base_salary)}</td>
        <td style="text-align:center">${Number(row.performance_rating || 0).toFixed(2)}</td>
        <td style="text-align:right">${money(row.performance_bonus)}</td>
        <td style="text-align:right">${money(row.allowance)}</td>
        <td style="text-align:right"><b>${money(row.gross_salary)}</b></td>
        <td><button class="btn-ghost btn-sm" data-sal-edit="${esc(row.id)}">编辑</button></td>
      </tr>`
    });
  } catch (err) { console.error(err); }
}

/* ---------------- 工资核算编辑（管理者）---------------- */
function recalcGross() {
  const b = Number($("#sf-base").value || 0), p = Number($("#sf-bonus").value || 0), a = Number($("#sf-allow").value || 0);
  $("#sf-gross").value = (b + p + a).toFixed(2);
}
["sf-base", "sf-bonus", "sf-allow"].forEach((i) => $("#" + i).addEventListener("input", recalcGross));
$("#salary-cancel-btn").addEventListener("click", () => $("#salary-edit-card").classList.add("hidden"));

$("#admin-salary-table").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-sal-edit]");
  if (!btn) return;
  const id = Number(btn.dataset.salEdit);
  const row = (lastSalaryRows || []).find((x) => Number(x.id) === id);
  if (!row) return;
  $("#salary-edit-title").textContent = `编辑工资核算：${row.name}（${row.id}）`;
  $("#sf-no").value = row.no;
  $("#sf-id").value = row.id;
  $("#sf-name").value = row.name;
  $("#sf-position").value = row.position;
  $("#sf-base").value = row.base_salary;
  $("#sf-rating").value = Number(row.performance_rating || 1.0).toFixed(2);
  $("#sf-bonus").value = row.performance_bonus;
  $("#sf-allow").value = row.allowance;
  recalcGross();
  setMsg($("#salary-msg"), "");
  $("#salary-edit-card").classList.remove("hidden");
  $("#salary-edit-card").scrollIntoView({ behavior: "smooth" });
});

$("#salary-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = Number($("#sf-id").value);
  const body = {
    no: Number($("#sf-no").value),
    name: $("#sf-name").value.trim(),
    position: $("#sf-position").value.trim(),
    base_salary: Number($("#sf-base").value || 0),
    performance_rating: Number($("#sf-rating").value || 1.0),
    performance_bonus: Number($("#sf-bonus").value || 0),
    allowance: Number($("#sf-allow").value || 0),
    gross_salary: Number($("#sf-gross").value || 0),
  };
  const btn = $("#salary-form button[type=submit]");
  loading(btn, true, "保存中…");
  try {
    await api(`/api/salary/${id}`, { method: "PUT", json: body });
    setMsg($("#salary-msg"), "已保存", "ok");
    $("#salary-edit-card").classList.add("hidden");
    loadAdminSalary();
  } catch (err) { setMsg($("#salary-msg"), err.message, "err"); }
  finally { loading(btn, false); }
});

async function loadAdminAssess() {
  try {
    let url = `/api/assessment/stats?period=${state.adminAssessPeriod}`;
    if (state.adminAssessPeriod === "specific" && state.adminAssessMonth) url += `&target_month=${state.adminAssessMonth}`;
    const r = await api(url);
    renderPagedTable("adminAssess", {
      rows: r.rows || [],
      head: `<thead><tr><th>员工</th><th>查询岗位</th><th>次数</th></tr></thead>`,
      tableSel: "#admin-assess-table",
      pagerSel: "#admin-assess-pager",
      colspan: 3,
      emptyText: "暂无岗位查询记录",
      render: (row) => `
      <tr><td>${esc(row.name)}</td><td>${esc(row.position_queried)}</td>
      <td><span class="tag tag-info">${row.count} 次</span></td></tr>`
    });
    const range = r.range_end ? `${r.range_start} ~ ${r.range_end}` : "";
    $("#admin-assess-range").textContent = range ? `统计区间：${range}` : "";
  } catch (err) { console.error(err); }
}

/* ---------------- 花名册维护 ---------------- */
$("#roster-add-btn").addEventListener("click", () => openRosterForm(null));
$("#roster-cancel-btn").addEventListener("click", () => $("#roster-edit-card").classList.add("hidden"));

function openRosterForm(emp) {
  state.rosterEditing = emp;
  $("#roster-edit-title").textContent = emp ? `编辑：${emp.name}` : "新增员工";
  $("#rf-empid").value = emp ? emp.emp_id : "";
  $("#rf-name").value = emp ? emp.name : "";
  $("#rf-position").value = emp ? emp.position : "";
  $("#rf-dept").value = emp ? emp.department : "总经办";
  $("#rf-perms").value = emp ? (emp.permissions || []).join(",") : "";
  $("#rf-pwd").value = "";
  setMsg($("#roster-msg"), "");
  $("#roster-edit-card").classList.remove("hidden");
  $("#roster-edit-card").scrollIntoView({ behavior: "smooth" });
}

$("#roster-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msgEl = $("#roster-msg");
  const body = {
    emp_id: Number($("#rf-empid").value),
    name: $("#rf-name").value.trim(),
    position: $("#rf-position").value.trim(),
    department: $("#rf-dept").value,
    permissions: $("#rf-perms").value.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
    password: $("#rf-pwd").value.trim() || null,
  };
  if (!body.emp_id || !body.name || !body.position) return setMsg(msgEl, "工号、姓名、岗位必填", "err");
  try {
    const btn = $("#roster-form button[type=submit]");
    loading(btn, true, "保存中…");
    if (state.rosterEditing) {
      await api(`/api/roster/${state.rosterEditing.id}`, { method: "PUT", json: body });
      setMsg(msgEl, "已保存", "ok");
    } else {
      await api("/api/roster", { method: "POST", json: body });
      setMsg(msgEl, "已新增", "ok");
    }
    loadRoster();
    setTimeout(() => $("#roster-edit-card").classList.add("hidden"), 800);
    loading(btn, false);
  } catch (err) { setMsg(msgEl, err.message, "err"); }
});

async function loadRoster() {
  try {
  const data = await api("/api/roster");
  const rows = data.records || [];
  renderPagedTable("roster", {
    rows,
    head: `<thead><tr><th>序号</th><th>姓名</th><th>工号</th><th>部门</th><th>岗位</th><th>权限范围</th><th>角色</th><th>操作</th></tr></thead>`,
    tableSel: "#roster-table",
    pagerSel: "#roster-pager",
    colspan: 8,
    emptyText: "暂无员工",
    render: (e) => `
    <tr><td>${e.no}</td><td><b>${esc(e.name)}</b></td><td>${e.emp_id}</td>
      <td>${esc(e.department)}</td><td>${esc(e.position)}</td>
      <td>${(e.permissions || []).map((p) => `<span class="tag tag-gray">${esc(p)}</span>`).join(" ") || "-"}</td>
      <td>${e.role === "manager" ? '<span class="tag tag-info">管理者</span>' : '<span class="tag">员工</span>'}</td>
      <td><div class="review-actions">
        <button class="btn-ghost btn-sm" data-edit="${e.id}">编辑</button>
        <button class="btn-reject" data-del="${e.id}">删除</button>
      </div></td></tr>`
  });
  } catch (err) { console.error(err); }
}

$("#roster-table").addEventListener("click", async (e) => {
  const editBtn = e.target.closest("[data-edit]");
  const delBtn = e.target.closest("[data-del]");
  if (editBtn) {
    const data = await api("/api/roster");
    const emp = (data.records || []).find((x) => x.id === Number(editBtn.dataset.edit));
    if (emp) openRosterForm(emp);
  }
  if (delBtn) {
    const ok = await confirmModal("确认删除该员工？此操作不可恢复。", "删除员工");
    if (!ok) return;
    try {
      await api(`/api/roster/${delBtn.dataset.del}`, { method: "DELETE" });
      toast("已删除员工", "ok");
      loadRoster();
    } catch (err) { toast(err.message, "err"); }
  }
});

/* ---------------- 自动登录 ---------------- */
(function init() {
  const saved = localStorage.getItem(USER_KEY);
  const token = localStorage.getItem(TOKEN_KEY);
  if (saved && token) {
    try { enterApp(JSON.parse(saved)); return; } catch (e) { /* fallthrough */ }
  }
  $("#login-page").classList.remove("hidden");
})();

/* ---------------- 智能助手（统一对话，走后端 /api/chat） ---------------- */
function appendChatMsg(role, html) {
  const log = $("#chat-log");
  const el = document.createElement("div");
  el.className = "chat-msg " + role;
  el.innerHTML = html;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  syncChatWelcome();
  return el;
}
function appendChatTyping() {
  const log = $("#chat-log");
  const el = document.createElement("div");
  el.className = "chat-msg bot";
  el.innerHTML = '<span class="float-typing"><i></i><i></i><i></i></span>';
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

async function sendChat(message, fileObj = null) {
  if ((!message || !message.trim()) && !fileObj) return;
  appendChatMsg("user", fileObj
    ? `📎 ${esc(fileObj.name)}${message ? " · " + esc(message) : ""}`
    : renderText(message.trim()));
  const typing = appendChatTyping();
  const btn = $("#chat-send");
  btn.disabled = true;
  setPetAction("eating");
  try {
    let r;
    if (fileObj) {
      const fd = new FormData();
      if (message && message.trim()) fd.append("message", message.trim());
      if (state.chatConvId) fd.append("conversation_id", state.chatConvId);
      fd.append("file", fileObj);
      r = await api("/api/chat/file", { method: "POST", body: fd });
    } else {
      r = await api("/api/chat", {
        method: "POST",
        json: { message: message, conversation_id: state.chatConvId },
      });
    }
    if (r.conversation_id) state.chatConvId = r.conversation_id;
    typing.innerHTML = renderText(r.reply);
    setPetAction("talk");
    setTimeout(() => { if (_petAction === "talk") setPetAction("idle"); }, 3200);
  } catch (err) {
    typing.innerHTML = "出错了：" + esc(err.message);
    setPetAction("idle");
  } finally {
    btn.disabled = false;
    clearChatFile(); // 发送后清掉已选文件
    const log = $("#chat-log");
    log.scrollTop = log.scrollHeight;
  }
}

$("#chat-welcome").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-q]");
  if (btn) sendChat(btn.dataset.q);
});

/* 📎 智能助手页文件发送（复用 .float-attach / .float-file-chip 样式与 /api/chat/file 接口） */
const chatFileInput = $("#chat-file");
const chatFileChip = $("#chat-file-chip");
const chatFileChipName = $("#chat-file-chip-name");
function clearChatFile() {
  if (!chatFileInput) return;
  chatFileInput.value = "";
  chatFileChip.classList.add("hidden");
  chatFileChipName.textContent = "";
}
function showChatFile(name) {
  chatFileChipName.textContent = name;
  chatFileChip.classList.remove("hidden");
}
$("#chat-attach").addEventListener("click", () => chatFileInput && chatFileInput.click());
chatFileInput.addEventListener("change", () => {
  const f = chatFileInput.files[0];
  if (f) showChatFile(f.name); else clearChatFile();
});
$("#chat-file-chip-del").addEventListener("click", () => clearChatFile());

$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("#chat-input").value;
  const f = chatFileInput.files[0];
  $("#chat-input").value = "";
  if (v.trim() || f) sendChat(v, f || null); // 有文件就走 /api/chat/file
});

function openChatView() {
  const ci = $("#chat-input");
  if (ci) ci.focus();
  syncChatWelcome();
}
function syncChatWelcome() {
  const log = $("#chat-log");
  const wel = $("#chat-welcome");
  if (!log || !wel) return;
  wel.classList.toggle("hidden", !!log.querySelector(".chat-msg"));
}

/* ---------------- 悬浮公司 AI 助手（集合统一智能体） ---------------- */
const floatGreeted = { done: false };

function renderUserCard(user) {
  if (!user) return "";
  const roleText = user.role === "manager" ? "管理者" : "员工";
  const idNo = (user.id !== undefined && user.id !== null) ? user.id : user.emp_id;
  return `<div class="float-idcard">
    <div class="float-idcard-title">当前登录身份</div>
    <div class="float-idcard-row"><span>ID</span><b>${esc(idNo)}</b></div>
    <div class="float-idcard-row"><span>工号</span><b>${esc(user.emp_id)}</b></div>
    <div class="float-idcard-row"><span>姓名</span><b>${esc(user.name)}</b></div>
    <div class="float-idcard-row"><span>部门</span><b>${esc(user.department)}</b></div>
    <div class="float-idcard-row"><span>岗位</span><b>${esc(user.position)}</b></div>
    <div class="float-idcard-row"><span>角色</span><b>${roleText}</b></div>
  </div>`;
}

function floatTogglePanel(show) {
  const p = $("#float-panel");
  const open = (show !== undefined) ? show : p.classList.contains("hidden");
  p.classList.toggle("hidden", !open);
  if (!open) setPetAction("idle");   /* 关闭对话 → 回待机 */
  if (open) {
    /* 恢复用户调整过的尺寸 */
    try {
      const sz = JSON.parse(localStorage.getItem("panel_size") || "");
      if (sz && sz.w && sz.h) { fpanel.style.width = sz.w + "px"; fpanel.style.height = sz.h + "px"; }
    } catch(_){}
    setPetAction("talk");
    const user = state.user;
    if (user) {
      $("#float-sub").textContent = `${esc(user.name)} · ${esc(user.department)} · ${esc(user.position)}`;
      $("#float-emp-id").textContent = esc(user.emp_id ?? "");
    }
    if (!floatGreeted.done) {
      floatGreeted.done = true;
      if (user) {
        appendFloatMsg("bot", renderUserCard(user), true);
        appendFloatMsg("bot", `你好，${esc(user.name)}！我是公司 AI 助手，已识别你的身份。可直接说「生成我的考核报告」「出一份岗位试卷」「阅试卷（需上传）」或自由提问。`);
      } else {
        appendFloatMsg("bot", "你好！我是公司 AI 助手，点下方功能或直接输入。");
      }
    }
    syncPanelToPet();
    $("#float-input").focus();
  }
}

function appendFloatMsg(role, text, isHtml = false) {
  const log = $("#float-log");
  const el = document.createElement("div");
  el.className = "float-msg " + role;
  el.innerHTML = isHtml ? text : esc(text);
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

function appendFloatTyping() {
  const log = $("#float-log");
  const el = document.createElement("div");
  el.className = "float-msg bot";
  el.innerHTML = '<span class="float-typing"><i></i><i></i><i></i></span>';
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

/* 统一发送：文字走 /api/chat（统一智能体）；带文件走 /api/chat/file */
async function askFloat(message, fileObj = null) {
  if (!message || !message.trim() && !fileObj) return;
  if (!fileObj) appendFloatMsg("user", message.trim());
  else appendFloatMsg("user", `📎 ${esc(fileObj.name)}${message ? " · " + message : ""}`);
  const typing = appendFloatTyping();
  $("#float-send").disabled = true;
  setPetAction("eating");   /* 等待回复：吃饭动作 */
  try {
    let r;
    if (fileObj) {
      const fd = new FormData();
      if (message && message.trim()) fd.append("message", message.trim());
      fd.append("file", fileObj);
      r = await api("/api/chat/file", { method: "POST", body: fd });
    } else {
      r = await api("/api/chat", { method: "POST",
        json: { message, conversation_id: state.floatConvId } });
    }
    if (r.conversation_id) state.floatConvId = r.conversation_id;
    typing.innerHTML = renderText(r.reply);
    setPetAction("talk");
    setTimeout(() => { if (_petAction === "talk") setPetAction("idle"); }, 3200);
  } catch (err) {
    typing.innerHTML = "出错了：" + esc(err.message);
    setPetAction("idle");
  } finally {
    $("#float-send").disabled = false;
    clearFloatFile(); // 发送后清掉已选文件
    $("#float-log").scrollTop = $("#float-log").scrollHeight;
  }
}

/* 📎 文件选择与预览条 */
const floatFileInput = $("#float-file");
const floatFileChip = $("#float-file-chip");
const floatFileChipName = $("#float-file-chip-name");

function clearFloatFile() {
  floatFileInput.value = "";
  floatFileChip.classList.add("hidden");
  floatFileChipName.textContent = "";
}

function showFloatFile(name) {
  floatFileChipName.textContent = name;
  floatFileChip.classList.remove("hidden");
}

$("#float-attach").addEventListener("click", () => floatFileInput.click());
floatFileInput.addEventListener("change", () => {
  const f = floatFileInput.files[0];
  if (f) showFloatFile(f.name); else clearFloatFile();
});
$("#float-file-chip-del").addEventListener("click", () => clearFloatFile());

/* ====== 桌宠拖动（替代原悬浮球点击） ====== */
const PET_DRAG_THRESHOLD = 8;
/* 桌宠物理引擎参数（重力下落 + 抛掷弹性反弹，复刻 exe 手感） */
const PET_GRAVITY = 0.0026;        // 重力加速度 px/ms^2
const PET_RESTITUTION = 0.56;      // 垂直（触底）反弹系数
const PET_RESTITUTION_X = 0.62;    // 水平（触边）反弹系数
const PET_FRICTION = 0.84;         // 落地水平摩擦衰减
const PET_MAX_THROW = 2.6;         // 抛掷初速度限幅 px/ms
const bubble = $("#float-bubble");
const fpanel = $("#float-panel");
let _drag = { on: false, grabbing: false, sx: 0, sy: 0, sl: 0, st: 0, moved: false, vx: 0, vy: 0, lastX: 0, lastY: 0, lastT: 0, recent: [] };

/* 桌宠动作状态机（素材：呆啵宠物 · 咕咕嘎嘎 真实动作帧） */
const petImg = $("#pet-img");
const PET_ACTS = {
  idle:      { prefix: "idle",      count: 66,  fps: 120 },
  push:      { prefix: "push",      count: 51,  fps: 60  },
  sleep:     { prefix: "sleep",     count: 82,  fps: 100 },
  dance:     { prefix: "dance",     count: 241, fps: 50  },
  walkleft:  { prefix: "walkleft",  count: 30,  fps: 90  },
  walkright: { prefix: "walkright", count: 31,  fps: 90  },
  patpat:    { prefix: "patpat",    count: 82,  fps: 80  },
  playcar:   { prefix: "playcar",   count: 129, fps: 80  },
  fall:      { prefix: "fall",      count: 51,  fps: 70  },
};
const FRAME_ACTS = ["idle","push","sleep","dance","walkleft","walkright","patpat","playcar","fall"];
const PET_TRICKS = ["dance","patpat","playcar","fall","walkleft","walkright","sleep"];
let _act = "idle";
let _fi = 0;
let _ft = null;
let _trickForceT = null;
let _sleepT = null;
let _trickT = null;

function startPetFrames(action, once) {
  const cfg = PET_ACTS[action] || PET_ACTS.idle;
  clearInterval(_ft); _ft = null; _act = action; _fi = 0;
  clearTimeout(_trickForceT); _trickForceT = null;
  petImg.src = "assets/pet/frames/" + cfg.prefix + "_000.png";
  if (once) {
    _ft = setInterval(() => {
      _fi++;
      if (_fi >= cfg.count) {
        clearInterval(_ft); _ft = null;
        if (_act === action) setPetAction("idle");
        return;
      }
      const n = String(_fi).padStart(3, "0");
      petImg.src = "assets/pet/frames/" + cfg.prefix + "_" + n + ".png";
    }, cfg.fps);
    /* 长动画（如跳舞 241 帧）按完整时长 + 1.5s 缓冲收尾，避免卡在中间帧，也不再提前截断 */
    const durMs = cfg.count * cfg.fps;
    if (durMs > 6000) {
      _trickForceT = setTimeout(() => { if (_act === action) setPetAction("idle"); }, durMs + 1500);
    }
  } else {
    _ft = setInterval(() => {
      _fi = (_fi + 1) % cfg.count;
      const n = String(_fi).padStart(3, "0");
      petImg.src = "assets/pet/frames/" + cfg.prefix + "_" + n + ".png";
    }, cfg.fps);
  }
}

/* 动作切换：talk/eating 复用 idle 帧 + CSS 视觉；其余用各自真实帧集（once=播放一遍后回 idle） */
function setPetAction(a, once) {
  const valid = ["idle","talk","sleep","push","eating","dance","walkleft","walkright","patpat","playcar","fall"];
  if (!valid.includes(a)) a = "idle";
  if (a === "walkleft" || a === "walkright") {
    /* 走动：循环播放走路帧 + 实际水平位移，走到视口边缘自动停下回待机 */
    bubble.className = "float-bubble" + (bubble.classList.contains("hidden") ? " hidden" : "") + " pet-" + a;
    startPetFrames(a, false);
    startWalk(a === "walkleft" ? -1 : 1);
    resetPetSleep();
    return;
  }
  stopWalk(); /* 切到其它动作时停止走动 */
  if (FRAME_ACTS.includes(a)) {
    startPetFrames(a, !!once);
  } else if (_act !== "idle") {
    startPetFrames("idle", false);
  }
  bubble.className = "float-bubble" + (bubble.classList.contains("hidden") ? " hidden" : "") +
    (a !== "idle" ? " pet-" + a : "");
  resetPetSleep();
  if (a === "idle") scheduleRandomTrick(); /* 回到待机后继续排程随机动作 */
}
function resetPetSleep() {
  clearTimeout(_sleepT);   // 不再自动安排 22s 强制睡觉；睡觉改为随机动作池的一员（见 PET_TRICKS）
}
function wakePet() { if (_act === "sleep") setPetAction("idle"); }

/* 随机趣味动作：空闲时偶尔自发跳舞/拍拍/玩车/跌倒/踱步/睡觉 */
function scheduleRandomTrick() {
  clearTimeout(_trickT);
  _trickT = setTimeout(() => {
    /* 仅当真正空闲：待机态、未拖拽、对话框未打开 */
    if (_act === "idle" && !_drag.on && fpanel.classList.contains("hidden")) {
      const t = PET_TRICKS[Math.floor(Math.random() * PET_TRICKS.length)];
      setPetAction(t, true);
    }
    scheduleRandomTrick();
  }, 7000 + Math.random() * 9000);
}

/* 启动：待机循环 + 随机动作调度 */
startPetFrames("idle", false);
resetPetSleep();
scheduleRandomTrick();

(function initPetPos() {
  try {
    const s = JSON.parse(localStorage.getItem("pet_pos") || "null");
    if (s && typeof s.x === "number") {
      bubble.style.right = "auto"; bubble.style.bottom = "auto";
      bubble.style.left = s.x + "px"; bubble.style.top = s.y + "px";
    }
  } catch(_) {}
})();

function syncPanelToPet() {
  const br = bubble.getBoundingClientRect();
  const pw = fpanel.offsetWidth || 480;
  const ph = fpanel.offsetHeight || 480;
  /* 居中于宠物正上方 */
  let pl = br.left + (br.width - pw) / 2;
  let pt = br.top - ph - 8;
  /* 边界保护 */
  if (pl < 10) pl = 10;
  if (pl + pw > innerWidth - 10) pl = innerWidth - pw - 10;
  if (pt < 10) pt = br.bottom + 8;           /* 上方放不下 → 放下方 */
  if (pt + ph > innerHeight - 10) pt = innerHeight - ph - 10;
  fpanel.style.right = "auto"; fpanel.style.bottom = "auto";
  fpanel.style.left = pl + "px"; fpanel.style.top = pt + "px";
}

/* ===== 面板拖拽调整大小（8 方向） ===== */
let _resize = { on: false, dir: "", sx: 0, sy: 0, sw: 0, sh: 0, sl: 0, st: 0 };
const FP_MIN_W = 280, FP_MIN_H = 320;

fpanel.querySelectorAll(".fp-resize").forEach(el => {
  el.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    _resize.on = true;
    _resize.dir = el.dataset.dir || "se";
    _resize.sx = e.clientX; _resize.sy = e.clientY;
    _resize.sw = fpanel.offsetWidth;
    _resize.sh = fpanel.offsetHeight;
    _resize.sl = parseFloat(fpanel.style.left) || fpanel.offsetLeft;
    _resize.st = parseFloat(fpanel.style.top) || fpanel.offsetTop;
    el.setPointerCapture(e.pointerId);
  });
});

document.addEventListener("pointermove", (e) => {
  if (!_resize.on) return;
  const dx = e.clientX - _resize.sx;
  const dy = e.clientY - _resize.sy;
  let nw = _resize.sw, nh = _resize.sh, nl = _resize.sl, nt = _resize.st;
  const d = _resize.dir;
  if (d.includes("e")) nw = Math.max(FP_MIN_W, _resize.sw + dx);
  if (d.includes("w")) { nw = Math.max(FP_MIN_W, _resize.sw - dx); nl = _resize.sl + _resize.sw - nw; }
  if (d.includes("s")) nh = Math.max(FP_MIN_H, _resize.sh + dy);
  if (d.includes("n")) { nh = Math.max(FP_MIN_H, _resize.sh - dy); nt = _resize.st + _resize.sh - nh; }
  /* 视口边界 */
  if (nl < 4) { nl = 4; }
  if (nt < 4) { nt = 4; }
  if (nl + nw > innerWidth - 4) nw = innerWidth - 4 - nl;
  if (nt + nh > innerHeight - 4) nh = innerHeight - 4 - nt;
  fpanel.style.width = nw + "px";
  fpanel.style.height = nh + "px";
  fpanel.style.left = nl + "px";
  fpanel.style.top = nt + "px";
});

document.addEventListener("pointerup", (e) => {
  if (!_resize.on) return;
  _resize.on = false;
  /* 存储用户调整后的尺寸 */
  try { localStorage.setItem("panel_size", JSON.stringify({w:fpanel.offsetWidth,h:fpanel.offsetHeight})); } catch(_){}
});

function savePetPos() {
  try { localStorage.setItem("pet_pos", JSON.stringify({x:parseFloat(bubble.style.left),y:parseFloat(bubble.style.top)})); } catch(_){}
}

/* ===== 桌宠物理引擎：松手后按初速度做抛物运动，触底/触边弹性反弹 ===== */
function clamp(v, lo, hi){ return v < lo ? lo : (v > hi ? hi : v); }
let _physRAF = null;
function startPhysics(vx, vy) {
  stopWalk();                      // 走动与抛物互斥
  _drag.on = true;                 // 物理活动中：阻止随机动作 & 标记占用
  let last = performance.now();
  const step = (now) => {
  let dt = now - last; last = now;
  if (dt > 40) dt = 40;          // 限幅，避免后台标签页回切时大跳
  if (dt < 0) dt = 0;            // 首帧 rAF 时间戳可能早于起始时刻，钳掉防止反向位移
    const W = bubble.offsetWidth, H = bubble.offsetHeight;
    let x = parseFloat(bubble.style.left) || 0;
    let y = parseFloat(bubble.style.top) || 0;
    const vw = innerWidth, vh = innerHeight;
    vy += PET_GRAVITY * dt;
    x += vx * dt; y += vy * dt;
    if (y + H >= vh) { y = vh - H; if (vy > 0) vy = -vy * PET_RESTITUTION; vx *= PET_FRICTION; if (Math.abs(vy) < 0.04) vy = 0; }
    if (y < 0) { y = 0; if (vy < 0) vy = -vy * PET_RESTITUTION; }
    if (x < 0) { x = 0; if (vx < 0) vx = -vx * PET_RESTITUTION_X; }
    if (x + W > vw) { x = vw - W; if (vx > 0) vx = -vx * PET_RESTITUTION_X; }
    bubble.style.left = x + "px"; bubble.style.top = y + "px";
    if (!fpanel.classList.contains("hidden")) syncPanelToPet();
    /* 静止判定：贴地且速度几乎归零 */
    if (y + H >= vh - 1 && Math.abs(vy) < 0.03 && Math.abs(vx) < 0.03) { stopPhysics(); return; }
    _physRAF = requestAnimationFrame(step);
  };
  _physRAF = requestAnimationFrame(step);
}
function stopPhysics() {
  if (_physRAF) { cancelAnimationFrame(_physRAF); _physRAF = null; }
  _drag.on = false;
  savePetPos();
  setPetAction("idle");
}

/* 走动：触发 walkleft/walkright 时让宠物沿该方向实际平移，到视口边缘停下回待机 */
let _walkRAF = null;
function stopWalk() {
  if (_walkRAF) { cancelAnimationFrame(_walkRAF); _walkRAF = null; }
}
function _endWalk() {
  stopWalk();
  _drag.on = false;
  savePetPos();
  setPetAction("idle");
}
function startWalk(dir) {
  stopWalk();
  _drag.on = true;              // 占用中，屏蔽随机动作
  let last = performance.now();
  const speed = 0.16;           // 水平速度 px/ms（约 160px/s）
  const dur = 700 + Math.random() * 1800;  // 随机移动时长 0.7~2.5s → 走的距离随机（约 112~400px）
  const endAt = performance.now() + dur;
  const step = (now) => {
    if (now >= endAt) { _endWalk(); return; }   // 时长到 → 自动停下回待机
    let dt = now - last; last = now;
    if (dt > 40) dt = 40; if (dt < 0) dt = 0;
    const W = bubble.offsetWidth;
    let x = parseFloat(bubble.style.left) || 0;
    const vw = innerWidth;
    x += dir * speed * dt;
    if (x <= 0) { x = 0; _endWalk(); return; }   // 撞到左边缘也提前停
    if (x + W >= vw) { x = vw - W; _endWalk(); return; }
    bubble.style.left = x + "px";
    if (!fpanel.classList.contains("hidden")) syncPanelToPet();
    _walkRAF = requestAnimationFrame(step);
  };
  _walkRAF = requestAnimationFrame(step);
}

bubble.addEventListener("pointerdown", (e) => {
  stopWalk();                     // 走动中再次按下 → 先停下
  if (_physRAF) stopPhysics();     // 物理下落中再次按下 → 先定格再拖
  wakePet();
  _drag.on = true; _drag.grabbing = true; _drag.moved = false; _drag.justClicked = false;
  _drag.pid = e.pointerId;       // 记录 pointerId，仅拖动开始时才 setPointerCapture（避免纯点击吞掉 pointerup）
  _drag.sx = e.clientX; _drag.sy = e.clientY;
  _drag.vx = 0; _drag.vy = 0;
  _drag.lastX = e.clientX; _drag.lastY = e.clientY; _drag.lastT = performance.now();
  const r = bubble.getBoundingClientRect();
  _drag.sl = r.left; _drag.st = r.top;
  bubble.classList.add("dragging");
});
document.addEventListener("pointermove", (e) => {
  if (!_drag.grabbing) return;   // 仅按住拖拽时跟随；物理飞行/hover 时不跟随，避免松手后瞬移回鼠标
  /* 记录瞬时速度（用于松手抛掷）：用上一帧位置差 / 时间差 */
  const nowT = performance.now();
  if (_drag.lastT) {
    const ddt = nowT - _drag.lastT;
    if (ddt > 0) {
      _drag.vx = (e.clientX - _drag.lastX) / ddt;
      _drag.vy = (e.clientY - _drag.lastY) / ddt;
    }
  }
  _drag.lastX = e.clientX; _drag.lastY = e.clientY; _drag.lastT = nowT;
  const dx = e.clientX - _drag.sx, dy = e.clientY - _drag.sy;
  if (Math.abs(dx) > PET_DRAG_THRESHOLD || Math.abs(dy) > PET_DRAG_THRESHOLD) {
    if (!_drag.moved) { setPetAction("push"); try { bubble.setPointerCapture(_drag.pid); } catch(_){} } /* 开始拖动才捕获，指针移出元素也跟手 */
    _drag.moved = true;
  }
  let nx = Math.max(0, Math.min(_drag.sl + dx, innerWidth - bubble.offsetWidth));
  let ny = Math.max(0, Math.min(_drag.st + dy, innerHeight - bubble.offsetHeight));
  bubble.style.right = "auto"; bubble.style.bottom = "auto";
  bubble.style.left = nx + "px"; bubble.style.top = ny + "px";
  if (!fpanel.classList.contains("hidden")) syncPanelToPet();
});
function finishDrag(e) {
  if (!_drag.on) return;
  _drag.grabbing = false;        // 松手即解除"按住"状态，mouse 后续移动不再触发展开跟随
  bubble.classList.remove("dragging");
  try { bubble.releasePointerCapture(e.pointerId); } catch(_){}
  /* 区分"点击"与"真正拖动/抛掷"：人手点击通常有数像素微抖，不能只靠 moved 标志。
     只有 总位移 > 10px 或 松手仍有明显速度 才视为拖动/抛掷 → 走物理；
     其余（含普通点击的微小抖动）一律视为点击 → 直接弹出/收起对话框。 */
  const dx = e.clientX - _drag.sx, dy = e.clientY - _drag.sy;
  const dist = Math.hypot(dx, dy);
  const spd = Math.hypot(_drag.vx, _drag.vy);
  if (_drag.moved && (dist > 10 || spd > 0.5)) {
    let vx = _drag.vx, vy = _drag.vy;
    /* 松手前已停顿（>90ms 无移动）视为轻放，只受重力下落不抛掷 */
    if (performance.now() - (_drag.lastT || 0) > 90) { vx = 0; vy = 0; }
    vx = clamp(vx, -PET_MAX_THROW, PET_MAX_THROW);
    vy = clamp(vy, -PET_MAX_THROW, PET_MAX_THROW);
    setPetAction("idle");
    startPhysics(vx, vy);
  } else {
    _drag.on = false;
    /* 点击：还原到按下位置（避免微抖导致宠物漂移），弹出/收起对话框 */
    bubble.style.left = _drag.sl + "px"; bubble.style.top = _drag.st + "px";
    savePetPos();
    _drag.justClicked = true;
    floatTogglePanel();
  }
}
document.addEventListener("pointerup", finishDrag);
document.addEventListener("pointercancel", finishDrag); /* 指针在窗口外释放时也兜底解除 */

/* 单击兜底：开面板的主体逻辑在 pointerup(finishDrag) 里。此处仅兜底极少数 pointerup 未触发的情况；
   若 finishDrag 已处理本次点击（justClicked=true）则跳过，避免面板被"开→又关"重复切换 */
bubble.addEventListener("click", () => {
  if (_drag.justClicked) { _drag.justClicked = false; return; }  // pointerup 已处理本次点击，避免重复切换
  if (_drag.moved) return;   // 拖动过 → 不是点击，忽略
  floatTogglePanel();        // 兜底：极少数情况下 pointerup 未触发时由 click 打开
});
bubble.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); floatTogglePanel(); }
});
$("#float-close").addEventListener("click", () => floatTogglePanel(false));
$("#float-quick").addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  let q = btn.dataset.q || "";
  q = q.replace("{emp_id}", state.user?.emp_id ?? "")
       .replace("{position}", state.user?.position ?? "");
  if (q) askFloat(q, null); // chip 只发文字
});
$("#float-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("#float-input").value.trim();
  const f = floatFileInput.files[0];
  $("#float-input").value = "";
  if (v || f) askFloat(v, f || null); // 有文件就走 /api/chat/file
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#float-panel").classList.contains("hidden")) floatTogglePanel(false);
});
