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

  function bindDirtyForm(form) {
    if (!form || form.dataset.statefulBound === "true") return null;
    form.dataset.statefulBound = "true";
    const submit = form.querySelector("[data-stateful-submit]") || form.querySelector("button[type='submit']");
    if (!submit) return null;
    const reason = form.querySelector("[data-stateful-reason]");
    const dependentActions = Array.from(form.querySelectorAll("[data-requires-dirty]"));
    let baseline = formSnapshot(form);
    let busy = false;

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
      if (reason) {
        reason.textContent = stateBlocked ? (submit.dataset.stateReason || "現在の状態では実行できません。") : reasons.join(" ");
        reason.hidden = !stateBlocked && reasons.length === 0;
      }
      form.dataset.formState = busy ? "busy" : !dirty ? "pristine" : !valid ? "invalid" : "ready";
      form.dispatchEvent(new CustomEvent("stateful-action-state", { detail: { dirty, valid, busy, reasons } }));
    };

    form.addEventListener("input", update);
    form.addEventListener("change", update);
    form.addEventListener("submit", (event) => {
      queueMicrotask(() => {
        if (event.defaultPrevented || !form.checkValidity() || submit.dataset.stateBlocked === "true") return;
        busy = true;
        update();
      });
    });
    form.addEventListener("stateful-form-reset", () => {
      baseline = formSnapshot(form);
      busy = false;
      update();
    });
    form.addEventListener("stateful-form-busy", (event) => {
      busy = Boolean(event.detail);
      update();
    });
    update();
    return { update };
  }

  function bindAll(root) {
    root.querySelectorAll("[data-stateful-form]").forEach(bindDirtyForm);
  }

  window.StatefulActions = { bindDirtyForm, bindAll };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => bindAll(document));
  else bindAll(document);
})();
