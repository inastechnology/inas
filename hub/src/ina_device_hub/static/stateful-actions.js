(function () {
  function formSnapshot(form) {
    const values = [];
    form.querySelectorAll("input, select, textarea").forEach((control, index) => {
      const dataKey = Object.keys(control.dataset)[0];
      const key = control.name || control.id || (dataKey ? `${dataKey}-${index}` : `control-${index}`);
      if (control.type === "checkbox" || control.type === "radio") {
        values.push([key, control.checked ? "1" : "0"]);
        return;
      }
      if (control.type === "file") {
        const files = Array.from(control.files || []).map((file) => [file.name, file.size, file.lastModified]);
        values.push([key, JSON.stringify(files)]);
        return;
      }
      values.push([key, control.value]);
    });
    return JSON.stringify(values);
  }

  function captureFormState(form) {
    return Array.from(form.querySelectorAll("input, select, textarea")).map((control) => ({
      control,
      checked: control.checked,
      value: control.type === "file" ? "" : control.value,
      selected: control instanceof HTMLSelectElement && control.multiple
        ? Array.from(control.options).map((option) => option.selected)
        : null,
    }));
  }

  function restoreFormState(state) {
    const changed = [];
    state.forEach((item) => {
      const control = item.control;
      if (!control?.isConnected) return;
      const before = control.type === "checkbox" || control.type === "radio" ? control.checked : control.value;
      if (control.type === "checkbox" || control.type === "radio") control.checked = item.checked;
      else if (control.type === "file") control.value = "";
      else if (item.selected) Array.from(control.options).forEach((option, index) => { option.selected = item.selected[index]; });
      else control.value = item.value;
      const after = control.type === "checkbox" || control.type === "radio" ? control.checked : control.value;
      if (before !== after) {
        changed.push(control);
        control.dispatchEvent(new Event("input", { bubbles: true }));
        control.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    return changed;
  }

  function feedbackRegion(form, submit) {
    const existing = form.querySelector("[data-stateful-feedback]");
    if (existing) return existing;
    const region = document.createElement("span");
    region.className = "stateful-feedback";
    region.dataset.statefulFeedback = "true";
    region.setAttribute("role", "status");
    region.setAttribute("aria-live", "polite");
    region.hidden = true;
    submit.insertAdjacentElement("beforebegin", region);
    return region;
  }

  function announce(form, message, kind = "info") {
    const region = form?.querySelector("[data-stateful-feedback]");
    if (!region) return;
    region.textContent = message || "";
    region.className = `stateful-feedback ${kind}`;
    region.hidden = !message;
  }

  function bindDirtyForm(form) {
    if (!form || form.dataset.statefulBound === "true") return null;
    form.dataset.statefulBound = "true";
    const submit = form.querySelector("[data-stateful-submit]") || form.querySelector("button[type='submit']");
    if (!submit) return null;
    const reason = form.querySelector("[data-stateful-reason]");
    const dependentActions = Array.from(form.querySelectorAll("[data-requires-dirty]"));
    const feedback = feedbackRegion(form, submit);
    let undo = form.querySelector("[data-stateful-undo]");
    if (!undo) {
      undo = document.createElement("button");
      undo.type = "button";
      undo.className = "stateful-undo";
      undo.dataset.statefulUndo = "true";
      undo.textContent = "変更を元に戻す";
      undo.hidden = true;
      submit.insertAdjacentElement("beforebegin", undo);
    }
    let baselineState = captureFormState(form);
    let baseline = formSnapshot(form);
    let busy = false;
    let restoring = false;

    const update = () => {
      const dirty = formSnapshot(form) !== baseline;
      const valid = form.checkValidity();
      const pristineMessage = form.dataset.pristineMessage || "変更はありません。";
      const invalidMessage = form.dataset.invalidMessage || "必須項目を入力してください。";
      const busyMessage = form.dataset.busyMessage || "処理が完了するまでお待ちください。";
      const reasons = [];
      if (!dirty) reasons.push(pristineMessage);
      if (!valid) reasons.push(invalidMessage);
      if (busy) reasons.push(busyMessage);
      const stateBlocked = submit.dataset.stateBlocked === "true";
      submit.disabled = stateBlocked || reasons.length > 0;
      if (busy) submit.setAttribute("aria-busy", "true");
      else submit.removeAttribute("aria-busy");
      if (busy) form.setAttribute("aria-busy", "true");
      else form.removeAttribute("aria-busy");
      if (!stateBlocked) submit.title = reasons.length ? `実行できません: ${reasons.join(" ")}` : "";
      submit.setAttribute("aria-disabled", submit.disabled ? "true" : "false");
      dependentActions.forEach((button) => {
        const blocked = button.dataset.stateBlocked === "true";
        button.disabled = blocked || !dirty || !valid || busy;
        if (!blocked) button.title = button.disabled ? `実行できません: ${reasons.join(" ")}` : "";
        button.setAttribute("aria-disabled", button.disabled ? "true" : "false");
      });
      undo.hidden = !dirty;
      undo.disabled = busy;
      undo.setAttribute("aria-disabled", busy ? "true" : "false");
      if (reason) {
        reason.textContent = stateBlocked ? (submit.dataset.stateReason || "現在の状態では実行できません。") : reasons.join(" ");
        reason.hidden = !stateBlocked && reasons.length === 0;
      }
      form.dataset.formState = busy ? "busy" : !dirty ? "pristine" : !valid ? "invalid" : "ready";
      form.dispatchEvent(new CustomEvent("stateful-action-state", { detail: { dirty, valid, busy, reasons } }));
    };

    const handleChange = () => {
      if (!restoring && !feedback.hidden) announce(form, "");
      update();
    };
    form.addEventListener("input", handleChange);
    form.addEventListener("change", handleChange);
    undo.addEventListener("click", () => {
      restoring = true;
      const changed = restoreFormState(baselineState);
      restoring = false;
      update();
      announce(form, "変更前の内容に戻しました。", "ok");
      (changed[0] || form.querySelector("input:not([type='hidden']), select, textarea"))?.focus({ preventScroll: true });
    });
    form.addEventListener("submit", (event) => {
      queueMicrotask(() => {
        if (event.defaultPrevented || !form.checkValidity() || submit.dataset.stateBlocked === "true") return;
        busy = true;
        update();
      });
    });
    form.addEventListener("stateful-form-reset", (event) => {
      baselineState = captureFormState(form);
      baseline = formSnapshot(form);
      busy = false;
      update();
      if (event.detail?.message) announce(form, event.detail.message, event.detail.kind || "ok");
    });
    form.addEventListener("stateful-form-busy", (event) => {
      busy = Boolean(event.detail);
      update();
    });
    update();
    return { update, announce: (message, kind) => announce(form, message, kind) };
  }

  function bindAll(root) {
    root.querySelectorAll("[data-stateful-form]").forEach(bindDirtyForm);
  }

  window.StatefulActions = { bindDirtyForm, bindAll, announce };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => bindAll(document));
  else bindAll(document);
})();
