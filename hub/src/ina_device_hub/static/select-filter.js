(() => {
  const normalize = (value) => String(value || "").normalize("NFKC").toLocaleLowerCase();
  const termsFor = (value) => normalize(value).split(/[\s\u3000]+/).filter(Boolean);

  function initializeSearchableSelect(select) {
    if (!(select instanceof HTMLSelectElement) || select.dataset.searchableReady === "true") return;
    select.dataset.searchableReady = "true";
    select.classList.add("searchable-select-native");

    const wrapper = document.createElement("div");
    wrapper.className = "searchable-select static-searchable-select";
    const control = document.createElement("button");
    control.type = "button";
    control.className = "searchable-select-control";
    control.setAttribute("aria-haspopup", "listbox");
    control.setAttribute("aria-expanded", "false");
    control.setAttribute("aria-label", select.getAttribute("aria-label") || "候補を選択");

    const controlLabel = document.createElement("span");
    const chevron = document.createElement("span");
    chevron.className = "searchable-select-chevron";
    chevron.setAttribute("aria-hidden", "true");
    chevron.textContent = "⌄";
    control.append(controlLabel, chevron);

    const popover = document.createElement("div");
    popover.className = "searchable-select-popover";
    popover.hidden = true;
    const search = document.createElement("label");
    search.className = "searchable-select-search";
    const searchMark = document.createElement("span");
    searchMark.setAttribute("aria-hidden", "true");
    searchMark.textContent = "⌕";
    const input = document.createElement("input");
    input.type = "search";
    input.autocomplete = "off";
    input.placeholder = select.dataset.searchPlaceholder || "候補を検索";
    input.setAttribute("aria-label", `${control.getAttribute("aria-label")}の候補を検索`);
    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "searchable-select-clear";
    clear.title = "検索をクリア";
    clear.setAttribute("aria-label", "検索をクリア");
    clear.textContent = "×";
    clear.hidden = true;
    search.append(searchMark, input, clear);

    const listbox = document.createElement("div");
    const listboxId = `searchable-select-${Math.random().toString(36).slice(2)}`;
    listbox.id = listboxId;
    listbox.className = "searchable-select-options";
    listbox.setAttribute("role", "listbox");
    control.setAttribute("aria-controls", listboxId);
    popover.append(search, listbox);
    wrapper.append(control, popover);
    select.insertAdjacentElement("afterend", wrapper);

    const close = ({ focusControl = false } = {}) => {
      wrapper.classList.remove("open");
      popover.hidden = true;
      control.setAttribute("aria-expanded", "false");
      input.value = "";
      clear.hidden = true;
      if (focusControl) control.focus();
    };

    const syncControl = () => {
      const selected = select.selectedOptions[0];
      controlLabel.textContent = selected?.textContent?.trim() || select.dataset.placeholder || "選択してください";
      controlLabel.classList.toggle("placeholder", !selected || selected.value === "");
      control.disabled = select.disabled;
    };

    const optionRows = () => {
      const rows = [];
      Array.from(select.children).forEach((child) => {
        if (child instanceof HTMLOptionElement) rows.push({ group: "", option: child });
        if (child instanceof HTMLOptGroupElement) {
          Array.from(child.children).forEach((option) => {
            if (option instanceof HTMLOptionElement) rows.push({ group: child.label, option });
          });
        }
      });
      return rows;
    };

    const renderOptions = () => {
      listbox.replaceChildren();
      const terms = termsFor(input.value);
      const visible = optionRows().filter(({ group, option }) => {
        const fixed = option.value === "" || option.dataset.filterFixed === "true" || option.selected;
        const searchable = normalize(`${option.textContent} ${option.value} ${group} ${option.dataset.search || ""}`);
        return fixed || terms.every((term) => searchable.includes(term));
      });
      const groups = new Map();
      visible.forEach((row) => groups.set(row.group, [...(groups.get(row.group) || []), row.option]));

      groups.forEach((options, groupName) => {
        const group = document.createElement("div");
        group.className = "searchable-select-group";
        group.setAttribute("role", "group");
        if (groupName) {
          group.setAttribute("aria-label", groupName);
          const label = document.createElement("span");
          label.className = "searchable-select-group-label";
          label.textContent = groupName;
          group.append(label);
        }
        options.forEach((option) => {
          const button = document.createElement("button");
          button.type = "button";
          button.setAttribute("role", "option");
          button.setAttribute("aria-selected", String(option.selected));
          button.dataset.searchableOption = "";
          button.dataset.value = option.value;
          button.disabled = option.disabled;
          const label = document.createElement("span");
          label.textContent = option.textContent.trim();
          const check = document.createElement("span");
          check.className = "searchable-select-check";
          check.setAttribute("aria-hidden", "true");
          check.textContent = option.selected ? "✓" : "";
          button.append(label, check);
          button.addEventListener("click", () => {
            select.value = option.value;
            select.dispatchEvent(new Event("input", { bubbles: true }));
            select.dispatchEvent(new Event("change", { bubbles: true }));
            syncControl();
            close({ focusControl: true });
          });
          button.addEventListener("keydown", (event) => {
            if (event.key === "Escape") close({ focusControl: true });
            if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
            event.preventDefault();
            const buttons = [...listbox.querySelectorAll("button[data-searchable-option]")];
            const index = buttons.indexOf(button);
            const next = event.key === "ArrowDown" ? buttons[index + 1] : buttons[index - 1];
            (next || (event.key === "ArrowDown" ? buttons[0] : buttons[buttons.length - 1]))?.focus();
          });
          group.append(button);
        });
        listbox.append(group);
      });

      if (!visible.length) {
        const empty = document.createElement("p");
        empty.className = "searchable-select-empty";
        empty.textContent = select.dataset.emptyMessage || "一致する候補はありません。";
        listbox.append(empty);
      }
    };

    const open = () => {
      if (select.disabled) return;
      document.querySelectorAll(".static-searchable-select.open").forEach((other) => {
        if (other !== wrapper) other.querySelector(".searchable-select-control")?.click();
      });
      wrapper.classList.add("open");
      popover.hidden = false;
      control.setAttribute("aria-expanded", "true");
      renderOptions();
      requestAnimationFrame(() => input.focus());
    };

    control.addEventListener("click", () => popover.hidden ? open() : close());
    control.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !popover.hidden) {
        event.preventDefault();
        close({ focusControl: true });
        return;
      }
      if (!["ArrowDown", "Enter", " "].includes(event.key)) return;
      event.preventDefault();
      if (popover.hidden) open();
    });
    input.addEventListener("input", () => {
      clear.hidden = !input.value;
      renderOptions();
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close({ focusControl: true });
      if (event.key !== "ArrowDown") return;
      event.preventDefault();
      listbox.querySelector("button[data-searchable-option]")?.focus();
    });
    clear.addEventListener("click", () => {
      input.value = "";
      clear.hidden = true;
      renderOptions();
      input.focus();
    });
    select.addEventListener("change", syncControl);
    document.addEventListener("pointerdown", (event) => {
      if (!popover.hidden && !wrapper.contains(event.target)) close();
    });
    new MutationObserver(() => {
      syncControl();
      if (!popover.hidden) renderOptions();
    }).observe(select, { childList: true, subtree: true, characterData: true, attributes: true });

    syncControl();
  }

  document.querySelectorAll("select[data-searchable-select]").forEach(initializeSearchableSelect);
})();
