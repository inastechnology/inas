const printButton = document.querySelector("[data-print-button]");
printButton?.addEventListener("click", () => window.print());

const header = document.querySelector("[data-site-header]");
const updateHeader = () => header?.classList.toggle("scrolled", window.scrollY > 16);
window.addEventListener("scroll", updateHeader, { passive: true });
updateHeader();
