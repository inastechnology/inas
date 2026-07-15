export function todayString(): string {
  const value = new Date();
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  return value.toISOString().slice(0, 10);
}

export function formatDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? `${Number(match[1])}年${Number(match[2])}月${Number(match[3])}日` : value;
}

export function formatDateRange(start: string, end: string): string {
  if (start === end) return formatDate(start);
  const startMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(start);
  const endMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(end);
  if (!startMatch || !endMatch) return `${start} - ${end}`;
  if (startMatch[1] === endMatch[1]) {
    return `${Number(startMatch[1])}年${Number(startMatch[2])}月${Number(startMatch[3])}日 - ${Number(endMatch[2])}月${Number(endMatch[3])}日`;
  }
  return `${formatDate(start)} - ${formatDate(end)}`;
}

export function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : "処理に失敗しました。";
}
