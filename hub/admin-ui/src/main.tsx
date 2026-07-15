import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";

const rootElement = document.getElementById("installation-layout-root");

if (rootElement) {
  createRoot(rootElement).render(
    <App
      fieldId={rootElement.dataset.fieldId ?? ""}
      fieldName={rootElement.dataset.fieldName ?? "圃場"}
      fieldDetailUrl={rootElement.dataset.fieldDetailUrl ?? "/fields"}
    />,
  );
}
