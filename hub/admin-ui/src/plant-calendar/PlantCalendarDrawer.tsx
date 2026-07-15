import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Leaf, MessageCircle, Plus, RefreshCw, Sparkles, X } from "lucide-react";

import { errorMessage, formatDate, todayString } from "../formatters";
import type { PlantBundle, PlantCalendar, PlantCalendarAction, PlantQuestionRecord } from "../types";
import { AnnualCalendarGantt } from "./AnnualCalendarGantt";
import { CalendarActionCard, NewCalendarActionForm } from "./CalendarActionCard";
import { FALLBACK_ACTION_TYPES } from "./constants";


export interface PlantCalendarDrawerProps {
  bundle: PlantBundle;
  selectedPlantingId: string;
  busy: boolean;
  onPlantingChange: (plantingId: string) => void;
  onClose: () => void;
  onEditAction: (plantingId: string, actionId: string, payload: Partial<PlantCalendarAction> & { use_as_guidance?: boolean }) => Promise<void>;
  onCompleteAction: (plantingId: string, actionId: string, performedOn: string, note: string, rating: number, images: File[]) => Promise<void>;
  onAskQuestion: (plantingId: string, question: string) => Promise<PlantQuestionRecord>;
  onRegenerate: (plantingId: string, startDate: string, planningNotes: string) => Promise<void>;
  onAddAction: (plantingId: string, payload: Partial<PlantCalendarAction>) => Promise<void>;
  onDeleteAction: (plantingId: string, actionId: string) => Promise<void>;
}

export function PlantCalendarDrawer({
  bundle,
  selectedPlantingId,
  busy,
  onPlantingChange,
  onClose,
  onEditAction,
  onCompleteAction,
  onAskQuestion,
  onRegenerate,
  onAddAction,
  onDeleteAction,
}: PlantCalendarDrawerProps) {
  const activePlantings = bundle.plantings.filter((planting) => planting.status === "active");
  const planting = activePlantings.find((item) => item.id === selectedPlantingId) ?? activePlantings[0] ?? null;
  const calendar = planting ? bundle.calendars[planting.id] : null;
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [questionError, setQuestionError] = useState("");
  const [generationOpen, setGenerationOpen] = useState(false);
  const [generationStart, setGenerationStart] = useState(todayString());
  const [generationNotes, setGenerationNotes] = useState("");
  const [generationError, setGenerationError] = useState("");
  const [addingAction, setAddingAction] = useState(false);

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

  const actions = useMemo(
    () => [...(calendar?.actions ?? [])].sort((left, right) => left.window_start.localeCompare(right.window_start)),
    [calendar?.actions],
  );
  const actionTypes = bundle.action_types?.length ? bundle.action_types : FALLBACK_ACTION_TYPES;
  const actionTypeByCode = useMemo(() => new Map(actionTypes.map((item) => [item.code, item])), [actionTypes]);
  const suggestions = useMemo(
    () => bundle.suggestions.filter((suggestion) => suggestion.planting_id === planting?.id),
    [bundle.suggestions, planting?.id],
  );
  const suggestionByActionId = useMemo(
    () => new Map(suggestions.map((suggestion) => [suggestion.action.id, suggestion.timing_state])),
    [suggestions],
  );

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

  return (
    <div className="calendar-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className="calendar-drawer" role="dialog" aria-modal="true" aria-label="栽培カレンダー">
        <header className="calendar-header">
          <div><span>栽培支援</span><h2>栽培カレンダー</h2></div>
          <button type="button" className="icon-button" onClick={onClose} title="閉じる"><X size={19} /></button>
        </header>

        {activePlantings.length === 0 ? (
          <CalendarEmptyState />
        ) : planting && (
          <>
            <section className="calendar-plant-selector">
              <label>管理する作物
                <select value={planting.id} onChange={(event) => onPlantingChange(event.target.value)}>
                  {activePlantings.map((item) => (
                    <option key={item.id} value={item.id}>{item.placement_name} / {item.crop_name}{item.cultivar ? ` (${item.cultivar})` : ""}</option>
                  ))}
                </select>
              </label>
              <div className="plant-context">
                <span><Leaf size={15} />{planting.crop_name}</span>
                <span>{planting.placement_name}</span>
                <span>{formatDate(planting.planted_on)} 定植</span>
              </div>
            </section>

            <SuggestionSummary suggestions={suggestions} />
            {calendar && <CareProfileSummary calendar={calendar} />}
            <AnnualCalendarGantt actions={actions} />

            <section className="calendar-generation" aria-label="計画の生成設定">
              <div className="calendar-section-heading">
                <div><Sparkles size={17} /><strong>AI計画</strong></div>
                <button type="button" onClick={() => setGenerationOpen((value) => !value)}><RefreshCw size={15} />条件を編集して再生成</button>
              </div>
              {generationOpen && (
                <form onSubmit={(event) => void regenerate(event)}>
                  <label>計画開始日<input type="date" required value={generationStart} onChange={(event) => setGenerationStart(event.target.value)} /></label>
                  <label>今回の生成条件<textarea value={generationNotes} onChange={(event) => setGenerationNotes(event.target.value)} placeholder="今年は収穫を優先、農薬を使わない、現在は開花直前など" /></label>
                  <p>計画済みの将来作業を置き換えます。実施済みの記録は保持します。AI呼び出しが1回発生します。</p>
                  {generationError && <p className="form-error">{generationError}</p>}
                  <div className="form-actions">
                    <button type="button" onClick={() => setGenerationOpen(false)}>キャンセル</button>
                    <button type="submit" disabled={busy}><Sparkles size={15} />12か月計画を再生成</button>
                  </div>
                </form>
              )}
            </section>

            <section className="calendar-action-list" aria-label="管理作業">
              <div className="calendar-section-heading">
                <div><strong>管理作業</strong><span>{actions.length}件</span></div>
                <div>
                  {calendar && <small>r{calendar.revision} / {calendar.generation.source === "llm" ? "AI生成" : "標準提案"}</small>}
                  <button type="button" onClick={() => setAddingAction(true)}><Plus size={15} />作業を追加</button>
                </div>
              </div>
              {addingAction && (
                <NewCalendarActionForm
                  actionTypes={actionTypes}
                  busy={busy}
                  onCancel={() => setAddingAction(false)}
                  onSave={async (payload) => {
                    await onAddAction(planting.id, payload);
                    setAddingAction(false);
                  }}
                />
              )}
              {actions.map((action) => (
                <CalendarActionCard
                  key={action.id}
                  plantingId={planting.id}
                  action={action}
                  actionType={actionTypeByCode.get(action.action_type) ?? actionTypeByCode.get("other") ?? FALLBACK_ACTION_TYPES[FALLBACK_ACTION_TYPES.length - 1]}
                  actionTypes={actionTypes}
                  timingState={suggestionByActionId.get(action.id)}
                  busy={busy}
                  onEdit={onEditAction}
                  onComplete={onCompleteAction}
                  onDelete={onDeleteAction}
                />
              ))}
            </section>

            <section className="plant-question">
              <div className="calendar-section-heading"><div><MessageCircle size={17} /><strong>この作物について質問</strong></div></div>
              <form onSubmit={(event) => void ask(event)}>
                <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="追肥は今必要ですか？ 葉の斑点は何を確認すべきですか？" />
                <button type="submit" disabled={busy || !question.trim()}><MessageCircle size={16} />質問する</button>
              </form>
              {questionError && <p className="form-error">{questionError}</p>}
              {answer && <div className="question-answer"><strong>回答</strong><p>{answer}</p></div>}
              <p className="safety-note">農薬を使う場合は、対象作物への登録、ラベル、希釈倍率、収穫前日数と地域の指針を必ず確認してください。</p>
            </section>
          </>
        )}
      </aside>
    </div>
  );
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
