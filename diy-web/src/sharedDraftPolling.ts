export type SharedDraftPollingOptions = {
  poll: (signal: AbortSignal) => Promise<void>;
  canPoll: () => boolean;
  isTerminal: (error: unknown) => boolean;
  onTerminal: () => void;
  intervalMs?: number;
  maxBackoffMs?: number;
  setTimer?: typeof setTimeout;
  clearTimer?: typeof clearTimeout;
};

export function startSharedDraftPolling({
  poll,
  canPoll,
  isTerminal,
  onTerminal,
  intervalMs = 3000,
  maxBackoffMs = 30000,
  setTimer = setTimeout,
  clearTimer: cancelTimer = clearTimeout,
}: SharedDraftPollingOptions) {
  let stopped = false;
  let running = false;
  let pending = false;
  let failures = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | undefined;

  const clearTimer = () => {
    if (timer !== undefined) cancelTimer(timer);
    timer = undefined;
  };

  const run = async () => {
    if (stopped || !canPoll()) return;
    if (running) { pending = true; return; }
    clearTimer();
    running = true;
    controller = new AbortController();
    try {
      await poll(controller.signal);
      failures = 0;
    } catch (error) {
      if (!controller.signal.aborted && isTerminal(error)) {
        stopped = true;
        onTerminal();
      } else if (!controller.signal.aborted) {
        failures += 1;
      }
    } finally {
      controller = undefined;
      running = false;
      if (!stopped && canPoll()) {
        const delay = failures ? Math.min(maxBackoffMs, intervalMs * 2 ** Math.min(failures, 4)) : pending ? 0 : intervalMs;
        pending = false;
        timer = setTimer(() => void run(), delay);
      }
    }
  };

  const pause = () => {
    pending = false;
    clearTimer();
    controller?.abort();
  };
  const resume = () => {
    if (stopped || !canPoll()) return;
    failures = 0;
    clearTimer();
    void run();
  };
  resume();
  return { pause, resume, stop: () => { stopped = true; pause(); } };
}
