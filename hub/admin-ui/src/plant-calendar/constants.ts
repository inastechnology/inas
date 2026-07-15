import type { PlantActionPriority, PlantActionTypeDefinition } from "../types";

export const PRIORITY_LABELS: Record<PlantActionPriority, string> = {
  required: "必須",
  should: "やった方がよい",
  recommended: "おすすめ",
  optional: "好みで",
};

export const TIMING_LABELS = {
  overdue: "期限超過",
  due: "今やる",
  upcoming: "まもなく",
} as const;

export const RATING_OPTIONS = [
  { value: 1, emoji: "😞", label: "とても悪い" },
  { value: 2, emoji: "😕", label: "悪い" },
  { value: 3, emoji: "😐", label: "普通" },
  { value: 4, emoji: "😊", label: "良い" },
  { value: 5, emoji: "😄", label: "とても良い" },
] as const;

const FALLBACK_ACTION_TYPE_ENTRIES = [
  ["fertilization", "追肥"],
  ["pest_control", "防除"],
  ["pruning", "剪定"],
  ["girdling", "環状剥皮"],
  ["pollination", "受粉・結実"],
  ["gibberellin_treatment", "ジベレリン処理"],
  ["harvest", "収穫"],
  ["repotting", "植え替え"],
  ["watering", "潅水"],
  ["observation", "観察"],
  ["winter_care", "越冬・季節管理"],
  ["other", "その他"],
] as const;

export const FALLBACK_ACTION_TYPES: PlantActionTypeDefinition[] = FALLBACK_ACTION_TYPE_ENTRIES.map(([code, label]) => ({
  code,
  label,
  todo_label: label,
  illustration_url: "",
  accent: "#6e7c73",
  keywords: [label],
}));
