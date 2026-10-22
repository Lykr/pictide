import { useSyncExternalStore } from 'react';
import { snapshot, subscribe, tr } from './i18n/index.mjs';
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { FeedShell } from "./feed";
import { loadTheme } from "./controllers/theme.mjs";
import { TooltipLayer } from "./components/actions";
import { createApplication } from "./controllers/app.js";
import { ApplicationContext } from "./shared/application-context";
import { ConfirmationLayer } from "./components/confirm-action";
import { GuideLayer } from "./components/onboarding/guide-layer";
import { NotificationLayer } from "./components/notifications";

let themeError = "";
try { await loadTheme(); } catch (error) { themeError = tr`主题读取失败：${error instanceof Error ? error.message : String(error)}`; }

const mount = document.getElementById("root");
if (!mount) throw new Error("Missing Pictide application mount.");
// There is one root and both workspaces stay mounted while navigation changes.
const application = createApplication();
function Application() {
  useSyncExternalStore(subscribe, snapshot);
  return <ApplicationContext.Provider value={application}><FeedShell themeError={themeError} /><ConfirmationLayer /><TooltipLayer /><GuideLayer /><NotificationLayer /></ApplicationContext.Provider>;
}
flushSync(() => createRoot(mount).render(<Application />));
