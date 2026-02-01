import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

const GA_ID = import.meta.env.VITE_GA_MEASUREMENT_ID as string | undefined;
const isProd = import.meta.env.PROD;

export function initGtag() {
    if (!isProd || !GA_ID) return;
    if ((window as any).gtag) return; // already inited
    const s = document.createElement("script");
    s.async = true;
    s.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
    document.head.appendChild(s);

    window.dataLayer = window.dataLayer || [];
    (window as any).gtag = function () { (window as any).dataLayer.push(arguments); };
    (window as any).gtag("js", new Date());
    (window as any).gtag("config", GA_ID);
}

export function usePageViews() {
    const location = useLocation();
    const sentRef = useRef(false);
    useEffect(() => {
        if (!isProd || !GA_ID) return;
        // send page_view on route change
        (window as any).gtag?.("event", "page_view", {
            page_location: window.location.href,
            page_path: location.pathname + location.search,
            send_to: GA_ID,
        });
        sentRef.current = true;
    }, [location]);
}