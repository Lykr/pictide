import { useEffect, useState } from "react";
import { tr } from "../i18n/index.mjs";
import { onSignal } from "./signals.mjs";

export type VocabularyTag = { id: number; name: string; post_count: number };
type SearchResult = { key: string; tags: VocabularyTag[]; error: string };

/** Read the selected library without letting an older request replace newer suggestions. */
export function useVocabularySearch(query: string, enabled: boolean) {
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<SearchResult | null>(null);
  const key = JSON.stringify([query, revision]);
  useEffect(() => onSignal("candidate-library-changed", () => setRevision(value => value + 1)), []);
  useEffect(() => {
    if (!enabled) return;
    const abort = new AbortController();
    setResult(null);
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/candidate/tags?query=${encodeURIComponent(query)}&page=1&page_size=12`, { signal: abort.signal });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : data.error?.message || tr`请求失败（${response.status}）`);
        if (!abort.signal.aborted) setResult({ key, tags: data.tags, error: "" });
      } catch (failure) {
        if (!abort.signal.aborted) setResult({ key, tags: [], error: failure instanceof Error ? failure.message : String(failure) });
      }
    }, 180);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [query, revision, key, enabled]);
  const current = enabled && result?.key === key ? result : null;
  return { matches: current?.tags ?? [], error: current?.error ?? "", loading: enabled && current === null };
}
