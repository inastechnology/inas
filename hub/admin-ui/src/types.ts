export type SpaceType = "field" | "open_field" | "greenhouse" | "indoor" | "hydroponic" | "shade";

export type PlacementPreset =
  | "greenhouse"
  | "open_field"
  | "shade_area"
  | "ridge"
  | "tree"
  | "pot"
  | "hydroponic_bed"
  | "watering_device"
  | "sensor"
  | "irrigation_line"
  | "tank"
  | "grow_light"
  | "mister"
  | "fan"
  | "hvac";

export type BindingResourceType = "device" | "mosfet_switch" | "sensor" | "camera";

export interface DeviceBinding {
  device_id: string;
  resource_type: BindingResourceType;
  resource_id: string;
  target_placement_ids: string[];
}

export interface Placement {
  id: string;
  preset: PlacementPreset;
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: 0 | 90 | 180 | 270;
  z: number;
  child_space_id: string;
  binding: DeviceBinding | null;
  memo: string;
}

export interface LayoutSpace {
  id: string;
  name: string;
  space_type: SpaceType;
  north_angle_deg: number;
  grid: {
    columns: number;
    rows: number;
    cell_size_m: number;
  };
  placements: Placement[];
}

export interface FieldLayout {
  schema_version: number;
  id: string;
  field_id: string;
  name: string;
  root_space_id: string;
  spaces: LayoutSpace[];
  revision: number;
  updated_at: string;
}

export interface DeviceResource {
  resource_type: BindingResourceType;
  resource_id: string;
  name: string;
}

export interface LayoutDevice {
  id: string;
  name: string;
  device_kind: string;
  state: string;
  location: string;
  kind_label: string;
  group_label: string;
  assigned_field_id: string;
  resources: DeviceResource[];
}

export interface GrowthTarget {
  min: number | null;
  max: number | null;
}

export type PlantActionPriority = "required" | "should" | "recommended" | "optional";
export type PlantActionStatus = "planned" | "completed" | "skipped";

export interface PlantActionTypeDefinition {
  code: string;
  label: string;
  todo_label: string;
  illustration_url: string;
  accent: string;
  keywords: string[];
}

export interface RecordImageAttachment {
  id: string;
  storage: "r2";
  content_type: string;
  size_bytes: number;
  original_filename: string;
  url: string;
}

export interface Planting {
  id: string;
  field_id: string;
  space_id: string;
  placement_id: string;
  placement_name: string;
  crop_name: string;
  cultivar: string;
  crop_category: "vegetable" | "fruit_tree" | "flower" | "herb" | "other";
  tree_age_years: number | null;
  planted_on: string;
  plant_count: number;
  cultivation_method: string;
  conditions: {
    environment: string;
    soil_or_substrate: string;
    region: string;
    sunlight: string;
    notes: string;
  };
  growth_targets: Record<string, GrowthTarget>;
  memo: string;
  status: "active" | "harvested" | "removed";
  calendar_id: string;
  created_at: string;
  updated_at: string;
}

export interface PlantCalendarAction {
  id: string;
  action_type: string;
  title: string;
  priority: PlantActionPriority;
  window_start: string;
  window_end: string;
  timing_label: string;
  reason: string;
  instructions: string;
  tags: string[];
  status: PlantActionStatus;
  completion: {
    work_log_id: string;
    performed_on: string;
    note: string;
    rating?: number | null;
    attachments?: RecordImageAttachment[];
  } | null;
  source: string;
  rule_id: string;
}

export interface PlantTaskRule {
  rule_id: string;
  action_type: string;
  title: string;
  recurrence_type: "one_time" | "interval_after_completion" | "seasonal" | "condition_based" | "continuous_review";
  anchor: "planting_date" | "completion_date" | "calendar_date" | "observation";
  interval_days: { min: number | null; preferred: number | null; max: number | null };
  active_months: number[];
  conditions: string[];
  skip_conditions: string[];
  notes: string;
}

export interface PlantCareProfile {
  summary: string;
  assumptions: string[];
  knowledge_sources: string[];
  irrigation: {
    strategy: string;
    baseline_interval_days: { min: number | null; preferred: number | null; max: number | null };
    decision_factors: string[];
    skip_conditions: string[];
  };
  fertilization: {
    strategy: string;
    ec_management: string;
    ph_management: string;
    decision_factors: string[];
    skip_conditions: string[];
  };
  stage_notes: Array<{ stage: string; indicators: string[]; management: string }>;
}

export interface PlantCalendar {
  id: string;
  planting_id: string;
  field_id: string;
  revision: number;
  actions: PlantCalendarAction[];
  care_profile: PlantCareProfile;
  task_rules: PlantTaskRule[];
  generation: {
    source: string;
    model: string;
    generated_at: string;
    guidance_count: number;
    context_snapshot?: Record<string, unknown>;
  };
  created_at: string;
  updated_at: string;
}

export interface PlantSuggestion {
  planting_id: string;
  crop_name: string;
  cultivar: string;
  placement_id: string;
  placement_name: string;
  timing_state: "overdue" | "due" | "upcoming";
  action: PlantCalendarAction;
}

export interface PlantWorkLog {
  id: string;
  planting_id: string;
  action_id: string;
  title: string;
  performed_on: string;
  note: string;
  rating: number | null;
  attachments: RecordImageAttachment[];
}

export interface PlantBundle {
  action_types: PlantActionTypeDefinition[];
  plantings: Planting[];
  calendars: Record<string, PlantCalendar>;
  suggestions: PlantSuggestion[];
  work_logs: PlantWorkLog[];
}

export interface PlantQuestionRecord {
  id: string;
  planting_id: string;
  question: string;
  answer: string;
  created_at: string;
}
