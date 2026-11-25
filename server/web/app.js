/* Talabat Home — واجهة التطبيق (عربي RTL، بدون مكتبات خارجية). */
(() => {
  "use strict";

  const app = document.getElementById("app");
  const modalRoot = document.getElementById("modal-root");
  const toastRoot = document.getElementById("toast-root");

  const savedBase = localStorage.getItem("talabat_api_base");
  let API_BASE = (
    savedBase !== null ? savedBase : window.TALABAT_API_BASE || ""
  ).replace(/\/$/, "");

  const S = {
    token: localStorage.getItem("talabat_token") || "",
    role: localStorage.getItem("talabat_role") || "",
    screen: "login",
    tab: "orders",
    loginRole: "husband",
    catalog: [],
    orders: [],
    notifications: { unread: 0, latest: null },
    openGroups: new Set([1, "d1"]),
    selectedOrders: new Set(),
    draft: null,
    order: null,
    report: null,
    customGroup: null,
    modal: null,
  };

  let pollTimer = null;
  let lastUnread = 0;

  /* ---------------------- أدوات مساعدة ---------------------- */

  const esc = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const money = (value) =>
    `${Number(value || 0).toLocaleString("en-US", { maximumFractionDigits: 2 })} ج.م`;

  const itemCount = (n) => (n === 1 ? "صنف واحد" : n === 2 ? "صنفان" : `${n} أصناف`);

  const dateText = (iso, withTime = true) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("ar-EG", {
        dateStyle: "medium",
        ...(withTime ? { timeStyle: "short" } : {}),
      });
    } catch {
      return iso;
    }
  };

  const uid = () => `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

  function toast(message, kind = "") {
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.textContent = message;
    toastRoot.appendChild(el);
    setTimeout(() => el.remove(), 3800);
  }

  async function api(path, { method = "GET", body, headers = {}, raw = false } = {}) {
    const init = { method, headers: {} };
    if (S.token) init.headers.Authorization = `Bearer ${S.token}`;
    Object.assign(init.headers, headers);
    if (body instanceof FormData) {
      init.body = body;
    } else if (body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }

    let response;
    try {
      response = await fetch(API_BASE + path, init);
    } catch (error) {
      toast("لا يوجد اتصال بالسيرفر. تحقق من الإنترنت أو رابط السيرفر في الإعدادات.", "error");
      throw error;
    }
    if (response.status === 401) {
      logout();
      throw new Error("انتهت الجلسة");
    }
    if (!response.ok) {
      let detail = "حدث خطأ غير متوقع";
      try {
        const json = await response.json();
        if (json.detail) detail = json.detail;
      } catch (_) {
        /* تجاهل */
      }
      toast(detail, "error");
      throw new Error(detail);
    }
    if (raw) return response;
    if (response.status === 204) return null;
    return response.json();
  }

  const imageUrl = (itemId) =>
    `${API_BASE}/api/images/${itemId}?t=${encodeURIComponent(S.token)}`;

  function thumb(item, small = false) {
    const cls = `thumb${small ? " small" : ""}`;
    if (item && item.has_image) {
      return `<div class="${cls}"><img src="${imageUrl(item.id)}" alt="${esc(item.name)}" loading="lazy"></div>`;
    }
    return `<div class="${cls}"><span class="fallback">${esc(item?.emoji || "🛍️")}</span></div>`;
  }

  function beep() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.28);
      osc.start();
      osc.stop(ctx.currentTime + 0.3);
      osc.onended = () => ctx.close();
    } catch (_) {
      /* الإشعار الصوتي اختياري */
    }
  }

  /* ---------------------- النوافذ المنبثقة ---------------------- */

  function openModal(config) {
    S.modal = config;
    const { title, body, confirmText = "حفظ", danger = false, extra } = config;
    modalRoot.innerHTML = `
      <div class="modal-backdrop" data-action="modal-backdrop">
        <form class="modal" id="modal-form">
          <h3>${esc(title)}</h3>
          <div class="modal-body">${body}</div>
          ${extra || ""}
          <div class="modal-actions">
            <button type="button" class="btn" data-action="modal-close">إلغاء</button>
            <button type="submit" class="btn ${danger ? "btn-danger" : "btn-primary"}">${esc(confirmText)}</button>
          </div>
        </form>
      </div>`;
    const first = modalRoot.querySelector("input, select, textarea");
    if (first) setTimeout(() => first.focus(), 40);
  }

  function closeModal() {
    S.modal = null;
    modalRoot.innerHTML = "";
  }

  function confirmModal(title, message, onConfirm) {
    openModal({
      title,
      body: `<p class="hint">${esc(message)}</p>`,
      confirmText: "تأكيد",
      danger: true,
      onSubmit: async () => {
        closeModal();
        await onConfirm();
      },
    });
  }

  /* ---------------------- تحميل البيانات ---------------------- */

  async function refreshData() {
    const tasks = [api("/api/catalog").then((r) => (S.catalog = r.groups))];
    if (S.role === "husband") {
      tasks.push(api("/api/orders").then((r) => (S.orders = r.orders)));
      tasks.push(api("/api/notifications").then((r) => {
        S.notifications = r;
        lastUnread = r.unread;
      }));
    } else if (S.role === "wife") {
      tasks.push(api("/api/orders").then((r) => (S.orders = r.orders)));
    }
    await Promise.allSettled(tasks);
  }

  async function enterApp() {
    S.screen = "home";
    S.tab = S.role === "husband" ? "orders" : "new";
    S.order = null;
    S.report = null;
    await refreshData();
    if (S.role === "wife" && !S.draft) {
      const pending = S.orders.find((order) => order.status === "draft");
      if (pending) S.draft = loadDraft(pending.id);
    }
    if (S.draft) {
      const valid = new Set(S.catalog.flatMap((g) => g.items.map((i) => i.id)));
      S.draft.rows = S.draft.rows.filter((r) => r.is_custom || valid.has(r.item_id));
      saveDraft();
    }
    render();
    startPolling();
  }

  function logout() {
    S.token = "";
    S.role = "";
    S.screen = "login";
    S.draft = null;
    stopPolling();
    localStorage.removeItem("talabat_token");
    localStorage.removeItem("talabat_role");
    render();
  }

  function startPolling() {
    stopPolling();
    if (S.role !== "husband") return;
    pollTimer = setInterval(poll, 12000);
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  async function poll() {
    if (S.role !== "husband" || !S.token || S.screen !== "home") return;
    try {
      const info = await api("/api/notifications");
      const increased = info.unread > lastUnread && lastUnread >= 0 && info.unread > 0;
      S.notifications = info;
      if (increased && info.latest) {
        beep();
        toast(`طلب جديد رقم #${info.latest.serial}`, "success");
      }
      lastUnread = info.unread;
      updateBadgeDom();
      if (S.tab === "orders") {
        S.orders = (await api("/api/orders")).orders;
        render();
      }
    } catch (_) {
      /* المحاولة القادمة */
    }
  }

  function updateBadgeDom() {
    const count = S.notifications.unread || 0;
    document.querySelectorAll("[data-unread-badge]").forEach((el) => {
      el.hidden = count === 0;
      el.textContent = count > 9 ? "9+" : String(count);
    });
  }

  /* ---------------------- مسودة طلب الزوجة ---------------------- */

  function draftKey() {
    return `talabat_draft_${S.draft.id}`;
  }

  function saveDraft() {
    if (S.draft) localStorage.setItem(draftKey(), JSON.stringify(S.draft));
  }

  function loadDraft(id) {
    try {
      const raw = localStorage.getItem(`talabat_draft_${id}`);
      if (!raw) return null;
      const draft = JSON.parse(raw);
      const valid = new Set(S.catalog.flatMap((g) => g.items.map((i) => i.id)));
      draft.rows = (draft.rows || []).filter((r) => r.is_custom || valid.has(r.item_id));
      return draft;
    } catch {
      return null;
    }
  }

  function setRowQuantity(key, quantity) {
    if (!S.draft) return;
    const row = S.draft.rows.find((r) => r.key === key);
    if (!row) return;
    row.quantity = Math.max(0, Number(quantity) || 0);
    saveDraft();
    updateDraftTotals();
  }

  function draftTotals() {
    const active = (S.draft?.rows || []).filter((r) => r.quantity > 0);
    return {
      count: active.length,
      total: active.reduce((sum, r) => sum + r.quantity * (r.price || 0), 0),
    };
  }

  function updateDraftTotals() {
    const totals = draftTotals();
    document.querySelectorAll("[data-total]").forEach((el) => (el.textContent = money(totals.total)));
    document.querySelectorAll("[data-review-count]").forEach((el) => (el.textContent = itemCount(totals.count)));
  }

  function groupedDraftRows() {
    if (!S.draft) return [];
    const result = [];
    for (const group of S.catalog) {
      const rows = [];
      for (const item of group.items) {
        const row = S.draft.rows.find((r) => r.item_id === item.id);
        if (row) rows.push({ row, name: item.name, price: item.price, emoji: group.emoji, item });
      }
      if (rows.length) result.push({ group, rows, custom: false });
    }
    const custom = S.draft.rows.filter((r) => r.is_custom);
    if (custom.length) {
      result.push({
        group: { id: null, name: "إضافات مطلوبة", emoji: "✨" },
        rows: custom.map((r) => ({ row: r, name: r.name, price: r.price, emoji: "✨", item: null })),
        custom: true,
      });
    }
    return result;
  }

  /* ---------------------- أجزاء الواجهة ---------------------- */

  function topbar() {
    const unread = S.notifications.unread || 0;
    return `
      <header class="topbar">
        <div class="brand">
          <div class="brand-mark">🛒</div>
          <div>
            <div class="brand-title">Talabat Home</div>
            <div class="brand-sub">قائمة مشتريات البيت</div>
          </div>
        </div>
        <div class="top-actions">
          ${S.role === "husband" ? `
            <span class="role-chip">👨 الزوج</span>
            <button class="bell" data-action="bell" aria-label="الإشعارات">🔔
              <span class="badge" data-unread-badge ${unread ? "" : "hidden"}>${unread > 9 ? "9+" : unread}</span>
            </button>` : `<span class="role-chip">👩 الزوجة</span>`}
        </div>
      </header>`;
  }

  function tabs(active) {
    if (S.role === "husband") {
      const unread = S.notifications.unread || 0;
      return `<nav class="tabs">
        <button class="tab ${active === "orders" ? "active" : ""}" data-action="tab" data-tab="orders">📋 الطلبات
          ${unread ? `<span class="mini-badge" data-unread-badge>${unread > 9 ? "9+" : unread}</span>` : ""}
        </button>
        <button class="tab ${active === "catalog" ? "active" : ""}" data-action="tab" data-tab="catalog">🗂️ القوائم</button>
        <button class="tab ${active === "settings" ? "active" : ""}" data-action="tab" data-tab="settings">⚙️ الإعدادات</button>
      </nav>`;
    }
    return `<nav class="tabs">
      <button class="tab ${active === "new" ? "active" : ""}" data-action="tab" data-tab="new">🛍️ طلب جديد</button>
      <button class="tab ${active === "mine" ? "active" : ""}" data-action="tab" data-tab="mine">📄 طلباتي</button>
      <button class="tab ${active === "settings" ? "active" : ""}" data-action="tab" data-tab="settings">⚙️ الإعدادات</button>
    </nav>`;
  }

  function bottomBar(total, label, action, count = null) {
    return `<div class="bottom-bar">
      <div>
        <div class="small muted">الإجمالي التقديري</div>
        <div class="total" data-total>${money(total)}</div>
      </div>
      ${count === null ? "" : `<span class="chip" data-review-count>${itemCount(count)}</span>`}
      <button class="btn btn-primary" data-action="${action}">${label}</button>
    </div>`;
  }

  /* ---------------------- شاشة الدخول ---------------------- */

  function loginView() {
    return `<div class="login-wrap">
      <div class="login-hero">
        <div class="logo">🛒</div>
        <h1>Talabat Home</h1>
        <p>قائمة مشتريات البيت، بين الزوج والزوجة</p>
      </div>
      <div class="card pad stack">
        <div class="role-picker">
          <button class="role-card ${S.loginRole === "husband" ? "selected" : ""}" data-action="pick-role" data-role="husband">
            <span class="face">👨</span><span class="name">الزوج</span>
            <span class="desc">إدارة القوائم وتنفيذ الطلبات</span>
          </button>
          <button class="role-card ${S.loginRole === "wife" ? "selected" : ""}" data-action="pick-role" data-role="wife">
            <span class="face">👩</span><span class="name">الزوجة</span>
            <span class="desc">تجهيز الطلب وإرساله</span>
          </button>
        </div>
        <div class="field">
          <label>رمز الدخول</label>
          <input class="pin-input" name="pin" inputmode="numeric" maxlength="8" autocomplete="off" placeholder="••••" />
        </div>
        <button class="btn btn-primary btn-block" data-action="login">دخول</button>
        <button class="btn btn-ghost btn-block btn-sm" data-action="connection">⚙️ إعدادات الاتصال بالسيرفر</button>
      </div>
      <p class="hint center">كل موبايل يستخدم رمزه الخاص. الرموز تُنشأ عند أول تشغيل للسيرفر.</p>
    </div>`;
  }

  /* ---------------------- القوائم (الزوج) ---------------------- */

  function catalogView() {
    const groups = S.catalog.map((group, index) => {
      const open = S.openGroups.has(group.id);
      const items = group.items.map((item, i) => `
        <div class="item-row">
          ${thumb({ ...item, emoji: group.emoji })}
          <div class="grow">
            <div class="item-name elide">${esc(item.name)}</div>
            <div class="item-price">السعر التقديري: ${money(item.price)}</div>
          </div>
          <div class="actions">
            <button class="icon-btn" data-action="item-up" data-id="${item.id}" ${i === 0 ? "disabled" : ""} title="أعلى">↑</button>
            <button class="icon-btn" data-action="item-down" data-id="${item.id}" ${i === group.items.length - 1 ? "disabled" : ""} title="أسفل">↓</button>
            <button class="icon-btn" data-action="edit-item" data-id="${item.id}" title="تعديل">✏️</button>
            <button class="icon-btn" data-action="upload-image" data-id="${item.id}" title="صورة">🖼️</button>
            ${item.has_image ? `<button class="icon-btn danger" data-action="remove-image" data-id="${item.id}" title="حذف الصورة">🚫</button>` : ""}
            <button class="icon-btn danger" data-action="delete-item" data-id="${item.id}" title="حذف">🗑️</button>
          </div>
        </div>`).join("");

      return `<section class="group-card ${open ? "open" : ""}">
        <div class="group-head" data-action="toggle-group" data-id="${group.id}">
          <span class="gemoji">${esc(group.emoji)}</span>
          <div class="grow">
            <div class="gname">${esc(group.name)}</div>
            <div class="gcount">${itemCount(group.items.length)}</div>
          </div>
          <button class="icon-btn" data-action="group-up" data-id="${group.id}" ${index === 0 ? "disabled" : ""} title="أعلى">↑</button>
          <button class="icon-btn" data-action="group-down" data-id="${group.id}" ${index === S.catalog.length - 1 ? "disabled" : ""} title="أسفل">↓</button>
          <button class="icon-btn" data-action="edit-group" data-id="${group.id}" title="تعديل">✏️</button>
          <button class="icon-btn danger" data-action="delete-group" data-id="${group.id}" title="حذف">🗑️</button>
          <span class="chevron">▼</span>
        </div>
        ${open ? `<div class="group-body">${items || `<p class="hint center">لا توجد أصناف بعد.</p>`}</div>
        <div class="group-foot"><button class="btn btn-ghost btn-sm btn-block" data-action="add-item" data-id="${group.id}">＋ إضافة صنف</button></div>` : ""}
      </section>`;
    }).join("");

    return `${topbar()}${tabs("catalog")}
      <main class="page">
        <button class="btn btn-primary btn-block" data-action="add-group">＋ إضافة مجموعة جديدة</button>
        ${groups || `<div class="empty"><span class="emoji">🗂️</span>لا توجد مجموعات بعد</div>`}
      </main>`;
  }

  /* ---------------------- الطلبات (الزوج) ---------------------- */

  function ordersView() {
    const unread = S.notifications.unread || 0;
    const list = S.orders.map((order) => {
      const checked = S.selectedOrders.has(order.id);
      return `<div class="order-card">
        <input type="checkbox" class="order-check" data-action="select-order" data-id="${order.id}" ${checked ? "checked" : ""} aria-label="تحديد للحذف" />
        <div class="order-main" data-action="open-order" data-id="${order.id}">
          <div class="between">
            <span class="order-serial">طلب #${order.serial}</span>
            <span class="chip ${order.status}">${order.status === "submitted" ? "جديد" : "مغلق"}</span>
          </div>
          <div class="order-meta">${dateText(order.created_at)}</div>
          <div class="order-meta">${itemCount(order.item_count)} · ${money(order.estimated_total)}</div>
        </div>
      </div>`;
    }).join("");

    return `${topbar()}${tabs("orders")}
      <main class="page">
        ${unread ? `<div class="alert">🔔 يوجد ${unread} طلب جديد بانتظار الشراء
          <button class="btn btn-sm btn-primary" data-action="open-unread">فتح</button></div>` : ""}
        <div class="between">
          <div><h2 class="section-title">طلبات الشراء</h2><p class="hint">اضغط على الطلب لفتحه وتحديد ما تم شراؤه</p></div>
          <button class="icon-btn" data-action="refresh-orders" title="تحديث">🔄</button>
        </div>
        ${list || `<div class="empty"><span class="emoji">📋</span>لا توجد طلبات بعد</div>`}
        ${S.selectedOrders.size ? `<button class="btn btn-danger btn-block" data-action="delete-selected">🗑️ حذف المحدد (${S.selectedOrders.size})</button>` : ""}
      </main>`;
  }

  function orderRowsHtml(order, editable) {
    const sections = order.groups.map((group) => `
      <div class="card">
        <div class="pad between">
          <div class="row"><span style="font-size:22px">${esc(group.emoji)}</span><strong>${esc(group.name)}</strong></div>
          <span class="chip">${itemCount(group.rows.length)}</span>
        </div>
        ${group.rows.map((row) => orderRowHtml(row, editable)).join("")}
      </div>`).join("");

    const custom = order.custom_rows.length ? `
      <div class="card">
        <div class="pad between"><strong>✨ إضافات مطلوبة</strong><span class="chip custom">${order.custom_rows.length}</span></div>
        ${order.custom_rows.map((row) => orderRowHtml(row, editable)).join("")}
      </div>` : "";

    return sections + custom;
  }

  function orderRowHtml(row, editable) {
    return `<div class="check-row ${row.purchased ? "done" : ""}">
      ${editable ? `<input type="checkbox" class="big-check" data-action="check-row" data-row="${row.id}" ${row.purchased ? "checked" : ""} aria-label="تم الشراء" />` : `<span>${row.purchased ? "✅" : "⬜"}</span>`}
      ${thumb({ id: row.item_id, name: row.name, has_image: row.has_image }, true)}
      <div class="grow">
        <div class="item-name">${esc(row.name)} ${row.is_custom ? `<span class="chip custom">إضافة</span>` : ""}</div>
        <div class="item-price">${row.quantity} × ${money(row.estimated_price)} = ${money(row.quantity * row.estimated_price)}</div>
        ${row.note ? `<div class="small muted">${esc(row.note)}</div>` : ""}
      </div>
    </div>`;
  }

  function orderView() {
    const order = S.order;
    if (!order) return `${topbar()}<main class="page"><div class="empty">جارٍ التحميل…</div></main>`;
    const editable = S.role === "husband" && order.status === "submitted";
    const summary = order.summary;
    const percent = summary.item_count ? Math.round((summary.purchased_count / summary.item_count) * 100) : 0;

    return `${topbar()}
      <main class="page">
        <div class="detail-head">
          <div class="between">
            <h2 class="section-title">طلب #${order.serial}</h2>
            <span class="chip ${order.status}">${order.status === "submitted" ? "مفتوح" : order.status === "closed" ? "مغلق" : "مسودة"}</span>
          </div>
          <div class="small muted">${dateText(order.created_at)}</div>
          <div class="between small"><span>تم شراء ${summary.purchased_count} من ${summary.item_count}</span><strong>${percent}%</strong></div>
          <div class="progress"><span style="width:${percent}%"></span></div>
        </div>
        ${orderRowsHtml(order, editable)}
        ${order.status === "closed" ? `<button class="btn btn-block" data-action="show-report-from-order">📊 عرض تقرير الطلب</button>` : ""}
      </main>
      ${editable ? bottomBar(summary.estimated_total, "إنهاء الطلب", "close-order") : ""}
      <div style="padding:0 14px 16px"><button class="btn btn-block" data-action="back-home">← رجوع</button></div>`;
  }

  function reportView() {
    const report = S.report;
    if (!report) return orderView();
    const p = report.purchased || [];
    const np = report.not_purchased || [];
    const itemHtml = (row, missed) => `<div class="report-item ${missed ? "missed" : ""}">
      ${missed ? "❌" : "✅"}
      ${thumb({ id: row.item_id, name: row.name, has_image: row.has_image }, true)}
      <div class="grow"><div class="item-name">${esc(row.name)}</div>
      <div class="item-price">الكمية: ${row.quantity} · ${money(row.quantity * row.estimated_price)}</div></div>
    </div>`;

    return `${topbar()}
      <main class="page">
        <div class="detail-head">
          <h2 class="section-title">تقرير الطلب #${report.serial}</h2>
          <div class="small muted">أُغلق في ${dateText(report.closed_at)}</div>
          <div class="stat-grid">
            <div class="stat"><div class="v">${p.length}</div><div class="l">تم شراؤها</div></div>
            <div class="stat"><div class="v">${np.length}</div><div class="l">لم تُشترَ</div></div>
            <div class="stat"><div class="v">${money(report.summary.estimated_total)}</div><div class="l">الإجمالي التقديري</div></div>
          </div>
        </div>
        <div class="card pad"><h3 class="section-title">✅ المنتجات التي تم شراؤها</h3>
          <div class="report-list">${p.length ? p.map((r) => itemHtml(r, false)).join("") : `<p class="hint">لا شيء</p>`}</div>
        </div>
        <div class="card pad"><h3 class="section-title">❌ المنتجات التي لم تُشترَ</h3>
          <div class="report-list">${np.length ? np.map((r) => itemHtml(r, true)).join("") : `<p class="hint">لا شيء — اكتمل الطلب 👏</p>`}</div>
        </div>
        <button class="btn btn-block" data-action="back-home">← رجوع للطلبات</button>
      </main>`;
  }

  /* ---------------------- طلب الزوجة ---------------------- */

  function newOrderView() {
    if (!S.draft) {
      return `${topbar()}${tabs("new")}
        <main class="page">
          <div class="empty" style="padding:50px 18px">
            <span class="emoji">🛍️</span>
            <h2 class="section-title">جاهزة تكتب الطلب؟</h2>
            <p class="hint">سيأخذ الطلب رقماً مسلسلاً وتاريخاً، ثم تختاري الأصناف والكميات وتراجعيه قبل الإرسال.</p>
          </div>
          <button class="btn btn-primary btn-block" data-action="start-order">＋ فتح طلب شراء جديد</button>
        </main>`;
    }

    const totals = draftTotals();
    const groups = S.catalog.map((group) => {
      const open = S.openGroups.has(`d${group.id}`);
      const items = group.items.map((item) => {
        const row = S.draft.rows.find((r) => r.item_id === item.id);
        return `<div class="item-row">
          ${thumb({ ...item, emoji: group.emoji })}
          <div class="grow">
            <div class="item-name elide">${esc(item.name)}</div>
            <div class="item-price">السعر التقديري: ${money(item.price)}</div>
          </div>
          <input type="number" class="qty" min="0" step="1" inputmode="numeric" placeholder="0"
            value="${row ? row.quantity : ""}" data-input="qty" data-key="${row ? row.key : `i${item.id}`}"
            data-item="${item.id}" data-name="${esc(item.name)}" data-price="${item.price}" aria-label="كمية ${esc(item.name)}" />
        </div>`;
      }).join("");

      return `<section class="group-card ${open ? "open" : ""}">
        <div class="group-head" data-action="toggle-group" data-id="d${group.id}">
          <span class="gemoji">${esc(group.emoji)}</span>
          <div class="grow"><div class="gname">${esc(group.name)}</div><div class="gcount">${itemCount(group.items.length)}</div></div>
          <span class="chevron">▼</span>
        </div>
        ${open ? `<div class="group-body">${items || `<p class="hint center">لا توجد أصناف في هذه المجموعة.</p>`}</div>
          <div class="group-foot">
            <button class="btn btn-ghost btn-sm btn-block" data-action="toggle-custom" data-id="${group.id}">＋ إضافة صنف مطلوب (غير موجود بالقائمة)</button>
          </div>
          ${S.customGroup === group.id ? `<div class="group-foot">
            <div class="custom-form grid3" data-group="${group.id}">
              <input name="name" placeholder="اسم الصنف" maxlength="160" />
              <input name="qty" type="number" min="1" step="1" value="1" placeholder="كمية" />
              <input name="price" type="number" min="0" step="0.5" value="0" placeholder="السعر" />
            </div>
            <button class="btn btn-primary btn-sm" data-action="add-custom" data-id="${group.id}">إضافة</button>
          </div>` : ""}` : ""}
      </section>`;
    }).join("");

    const customRows = groupedDraftRows().filter((g) => g.custom).map((g) => `
      <div class="card pad">
        <strong>✨ إضافات مطلوبة</strong>
        ${g.rows.map((r) => `<div class="item-row" style="margin-top:8px">
          <div class="grow"><div class="item-name">${esc(r.name)}</div><div class="item-price">${money(r.price)} × ${r.row.quantity}</div></div>
          <button class="remove-row" data-action="remove-draft-row" data-key="${r.row.key}">✕</button>
        </div>`).join("")}
      </div>`).join("");

    return `${topbar()}${tabs("new")}
      <main class="page">
        <div class="detail-head">
          <div class="between"><h2 class="section-title">طلب #${S.draft.serial}</h2><button class="btn btn-danger btn-sm" data-action="cancel-draft">إلغاء</button></div>
          <div class="small muted">${dateText(S.draft.created_at)}</div>
          <div class="small muted">اكتبي الكمية بجانب كل صنف، وأضيفي أي صنف غير موجود من زر الإضافة أسفل المجموعة.</div>
        </div>
        ${groups || `<div class="empty"><span class="emoji">🗂️</span>لا توجد مجموعات بعد — اطلب من الزوج إضافتها</div>`}
        ${customRows}
      </main>
      ${bottomBar(totals.total, "مراجعة الطلب", "review", totals.count)}`;
  }

  function reviewView() {
    const totals = draftTotals();
    const sections = groupedDraftRows().map((section) => {
      const rows = section.rows.filter((r) => r.row.quantity > 0);
      if (!rows.length) return "";
      return `<div class="card">
        <div class="pad between"><strong>${esc(section.group.emoji)} ${esc(section.group.name)}</strong><span class="chip">${rows.length}</span></div>
        ${rows.map((r) => `<div class="item-row">
          ${thumb({ ...r.item, name: r.name, emoji: section.group.emoji }, true)}
          <div class="grow"><div class="item-name">${esc(r.name)}</div>
            <div class="item-price">${r.row.quantity} × ${money(r.price)}</div></div>
          <div class="line-total">${money(r.row.quantity * r.price)}</div>
        </div>`).join("")}
      </div>`;
    }).join("");

    return `${topbar()}
      <main class="page">
        <div class="detail-head">
          <h2 class="section-title">مراجعة الطلب #${S.draft.serial}</h2>
          <div class="small muted">${dateText(S.draft.created_at)}</div>
          <div class="stat-grid">
            <div class="stat"><div class="v">${totals.count}</div><div class="l">أصناف</div></div>
            <div class="stat"><div class="v">${money(totals.total)}</div><div class="l">الإجمالي التقديري</div></div>
            <div class="stat"><div class="v">${S.catalog.length}</div><div class="l">مجموعات</div></div>
          </div>
        </div>
        ${sections || `<div class="empty"><span class="emoji">🛒</span>لم تختاري أي صنف بعد</div>`}
        <div class="row">
          <button class="btn" data-action="back-draft" style="flex:1">✏️ تعديل الكميات</button>
          <button class="btn btn-primary" data-action="submit-order" style="flex:2" ${totals.count ? "" : "disabled"}>📤 إرسال للزوج</button>
        </div>
      </main>`;
  }

  function successView(serial) {
    return `${topbar()}
      <main class="page">
        <div class="empty" style="padding:55px 18px">
          <span class="emoji">🎉</span>
          <h2 class="section-title">تم إرسال الطلب #${serial}</h2>
          <p class="hint">سيظهر عند الزوج مع إشعار بطلب جديد. يمكنك متابعة حالته من «طلباتي».</p>
        </div>
        <button class="btn btn-primary btn-block" data-action="finish-order">تم</button>
      </main>`;
  }

  function myOrdersView() {
    const list = S.orders.map((order) => `
      <div class="order-card">
        <div class="order-main" data-action="open-order" data-id="${order.id}">
          <div class="between">
            <span class="order-serial">طلب #${order.serial}</span>
            <span class="chip ${order.status}">${order.status === "draft" ? "مسودة" : order.status === "submitted" ? "أُرسل" : "مكتمل"}</span>
          </div>
          <div class="order-meta">${dateText(order.created_at)} · ${itemCount(order.item_count)}</div>
          <div class="order-meta">${money(order.estimated_total)}</div>
        </div>
        ${order.status === "draft" ? `<button class="btn btn-sm btn-primary" data-action="resume-draft" data-id="${order.id}">متابعة</button>
          <button class="icon-btn danger" data-action="delete-draft" data-id="${order.id}" title="حذف المسودة">🗑️</button>` : ""}
      </div>`).join("");

    return `${topbar()}${tabs("mine")}
      <main class="page">
        <h2 class="section-title">طلباتي</h2>
        ${list || `<div class="empty"><span class="emoji">📄</span>لا توجد طلبات بعد</div>`}
        <button class="btn btn-primary btn-block" data-action="start-order">＋ طلب جديد</button>
      </main>`;
  }

  function settingsView() {
    return `${topbar()}${tabs("settings")}
      <main class="page">
        <div class="card pad stack">
          <div class="field">
            <label>رابط السيرفر</label>
            <input name="api_base" value="${esc(API_BASE)}" placeholder="https://talabat-home.onrender.com" />
            <span class="hint">اتركه فارغاً إذا كان التطبيق يُفتح من نفس موقع السيرفر.</span>
          </div>
          <button class="btn btn-primary btn-block" data-action="save-settings">💾 حفظ الرابط</button>
        </div>
        ${S.role === "husband" ? `<div class="card pad stack">
          <h3 class="section-title">تغيير رموز الدخول</h3>
          <div class="field"><label>رمز الزوج الحالي</label><input name="current_pin" type="password" inputmode="numeric" autocomplete="off" /></div>
          <div class="field"><label>من تريد تغيير رمزه؟</label>
            <select name="target_role"><option value="husband">الزوج</option><option value="wife">الزوجة</option></select>
          </div>
          <div class="field"><label>الرمز الجديد (4 أرقام)</label><input name="new_pin" inputmode="numeric" maxlength="8" autocomplete="off" /></div>
          <button class="btn btn-block" data-action="change-pin">تغيير الرمز</button>
        </div>` : ""}
        <button class="btn btn-danger btn-block" data-action="logout">🚪 خروج</button>
      </main>`;
  }

  function render() {
    if (S.screen === "login") {
      app.innerHTML = loginView();
      return;
    }
    if (S.screen === "report") {
      app.innerHTML = reportView();
      return;
    }
    if (S.screen === "success") {
      app.innerHTML = successView(S.order?.serial || "");
      return;
    }
    if (S.screen === "order") {
      app.innerHTML = orderView();
      updateBadgeDom();
      return;
    }
    if (S.screen === "review") {
      app.innerHTML = reviewView();
      return;
    }
    if (S.screen === "home") {
      if (S.role === "husband") {
        app.innerHTML = S.tab === "catalog" ? catalogView() : S.tab === "settings" ? settingsView() : ordersView();
      } else {
        app.innerHTML = S.tab === "mine" ? myOrdersView() : S.tab === "settings" ? settingsView() : newOrderView();
      }
      updateBadgeDom();
      return;
    }
    app.innerHTML = `<div class="empty">جارٍ التحميل…</div>`;
  }

  /* ---------------------- الأحداث ---------------------- */

  app.addEventListener("click", async (event) => {
    const el = event.target.closest("[data-action]");
    if (!el || el.disabled) return;
    const action = el.dataset.action;
    const id = Number(el.dataset.id);

    try {
      switch (action) {
        case "pick-role":
          S.loginRole = el.dataset.role;
          render();
          break;

        case "login": {
          const pin = app.querySelector('[name="pin"]').value.trim();
          const result = await api("/api/auth/login", { method: "POST", body: { role: S.loginRole, pin } });
          S.token = result.token;
          S.role = result.role;
          localStorage.setItem("talabat_token", S.token);
          localStorage.setItem("talabat_role", S.role);
          toast(`أهلاً بك ${result.display_name}`, "success");
          await enterApp();
          break;
        }

        case "connection":
          openModal({
            title: "إعدادات الاتصال",
            body: `<div class="field"><label>رابط السيرفر</label><input name="base" value="${esc(API_BASE)}" placeholder="https://talabat-home.onrender.com" />
              <span class="hint">اتركه فارغاً إذا كان التطبيق مفتوحاً من نفس موقع السيرفر.</span></div>`,
            onSubmit: (form) => {
              API_BASE = new FormData(form).get("base").trim().replace(/\/$/, "");
              localStorage.setItem("talabat_api_base", API_BASE);
              closeModal();
              toast("تم حفظ رابط السيرفر", "success");
            },
          });
          break;

        case "tab":
          S.tab = el.dataset.tab;
          if (S.tab === "orders") {
            const info = await api("/api/notifications");
            S.notifications = info;
            lastUnread = info.unread;
            await api("/api/notifications/seen", { method: "POST" });
            S.notifications.unread = 0;
            updateBadgeDom();
            S.orders = (await api("/api/orders")).orders;
          }
          render();
          break;

        case "bell":
          S.tab = "orders";
          el.dataset.tab = "orders";
          S.notifications = await api("/api/notifications");
          lastUnread = S.notifications.unread;
          await api("/api/notifications/seen", { method: "POST" });
          S.notifications.unread = 0;
          S.orders = (await api("/api/orders")).orders;
          render();
          break;

        case "toggle-group": {
          const key = el.dataset.id;
          if (S.openGroups.has(key)) S.openGroups.delete(key);
          else S.openGroups.add(key);
          render();
          break;
        }

        case "add-group":
          openModal({
            title: "مجموعة جديدة",
            body: `<div class="field"><label>اسم المجموعة</label><input name="name" required maxlength="120" placeholder="مثال: مكانه؟" /></div>
              <div class="field"><label>الرمز (إيموجي اختياري)</label><input name="emoji" maxlength="6" value="🛒" /></div>`,
            onSubmit: async (form) => {
              const data = new FormData(form);
              await api("/api/groups", {
                method: "POST",
                body: {
                  name: data.get("name").trim(),
                  emoji: (data.get("emoji") || "🛒").trim() || "🛒",
                  sort_order: S.catalog.length,
                },
              });
              closeModal();
              await refreshData();
              render();
              toast("تمت إضافة المجموعة", "success");
            },
          });
          break;

        case "edit-group": {
          const group = S.catalog.find((g) => g.id === id);
          openModal({
            title: "تعديل المجموعة",
            body: `<div class="field"><label>الاسم</label><input name="name" required value="${esc(group.name)}" /></div>
              <div class="field"><label>الرمز</label><input name="emoji" maxlength="6" value="${esc(group.emoji)}" /></div>`,
            onSubmit: async (form) => {
              const data = new FormData(form);
              await api(`/api/groups/${id}`, { method: "PATCH", body: { name: data.get("name").trim(), emoji: data.get("emoji").trim() } });
              closeModal();
              await refreshData();
              render();
            },
          });
          break;
        }

        case "delete-group":
          confirmModal("حذف المجموعة", "سيتم حذف المجموعة وكل أصنافها. لا يمكن التراجع.", async () => {
            await api(`/api/groups/${id}`, { method: "DELETE" });
            await refreshData();
            render();
          });
          break;

        case "group-up":
        case "group-down": {
          const index = S.catalog.findIndex((g) => g.id === id);
          const other = action === "group-up" ? index - 1 : index + 1;
          if (other < 0 || other >= S.catalog.length) break;
          await api(`/api/groups/${id}`, { method: "PATCH", body: { sort_order: other } });
          await api(`/api/groups/${S.catalog[other].id}`, { method: "PATCH", body: { sort_order: index } });
          await refreshData();
          render();
          break;
        }

        case "add-item": {
          const group = S.catalog.find((g) => g.id === id);
          openModal({
            title: `إضافة صنف إلى ${group.name}`,
            body: `<div class="field"><label>اسم الصنف</label><input name="name" required maxlength="160" /></div>
              <div class="field"><label>السعر التقديري (ج.م)</label><input name="price" type="number" min="0" step="0.5" value="0" /></div>
              <div class="preview-box"><span class="hint">يمكنك رفع صورة PNG شفافة بعد إضافة الصنف من زر 🖼️</span></div>`,
            onSubmit: async (form) => {
              const data = new FormData(form);
              await api("/api/items", {
                method: "POST",
                body: { group_id: id, name: data.get("name").trim(), price: Number(data.get("price")) || 0, sort_order: group.items.length },
              });
              closeModal();
              await refreshData();
              render();
              toast("تمت إضافة الصنف", "success");
            },
          });
          break;
        }

        case "edit-item": {
          const item = S.catalog.flatMap((g) => g.items).find((i) => i.id === id);
          openModal({
            title: "تعديل الصنف",
            body: `<div class="field"><label>الاسم</label><input name="name" required value="${esc(item.name)}" /></div>
              <div class="field"><label>السعر التقديري (ج.م)</label><input name="price" type="number" min="0" step="0.5" value="${item.price}" /></div>
              <div class="field"><label>المجموعة</label><select name="group_id">${S.catalog.map((g) => `<option value="${g.id}" ${g.id === item.group_id ? "selected" : ""}>${esc(g.name)}</option>`).join("")}</select></div>`,
            onSubmit: async (form) => {
              const data = new FormData(form);
              await api(`/api/items/${id}`, {
                method: "PATCH",
                body: { name: data.get("name").trim(), price: Number(data.get("price")) || 0, group_id: Number(data.get("group_id")) },
              });
              closeModal();
              await refreshData();
              render();
            },
          });
          break;
        }

        case "delete-item":
          confirmModal("حذف الصنف", "سيُحذف الصنف من القائمة نهائياً.", async () => {
            await api(`/api/items/${id}`, { method: "DELETE" });
            await refreshData();
            render();
          });
          break;

        case "item-up":
        case "item-down": {
          const group = S.catalog.find((g) => g.items.some((i) => i.id === id));
          const index = group.items.findIndex((i) => i.id === id);
          const other = action === "item-up" ? index - 1 : index + 1;
          if (other < 0 || other >= group.items.length) break;
          await api(`/api/items/${id}`, { method: "PATCH", body: { sort_order: other } });
          await api(`/api/items/${group.items[other].id}`, { method: "PATCH", body: { sort_order: index } });
          await refreshData();
          render();
          break;
        }

        case "upload-image":
          openModal({
            title: "صورة الصنف",
            body: `<div class="field"><label>اختر صورة (PNG بخلفية شفافة أو JPG)</label>
              <input name="file" type="file" accept="image/png,image/jpeg,image/webp" /></div>
              <span class="hint">تُصغّر الصورة تلقائياً وتُحفظ داخل قاعدة البيانات.</span>`,
            onSubmit: async (form) => {
              const file = form.querySelector('input[name="file"]').files[0];
              if (!file) {
                toast("اختر صورة أولاً", "error");
                return;
              }
              const fd = new FormData();
              fd.append("file", file);
              await api(`/api/items/${id}/image`, { method: "POST", body: fd });
              closeModal();
              await refreshData();
              render();
              toast("تم رفع الصورة", "success");
            },
          });
          break;

        case "remove-image":
          confirmModal("حذف الصورة", "ستختفي صورة هذا الصنف من القائمة.", async () => {
            await api(`/api/items/${id}/image`, { method: "DELETE" });
            await refreshData();
            render();
          });
          break;

        case "select-order":
          if (el.checked) S.selectedOrders.add(id);
          else S.selectedOrders.delete(id);
          break;

        case "delete-selected":
          confirmModal("حذف الطلبات", `سيتم حذف ${S.selectedOrders.size} طلب نهائياً لتوفير المساحة.`, async () => {
            await api("/api/orders", { method: "DELETE", body: { ids: [...S.selectedOrders] } });
            S.selectedOrders.clear();
            S.orders = (await api("/api/orders")).orders;
            render();
            toast("تم حذف الطلبات", "success");
          });
          break;

        case "refresh-orders":
          S.notifications = await api("/api/notifications");
          S.orders = (await api("/api/orders")).orders;
          render();
          break;

        case "open-unread":
        case "open-order": {
          const orderId = action === "open-unread" ? S.notifications.latest?.id : id;
          if (!orderId) break;
          S.order = await api(`/api/orders/${orderId}`);
          S.screen = "order";
          if (S.role === "husband" && S.order.status === "submitted") {
            await api("/api/notifications/seen", { method: "POST" });
            S.notifications.unread = 0;
          }
          render();
          break;
        }

        case "check-row": {
          const detail = await api(`/api/orders/${S.order.id}/rows/${el.dataset.row}`, {
            method: "PATCH",
            body: { purchased: el.checked },
          });
          const row = [...S.order.groups.flatMap((g) => g.rows), ...S.order.custom_rows].find((r) => r.id === detail.id);
          if (row) row.purchased = detail.purchased;
          S.order.summary.purchased_count = [...S.order.groups.flatMap((g) => g.rows), ...S.order.custom_rows].filter((r) => r.purchased).length;
          render();
          break;
        }

        case "close-order":
          confirmModal("إغلاق الطلب", "سيُغلق الطلب ويظهر تقرير بالمشتري وغير المشترى.", async () => {
            S.report = await api(`/api/orders/${S.order.id}/close`, { method: "POST" });
            S.screen = "report";
            render();
          });
          break;

        case "show-report-from-order": {
          const detail = S.order;
          const purchased = [...detail.groups.flatMap((g) => g.rows), ...detail.custom_rows].filter((r) => r.purchased);
          const missed = [...detail.groups.flatMap((g) => g.rows), ...detail.custom_rows].filter((r) => !r.purchased);
          S.report = {
            serial: detail.serial,
            closed_at: detail.closed_at,
            purchased,
            not_purchased: missed,
            summary: detail.summary,
          };
          S.screen = "report";
          render();
          break;
        }

        case "back-home":
          S.screen = "home";
          S.order = null;
          S.report = null;
          await refreshData();
          render();
          break;

        case "start-order": {
          const created = await api("/api/orders", { method: "POST" });
          S.draft = { ...created, rows: [] };
          saveDraft();
          S.screen = "home";
          S.tab = "new";
          render();
          break;
        }

        case "cancel-draft":
          confirmModal("إلغاء الطلب", "سيُحذف الطلب المسودة نهائياً.", async () => {
            await api(`/api/orders/${S.draft.id}`, { method: "DELETE" });
            localStorage.removeItem(draftKey());
            S.draft = null;
            render();
          });
          break;

        case "toggle-custom":
          S.customGroup = S.customGroup === id ? null : id;
          render();
          setTimeout(() => app.querySelector(".custom-form input[name=name]")?.focus(), 40);
          break;

        case "add-custom": {
          const form = app.querySelector(`.custom-form[data-group="${id}"]`);
          const name = form.querySelector('input[name="name"]').value.trim();
          const quantity = Number(form.querySelector('input[name="qty"]').value) || 0;
          const price = Number(form.querySelector('input[name="price"]').value) || 0;
          if (!name || quantity <= 0) {
            toast("اكتب اسم الصنف والكمية", "error");
            break;
          }
          S.draft.rows.push({ key: uid(), item_id: null, name, quantity, price, is_custom: true });
          saveDraft();
          S.customGroup = null;
          render();
          break;
        }

        case "remove-draft-row":
          S.draft.rows = S.draft.rows.filter((r) => r.key !== el.dataset.key);
          saveDraft();
          render();
          break;

        case "review":
          S.screen = "review";
          render();
          break;

        case "back-draft":
          S.screen = "home";
          S.tab = "new";
          render();
          break;

        case "submit-order": {
          const rows = (S.draft.rows || []).filter((r) => r.quantity > 0).map((r) => ({
            item_id: r.item_id,
            name: r.is_custom ? r.name : undefined,
            quantity: r.quantity,
            estimated_price: r.price,
            is_custom: r.is_custom,
          }));
          await api(`/api/orders/${S.draft.id}/rows`, { method: "PUT", body: { rows } });
          await api(`/api/orders/${S.draft.id}/submit`, { method: "POST" });
          localStorage.removeItem(draftKey());
          S.order = { serial: S.draft.serial };
          S.draft = null;
          S.screen = "success";
          render();
          break;
        }

        case "finish-order":
          S.screen = "home";
          S.tab = "mine";
          S.order = null;
          S.orders = (await api("/api/orders")).orders;
          render();
          break;

        case "resume-draft": {
          const draft = loadDraft(id);
          if (!draft) {
            toast("تعذّر استعادة المسودة من هذا الجهاز", "error");
            break;
          }
          S.draft = draft;
          S.screen = "home";
          S.tab = "new";
          render();
          break;
        }

        case "delete-draft":
          confirmModal("حذف المسودة", "سيُحذف هذا الطلب المسودة.", async () => {
            await api(`/api/orders/${id}`, { method: "DELETE" });
            localStorage.removeItem(`talabat_draft_${id}`);
            S.orders = (await api("/api/orders")).orders;
            render();
          });
          break;

        case "save-settings": {
          const value = app.querySelector('[name="api_base"]').value.trim().replace(/\/$/, "");
          API_BASE = value;
          localStorage.setItem("talabat_api_base", value);
          toast("تم حفظ الرابط", "success");
          break;
        }

        case "change-pin": {
          const current_pin = app.querySelector('[name="current_pin"]').value.trim();
          const target_role = app.querySelector('[name="target_role"]').value;
          const new_pin = app.querySelector('[name="new_pin"]').value.trim();
          await api("/api/settings/pin", { method: "POST", body: { current_pin, target_role, new_pin } });
          toast("تم تغيير الرمز", "success");
          app.querySelector('[name="current_pin"]').value = "";
          app.querySelector('[name="new_pin"]').value = "";
          break;
        }

        case "logout":
          logout();
          break;

        case "modal-close":
          closeModal();
          break;

        case "modal-backdrop":
          if (event.target === el) closeModal();
          break;

        default:
          break;
      }
    } catch (error) {
      console.error("Talabat action failed:", action, error);
    }
  });

  app.addEventListener("input", (event) => {
    const el = event.target.closest('[data-input="qty"]');
    if (!el || !S.draft) return;
    const key = el.dataset.key;
    let row = S.draft.rows.find((r) => r.key === key);
    if (!row) {
      row = {
        key,
        item_id: Number(el.dataset.item),
        name: el.dataset.name,
        price: Number(el.dataset.price),
        quantity: 0,
        is_custom: false,
      };
      S.draft.rows.push(row);
    }
    setRowQuantity(key, el.value);
  });

  document.addEventListener("submit", (event) => {
    if (event.target.id !== "modal-form" || !S.modal?.onSubmit) return;
    event.preventDefault();
    Promise.resolve(S.modal.onSubmit(event.target)).catch(() => {});
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && S.role === "husband") poll();
  });

  /* ---------------------- بدء التطبيق ---------------------- */

  async function boot() {
    if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
      navigator.serviceWorker.register("sw.js").catch(() => {});
    }
    if (S.token) {
      try {
        const me = await api("/api/me");
        S.role = me.role;
        await enterApp();
        return;
      } catch (_) {
        /* جلسة غير صالحة */
      }
    }
    render();
  }

  boot();
})();
