"use client";
import { useEffect, useRef, useState } from "react";
import { WS_URL } from "@/lib/api";
import type { Frame } from "@/lib/types";

export type StreamStatus = "connecting" | "live" | "closed";

export function useNowcastStream(horizon: number) {
  const [frame, setFrame] = useState<Frame | null>(null);
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const horizonRef = useRef(horizon);

  // push horizon changes to the server without reconnecting
  useEffect(() => {
    horizonRef.current = horizon;
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ horizon }));
  }, [horizon]);

  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      setStatus("connecting");
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => {
        setStatus("live");
        ws.send(JSON.stringify({ horizon: horizonRef.current }));
      };
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.type === "frame") setFrame({ ...m, receivedAt: performance.now() });
      };
      ws.onclose = () => {
        setStatus("closed");
        if (!closed) retry = setTimeout(connect, 1500);
      };
    };
    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      wsRef.current?.close();
    };
  }, []);

  return { frame, status };
}
