import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, Leaf, LoaderCircle, MessageCircle, Plus, RefreshCw, Search, Sparkles, X } from "lucide-react";

import { DisabledActionReason, disabledActionTitle } from "../DisabledActionReason";
import { errorMessage, formatDate, todayString } from "../formatters";
import { SearchableSelect } from "../SearchableSelect";
import type { PlantActionCompletionPayload, PlantBundle, PlantCalendar, PlantCalendarAction, PlantQuestionRecord } from "../types";
import { AnnualCalendarGantt } from "./AnnualCalendarGantt";
import { CalendarActionCard, CalendarKanbanCard, NewCalendarActionForm } from "./CalendarActionCard";
import { FALLBACK_ACTION_TYPES } from "./constants";

type KanbanColumn = "planned" | "in_progress" | "completed";
type ActionTimingState = PlantBundle["suggestions"][number]["timing_state"];

const KANBAN_COLUMNS: Array<{ id: KanbanColumn; label: string; description: string }> = [
  { id: "planned", label: "未完了", description: "着手を待っている作業" },
  { id: "in_progress", label: "作業中", description: "現在取り組んでいる作業" },
  { id: "completed", label: "完了", description: "実施済み・見送りの作業" },
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
  onAskQuestion: (plantingId: string, question: string) => Promise<PlantQuestionRecord>;
  onRegenerate: (plantingId: string, startDate: string, planningNotes: string) => Promise<void>;
  onAddAction: (plantingId: string, payload: Partial<PlantCalendarAction>) => Promise<void>;
  onDeleteAction: (plantingId: string, actionId: string) => Promise<void>;
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
  onAskQuestion,
  onRegenerate,
  onAddAction,
  onDeleteAction,
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

  const leftDate = left.completion?.performed_on || left.window_end;
  const rightDate = right.completion?.performed_on || right.window_end;
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
