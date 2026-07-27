import { useState } from "react";
import { ArrowLeft, Check, ChevronDown, Info, Map as MapIcon, Play, Plus, Route, StickyNote, Trash2 } from "lucide-react";

import { answerWorkRouteStep, createWorkRoute, deleteWorkRoute, rewindWorkRouteStep, startWorkRoute } from "../api";
import { errorMessage } from "../formatters";
import type { GuidedWorkRoute, GuidedWorkRouteRun, GuidedWorkRouteStep, GuidedWorkStepType, Planting } from "../types";

const STEP_TYPES: Array<{ value: GuidedWorkStepType; label: string }> = [
  { value: "observe", label: "観察する" },
  { value: "measure", label: "測定する" },
  { value: "decide", label: "判断する" },
  { value: "prepare", label: "準備する" },
  { value: "perform", label: "実施する" },
  { value: "wait", label: "待つ" },
  { value: "verify", label: "確かめる" },
];

function newStep(index: number): GuidedWorkRouteStep {
  return {
    id: `step-${crypto.randomUUID()}`,
    type: index === 0 ? "observe" : "perform",
    title: "",
    description: "",
    prompt: "",
    metric: "",
    unit: "",
    instructions: "",
    next_step_id: "",
    missing_step_id: "",
    choices: [],
  };
}

function StepPictogram({ type, size = "normal" }: { type: GuidedWorkStepType; size?: "normal" | "large" }) {
  return (
    <span className={`route-step-pictogram ${type} ${size}`} aria-hidden="true">
      <img src={`/static/work-route-pictograms/${type}.png`} alt="" />
    </span>
  );
}

interface GuidedWorkRoutesPanelProps {
  plantings: Planting[];
  routes: GuidedWorkRoute[];
  runs: GuidedWorkRouteRun[];
  busy: boolean;
  actionId: string;
  actionTitle: string;
  plantingId: string;
  onChanged: (preferredPlantingId?: string) => Promise<unknown>;
}

export function GuidedWorkRoutesPanel({ plantings, routes, runs, busy, actionId, actionTitle, plantingId: initialPlantingId, onChanged }: GuidedWorkRoutesPanelProps) {
  const [creating, setCreating] = useState(false);
  const [plantingId] = useState(initialPlantingId);
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [dependencyRouteId, setDependencyRouteId] = useState("");
  const [steps, setSteps] = useState<GuidedWorkRouteStep[]>([newStep(0), newStep(1)]);
  const [activeRouteId, setActiveRouteId] = useState("");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const scopedRoutes = routes.filter((route) => route.action_id === actionId);
  const activeRuns = new Map(runs.filter((run) => run.status === "in_progress").map((run) => [run.route_id, run]));
  const primaryRoute = scopedRoutes.find((route) => route.status === "active");
  const primaryRun = primaryRoute ? activeRuns.get(primaryRoute.id) : undefined;

  const resetForm = () => {
    setTitle("");
    setSummary("");
    setDependencyRouteId("");
    setSteps([newStep(0), newStep(1)]);
    setCreating(false);
  };

  const updateStep = (id: string, patch: Partial<GuidedWorkRouteStep>) => {
    setSteps((current) => current.map((step) => {
      if (step.id !== id) return step;
      const next = { ...step, ...patch };
      if (patch.type === "decide" && next.choices.length < 2) {
        next.choices = [
          { id: `choice-${crypto.randomUUID()}`, label: "はい", next_step_id: "" },
          { id: `choice-${crypto.randomUUID()}`, label: "いいえ", next_step_id: "" },
        ];
      }
      return next;
    }));
  };

  const save = async () => {
    setError("");
    setWorking(true);
    try {
      const linkedSteps = steps.map((step, index) => ({
        ...step,
        next_step_id: step.type === "decide" ? "" : (step.next_step_id || steps[index + 1]?.id || ""),
      }));
      await createWorkRoute(plantingId, {
        action_id: actionId,
        title,
        summary,
        entry_step_id: linkedSteps[0]?.id,
        steps: linkedSteps,
        dependencies: dependencyRouteId
          ? [{ route_id: dependencyRouteId, type: "completed", min_days: 0, label: "先の案内ルートを完了してください" }]
          : [],
      });
      resetForm();
      await onChanged(plantingId);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  };

  const start = async (route: GuidedWorkRoute) => {
    setWorking(true);
    setError("");
    try {
      await startWorkRoute(route.planting_id, route.id);
      setActiveRouteId(route.id);
      await onChanged(route.planting_id);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  };

  const answer = async (route: GuidedWorkRoute, run: GuidedWorkRouteRun, payload: Record<string, string>) => {
    setWorking(true);
    setError("");
    try {
      await answerWorkRouteStep(route.planting_id, run.id, run.current_step_id, { ...payload, value, note, source: "manual" });
      setValue("");
      setNote("");
      await onChanged(route.planting_id);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  };

  const rewind = async (route: GuidedWorkRoute, run: GuidedWorkRouteRun) => {
    setWorking(true);
    setError("");
    try {
      await rewindWorkRouteStep(route.planting_id, run.id);
      setValue("");
      setNote("");
      await onChanged(route.planting_id);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  };

  return (
    <section className="guided-routes" aria-labelledby="guided-routes-title">
      <header className="guided-routes-heading">
        <div>
          <span className="guided-routes-icon"><MapIcon size={22} /></span>
          <div><small>「{actionTitle}」の進め方</small><h2 id="guided-routes-title">作業案内ルート</h2><p>判断・測定・実施をつなぎ、現場では「今やること」だけを案内します。</p></div>
        </div>
        {primaryRoute ? (
          <button
            type="button"
            className="primary route-start-primary"
            onClick={() => primaryRun ? setActiveRouteId(primaryRoute.id) : void start(primaryRoute)}
            disabled={busy || working || (!primaryRun && primaryRoute.start_blockers.length > 0)}
          ><Play size={17} />{primaryRun ? "作業を続ける" : "作業をはじめる"}</button>
        ) : (
          <button type="button" className="primary" onClick={() => setCreating(true)} disabled={busy || working}><Plus size={16} />案内ルートを登録</button>
        )}
      </header>

      {error && <p className="form-error" role="alert">{error}</p>}

      {creating && (
        <div className="route-builder">
          <header><div><small>新しい道順</small><h3>案内ルートを組み立てる</h3></div><button type="button" onClick={resetForm}>閉じる</button></header>
          <div className="route-builder-basics">
            <label>対象の作物<select value={plantingId} disabled>{plantings.filter((planting) => planting.id === plantingId).map((planting) => <option key={planting.id} value={planting.id}>{planting.placement_name} / {planting.crop_name}</option>)}</select></label>
            <label>ルート名<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例：施肥が必要か判断して実施する" /></label>
            <label className="wide">目的とゴール<textarea value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="どの状態を目指すルートか、現場の言葉で書きます" /></label>
            <label className="wide">先に終えるルート<select value={dependencyRouteId} onChange={(event) => setDependencyRouteId(event.target.value)}><option value="">なし — いつでも開始できる</option>{scopedRoutes.map((route) => <option key={route.id} value={route.id}>{route.title}</option>)}</select></label>
          </div>
          <div className="route-builder-path">
            {steps.map((step, index) => (
              <article className="route-builder-step" key={step.id}>
                <span className="route-step-number">{index + 1}</span>
                <div className="route-builder-step-body">
                  <div className="route-builder-step-top">
                    <label>この地点ですること<select value={step.type} onChange={(event) => updateStep(step.id, { type: event.target.value as GuidedWorkStepType })}>{STEP_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}</select></label>
                    <label>短い見出し<input value={step.title} onChange={(event) => updateStep(step.id, { title: event.target.value })} placeholder="例：土壌の状態を確認" /></label>
                    {steps.length > 1 && <button type="button" className="icon-button" onClick={() => setSteps((current) => current.filter((item) => item.id !== step.id))} aria-label="この地点を削除"><Trash2 size={16} /></button>}
                  </div>
                  <label>現場への案内<textarea value={step.description} onChange={(event) => updateStep(step.id, { description: event.target.value })} placeholder="何を見て、どう動けばよいかを簡潔に" /></label>
                  {step.type === "measure" && <>
                    <label>確認する値<input value={step.metric} onChange={(event) => updateStep(step.id, { metric: event.target.value })} placeholder="例：土壌EC、土壌水分" /></label>
                    <label>単位<input value={step.unit} onChange={(event) => updateStep(step.id, { unit: event.target.value })} placeholder="例：µS/cm、%" /></label>
                    <label>値を取得できない場合<select value={step.missing_step_id} onChange={(event) => updateStep(step.id, { missing_step_id: event.target.value })}><option value="">退避先を選択</option>{steps.filter((item) => item.id !== step.id).map((item) => <option key={item.id} value={item.id}>{item.title || "未入力の地点"}</option>)}</select></label>
                  </>}
                  {step.type === "decide" && <div className="route-choice-editor"><span>答えと行き先</span>{step.choices.map((choice) => <div key={choice.id}><input value={choice.label} onChange={(event) => updateStep(step.id, { choices: step.choices.map((item) => item.id === choice.id ? { ...item, label: event.target.value } : item) })} /><ChevronDown size={14} /><select value={choice.next_step_id} onChange={(event) => updateStep(step.id, { choices: step.choices.map((item) => item.id === choice.id ? { ...item, next_step_id: event.target.value } : item) })}><option value="">ここで終了</option>{steps.filter((item) => item.id !== step.id).map((item) => <option key={item.id} value={item.id}>{item.title || "未入力の地点"}</option>)}</select></div>)}</div>}
                </div>
                {index < steps.length - 1 && <span className="route-path-line" aria-hidden="true" />}
              </article>
            ))}
          </div>
          <button type="button" className="route-add-step" onClick={() => setSteps((current) => [...current, newStep(current.length)])}><Plus size={16} />道順を追加</button>
          <div className="form-actions"><button type="button" onClick={resetForm}>キャンセル</button><button type="button" className="primary" disabled={!title.trim() || steps.some((step) => !step.title.trim()) || working} onClick={() => void save()}><Route size={16} />この案内ルートを登録</button></div>
        </div>
      )}

      {!creating && scopedRoutes.length === 0 && <div className="guided-routes-empty"><Route size={34} /><strong>この作業の案内ルートはまだありません</strong><p>「何を確かめ、どう判断し、何をするか」をひとつの道順として登録します。</p><button type="button" onClick={() => setCreating(true)}><Plus size={16} />案内ルートを作る</button></div>}

      <div className="guided-route-list">
        {scopedRoutes.filter((route) => route.status === "active").map((route) => {
          const planting = plantings.find((item) => item.id === route.planting_id);
          const run = activeRuns.get(route.id);
          const currentStep = run ? route.steps.find((step) => step.id === run.current_step_id) : null;
          const open = activeRouteId === route.id || Boolean(run);
          return (
            <article className={`guided-route-card${open ? " active" : ""}`} key={route.id}>
              {!run && <header onClick={() => setActiveRouteId(open ? "" : route.id)}>
                <span className="guided-route-marker"><Route size={19} /></span>
                <div><small>{planting?.placement_name} / {planting?.crop_name}</small><h3>{route.title}</h3><p>{route.summary}</p></div>
                <span className="guided-route-count">{route.steps.length}地点</span>
              </header>}
              {open && <div className="guided-route-body">
                {!run ? <>
                  <div className="route-quest-banner"><span>作業の流れ</span><strong>全{route.steps.length}段階</strong></div>
                  <ol className="route-preview">{route.steps.map((step, index) => <li key={step.id}><StepPictogram type={step.type} /><div><small>{index + 1}. {STEP_TYPES.find((item) => item.value === step.type)?.label}</small><strong>{step.title}</strong>{step.type === "measure" && step.unit && <em>{step.unit}</em>}</div></li>)}</ol>
                  {route.start_blockers.length > 0 && <div className="route-blockers">{route.start_blockers.map((blocker) => <p key={blocker}>{blocker}</p>)}</div>}
                  <details className="route-supplement">
                    <summary><Info size={16} />この作業の補足を見る</summary>
                    <p>{route.summary || "登録された補足はありません。"}</p>
                    <button type="button" className="danger-quiet" disabled={working} onClick={async () => { if (!window.confirm("この案内ルートを削除しますか？")) return; await deleteWorkRoute(route.planting_id, route.id); await onChanged(route.planting_id); }}><Trash2 size={15} />案内ルートを削除</button>
                  </details>
                </> : currentStep ? <>
                  <div className="route-run-hud">
                    <div><span>進捗</span><strong>{run.history.length}<small> / {route.steps.length}</small></strong></div>
                    <div className="route-progress"><span style={{ width: `${Math.min(100, (run.history.length / route.steps.length) * 100)}%` }} /></div>
                    <span className="route-xp">{Math.round((run.history.length / route.steps.length) * 100)}%</span>
                  </div>
                  {run.history.length > 0 && (
                    <section className="route-flow-history" aria-label="通過した作業地点">
                      <header><Check size={16} /><strong>ここまでの流れ</strong><span>{run.history.length}地点を通過</span></header>
                      <ol>
                        {run.history.map((item, index) => {
                          const historyStep = route.steps.find((step) => step.id === item.step_id);
                          const selectedChoice = historyStep?.choices.find((choice) => choice.id === item.choice_id);
                          return (
                            <li key={`${item.step_id}-${item.completed_at}`}>
                              <StepPictogram type={item.step_type} />
                              <div className="route-history-copy">
                                <small>{index + 1}. {STEP_TYPES.find((type) => type.value === item.step_type)?.label}</small>
                                <strong>{item.title}</strong>
                                {(item.value || selectedChoice) && (
                                  <span className="route-history-result">
                                    {item.value && <b>{item.value}{historyStep?.unit ? ` ${historyStep.unit}` : ""}</b>}
                                    {selectedChoice && <b>{selectedChoice.label}</b>}
                                  </span>
                                )}
                                {item.note && <p>{item.note}</p>}
                              </div>
                              <span className="route-history-check"><Check size={14} /></span>
                            </li>
                          );
                        })}
                      </ol>
                    </section>
                  )}
                  <section className="route-current-step">
                    <div className="route-current-badge">現在のステップ · {run.history.length + 1}地点目</div>
                    <StepPictogram type={currentStep.type} size="large" />
                    <small>いま行うこと · {STEP_TYPES.find((item) => item.value === currentStep.type)?.label}</small>
                    <h4>{currentStep.title}</h4>
                    {currentStep.description && <div className="route-current-guidance"><Info size={17} /><p>{currentStep.description}</p></div>}
                    {currentStep.type === "measure" && <label>確認した値<span className="route-measurement-input"><input type="number" step="any" inputMode="decimal" value={value} onChange={(event) => setValue(event.target.value)} placeholder="数値を入力" />{currentStep.unit && <b>{currentStep.unit}</b>}</span></label>}
                    <details className="route-supplement current route-note">
                      <summary><StickyNote size={16} />今回の作業メモを残す</summary>
                      <label>メモ（任意）<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="気づいたことを短く残せます" /></label>
                    </details>
                    <div className="route-current-actions">
                      {run.history.length > 0 && <button type="button" className="route-rewind" disabled={working} onClick={() => void rewind(route, run)}><ArrowLeft size={16} />前のステップへ戻る</button>}
                      {currentStep.type === "decide"
                        ? currentStep.choices.map((choice) => <button type="button" key={choice.id} disabled={working} onClick={() => void answer(route, run, { outcome: "decided", choice_id: choice.id })}>{choice.label}<ChevronDown size={14} /></button>)
                        : <>
                          {currentStep.type === "measure" && currentStep.missing_step_id && <button type="button" disabled={working} onClick={() => void answer(route, run, { outcome: "missing" })}>値が取れない</button>}
                          <button type="button" className="primary route-complete-mission" disabled={working || (currentStep.type === "measure" && value === "")} onClick={() => void answer(route, run, { outcome: "completed" })}>完了して次へ</button>
                        </>}
                    </div>
                  </section>
                </> : null}
              </div>}
            </article>
          );
        })}
      </div>
    </section>
  );
}
