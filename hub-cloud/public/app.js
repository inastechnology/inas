const app = document.querySelector("#app");
const identity = document.querySelector("#identity");

function element(tag, options = {}) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = String(options.text);
  if (options.href) node.href = options.href;
  return node;
}

async function api(path) {
  let response;
  try {
    response = await fetch(path, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
  } catch {
    return beginAccess();
  }
  if (response.redirected && new URL(response.url).origin !== window.location.origin) {
    return beginAccess();
  }
  if (response.status === 401 || !(response.headers.get("Content-Type") || "").includes("application/json")) {
    return beginAccess();
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || `HTTP ${response.status}`);
  }
  return body;
}

function beginAccess() {
  const returnPath = `${window.location.pathname}${window.location.search}`;
  window.location.assign(`/api/session/start?return=${encodeURIComponent(returnPath)}`);
  return new Promise(() => {});
}

function panel(title, description) {
  const section = element("section", { className: "panel" });
  section.append(
    element("p", { className: "eyebrow", text: "INAS Cloud Hub" }),
    element("h1", { text: title }),
    element("p", { className: "muted", text: description }),
  );
  return section;
}

async function renderTenantPicker() {
  const result = await api("/api/tenants");
  identity.textContent = result.user.email;
  const section = panel("管理するHubを選択", "所属が確認できたHubだけを表示しています。");
  const grid = element("div", { className: "tenant-grid" });
  for (const tenant of result.tenants) {
    const card = element("a", {
      className: "tenant-card",
      href: `/t/${encodeURIComponent(tenant.public_id)}/`,
    });
    card.append(
      element("strong", { text: tenant.display_name }),
      element("span", { className: "muted", text: `権限: ${tenant.role}` }),
    );
    grid.append(card);
  }
  if (result.tenants.length === 0) {
    grid.append(element("p", { className: "muted", text: "利用可能なHubがありません。管理者へ連絡してください。" }));
  }
  section.append(grid);
  app.replaceChildren(section);
}

function metric(label, value) {
  const card = element("div", { className: "metric" });
  card.append(element("span", { text: label }), element("strong", { text: value }));
  return card;
}

async function renderTenant(publicId) {
  const prefix = `/api/t/${encodeURIComponent(publicId)}`;
  const [me, dashboard, nodes, events] = await Promise.all([
    api(`${prefix}/me`),
    api(`${prefix}/dashboard`),
    api(`${prefix}/nodes`),
    api(`${prefix}/events?limit=30`),
  ]);
  identity.textContent = `${me.user.email} · ${me.user.role}`;
  const section = panel(me.tenant.display_name, "Edge Gatewayから受け取った最新状態を表示します。");
  const metrics = element("div", { className: "metric-grid" });
  metrics.append(
    metric("登録Edge", dashboard.edge_nodes),
    metric("24時間のイベント", dashboard.events_24h),
    metric("MQTT接続中", dashboard.mqtt_connected_nodes),
    metric("保留コマンド", dashboard.pending_commands),
  );
  section.append(metrics, element("h2", { text: "Edge Gateway" }));
  const gatewayList = element("div", { className: "event-list" });
  for (const gateway of nodes.nodes) {
    const card = element("article", { className: "event" });
    const head = element("div", { className: "event-head" });
    head.append(
      element("strong", { text: gateway.label || gateway.node_id }),
      element("span", { text: gateway.status === "active" ? "稼働対象" : "停止" }),
    );
    card.append(
      head,
      element("code", { text: gateway.node_id }),
      element("span", {
        className: "muted",
        text: gateway.last_seen_at
          ? `最終同期: ${new Date(gateway.last_seen_at).toLocaleString("ja-JP")}`
          : "まだ同期していません",
      }),
    );
    gatewayList.append(card);
  }
  if (nodes.nodes.length === 0) {
    gatewayList.append(element("p", { className: "muted", text: "Edge Gatewayはまだ登録されていません。" }));
  }
  section.append(gatewayList, element("h2", { text: "最新イベント" }));
  const list = element("div", { className: "event-list" });
  for (const event of events.events) {
    const card = element("article", { className: "event" });
    const head = element("div", { className: "event-head" });
    head.append(element("strong", { text: event.event_type }), element("time", { text: new Date(event.occurred_at).toLocaleString("ja-JP") }));
    card.append(head, element("code", { text: event.device_id || event.origin_node_id || "Hub" }));
    list.append(card);
  }
  if (events.events.length === 0) {
    list.append(element("p", { className: "muted", text: "まだイベントはありません。" }));
  }
  section.append(list);
  app.replaceChildren(section);
}

async function main() {
  const match = window.location.pathname.match(/^\/t\/([a-z0-9](?:[a-z0-9-]{4,30}[a-z0-9]))(?:\/|$)/);
  if (match) {
    await renderTenant(match[1]);
  } else {
    await renderTenantPicker();
  }
}

main().catch((error) => {
  const section = panel("表示できませんでした", error instanceof Error ? error.message : "不明なエラーです。");
  section.classList.add("error");
  const button = element("button", { text: "再読み込み" });
  button.addEventListener("click", () => window.location.reload());
  section.append(button);
  app.replaceChildren(section);
});
