import { createRoot } from "react-dom/client";

import { App } from "./App";
import { PlantCalendarPage } from "./plant-calendar/PlantCalendarPage";
import "./styles.css";

const rootElement = document.getElementById("installation-layout-root");

if (rootElement) {
  const commonProps = {
    fieldId: rootElement.dataset.fieldId ?? "",
    fieldName: rootElement.dataset.fieldName ?? "圃場",
    fieldDetailUrl: rootElement.dataset.fieldDetailUrl ?? "/fields",
  };
  createRoot(rootElement).render(
    rootElement.dataset.view === "calendar"
      ? <PlantCalendarPage {...commonProps} initialPlantingId={rootElement.dataset.plantingId ?? ""} initialActionId={rootElement.dataset.actionId ?? ""} />
      : <App {...commonProps} />,
  );
}
