import { useEffect, useRef, useState } from "react";
import { Check, Copy, X } from "lucide-react";
import { IconButton } from "./actions";

function PromptText({ title, text }: { title: string; text: string }) {
  const [status, setStatus] = useState("idle");
  const request = useRef(0);
  useEffect(() => () => { request.current++; }, []);
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
  return <div>
    <div className="flex items-center justify-between gap-2">
      <h3>{title}</h3>
      <span className="relative">
        <IconButton icon={status === "success" ? Check : status === "error" ? X : Copy} label={feedback ? `${title}：${feedback}` : `复制${title}`} disabled={!text || status === "copying"} onClick={copy} />
        <span className="sr-only" role="status">{feedback}</span>
      </span>
    </div>
    <pre>{text || "（无）"}</pre>
  </div>;
}

export function ImagePromptDetails({ seed, positive, negative }: { seed: string | number; positive: string; negative: string }) {
  return <>
    <div><h3>图像种子</h3><span className="hint">{seed}</span></div>
    <PromptText title="正向提示词" text={positive} />
    <PromptText title="负向提示词" text={negative} />
  </>;
}
