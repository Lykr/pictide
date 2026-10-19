import { t } from "../i18n/index.mjs";
import { useEffect, useState } from "react";
import { Download, Info } from "lucide-react";
import { IconButton } from "./actions";
import { Button } from "./ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { ImagePromptDetails } from "./image-prompt-details";

type ImageDetails = { id: string; seed: string; positive: string; negative: string };

export function ImageInfo() {
  const [image, setImage] = useState<ImageDetails | null>(null);
  const [open, setOpen] = useState(false);
  const [container, setContainer] = useState<HTMLElement | undefined>();
  useEffect(() => {
    const receive = (event: Event) => {
      const next = (event as CustomEvent<ImageDetails | null>).detail;
      setImage(next);
      if (!next) setOpen(false);
    };
    const close = () => setOpen(false);
    document.addEventListener("pictide:image-info", receive);
    document.addEventListener("pictide:close-image-info", close);
    return () => {
      document.removeEventListener("pictide:image-info", receive);
      document.removeEventListener("pictide:close-image-info", close);
    };
  }, []);
  return <>
    <Popover open={open && !!image} onOpenChange={next => {
      setContainer(document.querySelector<HTMLElement>("#image-card.immersive") ?? undefined);
      setOpen(next);
    }}>
    <PopoverTrigger asChild><IconButton icon={Info} label={t("图片信息")} disabled={!image} /></PopoverTrigger>
    <PopoverContent container={container} className="image-info-popover image-details-popover" align="start" side="top" aria-label={t("图片信息")}>
      {image && <ImagePromptDetails key={image.id} imageId={image.id} active={open && !!image} seed={image.seed} positive={image.positive} negative={image.negative}
        actions={<Button asChild variant="ghost" size="icon-sm"><a href={`/api/artifacts/${encodeURIComponent(image.id)}/prompts`} aria-label={t("下载提示词 JSON")} data-tooltip={t("下载提示词 JSON")} download><Download aria-hidden="true" /></a></Button>} />}
    </PopoverContent>
    </Popover>
  </>;
}
