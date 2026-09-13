(() => {
  const get = (object, path) => path.split(".").reduce((value, key) => value?.[key], object);
  window.refreshDeviceThresholdRules = (contexts, config) => {
    document.querySelectorAll("[data-threshold-source-badge]").forEach((badge) => { badge.hidden = true; });
    for (const context of contexts) {
      const rule = context.rule;
      const panel = document.getElementById(`threshold-rule-${rule.id}`);
      if (!panel) continue;
      const key = get(config, rule.source_path) || "first";
      const option = context.options.find((item) => item.key === key);
      const enabled = get(config, rule.enabled_path) === true;
      const threshold = get(config, rule.threshold_path);
      const value = option?.percent;
      const valid = typeof value === "number" && Number.isFinite(value);
      const confirmed = context.supported && context.device_enabled === enabled && context.device_threshold === threshold && context.device_source === key;
      const unit = context.threshold_field.unit || "";
      panel.querySelector("[data-threshold-reading]").textContent = valid ? `${value.toFixed(1)} ${unit}` : "取得できず";
      panel.querySelector("[data-threshold-source-state]").textContent = option?.state || "保存済みの対象は現在の一覧にありません";
      const members = panel.querySelector("[data-threshold-members]");
      members.replaceChildren();
      for (const member of option?.members || []) {
        const item = document.createElement("li");
        const label = `${member.name}${member.location ? `（${member.location}）` : ""}`;
        const measurement = member.enabled && member.percent !== null ? `${member.percent.toFixed(1)} ${unit}` : member.enabled ? "読取エラー" : "停止中";
        item.textContent = `${label}：${measurement}`;
        members.append(item);
        if (member.position !== null) {
          const badge = document.querySelector(`[data-threshold-source-badge="${member.position}"]`);
          if (badge) {
            badge.hidden = false;
            badge.textContent = !enabled ? "判定対象に選択中（見送りOFF）" : !confirmed ? "判定対象に選択中（反映待ち）" : key === "average" ? "判定に使用（平均の対象）" : "判定に使用";
          }
        }
      }
      const comparison = panel.querySelector("[data-threshold-comparison]");
      if (!enabled) comparison.textContent = "水分による見送りはOFFです。予約どおりの運転を設定しています。";
      else if (!Number.isInteger(threshold) || threshold < context.threshold_field.min || threshold > context.threshold_field.max) comparison.textContent = "範囲内のしきい値を入力してください。";
      else if (!valid) comparison.textContent = "選択した値を読み取れない場合は、水分条件では見送らず予約どおり潅水します。";
      else if (value >= threshold) comparison.textContent = `この測定値なら見送り：${value.toFixed(1)}${unit} ≧ ${threshold}${unit}（しきい値）`;
      else comparison.textContent = `この測定値なら水分条件を通過：${value.toFixed(1)}${unit} ＜ ${threshold}${unit}（しきい値）`;
      const applied = panel.querySelector("[data-threshold-applied]");
      applied.textContent = confirmed ? "機器で確認済み" : "機器への反映待ち";
      applied.className = `badge ${confirmed ? "good" : "warn"}`;
    }
  };
})();
