import React, { useEffect, useRef, useState } from "react";

const LOTTIE_SCRIPT_SRC = "https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js";
let lottieLoaderPromise = null;

function ensureLottieLoader() {
  if (typeof window === "undefined") return Promise.reject(new Error("No window"));
  if (window.lottie) return Promise.resolve(window.lottie);
  if (lottieLoaderPromise) return lottieLoaderPromise;

  lottieLoaderPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${LOTTIE_SCRIPT_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve(window.lottie), { once: true });
      existing.addEventListener("error", () => reject(new Error("Failed to load lottie script")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = LOTTIE_SCRIPT_SRC;
    script.async = true;
    script.onload = () => resolve(window.lottie);
    script.onerror = () => reject(new Error("Failed to load lottie script"));
    document.head.appendChild(script);
  });

  return lottieLoaderPromise;
}

export default function GateMascotLottie({
  src = "/lottie/team-mascot.json",
  className = "",
  loop = true,
  autoplay = true,
}) {
  const containerRef = useRef(null);
  const animationRef = useRef(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let disposed = false;

    (async () => {
      try {
        const lottie = await ensureLottieLoader();
        if (disposed || !containerRef.current || !lottie) return;

        animationRef.current = lottie.loadAnimation({
          container: containerRef.current,
          renderer: "svg",
          loop,
          autoplay,
          path: src,
          rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
        });
      } catch {
        if (!disposed) setFailed(true);
      }
    })();

    return () => {
      disposed = true;
      if (animationRef.current) {
        animationRef.current.destroy();
        animationRef.current = null;
      }
    };
  }, [src, loop, autoplay]);

  if (failed) {
    return (
      <div className={className} aria-hidden="true">
        <div style={{ display: "grid", placeItems: "center", width: "100%", height: "100%", fontSize: "64px" }}>
          @
        </div>
      </div>
    );
  }

  return <div ref={containerRef} className={className} aria-hidden="true" />;
}
