import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { FeedShell } from "./feed";
import { loadTheme } from "./controllers/theme.mjs";
import { TooltipLayer } from "./components/actions";
import { ControlLayer } from "./components/control-bridge";
import { ConfirmationLayer } from "./components/confirm-action";

let themeError = "";
try { await loadTheme(); } catch (error) { themeError = `主题读取失败：${error instanceof Error ? error.message : String(error)}`; }

const mount = document.getElementById("root");
if (!mount) throw new Error("Missing Pictide application mount.");
// There is one root and both workspaces stay mounted while navigation changes.
flushSync(() => createRoot(mount).render(<><FeedShell themeError={themeError} /><ControlLayer /><ConfirmationLayer /><TooltipLayer /></>));
await import("./controllers/app.js");
