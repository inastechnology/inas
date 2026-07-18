import {
  Activity,
  AirVent,
  Box,
  Camera,
  Cpu,
  Database,
  Droplets,
  Fan,
  LampCeiling,
  LandPlot,
  Minus,
  ShowerHead,
  Sprout,
  SunDim,
  TreePine,
  Warehouse,
  Waves,
  type LucideIcon,
} from "lucide-react";

import type { PlacementPreset, SpaceType } from "./types";

export interface PresetDefinition {
  id: PlacementPreset;
  label: string;
  group: "空間" | "培地" | "設備";
  icon: LucideIcon;
  width: number;
  height: number;
  fill: string;
  stroke: string;
  childSpaceType?: SpaceType;
  keywords: string[];
  paletteVisible?: boolean;
}

export const PRESETS: PresetDefinition[] = [
  { id: "greenhouse", label: "ハウス", group: "空間", icon: Warehouse, width: 16, height: 9, fill: "#dff4e8", stroke: "#398260", childSpaceType: "greenhouse", keywords: ["温室", "ビニールハウス", "施設"] },
  { id: "open_field", label: "露地エリア", group: "空間", icon: LandPlot, width: 16, height: 10, fill: "#e8efd2", stroke: "#788d35", childSpaceType: "open_field", keywords: ["屋外", "畑", "路地"] },
  { id: "shade_area", label: "日陰エリア", group: "空間", icon: SunDim, width: 8, height: 6, fill: "#dce5dc", stroke: "#687d6d", childSpaceType: "shade", keywords: ["軒下", "軒先", "半日陰", "遮光", "シェード"] },
  { id: "ridge", label: "畝", group: "培地", icon: Sprout, width: 8, height: 2, fill: "#d8c5a0", stroke: "#8b7044", keywords: ["うね", "ベッド", "土耕"] },
  { id: "tree", label: "植木", group: "培地", icon: TreePine, width: 3, height: 3, fill: "#d7edcf", stroke: "#4e7b43", keywords: ["樹木", "果樹", "庭木", "地植え"] },
  { id: "pot", label: "植木鉢", group: "培地", icon: Box, width: 2, height: 2, fill: "#efdbc5", stroke: "#9b6745", keywords: ["鉢植え", "ポット", "プランター", "コンテナ"] },
  { id: "hydroponic_bed", label: "水耕ベッド", group: "培地", icon: Waves, width: 8, height: 3, fill: "#d9edf4", stroke: "#3f7f94", childSpaceType: "hydroponic", keywords: ["養液", "NFT", "DWC", "水耕栽培"] },
  { id: "watering_device", label: "潅水機", group: "設備", icon: Droplets, width: 2, height: 2, fill: "#cfe9ee", stroke: "#197082", keywords: ["灌水", "水やり", "WTR", "WRS", "ポンプ", "バルブ"] },
  { id: "sensor", label: "センサー", group: "設備", icon: Activity, width: 2, height: 2, fill: "#f5e8b8", stroke: "#947927", keywords: ["計測", "測定", "土壌水分", "EC", "pH", "PAR", "温湿度"] },
  { id: "camera", label: "カメラ", group: "設備", icon: Camera, width: 2, height: 2, fill: "#e8ddf2", stroke: "#6f4b87", keywords: ["監視", "映像", "撮影", "定点", "Reolink", "Tapo", "RTSP"] },
  { id: "grow_light", label: "植物育成ライト", group: "設備", icon: LampCeiling, width: 3, height: 2, fill: "#fff1b8", stroke: "#9a7921", keywords: ["生育ライト", "LED", "補光", "照明", "ランプ"] },
  { id: "mister", label: "噴霧器", group: "設備", icon: ShowerHead, width: 2, height: 2, fill: "#d8edf2", stroke: "#397b88", keywords: ["ミスト", "霧", "散水", "加湿"] },
  { id: "fan", label: "送風機", group: "設備", icon: Fan, width: 2, height: 2, fill: "#e4ece8", stroke: "#537469", keywords: ["扇風機", "サーキュレーター", "換気", "ファン"] },
  { id: "hvac", label: "空調", group: "設備", icon: AirVent, width: 3, height: 2, fill: "#e4e8ef", stroke: "#596a80", keywords: ["エアコン", "冷房", "暖房", "除湿", "空調機"] },
  { id: "irrigation_line", label: "配管（既存データ）", group: "設備", icon: Minus, width: 8, height: 1, fill: "#c9e6f0", stroke: "#287a96", keywords: ["ホース", "チューブ", "パイプ", "水道", "物理経路"], paletteVisible: false },
  { id: "tank", label: "タンク", group: "設備", icon: Database, width: 3, height: 3, fill: "#dbe6ef", stroke: "#526f86", keywords: ["貯水", "液肥", "養液槽", "水槽"] },
];

export const PRESET_BY_ID = Object.fromEntries(PRESETS.map((preset) => [preset.id, preset])) as Record<PlacementPreset, PresetDefinition>;

export const SPACE_TYPE_LABELS: Record<SpaceType, string> = {
  field: "圃場",
  open_field: "露地",
  greenhouse: "ハウス内",
  indoor: "屋内",
  hydroponic: "水耕設備内",
  shade: "日陰・軒下",
};

export const DEVICE_KIND_ICONS = { Cpu };
