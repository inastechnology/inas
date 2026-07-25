const lightboxSelector = [
  "figure.product-screenshot > a[href]",
  "figure.concept-illustration > a[href]",
].join(",");

function createManualLightbox() {
  const dialog = document.createElement("dialog");
  dialog.className = "manual-lightbox";
  dialog.setAttribute("aria-label", "図を拡大表示");
  dialog.innerHTML = `
    <div class="manual-lightbox__surface">
      <div class="manual-lightbox__toolbar">
        <p class="manual-lightbox__title">図を拡大表示</p>
        <button type="button" class="manual-lightbox__close" aria-label="拡大表示を閉じる">閉じる</button>
      </div>
      <div class="manual-lightbox__viewport">
        <img alt="" />
      </div>
      <p class="manual-lightbox__caption"></p>
    </div>
  `;
  document.body.append(dialog);
  return dialog;
}

let manualLightbox;
let lightboxReturnTarget;

function getManualLightbox() {
  manualLightbox ??= createManualLightbox();
  return manualLightbox;
}

document.addEventListener("click", (event) => {
  const link = event.target.closest?.(lightboxSelector);
  if (link) {
    const image = link.querySelector("img");
    if (!image) return;

    event.preventDefault();
    const dialog = getManualLightbox();
    const caption = link.closest("figure")?.querySelector("figcaption")?.textContent?.trim() ?? "";
    const expandedImage = dialog.querySelector("img");
    expandedImage.src = link.href;
    expandedImage.alt = image.alt;
    dialog.querySelector(".manual-lightbox__caption").textContent = caption;
    lightboxReturnTarget = link;
    dialog.showModal();
    dialog.querySelector(".manual-lightbox__close").focus();
    return;
  }

  const closeButton = event.target.closest?.(".manual-lightbox__close");
  if (closeButton) {
    closeButton.closest("dialog").close();
    return;
  }

  if (event.target.matches?.("dialog.manual-lightbox")) {
    event.target.close();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  for (const link of document.querySelectorAll(lightboxSelector)) {
    link.classList.add("manual-zoomable");
    link.title = "このページ内で拡大";
  }
});

document.addEventListener("close", (event) => {
  if (!event.target.matches?.("dialog.manual-lightbox")) return;
  event.target.querySelector("img").removeAttribute("src");
  lightboxReturnTarget?.focus();
  lightboxReturnTarget = undefined;
}, true);
