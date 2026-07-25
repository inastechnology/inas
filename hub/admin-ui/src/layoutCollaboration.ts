import type { LayoutPresenceState } from "./types";

const COLLABORATOR_COLORS = ["#0f766e", "#2563a7", "#a44f08", "#7c3aad", "#b4234d", "#08735b", "#b94717", "#4f46a5"];

export function collaboratorColor(identity: string): string {
  let hash = 0;
  for (let index = 0; index < identity.length; index += 1) hash = ((hash << 5) - hash + identity.charCodeAt(index)) | 0;
  return COLLABORATOR_COLORS[Math.abs(hash) % COLLABORATOR_COLORS.length];
}

export function collaboratorLabel(email: string): string {
  const localPart = email.trim().split("@", 1)[0] || "共同編集者";
  return localPart.length > 18 ? `${localPart.slice(0, 17)}…` : localPart;
}

export function presenceStateLabel(state: LayoutPresenceState): string {
  return {
    viewing: "閲覧中",
    editing: "編集中",
    saving: "保存中",
    conflict: "競合を確認中",
  }[state];
}
