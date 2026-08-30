export type StorageLike = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

export type TrackingContext = {
  store_id?: number;
  selection_session_id?: string;
  position_id?: number;
  source?: string;
};

export type TrackingEvent = {
  event: string;
  page: string;
  data: Record<string, unknown>;
  ts: string;
};

type TrackerOptions = {
  localStorage: StorageLike;
  sessionStorage: StorageLike;
  randomId: () => string;
  now: () => Date;
  send: (events: TrackingEvent[]) => Promise<void>;
};

const ANONYMOUS_ID_KEY = 'hxy_diy_anonymous_id';
const CLIENT_SESSION_ID_KEY = 'hxy_diy_client_session_id';
const EVENT_QUEUE_KEY = 'hxy_diy_tracking_queue';

function readOrCreate(storage: StorageLike, key: string, randomId: () => string): string {
  const existing = storage.getItem(key);
  if (existing) return existing;
  const value = randomId();
  storage.setItem(key, value);
  return value;
}

function readQueue(storage: StorageLike): TrackingEvent[] {
  try {
    const value = JSON.parse(storage.getItem(EVENT_QUEUE_KEY) || '[]');
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

export function createTracker(options: TrackerOptions) {
  const anonymousId = readOrCreate(options.localStorage, ANONYMOUS_ID_KEY, options.randomId);
  const clientSessionId = readOrCreate(options.sessionStorage, CLIENT_SESSION_ID_KEY, options.randomId);
  let context: TrackingContext = {};
  let flushing = false;

  const saveQueue = (events: TrackingEvent[]) => {
    options.localStorage.setItem(EVENT_QUEUE_KEY, JSON.stringify(events.slice(-100)));
  };

  const queuedEvents = () => readQueue(options.localStorage);

  const flush = async () => {
    if (flushing) return;
    const batch = queuedEvents().slice(0, 50);
    if (!batch.length) return;
    flushing = true;
    try {
      await options.send(batch);
      const remaining = queuedEvents().slice(batch.length);
      if (remaining.length) saveQueue(remaining);
      else options.localStorage.removeItem(EVENT_QUEUE_KEY);
    } catch {
      // Analytics must never block the customer flow; the queue is retried later.
    } finally {
      flushing = false;
    }
  };

  const track = (event: string, data: Record<string, unknown> = {}, page = '') => {
    const next: TrackingEvent = {
      event,
      page,
      ts: options.now().toISOString(),
      data: {
        anonymous_id: anonymousId,
        client_session_id: clientSessionId,
        ...context,
        ...data,
      },
    };
    const queue = queuedEvents();
    queue.push(next);
    saveQueue(queue);
    if (queue.length >= 10) void flush();
  };

  return {
    setContext(next: TrackingContext) {
      context = { ...context, ...next };
    },
    track,
    flush,
    queuedEvents,
  };
}

let trackingAuthToken = '';
const browserTracker = typeof window === 'undefined' ? null : createTracker({
  localStorage: window.localStorage,
  sessionStorage: window.sessionStorage,
  randomId: () => crypto.randomUUID(),
  now: () => new Date(),
  send: async (events) => {
    const response = await fetch('/api/v1/events', {
      method: 'POST',
      credentials: 'include',
      keepalive: true,
      headers: {
        'Content-Type': 'application/json',
        ...(trackingAuthToken ? { Authorization: `Bearer ${trackingAuthToken}` } : {}),
      },
      body: JSON.stringify({ events }),
    });
    if (!response.ok) throw new Error(`tracking failed: ${response.status}`);
  },
});

export function setDiyTrackingContext(context: TrackingContext & { auth_token?: string }) {
  if (context.auth_token !== undefined) trackingAuthToken = context.auth_token;
  const { auth_token: _authToken, ...publicContext } = context;
  browserTracker?.setContext(publicContext);
}

export function trackDiyEvent(event: string, data: Record<string, unknown> = {}, page?: string) {
  browserTracker?.track(event, data, page ?? window.location.pathname);
}

export async function runTrackedOperation<T>(
  eventPrefix: string,
  data: Record<string, unknown>,
  operation: () => Promise<T>,
  emit: (event: string, eventData: Record<string, unknown>) => void = trackDiyEvent,
): Promise<T> {
  emit(`${eventPrefix}_attempt`, data);
  try {
    const result = await operation();
    emit(`${eventPrefix}_success`, data);
    return result;
  } catch (error) {
    const value = error as { code?: string; status?: number };
    emit(`${eventPrefix}_fail`, {
      ...data,
      error_code: value?.code || 'UNKNOWN',
      ...(value?.status ? { http_status: value.status } : {}),
    });
    throw error;
  }
}

export function flushDiyTracking() {
  return browserTracker?.flush() ?? Promise.resolve();
}
