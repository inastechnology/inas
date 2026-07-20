interface LoadingStateProps {
  label: string;
  detail?: string;
}

interface ActivityIndicatorProps {
  size?: "small" | "medium" | "large";
}

export function ActivityIndicator({ size = "medium" }: ActivityIndicatorProps) {
  return (
    <span className={`inas-activity ${size}`} aria-hidden="true">
      <span className="inas-activity-field" />
      <span className="inas-activity-sprout" />
    </span>
  );
}

export function LoadingState({ label, detail = "栽培データと接続状態を整えています" }: LoadingStateProps) {
  return (
    <div className="layout-state inas-loading-state" role="status" aria-live="polite" aria-busy="true">
      <ActivityIndicator size="large" />
      <div className="inas-loading-copy">
        <strong>{label}</strong>
        <span>{detail}</span>
      </div>
      <span className="inas-loading-signal" aria-hidden="true"><i /><i /><i /></span>
    </div>
  );
}

export function InlineLoading({ label }: { label: string }) {
  return (
    <span className="inas-inline-loading" role="status" aria-live="polite" aria-busy="true">
      <ActivityIndicator size="small" />
      <span>{label}</span>
    </span>
  );
}
