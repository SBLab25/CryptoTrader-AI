"use client";

import { useEffect, useRef } from "react";

import type { OHLCV } from "@/types";

export function CandlestickChart({ data, height = 280 }: { data: OHLCV[]; height?: number }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<any>(null);
  const candleRef = useRef<any>(null);
  const volumeRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }
    let resizeObserver: ResizeObserver | null = null;

    void import("lightweight-charts").then(({ createChart, CrosshairMode, LineStyle }) => {
      if (!containerRef.current) {
        return;
      }
      chartRef.current?.remove();
      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height,
        layout: { background: { color: "transparent" }, textColor: "#64748b" },
        crosshair: { mode: CrosshairMode.Normal },
        grid: {
          vertLines: { color: "#1e1e2e", style: LineStyle.Dotted },
          horzLines: { color: "#1e1e2e", style: LineStyle.Dotted }
        },
        rightPriceScale: { borderColor: "#1e1e2e" },
        timeScale: { borderColor: "#1e1e2e", timeVisible: true }
      });

      candleRef.current = chart.addCandlestickSeries({
        upColor: "#00ff88",
        downColor: "#ff4466",
        wickUpColor: "#00ff88",
        wickDownColor: "#ff4466",
        borderVisible: false
      });
      volumeRef.current = chart.addHistogramSeries({
        color: "#00ff88",
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
        scaleMargins: { top: 0.78, bottom: 0 }
      });
      chartRef.current = chart;

      resizeObserver = new ResizeObserver((entries) => {
        const entry = entries[0];
        chart.resize(entry.contentRect.width, height);
      });
      resizeObserver.observe(containerRef.current);
    });

    return () => {
      resizeObserver?.disconnect();
      chartRef.current?.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    if (!candleRef.current || !volumeRef.current || !data.length) {
      return;
    }
    candleRef.current.setData(
      data.map((item) => ({
        time: item.time,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close
      }))
    );
    volumeRef.current.setData(
      data.map((item) => ({
        time: item.time,
        value: item.volume,
        color: item.close >= item.open ? "rgba(0,255,136,0.25)" : "rgba(255,68,102,0.25)"
      }))
    );
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return <div ref={containerRef} className="w-full" style={{ height }} />;
}
