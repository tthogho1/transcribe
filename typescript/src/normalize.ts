export function normalizeTextForSearch(text: string): string {
  if (!text) return '';
  // lowercase
  let t = text.toLowerCase();
  // Unicode NFKC
  t = t.normalize('NFKC');
  // hiragana -> katakana
  let out = '';
  for (const ch of t) {
    const code = ch.codePointAt(0)!;
    if (code >= 0x3040 && code <= 0x309f) {
      out += String.fromCodePoint(code + 0x60);
    } else {
      out += ch;
    }
  }
  // collapse whitespace
  return out.replace(/\s+/g, ' ').trim();
}

export function containsNormalized(haystack: string, needle: string): boolean {
  if (!haystack || !needle) return false;
  return normalizeTextForSearch(haystack).includes(normalizeTextForSearch(needle));
}
