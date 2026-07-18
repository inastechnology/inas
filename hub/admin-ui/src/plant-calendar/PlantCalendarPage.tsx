import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";

import {
  addPlantAction,
  askPlantQuestion,
  completePlantAction,
  createFertilizerApplication,
  deleteFertilizerApplication,
  deletePlantAction,
  loadPlantBundle,
  regeneratePlantCalendar,
  searchPlantActions,
  updatePlantAction,
} from "../api";
import { errorMessage } from "../formatters";
import type { PlantBundle, PlantCalendarAction } from "../types";
import { PlantCalendarDrawer } from "./PlantCalendarDrawer";

const EMPTY_BUNDLE: PlantBundle = {
  action_types: [], plantings: [], calendars: {}, generation_tasks: [], suggestions: [], work_logs: [], fertilizer_applications: [],
};
const searchCalendarActions = (plantingId: string, query: string, page: number, signal: AbortSignal) => (
  searchPlantActions(plantingId, { query, page, pageSize: 50, signal })
);

interface PlantCalendarPageProps {
  fieldId: string;
  fieldName: string;
  fieldDetailUrl: string;
  initialPlantingId: string;
  initialActionId: string;
}

export function PlantCalendarPage({ fieldId, fieldName, fieldDetailUrl, initialPlantingId, initialActionId }: PlantCalendarPageProps) {
  const [bundle, setBundle] = useState<PlantBundle>(EMPTY_BUNDLE);
  const [selectedPlantingId, setSelectedPlantingId] = useState(initialPlantingId);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = async (preferredPlantingId = selectedPlantingId || initialPlantingId) => {
    let nextBundle = await loadPlantBundle(fieldId, { compact: true, calendarPlantingId: preferredPlantingId });
    const nextPlantingId = nextBundle.plantings.some((planting) => planting.status === "active" && planting.id === preferredPlantingId)
      ? preferredPlantingId
      : nextBundle.plantings.find((planting) => planting.status === "active")?.id ?? "";
    if (nextPlantingId && !nextBundle.calendars[nextPlantingId]) {
      nextBundle = await loadPlantBundle(fieldId, { compact: true, calendarPlantingId: nextPlantingId });
    }
    setBundle(nextBundle);
    setSelectedPlantingId(nextPlantingId);
    return nextBundle;
  };

  const generationPollingKey = bundle.generation_tasks
    .filter((task) => task.status === "queued" || task.status === "running")
    .map((task) => `${task.id}:${task.status}:${task.updated_at}`)
    .join("|");

  useEffect(() => {
    if (!generationPollingKey) return undefined;
    const timer = window.setInterval(() => {
      void refresh().catch((caught) => setError(errorMessage(caught)));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [fieldId, generationPollingKey, selectedPlantingId]);

  useEffect(() => {
    setLoading(true);
    setError("");
    void refresh().catch((caught) => setError(errorMessage(caught))).finally(() => setLoading(false));
    // The field id does not change without remounting this page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fieldId]);

  const execute = async <Result,>(operation: () => Promise<Result>, shouldRefresh = true) => {
    setBusy(true);
    setError("");
    try {
      const result = await operation();
      if (shouldRefresh) await refresh(selectedPlantingId);
      return result;
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async (plantingId: string, startDate: string, planningNotes: string) => {
    setError("");
    try {
      await regeneratePlantCalendar(plantingId, { start_date: startDate, planning_notes: planningNotes });
      await refresh(plantingId);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    }
  };

  const selectPlanting = (plantingId: string) => {
    setSelectedPlantingId(plantingId);
    const url = new URL(window.location.href);
    if (plantingId) url.searchParams.set("planting", plantingId);
    else url.searchParams.delete("planting");
    window.history.replaceState(null, "", url);
    setBusy(true);
    setError("");
    void refresh(plantingId).catch((caught) => setError(errorMessage(caught))).finally(() => setBusy(false));
  };

  if (loading) return <div className="layout-state">年間カレンダーを読み込んでいます...</div>;
  if (error && bundle.plantings.length === 0) {
    return (
      <div className="layout-state layout-state-error">
        <p>{error}</p>
        <button type="button" onClick={() => window.location.reload()}><RotateCcw size={16} />再読込</button>
      </div>
    );
  }

  return (
    <>
      {error && <div className="calendar-page-error" role="alert">{error}</div>}
      <PlantCalendarDrawer
        presentation="page"
        fieldName={fieldName}
        fieldDetailUrl={fieldDetailUrl}
        bundle={bundle}
        selectedPlantingId={selectedPlantingId}
        initialActionId={initialActionId}
        busy={busy}
        onPlantingChange={selectPlanting}
        onClose={() => undefined}
        onEditAction={(plantingId, actionId, payload) => execute(async () => {
          await updatePlantAction(plantingId, actionId, payload);
        })}
        onCompleteAction={(plantingId, actionId, payload) => execute(async () => {
          await completePlantAction(plantingId, actionId, payload);
        })}
        onAskQuestion={(plantingId, question) => execute(() => askPlantQuestion(plantingId, question), false)}
        onRegenerate={regenerate}
        onAddAction={(plantingId, payload: Partial<PlantCalendarAction>) => execute(async () => {
          await addPlantAction(plantingId, payload);
        })}
        onDeleteAction={(plantingId, actionId) => execute(async () => {
          await deletePlantAction(plantingId, actionId);
        })}
        onAddFertilizer={(plantingId, payload) => execute(async () => {
          await createFertilizerApplication(plantingId, payload);
        })}
        onDeleteFertilizer={(plantingId, applicationId) => execute(async () => {
          await deleteFertilizerApplication(plantingId, applicationId);
        })}
        onSearchActions={searchCalendarActions}
      />
    </>
  );
}
