import { useCallback, useEffect, useState } from "react";
import { flushSync } from "react-dom";
import "../styles/privacy.css";

/** Installed apps return with images covered until the user reveals them again. */
export function usePrivacyBlur() {
  const [privacy, setPrivacy] = useState({ blurred: true, covered: false });
  const setPrivacyBlur = useCallback((blurred: boolean) => {
    setPrivacy({ blurred, covered: false });
  }, []);
  useEffect(() => {
    const displayMode = window.matchMedia("(display-mode: standalone)");
    // Keep installation identity when immersive mode changes the display mode.
    const installed = displayMode.matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
    const cover = () => {
      if (installed || displayMode.matches) {
        // Hide original pixels without waiting for a new GPU blur surface.
        // The OS still controls when it snapshots or paints the suspended page.
        flushSync(() => setPrivacy({ blurred: true, covered: true }));
      }
    };
    document.addEventListener("visibilitychange", cover);
    window.addEventListener("blur", cover);
    window.addEventListener("pagehide", cover);
    return () => {
      document.removeEventListener("visibilitychange", cover);
      window.removeEventListener("blur", cover);
      window.removeEventListener("pagehide", cover);
    };
  }, []);
  return [privacy.blurred, setPrivacyBlur, privacy.covered] as const;
}
