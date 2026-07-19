import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, Beaker, Leaf, LoaderCircle, MessageCircle, Plus, RefreshCw, Search, Sparkles, Trash2, X } from "lucide-react";

import { DisabledActionReason, disabledActionTitle } from "../DisabledActionReason";
import { errorMessage, formatDate, todayString } from "../formatters";
import { SearchableSelect } from "../SearchableSelect";
import type {
  FertilizerApplication,
  FertilizerMaterialKind,
  PlantActionCompletionPayload,
  PlantActionSkipPayload,
  PlantBundle,
  PlantCalendar,
  PlantCalendarAction,
  PlantQuestionRecord,
} from "../types";
import { AnnualCalendarGantt } from "./AnnualCalendarGantt";
import { CalendarActionCard, CalendarKanbanCard, NewCalendarActionForm } from "./CalendarActionCard";
import { FALLBACK_ACTION_TYPES } from "./constants";

type KanbanColumn = "planned" | "in_progress" | "completed";
type ActionTimingState = PlantBundle["suggestions"][number]["timing_state"];

const KANBAN_COLUMNS: Array<{ id: KanbanColumn; label: string; description: string }> = [
  { id: "planned", label: "未完了", description: "着手を待っている作業" },
  { id: "in_progress", label: "作業中", description: "現在取り組んでいる作業" },
  { id: "completed", label: "完了・見送り", description: "実施済み、または確認して不要と判断した作業" },
];

const TIMING_SORT_ORDER: Record<ActionTimingState, number> = { overdue: 0, due: 1, upcoming: 2 };
const PRIORITY_SORT_ORDER: Record<PlantCalendarAction["priority"], number> = { required: 0, should: 1, recommended: 2, optional: 3 };


export interface PlantCalendarDrawerProps {
  bundle: PlantBundle;
  selectedPlantingId: string;
  busy: boolean;
  initialActionId?: string;
  presentation?: "modal" | "page";
  fieldName?: string;
  fieldDetailUrl?: string;
  onPlantingChange: (plantingId: string) => void;
  onClose: () => void;
  onEditAction: (plantingId: string, actionId: string, payload: Partial<PlantCalendarAction> & { use_as_guidance?: boolean }) => Promise<void>;
  onCompleteAction: (plantingId: string, actionId: string, payload: PlantActionCompletionPayload) => Promise<void>;
  onSkipAction: (plantingId: string, actionId: string, payload: PlantActionSkipPayload) => Promise<void>;
  onAskQuestion: (plantingId: string, question: string) => Promise<PlantQuestionRecord>;
  onRegenerate: (plantingId: string, startDate: string, planningNotes: string) => Promise<void>;
  onAddAction: (plantingId: string, payload: Partial<PlantCalendarAction>) => Promise<void>;
  onDeleteAction: (plantingId: string, actionId: string) => Promise<void>;
  onAddFertilizer: (plantingId: string, payload: Record<string, unknown>) => Promise<void>;
  onDeleteFertilizer: (plantingId: string, applicationId: string) => Promise<void>;
  onSearchActions: (plantingId: string, query: string, page: number, signal: AbortSignal) => Promise<ActionSearchPage>;
}

interface ActionSearchPage {
  items: PlantCalendarAction[];
  total: number;
  page: number;
  page_count: number;
  has_previous: boolean;
  has_next: boolean;
}

export function PlantCalendarDrawer({
  bundle,
  selectedPlantingId,
  busy,
  initialActionId = "",
  presentation = "modal",
  fieldName = "",
  fieldDetailUrl = "/fields",
  onPlantingChange,
  onClose,
  onEditAction,
  onCompleteAction,
  onSkipAction,
  onAskQuestion,
  onRegenerate,
  onAddAction,
  onDeleteAction,
  onAddFertilizer,
  onDeleteFertilizer,
  onSearchActions,
}: PlantCalendarDrawerProps) {
  const activePlantings = bundle.plantings.filter((planting) => planting.status === "active");
  const planting = activePlantings.find((item) => item.id === selectedPlantingId) ?? activePlantings[0] ?? null;
  const calendar = planting ? bundle.calendars[planting.id] : null;
  const generationTask = planting ? bundle.generation_tasks.find((task) => task.planting_id === planting.id) ?? null : null;
  const generationActive = generationTask?.status === "queued" || generationTask?.status === "running";
  const calendarMutationBusy = busy || generationActive;
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [questionError, setQuestionError] = useState("");
  const [generationOpen, setGenerationOpen] = useState(false);
  const [generationStart, setGenerationStart] = useState(todayString());
  const [generationNotes, setGenerationNotes] = useState("");
  const [generationError, setGenerationError] = useState("");
  const [addingAction, setAddingAction] = useState(false);
  const [selectedActionId, setSelectedActionId] = useState<string | null>(null);
  const [recordActionId, setRecordActionId] = useState<string | null>(null);
  const [actionQuery, setActionQuery] = useState("");
  const [actionSearchPage, setActionSearchPage] = useState(1);
  const [actionSearchResult, setActionSearchResult] = useState<ActionSearchPage | null>(null);
  const [actionSearchLoading, setActionSearchLoading] = useState(false);
  const [actionSearchError, setActionSearchError] = useState("");
  const [draggedActionId, setDraggedActionId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<KanbanColumn | null>(null);
  const [dropMessage, setDropMessage] = useState("");
  const consumedInitialActionId = useRef("");
  const actionSearchCache = useRef(new Map<string, ActionSearchPage>());
  const regenerationBlockingReasons = [
    ...(!generationStart ? ["計画開始日を選択してください"] : []),
    ...(generationActive ? ["AI計画を作成中です"] : []),
    ...(busy ? ["現在のAI処理が完了するまでお待ちください"] : []),
  ];
  const questionBlockingReasons = [
    ...(!question.trim() ? ["質問を入力してください"] : []),
    ...(busy ? ["現在のAI処理が完了するまでお待ちください"] : []),
  ];

  useEffect(() => {
    if (planting && planting.id !== selectedPlantingId) onPlantingChange(planting.id);
  }, [planting, selectedPlantingId, onPlantingChange]);

  useEffect(() => {
    setAnswer("");
    setQuestionError("");
    setGenerationOpen(false);
    const planning = calendarPlanningContext(calendar);
    setGenerationStart(typeof planning.start_date === "string" ? planning.start_date : todayString());
    setGenerationNotes(typeof planning.notes === "string" ? planning.notes : "");
  }, [planting?.id, calendar?.updated_at]);

  useEffect(() => {
    setSelectedActionId(null);
    setRecordActionId(null);
    setActionQuery("");
    setActionSearchPage(1);
    setActionSearchResult(null);
  }, [planting?.id]);

  const actions = useMemo(
    () => [...(calendar?.actions ?? [])].sort((left, right) => left.window_start.localeCompare(right.window_start)),
    [calendar?.actions],
  );
  const actionTypes = bundle.action_types?.length ? bundle.action_types : FALLBACK_ACTION_TYPES;
  const actionTypeByCode = useMemo(() => new Map(actionTypes.map((item) => [item.code, item])), [actionTypes]);
  const filteredActions = actionQuery.trim() ? actionSearchResult?.items ?? [] : actions;
  const suggestions = useMemo(
    () => bundle.suggestions.filter((suggestion) => suggestion.planting_id === planting?.id),
    [bundle.suggestions, planting?.id],
  );
  const fertilizerApplications = useMemo(
    () => bundle.fertilizer_applications.filter((application) => application.placement_id === planting?.placement_id),
    [bundle.fertilizer_applications, planting?.placement_id],
  );
  const suggestionByActionId = useMemo(
    () => new Map(suggestions.map((suggestion) => [suggestion.action.id, suggestion.timing_state])),
    [suggestions],
  );
  const actionsByColumn = useMemo(
    () => new Map(KANBAN_COLUMNS.map((column) => [column.id, sortKanbanActions(filteredActions, column.id, suggestionByActionId)])),
    [filteredActions, suggestionByActionId],
  );
  const selectedAction = filteredActions.find((action) => action.id === selectedActionId)
    ?? actions.find((action) => action.id === selectedActionId)
    ?? null;

  useEffect(() => {
    actionSearchCache.current.clear();
  }, [calendar?.revision]);

  useEffect(() => {
    const query = actionQuery.trim();
    if (!query || !planting) {
      setActionSearchResult(null);
      setActionSearchLoading(false);
      setActionSearchError("");
      return undefined;
    }
    const cacheKey = `${planting.id}:${calendar?.revision ?? 0}:${actionSearchPage}:${query}`;
    const cached = actionSearchCache.current.get(cacheKey);
    if (cached) {
      setActionSearchResult(cached);
      setActionSearchLoading(false);
      setActionSearchError("");
      return undefined;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setActionSearchLoading(true);
      setActionSearchError("");
      void onSearchActions(planting.id, query, actionSearchPage, controller.signal)
        .then((result) => {
          actionSearchCache.current.set(cacheKey, result);
          setActionSearchResult(result);
        })
        .catch((caught) => {
          if (caught instanceof DOMException && caught.name === "AbortError") return;
          setActionSearchError(errorMessage(caught));
        })
        .finally(() => {
          if (!controller.signal.aborted) setActionSearchLoading(false);
        });
    }, 350);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [actionQuery, actionSearchPage, calendar?.revision, onSearchActions, planting]);

  const openActionFromGantt = (action: PlantCalendarAction) => {
    setRecordActionId(null);
    setSelectedActionId(action.id);
  };

  const closeAction = () => {
    setSelectedActionId(null);
    setRecordActionId(null);
  };

  useEffect(() => {
    if (
      initialActionId
      && initialActionId !== consumedInitialActionId.current
      && actions.some((action) => action.id === initialActionId)
    ) {
      consumedInitialActionId.current = initialActionId;
      setSelectedActionId(initialActionId);
    }
  }, [actions, initialActionId]);

  const moveAction = async (destination: KanbanColumn) => {
    const action = filteredActions.find((item) => item.id === draggedActionId)
      ?? actions.find((item) => item.id === draggedActionId);
    setDragOverColumn(null);
    setDraggedActionId(null);
    if (!action || !planting || calendarMutationBusy || !canDropAction(action, destination)) return;
    try {
      if (destination === "completed") {
        if (action.status === "planned") {
          await onEditAction(planting.id, action.id, { status: "in_progress", use_as_guidance: false });
        }
        setSelectedActionId(action.id);
        setRecordActionId(action.id);
        setDropMessage(`${action.title}の実績入力を開きました。保存すると完了になります。`);
        return;
      }
      const status = destination === "planned" ? "planned" : "in_progress";
      await onEditAction(planting.id, action.id, { status, use_as_guidance: false });
      setDropMessage(`${action.title}を${destination === "planned" ? "未完了" : "作業中"}へ移動しました。`);
    } catch (caught) {
      setDropMessage(errorMessage(caught));
    }
  };

  const regenerate = async (event: FormEvent) => {
    event.preventDefault();
    if (!planting) return;
    setGenerationError("");
    try {
      await onRegenerate(planting.id, generationStart, generationNotes);
      setGenerationOpen(false);
    } catch (caught) {
      setGenerationError(errorMessage(caught));
    }
  };

  const ask = async (event: FormEvent) => {
    event.preventDefault();
    if (!planting || !question.trim()) return;
    setQuestionError("");
    try {
      const record = await onAskQuestion(planting.id, question.trim());
      setAnswer(record.answer);
    } catch (caught) {
      setQuestionError(errorMessage(caught));
    }
  };

  const panel = (
      <aside className={`calendar-drawer ${presentation === "page" ? "calendar-page-panel" : "calendar-modal-panel"}`} role={presentation === "modal" ? "dialog" : undefined} aria-modal={presentation === "modal" ? "true" : undefined} aria-label="栽培カレンダー">
        <header className="calendar-header">
          <div className="calendar-header-identity">
            {presentation === "page" && <a className="icon-link" href={fieldDetailUrl} title={`${fieldName || "圃場"}へ戻る`}><ArrowLeft size={19} /></a>}
            <div><span>{fieldName || "栽培支援"}</span><h2>{presentation === "page" ? "年間栽培カレンダー" : "生成した栽培カレンダー"}</h2></div>
          </div>
          {presentation === "modal" && <button type="button" className="icon-button" onClick={onClose} title="閉じる"><X size={19} /></button>}
        </header>

        {activePlantings.length === 0 ? (
          <CalendarEmptyState />
        ) : planting && (
          <>
            <section className="calendar-plant-selector">
              <div className="filterable-field">
                <span className="field-label">管理する作物</span>
                <SearchableSelect
                  ariaLabel="管理する作物"
                  value={planting.id}
                  onChange={onPlantingChange}
                  searchPlaceholder="作物、品種、設置場所を検索"
                  emptyMessage="一致する栽培はありません。"
                  options={activePlantings.map((item) => ({
                    value: item.id,
                    label: `${item.placement_name} / ${item.crop_name}${item.cultivar ? ` (${item.cultivar})` : ""}`,
                    searchText: `${item.crop_name} ${item.cultivar} ${item.placement_name}`,
                  }))}
                />
              </div>
              <div className="plant-context">
                <span><Leaf size={15} />{planting.crop_name}</span>
                <span>{planting.placement_name}</span>
                <span>{formatDate(planting.planted_on)} 定植</span>
              </div>
            </section>

            <SuggestionSummary suggestions={suggestions} />
            <FertilizerEffectPanel
              plantingId={planting.id}
              placementName={planting.placement_name}
              applications={fertilizerApplications}
              busy={calendarMutationBusy}
              onAdd={onAddFertilizer}
              onDelete={onDeleteFertilizer}
            />
            {calendar && <CareProfileSummary calendar={calendar} />}
            {calendar && <AnnualCalendarGantt actions={actions} onActionSelect={openActionFromGantt} />}

            <section className="calendar-generation" aria-label="計画の生成設定">
              <div className="calendar-section-heading">
                <div><Sparkles size={17} /><strong>AI計画</strong></div>
                <button type="button" disabled={generationActive} onClick={() => setGenerationOpen((value) => !value)}>
                  {generationActive ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}
                  {generationActive ? "AI計画を作成中..." : calendar ? "条件を編集して再生成" : "条件を編集して作成"}
                </button>
              </div>
              {generationActive && (
                <div className="generation-status active" role="status" aria-live="polite">
                  <LoaderCircle className="spin" size={18} />
                  <div><strong>{generationTask.status === "queued" ? "AI計画の作成を待っています" : "AI計画を作成しています"}</strong><p>この画面を離れても処理は続きます。他の作業を進めてかまいません。</p></div>
                </div>
              )}
              {generationTask?.status === "failed" && (
                <div className="generation-status failed" role="alert">
                  <div><strong>AI計画を作成できませんでした</strong><p>{generationTask.error || "時間をおいてもう一度お試しください。"}</p></div>
                </div>
              )}
              {generationOpen && (
                <form onSubmit={(event) => void regenerate(event)}>
                  <label>計画開始日<input type="date" required value={generationStart} onChange={(event) => setGenerationStart(event.target.value)} /></label>
                  <label>今回の生成条件<textarea value={generationNotes} onChange={(event) => setGenerationNotes(event.target.value)} placeholder="今年は収穫を優先、農薬を使わない、現在は開花直前など" /></label>
                  <p>計画済みの将来作業を置き換えます。実施済みの記録は保持します。AI呼び出しが1回発生します。</p>
                  <DisabledActionReason id="calendar-regeneration-blocked" reasons={regenerationBlockingReasons} prefix="再生成するには" />
                  {generationError && <p className="form-error">{generationError}</p>}
                  <div className="form-actions">
                    <button type="button" onClick={() => setGenerationOpen(false)}>キャンセル</button>
                    <button type="submit" disabled={regenerationBlockingReasons.length > 0} aria-describedby={regenerationBlockingReasons.length > 0 ? "calendar-regeneration-blocked" : undefined} title={disabledActionTitle(regenerationBlockingReasons)}><Sparkles size={15} />12か月計画を{calendar ? "再生成" : "作成"}</button>
                  </div>
                </form>
              )}
            </section>

            {calendar && <section className="calendar-action-list" aria-label="管理作業">
              <div className="calendar-section-heading">
                <div><strong>管理作業</strong><span>{actions.length}件を状態別に管理</span></div>
                <div>
                  {calendar && <small>r{calendar.revision} / {calendar.generation.source === "llm" ? "AI生成" : "標準提案"}</small>}
                  {!addingAction && <button type="button" onClick={() => setAddingAction(true)} disabled={calendarMutationBusy} title={calendarMutationBusy ? "AI計画の作成または現在の操作が完了するまでお待ちください" : "管理作業を追加"}><Plus size={15} />作業を追加</button>}
                </div>
              </div>
              {addingAction && (
                <NewCalendarActionForm
                  actionTypes={actionTypes}
                  busy={calendarMutationBusy}
                  onCancel={() => setAddingAction(false)}
                  onSave={async (payload) => {
                    await onAddAction(planting.id, payload);
                    setAddingAction(false);
                  }}
                />
              )}
              <div className="calendar-kanban-toolbar">
                <label><Search size={16} /><input type="search" value={actionQuery} onChange={(event) => { setActionQuery(event.target.value); setActionSearchPage(1); }} placeholder="作業名、種別、資材、タグで検索" aria-label="管理作業を検索" />{actionQuery && <button type="button" onClick={() => { setActionQuery(""); setActionSearchPage(1); }} title="作業検索をクリア"><X size={14} /></button>}</label>
                <output>{actionSearchLoading ? "検索中..." : actionQuery.trim() ? `${filteredActions.length} / ${actionSearchResult?.total ?? 0}件` : `${actions.length}件`}</output>
              </div>
              {actionSearchError && <p className="calendar-search-error" role="alert">{actionSearchError}</p>}
              {actionQuery.trim() && actionSearchResult && actionSearchResult.page_count > 1 && (
                <nav className="calendar-search-pagination" aria-label="作業検索結果ページ">
                  <button type="button" disabled={!actionSearchResult.has_previous || actionSearchLoading} onClick={() => setActionSearchPage((page) => Math.max(1, page - 1))}>前へ</button>
                  <span>{actionSearchResult.page} / {actionSearchResult.page_count}</span>
                  <button type="button" disabled={!actionSearchResult.has_next || actionSearchLoading} onClick={() => setActionSearchPage((page) => page + 1)}>次へ</button>
                </nav>
              )}
              <p className="kanban-dnd-help">カードを列へドラッグして状態を変更できます。完了列への移動では実績入力が開きます。</p>
              <p className="kanban-drop-status" role="status" aria-live="polite">{dropMessage}</p>
              <div className="calendar-kanban-scroll">
                <div className="calendar-kanban" aria-label="管理作業カンバン">
                  {KANBAN_COLUMNS.map((column) => {
                    const columnActions = actionsByColumn.get(column.id) ?? [];
                    return (
                      <section
                        key={column.id}
                        className={`calendar-kanban-column ${column.id}${dragOverColumn === column.id ? " drag-over" : ""}`}
                        data-kanban-status={column.id}
                        aria-labelledby={`kanban-column-${planting.id}-${column.id}`}
                        onDragOver={(event) => {
                          const action = filteredActions.find((item) => item.id === draggedActionId)
                            ?? actions.find((item) => item.id === draggedActionId);
                          if (!action || calendarMutationBusy || !canDropAction(action, column.id)) return;
                          event.preventDefault();
                          event.dataTransfer.dropEffect = "move";
                          setDragOverColumn(column.id);
                        }}
                        onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragOverColumn(null); }}
                        onDrop={(event) => { event.preventDefault(); void moveAction(column.id); }}
                      >
                        <header>
                          <div><span className="kanban-column-marker" /><h3 id={`kanban-column-${planting.id}-${column.id}`}>{column.label}</h3><strong>{columnActions.length}</strong></div>
                          <p>{column.description}</p>
                          <small>{formatPersonHours(columnActions)}人時</small>
                        </header>
                        <div className="calendar-kanban-cards">
                          {columnActions.map((action) => (
                            <CalendarKanbanCard
                              key={action.id}
                              action={action}
                              actionType={actionTypeByCode.get(action.action_type) ?? actionTypeByCode.get("other") ?? FALLBACK_ACTION_TYPES[FALLBACK_ACTION_TYPES.length - 1]}
                              timingState={suggestionByActionId.get(action.id)}
                              onOpen={() => { setRecordActionId(null); setSelectedActionId(action.id); }}
                              draggable={!calendarMutationBusy && action.status !== "completed"}
                              onDragStart={(event) => {
                                setDraggedActionId(action.id);
                                setDropMessage("");
                                event.dataTransfer.effectAllowed = "move";
                                event.dataTransfer.setData("text/plain", action.id);
                              }}
                              onDragEnd={() => { setDraggedActionId(null); setDragOverColumn(null); }}
                            />
                          ))}
                          {columnActions.length === 0 && <KanbanEmptyState column={column.id} />}
                        </div>
                      </section>
                    );
                  })}
                </div>
              </div>
            </section>}

            <section className="plant-question">
              <div className="calendar-section-heading"><div><MessageCircle size={17} /><strong>この作物について質問</strong></div></div>
              <form onSubmit={(event) => void ask(event)}>
                <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="追肥は今必要ですか？ 葉の斑点は何を確認すべきですか？" />
                <button type="submit" disabled={questionBlockingReasons.length > 0} aria-describedby={questionBlockingReasons.length > 0 ? "plant-question-blocked" : undefined} title={disabledActionTitle(questionBlockingReasons)}><MessageCircle size={16} />質問する</button>
              </form>
              <DisabledActionReason id="plant-question-blocked" reasons={questionBlockingReasons} prefix="質問するには" />
              {questionError && <p className="form-error">{questionError}</p>}
              {answer && <div className="question-answer"><strong>回答</strong><p>{answer}</p></div>}
              <p className="safety-note">農薬を使う場合は、対象作物への登録、ラベル、希釈倍率、収穫前日数と地域の指針を必ず確認してください。</p>
            </section>

            {selectedAction && (
              <div className="calendar-action-detail-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeAction(); }}>
                <section className="calendar-action-detail-dialog" role="dialog" aria-modal="true" aria-labelledby={`calendar-action-detail-title-${selectedAction.id}`}>
                  <header>
                    <div><span>管理作業の詳細</span><h2 id={`calendar-action-detail-title-${selectedAction.id}`}>{selectedAction.title}</h2></div>
                    <button type="button" className="icon-button" onClick={closeAction} title="閉じる"><X size={19} /></button>
                  </header>
                  <div className="calendar-action-detail-body">
                    <CalendarActionCard
                      plantingId={planting.id}
                      action={selectedAction}
                      actionType={actionTypeByCode.get(selectedAction.action_type) ?? actionTypeByCode.get("other") ?? FALLBACK_ACTION_TYPES[FALLBACK_ACTION_TYPES.length - 1]}
                      actionTypes={actionTypes}
                      timingState={suggestionByActionId.get(selectedAction.id)}
                      busy={calendarMutationBusy}
                      initialRecording={recordActionId === selectedAction.id}
                      onEdit={onEditAction}
                      onComplete={onCompleteAction}
                      onSkip={onSkipAction}
                      onDelete={async (...args) => {
                        await onDeleteAction(...args);
                        closeAction();
                      }}
                    />
                  </div>
                </section>
              </div>
            )}
          </>
        )}
      </aside>
  );
  if (presentation === "page") return <main className="calendar-page-shell">{panel}</main>;
  return <div className="calendar-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>{panel}</div>;
}

function sortKanbanActions(
  actions: PlantCalendarAction[],
  column: KanbanColumn,
  timingByActionId: Map<string, ActionTimingState>,
) {
  return actions
    .filter((action) => actionKanbanColumn(action) === column)
    .sort((left, right) => compareManagementActions(left, right, timingByActionId));
}

function actionKanbanColumn(action: PlantCalendarAction): KanbanColumn {
  if (action.status === "planned") return "planned";
  if (action.status === "in_progress") return "in_progress";
  return "completed";
}

function canDropAction(action: PlantCalendarAction, destination: KanbanColumn): boolean {
  if (destination === "planned") return action.status === "in_progress" || action.status === "skipped";
  if (destination === "in_progress") return action.status === "planned";
  return action.status === "planned" || action.status === "in_progress";
}

function compareManagementActions(
  left: PlantCalendarAction,
  right: PlantCalendarAction,
  timingByActionId: Map<string, ActionTimingState>,
) {
  const statusOrder = { planned: 0, in_progress: 1, completed: 2, skipped: 3 };
  const statusDifference = statusOrder[left.status] - statusOrder[right.status];
  if (statusDifference !== 0) return statusDifference;

  if ((left.status === "planned" || left.status === "in_progress") && left.status === right.status) {
    const leftTiming = timingByActionId.get(left.id);
    const rightTiming = timingByActionId.get(right.id);
    const timingDifference = (leftTiming ? TIMING_SORT_ORDER[leftTiming] : 3) - (rightTiming ? TIMING_SORT_ORDER[rightTiming] : 3);
    if (timingDifference !== 0) return timingDifference;
    const priorityDifference = PRIORITY_SORT_ORDER[left.priority] - PRIORITY_SORT_ORDER[right.priority];
    if (priorityDifference !== 0) return priorityDifference;
    return left.window_start.localeCompare(right.window_start) || left.window_end.localeCompare(right.window_end);
  }

  const leftDate = left.completion?.performed_on || left.skip_decision?.decided_on || left.window_end;
  const rightDate = right.completion?.performed_on || right.skip_decision?.decided_on || right.window_end;
  return rightDate.localeCompare(leftDate) || right.window_end.localeCompare(left.window_end);
}

function formatPersonHours(actions: PlantCalendarAction[]): string {
  const totalMinutes = actions.reduce((total, action) => total + action.required_people * action.estimated_minutes, 0);
  const hours = totalMinutes / 60;
  return Number.isInteger(hours) ? String(hours) : hours.toFixed(1);
}

function KanbanEmptyState({ column }: { column: KanbanColumn }) {
  const message = column === "planned"
    ? "着手待ちの作業はありません。"
    : column === "in_progress"
      ? "作業中の項目はありません。"
      : "完了した作業はありません。";
  return <p className="calendar-kanban-empty">{message}</p>;
}

function CalendarEmptyState() {
  return (
    <div className="calendar-empty">
      <Leaf size={32} />
      <strong>定植情報がありません</strong>
      <p>設置ビューで鉢や畝を選び、作物を登録するとカレンダーが作成されます。</p>
    </div>
  );
}

function SuggestionSummary({ suggestions }: { suggestions: PlantBundle["suggestions"] }) {
  const count = (state: PlantBundle["suggestions"][number]["timing_state"]) => suggestions.filter((item) => item.timing_state === state).length;
  return (
    <section className="suggestion-summary" aria-label="現在の提案">
      <span><strong>{count("overdue")}</strong>期限超過</span>
      <span><strong>{count("due")}</strong>今やる</span>
      <span><strong>{count("upcoming")}</strong>まもなく</span>
    </section>
  );
}

const FERTILIZER_KIND_OPTIONS: Array<{ value: FertilizerMaterialKind; label: string }> = [
  { value: "cattle_manure", label: "牛ふん堆肥" },
  { value: "poultry_manure", label: "鶏ふん・鶏ふん堆肥" },
  { value: "compost", label: "植物性堆肥・その他堆肥" },
  { value: "organic_fertilizer", label: "有機質肥料" },
  { value: "chemical_fertilizer", label: "化成・無機質肥料" },
  { value: "custom", label: "その他・独自資材" },
];

interface FertilizerDraft {
  appliedOn: string;
  materialKind: FertilizerMaterialKind;
  materialName: string;
  amountKg: string;
  nPercent: string;
  pPercent: string;
  kPercent: string;
  annualAvailablePercent: string;
  effectYears: string;
  startDelayDays: string;
  analysisSource: string;
  notes: string;
}

function newFertilizerDraft(): FertilizerDraft {
  return {
    appliedOn: todayString(),
    materialKind: "cattle_manure",
    materialName: "牛ふん堆肥",
    amountKg: "",
    nPercent: "",
    pPercent: "",
    kPercent: "",
    annualAvailablePercent: "10",
    effectYears: "1",
    startDelayDays: "0",
    analysisSource: "",
    notes: "",
  };
}

function FertilizerEffectPanel({
  plantingId,
  placementName,
  applications,
  busy,
  onAdd,
  onDelete,
}: {
  plantingId: string;
  placementName: string;
  applications: FertilizerApplication[];
  busy: boolean;
  onAdd: (plantingId: string, payload: Record<string, unknown>) => Promise<void>;
  onDelete: (plantingId: string, applicationId: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<FertilizerDraft>(newFertilizerDraft);
  const [error, setError] = useState("");
  const estimate = useMemo(() => summarizeFertilizerApplications(applications), [applications]);
  const change = <Key extends keyof FertilizerDraft>(key: Key, value: FertilizerDraft[Key]) => (
    setDraft((current) => ({ ...current, [key]: value }))
  );

  const selectKind = (kind: FertilizerMaterialKind) => {
    const option = FERTILIZER_KIND_OPTIONS.find((item) => item.value === kind);
    setDraft((current) => ({
      ...current,
      materialKind: kind,
      materialName: kind === "custom" ? "" : option?.label ?? current.materialName,
      annualAvailablePercent: kind === "cattle_manure" ? "10" : "",
    }));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const nutrientValues = [draft.nPercent, draft.pPercent, draft.kPercent].map(Number);
    if (!nutrientValues.some((value) => value > 0)) {
      setError("製品表示や分析表から、N・P₂O₅・K₂Oのいずれかを入力してください。");
      return;
    }
    try {
      await onAdd(plantingId, {
        applied_on: draft.appliedOn,
        material_kind: draft.materialKind,
        material_name: draft.materialName,
        amount_kg: Number(draft.amountKg),
        nutrient_percent: { n: nutrientValues[0], p2o5: nutrientValues[1], k2o: nutrientValues[2] },
        annual_available_percent: Number(draft.annualAvailablePercent),
        effect_years: Number(draft.effectYears),
        start_delay_days: Number(draft.startDelayDays),
        analysis_source: draft.analysisSource,
        notes: draft.notes,
      });
      setDraft(newFertilizerDraft());
      setEditing(false);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  return (
    <section className="fertilizer-effect-panel" aria-label="培地の施肥履歴と肥効見込み">
      <div className="calendar-section-heading">
        <div><Beaker size={17} /><strong>培地の施肥と残存肥効</strong><span>{placementName}</span></div>
        {!editing && <button type="button" disabled={busy} onClick={() => setEditing(true)}><Plus size={15} />施肥履歴を追加</button>}
      </div>
      {applications.length === 0 ? (
        <p className="fertilizer-empty">この培地の施肥履歴は未登録です。元肥や堆肥を登録すると、AI計画が残存肥効を考慮します。</p>
      ) : (
        <>
          <div className="fertilizer-balance" aria-label="推定残存養分">
            {(["n", "p2o5", "k2o"] as const).map((key) => (
              <div key={key}><span>{key === "n" ? "N" : key === "p2o5" ? "P₂O₅" : "K₂O"}</span><strong>{formatNutrientKg(estimate[key].remaining)}</strong><small>期間内の残存見込み</small></div>
            ))}
          </div>
          <div className="fertilizer-history-list">
            {[...applications].sort((left, right) => right.applied_on.localeCompare(left.applied_on)).map((application) => {
              const effect = fertilizerApplicationEstimate(application);
              return (
                <article key={application.id}>
                  <div><strong>{application.material_name}</strong><span>{formatDate(application.applied_on)} / {application.amount_kg.toLocaleString("ja-JP", { maximumFractionDigits: 3 })} kg</span></div>
                  <div className="fertilizer-effect-window"><span style={{ width: `${effect.progressPercent}%` }} /><small>{formatDate(effect.start)}〜{formatDate(effect.end)} / 年間肥効率 {application.annual_available_percent}%</small></div>
                  <button
                    type="button"
                    disabled={busy}
                    title="この施肥履歴を削除"
                    onClick={() => { if (window.confirm(`${application.material_name}の施肥履歴を削除しますか？`)) void onDelete(plantingId, application.id); }}
                  ><Trash2 size={14} />削除</button>
                </article>
              );
            })}
          </div>
        </>
      )}
      <p className="fertilizer-caution">概算値です。製品分析値・地域の施肥基準・土壌分析・EC・葉色・樹勢・収穫品質を優先し、残効が不明なまま追加施肥しないでください。</p>
      {applications.length > 0 && <p className="fertilizer-regenerate-note">施肥履歴を追加・削除した後は「条件を編集して再生成」すると、12か月計画へ反映されます。</p>}
      {editing && (
        <form className="fertilizer-entry-form" data-fertilizer-form onSubmit={(event) => void submit(event)}>
          <div className="fertilizer-form-intro"><strong>実際に入れた肥料を記録</strong><span>製品kgと養分kgを分けて計算します。</span></div>
          <div className="fertilizer-form-grid three">
            <label>施肥日<input name="applied_on" type="date" required max={todayString()} value={draft.appliedOn} onChange={(event) => change("appliedOn", event.target.value)} /></label>
            <label>資材の種類<select name="material_kind" value={draft.materialKind} onChange={(event) => selectKind(event.target.value as FertilizerMaterialKind)}>{FERTILIZER_KIND_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
            <label>投入量（kg）<input name="amount_kg" type="number" required min="0.001" max="1000000" step="0.001" value={draft.amountKg} onChange={(event) => change("amountKg", event.target.value)} /></label>
          </div>
          <label>資材・製品名<input name="material_name" required maxLength={180} value={draft.materialName} onChange={(event) => change("materialName", event.target.value)} placeholder="袋や分析表に記載された名称" /></label>
          <fieldset><legend>保証・分析成分（製品重量に対する%）</legend><div className="fertilizer-form-grid three">
            <label>N<input name="n_percent" type="number" min="0" max="100" step="0.01" value={draft.nPercent} onChange={(event) => change("nPercent", event.target.value)} /></label>
            <label>P₂O₅<input name="p2o5_percent" type="number" min="0" max="100" step="0.01" value={draft.pPercent} onChange={(event) => change("pPercent", event.target.value)} /></label>
            <label>K₂O<input name="k2o_percent" type="number" min="0" max="100" step="0.01" value={draft.kPercent} onChange={(event) => change("kPercent", event.target.value)} /></label>
          </div></fieldset>
          <fieldset><legend>肥効の見積条件</legend><div className="fertilizer-form-grid three">
            <label>年間肥効率（%）<input name="annual_available_percent" type="number" required min="0.1" max="100" step="0.1" value={draft.annualAvailablePercent} onChange={(event) => change("annualAvailablePercent", event.target.value)} /><small>牛ふんの10%は編集可能な開始値です。</small></label>
            <label>肥効を見込む年数<input name="effect_years" type="number" required min="1" max="10" step="1" value={draft.effectYears} onChange={(event) => change("effectYears", event.target.value)} /></label>
            <label>効き始めるまで（日）<input name="start_delay_days" type="number" required min="0" max="3650" step="1" value={draft.startDelayDays} onChange={(event) => change("startDelayDays", event.target.value)} /></label>
          </div></fieldset>
          <label>成分・肥効率の根拠<input maxLength={500} value={draft.analysisSource} onChange={(event) => change("analysisSource", event.target.value)} placeholder="製品ラベル、分析表、地域施肥基準など" /></label>
          <label>メモ<textarea maxLength={1000} value={draft.notes} onChange={(event) => change("notes", event.target.value)} placeholder="全面施用、畝内混和、施用範囲など" /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="form-actions"><button type="button" onClick={() => { setEditing(false); setError(""); }}>キャンセル</button><button type="submit" disabled={busy}>履歴と肥効を保存</button></div>
        </form>
      )}
    </section>
  );
}

function fertilizerApplicationEstimate(application: FertilizerApplication) {
  const applied = new Date(`${application.applied_on}T00:00:00`);
  const startDate = new Date(applied);
  startDate.setDate(startDate.getDate() + application.start_delay_days);
  const endDate = new Date(startDate);
  endDate.setDate(endDate.getDate() + application.effect_years * 365);
  const totalDuration = Math.max(1, endDate.getTime() - startDate.getTime());
  const progress = Math.max(0, Math.min(1, (Date.now() - startDate.getTime()) / totalDuration));
  const effectiveFraction = Math.min(1, application.annual_available_percent / 100 * application.effect_years);
  const nutrients = Object.fromEntries((["n", "p2o5", "k2o"] as const).map((key) => {
    const total = application.amount_kg * application.nutrient_percent[key] / 100 * effectiveFraction;
    return [key, { total, remaining: total * (1 - progress) }];
  })) as Record<"n" | "p2o5" | "k2o", { total: number; remaining: number }>;
  return { start: dateString(startDate), end: dateString(endDate), progressPercent: Math.round(progress * 100), nutrients };
}

function summarizeFertilizerApplications(applications: FertilizerApplication[]) {
  const result = { n: { remaining: 0 }, p2o5: { remaining: 0 }, k2o: { remaining: 0 } };
  applications.forEach((application) => {
    const estimate = fertilizerApplicationEstimate(application);
    (["n", "p2o5", "k2o"] as const).forEach((key) => { result[key].remaining += estimate.nutrients[key].remaining; });
  });
  return result;
}

function dateString(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function formatNutrientKg(value: number) {
  if (value >= 1) return `${value.toFixed(2)} kg`;
  return `${Math.round(value * 1000)} g`;
}

function CareProfileSummary({ calendar }: { calendar: PlantCalendar }) {
  const profile = calendar.care_profile;
  const rules = calendar.task_rules ?? [];
  if (!profile && rules.length === 0) return null;

  return (
    <details className="care-profile-summary">
      <summary><span><Leaf size={17} /><strong>栽培基準</strong></span><small>{rules.length}規則</small></summary>
      <div className="care-profile-body">
        {profile?.summary && <p>{profile.summary}</p>}
        <dl>
          <div><dt>潅水</dt><dd>{profile?.irrigation?.strategy || "条件未設定"}<small>{formatInterval(profile?.irrigation?.baseline_interval_days)}</small></dd></div>
          <div><dt>施肥</dt><dd>{profile?.fertilization?.strategy || "条件未設定"}</dd></div>
          <div><dt>EC</dt><dd>{profile?.fertilization?.ec_management || "条件未設定"}</dd></div>
          <div><dt>pH</dt><dd>{profile?.fertilization?.ph_management || "条件未設定"}</dd></div>
        </dl>
        {rules.length > 0 && (
          <div className="care-rule-list">
            {rules.filter((rule) => rule.recurrence_type !== "one_time").slice(0, 8).map((rule) => (
              <div key={rule.rule_id}>
                <strong>{rule.title}</strong>
                <span>{formatInterval(rule.interval_days)}{rule.anchor === "completion_date" ? " / 実施日起点" : ""}</span>
              </div>
            ))}
          </div>
        )}
        {profile?.assumptions?.length > 0 && <p className="care-assumptions">前提: {profile.assumptions.join(" / ")}</p>}
      </div>
    </details>
  );
}

function formatInterval(interval?: { min: number | null; preferred: number | null; max: number | null }) {
  if (!interval) return "条件で判断";
  if (interval.preferred) return `標準 ${interval.preferred}日`;
  if (interval.min || interval.max) return `${interval.min ?? "?"}〜${interval.max ?? "?"}日`;
  return "条件で判断";
}

function calendarPlanningContext(calendar: PlantCalendar | null): Record<string, unknown> {
  const snapshot = calendar?.generation.context_snapshot;
  if (!snapshot || typeof snapshot.planning !== "object" || snapshot.planning === null) return {};
  return snapshot.planning as Record<string, unknown>;
}
