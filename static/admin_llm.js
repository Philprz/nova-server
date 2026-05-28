"use strict";
(function() {
  const API = "/api/admin/llm";
  const TOKEN_KEY = "nova_llm_admin_token";

  // DOM helpers
  const $ = (id) => document.getElementById(id);
  const show = (el) => el.classList.remove("hidden");
  const hide = (el) => el.classList.add("hidden");
  function flash(elId, msg, kind) {
    const el = $(elId);
    el.className = "flash " + (kind || "info");
    el.textContent = msg;
    show(el);
    if (kind === "success") setTimeout(() => hide(el), 4000);
  }

  // State
  let providers = [];
  let chain = [];
  let chainDirty = false;

  function token() { return sessionStorage.getItem(TOKEN_KEY); }
  function setToken(t) { sessionStorage.setItem(TOKEN_KEY, t); }
  function clearToken() { sessionStorage.removeItem(TOKEN_KEY); }

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({"Content-Type": "application/json"}, opts.headers || {});
    const t = token();
    if (t) opts.headers["X-LLM-Admin-Token"] = t;
    const r = await fetch(API + path, opts);
    if (r.status === 401) {
      clearToken();
      hide($("dashboard-screen")); show($("auth-screen"));
      throw new Error("Session expiree");
    }
    let body = null;
    try { body = await r.json(); } catch { body = null; }
    if (!r.ok) {
      const detail = (body && body.detail) ? body.detail : ("HTTP " + r.status);
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return body;
  }

  // Auth flow
  async function bootstrap() {
    if (token()) {
      try {
        await loadDashboard();
        return;
      } catch (e) { /* token invalide, on retombe */ }
    }
    try {
      const st = await fetch(API + "/auth/status").then(r => r.json());
      if (st.initialized) {
        $("auth-subtitle").textContent = "Connexion au panneau d'administration";
        show($("form-login"));
        hide($("form-setup"));
        hide($("form-reset"));
      } else {
        $("auth-subtitle").textContent = "Premier parametrage";
        hide($("form-login"));
        show($("form-setup"));
        hide($("form-reset"));
      }
    } catch (e) {
      flash("flash", "Erreur reseau : " + e.message, "error");
    }
  }

  $("form-login").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    hide($("flash"));
    try {
      const r = await fetch(API + "/auth/login", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({password: $("login-password").value}),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Echec connexion");
      setToken(data.session_token);
      $("login-password").value = "";
      await loadDashboard();
    } catch (e) { flash("flash", e.message, "error"); }
  });

  $("form-setup").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    hide($("flash"));
    try {
      const r = await fetch(API + "/auth/setup", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          password: $("setup-password").value,
          security_question: $("setup-question").value,
          security_answer: $("setup-answer").value,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Echec setup");
      setToken(data.session_token);
      await loadDashboard();
    } catch (e) { flash("flash", e.message, "error"); }
  });

  $("link-forgot").addEventListener("click", async () => {
    hide($("flash"));
    try {
      const st = await fetch(API + "/auth/status").then(r => r.json());
      if (!st.initialized) {
        flash("flash", "Aucun mot de passe configure.", "info");
        return;
      }
      $("reset-question").textContent = st.security_question || "";
      hide($("form-login")); show($("form-reset"));
    } catch (e) { flash("flash", e.message, "error"); }
  });

  $("link-back-login").addEventListener("click", () => {
    hide($("form-reset")); show($("form-login"));
  });

  $("form-reset").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      const r = await fetch(API + "/auth/reset", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          security_answer: $("reset-answer").value,
          new_password: $("reset-password").value,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Echec reset");
      setToken(data.session_token);
      await loadDashboard();
    } catch (e) { flash("flash", e.message, "error"); }
  });

  $("btn-logout").addEventListener("click", () => {
    clearToken();
    hide($("dashboard-screen"));
    show($("auth-screen"));
    bootstrap();
  });

  // Dashboard
  async function loadDashboard() {
    await Promise.all([loadProviders(), loadConfig()]);
    hide($("auth-screen"));
    show($("dashboard-screen"));
  }

  document.querySelectorAll(".tab").forEach(el => {
    el.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      el.classList.add("active");
      const tab = el.getAttribute("data-tab");
      $("tab-providers").classList.toggle("hidden", tab !== "providers");
      $("tab-config").classList.toggle("hidden", tab !== "config");
    });
  });

  // Providers
  async function loadProviders() {
    try {
      const data = await api("/providers");
      providers = data.providers;
      renderProviders();
      refreshAddProviderDropdown();
    } catch (e) {
      flash("dash-flash", "Erreur chargement providers : " + e.message, "error");
    }
  }

  function renderProviders() {
    const tbody = $("providers-tbody");
    if (!providers.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--gray-400);">Aucun fournisseur. Cliquez sur "+ Ajouter".</td></tr>';
      return;
    }
    tbody.innerHTML = providers.map(p => `
      <tr>
        <td><b>${escapeHtml(p.name)}</b></td>
        <td><span class="pill ${p.api_format === "anthropic" ? "on" : "off"}">${escapeHtml(p.api_format)}</span></td>
        <td class="mono">${escapeHtml(p.base_url)}</td>
        <td class="mono">${escapeHtml(p.api_key_preview)}</td>
        <td>${(p.available_models || []).map(m => '<span class="pill off" style="margin-right:4px;">' + escapeHtml(m) + '</span>').join("")}</td>
        <td><span class="pill ${p.is_active ? "on" : "off"}">${p.is_active ? "actif" : "inactif"}</span></td>
        <td class="actions">
          <button class="btn-ghost" data-act="test" data-id="${p.id}">Tester</button>
          <button class="btn-ghost" data-act="edit" data-id="${p.id}">Modifier</button>
          <button class="btn-ghost" style="color: var(--red);" data-act="del" data-id="${p.id}">Suppr.</button>
        </td>
      </tr>
    `).join("");
    tbody.querySelectorAll("button[data-act]").forEach(btn => {
      btn.addEventListener("click", () => providerAction(btn.dataset.act, parseInt(btn.dataset.id, 10)));
    });
  }

  async function providerAction(act, id) {
    if (act === "test") {
      flash("dash-flash", "Test en cours...", "info");
      try {
        const r = await api("/test/" + id, {method: "POST"});
        flash("dash-flash", (r.ok ? "OK : " : "ECHEC : ") + r.message, r.ok ? "success" : "error");
      } catch (e) { flash("dash-flash", e.message, "error"); }
    } else if (act === "edit") {
      openProviderModal(providers.find(p => p.id === id));
    } else if (act === "del") {
      if (!confirm("Supprimer ce fournisseur ?")) return;
      try {
        await api("/providers/" + id, {method: "DELETE"});
        flash("dash-flash", "Fournisseur supprime", "success");
        await loadProviders();
        await loadConfig();
      } catch (e) { flash("dash-flash", e.message, "error"); }
    }
  }

  $("btn-add-provider").addEventListener("click", () => openProviderModal(null));

  function openProviderModal(p) {
    $("provider-modal-title").textContent = p ? "Modifier le fournisseur" : "Ajouter un fournisseur";
    $("provider-id").value = p ? p.id : "";
    $("provider-name").value = p ? p.name : "";
    $("provider-format").value = p ? p.api_format : "anthropic";
    $("provider-base-url").value = p ? p.base_url : "";
    $("provider-api-key").value = "";
    $("provider-api-key").placeholder = p ? "Laisser vide pour conserver" : "sk-...";
    renderModelsList(p ? (p.available_models || []) : []);
    $("provider-active").checked = p ? p.is_active : true;
    show($("provider-modal"));
  }

  function renderModelsList(models) {
    const list = $("provider-models-list");
    if (!models.length) {
      list.innerHTML = '<div style="font-size: 12px; color: var(--gray-400); padding: 6px 0;">Aucun modele. Cliquez "+ Ajouter un modele" ou "Decouvrir depuis l\'API".</div>';
      return;
    }
    list.innerHTML = models.map((m, i) => `
      <div class="model-line" style="display: flex; gap: 6px; align-items: center;">
        <input type="text" data-model-i="${i}" value="${escapeHtml(m)}" placeholder="ex: claude-sonnet-4-6" style="flex: 1; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px;">
        <button type="button" class="icon-btn" data-model-rm="${i}" style="color: var(--red);" title="Retirer">&times;</button>
      </div>
    `).join("");
    list.querySelectorAll("button[data-model-rm]").forEach(btn => {
      btn.addEventListener("click", () => {
        const i = parseInt(btn.dataset.modelRm, 10);
        const current = collectModelsFromList();
        current.splice(i, 1);
        renderModelsList(current);
      });
    });
  }

  function collectModelsFromList() {
    return Array.from(document.querySelectorAll('#provider-models-list input[data-model-i]'))
      .map(inp => inp.value.trim())
      .filter(Boolean);
  }

  $("btn-add-model-line").addEventListener("click", () => {
    const current = collectModelsFromList();
    current.push("");
    renderModelsList(current);
    // Focus le nouveau champ
    const inputs = document.querySelectorAll('#provider-models-list input[data-model-i]');
    if (inputs.length) inputs[inputs.length - 1].focus();
  });

  $("btn-discover-models").addEventListener("click", async () => {
    const id = $("provider-id").value;
    if (!id) {
      alert("Enregistre d'abord le fournisseur (nom + URL + cle), puis reouvre la modale pour decouvrir les modeles.");
      return;
    }
    const btn = $("btn-discover-models");
    const originalLabel = btn.textContent;
    btn.textContent = "Recuperation...";
    btn.disabled = true;
    try {
      const res = await api(`/providers/${id}/discover-models`, {method: "POST"});
      if (!res.models || !res.models.length) {
        alert("Aucun modele decouvert");
        return;
      }
      // Pre-cocher les modeles deja presents
      const current = new Set(collectModelsFromList());
      const choice = await pickModelsFromDiscover(res.models, current);
      if (choice) renderModelsList(choice);
    } catch (e) {
      alert("Echec decouverte : " + e.message);
    } finally {
      btn.textContent = originalLabel;
      btn.disabled = false;
    }
  });

  // Mini-picker overlay pour selectionner les modeles a importer
  function pickModelsFromDiscover(allModels, preselected) {
    return new Promise(resolve => {
      const overlay = document.createElement("div");
      overlay.className = "modal-backdrop";
      overlay.style.zIndex = "2000";
      overlay.innerHTML = `
        <div class="modal" style="max-width: 560px;">
          <h2>Modeles decouverts (${allModels.length})</h2>
          <p class="subtitle">Coche les modeles a conserver dans la liste du fournisseur.</p>
          <input type="text" id="discover-filter" placeholder="Filtrer..." style="margin-bottom: 10px;">
          <div id="discover-list" style="max-height: 320px; overflow-y: auto; border: 1px solid var(--gray-200); border-radius: 6px; padding: 6px;"></div>
          <div class="modal-actions">
            <button class="btn-secondary" id="discover-cancel">Annuler</button>
            <button class="btn-primary" id="discover-ok">Valider</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);

      const listEl = overlay.querySelector("#discover-list");
      const sorted = [...allModels].sort();

      function renderList(filter) {
        const f = (filter || "").toLowerCase();
        listEl.innerHTML = sorted
          .filter(m => !f || m.toLowerCase().includes(f))
          .map(m => `
            <label style="display: flex; align-items: center; gap: 8px; padding: 4px 6px; cursor: pointer; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px;">
              <input type="checkbox" value="${escapeHtml(m)}" ${preselected.has(m) ? "checked" : ""} style="width: auto; flex: 0;">
              <span>${escapeHtml(m)}</span>
            </label>`).join("");
        listEl.querySelectorAll("input[type=checkbox]").forEach(cb => {
          cb.addEventListener("change", () => {
            if (cb.checked) preselected.add(cb.value);
            else preselected.delete(cb.value);
          });
        });
      }
      renderList("");
      overlay.querySelector("#discover-filter").addEventListener("input", e => renderList(e.target.value));
      overlay.querySelector("#discover-cancel").addEventListener("click", () => {
        document.body.removeChild(overlay);
        resolve(null);
      });
      overlay.querySelector("#discover-ok").addEventListener("click", () => {
        document.body.removeChild(overlay);
        resolve(Array.from(preselected).sort());
      });
    });
  }

  $("btn-cancel-provider").addEventListener("click", () => hide($("provider-modal")));

  function normalizeBaseUrl(v) {
    v = (v || "").trim().replace(/\/+$/, "");
    if (!v) return v;
    if (v.startsWith("https//")) v = "https://" + v.slice(7);
    else if (v.startsWith("http//")) v = "http://" + v.slice(6);
    else if (!/^https?:\/\//i.test(v)) v = "https://" + v;
    return v;
  }

  $("btn-save-provider").addEventListener("click", async () => {
    const id = $("provider-id").value;
    const models = collectModelsFromList();
    const apiKey = $("provider-api-key").value;
    const rawBaseUrl = $("provider-base-url").value;
    const normalizedBaseUrl = normalizeBaseUrl(rawBaseUrl);
    if (normalizedBaseUrl !== rawBaseUrl.trim()) {
      // Mettre a jour le champ pour montrer la correction
      $("provider-base-url").value = normalizedBaseUrl;
    }
    const payload = {
      name: $("provider-name").value.trim(),
      base_url: normalizedBaseUrl,
      api_format: $("provider-format").value,
      available_models: models,
      is_active: $("provider-active").checked,
    };
    try {
      if (id) {
        if (apiKey) payload.api_key = apiKey;
        await api("/providers/" + id, {method: "PUT", body: JSON.stringify(payload)});
      } else {
        if (!apiKey) { alert("Cle API requise pour un nouveau fournisseur"); return; }
        payload.api_key = apiKey;
        await api("/providers", {method: "POST", body: JSON.stringify(payload)});
      }
      hide($("provider-modal"));
      flash("dash-flash", "Fournisseur enregistre", "success");
      await loadProviders();
      await loadConfig();
    } catch (e) { alert("Erreur : " + e.message); }
  });

  // Configuration
  async function loadConfig() {
    try {
      const data = await api("/config");
      chain = data.chain.map(c => ({
        provider_id: c.provider_id,
        model_name: c.model_name,
        provider_name: c.provider_name,
        api_format: c.api_format,
      }));
      chainDirty = false;
      renderChain();
    } catch (e) {
      flash("dash-flash", "Erreur chargement config : " + e.message, "error");
    }
  }

  function renderChain() {
    const ul = $("chain-ul");
    if (!chain.length) {
      ul.innerHTML = '<li style="color: var(--gray-400); text-align: center; padding: 20px;">Aucune entree. Ajoutez le modele principal ci-dessous.</li>';
      return;
    }
    ul.innerHTML = chain.map((c, i) => {
      if (c._editing) return renderChainItemEdit(c, i);
      return renderChainItemView(c, i);
    }).join("");
    ul.querySelectorAll("button[data-act]").forEach(btn => {
      btn.addEventListener("click", () => chainAction(btn.dataset.act, parseInt(btn.dataset.i, 10)));
    });
    // Liaisons specifiques aux entrees en mode edition
    ul.querySelectorAll("select[data-edit-i]").forEach(sel => {
      sel.addEventListener("change", () => onEditSelectChange(parseInt(sel.dataset.editI, 10)));
    });
  }

  function renderChainItemView(c, i) {
    const testHtml = c._testResult
      ? `<div style="margin-left: 40px; margin-top: -4px; padding: 6px 10px; border-radius: 6px; font-size: 12px; ${c._testResult.ok ? "background:#F0FDF4;color:var(--green);" : "background:#FEF2F2;color:var(--red);"}">
          ${c._testResult.ok ? "OK" : "ECHEC"} &middot; ${c._testResult.latency_ms} ms &middot; ${escapeHtml(c._testResult.message)}
         </div>`
      : "";
    return `
      <li class="chain-item-wrap" style="margin-bottom: 8px;">
        <div class="chain-item" style="margin-bottom: 0;">
          <div class="badge ${i === 0 ? "primary" : "fb"}">${i === 0 ? "P" : i}</div>
          <div class="meta">
            <b>${escapeHtml(c.provider_name)} &mdash; ${escapeHtml(c.model_name)}</b>
            <span>${i === 0 ? "Principal" : "Fallback " + i} &middot; format ${escapeHtml(c.api_format)}</span>
          </div>
          <div class="move">
            <button class="icon-btn" data-act="test" data-i="${i}" title="Tester ce couple">&#x2713;</button>
            <button class="icon-btn" data-act="edit" data-i="${i}" title="Modifier">&#x270E;</button>
            <button class="icon-btn" data-act="up" data-i="${i}" ${i === 0 ? "disabled" : ""}>&uarr;</button>
            <button class="icon-btn" data-act="down" data-i="${i}" ${i === chain.length - 1 ? "disabled" : ""}>&darr;</button>
            <button class="icon-btn" data-act="rm" data-i="${i}" style="color: var(--red);">&times;</button>
          </div>
        </div>
        ${testHtml}
      </li>
    `;
  }

  function renderChainItemEdit(c, i) {
    const draftProviderId = c._draftProviderId ?? c.provider_id;
    const draftModel = c._draftModel ?? c.model_name;
    const prov = providers.find(p => p.id === draftProviderId);
    const providerOptions = providers.filter(p => p.is_active).map(p =>
      `<option value="${p.id}" ${p.id === draftProviderId ? "selected" : ""}>${escapeHtml(p.name)}</option>`
    ).join("");
    const modelOptions = ((prov && prov.available_models) || []).map(m =>
      `<option value="${escapeHtml(m)}" ${m === draftModel ? "selected" : ""}>${escapeHtml(m)}</option>`
    ).join("");
    return `
      <li class="chain-item" style="background: #FFFBEB; border-color: #FCD34D;">
        <div class="badge ${i === 0 ? "primary" : "fb"}">${i === 0 ? "P" : i}</div>
        <div class="meta" style="display: flex; gap: 8px; align-items: center;">
          <select data-edit-i="${i}" data-field="provider" style="flex: 1;">${providerOptions}</select>
          <select data-edit-i="${i}" data-field="model" style="flex: 2;">${modelOptions}</select>
        </div>
        <div class="move">
          <button class="icon-btn" data-act="edit-ok" data-i="${i}" style="color: var(--green);" title="Valider">&#x2714;</button>
          <button class="icon-btn" data-act="edit-cancel" data-i="${i}" title="Annuler">&times;</button>
        </div>
      </li>
    `;
  }

  function onEditSelectChange(i) {
    const ul = $("chain-ul");
    const provSel = ul.querySelector(`select[data-edit-i="${i}"][data-field="provider"]`);
    const modelSel = ul.querySelector(`select[data-edit-i="${i}"][data-field="model"]`);
    if (!provSel || !modelSel) return;
    const provId = parseInt(provSel.value, 10);
    chain[i]._draftProviderId = provId;
    // Si on change le provider, regenerer la liste des modeles
    const prov = providers.find(p => p.id === provId);
    const models = (prov && prov.available_models) || [];
    // Si le modele courant n'est plus dans la liste, prendre le premier
    if (!models.includes(modelSel.value)) {
      chain[i]._draftModel = models[0] || "";
      renderChain();
    } else {
      chain[i]._draftModel = modelSel.value;
    }
  }

  async function chainAction(act, i) {
    if (act === "up" && i > 0) {
      [chain[i-1], chain[i]] = [chain[i], chain[i-1]];
      chainDirty = true; renderChain(); return;
    }
    if (act === "down" && i < chain.length - 1) {
      [chain[i+1], chain[i]] = [chain[i], chain[i+1]];
      chainDirty = true; renderChain(); return;
    }
    if (act === "rm") {
      chain.splice(i, 1);
      chainDirty = true; renderChain(); return;
    }
    if (act === "edit") {
      chain[i]._editing = true;
      chain[i]._draftProviderId = chain[i].provider_id;
      chain[i]._draftModel = chain[i].model_name;
      renderChain(); return;
    }
    if (act === "edit-cancel") {
      delete chain[i]._editing;
      delete chain[i]._draftProviderId;
      delete chain[i]._draftModel;
      renderChain(); return;
    }
    if (act === "edit-ok") {
      const newProvId = chain[i]._draftProviderId;
      const newModel = chain[i]._draftModel;
      const prov = providers.find(p => p.id === newProvId);
      if (!prov || !newModel) { alert("Provider/modele invalide"); return; }
      chain[i].provider_id = newProvId;
      chain[i].model_name = newModel;
      chain[i].provider_name = prov.name;
      chain[i].api_format = prov.api_format;
      delete chain[i]._editing;
      delete chain[i]._draftProviderId;
      delete chain[i]._draftModel;
      delete chain[i]._testResult;
      chainDirty = true; renderChain(); return;
    }
    if (act === "test") {
      const c = chain[i];
      c._testResult = {ok: false, message: "Test en cours...", latency_ms: 0};
      renderChain();
      try {
        const res = await api("/test-entry", {
          method: "POST",
          body: JSON.stringify({provider_id: c.provider_id, model_name: c.model_name}),
        });
        c._testResult = res;
      } catch (e) {
        c._testResult = {ok: false, message: e.message, latency_ms: 0};
      }
      renderChain();
      return;
    }
  }

  function refreshAddProviderDropdown() {
    const sel = $("add-provider-id");
    sel.innerHTML = providers.filter(p => p.is_active).map(p =>
      `<option value="${p.id}">${escapeHtml(p.name)}</option>`
    ).join("");
    refreshAddModelDropdown();
  }

  function refreshAddModelDropdown() {
    const pid = parseInt($("add-provider-id").value, 10);
    const prov = providers.find(p => p.id === pid);
    const sel = $("add-model-name");
    if (!prov) { sel.innerHTML = ""; return; }
    sel.innerHTML = (prov.available_models || []).map(m =>
      `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`
    ).join("");
  }

  $("add-provider-id").addEventListener("change", refreshAddModelDropdown);

  $("btn-add-to-chain").addEventListener("click", () => {
    const pid = parseInt($("add-provider-id").value, 10);
    const model = $("add-model-name").value;
    const prov = providers.find(p => p.id === pid);
    if (!prov || !model) return;
    chain.push({
      provider_id: pid, model_name: model,
      provider_name: prov.name, api_format: prov.api_format,
    });
    chainDirty = true;
    renderChain();
  });

  $("btn-reload-config").addEventListener("click", () => loadConfig());

  // Test de la chaine complete
  async function runChainTest(triggerEl) {
    const originalLabel = triggerEl.textContent;
    triggerEl.textContent = "Test en cours...";
    triggerEl.disabled = true;
    const resultsBlock = $("chain-test-results");
    const list = $("chain-test-list");
    show(resultsBlock);
    list.innerHTML = '<li class="chain-item"><div class="meta"><b>Appels en cours...</b><span>Chaque entree est testee avec son modele configure (ping minimal).</span></div></li>';
    document.querySelector('.tab[data-tab="config"]').click();
    try {
      const data = await api("/test-chain", {method: "POST"});
      renderChainTestResults(data);
      flash("dash-flash",
            data.ok ? "Configuration OK : " + data.summary
                    : "Configuration partielle : " + data.summary,
            data.ok ? "success" : "error");
    } catch (e) {
      list.innerHTML = '';
      flash("dash-flash", "Erreur test chaine : " + e.message, "error");
    } finally {
      triggerEl.textContent = originalLabel;
      triggerEl.disabled = false;
    }
  }

  function renderChainTestResults(data) {
    const list = $("chain-test-list");
    if (!data.results || !data.results.length) {
      list.innerHTML = '<li style="color: var(--gray-400); padding: 12px;">Aucune chaine a tester. Sauvegarde la configuration d\'abord.</li>';
      return;
    }
    list.innerHTML = data.results.map(r => {
      const badgeClass = r.ok ? "primary" : "fb";
      const badgeText = r.ok ? "OK" : "KO";
      const badgeStyle = r.ok ? "background: var(--green);"
                              : "background: var(--red);";
      const subColor = r.ok ? "var(--green)" : "var(--red)";
      return `
        <li class="chain-item">
          <div class="badge" style="${badgeStyle}">${badgeText}</div>
          <div class="meta">
            <b>${escapeHtml(r.provider_name)} &mdash; ${escapeHtml(r.model_name)}</b>
            <span>
              ${escapeHtml(r.role)} &middot; ${r.latency_ms} ms &middot;
              <span style="color: ${subColor};">${escapeHtml(r.message)}</span>
            </span>
          </div>
        </li>`;
    }).join("");
  }

  $("btn-test-chain-providers").addEventListener("click", (ev) => runChainTest(ev.currentTarget));
  $("btn-test-chain-config").addEventListener("click", (ev) => runChainTest(ev.currentTarget));

  $("btn-save-config").addEventListener("click", async () => {
    if (!chain.length) {
      flash("dash-flash", "La chaine ne peut pas etre vide.", "error");
      return;
    }
    try {
      await api("/config", {
        method: "PUT",
        body: JSON.stringify({
          chain: chain.map(c => ({provider_id: c.provider_id, model_name: c.model_name})),
        }),
      });
      flash("dash-flash", "Configuration sauvegardee", "success");
      chainDirty = false;
    } catch (e) { flash("dash-flash", e.message, "error"); }
  });

  // Utils
  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, c => (
      {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]
    ));
  }

  // Boot
  bootstrap();
})();
