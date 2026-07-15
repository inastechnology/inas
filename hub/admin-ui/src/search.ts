export function normalizeSearchText(value: string): string {
  return value
    .normalize("NFKC")
    .toLocaleLowerCase("ja")
    .replace(/[\s・_\-\/]+/g, "")
    .replace(/灌/g, "潅")
    .replace(/鉢植え/g, "鉢")
    .replace(/ハウス/g, "温室");
}

export function matchesSearch(query: string, values: Array<string | undefined>): boolean {
  const terms = query.split(/[\s　]+/).map(normalizeSearchText).filter(Boolean);
  if (terms.length === 0) return true;
  const haystack = normalizeSearchText(values.filter(Boolean).join(" "));
  return terms.every((term) => haystack.includes(term));
}
