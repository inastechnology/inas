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
  | "camera"
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
  updated_by: string;
}

export type LayoutPresenceState = "viewing" | "editing" | "saving" | "conflict";

export interface LayoutCollaborator {
  client_id: string;
  email: string;
  active_space_id: string;
  selected_placement_id: string;
  state: LayoutPresenceState;
  last_seen_at: string;
  is_current: boolean;
}

export interface LayoutCollaborationSnapshot {
  field_id: string;
  layout: Pick<FieldLayout, "revision" | "updated_at" | "updated_by">;
  participants: LayoutCollaborator[];
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
  preview_url?: string;
  manage_url?: string;
}

export interface GrowthTarget {
  min: number | null;
  max: number | null;
}

export type PlantActionPriority = "required" | "should" | "recommended" | "optional";
export type PlantActionStatus = "planned" | "in_progress" | "awaiting_review" | "completed" | "skipped";
export type PlantActionReviewStatus = "pending" | "approved" | "rejected";
export type PlantActionSkipReason =
  | "already_satisfied"
  | "start_conditions_not_met"
  | "timing_passed"
  | "duplicate"
  | "generated_in_error"
  | "not_applicable"
  | "other";

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
  instructions_html: string;
  attachments: RecordImageAttachment[];
  tags: string[];
  required_people: number;
  estimated_minutes: number;
  assigned_to: string;
  work_plan: ActionWorkPlan;
  status: PlantActionStatus;
  completion: {
    work_log_id: string;
    performed_on: string;
    performed_by: string;
    note: string;
    rating?: number | null;
    attachments?: RecordImageAttachment[];
    work_details?: PlantActionWorkDetails;
    review_status: PlantActionReviewStatus;
    submitted_at: string;
    reviewed_by: string;
    reviewed_at: string;
    review_note: string;
  } | null;
  skip_decision: {
    decided_on: string;
    reason_code: PlantActionSkipReason;
    observed_facts: string;
    note: string;
    next_review_on: string | null;
    attachments: RecordImageAttachment[];
    decided_by: string;
    created_at: string;
  } | null;
  source: string;
  rule_id: string;
}

export type PlantActionMutationPayload = Partial<PlantCalendarAction> & { images?: File[] };

export type WorkMethodType =
  | "observation"
  | "manual"
  | "device"
  | "material_application"
  | "chemical"
  | "physical"
  | "biological"
  | "cultural"
  | "other";

export interface WorkMethodOption {
  id: string;
  label: string;
  method_type: WorkMethodType;
  material_name: string;
  registration_number: string;
  purpose: string;
  application_method: string;
  amount_or_rate: string;
  procedure_steps: string[];
  completion_checks: string[];
  precautions: string[];
  frequency: WorkFrequency;
  instructions: string;
  follow_up_days_default: number | null;
  source_name: string;
  source_url: string;
  source_checked_at: string;
}

export interface WorkFrequency {
  mode: "one_time" | "as_needed" | "interval" | "seasonal" | "continuous";
  min_interval_days: number | null;
  preferred_interval_days: number | null;
  max_interval_days: number | null;
  max_applications: number | null;
  basis: string;
}

export interface ActionWorkPlan {
  targets: string[];
  start_conditions: string[];
  skip_conditions: string[];
  checkpoints: string[];
  method_options: WorkMethodOption[];
  completion_criteria: string[];
}

export interface ActionExecutionDetails {
  target: string;
  method_id: string;
  method_label: string;
  method_type: WorkMethodType;
  material_name: string;
  amount_or_rate: string;
  registration_number: string;
  custom_method: string;
  follow_up_days: number | null;
  source_name: string;
  source_url: string;
  source_checked_at: string;
}

export interface PlantActionWorkDetails {
  execution?: ActionExecutionDetails;
}

export interface PlantActionCompletionPayload {
  performed_on: string;
  note: string;
  rating: number;
  images: File[];
  work_details: PlantActionWorkDetails;
}

export interface PlantActionReviewPayload {
  decision: "approved" | "rejected";
  note: string;
}

export interface PlantActionSkipPayload {
  decided_on: string;
  reason_code: PlantActionSkipReason;
  observed_facts: string;
  note: string;
  next_review_on: string;
  images: File[];
  use_as_guidance: boolean;
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
  knowledge_evidence: Array<{
    title: string;
    url: string;
    publisher: string;
    applicable_region: string;
    published_at: string;
    fetched_at: string;
  }>;
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
  action_id: string;
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
  performed_by: string;
  note: string;
  rating: number | null;
  attachments: RecordImageAttachment[];
  work_details: PlantActionWorkDetails;
  review_status: PlantActionReviewStatus;
  submitted_at: string;
  reviewed_by: string;
  reviewed_at: string;
  review_note: string;
}

export type FertilizerMaterialKind =
  | "cattle_manure"
  | "poultry_manure"
  | "compost"
  | "organic_fertilizer"
  | "chemical_fertilizer"
  | "custom";

export interface FertilizerMaterial {
  id: string;
  scope: "builtin" | "user";
  catalog_revision: number;
  label: string;
  summary: string;
  material_kind: FertilizerMaterialKind;
  material_name: string;
  nutrient_percent: { n: number; p2o5: number; k2o: number; mgo: number };
  annual_available_percent: number;
  effect_years: number;
  start_delay_days: number;
  analysis_source: string;
  source_url: string;
  created_at: string;
  updated_at: string;
}

export interface FertilizerApplication {
  id: string;
  field_id: string;
  planting_id: string;
  space_id: string;
  placement_id: string;
  placement_name: string;
  applied_on: string;
  material_kind: FertilizerMaterialKind;
  material_name: string;
  amount_kg: number;
  nutrient_percent: { n: number; p2o5: number; k2o: number; mgo: number };
  annual_available_percent: number;
  effect_years: number;
  start_delay_days: number;
  analysis_source: string;
  notes: string;
  created_at: string;
  material_id: string;
  material_snapshot: Partial<FertilizerMaterial>;
}

export interface FertilizerEffectSummary {
  as_of: string;
  model: "linear_estimate_from_user_inputs";
  application_count: number;
  active_count: number;
  nutrients: Record<"n" | "p2o5" | "k2o" | "mgo", {
    applied_kg: number;
    effective_total_kg: number;
    released_to_date_kg: number;
    remaining_kg: number;
  }>;
  applications: Array<{
    id: string;
    material_name: string;
    amount_kg: number;
    applied_on: string;
    effect_start: string;
    effect_end: string;
    state: "waiting" | "active" | "finished";
    progress_percent: number;
  }>;
  forecast: Array<{
    period_start: string;
    period_end: string;
    nutrients_kg: Record<"n" | "p2o5" | "k2o" | "mgo", number>;
  }>;
  caution: string;
}

export interface PlantCalendarGenerationTask {
  id: string;
  field_id: string;
  planting_id: string;
  kind: "initial" | "regenerate";
  status: "queued" | "running" | "awaiting_review" | "succeeded" | "failed";
  mode: "automatic" | "review";
  start_date: string;
  planning_notes: string;
  attempts: number;
  error: string;
  created_at: string;
  started_at: string;
  finished_at: string;
  updated_at: string;
  proposals: PlantCalendarRegenerationProposal[];
}

export interface PlantCalendarRegenerationProposal {
  id: string;
  change_type: "add" | "update" | "delete";
  decision: "pending" | "approved" | "rejected";
  existing_action_id: string;
  title: string;
  before: PlantCalendarAction | null;
  after: PlantCalendarAction | null;
  decided_at: string;
}

export interface AgenticOperationExecutorCandidate {
  device_id: string;
  name: string;
  device_kind: string;
  placement_name: string;
  resource_id: string;
  channel_mask: number | null;
  manage_url: string;
}

export interface AgenticOperationReadiness {
  action_type: string;
  operation_label: string;
  executor_mode: "human" | "device_assisted";
  automation_stage: "guidance_only" | "supervised_device";
  summary: string;
  decision_checks: string[];
  stop_conditions: string[];
  verification_checks: string[];
  executor_candidates: AgenticOperationExecutorCandidate[];
  allowed_by_policy: boolean;
  autonomy_level: string;
  requires_approval: boolean;
  can_dispatch: boolean;
  dispatch_reason: string;
  next_href: string;
  next_label: string;
}

export interface PlantBundle {
  viewer: { email: string; role: "admin" | "operator" };
  action_types: PlantActionTypeDefinition[];
  plantings: Planting[];
  calendars: Record<string, PlantCalendar>;
  generation_tasks: PlantCalendarGenerationTask[];
  suggestions: PlantSuggestion[];
  work_logs: PlantWorkLog[];
  fertilizer_applications: FertilizerApplication[];
  fertilizer_materials: FertilizerMaterial[];
  operation_readiness: Record<string, AgenticOperationReadiness>;
  work_routes: GuidedWorkRoute[];
  work_route_runs: GuidedWorkRouteRun[];
}

export type GuidedWorkStepType = "observe" | "measure" | "decide" | "prepare" | "perform" | "wait" | "verify";

export interface GuidedWorkRouteStep {
  id: string;
  type: GuidedWorkStepType;
  title: string;
  description: string;
  prompt: string;
  metric: string;
  unit: string;
  instructions: string;
  next_step_id: string;
  missing_step_id: string;
  choices: Array<{ id: string; label: string; next_step_id: string }>;
}

export interface GuidedWorkRoute {
  id: string;
  planting_id: string;
  field_id: string;
  action_id: string;
  title: string;
  summary: string;
  status: "active" | "archived";
  entry_step_id: string;
  steps: GuidedWorkRouteStep[];
  dependencies: Array<{ route_id: string; type: "completed" | "approved" | "elapsed_days"; min_days: number; label: string }>;
  start_blockers: string[];
  created_at: string;
  updated_at: string;
}

export interface GuidedWorkRouteRun {
  id: string;
  route_id: string;
  planting_id: string;
  field_id: string;
  status: "in_progress" | "completed";
  current_step_id: string;
  history: Array<{
    step_id: string;
    step_type: GuidedWorkStepType;
    title: string;
    outcome: string;
    choice_id: string;
    value: string;
    note: string;
    source: string;
    completed_at: string;
  }>;
  started_at: string;
  completed_at: string;
  updated_at: string;
}

export interface PlantQuestionRecord {
  id: string;
  planting_id: string;
  question: string;
  answer: string;
  created_at: string;
}
