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
  const tbody = rows.length ? rows.map((r) => `
    <tr><td>${esc(r.work_date)}</td><td>${r.type === "clock_in" ? "上班" : "下班"}</td>
    <td>${fmtTime(r.checkin_time)}</td>
    <td>${r.is_late ? '<span class="tag tag-danger">迟到</span>' : '<span class="tag tag-ok">正常</span>'}</td></tr>`).join("")
    : `<tr class="empty"><td colspan="4">${emptyHTML("暂无打卡记录")}</td></tr>`;
  $("#att-table").innerHTML = `<thead><tr><th>日期</th><th>类型</th><th>时间</th><th>状态</th></tr></thead><tbody>${tbody}</tbody>`;
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
  const tbody = rows.length ? rows.map((r) => {
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
  }).join("") : '<tr class="empty"><td colspan="6">暂无报销记录</td></tr>';
  $("#reimb-table").innerHTML = `<thead><tr><th>单号</th><th>类目</th><th>金额(元)</th><th>状态</th><th>提交时间</th><th>材料信息</th></tr></thead><tbody>${tbody}</tbody>`;
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
  const tbody = rows.length ? rows.map((r) => `
    <tr><td>${esc(r.no)}</td><td>${esc(r.id)}</td><td>${esc(r.name)}</td><td>${esc(r.position)}</td>
      <td style="text-align:right">${money(r.base_salary)}</td>
      <td style="text-align:center">${Number(r.performance_rating || 0).toFixed(2)}</td>
      <td style="text-align:right">${money(r.performance_bonus)}</td>
      <td style="text-align:right">${money(r.allowance)}</td>
      <td style="text-align:right"><b>${money(r.gross_salary)}</b></td></tr>`).join("")
    : `<tr class="empty"><td colspan="9">${emptyHTML("暂无工资核算记录，提交绩效后生成", "完成绩效评估后将自动生成")}</td></tr>`;
  $("#salary-table").innerHTML = `<thead><tr><th>序号</th><th>工号</th><th>姓名</th><th>岗位</th><th>基本工资</th><th>系数</th><th>绩效奖金</th><th>津贴</th><th>应发合计</th></tr></thead><tbody>${tbody}</tbody>`;
}

/* ---------------- 考核 ---------------- */
$("#assess-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const pos = $("#assess-position").value.trim();
  if (!pos) return;
  $("#assess-result").innerHTML = `<div class="card assess-card"><p>查询中…</p></div>`;
  try {
    const r = await api("/api/assessment/query", { method: "POST", json: { position: pos } });
    $("#assess-result").innerHTML = `
      <div class="card assess-card">
        <h4>${esc(pos)}</h4>
        <p>${esc(r.intro || "暂无介绍")}</p>
        <div class="assess-sub">核心能力要求</div>
        <div class="chip-row">${(r.skills || []).map((s) => `<span class="chip">${esc(s)}</span>`).join("") || "<span style='color:var(--ink-3)'>暂无</span>"}</div>
        <div class="assess-sub">管理能力要求</div>
        <div class="chip-row">${(r.management_abilities || []).map((s) => `<span class="chip alt">${esc(s)}</span>`).join("") || "<span style='color:var(--ink-3)'>暂无</span>"}</div>
        <div class="assess-sub">建议发展路径</div>
        <ol style="padding-left:20px;color:var(--ink-2);font-size:13.5px">${(r.suggested_path || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
      </div>`;
  } catch (err) {
    $("#assess-result").innerHTML = `<div class="card assess-card"><p style="color:var(--danger)">${esc(err.message)}</p></div>`;
  }
});

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
      wrap.innerHTML = `<p class="form-tip">暂无考核成绩记录。</p>`;
      return;
    }
    wrap.innerHTML = `
      <div class="table-wrap"><table class="tbl">
        <thead><tr><th>原岗位</th><th>意向岗位</th><th>成绩</th><th>测试时间</th></tr></thead>
        <tbody>${list.map((s) => `
          <tr><td>${esc(s.original_position || "-")}</td>
              <td>${esc(s.target_position || "-")}</td>
              <td>${s.score ?? "-"}</td>
              <td>${s.test_time ? s.test_time.slice(0, 10) : "-"}</td></tr>`).join("")}
        </tbody>
      </table></div>`;
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
    const list = r.scores || [];
    el.innerHTML = head + (list.length
      ? `<tbody>${list.map((s) => `
          <tr><td>${esc(s.name || "-")}</td>
              <td>${s.employee_id}</td>
              <td>${esc(s.original_position || "-")}</td>
              <td>${esc(s.target_position || "-")}</td>
              <td>${s.score ?? "-"}</td>
              <td>${s.test_time ? s.test_time.slice(0, 10) : "-"}</td></tr>`).join("")}
        </tbody>`
      : "");
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
    const tbody = (r.rows || []).length ? r.rows.map((row) => {
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
    }).join("") : '<tr class="empty"><td colspan="8">暂无数据</td></tr>';
    $("#admin-reimb-table").innerHTML = `<thead><tr><th>单号</th><th>员工</th><th>类目</th><th>金额(元)</th><th>状态</th><th>提交时间</th><th>材料信息</th><th>操作</th></tr></thead><tbody>${tbody}</tbody>`;
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
    // (removed: #admin-salary-analysis element not in HTML)
    const tbody = (r.rows || []).length ? r.rows.map((row) => `
      <tr data-id="${esc(row.id)}">
        <td>${esc(row.no)}</td><td>${esc(row.id)}</td><td>${esc(row.name)}</td><td>${esc(row.position || "")}</td>
        <td style="text-align:right">${money(row.base_salary)}</td>
        <td style="text-align:center">${Number(row.performance_rating || 0).toFixed(2)}</td>
        <td style="text-align:right">${money(row.performance_bonus)}</td>
        <td style="text-align:right">${money(row.allowance)}</td>
        <td style="text-align:right"><b>${money(row.gross_salary)}</b></td>
        <td><button class="btn-ghost btn-sm" data-sal-edit="${esc(row.id)}">编辑</button></td>
      </tr>`).join("")
      : `<tr class="empty"><td colspan="10">${emptyHTML("暂无工资数据")}</td></tr>`;
    $("#admin-salary-table").innerHTML = `<thead><tr><th>序号</th><th>工号</th><th>姓名</th><th>岗位</th><th>基本工资</th><th>系数</th><th>绩效奖金</th><th>津贴</th><th>应发合计</th><th>操作</th></tr></thead><tbody>${tbody}</tbody>`;
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
    const tbody = (r.rows || []).length ? r.rows.map((row) => `
      <tr><td>${esc(row.name)}</td><td>${esc(row.position_queried)}</td>
      <td><span class="tag tag-info">${row.count} 次</span></td></tr>`).join("")
      : `<tr class="empty"><td colspan="3">${emptyHTML("暂无岗位查询记录")}</td></tr>`;
    $("#admin-assess-table").innerHTML = `<thead><tr><th>员工</th><th>查询岗位</th><th>次数</th></tr></thead><tbody>${tbody}</tbody>`;
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
    const tbody = rows.map((e) => `
      <tr><td>${e.no}</td><td><b>${esc(e.name)}</b></td><td>${e.emp_id}</td>
      <td>${esc(e.department)}</td><td>${esc(e.position)}</td>
      <td>${(e.permissions || []).map((p) => `<span class="tag tag-gray">${esc(p)}</span>`).join(" ") || "-"}</td>
      <td>${e.role === "manager" ? '<span class="tag tag-info">管理者</span>' : '<span class="tag">员工</span>'}</td>
      <td><div class="review-actions">
        <button class="btn-ghost btn-sm" data-edit="${e.id}">编辑</button>
        <button class="btn-reject" data-del="${e.id}">删除</button>
      </div></td></tr>`).join("");
    $("#roster-table").innerHTML = `<thead><tr><th>序号</th><th>姓名</th><th>工号</th><th>部门</th><th>岗位</th><th>权限范围</th><th>角色</th><th>操作</th></tr></thead><tbody>${tbody}</tbody>`;
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
const chatGreeted = { done: false };

function appendChatMsg(role, html) {
  const log = $("#chat-log");
  const el = document.createElement("div");
  el.className = "chat-msg " + role;
  el.innerHTML = html;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
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

async function sendChat(message) {
  if (!message || !message.trim()) return;
  appendChatMsg("user", renderText(message.trim()));
  const typing = appendChatTyping();
  const btn = $("#chat-send");
  btn.disabled = true;
  try {
    const r = await api("/api/chat", {
      method: "POST",
      json: { message: message, conversation_id: state.chatConvId },
    });
    if (r.conversation_id) state.chatConvId = r.conversation_id;
    typing.innerHTML = renderText(r.reply);
  } catch (err) {
    typing.innerHTML = "出错了：" + esc(err.message);
  } finally {
    btn.disabled = false;
    const log = $("#chat-log");
    log.scrollTop = log.scrollHeight;
  }
}

$("#chat-quick").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-q]");
  if (btn) sendChat(btn.dataset.q);
});
$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("#chat-input").value;
  $("#chat-input").value = "";
  sendChat(v);
});

function openChatView() {
  if (!chatGreeted.done) {
    chatGreeted.done = true;
    const who = state.user ? state.user.name : "";
    appendChatMsg("bot",
      `你好${who ? "，" + esc(who) : ""}！我是公司智能助手，已知道你的身份与权限。<br>可以直接问我：考勤、报销、工资、考核相关问题，对话会一直记住上下文。`);
  }
  const ci = $("#chat-input");
  if (ci) ci.focus();
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
  if (open) {
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
  } catch (err) {
    typing.innerHTML = "出错了：" + esc(err.message);
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

/* 悬浮球事件绑定 */
$("#float-bubble").addEventListener("click", () => floatTogglePanel());
$("#float-bubble").addEventListener("keydown", (e) => {
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
