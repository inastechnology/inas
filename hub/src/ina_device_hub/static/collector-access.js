"use strict";
const config = JSON.parse(document.getElementById("access-config").textContent);
const form = document.getElementById("access-form");
const message = document.getElementById("message");
let editing = null;
let busy = false;
const labels = {active: "有効", expired: "期限切れ", revoked: "停止済み", pending: "発行未完了"};
function notify(text) { message.textContent = text; }
function hideSecret() { document.getElementById("credentials").value = ""; document.getElementById("issued").hidden = true; }
async function call(path = "", body) {
  const response = await fetch(`/local/api/settings/ai-access${path}`, {method: body ? "POST" : "GET", credentials: "same-origin", cache: "no-store", headers: body ? {"Content-Type": "application/json"} : {}, body: body ? JSON.stringify(body) : undefined});
  let data;
  try { data = await response.json(); } catch { throw new Error("接続を確認できませんでした。再読み込みして状態を確認してください。"); }
  if (!response.ok) throw new Error(data.error || "処理を完了できませんでした。");
  return data;
}
function permissions() {
  return {scopes: Array.from(form.querySelectorAll('[name="scope"]:checked'), x => x.value), field_ids: document.getElementById("all-fields").checked ? ["*"] : Array.from(form.querySelectorAll('[name="field"]:checked'), x => x.value)};
}
function resetForm() {
  editing = null; form.reset(); document.getElementById("name").required = true;
  document.getElementById("name-row").hidden = false; document.getElementById("expiry-row").hidden = false;
  document.getElementById("cancel").hidden = true; document.getElementById("editor-heading").textContent = "接続を作成";
  document.getElementById("submit").textContent = "Token を発行";
  document.getElementById("submit").disabled = !config.configured;
  form.querySelectorAll('[name="field"]').forEach(x => { x.disabled = false; });
}
function edit(item) {
  if (busy) return;
  hideSecret(); editing = item.id;
  document.getElementById("editor-heading").textContent = `${item.name} の権限`;
  document.getElementById("name-row").hidden = true; document.getElementById("name").required = false;
  document.getElementById("expiry-row").hidden = true; document.getElementById("cancel").hidden = false;
  document.getElementById("submit").textContent = "権限を保存"; document.getElementById("submit").disabled = false;
  form.querySelectorAll('[name="scope"]').forEach(x => { x.checked = item.scopes.includes(x.value); });
  document.getElementById("all-fields").checked = item.field_ids.includes("*");
  form.querySelectorAll('[name="field"]').forEach(x => { x.checked = item.field_ids.includes(x.value); x.disabled = item.field_ids.includes("*"); });
  form.scrollIntoView({behavior: "smooth"});
}
async function load() {
  const {items} = await call();
  const list = document.getElementById("connections"); list.replaceChildren();
  if (!items.length) { list.textContent = "発行した接続はありません。"; return; }
  for (const item of items) {
    const card = document.createElement("article"); card.className = "connection";
    const title = document.createElement("h3"); title.textContent = item.name;
    const info = document.createElement("p");
    const scopeNames = item.scopes.map(x => x === "records:read" ? "記録" : "画像").join("・");
    const fields = item.field_ids.includes("*") ? "全圃場" : item.field_ids.map(id => Array.from(form.querySelectorAll('[name="field"]')).find(x => x.value === id)?.parentElement.textContent.trim() || "削除された圃場").join("、");
    info.textContent = `${labels[item.status] || "要確認"} / ${fields} / ${scopeNames} / 有効期限 ${new Date(item.expires_at).toLocaleDateString()}`;
    card.append(title, info);
    if (item.cleanup_pending || item.status === "pending") {
      const note = document.createElement("p"); note.textContent = "Hub での取得は停止しています。Cloudflare 側の停止確認が必要です。"; card.append(note);
      const details = document.createElement("details");
      const summary = document.createElement("summary"); summary.textContent = "管理者向けの確認情報";
      const identifier = document.createElement("p"); identifier.textContent = `Cloudflare の Token・ポリシー名: inas-collector-${item.id}`;
      details.append(summary, identifier); card.append(details);
    }
    if (item.status === "active") {
      const button = document.createElement("button"); button.textContent = "権限を変更"; button.onclick = () => edit(item); card.append(button);
    }
    if (item.status !== "revoked" || item.cleanup_pending) {
      const button = document.createElement("button"); button.className = "revoke"; button.textContent = item.cleanup_pending ? "停止を再確認" : "接続を停止";
      button.onclick = async () => {
        if (busy || !window.confirm(`「${item.name}」の接続を停止しますか？`)) return;
        busy = true; button.disabled = true; hideSecret();
        try { const result = await call(`/${encodeURIComponent(item.id)}/revoke`, {}); notify(result.cleanup_pending ? "Hub での取得を停止しました。Cloudflare 側の停止を再確認してください。" : "接続を停止しました。"); resetForm(); await load(); }
        catch (error) { notify(error.message); }
        finally { busy = false; button.disabled = false; }
      }; card.append(button);
    }
    list.append(card);
  }
}
form.addEventListener("submit", async event => {
  event.preventDefault(); if (busy) return;
  const payload = permissions();
  if (!payload.scopes.length || !payload.field_ids.length) { notify("参照する情報と圃場を選んでください。"); return; }
  busy = true; document.getElementById("submit").disabled = true; hideSecret();
  try {
    if (editing) { await call(`/${encodeURIComponent(editing)}/permissions`, payload); notify("権限を保存しました。"); }
    else {
      const result = await call("", {...payload, name: document.getElementById("name").value, days: Number(document.getElementById("days").value)});
      document.getElementById("credentials").value = `CF_ACCESS_CLIENT_ID=${result.client_id}\nCF_ACCESS_CLIENT_SECRET=${result.client_secret}\nINAS_HUB_OPERATIONS_URL=${location.origin}/operations/api/v1\n`;
      document.getElementById("issued").hidden = false; notify("Token を発行しました。接続情報を保存してください。");
    }
    resetForm(); await load();
  } catch (error) { notify(error.message); }
  finally { busy = false; document.getElementById("submit").disabled = !editing && !config.configured; }
});
document.getElementById("all-fields").addEventListener("change", event => { form.querySelectorAll('[name="field"]').forEach(x => { x.disabled = event.target.checked; }); });
document.getElementById("cancel").onclick = () => { if (!busy) resetForm(); };
document.getElementById("hide-secret").onclick = hideSecret;
window.addEventListener("pagehide", hideSecret);
load().catch(error => notify(error.message));
