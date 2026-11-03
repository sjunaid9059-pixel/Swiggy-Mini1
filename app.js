/* SJ Cash Mini App */
(() => {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    try { tg.setHeaderColor("#07070c"); tg.setBackgroundColor("#07070c"); } catch (_) {}
  }

  
  function ripple(e, el) {
    const r = document.createElement("span");
    r.className = "ripple";
    const rect = el.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    r.style.width = r.style.height = size + "px";
    r.style.left = (e.clientX - rect.left - size / 2) + "px";
    r.style.top = (e.clientY - rect.top - size / 2) + "px";
    el.appendChild(r);
    setTimeout(() => r.remove(), 600);
  }

  document.addEventListener("click", (e) => {
    const t = e.target.closest(".qbtn, .seg-btn, .offer-item, .cta, .btn, .tab, .chip, .pill");
    if (!t) return;
    const cs = getComputedStyle(t);
    if (cs.position === "static") t.style.position = "relative";
    ripple(e, t);
  }, true);

  const state = {
    accounts: [],
    limit: 15,
    kind: "ln",
    offerId: 1,
    pendingPhone: null,
    pendingName: "",
  };

  const OFFERS = {
    ln: {
      1: "₹50 Free Cash (min ₹199)",
      2: "₹150 OFF Coupon (min ₹249)",
      3: "₹100 OFF Coupon (min ₹149)",
      4: "Offer 4",
    },
    bf: {
      1: "₹50 FREE Cash (≥ ₹199)",
      2: "₹150 OFF Coupon (≥ ₹249)",
      3: "₹100 OFF + ₹50 FC (≥ ₹249)",
      4: "₹100 OFF Coupon (≥ ₹149)",
    },
    pyo: {
      1: "₹50 FREE Cash (min ₹199)",
      2: "₹150 OFF Coupon (min ₹249)",
      3: "₹130 OFF Coupon (min ₹199)",
      4: "₹100 OFF Coupon (min ₹149)",
    },
    diya: { 1: "Light all Diya links (auto)" },
  };

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (el.hidden = true), 2400);
  }

  function authHeaders() {
    const init = tg?.initData || "";
    return {
      "Content-Type": "application/json",
      "X-Telegram-InitData": init,
    };
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      ...opts,
      headers: { ...authHeaders(), ...(opts.headers || {}) },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      throw new Error(data.msg || data.detail || `HTTP ${res.status}`);
    }
    return data;
  }

  /* tabs */
  $$(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".tab").forEach((b) => b.classList.remove("active"));
      $$(".page").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`#page-${btn.dataset.tab}`).classList.add("active");
    });
  });

  $$(".qbtn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.goto;
      const kind = btn.dataset.kind;
      $$(`.tab[data-tab="${tab}"]`)[0]?.click();
      if (kind) setKind(kind);
    });
  });

  function setKind(kind) {
    state.kind = kind;
    $$("#kindSeg .seg-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.kind === kind);
    });
    renderOffers();
    $("#offerPickWrap").style.display = kind === "diya" ? "none" : "block";
  }

  $$("#kindSeg .seg-btn").forEach((b) => {
    b.addEventListener("click", () => setKind(b.dataset.kind));
  });

  function renderOffers() {
    const map = OFFERS[state.kind] || {};
    const grid = $("#offerGrid");
    grid.innerHTML = "";
    Object.entries(map).forEach(([id, name]) => {
      const btn = document.createElement("button");
      btn.className = "offer-item" + (Number(id) === state.offerId ? " active" : "");
      btn.textContent = `${id}. ${name}`;
      btn.addEventListener("click", () => {
        state.offerId = Number(id);
        renderOffers();
      });
      grid.appendChild(btn);
    });
  }

  function renderAccounts() {
    const list = $("#accountsList");
    const empty = $("#accEmpty");
    list.innerHTML = "";
    $("#statAccounts").textContent = state.accounts.length;
    $("#statLimit").textContent = state.limit;
    if (!state.accounts.length) {
      empty.hidden = false;
    } else {
      empty.hidden = true;
    }
    state.accounts.forEach((a) => {
      const el = document.createElement("div");
      el.className = "acc-card";
      const initials = (a.name || a.mobile || "SJ").slice(0, 2).toUpperCase();
      el.innerHTML = `
        <div class="acc-avatar">${initials}</div>
        <div class="acc-meta">
          <div class="acc-name">${escapeHtml(a.name || "SJ User")}</div>
          <div class="acc-sub">${escapeHtml(a.mobile || "")} · ${escapeHtml(a.customerId || "")}</div>
        </div>
        <div class="acc-actions">
          <button class="chip" data-copy="${a.slot_id}">JSON</button>
          <button class="chip danger" data-rm="${a.slot_id}">Del</button>
        </div>`;
      list.appendChild(el);
    });
    list.querySelectorAll("[data-rm]").forEach((b) => {
      b.addEventListener("click", async () => {
        try {
          await api(`/api/accounts/${b.dataset.rm}`, { method: "DELETE" });
          toast("Removed");
          await loadAccounts();
        } catch (e) {
          toast(e.message);
        }
      });
    });
    list.querySelectorAll("[data-copy]").forEach((b) => {
      b.addEventListener("click", async () => {
        const acc = state.accounts.find((x) => x.slot_id === b.dataset.copy);
        if (!acc) return;
        const clean = {
          mobile: acc.mobile || "",
          name: acc.name || "",
          token: acc.token || "",
          sid: acc.sid || "",
          tid: acc.tid || "",
          deviceId: acc.deviceId || "",
          customerId: acc.customerId || "",
        };
        showSession(clean);
        try {
          await navigator.clipboard.writeText(JSON.stringify(clean, null, 2));
          toast("JSON copied");
        } catch (_) {
          toast("JSON ready below");
        }
      });
    });

    // claim checkboxes
    const sel = $("#accSelect");
    sel.innerHTML = "";
    state.accounts.forEach((a) => {
      const row = document.createElement("label");
      row.className = "acc-check";
      row.innerHTML = `<input type="checkbox" checked value="${a.slot_id}" />
        <span>${escapeHtml(a.name || a.mobile || a.customerId)}</span>`;
      sel.appendChild(row);
    });

    // delete select
    const ds = $("#delAccSelect");
    ds.innerHTML = state.accounts
      .map(
        (a) =>
          `<option value="${a.slot_id}">${escapeHtml(a.name || "")} · ${escapeHtml(a.mobile || a.customerId || "")}</option>`
      )
      .join("");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showSession(obj) {
    $("#sessionPreview").hidden = false;
    $("#sessionJson").textContent = JSON.stringify(obj, null, 2);
  }

  async function loadAccounts() {
    try {
      const data = await api("/api/accounts");
      state.accounts = data.accounts || [];
      state.limit = data.limit || 15;
      renderAccounts();
    } catch (e) {
      toast(e.message);
    }
  }

  $("#btnRefresh")?.addEventListener("click", () => {
    const b = $("#btnRefresh");
    b?.classList.add("spin");
    setTimeout(() => b?.classList.remove("spin"), 700);
    loadAccounts();
    toast("Refreshed");
  });

  $("#btnAddAccount")?.addEventListener("click", () => {
    $("#modalAdd").hidden = false;
  });
  $("#modalClose")?.addEventListener("click", () => {
    $("#modalAdd").hidden = true;
  });
  $("#modalPhone")?.addEventListener("click", () => {
    $("#modalAdd").hidden = true;
    $$(`.tab[data-tab="tools"]`)[0]?.click();
    $("#newPhone")?.focus();
  });
  $("#modalJson")?.addEventListener("click", () => {
    $("#modalAdd").hidden = true;
    $$(`.tab[data-tab="tools"]`)[0]?.click();
    $("#jsonPaste")?.focus();
  });

  $("#btnSendOtp")?.addEventListener("click", async () => {
    const phone = $("#newPhone").value.trim();
    const name = $("#newName").value.trim();
    try {
      const data = await api("/api/login/otp", {
        method: "POST",
        body: JSON.stringify({ phone, name }),
      });
      state.pendingPhone = phone;
      state.pendingName = name || data.preferred_name || "";
      toast("OTP sent");
    } catch (e) {
      toast(e.message);
    }
  });

  $("#btnVerifyOtp")?.addEventListener("click", async () => {
    const otp = $("#newOtp").value.trim();
    try {
      const data = await api("/api/login/verify", {
        method: "POST",
        body: JSON.stringify({
          phone: state.pendingPhone || $("#newPhone").value.trim(),
          otp,
          name: state.pendingName || $("#newName").value.trim(),
        }),
      });
      showSession(data.session);
      toast("Account saved");
      await loadAccounts();
      $$(`.tab[data-tab="accounts"]`)[0]?.click();
    } catch (e) {
      toast(e.message);
    }
  });

  $("#btnSaveJson")?.addEventListener("click", async () => {
    try {
      const raw = $("#jsonPaste").value.trim();
      const data = await api("/api/accounts", {
        method: "POST",
        body: JSON.stringify({ session: JSON.parse(raw) }),
      });
      showSession(data.account);
      toast("Saved");
      await loadAccounts();
    } catch (e) {
      toast(e.message);
    }
  });

  $("#btnCopyJson")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("#sessionJson").textContent);
      toast("Copied");
    } catch (_) {
      toast("Copy failed");
    }
  });

  $("#btnDelOtp")?.addEventListener("click", async () => {
    const slot = $("#delAccSelect").value;
    try {
      await api("/api/delete/request", {
        method: "POST",
        body: JSON.stringify({ slot_id: slot }),
      });
      toast("Delete OTP sent");
    } catch (e) {
      toast(e.message);
    }
  });

  $("#btnDelConfirm")?.addEventListener("click", async () => {
    const slot = $("#delAccSelect").value;
    const otp = $("#delOtpInput").value.trim();
    try {
      await api("/api/delete/confirm", {
        method: "POST",
        body: JSON.stringify({ slot_id: slot, otp }),
      });
      toast("Account archived — login again for fresh JSON");
      await loadAccounts();
    } catch (e) {
      toast(e.message);
    }
  });

  $("#btnClaimAll")?.addEventListener("click", async () => {
    const slots = $$("#accSelect input:checked").map((x) => x.value);
    if (!slots.length) return toast("Select at least one account");
    const log = $("#claimLog");
    const body = $("#claimLogBody");
    log.hidden = false;
    body.textContent = "Starting…\n";
    $("#btnClaimAll").disabled = true;
    $("#btnClaimAll").classList.add("loading");
    try {
      const data = await api("/api/claim", {
        method: "POST",
        body: JSON.stringify({
          kind: state.kind,
          offer_id: state.offerId,
          slot_ids: slots,
        }),
      });
      const lines = (data.results || []).map((r) => {
        const ok = r.result?.ok ? "OK" : "FAIL";
        const extra = r.result?.msg || r.result?.campaign || r.result?.lit || "";
        return `[${ok}] ${r.account} · ${extra}`;
      });
      body.textContent = lines.join("\n") || "No results";
      toast("Claim finished");
    } catch (e) {
      body.textContent += "\n" + e.message;
      toast(e.message);
    } finally {
      $("#btnClaimAll").disabled = false;
      $("#btnClaimAll").classList.remove("loading");
    }
  });

  renderOffers();
  loadAccounts();
  $$(".qbtn").forEach((b) => b.classList.add("anim-in"));
})();
