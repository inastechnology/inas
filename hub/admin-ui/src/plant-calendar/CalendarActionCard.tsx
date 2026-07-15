import { useState, type FormEvent } from "react";
import { Check, Edit3, ImagePlus, Leaf, Plus, Save, Trash2 } from "lucide-react";

import { errorMessage, formatDate, formatDateRange, todayString } from "../formatters";
import type { PlantActionPriority, PlantActionTypeDefinition, PlantCalendarAction } from "../types";
import { PRIORITY_LABELS, RATING_OPTIONS, TIMING_LABELS } from "./constants";


type TimingState = keyof typeof TIMING_LABELS;
type ActionUpdate = Partial<PlantCalendarAction> & { use_as_guidance?: boolean };

interface CalendarActionCardProps {
  plantingId: string;
  action: PlantCalendarAction;
  actionType: PlantActionTypeDefinition;
  actionTypes: PlantActionTypeDefinition[];
  timingState?: TimingState;
  busy: boolean;
  onEdit: (plantingId: string, actionId: string, payload: ActionUpdate) => Promise<void>;
  onComplete: (plantingId: string, actionId: string, performedOn: string, note: string, rating: number, images: File[]) => Promise<void>;
  onDelete: (plantingId: string, actionId: string) => Promise<void>;
}

interface NewCalendarActionFormProps {
  actionTypes: PlantActionTypeDefinition[];
  busy: boolean;
  onCancel: () => void;
  onSave: (payload: Partial<PlantCalendarAction>) => Promise<void>;
}

export function NewCalendarActionForm({ actionTypes, busy, onCancel, onSave }: NewCalendarActionFormProps) {
  const [title, setTitle] = useState("");
  const [actionType, setActionType] = useState("observation");
  const [priority, setPriority] = useState<PlantActionPriority>("recommended");
  const [start, setStart] = useState(todayString());
  const [end, setEnd] = useState(todayString());
  const [reason, setReason] = useState("");
  const [instructions, setInstructions] = useState("");

  const save = (event: FormEvent) => {
    event.preventDefault();
    void onSave({
      title,
      action_type: actionType,
      priority,
      window_start: start,
      window_end: end,
      reason,
      instructions,
      tags: [],
    });
  };

  return (
    <form className="action-edit-form new-action-form" onSubmit={save}>
      <strong>手動で作業を追加</strong>
      <label>作業名<input required value={title} onChange={(event) => setTitle(event.target.value)} /></label>
      <div className="field-grid two">
        <ActionTypeSelect actionTypes={actionTypes} value={actionType} onChange={setActionType} />
        <PrioritySelect value={priority} onChange={setPriority} />
      </div>
      <div className="field-grid two">
        <label>開始日<input type="date" required value={start} onChange={(event) => setStart(event.target.value)} /></label>
        <label>終了日<input type="date" required value={end} onChange={(event) => setEnd(event.target.value)} /></label>
      </div>
      <label>理由<textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      <label>作業内容<textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} /></label>
      <div className="form-actions">
        <button type="button" onClick={onCancel}>キャンセル</button>
        <button type="submit" disabled={busy || !title.trim()}><Plus size={15} />追加</button>
      </div>
    </form>
  );
}

export function CalendarActionCard({
  plantingId,
  action,
  actionType,
  actionTypes,
  timingState,
  busy,
  onEdit,
  onComplete,
  onDelete,
}: CalendarActionCardProps) {
  const [editing, setEditing] = useState(false);
  const [recording, setRecording] = useState(false);

  return (
    <article
      className={`calendar-action ${action.status}`}
      id={`calendar-action-${action.id}`}
      style={{ borderLeftColor: actionType.accent }}
    >
      <ActionStatusLine action={action} timingState={timingState} />
      <div className="action-main">
        <ActionIllustration actionType={actionType} />
        <div className="action-copy">
          <div className="action-heading">
            <div><small>{actionType.label}</small><h3>{action.title}</h3></div>
            <div className="action-row-tools">
              <button type="button" className="action-icon-button" onClick={() => setEditing((value) => !value)} title="作業を編集"><Edit3 size={16} /></button>
              {action.status !== "completed" && (
                <button type="button" className="action-icon-button danger" onClick={() => void onDelete(plantingId, action.id)} title="作業を削除"><Trash2 size={16} /></button>
              )}
            </div>
          </div>
          {action.timing_label && <p className="timing-label">{action.timing_label}</p>}
          <dl className="action-detail">
            <dt>理由</dt><dd>{action.reason || "未設定"}</dd>
            <dt>作業</dt><dd>{action.instructions || "未設定"}</dd>
          </dl>
          {action.tags.length > 0 && <div className="action-tags">{action.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
        </div>
      </div>

      {action.completion && <CompletionRecord action={action} />}
      {editing && (
        <ActionEditForm
          action={action}
          actionTypes={actionTypes}
          busy={busy}
          onCancel={() => setEditing(false)}
          onSave={async (payload) => {
            await onEdit(plantingId, action.id, payload);
            setEditing(false);
          }}
        />
      )}
      {action.status === "planned" && !editing && (
        recording ? (
          <WorkRecordForm
            plantingId={plantingId}
            actionId={action.id}
            busy={busy}
            onCancel={() => setRecording(false)}
            onComplete={async (...args) => {
              await onComplete(...args);
              setRecording(false);
            }}
          />
        ) : (
          <button type="button" className="complete-button" onClick={() => setRecording(true)}><Check size={16} />実施を記録</button>
        )
      )}
    </article>
  );
}

function ActionStatusLine({ action, timingState }: { action: PlantCalendarAction; timingState?: TimingState }) {
  return (
    <div className="action-topline">
      <span className={`priority-badge ${action.priority}`}>{PRIORITY_LABELS[action.priority]}</span>
      {timingState && <span className={`timing-badge ${timingState}`}>{TIMING_LABELS[timingState]}</span>}
      {action.status === "completed" && <span className="completed-badge"><Check size={13} />実施済み</span>}
      {action.status === "skipped" && <span className="skipped-badge">見送り</span>}
      <time>{formatDateRange(action.window_start, action.window_end)}</time>
    </div>
  );
}

function ActionIllustration({ actionType }: { actionType: PlantActionTypeDefinition }) {
  if (!actionType.illustration_url) {
    return <div className="action-illustration-fallback" aria-hidden="true"><Leaf size={28} /></div>;
  }
  return <img className="action-illustration" src={actionType.illustration_url} alt={`${actionType.label}の作業イラスト`} loading="lazy" />;
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
      {Boolean(completion.attachments?.length) && (
        <div className="completion-images">
          {completion.attachments?.map((attachment) => (
            <a key={attachment.id} href={attachment.url} target="_blank" rel="noreferrer">
              <img src={attachment.url} alt={attachment.original_filename || "作業記録画像"} loading="lazy" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

interface WorkRecordFormProps {
  plantingId: string;
  actionId: string;
  busy: boolean;
  onCancel: () => void;
  onComplete: CalendarActionCardProps["onComplete"];
}

function WorkRecordForm({ plantingId, actionId, busy, onCancel, onComplete }: WorkRecordFormProps) {
  const [performedOn, setPerformedOn] = useState(todayString());
  const [note, setNote] = useState("");
  const [rating, setRating] = useState<number | null>(null);
  const [images, setImages] = useState<File[]>([]);
  const [localError, setLocalError] = useState("");

  const complete = async (event: FormEvent) => {
    event.preventDefault();
    setLocalError("");
    if (rating === null) {
      setLocalError("評価を選択してください。");
      return;
    }
    try {
      await onComplete(plantingId, actionId, performedOn, note, rating, images);
    } catch (caught) {
      setLocalError(errorMessage(caught));
    }
  };

  return (
    <form className="work-record-form" onSubmit={(event) => void complete(event)}>
      <label>実施日<input type="date" required value={performedOn} onChange={(event) => setPerformedOn(event.target.value)} /></label>
      <label>メモ<input value={note} onChange={(event) => setNote(event.target.value)} placeholder="使用量、状態など（任意）" /></label>
      <fieldset className="work-rating">
        <legend>評価</legend>
        <div>
          {RATING_OPTIONS.map((option) => (
            <label key={option.value} title={option.label}>
              <input type="radio" name={`rating-${actionId}`} value={option.value} checked={rating === option.value} onChange={() => setRating(option.value)} />
              <span aria-hidden="true">{option.emoji}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <label className="image-input">
        <span><ImagePlus size={15} />画像</span>
        <input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => setImages(Array.from(event.target.files ?? []).slice(0, 5))} />
      </label>
      {localError && <p className="form-error">{localError}</p>}
      <div>
        <button type="button" onClick={onCancel}>戻る</button>
        <button type="submit" disabled={busy}><Check size={15} />この日付で記録</button>
      </div>
    </form>
  );
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
  const [tags, setTags] = useState(action.tags.join(", "));
  const [useAsGuidance, setUseAsGuidance] = useState(true);
  const [localError, setLocalError] = useState("");

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
        tags: tags.split(/[,、\n]/).map((tag) => tag.trim()).filter(Boolean),
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
      <label>理由<textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      <label>作業内容<textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} /></label>
      <label>タグ<input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="結実, 樹勢, 防除" /></label>
      <label className="guidance-check">
        <input type="checkbox" checked={useAsGuidance} onChange={(event) => setUseAsGuidance(event.target.checked)} />
        <span>この修正を同じ作物の今後の提案に反映する</span>
      </label>
      {localError && <p className="form-error">{localError}</p>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>キャンセル</button>
        <button type="submit" disabled={busy}><Save size={15} />変更を保存</button>
      </div>
    </form>
  );
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
