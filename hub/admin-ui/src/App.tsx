import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import {
  ArrowLeft,
  ArrowUp,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronRight,
  Compass,
  DoorOpen,
  Droplets,
  ExternalLink,
  Leaf,
  Minus,
  Plus,
  Redo2,
  RotateCcw,
  Save,
  Search,
  Sparkles,
  Trash2,
  Undo2,
  Users,
  WifiOff,
  X,
} from "lucide-react";

import {
  ApiError,
  askPlantQuestion,
  listPlantQuestions,
  addPlantAction,
  completePlantAction,
  createFertilizerApplication,
  createFertilizerMaterial,
  createPlanting,
  decidePlantCalendarRegenerationProposals,
  deleteFertilizerApplication,
  deleteFertilizerMaterial,
  deletePlantAction,
  loadLayout,
  loadLayoutDevices,
  loadPlantBundle,
  regeneratePlantCalendar,
  reviewPlantAction,
  saveLayout,
  searchLayoutDevices,
  skipPlantAction,
  updatePlantAction,
  updatePlanting,
  updateFertilizerMaterial,
} from "./api";
import { DisabledActionReason, disabledActionTitle } from "./DisabledActionReason";
import { errorMessage, formatDate, todayString } from "./formatters";
import { InstallationCanvas } from "./InstallationCanvas";
import { HelpDisclosure } from "./HelpDisclosure";
import { collaboratorColor, collaboratorLabel, presenceStateLabel } from "./layoutCollaboration";
import { reconcileRemoteLayout } from "./layoutMerge";
import { ActivityIndicator, LoadingState } from "./LoadingState";
import { PlantCalendarDrawer } from "./plant-calendar/PlantCalendarDrawer";
import { PRESET_BY_ID, PRESETS, SPACE_TYPE_LABELS } from "./presets";
import { matchesSearch } from "./search";
import { SearchableSelect } from "./SearchableSelect";
import { useLayoutCollaboration, type CollaborationConnectionState } from "./useLayoutCollaboration";
import type {
  FieldLayout,
  LayoutCollaborator,
  LayoutDevice,
  LayoutPresenceState,
  LayoutSpace,
  Placement,
  PlacementPreset,
  PlantActionCompletionPayload,
  PlantActionMutationPayload,
  PlantActionReviewPayload,
  PlantActionSkipPayload,
  PlantBundle,
  PlantCalendarGenerationTask,
  PlantCalendarAction,
  Planting,
} from "./types";

interface AppProps {
  fieldId: string;
  fieldName: string;
  fieldDetailUrl: string;
}

const HISTORY_LIMIT = 40;
const EMPTY_PLANT_BUNDLE: PlantBundle = {
  viewer: { email: "", role: "operator" }, action_types: [], plantings: [], calendars: {}, generation_tasks: [], suggestions: [], work_logs: [], fertilizer_applications: [], fertilizer_materials: [], operation_readiness: {},
};
const PLANTABLE_PRESETS = new Set<PlacementPreset>(["ridge", "tree", "pot", "hydroponic_bed"]);
const SPACE_TARGET_PRESETS = new Set<PlacementPreset>(["greenhouse", "open_field", "shade_area"]);
const TARGETABLE_PRESETS = new Set<PlacementPreset>(["greenhouse", "open_field", "shade_area", ...PLANTABLE_PRESETS]);
const DEVICE_BINDABLE_PRESETS = new Set<PlacementPreset>(["watering_device", "sensor", "camera", "grow_light", "mister", "fan", "hvac"]);
const INITIAL_QUERY = new URLSearchParams(window.location.search);
const REQUESTED_SPACE_ID = INITIAL_QUERY.get("space") ?? "";
const REQUESTED_PLACEMENT_ID = INITIAL_QUERY.get("placement") ?? "";
const REQUESTED_PLANTING_ID = INITIAL_QUERY.get("planting") ?? "";
const REQUESTED_TARGET_METRIC = INITIAL_QUERY.get("target_metric") ?? "";

interface LayoutConflictState {
  server: FieldLayout;
  localPreferred: FieldLayout;
  serverPreferred: FieldLayout;
  conflictPaths: string[];
}

interface CollaborationNotice {
  id: number;
  message: string;
}

export function App({ fieldId, fieldName, fieldDetailUrl }: AppProps) {
  const [layout, setLayout] = useState<FieldLayout | null>(null);
  const [baseLayout, setBaseLayout] = useState<FieldLayout | null>(null);
  const [layoutConflict, setLayoutConflict] = useState<LayoutConflictState | null>(null);
  const [devices, setDevices] = useState<LayoutDevice[]>([]);
  const [activeSpaceId, setActiveSpaceId] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [past, setPast] = useState<FieldLayout[]>([]);
  const [future, setFuture] = useState<FieldLayout[]>([]);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [zoom, setZoom] = useState(1);
  const [plantBundle, setPlantBundle] = useState<PlantBundle>(EMPTY_PLANT_BUNDLE);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [calendarPlantingId, setCalendarPlantingId] = useState("");
  const [plantBusy, setPlantBusy] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [collaborationNotice, setCollaborationNotice] = useState<CollaborationNotice | null>(null);
  const collaborationEditorRef = useRef({ layout, baseLayout, dirty, saving, layoutConflict, activeSpaceId });
  const remoteLayoutLoadRef = useRef(0);

  collaborationEditorRef.current = { layout, baseLayout, dirty, saving, layoutConflict, activeSpaceId };

  const reload = async () => {
    setLoading(true);
    setError("");
    try {
      const [nextLayout, nextPlantBundle] = await Promise.all([
        loadLayout(fieldId),
        loadPlantBundle(fieldId, { compact: true }),
      ]);
      const boundDeviceIds = nextLayout.spaces.flatMap((space) => space.placements.map((placement) => placement.binding?.device_id ?? "")).filter(Boolean);
      const nextDevices = await loadLayoutDevices(fieldId, boundDeviceIds);
      setLayout(nextLayout);
      setBaseLayout(structuredClone(nextLayout));
      setLayoutConflict(null);
      setDevices(nextDevices);
      setPlantBundle(nextPlantBundle);
      let requestedPlacementLocation = nextLayout.spaces
        .map((space) => ({ space, placement: space.placements.find((placement) => placement.id === REQUESTED_PLACEMENT_ID) }))
        .find((item) => item.placement);
      if (!requestedPlacementLocation && REQUESTED_TARGET_METRIC) {
        const targetPlanting = nextPlantBundle.plantings.find((planting) => planting.status === "active" && planting.id === REQUESTED_PLANTING_ID)
          ?? nextPlantBundle.plantings.find((planting) => planting.status === "active");
        requestedPlacementLocation = nextLayout.spaces
          .map((space) => ({ space, placement: space.placements.find((placement) => placement.id === targetPlanting?.placement_id) }))
          .find((item) => item.placement);
      }
      const requestedSpaceId = requestedPlacementLocation?.space.id
        ?? (nextLayout.spaces.some((space) => space.id === REQUESTED_SPACE_ID) ? REQUESTED_SPACE_ID : nextLayout.root_space_id);
      setActiveSpaceId(requestedSpaceId);
      setSelectedId(requestedPlacementLocation?.placement?.id ?? null);
      setPast([]);
      setFuture([]);
      setDirty(false);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
    // The field id does not change without remounting this editor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fieldId]);

  const activeSpace = layout?.spaces.find((space) => space.id === activeSpaceId) ?? layout?.spaces[0] ?? null;
  const selectedPlacement = activeSpace?.placements.find((placement) => placement.id === selectedId) ?? null;
  const breadcrumbs = useMemo(() => (layout && activeSpace ? buildBreadcrumbs(layout, activeSpace.id) : []), [layout, activeSpace]);
  const activePlantings = plantBundle.plantings.filter((planting) => planting.status === "active");
  const plantingByPlacementId = useMemo(
    () => Object.fromEntries(activePlantings.map((planting) => [planting.placement_id, planting.crop_name])),
    [plantBundle.plantings],
  );
  const selectedPlanting = selectedPlacement
    ? activePlantings.find((planting) => planting.space_id === activeSpace?.id && planting.placement_id === selectedPlacement.id) ?? null
    : null;
  const targetPlacements = useMemo(
    () => layout?.spaces.flatMap((space) => space.placements
      .filter((placement) => TARGETABLE_PRESETS.has(placement.preset))
      .map((placement) => ({
        id: placement.id,
        name: placement.name,
        preset: placement.preset,
        spaceId: space.id,
        spaceName: space.name,
      }))) ?? [],
    [layout],
  );
  const wateringSources = useMemo(
    () => layout?.spaces.flatMap((space) => space.placements
      .filter((placement) => placement.preset === "watering_device" && placement.binding)
      .map((placement) => ({
        id: placement.id,
        name: placement.name,
        spaceId: space.id,
        spaceName: space.name,
        deviceName: devices.find((device) => device.id === placement.binding?.device_id)?.name ?? placement.binding?.device_id ?? "",
        targetPlacementIds: placement.binding?.target_placement_ids ?? [],
      }))) ?? [],
    [devices, layout],
  );
  const wateringSourceNamesByPlacementId = useMemo(() => {
    const assignments: Record<string, string[]> = {};
    wateringSources.forEach((source) => source.targetPlacementIds.forEach((targetId) => {
      assignments[targetId] = [...(assignments[targetId] ?? []), source.name];
    }));
    return assignments;
  }, [wateringSources]);
  const usedDeviceIds = useMemo(
    () => new Set(layout?.spaces.flatMap((space) => space.placements
      .filter((placement) => placement.id !== selectedPlacement?.id)
      .map((placement) => placement.binding?.device_id)
      .filter((deviceId): deviceId is string => Boolean(deviceId))) ?? []),
    [layout, selectedPlacement?.id],
  );
  const filteredPresets = useMemo(
    () => PRESETS.filter((preset) => preset.paletteVisible !== false && matchesSearch(paletteQuery, [preset.label, preset.group, ...preset.keywords])),
    [paletteQuery],
  );
  const presenceState: LayoutPresenceState = saving ? "saving" : layoutConflict ? "conflict" : dirty ? "editing" : "viewing";
  const {
    snapshot: collaborationSnapshot,
    connectionState: collaborationConnectionState,
  } = useLayoutCollaboration({
    fieldId,
    activeSpaceId: activeSpace?.id ?? "",
    selectedPlacementId: selectedId ?? "",
    state: presenceState,
    enabled: Boolean(layout && activeSpace),
  });
  const collaborators = collaborationSnapshot?.participants ?? [];
  const remoteCollaborators = collaborationConnectionState === "online"
    ? collaborators.filter((participant) => !participant.is_current)
    : [];

  useEffect(() => {
    if (!collaborationNotice) return undefined;
    const timer = window.setTimeout(() => setCollaborationNotice(null), 5_500);
    return () => window.clearTimeout(timer);
  }, [collaborationNotice]);

  useEffect(() => {
    const remoteRevision = collaborationSnapshot?.layout.revision ?? 0;
    const editor = collaborationEditorRef.current;
    if (
      !remoteRevision
      || !editor.layout
      || !editor.baseLayout
      || remoteRevision <= editor.baseLayout.revision
      || editor.saving
      || editor.layoutConflict
      || remoteLayoutLoadRef.current > 0
    ) return;

    remoteLayoutLoadRef.current = remoteRevision;
    void loadLayout(fieldId)
      .then((serverLayout) => {
        const current = collaborationEditorRef.current;
        if (!current.layout || !current.baseLayout || current.saving || current.layoutConflict) return;
        const reconciliation = reconcileRemoteLayout(current.baseLayout, current.layout, serverLayout, current.dirty);
        if (reconciliation.kind === "unchanged") return;
        if (reconciliation.kind === "conflict") {
          setLayoutConflict(reconciliation.conflict);
          return;
        }

        setLayout(reconciliation.layout);
        setBaseLayout(reconciliation.baseLayout);
        setPast([]);
        setFuture([]);
        setDirty(reconciliation.dirty);
        ensureActiveSpace(reconciliation.layout, current.activeSpaceId, setActiveSpaceId, setSelectedId);
        const boundDeviceIds = reconciliation.layout.spaces
          .flatMap((space) => space.placements.map((placement) => placement.binding?.device_id ?? ""))
          .filter(Boolean);
        void loadLayoutDevices(fieldId, boundDeviceIds).then(setDevices).catch(() => undefined);
        const actor = serverLayout.updated_by ? collaboratorLabel(serverLayout.updated_by) : "別の編集者";
        setCollaborationNotice({
          id: Date.now(),
          message: reconciliation.kind === "merge"
            ? `${actor}さんの更新を、自分の未保存変更と自動統合しました。`
            : `${actor}さんの更新を反映しました（r${serverLayout.revision}）。`,
        });
      })
      .catch(() => {
        setCollaborationNotice({ id: Date.now(), message: "共同編集の最新版を取得できませんでした。接続後に自動で再試行します。" });
      })
      .finally(() => {
        remoteLayoutLoadRef.current = 0;
      });
  }, [collaborationSnapshot, fieldId]);

  const refreshPlants = async (_calendarPlantingId = "") => {
    const nextBundle = await loadPlantBundle(fieldId);
    setPlantBundle(nextBundle);
    return nextBundle;
  };

  const generationPollingKey = plantBundle.generation_tasks
    .filter((task) => task.status === "queued" || task.status === "running")
    .map((task) => `${task.id}:${task.status}:${task.updated_at}`)
    .join("|");

  useEffect(() => {
    if (!generationPollingKey) return undefined;
    const timer = window.setInterval(() => {
      void refreshPlants(calendarPlantingId).catch((caught) => setError(errorMessage(caught)));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [calendarPlantingId, fieldId, generationPollingKey]);

  const registerPlanting = async (payload: Record<string, unknown>) => {
    setPlantBusy(true);
    setError("");
    try {
      const created = await createPlanting(fieldId, payload) as { planting?: Planting };
      let plantingId = created.planting?.id || "";
      let nextBundle = await refreshPlants(plantingId);
      if (!plantingId) {
        plantingId = nextBundle.plantings.find((planting) => planting.placement_id === payload.placement_id)?.id || "";
        if (plantingId) nextBundle = await refreshPlants(plantingId);
      }
      setCalendarPlantingId(plantingId);
      setCalendarOpen(true);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const editPlantAction = async (plantingId: string, actionId: string, payload: PlantActionMutationPayload & { use_as_guidance?: boolean }) => {
    setPlantBusy(true);
    setError("");
    try {
      await updatePlantAction(plantingId, actionId, payload);
      await refreshPlants(plantingId);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const regenerateCalendar = async (plantingId: string, startDate: string, planningNotes: string, mode: "automatic" | "review") => {
    setError("");
    try {
      await regeneratePlantCalendar(plantingId, { start_date: startDate, planning_notes: planningNotes, mode });
      await refreshPlants(plantingId);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    }
  };

  const createPlantAction = async (plantingId: string, payload: PlantActionMutationPayload) => {
    setPlantBusy(true);
    try {
      await addPlantAction(plantingId, payload);
      await refreshPlants(plantingId);
    } finally {
      setPlantBusy(false);
    }
  };

  const removePlantAction = async (plantingId: string, actionId: string) => {
    setPlantBusy(true);
    try {
      await deletePlantAction(plantingId, actionId);
      await refreshPlants(plantingId);
    } finally {
      setPlantBusy(false);
    }
  };

  const addFertilizerApplication = async (plantingId: string, payload: Record<string, unknown>) => {
    setPlantBusy(true);
    setError("");
    try {
      await createFertilizerApplication(plantingId, payload);
      await refreshPlants(plantingId);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const removeFertilizerApplication = async (plantingId: string, applicationId: string) => {
    setPlantBusy(true);
    setError("");
    try {
      await deleteFertilizerApplication(plantingId, applicationId);
      await refreshPlants(plantingId);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const saveFertilizerMaterial = async (materialId: string, payload: Record<string, unknown>) => {
    setPlantBusy(true);
    setError("");
    try {
      if (materialId) await updateFertilizerMaterial(materialId, payload);
      else await createFertilizerMaterial(payload);
      await refreshPlants(calendarPlantingId);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const removeFertilizerMaterial = async (materialId: string) => {
    setPlantBusy(true);
    setError("");
    try {
      await deleteFertilizerMaterial(materialId);
      await refreshPlants(calendarPlantingId);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const recordPlantAction = async (plantingId: string, actionId: string, payload: PlantActionCompletionPayload) => {
    setPlantBusy(true);
    setError("");
    try {
      await completePlantAction(plantingId, actionId, payload);
      await refreshPlants(plantingId);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const reviewPlantActionCompletion = async (plantingId: string, actionId: string, payload: PlantActionReviewPayload) => {
    setPlantBusy(true);
    setError("");
    try {
      await reviewPlantAction(plantingId, actionId, payload);
      await refreshPlants(plantingId);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const skipPlantCalendarAction = async (plantingId: string, actionId: string, payload: PlantActionSkipPayload) => {
    setPlantBusy(true);
    setError("");
    try {
      await skipPlantAction(plantingId, actionId, payload);
      await refreshPlants(plantingId);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const answerPlantQuestion = async (plantingId: string, question: string) => {
    setPlantBusy(true);
    setError("");
    try {
      return await askPlantQuestion(plantingId, question);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const editPlanting = async (plantingId: string, payload: Partial<Planting>) => {
    setPlantBusy(true);
    setError("");
    try {
      await updatePlanting(plantingId, payload);
      await refreshPlants(calendarOpen ? calendarPlantingId : "");
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const openPlantCalendar = (plantingId = "") => {
    setCalendarPlantingId(plantingId || activePlantings[0]?.id || "");
    setCalendarOpen(true);
  };

  const mutate = (mutator: (draft: FieldLayout) => void) => {
    if (!layout) return;
    const next = structuredClone(layout);
    mutator(next);
    setPast((items) => [...items, layout].slice(-HISTORY_LIMIT));
    setFuture([]);
    setLayout(next);
    setDirty(true);
  };

  const undo = () => {
    const previous = past.at(-1);
    if (!layout || !previous) return;
    setPast((items) => items.slice(0, -1));
    setFuture((items) => [layout, ...items].slice(0, HISTORY_LIMIT));
    setLayout(previous);
    ensureActiveSpace(previous, activeSpaceId, setActiveSpaceId, setSelectedId);
    setDirty(true);
  };

  const redo = () => {
    const next = future[0];
    if (!layout || !next) return;
    setFuture((items) => items.slice(1));
    setPast((items) => [...items, layout].slice(-HISTORY_LIMIT));
    setLayout(next);
    ensureActiveSpace(next, activeSpaceId, setActiveSpaceId, setSelectedId);
    setDirty(true);
  };

  const persist = async () => {
    if (!layout || saving) return;
    setSaving(true);
    setError("");
    let candidate = structuredClone(layout);
    let mergeBase = baseLayout ? structuredClone(baseLayout) : null;
    let mergedConcurrentUpdate = false;
    try {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          const saved = await saveLayout(fieldId, candidate);
          setLayout(saved);
          setBaseLayout(structuredClone(saved));
          setPast([]);
          setFuture([]);
          setDirty(false);
          if (mergedConcurrentUpdate) {
            setCollaborationNotice({ id: Date.now(), message: `同時更新を自動統合して保存しました（r${saved.revision}）。` });
          }
          return;
        } catch (caught) {
          const current = caught instanceof ApiError && caught.status === 409 ? caught.body.current : null;
          if (!mergeBase || !current || typeof current !== "object") {
            setError(errorMessage(caught));
            return;
          }

          const reconciliation = reconcileRemoteLayout(mergeBase, candidate, current as FieldLayout, true);
          if (reconciliation.kind === "conflict") {
            setLayoutConflict(reconciliation.conflict);
            return;
          }
          if (reconciliation.kind === "unchanged") {
            setError("最新版との統合に失敗しました。しばらく待ってから再度保存してください。");
            return;
          }

          candidate = reconciliation.layout;
          mergeBase = reconciliation.baseLayout;
          mergedConcurrentUpdate = true;
          setLayout(candidate);
          setBaseLayout(mergeBase);
          setPast([]);
          setFuture([]);
          setDirty(reconciliation.dirty);
          if (!reconciliation.dirty) {
            setCollaborationNotice({ id: Date.now(), message: `同じ更新がすでに保存されていました（r${candidate.revision}）。` });
            return;
          }
          if (attempt === 1) {
            setCollaborationNotice({ id: Date.now(), message: "新しい更新を自動統合しました。もう一度保存してください。" });
            return;
          }
        }
      }
    } finally {
      setSaving(false);
    }
  };

  const resolveLayoutConflict = (choice: "server" | "local-merge" | "server-merge") => {
    if (!layoutConflict) return;
    const next = choice === "server"
      ? structuredClone(layoutConflict.server)
      : structuredClone(choice === "local-merge" ? layoutConflict.localPreferred : layoutConflict.serverPreferred);
    setLayout(next);
    setBaseLayout(structuredClone(layoutConflict.server));
    setPast([]);
    setFuture([]);
    setLayoutConflict(null);
    setError("");
    setDirty(choice !== "server");
    ensureActiveSpace(next, activeSpaceId, setActiveSpaceId, setSelectedId);
  };

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [dirty]);

  const addPreset = (presetId: PlacementPreset, requestedX?: number, requestedY?: number) => {
    if (!activeSpace || !layout) return;
    const preset = PRESET_BY_ID[presetId];
    const width = Math.min(preset.width, activeSpace.grid.columns);
    const height = Math.min(preset.height, activeSpace.grid.rows);
    const x = clamp(requestedX ?? Math.round((activeSpace.grid.columns - width) / 2), 0, activeSpace.grid.columns - width);
    const y = clamp(requestedY ?? Math.round((activeSpace.grid.rows - height) / 2), 0, activeSpace.grid.rows - height);
    const placementId = createId(`placement-${presetId}`);
    const childSpaceId = preset.childSpaceType ? createId("space") : "";
    const samePresetCount = activeSpace.placements.filter((placement) => placement.preset === presetId).length;
    const name = `${preset.label}${samePresetCount + 1}`;

    mutate((draft) => {
      const space = requireSpace(draft, activeSpace.id);
      space.placements.push({
        id: placementId,
        preset: presetId,
        name,
        x,
        y,
        width,
        height,
        rotation: 0,
        z: space.placements.length,
        child_space_id: childSpaceId,
        binding: null,
        memo: "",
      });
      if (preset.childSpaceType) {
        draft.spaces.push({
          id: childSpaceId,
          name: `${name} 内部`,
          space_type: preset.childSpaceType,
          north_angle_deg: activeSpace.north_angle_deg,
          grid: {
            columns: clamp(width * 2, 12, 80),
            rows: clamp(height * 2, 10, 60),
            cell_size_m: space.grid.cell_size_m,
          },
          placements: [],
        });
      }
    });
    setSelectedId(placementId);
  };

  const updatePlacement = (placementId: string, patch: Partial<Placement>) => {
    if (!activeSpace) return;
    mutate((draft) => {
      const space = requireSpace(draft, activeSpace.id);
      const placement = space.placements.find((item) => item.id === placementId);
      if (!placement) return;
      Object.assign(placement, patch);
      placement.width = clamp(placement.width, 1, space.grid.columns);
      placement.height = clamp(placement.height, 1, space.grid.rows);
      placement.x = clamp(placement.x, 0, space.grid.columns - placement.width);
      placement.y = clamp(placement.y, 0, space.grid.rows - placement.height);
    });
  };

  const setPlacementWateringSource = (targetPlacementId: string, sourcePlacementId: string) => {
    mutate((draft) => {
      draft.spaces.forEach((space) => space.placements.forEach((candidate) => {
        if (candidate.preset !== "watering_device" || !candidate.binding) return;
        const targets = candidate.binding.target_placement_ids.filter((targetId) => targetId !== targetPlacementId);
        if (candidate.id === sourcePlacementId) targets.push(targetPlacementId);
        candidate.binding.target_placement_ids = Array.from(new Set(targets));
      }));
    });
  };

  const deletePlacement = (placementId: string) => {
    if (!activeSpace) return;
    mutate((draft) => {
      const space = requireSpace(draft, activeSpace.id);
      const placement = space.placements.find((item) => item.id === placementId);
      space.placements = space.placements.filter((item) => item.id !== placementId);
      if (placement?.child_space_id) removeSpaceTree(draft, placement.child_space_id);
      const existingPlacementIds = new Set(draft.spaces.flatMap((item) => item.placements.map((candidate) => candidate.id)));
      draft.spaces.forEach((item) => item.placements.forEach((candidate) => {
        if (!candidate.binding) return;
        candidate.binding.target_placement_ids = candidate.binding.target_placement_ids.filter((targetId) => existingPlacementIds.has(targetId));
      }));
    });
    setSelectedId(null);
  };

  const updateActiveSpace = (patch: Partial<LayoutSpace>) => {
    if (!activeSpace) return;
    mutate((draft) => {
      const space = requireSpace(draft, activeSpace.id);
      if (patch.name !== undefined) space.name = patch.name;
      if (patch.space_type !== undefined) space.space_type = patch.space_type;
      if (patch.north_angle_deg !== undefined) space.north_angle_deg = clamp(Math.round(patch.north_angle_deg), 0, 359);
      if (patch.grid !== undefined) {
        space.grid = {
          columns: clamp(Math.round(patch.grid.columns), 8, 200),
          rows: clamp(Math.round(patch.grid.rows), 8, 200),
          cell_size_m: clamp(Number(patch.grid.cell_size_m), 0.01, 100),
        };
        space.placements.forEach((placement) => {
          placement.width = clamp(placement.width, 1, space.grid.columns);
          placement.height = clamp(placement.height, 1, space.grid.rows);
          placement.x = clamp(placement.x, 0, space.grid.columns - placement.width);
          placement.y = clamp(placement.y, 0, space.grid.rows - placement.height);
        });
      }
    });
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isEditing = target?.matches("input, textarea, select, [contenteditable='true']");
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void persist();
      } else if (!isEditing && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) redo(); else undo();
      } else if (!isEditing && event.key === "Delete" && selectedPlacement) {
        event.preventDefault();
        deletePlacement(selectedPlacement.id);
      } else if (event.key === "Escape") {
        setSelectedId(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  if (loading) {
    return <LoadingState label="設置ビューを読み込んでいます" detail="設備と栽培エリアの接続状態を整えています" />;
  }
  if (!layout || !activeSpace) {
    return (
      <div className="layout-state layout-state-error">
        <p>{error || "設置ビューを読み込めませんでした。"}</p>
        <button type="button" onClick={() => void reload()}><RotateCcw size={16} />再読込</button>
      </div>
    );
  }

  return (
    <div className={`installation-app ${error ? "has-error" : ""} ${collaborationNotice ? "has-collaboration-notice" : ""}`}>
      <header className="editor-header">
        <div className="editor-identity">
          <a className="icon-link labeled-icon-button" href={fieldDetailUrl} aria-label="圃場詳細へ戻る" title="圃場詳細へ戻る"><ArrowLeft size={19} /><span>圃場へ戻る</span></a>
          <div>
            <span className="eyebrow">設置ビュー</span>
            <h1>{fieldName}</h1>
          </div>
        </div>
        <nav className="breadcrumbs" aria-label="設置空間">
          {breadcrumbs.map((space, index) => (
            <span key={space.id}>
              {index > 0 && <ChevronRight size={14} />}
              <button type="button" className={space.id === activeSpace.id ? "active" : ""} onClick={() => { setActiveSpaceId(space.id); setSelectedId(null); }}>
                {space.name}
              </button>
            </span>
          ))}
        </nav>
        <div className="editor-actions">
          <a className="calendar-button" href={`/fields/${encodeURIComponent(fieldId)}/calendar`} target="_blank" rel="noopener" aria-label="栽培カレンダーを新しいタブで開く" title="栽培カレンダーを新しいタブで開く">
            <CalendarDays size={17} />
            <span>栽培カレンダー</span>
            {plantBundle.suggestions.length > 0 && <strong>{plantBundle.suggestions.length}</strong>}
          </a>
          <span className={`save-state ${dirty ? "dirty" : ""}`}>{saving ? "保存中" : dirty ? "未保存" : `保存済み r${layout.revision}`}</span>
          <button type="button" className="icon-button labeled-icon-button" onClick={undo} disabled={!past.length} aria-label="直前の変更を元に戻す" title={past.length ? "元に戻す" : "元に戻せる変更はありません"}><Undo2 size={18} /><span>元に戻す</span></button>
          <button type="button" className="icon-button labeled-icon-button" onClick={redo} disabled={!future.length} aria-label="取り消した変更をやり直す" title={future.length ? "やり直す" : "やり直せる変更はありません"}><Redo2 size={18} /><span>やり直す</span></button>
          <div className="zoom-control">
            <button type="button" onClick={() => setZoom((value) => clamp(value / 1.15, 0.2, 2.5))} aria-label="設置図を縮小" title="縮小"><Minus size={16} /></button>
            <span>{Math.round(zoom * 100)}%</span>
            <button type="button" onClick={() => setZoom((value) => clamp(value * 1.15, 0.2, 2.5))} aria-label="設置図を拡大" title="拡大"><Plus size={16} /></button>
          </div>
          <button type="button" className="save-button" onClick={() => void persist()} disabled={!dirty || saving} aria-busy={saving} title={saving ? "保存処理中です" : !dirty ? "未保存の変更はありません" : "設置ビューを保存"}>{!saving && <Save size={17} />}{saving ? "保存しています" : "保存"}</button>
        </div>
      </header>

      {collaborationNotice && (
        <div className="collaboration-notice" role="status" aria-live="polite">
          <Users size={16} />
          <span>{collaborationNotice.message}</span>
          <button type="button" onClick={() => setCollaborationNotice(null)} aria-label="共同編集のお知らせを閉じる" title="閉じる"><X size={15} /></button>
        </div>
      )}

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => void reload()}><RotateCcw size={15} />サーバーから再読込</button>
        </div>
      )}

      <main className="editor-workspace">
        <aside className="palette-panel" aria-label="配置パレット">
          <div className="panel-heading">
            <span>配置パレット</span>
            <strong>{activeSpace.placements.length}</strong>
          </div>
          <label className="palette-search"><Search size={16} /><input type="search" value={paletteQuery} onChange={(event) => setPaletteQuery(event.target.value)} placeholder="配置物を検索" aria-label="配置物を検索" />{paletteQuery && <button type="button" onClick={() => setPaletteQuery("")} aria-label="配置物の検索をクリア" title="検索をクリア"><X size={14} /></button>}</label>
          {(["空間", "培地", "設備"] as const).map((group) => filteredPresets.some((preset) => preset.group === group) && (
            <section className="preset-group" key={group}>
              <h2>{group}</h2>
              <div className="preset-list">
                {filteredPresets.filter((preset) => preset.group === group).map((preset) => {
                  const Icon = preset.icon;
                  return (
                    <button
                      type="button"
                      className="preset-button"
                      key={preset.id}
                      draggable
                      title={`${preset.label}を追加`}
                      onDragStart={(event) => {
                        event.dataTransfer.setData("application/x-ina-layout-preset", preset.id);
                        event.dataTransfer.effectAllowed = "copy";
                      }}
                      onClick={() => addPreset(preset.id)}
                    >
                      <span className="preset-swatch" style={{ background: preset.fill, color: preset.stroke }}><Icon size={20} /></span>
                      <span>{preset.label}</span>
                      <Plus size={15} />
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
          {filteredPresets.length === 0 && <p className="palette-empty">一致する配置物はありません。</p>}
        </aside>

        <section className="canvas-panel">
          <div className="canvas-toolbar">
            <div>
              <strong>{activeSpace.name}</strong>
              <span>{SPACE_TYPE_LABELS[activeSpace.space_type]} ・ {activeSpace.grid.columns} × {activeSpace.grid.rows} マス</span>
            </div>
            <div className="canvas-toolbar-meta">
              <CollaborationPresence
                participants={collaborators}
                connectionState={collaborationConnectionState}
                activeSpaceId={activeSpace.id}
              />
              <span className="canvas-dimensions">{activeSpace.grid.columns * activeSpace.grid.cell_size_m}m × {activeSpace.grid.rows * activeSpace.grid.cell_size_m}m</span>
            </div>
          </div>
          <InstallationCanvas
            layout={layout}
            space={activeSpace}
            selectedId={selectedId}
            plantingByPlacementId={plantingByPlacementId}
            wateringSourceNamesByPlacementId={wateringSourceNamesByPlacementId}
            collaborators={remoteCollaborators}
            zoom={zoom}
            onZoomChange={setZoom}
            onSelect={setSelectedId}
            onPlacementChange={updatePlacement}
            onAddPreset={addPreset}
            onOpenChild={(spaceId) => { setActiveSpaceId(spaceId); setSelectedId(null); }}
          />
        </section>

        <aside className="inspector-panel" aria-label="プロパティ">
          {selectedPlacement ? (
            <PlacementInspector
              fieldId={fieldId}
              placement={selectedPlacement}
              space={activeSpace}
              devices={devices}
              targetPlacements={targetPlacements}
              wateringSources={wateringSources}
              wateringSourceIds={wateringSources.filter((source) => source.targetPlacementIds.includes(selectedPlacement.id)).map((source) => source.id)}
              usedDeviceIds={usedDeviceIds}
              planting={selectedPlanting}
              generationTask={selectedPlanting ? plantBundle.generation_tasks.find((task) => task.planting_id === selectedPlanting.id) ?? null : null}
              targetMetric={REQUESTED_TARGET_METRIC}
              fieldDetailUrl={fieldDetailUrl}
              layoutDirty={dirty}
              plantBusy={plantBusy}
              onChange={(patch) => updatePlacement(selectedPlacement.id, patch)}
              onWateringSourceChange={(sourcePlacementId) => setPlacementWateringSource(selectedPlacement.id, sourcePlacementId)}
              onDelete={() => deletePlacement(selectedPlacement.id)}
              onOpenChild={() => { setActiveSpaceId(selectedPlacement.child_space_id); setSelectedId(null); }}
              onRegisterPlanting={(value) => registerPlanting({
                ...value,
                space_id: activeSpace.id,
                placement_id: selectedPlacement.id,
              })}
              calendarUrl={selectedPlanting ? `/fields/${encodeURIComponent(fieldId)}/calendar?planting=${encodeURIComponent(selectedPlanting.id)}` : `/fields/${encodeURIComponent(fieldId)}/calendar`}
              onUpdatePlanting={editPlanting}
            />
          ) : (
            <SpaceInspector space={activeSpace} isRoot={activeSpace.id === layout.root_space_id} onChange={updateActiveSpace} />
          )}
        </aside>
      </main>
      {calendarOpen && (
        <PlantCalendarDrawer
          bundle={plantBundle}
          selectedPlantingId={calendarPlantingId}
          busy={plantBusy}
          onPlantingChange={setCalendarPlantingId}
          onClose={() => setCalendarOpen(false)}
          onEditAction={editPlantAction}
          onCompleteAction={recordPlantAction}
          onReviewAction={reviewPlantActionCompletion}
          onSkipAction={skipPlantCalendarAction}
          onAskQuestion={answerPlantQuestion}
          onListQuestions={(plantingId, options) => listPlantQuestions(plantingId, options)}
          onRegenerate={regenerateCalendar}
          onDecideRegeneration={async (plantingId, taskId, decisions) => {
            setPlantBusy(true);
            setError("");
            try {
              const result = await decidePlantCalendarRegenerationProposals(plantingId, taskId, decisions);
              setPlantBundle(result.bundle);
            } catch (caught) {
              setError(errorMessage(caught));
              throw caught;
            } finally {
              setPlantBusy(false);
            }
          }}
          onAddAction={createPlantAction}
          onDeleteAction={removePlantAction}
          onAddFertilizer={addFertilizerApplication}
          onDeleteFertilizer={removeFertilizerApplication}
          onSaveFertilizerMaterial={saveFertilizerMaterial}
          onDeleteFertilizerMaterial={removeFertilizerMaterial}
        />
      )}
      {layoutConflict && (
        <div className="layout-conflict-backdrop" role="presentation">
          <section className="layout-conflict-dialog" role="dialog" aria-modal="true" aria-labelledby="layout-conflict-title">
            <header>
              <div>
                <span className="eyebrow">同時編集を検出</span>
                <h2 id="layout-conflict-title">設置ビューが別の画面で更新されました</h2>
              </div>
              <button type="button" className="icon-button labeled-icon-button" onClick={() => resolveLayoutConflict("server")} aria-label="最新版を読み込んで閉じる" title="最新版を読み込んで閉じる"><X size={18} /><span>閉じる</span></button>
            </header>
            <div className="layout-conflict-summary">
              <dl>
                <dt>更新者</dt><dd>{layoutConflict.server.updated_by || "不明"}</dd>
                <dt>最新版</dt><dd>r{layoutConflict.server.revision}</dd>
                <dt>更新日時</dt><dd>{formatConflictTimestamp(layoutConflict.server.updated_at)}</dd>
              </dl>
              {layoutConflict.conflictPaths.length === 0 ? (
                <p className="merge-success">変更箇所は重なっていません。両方の変更を自動統合できます。</p>
              ) : (
                <div className="conflict-paths"><strong>{layoutConflict.conflictPaths.length}件の同じ項目が変更されています</strong><ul>{layoutConflict.conflictPaths.slice(0, 6).map((path) => <li key={path}>{path}</li>)}</ul></div>
              )}
            </div>
            <footer>
              <button type="button" onClick={() => resolveLayoutConflict("server")}>自分の変更を破棄</button>
              {layoutConflict.conflictPaths.length > 0 && <button type="button" onClick={() => resolveLayoutConflict("server-merge")}>競合箇所は最新版を採用</button>}
              <button type="button" className="primary" onClick={() => resolveLayoutConflict("local-merge")}>
                {layoutConflict.conflictPaths.length === 0 ? "変更を自動統合" : "競合箇所は自分の入力を採用"}
              </button>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}

function CollaborationPresence({
  participants,
  connectionState,
  activeSpaceId,
}: {
  participants: LayoutCollaborator[];
  connectionState: CollaborationConnectionState;
  activeSpaceId: string;
}) {
  const participantGroups = Array.from(participants.reduce((groups, participant) => {
    const identity = participant.email || participant.client_id;
    groups.set(identity, [...(groups.get(identity) ?? []), participant]);
    return groups;
  }, new Map<string, LayoutCollaborator[]>())).map(([identity, tabs]) => ({
    identity,
    tabs,
    representative: tabs.slice().sort((left, right) => presenceStatePriority(right.state) - presenceStatePriority(left.state))[0],
    isCurrent: tabs.some((participant) => participant.is_current),
    isInActiveSpace: tabs.some((participant) => participant.active_space_id === activeSpaceId),
  }));
  const tabSuffix = participants.length > participantGroups.length ? `・${participants.length}画面` : "";
  const label = connectionState === "offline"
    ? "同期を再接続中"
    : connectionState === "connecting"
      ? "共同編集に接続中"
      : `${Math.max(1, participantGroups.length)}人${tabSuffix}で編集中`;
  const title = connectionState === "offline"
    ? "共同編集サーバーへ再接続しています。編集はこのまま続けられます。"
    : "現在この設置ビューを開いているユーザー";

  return (
    <details className={`collaboration-presence ${connectionState}`}>
      <summary title={title} aria-label={label}>
        <span className="collaboration-connection-dot" aria-hidden="true">{connectionState === "offline" && <WifiOff size={11} />}</span>
        <span className="collaboration-avatars" aria-hidden="true">
          {participantGroups.slice(0, 3).map((group) => (
            <span
              key={group.identity}
              style={{ "--collaborator-color": collaboratorColor(group.identity) } as CSSProperties}
            >
              {collaboratorLabel(group.representative.email).slice(0, 1).toUpperCase()}
            </span>
          ))}
        </span>
        <span className="collaboration-presence-label">{label}</span>
      </summary>
      <div className="collaboration-presence-popover">
        <header><Users size={16} /><strong>共同編集</strong></header>
        {connectionState === "offline" && <p>接続を復旧しています。未保存の変更は保持されます。</p>}
        {connectionState === "connecting" && <p>参加者を確認しています。</p>}
        {participantGroups.length > 0 && (
          <ul>
            {participantGroups.map((group) => (
              <li key={group.identity}>
                <span
                  className="collaboration-participant-avatar"
                  style={{ "--collaborator-color": collaboratorColor(group.identity) } as CSSProperties}
                  aria-hidden="true"
                >
                  {collaboratorLabel(group.representative.email).slice(0, 1).toUpperCase()}
                </span>
                <span>
                  <strong>{group.isCurrent ? "自分" : collaboratorLabel(group.representative.email)}{group.tabs.length > 1 ? `（${group.tabs.length}画面）` : ""}</strong>
                  <small>{group.representative.email} ・ {group.isInActiveSpace ? "この空間" : "別の空間"} ・ {presenceStateLabel(group.representative.state)}</small>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}

function presenceStatePriority(state: LayoutPresenceState): number {
  return { viewing: 0, editing: 1, saving: 2, conflict: 3 }[state];
}

function formatConflictTimestamp(value: string): string {
  if (!value) return "不明";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("ja-JP");
}

function SpaceInspector({ space, isRoot, onChange }: { space: LayoutSpace; isRoot: boolean; onChange: (patch: Partial<LayoutSpace>) => void }) {
  const northAngle = clamp(Math.round(space.north_angle_deg ?? 0), 0, 359);
  return (
    <div className="inspector-content">
      <div className="panel-heading"><span>空間設定</span><strong>{SPACE_TYPE_LABELS[space.space_type]}</strong></div>
      <label>空間名<input value={space.name} onChange={(event) => onChange({ name: event.target.value })} /></label>
      <label>空間種別
        <select value={space.space_type} disabled={isRoot} title={isRoot ? "圃場全体の空間種別は変更できません" : undefined} onChange={(event) => onChange({ space_type: event.target.value as LayoutSpace["space_type"] })}>
          {Object.entries(SPACE_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <section className="north-angle-control" aria-label="北の向き">
        <div className="north-angle-heading"><span><Compass size={17} /><strong>北の向き</strong></span><b>{northDirectionLabel(northAngle)}</b></div>
        <div className="north-angle-editor">
          <div className="north-angle-preview" aria-hidden="true"><div style={{ transform: `rotate(${northAngle}deg)` }}><span style={{ transform: `rotate(-${northAngle}deg)` }}>N</span><ArrowUp size={22} /></div></div>
          <label>角度
            <input type="range" min="0" max="359" step="1" value={northAngle} onChange={(event) => onChange({ north_angle_deg: Number(event.target.value) })} />
          </label>
          <output>{northAngle}°</output>
        </div>
        <div className="north-angle-presets" role="group" aria-label="北向きのプリセット">
          {[0, 90, 180, 270].map((angle) => <button type="button" key={angle} className={northAngle === angle ? "active" : ""} onClick={() => onChange({ north_angle_deg: angle })} title={`北を${northDirectionLabel(angle)}に設定`} aria-label={`北を${northDirectionLabel(angle)}に設定`}><ArrowUp size={16} style={{ transform: `rotate(${angle}deg)` }} /></button>)}
        </div>
      </section>
      <div className="field-grid three">
        <label>横<input type="number" min="8" max="200" value={space.grid.columns} onChange={(event) => onChange({ grid: { ...space.grid, columns: Number(event.target.value) } })} /></label>
        <label>縦<input type="number" min="8" max="200" value={space.grid.rows} onChange={(event) => onChange({ grid: { ...space.grid, rows: Number(event.target.value) } })} /></label>
        <label>m/マス<input type="number" min="0.01" max="100" step="0.01" value={space.grid.cell_size_m} onChange={(event) => onChange({ grid: { ...space.grid, cell_size_m: Number(event.target.value) } })} /></label>
      </div>
      <dl className="space-summary">
        <dt>実寸</dt><dd>{space.grid.columns * space.grid.cell_size_m}m × {space.grid.rows * space.grid.cell_size_m}m</dd>
        <dt>配置数</dt><dd>{space.placements.length}</dd>
      </dl>
    </div>
  );
}

interface PlacementInspectorProps {
  fieldId: string;
  placement: Placement;
  space: LayoutSpace;
  devices: LayoutDevice[];
  targetPlacements: Array<{ id: string; name: string; preset: PlacementPreset; spaceId: string; spaceName: string }>;
  wateringSources: Array<{ id: string; name: string; spaceId: string; spaceName: string; deviceName: string; targetPlacementIds: string[] }>;
  wateringSourceIds: string[];
  usedDeviceIds: Set<string>;
  planting: Planting | null;
  generationTask: PlantCalendarGenerationTask | null;
  targetMetric: string;
  fieldDetailUrl: string;
  calendarUrl: string;
  layoutDirty: boolean;
  plantBusy: boolean;
  onChange: (patch: Partial<Placement>) => void;
  onWateringSourceChange: (sourcePlacementId: string) => void;
  onDelete: () => void;
  onOpenChild: () => void;
  onRegisterPlanting: (value: Record<string, unknown>) => Promise<void>;
  onUpdatePlanting: (plantingId: string, payload: Partial<Planting>) => Promise<void>;
}

function PlacementInspector({
  fieldId,
  placement,
  space,
  devices,
  targetPlacements,
  wateringSources,
  wateringSourceIds,
  usedDeviceIds,
  planting,
  generationTask,
  targetMetric,
  fieldDetailUrl,
  calendarUrl,
  layoutDirty,
  plantBusy,
  onChange,
  onWateringSourceChange,
  onDelete,
  onOpenChild,
  onRegisterPlanting,
  onUpdatePlanting,
}: PlacementInspectorProps) {
  const [deviceQuery, setDeviceQuery] = useState("");
  const [remoteDevices, setRemoteDevices] = useState<LayoutDevice[]>([]);
  const [deviceSearching, setDeviceSearching] = useState(false);
  const [deviceSearchError, setDeviceSearchError] = useState("");
  const [targetQuery, setTargetQuery] = useState("");
  const preset = PRESET_BY_ID[placement.preset];
  const availableDevices = Array.from(new Map([...devices, ...remoteDevices].map((device) => [device.id, device])).values());
  const selectedDevice = availableDevices.find((device) => device.id === placement.binding?.device_id);
  const resourceValue = placement.binding ? `${placement.binding.resource_type}:${placement.binding.resource_id}` : "device:";
  const canBindDevice = DEVICE_BINDABLE_PRESETS.has(placement.preset);
  const deviceOptions = (deviceQuery.trim() ? availableDevices : devices).filter((device) => {
    if (usedDeviceIds.has(device.id)) return false;
    if (placement.preset === "watering_device") return device.group_label === "潅水デバイス";
    if (placement.preset === "camera") return device.group_label === "カメラ";
    if (placement.preset === "sensor") return device.group_label !== "潅水デバイス" && device.group_label !== "カメラ";
    return device.group_label !== "カメラ";
  });
  const filteredDeviceOptions = deviceOptions.filter((device) => (
    device.id === selectedDevice?.id || matchesSearch(deviceQuery, [device.name, device.id, device.kind_label, device.group_label, device.location])
  ));
  const deviceResources = selectedDevice?.resources ?? [];
  const targetIds = placement.binding?.target_placement_ids ?? [];
  const selectableTargets = targetPlacements.filter((target) => targetIds.includes(target.id) || targetAllowedFor(placement.preset, target.preset));
  const filteredTargets = selectableTargets.filter((target) => (
    targetIds.includes(target.id) || matchesSearch(targetQuery, [target.name, PRESET_BY_ID[target.preset].label, target.spaceName])
  ));
  const spaceLocation = space.space_type === "field" ? "圃場（屋外）" : `${space.name}内`;
  const generationActive = generationTask?.status === "queued" || generationTask?.status === "running";

  useEffect(() => {
    setDeviceQuery("");
    setTargetQuery("");
  }, [placement.id]);

  useEffect(() => {
    const query = deviceQuery.trim();
    if (!query) {
      setRemoteDevices([]);
      setDeviceSearching(false);
      setDeviceSearchError("");
      return undefined;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setDeviceSearching(true);
      setDeviceSearchError("");
      void searchLayoutDevices(fieldId, {
        query,
        includeIds: placement.binding?.device_id ? [placement.binding.device_id] : [],
        signal: controller.signal,
      })
        .then((result) => setRemoteDevices(result.items))
        .catch((caught) => {
          if (caught instanceof DOMException && caught.name === "AbortError") return;
          setDeviceSearchError(errorMessage(caught));
        })
        .finally(() => {
          if (!controller.signal.aborted) setDeviceSearching(false);
        });
    }, 350);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [deviceQuery, fieldId, placement.binding?.device_id]);

  const bindDevice = (deviceId: string) => {
    if (!deviceId) {
      onChange({ binding: null });
      return;
    }
    const device = availableDevices.find((candidate) => candidate.id === deviceId);
    const onlyResource = device?.resources.length === 1 ? device.resources[0] : null;
    onChange({
      binding: {
        device_id: deviceId,
        resource_type: placement.preset === "camera" ? "camera" : placement.preset === "sensor" ? "sensor" : onlyResource?.resource_type ?? "device",
        resource_id: placement.preset === "camera" || placement.preset === "sensor" ? "" : onlyResource?.resource_id ?? "",
        target_placement_ids: [],
      },
    });
  };

  const toggleTarget = (targetId: string, checked: boolean) => {
    if (!placement.binding) return;
    const nextTargets = checked
      ? Array.from(new Set([...targetIds, targetId]))
      : targetIds.filter((id) => id !== targetId);
    onChange({ binding: { ...placement.binding, target_placement_ids: nextTargets } });
  };
  const setAllTargets = (selected: boolean) => {
    if (!placement.binding) return;
    onChange({
      binding: {
        ...placement.binding,
        target_placement_ids: selected
          ? Array.from(new Set([...targetIds, ...filteredTargets.map((target) => target.id)]))
          : targetIds.filter((targetId) => !filteredTargets.some((target) => target.id === targetId)),
      },
    });
  };
  return (
    <div className="inspector-content">
      <div className="selection-heading">
        <span className="preset-swatch large" style={{ background: preset.fill, color: preset.stroke }}><preset.icon size={22} /></span>
        <div><span>{preset.label}</span><strong>{placement.name}</strong></div>
      </div>
      <label>名前<input value={placement.name} onChange={(event) => onChange({ name: event.target.value })} /></label>
      <div className="field-grid four">
        <label>X<input type="number" min="0" max={space.grid.columns - placement.width} value={placement.x} onChange={(event) => onChange({ x: Number(event.target.value) })} /></label>
        <label>Y<input type="number" min="0" max={space.grid.rows - placement.height} value={placement.y} onChange={(event) => onChange({ y: Number(event.target.value) })} /></label>
        <label>幅<input type="number" min="1" max={space.grid.columns - placement.x} value={placement.width} onChange={(event) => onChange({ width: Number(event.target.value) })} /></label>
        <label>高さ<input type="number" min="1" max={space.grid.rows - placement.y} value={placement.height} onChange={(event) => onChange({ height: Number(event.target.value) })} /></label>
      </div>
      {canBindDevice && <section className="device-binding-section" aria-label="デバイス紐づけ">
        <div className="filterable-field">
          <span className="field-label">{bindingDeviceLabel(placement.preset)}</span>
          <SearchableSelect
            value={placement.binding?.device_id ?? ""}
            onChange={bindDevice}
            ariaLabel={bindingDeviceLabel(placement.preset)}
            searchPlaceholder="名前、ID、種別、場所を検索"
            emptyMessage="一致するデバイスはありません。"
            query={deviceQuery}
            onQueryChange={setDeviceQuery}
            loading={deviceSearching}
            statusText={deviceSearchError || (deviceQuery.trim() ? `${filteredDeviceOptions.length}件の候補` : "候補は最大50件です。見つからない場合は検索してください。")}
            options={[
              { value: "", label: "紐づけなし", fixed: true },
              ...filteredDeviceOptions.map((device) => ({
                value: device.id,
                label: `${device.name} / ${device.kind_label}`,
                group: device.group_label || "その他デバイス",
                searchText: `${device.id} ${device.location}`,
              })),
            ]}
          />
        </div>
        {placement.preset === "camera" && <HelpDisclosure title="カメラの候補について" align="left"><p>登録済みのネットワークカメラを選択します。候補がない場合は<a href="/cameras/new" target="_blank" rel="noopener">カメラを登録</a>してください。</p></HelpDisclosure>}
        <p className="binding-location"><span>設置環境</span><strong>{spaceLocation}</strong></p>
      </section>}
      {canBindDevice && placement.binding && placement.preset !== "camera" && (
        <div className="filterable-field">
          <span className="field-label">{bindingResourceLabel(placement.preset)}</span>
          <SearchableSelect
            ariaLabel={bindingResourceLabel(placement.preset)}
            value={resourceValue}
            onChange={(nextValue) => {
              const separator = nextValue.indexOf(":");
              onChange({ binding: { ...placement.binding!, resource_type: nextValue.slice(0, separator) as NonNullable<Placement["binding"]>["resource_type"], resource_id: nextValue.slice(separator + 1) } });
            }}
            searchPlaceholder="機能名、ID、種別を検索"
            emptyMessage="一致する機能はありません。"
            options={[
              { value: "device:", label: bindingWholeDeviceLabel(placement.preset), fixed: true },
              ...deviceResources.map((resource) => ({ value: `${resource.resource_type}:${resource.resource_id}`, label: resource.name, searchText: `${resource.resource_id} ${resource.resource_type}` })),
              ...(placement.preset === "sensor" ? [{ value: "sensor:", label: "搭載センサーすべて", fixed: true }] : []),
            ]}
          />
          <HelpDisclosure title={`${bindingResourceLabel(placement.preset)}とは`} align="left"><p>{bindingResourceHelp(placement.preset)}</p></HelpDisclosure>
        </div>
      )}
      {canBindDevice && placement.binding && selectableTargets.length > 0 && (
        <fieldset className="target-selector">
          <legend>{relationTargetLabel(placement.preset)}</legend>
          {selectableTargets.length > 1 && <CollectionSearch value={targetQuery} onChange={setTargetQuery} placeholder="培地・空間を検索" label={`${relationTargetLabel(placement.preset)}を検索`} />}
          <div className="target-selector-actions">
            <button type="button" onClick={() => setAllTargets(true)} disabled={filteredTargets.every((target) => targetIds.includes(target.id))} title={filteredTargets.every((target) => targetIds.includes(target.id)) ? "表示中の対象はすべて選択済みです" : "表示中の対象をすべて選択"}><CheckCheck size={13} />すべて選択</button>
            <button type="button" onClick={() => setAllTargets(false)} disabled={!filteredTargets.some((target) => targetIds.includes(target.id))} title={!filteredTargets.some((target) => targetIds.includes(target.id)) ? "表示中に選択済みの対象はありません" : "表示中の対象の選択を解除"}>すべて解除</button>
          </div>
          {filteredTargets.map((target) => (
            <label key={target.id}>
              <input type="checkbox" checked={targetIds.includes(target.id)} onChange={(event) => toggleTarget(target.id, event.target.checked)} />
              <span><strong>{target.name}</strong><small>{PRESET_BY_ID[target.preset].label} / {target.spaceId === space.id ? "この空間" : target.spaceName}</small></span>
            </label>
          ))}
          {filteredTargets.length === 0 && <p className="collection-empty">一致する対象はありません。</p>}
        </fieldset>
      )}
      {selectedDevice && (
        <dl className="device-summary">
          <dt>状態</dt><dd><span className={`device-state ${selectedDevice.state}`}>{selectedDevice.state}</span></dd>
          <dt>ID</dt><dd><code>{selectedDevice.id}</code></dd>
          {selectedDevice.location && <><dt>登録場所</dt><dd>{selectedDevice.location}</dd></>}
        </dl>
      )}
      {selectedDevice && placement.preset === "camera" && (
        <div className="camera-placement-links">
          {selectedDevice.preview_url && <a href={selectedDevice.preview_url} target="_blank" rel="noreferrer"><ExternalLink size={15} />ライブ映像を見る</a>}
          {selectedDevice.manage_url && <a href={selectedDevice.manage_url}><ExternalLink size={15} />カメラ設定を開く</a>}
        </div>
      )}
      <label>メモ<textarea value={placement.memo} onChange={(event) => onChange({ memo: event.target.value })} /></label>
      {PLANTABLE_PRESETS.has(placement.preset) && (
        <section className="watering-source-section" aria-label="潅水方法">
          <div className="watering-source-heading"><Droplets size={17} /><strong>潅水方法</strong></div>
          <SearchableSelect
            ariaLabel="潅水方法"
            value={wateringSourceIds[0] ?? ""}
            onChange={onWateringSourceChange}
            searchPlaceholder="潅水機、デバイス、設置空間を検索"
            emptyMessage="一致する潅水機はありません。"
            options={[
              { value: "", label: "手動潅水", fixed: true },
              ...wateringSources.map((source) => ({
                value: source.id,
                label: `${source.name} / ${source.deviceName} / ${source.spaceId === space.id ? "この空間" : source.spaceName}`,
                searchText: `${source.deviceName} ${source.spaceName}`,
              })),
            ]}
          />
          {wateringSourceIds.length > 1 && <span className="watering-source-warning">複数の潅水機に接続中</span>}
        </section>
      )}
      {PLANTABLE_PRESETS.has(placement.preset) && (
        planting ? (
          <section className="active-planting" aria-label="定植情報">
            <div><Leaf size={18} /><span>定植中</span></div>
            <strong>{planting.crop_name}{planting.cultivar ? ` / ${planting.cultivar}` : ""}</strong>
            <dl>
              <dt>定植日</dt><dd>{formatDate(planting.planted_on)}</dd>
              <dt>株数</dt><dd>{planting.plant_count}株</dd>
            </dl>
            <PlantTargetEditor planting={planting} busy={plantBusy || generationActive} focusMetric={targetMetric} onSave={onUpdatePlanting} />
            {generationTask?.status === "failed" && <p className="generation-status failed" role="alert">AI計画の作成に失敗しました。カレンダー画面から再実行できます。{generationTask.error && ` (${generationTask.error})`}</p>}
            <div className="planting-links">
              <a href={calendarUrl} target="_blank" rel="noopener" aria-label="カレンダーを新しいタブで開く" aria-busy={generationActive} className={generationActive ? "generation-active" : undefined}>
                {generationActive ? <ActivityIndicator size="small" /> : <CalendarDays size={16} />}
                {generationActive ? "AI計画を作成中..." : "カレンダーを開く"}
              </a>
              <a href={`${fieldDetailUrl}?planting=${encodeURIComponent(planting.id)}#cultivation`} target="_blank" rel="noopener" title="栽培タブを新しいタブで開いて定植情報を編集"><ExternalLink size={16} />作物情報を編集</a>
            </div>
          </section>
        ) : (
          <PlantRegistrationForm
            key={placement.id}
            draftKey={`ina-planting-draft:${placement.id}`}
            placementPreset={placement.preset}
            space={space}
            layoutDirty={layoutDirty}
            busy={plantBusy}
            onSubmit={onRegisterPlanting}
          />
        )
      )}
      {placement.child_space_id && <button type="button" className="open-child-button" onClick={onOpenChild}><DoorOpen size={17} />内部の設置ビューを開く</button>}
      <button type="button" className="delete-button" onClick={onDelete}><Trash2 size={17} />配置から削除</button>
    </div>
  );
}

function CollectionSearch({ value, onChange, placeholder, label }: { value: string; onChange: (value: string) => void; placeholder: string; label: string }) {
  return (
    <label className="collection-search">
      <Search size={14} />
      <input type="search" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} aria-label={label} />
      {value && <button type="button" onClick={() => onChange("")} aria-label={`${label}をクリア`} title={`${label}をクリア`}><X size={13} /></button>}
    </label>
  );
}

const PLANT_TARGET_SPECS = [
  { id: "air_temperature_c", label: "気温", unit: "℃", min: -40, max: 80, step: 0.5, defaults: [10, 35] },
  { id: "air_humidity_percent", label: "湿度", unit: "%", min: 0, max: 100, step: 1, defaults: [50, 75] },
  { id: "soil_moisture_percent", label: "土壌水分", unit: "%", min: 0, max: 100, step: 1, defaults: [35, 65] },
  { id: "soil_temperature_c", label: "地温", unit: "℃", min: -20, max: 60, step: 0.5, defaults: [10, 30] },
  { id: "soil_ec_us_cm", label: "土壌EC", unit: "uS/cm", min: 0, max: 3000, step: 10, defaults: [500, 1500] },
  { id: "soil_ph", label: "土壌pH", unit: "", min: 0, max: 14, step: 0.1, defaults: [5.5, 6.5] },
  { id: "par_umol_m2_s", label: "PAR", unit: "umol/m2/s", min: 0, max: 2000, step: 10, defaults: [300, 1000] },
] as const;

type EditableGrowthTargets = Record<string, { min: number | null; max: number | null }>;

function PlantTargetEditor({
  planting,
  busy,
  focusMetric,
  onSave,
}: {
  planting: Planting;
  busy: boolean;
  focusMetric?: string;
  onSave: (plantingId: string, payload: Partial<Planting>) => Promise<void>;
}) {
  const [targets, setTargets] = useState<EditableGrowthTargets>(() => structuredClone(planting.growth_targets ?? {}));
  const [saved, setSaved] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const dirty = JSON.stringify(targets) !== JSON.stringify(planting.growth_targets ?? {});
  const blockingReasons = [
    ...(!dirty ? ["目標レンジは変更されていません"] : []),
    ...(busy ? ["現在の処理が完了するまでお待ちください"] : []),
  ];

  useEffect(() => {
    setTargets(structuredClone(planting.growth_targets ?? {}));
    setSaved(false);
  }, [planting.id]);

  useEffect(() => {
    if (!focusMetric) return;
    const row = document.querySelector<HTMLElement>(`.plant-target-row[data-target-metric="${focusMetric}"]`);
    if (!row) return;
    row.classList.add("focused");
    requestAnimationFrame(() => {
      row.scrollIntoView({ block: "center", behavior: "smooth" });
      row.querySelector<HTMLInputElement>('input[type="checkbox"]')?.focus({ preventScroll: true });
    });
  }, [focusMetric, planting.id]);

  const setTarget = (metric: string, value: { min: number | null; max: number | null }) => {
    setSaved(false);
    setTargets((current) => ({ ...current, [metric]: value }));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onSave(planting.id, { growth_targets: targets });
      setSaved(true);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="plant-target-editor" onSubmit={(event) => void submit(event)}>
      <div className="plant-target-heading"><strong>目標レンジ</strong>{saved && <span><Check size={13} />保存済み</span>}</div>
      {PLANT_TARGET_SPECS.map((spec) => {
        const target = targets[spec.id] ?? { min: null, max: null };
        const enabled = target.min !== null || target.max !== null;
        const minimum = target.min ?? spec.defaults[0];
        const maximum = target.max ?? spec.defaults[1];
        const left = ((minimum - spec.min) / (spec.max - spec.min)) * 100;
        const width = ((maximum - minimum) / (spec.max - spec.min)) * 100;
        return (
          <div className={`plant-target-row ${enabled ? "enabled" : ""}`} key={spec.id} data-target-metric={spec.id}>
            <label className="plant-target-toggle">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setTarget(spec.id, event.target.checked ? { min: spec.defaults[0], max: spec.defaults[1] } : { min: null, max: null })}
              />
              <span>{spec.label}</span>
            </label>
            {enabled && (
              <>
                <div className="plant-target-values"><span>{minimum}</span><span>{maximum} {spec.unit}</span></div>
                <div className="plant-target-range">
                  <span className="plant-target-zone" style={{ left: `${left}%`, width: `${width}%` }} />
                  <input
                    aria-label={`${spec.label}下限`}
                    type="range"
                    min={spec.min}
                    max={spec.max}
                    step={spec.step}
                    value={minimum}
                    onChange={(event) => setTarget(spec.id, { min: Math.min(Number(event.target.value), maximum), max: maximum })}
                  />
                  <input
                    aria-label={`${spec.label}上限`}
                    type="range"
                    min={spec.min}
                    max={spec.max}
                    step={spec.step}
                    value={maximum}
                    onChange={(event) => setTarget(spec.id, { min: minimum, max: Math.max(Number(event.target.value), minimum) })}
                  />
                </div>
              </>
            )}
          </div>
        );
      })}
      <DisabledActionReason id={`plant-target-blocked-${planting.id}`} reasons={blockingReasons} prefix="目標を保存するには" />
      <button type="submit" disabled={blockingReasons.length > 0 || submitting} aria-busy={submitting} aria-describedby={blockingReasons.length > 0 ? `plant-target-blocked-${planting.id}` : undefined} title={disabledActionTitle(blockingReasons)}>{!submitting && <Save size={14} />}{submitting ? "目標を保存しています" : "目標を保存"}</button>
    </form>
  );
}

function PlantRegistrationForm({
  space,
  placementPreset,
  draftKey,
  layoutDirty,
  busy,
  onSubmit,
}: {
  space: LayoutSpace;
  placementPreset: PlacementPreset;
  draftKey: string;
  layoutDirty: boolean;
  busy: boolean;
  onSubmit: (value: Record<string, unknown>) => Promise<void>;
}) {
  const cultivationMethods = cultivationMethodsFor(placementPreset);
  const [draft, setDraft] = useState(() => loadPlantingDraft(draftKey, cultivationMethods[0]?.value ?? ""));
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const blockingReasons = plantingRegistrationBlockingReasons(draft, layoutDirty, busy);
  const blockingReasonId = `planting-blocked-${draftKey.replace(/[^a-zA-Z0-9_-]/g, "-")}`;

  useEffect(() => {
    localStorage.setItem(draftKey, JSON.stringify(draft));
  }, [draft, draftKey]);

  const change = <Key extends keyof PlantingDraft>(key: Key, value: PlantingDraft[Key]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError("");
    setSubmitting(true);
    try {
      await onSubmit({
        crop_name: draft.cropName,
        cultivar: draft.cultivar,
        crop_category: draft.cropCategory,
        tree_age_years: draft.cropCategory === "fruit_tree" ? draft.treeAgeYears : null,
        planted_on: draft.plantedOn,
        plant_count: draft.plantCount,
        cultivation_method: draft.cultivationMethod,
        planning_notes: draft.planningNotes,
        conditions: {
          environment: SPACE_TYPE_LABELS[space.space_type],
          soil_or_substrate: plantingChoiceLabel(SOIL_OR_SUBSTRATE_OPTIONS, draft.soil),
          sunlight: plantingChoiceLabel(SUNLIGHT_OPTIONS, draft.sunlight),
          notes: draft.notes,
        },
      });
      localStorage.removeItem(draftKey);
    } catch (caught) {
      setFormError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="plant-registration">
      <div className="section-title"><Leaf size={17} /><strong>この場所に定植</strong></div>
      <form onSubmit={(event) => void submit(event)}>
        <label>作物名（必須）<input name="crop_name" required value={draft.cropName} onChange={(event) => change("cropName", event.target.value)} placeholder="例: ブルーベリー" /></label>
        <label>品種<input name="cultivar" value={draft.cultivar} onChange={(event) => change("cultivar", event.target.value)} placeholder="例: オニール" /></label>
        <div className="field-grid two">
          <label>作物区分（必須）<select name="crop_category" value={draft.cropCategory} onChange={(event) => change("cropCategory", event.target.value as Planting["crop_category"])}>{Object.entries(CROP_CATEGORY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          {draft.cropCategory === "fruit_tree" && <label>樹齢（必須）<input name="tree_age_years" required type="number" min="0" max="300" value={draft.treeAgeYears ?? ""} onChange={(event) => change("treeAgeYears", event.target.value === "" ? null : Number(event.target.value))} placeholder="年" /></label>}
        </div>
        <div className="field-grid two">
          <label>定植日（必須）<input name="planted_on" required type="date" value={draft.plantedOn} onChange={(event) => change("plantedOn", event.target.value)} /></label>
          <label>株数（必須）<input name="plant_count" required type="number" min="1" value={draft.plantCount} onChange={(event) => change("plantCount", Number(event.target.value))} /></label>
        </div>
        <label>栽培方式（必須）<select name="cultivation_method" required value={draft.cultivationMethod} onChange={(event) => change("cultivationMethod", event.target.value)}>{cultivationMethods.map((method) => <option key={method.value} value={method.value}>{method.label}</option>)}</select></label>
        <label>用土・培地（必須）
          <select name="soil_or_substrate" required value={draft.soil} onChange={(event) => change("soil", event.target.value)}>
            <option value="">選択してください</option>
            {draft.soil && !SOIL_OR_SUBSTRATE_OPTIONS.some((option) => option.value === draft.soil) && <option value={draft.soil}>{draft.soil}（保存済み）</option>}
            {SOIL_OR_SUBSTRATE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label>日当たり（必須）
          <select name="sunlight" required value={draft.sunlight} onChange={(event) => change("sunlight", event.target.value)}>
            <option value="">選択してください</option>
            {draft.sunlight && !SUNLIGHT_OPTIONS.some((option) => option.value === draft.sunlight) && <option value={draft.sunlight}>{draft.sunlight}（保存済み）</option>}
            {SUNLIGHT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label>補足<textarea value={draft.notes} onChange={(event) => change("notes", event.target.value)} placeholder="購入時の状態、育苗条件など" /></label>
        <label className="ai-planning-notes"><span><Sparkles size={14} />AI計画へ伝えること</span><textarea value={draft.planningNotes} onChange={(event) => change("planningNotes", event.target.value)} placeholder="収穫を優先、農薬は使わない、週末だけ作業可能など" /></label>
        <p className="ai-call-notice">登録時にAIを1回呼び出し、目標レンジと12か月計画を生成します。AI未設定時は標準案を使用します。</p>
        <DisabledActionReason id={blockingReasonId} reasons={blockingReasons} prefix="AI計画を生成するには" />
        {formError && <p className="form-error">{formError}</p>}
        <button
          type="submit"
          className="register-button"
          disabled={blockingReasons.length > 0 || submitting}
          aria-busy={submitting}
          aria-describedby={blockingReasons.length > 0 ? blockingReasonId : undefined}
          title={disabledActionTitle(blockingReasons)}
        >
          {!submitting && <Sparkles size={16} />}{submitting ? "目標と計画を生成しています" : "定植を登録してAI計画を生成"}
        </button>
      </form>
    </section>
  );
}

interface PlantingDraft {
  cropName: string;
  cultivar: string;
  cropCategory: Planting["crop_category"];
  treeAgeYears: number | null;
  plantedOn: string;
  plantCount: number;
  cultivationMethod: string;
  soil: string;
  sunlight: string;
  notes: string;
  planningNotes: string;
}

const CROP_CATEGORY_LABELS: Record<Planting["crop_category"], string> = {
  vegetable: "野菜",
  fruit_tree: "果樹",
  flower: "花き",
  herb: "ハーブ",
  other: "その他",
};

const SOIL_OR_SUBSTRATE_OPTIONS = [
  { value: "field_soil", label: "畑土・地植え土壌" },
  { value: "general_potting_mix", label: "一般培養土" },
  { value: "vegetable_potting_mix", label: "野菜用培養土" },
  { value: "fruit_tree_potting_mix", label: "果樹用培養土" },
  { value: "acidic_blueberry_mix", label: "ブルーベリー用酸性用土" },
  { value: "cocopeat", label: "ココピート" },
  { value: "rockwool", label: "ロックウール" },
  { value: "inert_granular_media", label: "パーライト・バーミキュライト等" },
  { value: "hydroponic_solution", label: "水耕養液（固形培地なし）" },
  { value: "other_or_unknown", label: "その他・不明" },
] as const;

const SUNLIGHT_OPTIONS = [
  { value: "full_sun", label: "日なた（直射6時間以上）" },
  { value: "partial_sun", label: "半日なた（直射3〜6時間）" },
  { value: "partial_shade", label: "半日陰（直射1〜3時間）" },
  { value: "shade", label: "日陰（直射1時間未満）" },
  { value: "grow_light", label: "植物育成ライト主体" },
  { value: "unknown", label: "不明" },
] as const;

function plantingRegistrationBlockingReasons(draft: PlantingDraft, layoutDirty: boolean, busy: boolean) {
  const reasons: string[] = [];
  if (layoutDirty) reasons.push("先に配置を保存してください");
  if (!draft.cropName.trim()) reasons.push("作物名を入力してください");
  if (!draft.plantedOn) reasons.push("定植日を選択してください");
  if (!Number.isFinite(draft.plantCount) || draft.plantCount < 1) reasons.push("株数を1以上で入力してください");
  if (!draft.cultivationMethod) reasons.push("栽培方式を選択してください");
  if (!draft.soil) reasons.push("用土・培地を選択してください");
  if (!draft.sunlight) reasons.push("日当たりを選択してください");
  if (draft.cropCategory === "fruit_tree" && draft.treeAgeYears === null) reasons.push("果樹の樹齢を入力してください");
  if (busy) reasons.push("現在のAI処理が完了するまでお待ちください");
  return reasons;
}

function plantingChoiceLabel(options: ReadonlyArray<{ value: string; label: string }>, value: string) {
  return options.find((option) => option.value === value)?.label ?? value;
}

function loadPlantingDraft(key: string, defaultMethod: string): PlantingDraft {
  const defaults: PlantingDraft = { cropName: "", cultivar: "", cropCategory: "vegetable", treeAgeYears: null, plantedOn: todayString(), plantCount: 1, cultivationMethod: defaultMethod, soil: "", sunlight: "", notes: "", planningNotes: "" };
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? "null") as Partial<PlantingDraft> | null;
    return saved ? { ...defaults, ...saved, cultivationMethod: saved.cultivationMethod || defaultMethod } : defaults;
  } catch {
    return defaults;
  }
}

function cultivationMethodsFor(preset: PlacementPreset): Array<{ value: string; label: string }> {
  const methods: Partial<Record<PlacementPreset, Array<{ value: string; label: string }>>> = {
    ridge: [{ value: "ridge_soil", label: "畝・土耕" }, { value: "ridge_mulch", label: "畝・マルチ栽培" }],
    tree: [{ value: "in_ground_tree", label: "地植え果樹・樹木" }],
    pot: [{ value: "container", label: "鉢・コンテナ栽培" }],
    hydroponic_bed: [{ value: "hydroponic", label: "水耕栽培" }, { value: "nutrient_solution", label: "養液栽培" }],
  };
  return methods[preset] ?? [{ value: "other", label: "その他" }];
}

function relationTargetLabel(preset: PlacementPreset) {
  if (preset === "watering_device") return "潅水する培地";
  if (preset === "sensor") return "計測する培地・空間（任意）";
  if (preset === "camera") return "監視する培地・空間";
  if (preset === "grow_light") return "補光する培地・空間（任意）";
  if (preset === "mister") return "噴霧する培地・空間（任意）";
  if (preset === "fan" || preset === "hvac") return "環境制御する空間（任意）";
  return "接続対象（任意）";
}

function bindingDeviceLabel(preset: PlacementPreset) {
  if (preset === "watering_device") return "紐づける潅水デバイス";
  if (preset === "sensor") return "紐づけるセンサーデバイス";
  if (preset === "camera") return "紐づけるカメラ";
  return "紐づける設備デバイス";
}

function bindingResourceLabel(preset: PlacementPreset) {
  if (preset === "watering_device") return "使用する潅水系統";
  if (preset === "sensor") return "使用する計測機能";
  if (preset === "grow_light") return "使用する照明出力";
  if (preset === "mister") return "使用する噴霧出力";
  if (preset === "fan") return "使用する送風出力";
  if (preset === "hvac") return "使用する空調出力";
  return "使用する機能・接続口";
}

function bindingWholeDeviceLabel(preset: PlacementPreset) {
  if (preset === "sensor") return "デバイスの計測機能すべて";
  if (preset === "watering_device") return "デバイスの潅水系統すべて";
  return "デバイス全体";
}

function bindingResourceHelp(preset: PlacementPreset) {
  if (preset === "sensor") return "複数のセンサーを搭載している場合に、ここで使う計測機能を指定します。";
  if (preset === "watering_device") return "WRSなどに複数の潅水出力がある場合に、この配置で使う系統を指定します。";
  return "複数の出力がある機器では、この配置から制御する出力を指定します。";
}

function targetAllowedFor(sourcePreset: PlacementPreset, targetPreset: PlacementPreset) {
  if (sourcePreset === "watering_device") return PLANTABLE_PRESETS.has(targetPreset);
  if (sourcePreset === "fan" || sourcePreset === "hvac") return SPACE_TARGET_PRESETS.has(targetPreset);
  return TARGETABLE_PRESETS.has(targetPreset);
}

function northDirectionLabel(angle: number) {
  const directions = ["上", "右上", "右", "右下", "下", "左下", "左", "左上"];
  return directions[Math.round((((angle % 360) + 360) % 360) / 45) % directions.length];
}

function buildBreadcrumbs(layout: FieldLayout, activeSpaceId: string) {
  const result: LayoutSpace[] = [];
  let cursor = layout.spaces.find((space) => space.id === activeSpaceId);
  const visited = new Set<string>();
  while (cursor && !visited.has(cursor.id)) {
    result.unshift(cursor);
    visited.add(cursor.id);
    if (cursor.id === layout.root_space_id) break;
    const parent = layout.spaces.find((space) => space.placements.some((placement) => placement.child_space_id === cursor?.id));
    cursor = parent;
  }
  return result;
}

function requireSpace(layout: FieldLayout, spaceId: string) {
  const space = layout.spaces.find((item) => item.id === spaceId);
  if (!space) throw new Error(`space not found: ${spaceId}`);
  return space;
}

function removeSpaceTree(layout: FieldLayout, spaceId: string) {
  const space = layout.spaces.find((item) => item.id === spaceId);
  if (!space) return;
  space.placements.forEach((placement) => {
    if (placement.child_space_id) removeSpaceTree(layout, placement.child_space_id);
  });
  layout.spaces = layout.spaces.filter((item) => item.id !== spaceId);
}

function ensureActiveSpace(layout: FieldLayout, activeSpaceId: string, setActiveSpaceId: (value: string) => void, setSelectedId: (value: string | null) => void) {
  if (layout.spaces.some((space) => space.id === activeSpaceId)) return;
  setActiveSpaceId(layout.root_space_id);
  setSelectedId(null);
}

function createId(prefix: string) {
  const id = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${id}`;
}

function clamp(value: number, minimum: number, maximum: number) {
  const safeValue = Number.isFinite(value) ? value : minimum;
  return Math.min(Math.max(safeValue, minimum), Math.max(minimum, maximum));
}
