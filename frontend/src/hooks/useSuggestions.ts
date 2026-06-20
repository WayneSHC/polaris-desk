"use client";
import { useState, useEffect, useRef } from "react";
import { API_BASE } from "@/lib/config";

interface SuggestionsData {
  suggestions: string[];
  source: "rule" | "llm";
  is_generating: boolean;
}

export function useSuggestions(options?: { mode?: "research" | "peer" }) {
  const mode = options?.mode ?? "research";
  const [suggestions, setSuggestions] = useState<string[] | null>(null);
  const [fading, setFading] = useState(false);
  const prevSource = useRef<"rule" | "llm" | null>(null);
  const hasScheduledRefetch = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchSuggestions = async (isRefetch: boolean) => {
    try {
      const res = await fetch(`${API_BASE}/suggestions?mode=${mode}`);
      if (!res.ok) return;
      const data: SuggestionsData = await res.json();

      const isUpgrade = isRefetch && prevSource.current === "rule" && data.source === "llm";

      if (isUpgrade) {
        setFading(true);
        setTimeout(() => {
          setSuggestions(data.suggestions);
          prevSource.current = data.source;
          setFading(false);
        }, 250);
      } else {
        setSuggestions(data.suggestions);
        prevSource.current = data.source;
      }

      if (data.is_generating && !hasScheduledRefetch.current) {
        hasScheduledRefetch.current = true;
        timerRef.current = setTimeout(() => fetchSuggestions(true), 3000);
      }
    } catch {
      // network failure — keep showing existing suggestions or PRESETS fallback
    }
  };

  useEffect(() => {
    fetchSuggestions(false);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { suggestions, fading };
}
