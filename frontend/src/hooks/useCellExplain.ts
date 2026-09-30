"use client";
import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";
import type { Why } from "@/lib/types";

/** Fetches the drivers of the recent risk change for one cell; refreshes on every new tick. */
export function useCellExplain(cellIndex: number | null, tick: number) {
  const [why, setWhy] = useState<Why | null>(null);
  useEffect(() => {
    if (cellIndex === null) { setWhy(null); return; }
    let live = true;
    fetch(`${API_URL}/api/explain/cell/${cellIndex}`)
      .then((r) => r.json())
      .then((d) => { if (live) setWhy(d); })
      .catch(() => {});
    return () => { live = false; };
  }, [cellIndex, tick]);
  return why;
}