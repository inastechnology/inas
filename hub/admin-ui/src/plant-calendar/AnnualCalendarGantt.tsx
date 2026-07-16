import { useState } from "react";
import { CalendarDays, RotateCcw } from "lucide-react";

import type { PlantCalendarAction } from "../types";


interface VisibleAction {
  action: PlantCalendarAction;
  left: number;
  width: number;
}

export function AnnualCalendarGantt({ actions, onActionSelect }: { actions: PlantCalendarAction[]; onActionSelect?: (action: PlantCalendarAction) => void }) {
  const currentMonth = currentMonthString();
  const [startMonth, setStartMonth] = useState(currentMonth);
  const [monthCount, setMonthCount] = useState(12);
  const { start, end, months } = calendarWindow(startMonth, monthCount);
  const duration = end.getTime() - start.getTime();
  const today = startOfToday();
  const todayLeft = today >= start && today < end ? ((today.getTime() - start.getTime()) / duration) * 100 : null;
  const visible = actions.flatMap((action): VisibleAction[] => {
    const actionStart = new Date(`${action.window_start}T00:00:00`);
    const actionEnd = new Date(`${action.window_end}T23:59:59`);
    if (actionEnd < start || actionStart >= end) return [];

    const clippedStart = Math.max(actionStart.getTime(), start.getTime());
    const clippedEnd = Math.min(actionEnd.getTime(), end.getTime());
    return [{
      action,
      left: ((clippedStart - start.getTime()) / duration) * 100,
      width: Math.max(1.2, ((clippedEnd - clippedStart) / duration) * 100),
    }];
  });

  return (
    <section className="annual-gantt" aria-label="12か月の栽培計画">
      <div className="calendar-section-heading">
        <div><CalendarDays size={17} /><strong>栽培計画の見通し</strong></div>
        <span>{visible.length}件</span>
      </div>
      <div className="gantt-period-controls" aria-label="カレンダー表示期間">
        <label>開始月<input type="month" value={startMonth} onChange={(event) => setStartMonth(event.target.value || currentMonth)} /></label>
        <label>表示期間
          <select value={monthCount} onChange={(event) => setMonthCount(Number(event.target.value))}>
            <option value="6">6か月</option>
            <option value="12">12か月</option>
            <option value="24">24か月</option>
          </select>
        </label>
        <button type="button" onClick={() => { setStartMonth(currentMonth); setMonthCount(12); }} disabled={startMonth === currentMonth && monthCount === 12} title="今月から12か月に戻す"><RotateCcw size={15} />今月に戻す</button>
        <output>{formatMonthRange(start, end)}</output>
      </div>
      <div className="gantt-scroll">
        <div className="gantt-chart" style={{ height: `${Math.max(230, visible.length * 28 + 52)}px`, minWidth: `${Math.max(680, monthCount * 56)}px` }}>
          <div className="gantt-months" style={{ gridTemplateColumns: `repeat(${monthCount}, minmax(56px, 1fr))` }}>{months.map((month) => <span key={month.key}>{month.label}</span>)}</div>
          <div className="gantt-grid" style={{ gridTemplateColumns: `repeat(${monthCount}, minmax(56px, 1fr))` }}>{months.map((month) => <span key={month.key} />)}</div>
          {todayLeft !== null && <div className="gantt-today" style={{ left: `${todayLeft}%` }}><span>今日</span></div>}
          <div className="gantt-bars">
            {visible.map(({ action, left, width }, index) => (
              <a
                key={action.id}
                href={`#calendar-action-${action.id}`}
                className={`gantt-bar ${action.priority} ${action.status}`}
                style={{ left: `${left}%`, top: `${index * 28}px`, width: `${width}%` }}
                title={`${action.title}: ${action.window_start} - ${action.window_end}`}
                onClick={(event) => {
                  if (!onActionSelect) return;
                  event.preventDefault();
                  onActionSelect(action);
                }}
              >
                <span>{action.title}</span>
              </a>
            ))}
          </div>
        </div>
      </div>
      {visible.length === 0 && <p className="gantt-empty">選択した期間に予定または実施記録はありません。</p>}
    </section>
  );
}

function calendarWindow(startMonth: string, monthCount: number) {
  const match = /^(\d{4})-(\d{2})$/.exec(startMonth);
  const start = match ? new Date(Number(match[1]), Number(match[2]) - 1, 1) : new Date();
  start.setHours(0, 0, 0, 0);
  start.setDate(1);

  const end = new Date(start);
  end.setMonth(end.getMonth() + monthCount);
  const months = Array.from({ length: monthCount }, (_, index) => {
    const value = new Date(start);
    value.setMonth(value.getMonth() + index);
    return {
      key: `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}`,
      label: `${String(value.getFullYear()).slice(-2)}/${value.getMonth() + 1}`,
    };
  });
  return { start, end, months };
}

function currentMonthString() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function startOfToday() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today;
}

function formatMonthRange(start: Date, end: Date) {
  const lastMonth = new Date(end);
  lastMonth.setMonth(lastMonth.getMonth() - 1);
  return `${start.getFullYear()}年${start.getMonth() + 1}月〜${lastMonth.getFullYear()}年${lastMonth.getMonth() + 1}月`;
}
