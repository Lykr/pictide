import { useEffect, useState } from "react";
import { flushSync } from "react-dom";

/** Installed apps return with images covered until the user reveals them again. */
export function usePrivacyBlur() {
  const [privacyBlur, setPrivacyBlur] = useState(true);
  useEffect(() => {
    const displayMode = window.matchMedia("(display-mode: standalone)");
    // Keep installation identity when immersive mode changes the display mode.
    const installed = displayMode.matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
    const cover = () => {
      if (installed || displayMode.matches) {
        // Commit before suspension; React must not defer this until the app returns.
        flushSync(() => setPrivacyBlur(true));
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
  return [privacyBlur, setPrivacyBlur] as const;
}
