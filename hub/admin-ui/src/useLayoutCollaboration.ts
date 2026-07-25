import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { layoutCollaborationUrl, syncLayoutCollaboration } from "./api";
import type { LayoutCollaborationSnapshot, LayoutPresenceState } from "./types";

export type CollaborationConnectionState = "connecting" | "online" | "offline";

interface LayoutCollaborationOptions {
  fieldId: string;
  activeSpaceId: string;
  selectedPlacementId: string;
  state: LayoutPresenceState;
  enabled: boolean;
}

const ACTIVE_INTERVAL_MS = 2_000;
const BACKGROUND_INTERVAL_MS = 8_000;
const CLIENT_ID_PATTERN = /^[A-Za-z0-9._:-]{8,80}$/;
const PAGE_INSTANCE_TOKEN = randomToken().slice(0, 12);

export function useLayoutCollaboration({
  fieldId,
  activeSpaceId,
  selectedPlacementId,
  state,
  enabled,
}: LayoutCollaborationOptions): {
  clientId: string;
  snapshot: LayoutCollaborationSnapshot | null;
  connectionState: CollaborationConnectionState;
  syncNow: () => Promise<void>;
} {
  const clientId = useMemo(() => collaborationClientId(fieldId), [fieldId]);
  const [snapshot, setSnapshot] = useState<LayoutCollaborationSnapshot | null>(null);
  const [connectionState, setConnectionState] = useState<CollaborationConnectionState>("connecting");
  const presenceRef = useRef({ activeSpaceId, selectedPlacementId, state });
  const requestRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);
  const activeFieldRef = useRef(fieldId);

  presenceRef.current = { activeSpaceId, selectedPlacementId, state };
  activeFieldRef.current = fieldId;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const syncNow = useCallback(async () => {
    if (!enabled || inFlightRef.current) return;
    const requestFieldId = fieldId;
    const controller = new AbortController();
    requestRef.current = controller;
    inFlightRef.current = true;
    try {
      const presence = presenceRef.current;
      const nextSnapshot = await syncLayoutCollaboration(
        requestFieldId,
        {
          client_id: clientId,
          active_space_id: presence.activeSpaceId,
          selected_placement_id: presence.selectedPlacementId,
          state: presence.state,
        },
        { signal: controller.signal },
      );
      if (!mountedRef.current || activeFieldRef.current !== requestFieldId) return;
      setSnapshot(nextSnapshot);
      setConnectionState("online");
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      if (mountedRef.current && activeFieldRef.current === requestFieldId) setConnectionState("offline");
    } finally {
      if (requestRef.current === controller) requestRef.current = null;
      inFlightRef.current = false;
    }
  }, [clientId, enabled, fieldId]);

  useEffect(() => {
    if (!enabled) {
      setSnapshot(null);
      setConnectionState("connecting");
      return undefined;
    }

    let disposed = false;
    let timer = 0;
    const tick = async () => {
      await syncNow();
      if (!disposed) timer = window.setTimeout(tick, document.hidden ? BACKGROUND_INTERVAL_MS : ACTIVE_INTERVAL_MS);
    };
    const syncWhenVisible = () => {
      if (!document.hidden) void syncNow();
    };
    const syncWhenOnline = () => void syncNow();
    const leave = () => sendLeave(fieldId, clientId);

    setConnectionState("connecting");
    void tick();
    document.addEventListener("visibilitychange", syncWhenVisible);
    window.addEventListener("online", syncWhenOnline);
    window.addEventListener("pagehide", leave);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", syncWhenVisible);
      window.removeEventListener("online", syncWhenOnline);
      window.removeEventListener("pagehide", leave);
      requestRef.current?.abort();
      leave();
    };
  }, [clientId, enabled, fieldId, syncNow]);

  useEffect(() => {
    if (!enabled) return undefined;
    const timer = window.setTimeout(() => void syncNow(), 120);
    return () => window.clearTimeout(timer);
  }, [activeSpaceId, enabled, selectedPlacementId, state, syncNow]);

  return { clientId, snapshot, connectionState, syncNow };
}

function collaborationClientId(fieldId: string): string {
  const storageKey = `ina-layout-collaboration:${fieldId}`;
  try {
    const stored = window.sessionStorage.getItem(storageKey) ?? "";
    const seed = CLIENT_ID_PATTERN.test(stored) && stored.length <= 60 ? stored : createClientSeed();
    if (seed !== stored) window.sessionStorage.setItem(storageKey, seed);
    return `${seed}-${PAGE_INSTANCE_TOKEN}`;
  } catch {
    return `${createClientSeed()}-${PAGE_INSTANCE_TOKEN}`;
  }
}

function createClientSeed(): string {
  return `layout-${randomToken()}`;
}

function randomToken(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

function sendLeave(fieldId: string, clientId: string): void {
  const body = JSON.stringify({ client_id: clientId, leave: true });
  try {
    const beaconBody = new Blob([body], { type: "application/json" });
    if (navigator.sendBeacon?.(layoutCollaborationUrl(fieldId), beaconBody)) return;
  } catch {
    // A keepalive fetch below is the best-effort fallback during navigation.
  }
  void fetch(layoutCollaborationUrl(fieldId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => undefined);
}
