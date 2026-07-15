import { CalendarDays } from "lucide-react";

import type { PlantCalendarAction } from "../types";


interface VisibleAction {
  action: PlantCalendarAction;
  left: number;
  width: number;
}

export function AnnualCalendarGantt({ actions }: { actions: PlantCalendarAction[] }) {
  const { start, end, months } = calendarWindow();
  const duration = end.getTime() - start.getTime();
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
        <div><CalendarDays size={17} /><strong>12か月の見通し</strong></div>
        <span>{visible.length}件</span>
      </div>
      <div className="gantt-scroll">
        <div className="gantt-chart" style={{ height: `${Math.max(210, visible.length * 21 + 45)}px` }}>
          <div className="gantt-months">{months.map((month) => <span key={month}>{month}</span>)}</div>
          <div className="gantt-grid">{months.map((month) => <span key={month} />)}</div>
          <div className="gantt-bars">
            {visible.map(({ action, left, width }, index) => (
              <a
                key={action.id}
                href={`#calendar-action-${action.id}`}
                className={`gantt-bar ${action.priority} ${action.status}`}
                style={{ left: `${left}%`, top: `${index * 21}px`, width: `${width}%` }}
                title={`${action.title}: ${action.window_start} - ${action.window_end}`}
              >
                <span>{action.title}</span>
              </a>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function calendarWindow() {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  start.setDate(1);

  const end = new Date(start);
  end.setMonth(end.getMonth() + 12);
  const months = Array.from({ length: 12 }, (_, index) => {
    const value = new Date(start);
    value.setMonth(value.getMonth() + index);
    return `${value.getMonth() + 1}月`;
  });
  return { start, end, months };
}
