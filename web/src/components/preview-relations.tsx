import { t, tr, locale } from "../i18n/index.mjs";
import { copyText } from "../lib/copy-text";
import { useEffect, useRef, useState } from "react";
import { Check, Copy, LoaderCircle } from "lucide-react";
import { Button } from "./ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { HelpTip, IconButton } from "./actions";

export type PreviewTerm = { id: string; text: string; channel: "positive" | "negative" };
type Relation = { text: string; known: boolean; pmi: number | null; count: number | null };
type Relations = { anchor: { text: string; known: boolean }; relations: Relation[] };
type Query = { data?: Relations; error?: string };
const normalized = (text: string) => text.trim().replaceAll("_", " ");

function CopyText({ text, label }: { text: string; label: string }) {
  const [status, setStatus] = useState("");
  const copy = async () => { try { await copyText(text); setStatus("success"); } catch { setStatus("error"); } };
  useEffect(() => { if (!status) return; const timer = setTimeout(() => setStatus(""), 1800); return () => clearTimeout(timer); }, [status]);
  return <IconButton icon={status === "success" ? Check : Copy} label={status === "success" ? t("已复制") : status === "error" ? t("复制失败，请重试") : tr`复制${label}`} disabled={!text} onClick={copy} />;
}

function tone(relation: Relation | undefined, anchorKnown: boolean | undefined) {
  if (!relation || anchorKnown === undefined) return "";
  if (!anchorKnown || !relation.known) return "unknown";
  if (relation.count === null) return "omitted";
  return relation.pmi! > 0 ? "positive" : relation.pmi! < 0 ? "negative" : "neutral";
}

export function PreviewPrompts({ terms, positive, negative }: { terms: PreviewTerm[]; positive: string; negative: string }) {
  const [active, setActive] = useState<number | null>(null);
  const [queries, setQueries] = useState(new Map<string, Query>());
  const requested = useRef(new Set<string>());
  const controllers = useRef(new Set<AbortController>());
  useEffect(() => () => { for (const controller of controllers.current) controller.abort(); }, []);
  const load = (index: number) => {
    setActive(index);
    const anchor = normalized(terms[index].text);
    if (requested.current.has(anchor)) return;
    requested.current.add(anchor);
    const controller = new AbortController(); controllers.current.add(controller);
    const update = (query: Query) => setQueries(current => new Map(current).set(anchor, query));
    update({});
    fetch("/api/candidate/relations", { method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
      body: JSON.stringify({ anchor, terms: terms.map(term => term.text) }) })
      .then(async response => { const data = await response.json(); if (!response.ok) throw new Error(data.error || tr`请求失败（${response.status}）`); return data as Relations; })
      .then(data => { if (!controller.signal.aborted) update({ data }); })
      .catch(error => { if (!controller.signal.aborted) { requested.current.delete(anchor); update({ error: error instanceof Error ? error.message : String(error) }); } })
      .finally(() => controllers.current.delete(controller));
  };
  const anchor = active === null ? null : normalized(terms[active].text);
  const query = anchor === null ? undefined : queries.get(anchor);
  const relations = new Map(query?.data?.relations.map(relation => [normalized(relation.text), relation]));
  return <TooltipProvider delayDuration={200}><div className="cooc-preview-grid">
    {(["positive", "negative"] as const).map(channel => {
      const label = channel === "positive" ? t("正向提示词") : t("负向提示词");
      const items = terms.map((term, index) => ({ term, index })).filter(({ term }) => term.channel === channel);
      return <section key={channel}><div className="cooc-section-heading"><h2>{label}</h2>{channel === "negative" && <HelpTip text={t("负向词交给生图模型排除内容，不参与共现扩展筛选。")} />}<span className="spacer" /><CopyText text={channel === "positive" ? positive : negative} label={label} /></div>
        <p className="cooc-prompt">{items.length ? items.map(({ term, index }, position) => <span key={`${channel}:${index}`}>
          <Tooltip open={active === index} onOpenChange={open => { if (open) load(index); else setActive(current => current === index ? null : current); }}>
            <TooltipTrigger asChild><Button variant="ghost" size="sm" className="cooc-preview-term" data-relation={anchor === normalized(term.text) ? "anchor" : tone(relations.get(normalized(term.text)), query?.data?.anchor.known)} aria-label={tr`查看 ${term.text} 与其他提示词的相关性`} onClick={event => { event.preventDefault(); load(index); }}>{term.text}</Button></TooltipTrigger>
            <TooltipContent side="bottom" align="start" sideOffset={6} className="cooc-relations-tooltip">
              <strong>{term.text}</strong>
              {!query || !query.data && !query.error ? <p role="status"><LoaderCircle className="size-3 animate-spin" />{t("读取相关性…")}</p> : query.error ? <p role="status">{t("读取失败：{error}。移开后重试。", { error: query.error })}</p> : !query.data!.anchor.known ? <p>{t("自定义词，无统计；不参与 PMI 比较。")}</p> : !query.data!.relations.length ? <p>{t("当前组合没有其他词项。")}</p> : <>
                <div className="cooc-relations-scroll"><table><thead><tr><th>{t("提示词")}</th><th>PMI</th><th>{t("共现次数（≥10）")}</th></tr></thead><tbody>{query.data!.relations.map(relation => <tr key={relation.text}>
                  <td>{relation.text}</td><td>{!relation.known ? t("无统计") : relation.count === null ? t("未保留统计") : relation.pmi!.toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td><td>{!relation.known ? "—" : relation.count === null ? "<10" : relation.count.toLocaleString(locale())}</td>
                </tr>)}</tbody></table></div>
                <p className="cooc-relations-note">{t("PMI 表示统计关联，不代表画面协调或冲突。")}</p>
              </>}
            </TooltipContent>
          </Tooltip>{position < items.length - 1 ? ", " : ""}
        </span>) : "—"}</p>
      </section>;
    })}
  </div></TooltipProvider>;
}
