import type { FieldLayout, LayoutCollaborationSnapshot, LayoutDevice, LayoutPresenceState, PlantActionCompletionPayload, PlantActionMutationPayload, PlantActionReviewPayload, PlantActionSkipPayload, PlantBundle, PlantCalendarAction, Planting, PlantQuestionRecord } from "./types";

export interface SearchPage<Item> {
  items: Item[];
  total: number;
  page: number;
  page_size: number;
  page_count: number;
  has_previous: boolean;
  has_next: boolean;
}

export class ApiError extends Error {
  status: number;
  body: Record<string, unknown>;

  constructor(status: number, body: Record<string, unknown>) {
    super(typeof body.error === "string" ? body.error : `Request failed: ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const hasJsonBody = typeof options?.body === "string";
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(hasJsonBody ? { "Content-Type": "application/json" } : {}),
      ...options?.headers,
    },
  });
  const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new ApiError(response.status, body);
  }
  return body as T;
}

export function loadLayout(fieldId: string): Promise<FieldLayout> {
  return requestJson(`/local/api/fields/${encodeURIComponent(fieldId)}/layout`);
}

export function saveLayout(fieldId: string, layout: FieldLayout): Promise<FieldLayout> {
  return requestJson(`/local/api/fields/${encodeURIComponent(fieldId)}/layout`, {
    method: "PUT",
    body: JSON.stringify(layout),
  });
}

export function layoutCollaborationUrl(fieldId: string): string {
  return `/local/api/fields/${encodeURIComponent(fieldId)}/layout/collaboration`;
}

export function syncLayoutCollaboration(
  fieldId: string,
  payload: {
    client_id: string;
    active_space_id?: string;
    selected_placement_id?: string;
    state?: LayoutPresenceState;
    leave?: boolean;
  },
  { signal }: { signal?: AbortSignal } = {},
): Promise<LayoutCollaborationSnapshot> {
  return requestJson(layoutCollaborationUrl(fieldId), {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function loadLayoutDevices(fieldId: string, includeIds: string[] = []): Promise<LayoutDevice[]> {
  return (await searchLayoutDevices(fieldId, { includeIds })).items;
}

export function searchLayoutDevices(
  fieldId: string,
  { query = "", groups = [], includeIds = [], page = 1, pageSize = 50, signal }: {
    query?: string;
    groups?: string[];
    includeIds?: string[];
    page?: number;
    pageSize?: number;
    signal?: AbortSignal;
  } = {},
): Promise<SearchPage<LayoutDevice>> {
  const parameters = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (query.trim()) parameters.set("q", query.trim());
  groups.forEach((group) => parameters.append("group", group));
  includeIds.forEach((id) => parameters.append("include", id));
  return requestJson(`/local/api/fields/${encodeURIComponent(fieldId)}/layout/device-options?${parameters}`, { signal });
}

export function searchPlantActions(
  plantingId: string,
  { query = "", statuses = [], dateFrom = "", dateTo = "", page = 1, pageSize = 50, signal }: {
    query?: string;
    statuses?: string[];
    dateFrom?: string;
    dateTo?: string;
    page?: number;
    pageSize?: number;
    signal?: AbortSignal;
  } = {},
): Promise<SearchPage<PlantCalendarAction>> {
  const parameters = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (query.trim()) parameters.set("q", query.trim());
  if (dateFrom) parameters.set("date_from", dateFrom);
  if (dateTo) parameters.set("date_to", dateTo);
  statuses.forEach((status) => parameters.append("status", status));
  return requestJson(`/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/actions?${parameters}`, { signal });
}

export function loadPlantBundle(fieldId: string, { compact = false, calendarPlantingId = "" }: { compact?: boolean; calendarPlantingId?: string } = {}): Promise<PlantBundle> {
  const parameters = new URLSearchParams();
  if (compact) parameters.set("compact", "1");
  if (calendarPlantingId) parameters.append("calendar_planting_id", calendarPlantingId);
  const query = parameters.size ? `?${parameters}` : "";
  return requestJson(`/local/api/fields/${encodeURIComponent(fieldId)}/plantings${query}`);
}

export function createPlanting(fieldId: string, payload: Record<string, unknown>): Promise<unknown> {
  return requestJson(`/local/api/fields/${encodeURIComponent(fieldId)}/plantings`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updatePlanting(plantingId: string, payload: Partial<Planting>): Promise<Planting> {
  return requestJson(`/local/api/plantings/${encodeURIComponent(plantingId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function createFertilizerApplication(plantingId: string, payload: Record<string, unknown>): Promise<unknown> {
  return requestJson(`/local/api/plantings/${encodeURIComponent(plantingId)}/fertilizer-applications`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteFertilizerApplication(plantingId: string, applicationId: string): Promise<void> {
  return requestJson(
    `/local/api/plantings/${encodeURIComponent(plantingId)}/fertilizer-applications/${encodeURIComponent(applicationId)}`,
    { method: "DELETE" },
  );
}

export function createFertilizerMaterial(payload: Record<string, unknown>): Promise<unknown> {
  return requestJson("/local/api/fertilizer-materials", { method: "POST", body: JSON.stringify(payload) });
}

export function updateFertilizerMaterial(materialId: string, payload: Record<string, unknown>): Promise<unknown> {
  return requestJson(`/local/api/fertilizer-materials/${encodeURIComponent(materialId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteFertilizerMaterial(materialId: string): Promise<void> {
  return requestJson(`/local/api/fertilizer-materials/${encodeURIComponent(materialId)}`, { method: "DELETE" });
}

export function regeneratePlantCalendar(plantingId: string, payload: { start_date: string; planning_notes: string; mode: "automatic" | "review" }): Promise<unknown> {
  return requestJson(`/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/regenerate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function decidePlantCalendarRegenerationProposal(
  plantingId: string,
  taskId: string,
  proposalId: string,
  decision: "approved" | "rejected",
): Promise<unknown> {
  return requestJson(
    `/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/regeneration-proposals/${encodeURIComponent(taskId)}/${encodeURIComponent(proposalId)}`,
    { method: "POST", body: JSON.stringify({ decision }) },
  );
}

export function decidePlantCalendarRegenerationProposals(
  plantingId: string,
  taskId: string,
  decisions: Array<{ proposal_id: string; decision: "approved" | "rejected" }>,
): Promise<{ bundle: PlantBundle }> {
  return requestJson(
    `/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/regeneration-proposals/${encodeURIComponent(taskId)}/decisions`,
    { method: "POST", body: JSON.stringify({ decisions }) },
  );
}

export function addPlantAction(plantingId: string, payload: PlantActionMutationPayload): Promise<PlantCalendarAction> {
  const form = actionMutationForm(payload);
  return requestJson(`/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/actions`, {
    method: "POST",
    body: form,
  });
}

export function deletePlantAction(plantingId: string, actionId: string): Promise<void> {
  return requestJson(`/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/actions/${encodeURIComponent(actionId)}`, {
    method: "DELETE",
  });
}

export function updatePlantAction(
  plantingId: string,
  actionId: string,
  payload: PlantActionMutationPayload & { use_as_guidance?: boolean },
): Promise<PlantCalendarAction> {
  const form = actionMutationForm(payload);
  return requestJson(
    `/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/actions/${encodeURIComponent(actionId)}`,
    { method: "PATCH", body: form },
  );
}

function actionMutationForm(payload: PlantActionMutationPayload & { use_as_guidance?: boolean }): FormData {
  const form = new FormData();
  const { images = [], ...values } = payload;
  form.append("payload", JSON.stringify(values));
  images.slice(0, 5).forEach((image) => form.append("images", image));
  return form;
}

export function completePlantAction(
  plantingId: string,
  actionId: string,
  payload: PlantActionCompletionPayload,
): Promise<unknown> {
  const form = new FormData();
  form.append("performed_on", payload.performed_on);
  form.append("note", payload.note);
  form.append("rating", String(payload.rating));
  form.append("work_details", JSON.stringify(payload.work_details));
  payload.images.forEach((image) => form.append("images", image));
  return requestJson(
    `/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/actions/${encodeURIComponent(actionId)}/complete`,
    { method: "POST", body: form },
  );
}

export function reviewPlantAction(
  plantingId: string,
  actionId: string,
  payload: PlantActionReviewPayload,
): Promise<unknown> {
  return requestJson(
    `/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/actions/${encodeURIComponent(actionId)}/review`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function skipPlantAction(
  plantingId: string,
  actionId: string,
  payload: PlantActionSkipPayload,
): Promise<{ action: PlantCalendarAction }> {
  const form = new FormData();
  form.append("decided_on", payload.decided_on);
  form.append("reason_code", payload.reason_code);
  form.append("observed_facts", payload.observed_facts);
  form.append("note", payload.note);
  form.append("next_review_on", payload.next_review_on);
  form.append("use_as_guidance", String(payload.use_as_guidance));
  payload.images.forEach((image) => form.append("images", image));
  return requestJson(
    `/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/actions/${encodeURIComponent(actionId)}/skip`,
    { method: "POST", body: form },
  );
}

export function askPlantQuestion(plantingId: string, question: string): Promise<PlantQuestionRecord> {
  return requestJson(`/local/api/plantings/${encodeURIComponent(plantingId)}/questions`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export function listPlantQuestions(
  plantingId: string,
  { query = "", page = 1, pageSize = 5, signal }: { query?: string; page?: number; pageSize?: number; signal?: AbortSignal } = {},
): Promise<SearchPage<PlantQuestionRecord>> {
  const parameters = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (query.trim()) parameters.set("q", query.trim());
  return requestJson(`/local/api/plantings/${encodeURIComponent(plantingId)}/questions?${parameters}`, { signal });
}
