import { useEffect, useState, type DragEvent, type FormEvent } from "react";
import {
  Ban,
  CalendarRange,
  Check,
  ChevronRight,
  CirclePlay,
  ClipboardCheck,
  Clock3,
  Edit3,
  ExternalLink,
  GripVertical,
  ImagePlus,
  Leaf,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  Users,
} from "lucide-react";

import { DisabledActionReason, disabledActionTitle } from "../DisabledActionReason";
import { errorMessage, formatDate, formatDateRange, todayString } from "../formatters";
import { SearchableSelect } from "../SearchableSelect";
import type {
  PlantActionCompletionPayload,
  PlantActionMutationPayload,
  PlantActionPriority,
  PlantActionSkipPayload,
  PlantActionSkipReason,
  PlantActionTypeDefinition,
  PlantActionWorkDetails,
  PlantCalendarAction,
  WorkMethodOption,
  WorkMethodType,
} from "../types";
import { PRIORITY_LABELS, RATING_OPTIONS, TIMING_LABELS } from "./constants";


type TimingState = keyof typeof TIMING_LABELS;
type ActionUpdate = PlantActionMutationPayload & { use_as_guidance?: boolean };

const ACTION_CAPABILITIES: Record<PlantCalendarAction["status"], { edit: boolean; delete: boolean; start: boolean; returnToPlanned: boolean; record: boolean; skip: boolean }> = {
  planned: { edit: true, delete: true, start: true, returnToPlanned: false, record: false, skip: true },
  in_progress: { edit: true, delete: false, start: false, returnToPlanned: true, record: true, skip: true },
  completed: { edit: false, delete: false, start: false, returnToPlanned: false, record: false, skip: false },
  skipped: { edit: false, delete: false, start: false, returnToPlanned: true, record: false, skip: false },
};

const SKIP_REASON_OPTIONS: Array<{ value: PlantActionSkipReason; label: string }> = [
  { value: "generated_in_error", label: "自動計画で誤って生成された" },
  { value: "timing_passed", label: "適期を過ぎた" },
  { value: "start_conditions_not_met", label: "実施条件を満たしていない" },
  { value: "already_satisfied", label: "既に作業の目的を満たしている" },
  { value: "duplicate", label: "他の作業と重複している" },
  { value: "not_applicable", label: "現在の作物・区画には不要" },
  { value: "other", label: "その他" },
];

interface CalendarActionCardProps {
  plantingId: string;
  action: PlantCalendarAction;
  actionType: PlantActionTypeDefinition;
  actionTypes: PlantActionTypeDefinition[];
  timingState?: TimingState;
  busy: boolean;
  initialRecording?: boolean;
  onEdit: (plantingId: string, actionId: string, payload: ActionUpdate) => Promise<void>;
  onComplete: (plantingId: string, actionId: string, payload: PlantActionCompletionPayload) => Promise<void>;
  onSkip: (plantingId: string, actionId: string, payload: PlantActionSkipPayload) => Promise<void>;
  onDelete: (plantingId: string, actionId: string) => Promise<void>;
}

interface NewCalendarActionFormProps {
  actionTypes: PlantActionTypeDefinition[];
  busy: boolean;
  onCancel: () => void;
  onSave: (payload: PlantActionMutationPayload) => Promise<void>;
}

interface CalendarKanbanCardProps {
  action: PlantCalendarAction;
  actionType: PlantActionTypeDefinition;
  timingState?: TimingState;
  cropLabel?: string;
  onOpen: () => void;
  draggable: boolean;
  onDragStart: (event: DragEvent<HTMLButtonElement>) => void;
  onDragEnd: () => void;
}

export function NewCalendarActionForm({ actionTypes, busy, onCancel, onSave }: NewCalendarActionFormProps) {
  const [title, setTitle] = useState("");
  const [actionType, setActionType] = useState("observation");
  const [priority, setPriority] = useState<PlantActionPriority>("recommended");
  const [start, setStart] = useState(todayString());
  const [end, setEnd] = useState(todayString());
  const [reason, setReason] = useState("");
  const [instructions, setInstructions] = useState("");
  const [instructionsHtml, setInstructionsHtml] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [requiredPeople, setRequiredPeople] = useState(1);
  const [estimatedMinutes, setEstimatedMinutes] = useState(30);
  const [localError, setLocalError] = useState("");
  const blockingReasons = [
    ...(!title.trim() ? ["作業名を入力してください"] : []),
    ...(!start || !end ? ["開始日と終了日を選択してください"] : []),
    ...(start && end && end < start ? ["終了日を開始日以降にしてください"] : []),
    ...(!Number.isInteger(requiredPeople) || requiredPeople < 1 || requiredPeople > 100 ? ["必要人数は1〜100人の整数で入力してください"] : []),
    ...(!Number.isInteger(estimatedMinutes) || estimatedMinutes < 1 || estimatedMinutes > 1440 ? ["見積時間は1〜1440分の整数で入力してください"] : []),
    ...(busy ? ["現在の処理が完了するまでお待ちください"] : []),
  ];

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setLocalError("");
    try {
      await onSave({
        title,
        action_type: actionType,
        priority,
        window_start: start,
        window_end: end,
        reason,
        instructions,
        instructions_html: instructionsHtml,
        images,
        tags: [],
        required_people: requiredPeople,
        estimated_minutes: estimatedMinutes,
      });
    } catch (caught) {
      setLocalError(errorMessage(caught));
    }
  };

  return (
    <form className="action-edit-form new-action-form" onSubmit={(event) => void save(event)}>
      <strong>作業内容</strong>
      <label>作業名<input required value={title} onChange={(event) => setTitle(event.target.value)} /></label>
      <div className="field-grid two">
        <ActionTypeSelect actionTypes={actionTypes} value={actionType} onChange={setActionType} />
        <PrioritySelect value={priority} onChange={setPriority} />
      </div>
      <div className="field-grid two">
        <label>開始日<input type="date" required value={start} onChange={(event) => setStart(event.target.value)} /></label>
        <label>終了日<input type="date" required value={end} onChange={(event) => setEnd(event.target.value)} /></label>
      </div>
      <WorkloadFields
        requiredPeople={requiredPeople}
        estimatedMinutes={estimatedMinutes}
        onRequiredPeopleChange={setRequiredPeople}
        onEstimatedMinutesChange={setEstimatedMinutes}
      />
      <label>理由<textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      <label>作業の要約<textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} placeholder="カードですぐ確認できる短い説明" /></label>
      <RichActionContentField html={instructionsHtml} onHtmlChange={setInstructionsHtml} images={images} onImagesChange={setImages} />
      <DisabledActionReason id="new-calendar-action-blocked" reasons={blockingReasons} prefix="作業を追加するには" />
      {localError && <p className="form-error" role="alert">作業を追加できませんでした: {localError}</p>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>キャンセル</button>
        <button type="submit" disabled={blockingReasons.length > 0} aria-describedby={blockingReasons.length > 0 ? "new-calendar-action-blocked" : undefined} title={disabledActionTitle(blockingReasons)}><Plus size={15} />追加</button>
      </div>
    </form>
  );
}

export function CalendarKanbanCard({ action, actionType, timingState, cropLabel, onOpen, draggable, onDragStart, onDragEnd }: CalendarKanbanCardProps) {
  return (
    <button
      type="button"
      id={`calendar-action-${action.id}`}
      className={`calendar-kanban-card ${action.status}`}
      data-action-id={action.id}
      data-action-status={action.status}
      style={{ borderLeftColor: actionType.accent }}
      onClick={onOpen}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      aria-label={`${action.title}の詳細を開く`}
    >
      <span className="kanban-card-topline">
        {draggable && <span className="kanban-drag-handle" title="ドラッグして状態を変更"><GripVertical size={14} /></span>}
        <span className={`priority-badge ${action.priority}`}>{PRIORITY_LABELS[action.priority]}</span>
        {timingState && <span className={`timing-badge ${timingState}`}>{TIMING_LABELS[timingState]}</span>}
        <span className="kanban-action-type">{actionType.label}</span>
      </span>
      <span className="kanban-card-main">
        <ActionIllustration actionType={actionType} compact />
        <span className="kanban-card-copy">
          <strong>{action.title}</strong>
          <time dateTime={action.window_start}>{formatDateRange(action.window_start, action.window_end)}</time>
        </span>
        <ChevronRight size={18} aria-hidden="true" />
      </span>
      {cropLabel && <span className="kanban-card-crop"><Leaf size={13} />{cropLabel}</span>}
      <span className="kanban-card-workload">
        <span><Users size={14} />{action.required_people}人</span>
        <span><Clock3 size={14} />{formatDuration(action.estimated_minutes)}</span>
      </span>
    </button>
  );
}

export function CalendarActionCard({
  plantingId,
  action,
  actionType,
  actionTypes,
  timingState,
  busy,
  initialRecording = false,
  onEdit,
  onComplete,
  onSkip,
  onDelete,
}: CalendarActionCardProps) {
  const [editing, setEditing] = useState(false);
  const [recording, setRecording] = useState(false);
  const [skipping, setSkipping] = useState(false);
  const capabilities = ACTION_CAPABILITIES[action.status];
  const busyReason = busy ? "現在の処理が完了するまでお待ちください" : "";

  useEffect(() => {
    if (initialRecording && capabilities.record) setRecording(true);
  }, [capabilities.record, initialRecording]);

  return (
    <article
      className={`calendar-action ${action.status}`}
      data-action-id={action.id}
      style={{ borderLeftColor: actionType.accent }}
    >
      <ActionStatusLine action={action} timingState={timingState} />
      <div className="action-main">
        <ActionIllustration actionType={actionType} />
        <div className="action-copy">
          <div className="action-heading">
            <div><small>{actionType.label}</small><h3>{action.title}</h3></div>
            {(capabilities.edit || capabilities.delete) && <div className="action-row-tools">
              {capabilities.edit && <button type="button" className="action-edit-button" onClick={() => setEditing(true)} disabled={busy} title={busyReason || "予定、説明、人数を編集"}><Edit3 size={16} />作業内容を編集</button>}
              {capabilities.delete && <button type="button" className="action-icon-button danger" onClick={() => { if (window.confirm(`「${action.title}」を削除しますか？\nこの操作は元に戻せません。`)) void onDelete(plantingId, action.id); }} disabled={busy} title={busyReason || "作業を削除"}><Trash2 size={16} /></button>}
            </div>}
          </div>
          <dl className="action-detail">
            <dt>人員</dt><dd>{action.required_people}人</dd>
            <dt>見積</dt><dd>{formatDuration(action.estimated_minutes)}</dd>
            <dt>理由</dt><dd>{action.reason || "未設定"}</dd>
            <dt>作業</dt><dd>{action.instructions || "未設定"}</dd>
          </dl>
          {action.instructions_html && <RichActionContent html={action.instructions_html} />}
          {Boolean(action.attachments?.length) && <div className="action-content-images">{action.attachments.map((attachment) => <a key={attachment.id} href={attachment.url} target="_blank" rel="noopener noreferrer"><img src={attachment.url} alt={attachment.original_filename || "作業画像"} loading="lazy" /></a>)}</div>}
          <WorkGuidance action={action} />
          {action.tags.length > 0 && <div className="action-tags">{action.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
        </div>
      </div>

      {action.completion && <CompletionRecord action={action} />}
      {action.skip_decision && <SkipDecisionRecord action={action} />}
      {editing && (
        <div className="action-edit-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setEditing(false); }}>
          <section className="action-edit-dialog" role="dialog" aria-modal="true" aria-labelledby={`action-edit-title-${action.id}`}>
            <header><div><span>実績入力とは別に編集します</span><h3 id={`action-edit-title-${action.id}`}>作業内容を編集</h3></div><button type="button" className="icon-button" onClick={() => setEditing(false)} title="閉じる">×</button></header>
            <div className="action-edit-dialog-body"><ActionEditForm action={action} actionTypes={actionTypes} busy={busy} onCancel={() => setEditing(false)} onSave={async (payload) => { await onEdit(plantingId, action.id, payload); setEditing(false); }} /></div>
          </section>
        </div>
      )}
      {!editing && (capabilities.start || capabilities.returnToPlanned || capabilities.record || capabilities.skip) && (
        skipping && capabilities.skip ? (
          <SkipDecisionForm
            plantingId={plantingId}
            action={action}
            busy={busy}
            onCancel={() => setSkipping(false)}
            onSkip={async (...args) => {
              await onSkip(...args);
              setSkipping(false);
            }}
          />
        ) : recording && capabilities.record ? (
          <WorkRecordForm
            plantingId={plantingId}
            action={action}
            busy={busy}
            onCancel={() => setRecording(false)}
            onComplete={async (...args) => {
              await onComplete(...args);
              setRecording(false);
            }}
          />
        ) : (
          <div className={`action-state-panel ${action.status}`}>
            <div className="action-state-guidance">
              <strong>{actionStateGuidance(action.status).title}</strong>
              <span>{actionStateGuidance(action.status).description}</span>
            </div>
            <div className="action-state-controls">
              {capabilities.start && <button type="button" className="start-button" onClick={() => void onEdit(plantingId, action.id, { status: "in_progress", use_as_guidance: false })} disabled={busy} title={busyReason || "この作業を作業中へ移動"}><CirclePlay size={16} />作業を開始</button>}
              {capabilities.returnToPlanned && <button type="button" onClick={() => void onEdit(plantingId, action.id, { status: "planned", use_as_guidance: false })} disabled={busy} title={busyReason || "この作業を未完了へ戻す"}><RotateCcw size={16} />未完了に戻す</button>}
              {capabilities.record && <button type="button" className="complete-button" onClick={() => setRecording(true)} disabled={busy} title={busyReason || "実施内容を記録して完了にする"}><Check size={16} />実績を記録して完了</button>}
              {capabilities.skip && <button type="button" className="skip-button" onClick={() => setSkipping(true)} disabled={busy} title={busyReason || "確認結果を記録して、この作業を見送る"}><Ban size={16} />確認して見送る</button>}
            </div>
          </div>
        )
      )}
    </article>
  );
}

function actionStateGuidance(status: PlantCalendarAction["status"]) {
  if (status === "planned") return { title: "まだ開始していません", description: "着手すると、実績を記録できるようになります。" };
  if (status === "in_progress") return { title: "作業中です", description: "作業後に実施日と内容を記録して完了してください。" };
  if (status === "skipped") return { title: "今回は見送りました", description: "実施対象へ戻す場合は未完了に戻してください。" };
  return { title: "完了しています", description: "実施内容は記録として保持されます。" };
}

function ActionStatusLine({ action, timingState }: { action: PlantCalendarAction; timingState?: TimingState }) {
  const scheduleState = timingState ?? (action.status === "completed" ? "completed" : action.priority);
  return (
    <>
      <div className={`action-work-window ${scheduleState}`}>
        <CalendarRange size={20} />
        <div>
          <span>作業期間</span>
          <time dateTime={action.window_start}>{formatDateRange(action.window_start, action.window_end)}</time>
        </div>
        {action.timing_label && <strong>{action.timing_label}</strong>}
      </div>
      <div className="action-topline">
        <span className={`priority-badge ${action.priority}`}>{PRIORITY_LABELS[action.priority]}</span>
        {timingState && <span className={`timing-badge ${timingState}`}>{TIMING_LABELS[timingState]}</span>}
        {action.status === "completed" && <span className="completed-badge"><Check size={13} />実施済み</span>}
        {action.status === "in_progress" && <span className="in-progress-badge"><CirclePlay size={13} />作業中</span>}
        {action.status === "skipped" && <span className="skipped-badge">見送り</span>}
      </div>
    </>
  );
}

function WorkGuidance({ action }: { action: PlantCalendarAction }) {
  const details = action.work_plan;
  if (!details || (!details.targets.length && !details.checkpoints.length && !details.method_options.length)) return null;
  return (
    <section className="work-guidance" aria-label="作業の具体情報">
      <div><ClipboardCheck size={15} /><strong>作業の具体情報</strong></div>
      {details.targets.length > 0 && <p><span>対象</span>{details.targets.join("、")}</p>}
      {details.start_conditions.length > 0 && <p><span>開始条件</span>{details.start_conditions.join("、")}</p>}
      {details.skip_conditions.length > 0 && <p className="work-skip-condition"><span>見送り</span>{details.skip_conditions.join("、")}</p>}
      {details.checkpoints.length > 0 && <p><span>確認点</span>{details.checkpoints.join("、")}</p>}
      {details.method_options.length > 0 && (
        <div className="work-method-options">
          <span>方法候補</span>
          <div className="work-method-list">
            {details.method_options.map((method, index) => (
              <WorkMethodDetails key={method.id} method={method} initiallyOpen={index === 0} />
            ))}
          </div>
        </div>
      )}
      {details.completion_criteria.length > 0 && <p><span>完了確認</span>{details.completion_criteria.join("、")}</p>}
    </section>
  );
}

function WorkMethodDetails({ method, initiallyOpen }: { method: WorkMethodOption; initiallyOpen: boolean }) {
  const frequency = formatWorkFrequency(method);
  return (
    <details className="work-method-detail" open={initiallyOpen}>
      <summary>
        <strong>{method.label}</strong>
        {method.material_name && <small>{method.material_name}</small>}
      </summary>
      <dl>
        {method.purpose && <><dt>目的</dt><dd>{method.purpose}</dd></>}
        {method.application_method && <><dt>方法</dt><dd>{method.application_method}</dd></>}
        {method.amount_or_rate && <><dt>使用量等</dt><dd>{method.amount_or_rate}</dd></>}
        {frequency && <><dt>頻度</dt><dd>{frequency}</dd></>}
      </dl>
      {method.procedure_steps.length > 0 && <div><span>手順</span><ol>{method.procedure_steps.map((step) => <li key={step}>{step}</li>)}</ol></div>}
      {method.completion_checks.length > 0 && <div><span>終了確認</span><ul>{method.completion_checks.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      {method.precautions.length > 0 && <div className="method-precautions"><span>注意</span><ul>{method.precautions.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      {method.registration_number && <small>登録番号 {method.registration_number}</small>}
      {method.source_url && <a href={method.source_url} target="_blank" rel="noopener noreferrer">{method.source_name || "根拠情報"}<ExternalLink size={12} /></a>}
    </details>
  );
}

function formatWorkFrequency(method: WorkMethodOption): string {
  const { frequency } = method;
  const modeLabels = { one_time: "1回", as_needed: "状態を見て実施", interval: "間隔で実施", seasonal: "適期に実施", continuous: "継続確認" };
  const intervals = [frequency.min_interval_days, frequency.preferred_interval_days, frequency.max_interval_days].filter((value): value is number => value !== null);
  const intervalLabel = intervals.length > 0 ? `${Math.min(...intervals)}〜${Math.max(...intervals)}日間隔` : "";
  const countLabel = frequency.max_applications ? `最大${frequency.max_applications}回` : "";
  return [modeLabels[frequency.mode], intervalLabel, countLabel, frequency.basis].filter(Boolean).join(" / ");
}

function ActionIllustration({ actionType, compact = false }: { actionType: PlantActionTypeDefinition; compact?: boolean }) {
  const className = compact ? "kanban-action-illustration" : "action-illustration";
  if (!actionType.illustration_url) {
    return <span className={compact ? "kanban-action-illustration fallback" : "action-illustration-fallback"} aria-hidden="true"><Leaf size={compact ? 20 : 28} /></span>;
  }
  return <img className={className} src={actionType.illustration_url} alt="" loading="lazy" />;
}

function CompletionRecord({ action }: { action: PlantCalendarAction }) {
  const completion = action.completion;
  if (!completion) return null;
  const rating = completion.rating ? RATING_OPTIONS[completion.rating - 1] : null;
  return (
    <div className="completion-record">
      <p className="completion-line">
        <Check size={14} />{formatDate(completion.performed_on)} に実施{completion.note ? `: ${completion.note}` : ""}
        {rating && <span className="completion-rating" title={`評価 ${completion.rating} / 5`}>{rating.emoji}</span>}
      </p>
      {completion.work_details?.execution && <WorkCompletion details={completion.work_details.execution} />}
      {Boolean(completion.attachments?.length) && (
        <div className="completion-images">
          {completion.attachments?.map((attachment) => (
            <a key={attachment.id} href={attachment.url} target="_blank" rel="noopener noreferrer">
              <img src={attachment.url} alt={attachment.original_filename || "作業記録画像"} loading="lazy" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function SkipDecisionRecord({ action }: { action: PlantCalendarAction }) {
  const decision = action.skip_decision;
  if (!decision) return null;
  const reason = SKIP_REASON_OPTIONS.find((option) => option.value === decision.reason_code)?.label ?? "その他";
  return (
    <section className="skip-decision-record" aria-label="見送り判断の記録">
      <p className="skip-decision-line"><Ban size={14} />{formatDate(decision.decided_on)} に確認して見送り</p>
      <dl>
        <dt>理由</dt><dd>{reason}</dd>
        <dt>確認内容</dt><dd>{decision.observed_facts}</dd>
        {decision.note && <><dt>判断メモ</dt><dd>{decision.note}</dd></>}
        {decision.next_review_on && <><dt>次回確認</dt><dd>{formatDate(decision.next_review_on)}</dd></>}
        {decision.decided_by && <><dt>記録者</dt><dd>{decision.decided_by}</dd></>}
      </dl>
      {decision.attachments.length > 0 && (
        <div className="completion-images">
          {decision.attachments.map((attachment) => (
            <a key={attachment.id} href={attachment.url} target="_blank" rel="noopener noreferrer">
              <img src={attachment.url} alt={attachment.original_filename || "見送り判断の確認画像"} loading="lazy" />
            </a>
          ))}
        </div>
      )}
    </section>
  );
}

function WorkCompletion({ details }: { details: NonNullable<PlantActionWorkDetails["execution"]> }) {
  const method = details.custom_method || details.method_label;
  return (
    <dl className="work-completion-detail">
      {details.target && <><dt>対象</dt><dd>{details.target}</dd></>}
      {method && <><dt>実施手段</dt><dd>{method}{details.registration_number ? `（登録番号 ${details.registration_number}）` : ""}</dd></>}
      {details.material_name && details.material_name !== method && <><dt>資材・製品</dt><dd>{details.material_name}</dd></>}
      {details.amount_or_rate && <><dt>使用量等</dt><dd>{details.amount_or_rate}</dd></>}
      {details.follow_up_days && <><dt>次回確認</dt><dd>実施日から {details.follow_up_days} 日後を目安</dd></>}
    </dl>
  );
}

interface SkipDecisionFormProps {
  plantingId: string;
  action: PlantCalendarAction;
  busy: boolean;
  onCancel: () => void;
  onSkip: CalendarActionCardProps["onSkip"];
}

function SkipDecisionForm({ plantingId, action, busy, onCancel, onSkip }: SkipDecisionFormProps) {
  const [decidedOn, setDecidedOn] = useState(todayString());
  const [reasonCode, setReasonCode] = useState<PlantActionSkipReason>("generated_in_error");
  const [observedFacts, setObservedFacts] = useState("");
  const [note, setNote] = useState("");
  const [nextReviewOn, setNextReviewOn] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [useAsGuidance, setUseAsGuidance] = useState(true);
  const [localError, setLocalError] = useState("");
  const blockingReasons = [
    ...(!decidedOn ? ["確認日を選択してください"] : []),
    ...(!observedFacts.trim() ? ["確認した状態や測定値を入力してください"] : []),
    ...(nextReviewOn && nextReviewOn < decidedOn ? ["次回確認日は確認日以降にしてください"] : []),
    ...(busy ? ["現在の処理が完了するまでお待ちください"] : []),
  ];

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLocalError("");
    try {
      await onSkip(plantingId, action.id, {
        decided_on: decidedOn,
        reason_code: reasonCode,
        observed_facts: observedFacts.trim(),
        note: note.trim(),
        next_review_on: nextReviewOn,
        images,
        use_as_guidance: useAsGuidance,
      });
    } catch (caught) {
      setLocalError(errorMessage(caught));
    }
  };

  return (
    <form className="skip-decision-form" onSubmit={(event) => void submit(event)}>
      <div className="skip-decision-heading"><Ban size={17} /><div><strong>確認して見送る</strong><span>作業済みにはせず、不要と判断した根拠を記録します。</span></div></div>
      <div className="field-grid two">
        <label>確認日<input type="date" required max={todayString()} value={decidedOn} onChange={(event) => setDecidedOn(event.target.value)} /></label>
        <label>判断理由<select value={reasonCode} onChange={(event) => setReasonCode(event.target.value as PlantActionSkipReason)}>{SKIP_REASON_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      </div>
      <label>確認した状態・測定値<textarea required maxLength={2000} value={observedFacts} onChange={(event) => setObservedFacts(event.target.value)} placeholder="例: 葉色と新梢は良好。排液EC 1.2 mS/cmで追肥は不要と判断" /></label>
      <label>判断メモ（任意）<textarea maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} placeholder="期限切れになった経緯や補足を記録" /></label>
      <label>次回確認日（任意）<input type="date" min={decidedOn} value={nextReviewOn} onChange={(event) => setNextReviewOn(event.target.value)} /></label>
      <ImagePasteInput label="確認画像（任意）" images={images} onChange={setImages} />
      <label className="guidance-check"><input type="checkbox" checked={useAsGuidance} onChange={(event) => setUseAsGuidance(event.target.checked)} /><span>この判断を同じ作物の今後のAI計画改善に利用する</span></label>
      <DisabledActionReason id={`skip-decision-blocked-${action.id}`} reasons={blockingReasons} prefix="見送りを記録するには" />
      {localError && <p className="form-error">{localError}</p>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>キャンセル</button>
        <button type="submit" disabled={blockingReasons.length > 0} aria-describedby={blockingReasons.length > 0 ? `skip-decision-blocked-${action.id}` : undefined} title={disabledActionTitle(blockingReasons)}><Ban size={15} />見送りとして記録</button>
      </div>
    </form>
  );
}

interface WorkRecordFormProps {
  plantingId: string;
  action: PlantCalendarAction;
  busy: boolean;
  onCancel: () => void;
  onComplete: CalendarActionCardProps["onComplete"];
}

function WorkRecordForm({ plantingId, action, busy, onCancel, onComplete }: WorkRecordFormProps) {
  const [performedOn, setPerformedOn] = useState(todayString());
  const [note, setNote] = useState("");
  const [rating, setRating] = useState<number | null>(null);
  const [images, setImages] = useState<File[]>([]);
  const [localError, setLocalError] = useState("");
  const workPlan = action.work_plan ?? { targets: [], start_conditions: [], skip_conditions: [], checkpoints: [], method_options: [], completion_criteria: [] };
  const workMethods = [...workPlan.method_options, ...COMMON_WORK_METHODS]
    .filter((method, index, methods) => methods.findIndex((candidate) => candidate.id === method.id) === index);
  const initialWorkMethod = workMethods[0];
  const [workTarget, setWorkTarget] = useState(workPlan.targets[0] ?? "");
  const [workMethodId, setWorkMethodId] = useState(initialWorkMethod?.id ?? "");
  const [customMethod, setCustomMethod] = useState("");
  const [customMethodType, setCustomMethodType] = useState<WorkMethodType>(defaultCustomMethodType(action.action_type));
  const [materialName, setMaterialName] = useState(initialWorkMethod?.material_name ?? "");
  const [amountOrRate, setAmountOrRate] = useState("");
  const [followUpDays, setFollowUpDays] = useState(String(recommendedFollowUpDays(initialWorkMethod, action.action_type)));
  const selectedWorkMethod = workMethods.find((method) => method.id === workMethodId);
  const selectedMethodType = workMethodId === "custom" ? customMethodType : selectedWorkMethod?.method_type;
  const followUpDaysNumber = followUpDays ? Number(followUpDays) : null;
  const blockingReasons = [
    ...(!performedOn ? ["実施日を選択してください"] : []),
    ...(rating === null ? ["5段階評価を選択してください"] : []),
    ...(!workMethodId ? ["実施した方法を選択してください"] : []),
    ...(workMethodId === "custom" && !customMethod.trim() ? ["実施した方法または使用した資材を入力してください"] : []),
    ...(followUpDaysNumber !== null && (!Number.isInteger(followUpDaysNumber) || followUpDaysNumber < 1 || followUpDaysNumber > 365) ? ["次回確認までの日数は1〜365日の整数で入力してください"] : []),
    ...(busy ? ["現在の処理が完了するまでお待ちください"] : []),
  ];

  const complete = async (event: FormEvent) => {
    event.preventDefault();
    setLocalError("");
    if (rating === null) {
      setLocalError("評価を選択してください。");
      return;
    }
    try {
      const workDetails: PlantActionWorkDetails = {
        execution: {
          target: workTarget.trim(),
          method_id: workMethodId,
          method_label: workMethodId === "custom" ? customMethod.trim() : selectedWorkMethod?.label ?? "",
          method_type: workMethodId === "custom" ? customMethodType : selectedWorkMethod?.method_type ?? "other",
          material_name: materialName.trim(),
          amount_or_rate: amountOrRate.trim(),
          registration_number: selectedWorkMethod?.registration_number ?? "",
          custom_method: workMethodId === "custom" ? customMethod.trim() : "",
          follow_up_days: followUpDaysNumber,
          source_name: selectedWorkMethod?.source_name ?? "",
          source_url: selectedWorkMethod?.source_url ?? "",
          source_checked_at: selectedWorkMethod?.source_checked_at ?? "",
        },
      };
      await onComplete(plantingId, action.id, { performed_on: performedOn, note, rating, images, work_details: workDetails });
    } catch (caught) {
      setLocalError(errorMessage(caught));
    }
  };

  return (
    <form className="work-record-form" onSubmit={(event) => void complete(event)}>
      <label>実施日<input type="date" required value={performedOn} onChange={(event) => setPerformedOn(event.target.value)} /></label>
      <fieldset className="work-detail-fields">
        <legend>作業の実績</legend>
        <label>作業・確認した対象
          <input value={workTarget} onChange={(event) => setWorkTarget(event.target.value)} list={`work-targets-${action.id}`} placeholder="対象を入力または候補から選択" />
          <datalist id={`work-targets-${action.id}`}>{workPlan.targets.map((target) => <option key={target} value={target} />)}</datalist>
        </label>
        <div className="filterable-field">
          <span className="field-label">実施した方法</span>
          <SearchableSelect
            ariaLabel="実施した方法"
            value={workMethodId}
            searchPlaceholder="方法、資材、区分を検索"
            emptyMessage="一致する方法はありません。別の方法を入力できます。"
            onChange={(nextId) => {
            const nextMethod = workMethods.find((method) => method.id === nextId);
            setWorkMethodId(nextId);
            setMaterialName(nextMethod?.material_name ?? "");
            setAmountOrRate("");
            setFollowUpDays(String(recommendedFollowUpDays(nextMethod, action.action_type)));
            }}
            options={[
              { value: "", label: "選択してください", fixed: true },
              ...workMethods.map((method) => ({
                value: method.id,
                label: method.label,
                searchText: `${method.method_type} ${method.material_name} ${method.amount_or_rate}`,
              })),
              { value: "custom", label: "別の方法を入力", fixed: true },
            ]}
          />
        </div>
        {workMethodId === "custom" && (
          <div className="field-grid two">
            <label>区分
              <select value={customMethodType} onChange={(event) => {
                setCustomMethodType(event.target.value as WorkMethodType);
                if (!methodUsesMaterial(event.target.value as WorkMethodType)) setMaterialName("");
              }}>
                {WORK_METHOD_TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>実施内容<input value={customMethod} onChange={(event) => setCustomMethod(event.target.value)} placeholder="例: 株元へ少量施す" /></label>
          </div>
        )}
        {selectedMethodType && methodUsesMaterial(selectedMethodType) && (
          <label>使用した資材・製品（任意）<input value={materialName} onChange={(event) => setMaterialName(event.target.value)} placeholder="肥料、農薬、処理資材など" /></label>
        )}
        {selectedMethodType && methodUsesAmountOrRate(selectedMethodType, action.action_type) && (
          <label>実際の使用量・希釈・処理時間（任意）<input value={amountOrRate} onChange={(event) => setAmountOrRate(event.target.value)} placeholder={selectedWorkMethod?.amount_or_rate || "例: 500倍、1鉢2L、10分"} /></label>
        )}
        <label className="follow-up-default-field"><span>次回の確認目安 <small>AIの提案値・変更できます</small></span><input type="number" min="1" max="365" step="1" value={followUpDays} onChange={(event) => setFollowUpDays(event.target.value)} /><em>実施日から何日後に状態を見直すかの目安です。迷う場合はこのまま記録できます。</em></label>
      </fieldset>
      <label>メモ<input value={note} onChange={(event) => setNote(event.target.value)} placeholder="使用量、状態など（任意）" /></label>
      <fieldset className="work-rating">
        <legend>評価</legend>
        <div>
          {RATING_OPTIONS.map((option) => (
            <label key={option.value} title={option.label}>
              <input type="radio" name={`rating-${action.id}`} value={option.value} checked={rating === option.value} onChange={() => setRating(option.value)} />
              <span aria-hidden="true">{option.emoji}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <ImagePasteInput label="作業記録の画像" images={images} onChange={setImages} />
      <DisabledActionReason id={`work-record-blocked-${action.id}`} reasons={blockingReasons} prefix="作業を記録するには" />
      {localError && <p className="form-error">{localError}</p>}
      <div>
        <button type="button" onClick={onCancel}>戻る</button>
        <button type="submit" disabled={blockingReasons.length > 0} aria-describedby={blockingReasons.length > 0 ? `work-record-blocked-${action.id}` : undefined} title={disabledActionTitle(blockingReasons)}><Check size={15} />この日付で記録</button>
      </div>
    </form>
  );
}

function RichActionContentField({ html, onHtmlChange, images, onImagesChange }: { html: string; onHtmlChange: (value: string) => void; images: File[]; onImagesChange: (value: File[]) => void }) {
  const addImages = (files: File[], selectionStart = html.length, selectionEnd = html.length) => {
    const accepted = files.filter((file) => ["image/jpeg", "image/png", "image/webp"].includes(file.type)).slice(0, Math.max(0, 5 - images.length));
    if (accepted.length === 0) return;
    const markers = accepted.map((_, offset) => `{{image:${images.length + offset}}}`).join("\n");
    onImagesChange([...images, ...accepted]);
    onHtmlChange(`${html.slice(0, selectionStart)}${markers}${html.slice(selectionEnd)}`);
  };
  return (
    <fieldset className="rich-action-content">
      <legend>詳しい作業内容・画像</legend>
      <p><code>&lt;p&gt;</code>、<code>&lt;strong&gt;</code>、<code>&lt;ul&gt;</code>などのHTMLを使用できます。画像は選択または貼り付けた位置へ挿入されます。</p>
      <textarea
        value={html}
        onChange={(event) => onHtmlChange(event.target.value)}
        onPaste={(event) => {
          const files = Array.from(event.clipboardData.files);
          if (files.length === 0) return;
          event.preventDefault();
          addImages(files, event.currentTarget.selectionStart, event.currentTarget.selectionEnd);
        }}
        placeholder={'<p>葉の裏側を確認します。</p>\n<strong>注意:</strong> 雨の日は延期します。'}
        aria-label="HTML形式の詳しい作業内容"
      />
      <label className="image-input"><span><ImagePlus size={15} />画像を選ぶ・ここへ貼り付ける</span><input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => addImages(Array.from(event.target.files ?? []))} /></label>
      {images.length > 0 && <ul className="pending-image-list">{images.map((image, index) => <li key={`${image.name}-${index}`}><span>{index + 1}</span>{image.name}<code>{`{{image:${index}}}`}</code></li>)}</ul>}
      {html && <div className="rich-action-preview"><span>プレビュー</span><RichActionContent html={html.replace(/\{\{image:\d+\}\}/g, '<em class="pending-image-placeholder">画像（保存後に表示）</em>')} /></div>}
    </fieldset>
  );
}

function ImagePasteInput({ label, images, onChange }: { label: string; images: File[]; onChange: (images: File[]) => void }) {
  const append = (files: File[]) => onChange([...images, ...files.filter((file) => ["image/jpeg", "image/png", "image/webp"].includes(file.type))].slice(0, 5));
  return (
    <div className="image-paste-input" tabIndex={0} onPaste={(event) => { const files = Array.from(event.clipboardData.files); if (files.length) { event.preventDefault(); append(files); } }}>
      <label className="image-input"><span><ImagePlus size={15} />{label}</span><input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => append(Array.from(event.target.files ?? []))} /></label>
      <small>最大5枚。枠を選択してクリップボードから画像を貼り付けることもできます。</small>
      {images.length > 0 && <span className="image-paste-count">{images.length}枚を追加</span>}
    </div>
  );
}

function RichActionContent({ html }: { html: string }) {
  return <div className="rich-action-rendered" dangerouslySetInnerHTML={{ __html: sanitizeActionHtml(html) }} />;
}

function sanitizeActionHtml(value: string): string {
  const documentValue = new DOMParser().parseFromString(value, "text/html");
  const allowedTags = new Set(["P", "BR", "STRONG", "EM", "UL", "OL", "LI", "H3", "H4", "BLOCKQUOTE", "A", "IMG", "FIGURE", "CODE"]);
  [...documentValue.body.querySelectorAll("*")].forEach((element) => {
    if (!allowedTags.has(element.tagName)) {
      element.replaceWith(...element.childNodes);
      return;
    }
    [...element.attributes].forEach((attribute) => {
      const allowed = (element.tagName === "A" && ["href", "target", "rel"].includes(attribute.name))
        || (element.tagName === "IMG" && ["src", "alt", "loading"].includes(attribute.name))
        || (element.tagName === "EM" && attribute.name === "class" && attribute.value === "pending-image-placeholder");
      if (!allowed) element.removeAttribute(attribute.name);
    });
    if (element.tagName === "A") {
      const href = element.getAttribute("href") ?? "";
      if (!href.startsWith("https://") && !href.startsWith("/")) element.removeAttribute("href");
      element.setAttribute("target", "_blank");
      element.setAttribute("rel", "noopener noreferrer");
    }
    if (element.tagName === "IMG") {
      const source = element.getAttribute("src") ?? "";
      if (!source.startsWith("https://") && !source.startsWith("/local/api/")) element.remove();
    }
  });
  return documentValue.body.innerHTML;
}

const COMMON_WORK_METHODS: WorkMethodOption[] = [
  { id: "observation-only", label: "確認・観察のみ", method_type: "observation", material_name: "", registration_number: "", purpose: "状態を確認して記録する", application_method: "対象と前回記録を比較する", amount_or_rate: "", procedure_steps: ["対象を観察する", "前回からの変化を記録する"], completion_checks: ["必要な写真とメモを残した"], precautions: [], frequency: { mode: "as_needed", min_interval_days: null, preferred_interval_days: null, max_interval_days: null, max_applications: null, basis: "作業規則と現在の状態で判断する" }, instructions: "", follow_up_days_default: null, source_name: "", source_url: "", source_checked_at: "" },
];

const WORK_METHOD_TYPE_OPTIONS: Array<{ value: WorkMethodType; label: string }> = [
  { value: "manual", label: "手作業" },
  { value: "device", label: "設備・デバイス" },
  { value: "material_application", label: "肥料・資材" },
  { value: "chemical", label: "農薬" },
  { value: "physical", label: "物理的な対処" },
  { value: "biological", label: "生物的な対処" },
  { value: "cultural", label: "栽培管理による対処" },
  { value: "observation", label: "確認・観察のみ" },
  { value: "other", label: "その他" },
];

function defaultCustomMethodType(actionType: string): WorkMethodType {
  if (actionType === "fertilization" || actionType === "gibberellin_treatment") return "material_application";
  if (actionType === "watering") return "device";
  if (actionType === "pest_control") return "chemical";
  if (actionType === "observation") return "observation";
  return "manual";
}

function methodUsesMaterial(methodType: WorkMethodType): boolean {
  return methodType === "material_application" || methodType === "chemical" || methodType === "biological";
}

function methodUsesAmountOrRate(methodType: WorkMethodType, actionType: string): boolean {
  return actionType === "watering" || ["device", "material_application", "chemical", "biological"].includes(methodType);
}

function recommendedFollowUpDays(method: WorkMethodOption | undefined, actionType: string): number {
  const explicit = method?.follow_up_days_default;
  if (explicit && explicit > 0) return explicit;
  const preferred = method?.frequency.preferred_interval_days;
  if (preferred && preferred > 0) return preferred;
  return ({ watering: 1, pollination: 3, harvest: 3, pest_control: 7, gibberellin_treatment: 7, repotting: 7, fertilization: 14, pruning: 14, girdling: 14 } as Record<string, number>)[actionType] ?? 7;
}

interface ActionEditFormProps {
  action: PlantCalendarAction;
  actionTypes: PlantActionTypeDefinition[];
  busy: boolean;
  onCancel: () => void;
  onSave: (payload: ActionUpdate) => Promise<void>;
}

function ActionEditForm({ action, actionTypes, busy, onCancel, onSave }: ActionEditFormProps) {
  const [title, setTitle] = useState(action.title);
  const [actionType, setActionType] = useState(action.action_type);
  const [priority, setPriority] = useState<PlantActionPriority>(action.priority);
  const [windowStart, setWindowStart] = useState(action.window_start);
  const [windowEnd, setWindowEnd] = useState(action.window_end);
  const [reason, setReason] = useState(action.reason);
  const [instructions, setInstructions] = useState(action.instructions);
  const [instructionsHtml, setInstructionsHtml] = useState(action.instructions_html ?? "");
  const [images, setImages] = useState<File[]>([]);
  const [tags, setTags] = useState(action.tags.join(", "));
  const [requiredPeople, setRequiredPeople] = useState(action.required_people);
  const [estimatedMinutes, setEstimatedMinutes] = useState(action.estimated_minutes);
  const [useAsGuidance, setUseAsGuidance] = useState(true);
  const [localError, setLocalError] = useState("");
  const blockingReasons = [
    ...(!title.trim() ? ["作業名を入力してください"] : []),
    ...(!windowStart || !windowEnd ? ["開始日と終了日を選択してください"] : []),
    ...(windowStart && windowEnd && windowEnd < windowStart ? ["終了日を開始日以降にしてください"] : []),
    ...(!Number.isInteger(requiredPeople) || requiredPeople < 1 || requiredPeople > 100 ? ["必要人数は1〜100人の整数で入力してください"] : []),
    ...(!Number.isInteger(estimatedMinutes) || estimatedMinutes < 1 || estimatedMinutes > 1440 ? ["見積時間は1〜1440分の整数で入力してください"] : []),
    ...(busy ? ["現在の処理が完了するまでお待ちください"] : []),
  ];

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setLocalError("");
    try {
      await onSave({
        title,
        action_type: actionType,
        priority,
        window_start: windowStart,
        window_end: windowEnd,
        reason,
        instructions,
        instructions_html: instructionsHtml,
        images,
        tags: tags.split(/[,、\n]/).map((tag) => tag.trim()).filter(Boolean),
        required_people: requiredPeople,
        estimated_minutes: estimatedMinutes,
        use_as_guidance: useAsGuidance,
      });
    } catch (caught) {
      setLocalError(errorMessage(caught));
    }
  };

  return (
    <form className="action-edit-form" onSubmit={(event) => void save(event)}>
      <label>作業名<input required value={title} onChange={(event) => setTitle(event.target.value)} /></label>
      <div className="field-grid two">
        <ActionTypeSelect actionTypes={actionTypes} value={actionType} onChange={setActionType} />
        <PrioritySelect value={priority} onChange={setPriority} />
      </div>
      <div className="field-grid two">
        <label>開始日<input required type="date" value={windowStart} onChange={(event) => setWindowStart(event.target.value)} /></label>
        <label>終了日<input required type="date" value={windowEnd} onChange={(event) => setWindowEnd(event.target.value)} /></label>
      </div>
      <WorkloadFields
        requiredPeople={requiredPeople}
        estimatedMinutes={estimatedMinutes}
        onRequiredPeopleChange={setRequiredPeople}
        onEstimatedMinutesChange={setEstimatedMinutes}
      />
      <label>理由<textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      <label>作業の要約<textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} placeholder="カードですぐ確認できる短い説明" /></label>
      <RichActionContentField html={instructionsHtml} onHtmlChange={setInstructionsHtml} images={images} onImagesChange={setImages} />
      <label>タグ<input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="結実, 樹勢, 防除" /></label>
      <label className="guidance-check">
        <input type="checkbox" checked={useAsGuidance} onChange={(event) => setUseAsGuidance(event.target.checked)} />
        <span>この修正を同じ作物の今後の提案に反映する</span>
      </label>
      <DisabledActionReason id={`action-edit-blocked-${action.id}`} reasons={blockingReasons} prefix="変更を保存するには" />
      {localError && <p className="form-error">{localError}</p>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>キャンセル</button>
        <button type="submit" disabled={blockingReasons.length > 0} aria-describedby={blockingReasons.length > 0 ? `action-edit-blocked-${action.id}` : undefined} title={disabledActionTitle(blockingReasons)}><Save size={15} />変更を保存</button>
      </div>
    </form>
  );
}

function WorkloadFields({
  requiredPeople,
  estimatedMinutes,
  onRequiredPeopleChange,
  onEstimatedMinutesChange,
}: {
  requiredPeople: number;
  estimatedMinutes: number;
  onRequiredPeopleChange: (value: number) => void;
  onEstimatedMinutesChange: (value: number) => void;
}) {
  return (
    <div className="field-grid two">
      <label>必要人数
        <input type="number" min="1" max="100" step="1" required value={requiredPeople} onChange={(event) => onRequiredPeopleChange(Number(event.target.value))} />
      </label>
      <label>見積時間（分）
        <input type="number" min="1" max="1440" step="1" required value={estimatedMinutes} onChange={(event) => onEstimatedMinutesChange(Number(event.target.value))} />
      </label>
    </div>
  );
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}分`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours}時間${remainder}分` : `${hours}時間`;
}

function ActionTypeSelect({ actionTypes, value, onChange }: { actionTypes: PlantActionTypeDefinition[]; value: string; onChange: (value: string) => void }) {
  return (
    <label>種類
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {actionTypes.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
      </select>
    </label>
  );
}

function PrioritySelect({ value, onChange }: { value: PlantActionPriority; onChange: (value: PlantActionPriority) => void }) {
  return (
    <label>優先度
      <select value={value} onChange={(event) => onChange(event.target.value as PlantActionPriority)}>
        {Object.entries(PRIORITY_LABELS).map(([priority, label]) => <option key={priority} value={priority}>{label}</option>)}
      </select>
    </label>
  );
}
