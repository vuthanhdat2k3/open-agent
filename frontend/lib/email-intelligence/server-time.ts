export type ServerClock = {
  serverEpochMs: number;
  performanceMs: number;
};

export function createServerClock(serverTime: string, performanceNow: number = performance.now()): ServerClock {
  return { serverEpochMs: Date.parse(serverTime), performanceMs: performanceNow };
}

export function serverNow(clock: ServerClock, performanceNow: number = performance.now()): number {
  return clock.serverEpochMs + Math.max(0, performanceNow - clock.performanceMs);
}

export function remainingMs(expiresAt: string, clock: ServerClock, performanceNow?: number): number {
  return Math.max(0, Date.parse(expiresAt) - serverNow(clock, performanceNow));
}

export function formatRemaining(ms: number): string {
  const totalSeconds = Math.ceil(ms / 1000);
  if (totalSeconds <= 0) return "Đã hết hạn";
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `Còn ${hours} giờ ${minutes} phút`;
  if (minutes > 0) return `Còn ${minutes} phút`;
  return `Còn ${seconds} giây`;
}
