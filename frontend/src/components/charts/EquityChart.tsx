"use client";

import { useEffect, useRef } from "react";

import type { EquityPoint } from "@/types";

export function EquityChart({ data, height = 220 }: { data: EquityPoint[]; height?: number }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<any>(null);
  const seriesRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    let resizeObserver: ResizeObserver | null = null;

    void import("lightweight-charts").then(({ createChart, LineStyle }) => {
      if (!containerRef.current) {
        return;
      }

      chartRef.current?.remove();
      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height,
        layout: { background: { color: "transparent" }, textColor: "#64748b" },
        grid: {
          vertLines: { color: "#1e1e2e", style: LineStyle.Dotted },
          horzLines: { color: "#1e1e2e", style: LineStyle.Dotted }
        },
        rightPriceScale: { borderColor: "#1e1e2e" },
        timeScale: { borderColor: "#1e1e2e", timeVisible: true }
      });

      const series = chart.addAreaSeries({
        lineColor: "#00ff88",
        topColor: "rgba(0,255,136,0.22)",
        bottomColor: "rgba(0,255,136,0.02)"
      });

      chartRef.current = chart;
      seriesRef.current = series;

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
      seriesRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    if (!seriesRef.current || !data.length) {
      return;
    }
    seriesRef.current.setData(data);
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  if (!data.length) {
    return <div className="flex items-center justify-center text-sm text-slate-600" style={{ height }}>No equity data yet</div>;
  }

  return <div ref={containerRef} style={{ height }} className="w-full" />;
}
