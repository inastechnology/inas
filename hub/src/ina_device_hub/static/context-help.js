(() => {
  const helpSelector = "details.context-help";
  document.addEventListener("toggle", (event) => {
    const opened = event.target;
    if (!(opened instanceof HTMLDetailsElement) || !opened.matches(helpSelector) || !opened.open) return;
    document.querySelectorAll(`${helpSelector}[open]`).forEach((candidate) => {
      if (candidate !== opened) candidate.open = false;
    });
  }, true);
  document.addEventListener("click", (event) => {
    document.querySelectorAll(`${helpSelector}[open]`).forEach((opened) => {
      if (!opened.contains(event.target)) opened.open = false;
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const opened = document.querySelector(`${helpSelector}[open]`);
    if (!opened) return;
    opened.open = false;
    opened.querySelector("summary")?.focus();
  });
})();
