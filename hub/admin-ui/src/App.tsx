import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowUp,
  CalendarDays,
  Check,
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
  X,
} from "lucide-react";

import {
  askPlantQuestion,
  addPlantAction,
  completePlantAction,
  createPlanting,
  deletePlantAction,
  loadLayout,
  loadLayoutDevices,
  loadPlantBundle,
  regeneratePlantCalendar,
  saveLayout,
  updatePlantAction,
  updatePlanting,
} from "./api";
import { errorMessage, formatDate, todayString } from "./formatters";
import { InstallationCanvas } from "./InstallationCanvas";
import { PlantCalendarDrawer } from "./plant-calendar/PlantCalendarDrawer";
import { PRESET_BY_ID, PRESETS, SPACE_TYPE_LABELS } from "./presets";
import { matchesSearch } from "./search";
import type {
  FieldLayout,
  LayoutDevice,
  LayoutSpace,
  Placement,
  PlacementPreset,
  PlantBundle,
  PlantCalendarAction,
  Planting,
} from "./types";

interface AppProps {
  fieldId: string;
  fieldName: string;
  fieldDetailUrl: string;
}

const HISTORY_LIMIT = 40;
const EMPTY_PLANT_BUNDLE: PlantBundle = { action_types: [], plantings: [], calendars: {}, suggestions: [], work_logs: [] };
const PLANTABLE_PRESETS = new Set<PlacementPreset>(["ridge", "tree", "pot", "hydroponic_bed"]);
const SPACE_TARGET_PRESETS = new Set<PlacementPreset>(["greenhouse", "open_field", "shade_area"]);
const TARGETABLE_PRESETS = new Set<PlacementPreset>(["greenhouse", "open_field", "shade_area", ...PLANTABLE_PRESETS]);
const DEVICE_BINDABLE_PRESETS = new Set<PlacementPreset>(["watering_device", "sensor", "grow_light", "mister", "fan", "hvac"]);
const REQUESTED_CALENDAR_ID = new URLSearchParams(window.location.search).get("calendar") ?? "";
const REQUESTED_SPACE_ID = new URLSearchParams(window.location.search).get("space") ?? "";

export function App({ fieldId, fieldName, fieldDetailUrl }: AppProps) {
  const [layout, setLayout] = useState<FieldLayout | null>(null);
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

  const reload = async () => {
    setLoading(true);
    setError("");
    try {
      const [nextLayout, nextDevices, nextPlantBundle] = await Promise.all([
        loadLayout(fieldId),
        loadLayoutDevices(fieldId),
        loadPlantBundle(fieldId),
      ]);
      setLayout(nextLayout);
      setDevices(nextDevices);
      setPlantBundle(nextPlantBundle);
      setActiveSpaceId(nextLayout.spaces.some((space) => space.id === REQUESTED_SPACE_ID) ? REQUESTED_SPACE_ID : nextLayout.root_space_id);
      setSelectedId(null);
      setPast([]);
      setFuture([]);
      setDirty(false);
      if (REQUESTED_CALENDAR_ID && nextPlantBundle.plantings.some((planting) => planting.id === REQUESTED_CALENDAR_ID)) {
        setCalendarPlantingId(REQUESTED_CALENDAR_ID);
        setCalendarOpen(true);
      }
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
    () => PRESETS.filter((preset) => matchesSearch(paletteQuery, [preset.label, preset.group, ...preset.keywords])),
    [paletteQuery],
  );

  const refreshPlants = async () => {
    const nextBundle = await loadPlantBundle(fieldId);
    setPlantBundle(nextBundle);
    return nextBundle;
  };

  const registerPlanting = async (payload: Record<string, unknown>) => {
    setPlantBusy(true);
    setError("");
    try {
      const created = await createPlanting(fieldId, payload) as { planting?: Planting };
      const nextBundle = await refreshPlants();
      const plantingId = created.planting?.id || nextBundle.plantings.find((planting) => planting.placement_id === payload.placement_id)?.id || "";
      setCalendarPlantingId(plantingId);
      setCalendarOpen(true);
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const editPlantAction = async (plantingId: string, actionId: string, payload: Partial<PlantCalendarAction> & { use_as_guidance?: boolean }) => {
    setPlantBusy(true);
    setError("");
    try {
      await updatePlantAction(plantingId, actionId, payload);
      await refreshPlants();
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const regenerateCalendar = async (plantingId: string, startDate: string, planningNotes: string) => {
    setPlantBusy(true);
    setError("");
    try {
      await regeneratePlantCalendar(plantingId, { start_date: startDate, planning_notes: planningNotes });
      await refreshPlants();
    } catch (caught) {
      setError(errorMessage(caught));
      throw caught;
    } finally {
      setPlantBusy(false);
    }
  };

  const createPlantAction = async (plantingId: string, payload: Partial<PlantCalendarAction>) => {
    setPlantBusy(true);
    try {
      await addPlantAction(plantingId, payload);
      await refreshPlants();
    } finally {
      setPlantBusy(false);
    }
  };

  const removePlantAction = async (plantingId: string, actionId: string) => {
    setPlantBusy(true);
    try {
      await deletePlantAction(plantingId, actionId);
      await refreshPlants();
    } finally {
      setPlantBusy(false);
    }
  };

  const recordPlantAction = async (plantingId: string, actionId: string, performedOn: string, note: string, rating: number, images: File[]) => {
    setPlantBusy(true);
    setError("");
    try {
      await completePlantAction(plantingId, actionId, { performed_on: performedOn, note, rating, images });
      await refreshPlants();
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
      await refreshPlants();
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
    try {
      const saved = await saveLayout(fieldId, layout);
      setLayout(saved);
      setPast([]);
      setFuture([]);
      setDirty(false);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSaving(false);
    }
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
    return <div className="layout-state">設置ビューを読み込んでいます...</div>;
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
    <div className={`installation-app ${error ? "has-error" : ""}`}>
      <header className="editor-header">
        <div className="editor-identity">
          <a className="icon-link" href={fieldDetailUrl} title="圃場詳細へ戻る"><ArrowLeft size={19} /></a>
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
          <button type="button" className="calendar-button" onClick={() => openPlantCalendar()}>
            <CalendarDays size={17} />
            <span>栽培カレンダー</span>
            {plantBundle.suggestions.length > 0 && <strong>{plantBundle.suggestions.length}</strong>}
          </button>
          <span className={`save-state ${dirty ? "dirty" : ""}`}>{saving ? "保存中" : dirty ? "未保存" : `保存済み r${layout.revision}`}</span>
          <button type="button" className="icon-button" onClick={undo} disabled={!past.length} title="元に戻す"><Undo2 size={18} /></button>
          <button type="button" className="icon-button" onClick={redo} disabled={!future.length} title="やり直す"><Redo2 size={18} /></button>
          <div className="zoom-control">
            <button type="button" onClick={() => setZoom((value) => clamp(value / 1.15, 0.2, 2.5))} title="縮小"><Minus size={16} /></button>
            <span>{Math.round(zoom * 100)}%</span>
            <button type="button" onClick={() => setZoom((value) => clamp(value * 1.15, 0.2, 2.5))} title="拡大"><Plus size={16} /></button>
          </div>
          <button type="button" className="save-button" onClick={() => void persist()} disabled={!dirty || saving}><Save size={17} />保存</button>
        </div>
      </header>

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
          <label className="palette-search"><Search size={16} /><input type="search" value={paletteQuery} onChange={(event) => setPaletteQuery(event.target.value)} placeholder="配置物を検索" aria-label="配置物を検索" />{paletteQuery && <button type="button" onClick={() => setPaletteQuery("")} title="検索をクリア"><X size={14} /></button>}</label>
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
            <span>{activeSpace.grid.columns * activeSpace.grid.cell_size_m}m × {activeSpace.grid.rows * activeSpace.grid.cell_size_m}m</span>
          </div>
          <InstallationCanvas
            layout={layout}
            space={activeSpace}
            selectedId={selectedId}
            plantingByPlacementId={plantingByPlacementId}
            wateringSourceNamesByPlacementId={wateringSourceNamesByPlacementId}
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
              placement={selectedPlacement}
              space={activeSpace}
              devices={devices}
              targetPlacements={targetPlacements}
              wateringSources={wateringSources}
              wateringSourceIds={wateringSources.filter((source) => source.targetPlacementIds.includes(selectedPlacement.id)).map((source) => source.id)}
              usedDeviceIds={usedDeviceIds}
              planting={selectedPlanting}
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
              onOpenCalendar={() => selectedPlanting && openPlantCalendar(selectedPlanting.id)}
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
          onAskQuestion={answerPlantQuestion}
          onRegenerate={regenerateCalendar}
          onAddAction={createPlantAction}
          onDeleteAction={removePlantAction}
        />
      )}
    </div>
  );
}

function SpaceInspector({ space, isRoot, onChange }: { space: LayoutSpace; isRoot: boolean; onChange: (patch: Partial<LayoutSpace>) => void }) {
  const northAngle = clamp(Math.round(space.north_angle_deg ?? 0), 0, 359);
  return (
    <div className="inspector-content">
      <div className="panel-heading"><span>空間設定</span><strong>{SPACE_TYPE_LABELS[space.space_type]}</strong></div>
      <label>空間名<input value={space.name} onChange={(event) => onChange({ name: event.target.value })} /></label>
      <label>空間種別
        <select value={space.space_type} disabled={isRoot} onChange={(event) => onChange({ space_type: event.target.value as LayoutSpace["space_type"] })}>
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
  placement: Placement;
  space: LayoutSpace;
  devices: LayoutDevice[];
  targetPlacements: Array<{ id: string; name: string; preset: PlacementPreset; spaceId: string; spaceName: string }>;
  wateringSources: Array<{ id: string; name: string; spaceId: string; spaceName: string; deviceName: string; targetPlacementIds: string[] }>;
  wateringSourceIds: string[];
  usedDeviceIds: Set<string>;
  planting: Planting | null;
  fieldDetailUrl: string;
  layoutDirty: boolean;
  plantBusy: boolean;
  onChange: (patch: Partial<Placement>) => void;
  onWateringSourceChange: (sourcePlacementId: string) => void;
  onDelete: () => void;
  onOpenChild: () => void;
  onRegisterPlanting: (value: Record<string, unknown>) => Promise<void>;
  onOpenCalendar: () => void;
  onUpdatePlanting: (plantingId: string, payload: Partial<Planting>) => Promise<void>;
}

function PlacementInspector({
  placement,
  space,
  devices,
  targetPlacements,
  wateringSources,
  wateringSourceIds,
  usedDeviceIds,
  planting,
  fieldDetailUrl,
  layoutDirty,
  plantBusy,
  onChange,
  onWateringSourceChange,
  onDelete,
  onOpenChild,
  onRegisterPlanting,
  onOpenCalendar,
  onUpdatePlanting,
}: PlacementInspectorProps) {
  const preset = PRESET_BY_ID[placement.preset];
  const selectedDevice = devices.find((device) => device.id === placement.binding?.device_id);
  const resourceValue = placement.binding ? `${placement.binding.resource_type}:${placement.binding.resource_id}` : "device:";
  const canBindDevice = DEVICE_BINDABLE_PRESETS.has(placement.preset);
  const deviceOptions = devices.filter((device) => {
    if (usedDeviceIds.has(device.id)) return false;
    if (placement.preset === "watering_device") return device.group_label === "潅水デバイス";
    if (placement.preset === "sensor") return device.group_label !== "潅水デバイス";
    return true;
  });
  const groupedDevices = Object.entries(deviceOptions.reduce<Record<string, LayoutDevice[]>>((groups, device) => {
    const group = device.group_label || "その他デバイス";
    groups[group] = [...(groups[group] ?? []), device];
    return groups;
  }, {}));
  const targetIds = placement.binding?.target_placement_ids ?? [];
  const selectableTargets = targetPlacements.filter((target) => targetIds.includes(target.id) || targetAllowedFor(placement.preset, target.preset));
  const spaceLocation = space.space_type === "field" ? "圃場（屋外）" : `${space.name}内`;

  const toggleTarget = (targetId: string, checked: boolean) => {
    if (!placement.binding) return;
    const nextTargets = checked
      ? Array.from(new Set([...targetIds, targetId]))
      : targetIds.filter((id) => id !== targetId);
    onChange({ binding: { ...placement.binding, target_placement_ids: nextTargets } });
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
        <label>{placement.preset === "watering_device" ? "紐づける潅水デバイス" : placement.preset === "sensor" ? "紐づけるセンサーデバイス" : "紐づける設備デバイス"}
          <select
            value={placement.binding?.device_id ?? ""}
            onChange={(event) => onChange({ binding: event.target.value ? { device_id: event.target.value, resource_type: "device", resource_id: "", target_placement_ids: [] } : null })}
          >
            <option value="">紐づけなし</option>
            {groupedDevices.map(([group, groupDevices]) => (
              <optgroup key={group} label={group}>
                {(groupDevices ?? []).map((device) => <option key={device.id} value={device.id}>{device.name} / {device.kind_label}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        <p className="binding-location"><span>設置環境</span><strong>{spaceLocation}</strong></p>
      </section>}
      {canBindDevice && placement.binding && (
        <label>デバイス内機能
          <select
            value={resourceValue}
            onChange={(event) => {
              const separator = event.target.value.indexOf(":");
              onChange({ binding: { ...placement.binding!, resource_type: event.target.value.slice(0, separator) as NonNullable<Placement["binding"]>["resource_type"], resource_id: event.target.value.slice(separator + 1) } });
            }}
          >
            <option value="device:">デバイス全体</option>
            {selectedDevice?.resources.map((resource) => <option key={`${resource.resource_type}:${resource.resource_id}`} value={`${resource.resource_type}:${resource.resource_id}`}>{resource.name}</option>)}
            {placement.preset === "sensor" && <option value="sensor:">センサー計測</option>}
          </select>
        </label>
      )}
      {canBindDevice && placement.binding && selectableTargets.length > 0 && (
        <fieldset className="target-selector">
          <legend>{relationTargetLabel(placement.preset)}</legend>
          {selectableTargets.map((target) => (
            <label key={target.id}>
              <input type="checkbox" checked={targetIds.includes(target.id)} onChange={(event) => toggleTarget(target.id, event.target.checked)} />
              <span><strong>{target.name}</strong><small>{PRESET_BY_ID[target.preset].label} / {target.spaceId === space.id ? "この空間" : target.spaceName}</small></span>
            </label>
          ))}
        </fieldset>
      )}
      {selectedDevice && (
        <dl className="device-summary">
          <dt>状態</dt><dd><span className={`device-state ${selectedDevice.state}`}>{selectedDevice.state}</span></dd>
          <dt>ID</dt><dd><code>{selectedDevice.id}</code></dd>
          {selectedDevice.location && <><dt>登録場所</dt><dd>{selectedDevice.location}</dd></>}
        </dl>
      )}
      <label>メモ<textarea value={placement.memo} onChange={(event) => onChange({ memo: event.target.value })} /></label>
      {PLANTABLE_PRESETS.has(placement.preset) && (
        <section className="watering-source-section" aria-label="潅水方法">
          <div className="watering-source-heading"><Droplets size={17} /><strong>潅水方法</strong></div>
          <select value={wateringSourceIds[0] ?? ""} onChange={(event) => onWateringSourceChange(event.target.value)}>
            <option value="">手動潅水（ホース等）</option>
            {wateringSources.map((source) => <option key={source.id} value={source.id}>{source.name} / {source.deviceName} / {source.spaceId === space.id ? "この空間" : source.spaceName}</option>)}
          </select>
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
            <PlantTargetEditor planting={planting} busy={plantBusy} onSave={onUpdatePlanting} />
            <div className="planting-links">
              <button type="button" onClick={onOpenCalendar}><CalendarDays size={16} />カレンダーを開く</button>
              <a href={`${fieldDetailUrl}?planting=${encodeURIComponent(planting.id)}#cultivation`} title="栽培タブで定植情報を編集"><ExternalLink size={16} />作物情報を編集</a>
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

const PLANT_TARGET_SPECS = [
  { id: "soil_moisture_percent", label: "土壌水分", unit: "%", min: 0, max: 100, step: 1, defaults: [35, 65] },
  { id: "soil_ec_us_cm", label: "土壌EC", unit: "uS/cm", min: 0, max: 3000, step: 10, defaults: [500, 1500] },
  { id: "soil_ph", label: "土壌pH", unit: "", min: 0, max: 14, step: 0.1, defaults: [5.5, 6.5] },
  { id: "air_humidity_percent", label: "湿度", unit: "%", min: 0, max: 100, step: 1, defaults: [50, 75] },
  { id: "par_umol_m2_s", label: "PAR", unit: "umol/m2/s", min: 0, max: 2000, step: 10, defaults: [300, 1000] },
] as const;

type EditableGrowthTargets = Record<string, { min: number | null; max: number | null }>;

function PlantTargetEditor({
  planting,
  busy,
  onSave,
}: {
  planting: Planting;
  busy: boolean;
  onSave: (plantingId: string, payload: Partial<Planting>) => Promise<void>;
}) {
  const [targets, setTargets] = useState<EditableGrowthTargets>(() => structuredClone(planting.growth_targets ?? {}));
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setTargets(structuredClone(planting.growth_targets ?? {}));
    setSaved(false);
  }, [planting.id]);

  const setTarget = (metric: string, value: { min: number | null; max: number | null }) => {
    setSaved(false);
    setTargets((current) => ({ ...current, [metric]: value }));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    await onSave(planting.id, { growth_targets: targets });
    setSaved(true);
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
          <div className={`plant-target-row ${enabled ? "enabled" : ""}`} key={spec.id}>
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
      <button type="submit" disabled={busy}><Save size={14} />目標を保存</button>
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

  useEffect(() => {
    localStorage.setItem(draftKey, JSON.stringify(draft));
  }, [draft, draftKey]);

  const change = <Key extends keyof PlantingDraft>(key: Key, value: PlantingDraft[Key]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError("");
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
          soil_or_substrate: draft.soil,
          sunlight: draft.sunlight,
          notes: draft.notes,
        },
      });
      localStorage.removeItem(draftKey);
    } catch (caught) {
      setFormError(errorMessage(caught));
    }
  };

  return (
    <section className="plant-registration">
      <div className="section-title"><Leaf size={17} /><strong>この場所に定植</strong></div>
      <form onSubmit={(event) => void submit(event)}>
        <label>作物名<input required value={draft.cropName} onChange={(event) => change("cropName", event.target.value)} placeholder="例: ブルーベリー" /></label>
        <label>品種<input value={draft.cultivar} onChange={(event) => change("cultivar", event.target.value)} placeholder="例: オニール" /></label>
        <div className="field-grid two">
          <label>作物区分<select value={draft.cropCategory} onChange={(event) => change("cropCategory", event.target.value as Planting["crop_category"])}>{Object.entries(CROP_CATEGORY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          {draft.cropCategory === "fruit_tree" && <label>樹齢<input type="number" min="0" max="300" value={draft.treeAgeYears ?? ""} onChange={(event) => change("treeAgeYears", event.target.value === "" ? null : Number(event.target.value))} placeholder="年" /></label>}
        </div>
        <div className="field-grid two">
          <label>定植日<input required type="date" value={draft.plantedOn} onChange={(event) => change("plantedOn", event.target.value)} /></label>
          <label>株数<input required type="number" min="1" value={draft.plantCount} onChange={(event) => change("plantCount", Number(event.target.value))} /></label>
        </div>
        <label>栽培方式<select value={draft.cultivationMethod} onChange={(event) => change("cultivationMethod", event.target.value)}>{cultivationMethods.map((method) => <option key={method.value} value={method.value}>{method.label}</option>)}</select></label>
        <label>用土・培地<input value={draft.soil} onChange={(event) => change("soil", event.target.value)} placeholder="酸性用土、培養土など" /></label>
        <label>日当たり<input value={draft.sunlight} onChange={(event) => change("sunlight", event.target.value)} placeholder="日なた、半日陰など" /></label>
        <label>補足<textarea value={draft.notes} onChange={(event) => change("notes", event.target.value)} placeholder="購入時の状態、育苗条件など" /></label>
        <label className="ai-planning-notes"><span><Sparkles size={14} />AI計画へ伝えること</span><textarea value={draft.planningNotes} onChange={(event) => change("planningNotes", event.target.value)} placeholder="収穫を優先、農薬は使わない、週末だけ作業可能など" /></label>
        <p className="ai-call-notice">登録時にAIを1回呼び出し、目標レンジと12か月計画を生成します。AI未設定時は標準案を使用します。</p>
        {layoutDirty && <p className="form-notice">配置を保存すると定植を登録できます。</p>}
        {formError && <p className="form-error">{formError}</p>}
        <button type="submit" className="register-button" disabled={layoutDirty || busy || !draft.cropName.trim()}>
          <Sparkles size={16} />{busy ? "目標と計画を生成中..." : "定植を登録してAI計画を生成"}
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
  if (preset === "grow_light") return "補光する培地・空間（任意）";
  if (preset === "mister") return "噴霧する培地・空間（任意）";
  if (preset === "fan" || preset === "hvac") return "環境制御する空間（任意）";
  return "接続対象（任意）";
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
