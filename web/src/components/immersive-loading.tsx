import { useSyncExternalStore } from "react";
import { LoaderCircle } from "lucide-react";
import { t } from "../i18n/index.mjs";
import { getUiState, subscribeUiState } from "../shared/ui-state.mjs";
import "../styles/immersive-loading.css";

export function ImmersiveLoading({ loading }: { loading: boolean }) {
  if (!loading) return null;
  return <span className="immersive-loading" role="status" aria-label={t("图片加载中")}>
    <LoaderCircle aria-hidden="true" />
  </span>;
}

export function RoamImmersiveLoading() {
  const facts = useSyncExternalStore(subscribeUiState, getUiState) as Record<string, unknown>;
  return <ImmersiveLoading loading={facts.waiting === true || facts.imageLoading === true} />;
}
