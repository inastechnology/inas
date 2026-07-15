import type { FieldLayout, LayoutDevice, PlantBundle, PlantCalendarAction, Planting, PlantQuestionRecord } from "./types";

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
  const body = (await response.json().catch(() => ({}))) as { error?: string };
  if (!response.ok) {
    throw new Error(body.error || `Request failed: ${response.status}`);
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

export function loadLayoutDevices(fieldId: string): Promise<LayoutDevice[]> {
  return requestJson(`/local/api/fields/${encodeURIComponent(fieldId)}/layout/devices`);
}

export function loadPlantBundle(fieldId: string): Promise<PlantBundle> {
  return requestJson(`/local/api/fields/${encodeURIComponent(fieldId)}/plantings`);
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

export function regeneratePlantCalendar(plantingId: string, payload: { start_date: string; planning_notes: string }): Promise<unknown> {
  return requestJson(`/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/regenerate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function addPlantAction(plantingId: string, payload: Partial<PlantCalendarAction>): Promise<PlantCalendarAction> {
  return requestJson(`/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/actions`, {
    method: "POST",
    body: JSON.stringify(payload),
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
  payload: Partial<PlantCalendarAction> & { use_as_guidance?: boolean },
): Promise<PlantCalendarAction> {
  return requestJson(
    `/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/actions/${encodeURIComponent(actionId)}`,
    { method: "PATCH", body: JSON.stringify(payload) },
  );
}

export function completePlantAction(
  plantingId: string,
  actionId: string,
  payload: { performed_on: string; note: string; rating: number; images: File[] },
): Promise<unknown> {
  const form = new FormData();
  form.append("performed_on", payload.performed_on);
  form.append("note", payload.note);
  form.append("rating", String(payload.rating));
  payload.images.forEach((image) => form.append("images", image));
  return requestJson(
    `/local/api/plantings/${encodeURIComponent(plantingId)}/calendar/actions/${encodeURIComponent(actionId)}/complete`,
    { method: "POST", body: form },
  );
}

export function askPlantQuestion(plantingId: string, question: string): Promise<PlantQuestionRecord> {
  return requestJson(`/local/api/plantings/${encodeURIComponent(plantingId)}/questions`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}
