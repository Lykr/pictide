import { t, tr, messageKey } from "../i18n/index.mjs";
import { copyText } from "../lib/copy-text";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, Copy, X } from "lucide-react";
import { loadImagePreferenceScore } from "../controllers/image-preference-score.mjs";
import { HelpTip, IconButton } from "./actions";
import "../styles/image-prompt-details.css";

function CopyValue({ title, text, disabled = false }: { title: string; text: string; disabled?: boolean }) {
  const [status, setStatus] = useState("idle");
  const request = useRef(0);
  useEffect(() => {
    request.current++;
    setStatus("idle");
    return () => { request.current++; };
  }, [text]);
  useEffect(() => {
    if (status !== "success" && status !== "error") return;
    const timer = setTimeout(() => setStatus("idle"), 2000);
    return () => clearTimeout(timer);
  }, [status]);
  const copy = async () => {
    const token = ++request.current;
    setStatus("copying");
    try {
      await copyText(text);
      if (request.current === token) setStatus("success");
    } catch {
      if (request.current === token) setStatus("error");
    }
  };
  const feedback = status === "success" ? t("已复制") : status === "error" ? t("复制失败，请选中文本复制") : "";
  return <span className="image-detail-copy">
    <IconButton icon={status === "success" ? Check : status === "error" ? X : Copy}
      label={feedback ? t("{title}：{feedback}", { title, feedback }) : tr`复制${title}`}
      disabled={disabled || !text || status === "copying"} onClick={copy} />
    <span className="sr-only" role="status">{feedback}</span>
  </span>;
}

function DetailField({ title, text, disabled = false }: { title: string; text: string; disabled?: boolean }) {
  return <section className="image-prompt-section" aria-label={title}>
    <div className="image-detail-heading">
      <h3>{title}</h3>
      <CopyValue title={title} text={text} disabled={disabled} />
    </div>
    <pre className="image-prompt-text" tabIndex={text ? 0 : undefined}>{text || t("（无）")}</pre>
  </section>;
}

type PreferenceScore = {
  status: "scored" | "missing_snapshot" | "unavailable";
  score: number | null; love_score: number | null;
  score_min: number | null; score_max: number | null;
  reason?: string | null;
};

function ImagePreferenceScore({ imageId, active }: { imageId: string; active: boolean }) {
  const [result, setResult] = useState<PreferenceScore | null>(null);
  useEffect(() => {
    setResult(null);
    if (active) return loadImagePreferenceScore(imageId, setResult);
  }, [imageId, active]);
  const scored = result?.status === "scored";
  const value = !result ? t("加载中…") : !scored ? t("暂无法评分")
    : result.love_score === null ? t("暂无区分") : result.love_score.toFixed(1);
  const details = scored
    ? t("原始评分：{score}；历史范围：{minimum}–{maximum}。", {
      score: result.score?.toFixed(4) ?? "—",
      minimum: result.score_min?.toFixed(4) ?? "—", maximum: result.score_max?.toFixed(4) ?? "—",
    })
    : result?.reason ? t(messageKey(result.reason)) : "";
  const explanation = t("按当前偏好对提示词组合评分；0–100 是历史范围中的相对刻度，不是喜欢概率。");
  return <section className="image-prompt-section image-preference-score" aria-label={t("偏好评分")}>
    <div className="image-detail-heading">
      <h3>{t("偏好评分")}</h3>
      <HelpTip text={[details, explanation].filter(Boolean).join(" ")} />
    </div>
    <div className="image-preference-value" role="status" aria-live="polite" data-scored={scored && result.love_score !== null}>{value}</div>
  </section>;
}

export function ImagePromptDetails({ imageId, active, seed, positive, negative, actions }: {
  imageId: string; active: boolean;
  seed: string | number; positive: string; negative: string; actions?: ReactNode;
}) {
  const seedText = t(messageKey(String(seed)));
  const hasSeed = /^\d+$/.test(seedText);
  return <div className="image-prompt-details">
    <div className="image-detail-heading image-detail-title">
      <h2>{t("图片信息")}</h2>
      {actions}
    </div>
    <ImagePreferenceScore key={imageId} imageId={imageId} active={active} />
    <DetailField title={t("图像种子")} text={seedText} disabled={!hasSeed} />
    <DetailField title={t("正向提示词")} text={positive} />
    <DetailField title={t("负向提示词")} text={negative} />
  </div>;
}
