interface DisabledActionReasonProps {
  id: string;
  reasons: string[];
  prefix?: string;
}

export function DisabledActionReason({ id, reasons, prefix = "実行するには" }: DisabledActionReasonProps) {
  if (reasons.length === 0) return null;
  return (
    <p id={id} className="disabled-action-reason" role="status">
      <strong>{prefix}</strong>
      <span>{reasons.join("、")}</span>
    </p>
  );
}

export function disabledActionTitle(reasons: string[]) {
  return reasons.length > 0 ? `実行できません: ${reasons.join("、")}` : undefined;
}
