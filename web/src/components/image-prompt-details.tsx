import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, Copy, X } from "lucide-react";
import { IconButton } from "./actions";
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
      await navigator.clipboard.writeText(text);
      if (request.current === token) setStatus("success");
    } catch {
      if (request.current === token) setStatus("error");
    }
  };
  const feedback = status === "success" ? "已复制" : status === "error" ? "复制失败，请选中文本复制" : "";
  return <span className="image-detail-copy">
    <IconButton icon={status === "success" ? Check : status === "error" ? X : Copy}
      label={feedback ? `${title}：${feedback}` : `复制${title}`}
      disabled={disabled || !text || status === "copying"} onClick={copy} />
    <span className="sr-only" role="status">{feedback}</span>
  </span>;
}

function PromptText({ title, text }: { title: string; text: string }) {
  return <section className="image-prompt-section" aria-label={title}>
    <div className="image-detail-heading">
      <h3>{title}</h3>
      <CopyValue title={title} text={text} />
    </div>
    <pre className="image-prompt-text" tabIndex={text ? 0 : undefined}>{text || "（无）"}</pre>
  </section>;
}

export function ImagePromptDetails({ seed, positive, negative, actions }: {
  seed: string | number; positive: string; negative: string; actions?: ReactNode;
}) {
  const seedText = String(seed);
  const hasSeed = /^\d+$/.test(seedText);
  return <div className="image-prompt-details">
    <div className="image-detail-heading image-detail-title">
      <h2>图片信息</h2>
      {actions}
    </div>
    <div className="image-seed-row">
      <h3>图像种子</h3>
      <span className={hasSeed ? "image-seed-value" : "image-seed-unavailable"}>{seedText}</span>
      <CopyValue title="图像种子" text={seedText} disabled={!hasSeed} />
    </div>
    <PromptText title="正向提示词" text={positive} />
    <PromptText title="负向提示词" text={negative} />
  </div>;
}
