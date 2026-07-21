import type { ReactNode } from "react";

interface HelpDisclosureProps {
  title: string;
  children: ReactNode;
  align?: "left" | "right";
  compact?: boolean;
}

export function HelpDisclosure({ title, children, align = "right", compact = false }: HelpDisclosureProps) {
  return (
    <details className={`context-help ${align === "left" ? "left" : ""} ${compact ? "compact" : ""}`.trim()}>
      <summary aria-label={`${title}の説明を開く`} title={`${title}の説明`}>?</summary>
      <div className="context-help-panel" role="note">
        <strong>{title}</strong>
        <div>{children}</div>
      </div>
    </details>
  );
}
