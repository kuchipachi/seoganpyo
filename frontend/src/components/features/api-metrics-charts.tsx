"use client"

import { useEffect, useState } from "react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { Loader2 } from "lucide-react"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { adminApi } from "@/lib/api"
import type { AdminMetrics, MetricPoint, MetricsRange } from "@/types"

// 관리자 모니터링 차트 (D10) — Grafana Cloud 대시보드는 iframe 으로 넣을 수 없어(frame-ancestors 'none')
// 백엔드가 Prometheus 에서 가져온 숫자를 여기서 그린다. 사용자 요청 기준 (/metrics·헬스체크 제외).

const RANGES: { key: MetricsRange; label: string }[] = [
  { key: "1h", label: "1시간" },
  { key: "24h", label: "24시간" },
  { key: "7d", label: "7일" },
]

const CHARTS: {
  key: "rps" | "p95_ms" | "errors_5xx_rps"
  title: string
  unit: string
  color: string
  digits: number
}[] = [
  { key: "rps", title: "초당 요청 수", unit: "req/s", color: "#2563eb", digits: 2 },
  { key: "p95_ms", title: "응답 시간 p95", unit: "ms", color: "#d97706", digits: 0 },
  { key: "errors_5xx_rps", title: "5xx 에러", unit: "req/s", color: "#B0232A", digits: 3 },
]

function formatTime(t: number, range: MetricsRange) {
  const d = new Date(t * 1000)
  return range === "7d"
    ? `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}시`
    : d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false })
}

function hasValue(points: MetricPoint[]) {
  return points.some((p) => p.v !== null && p.v > 0)
}

export function ApiMetricsCharts() {
  const [range, setRange] = useState<MetricsRange>("1h")
  const [data, setData] = useState<AdminMetrics | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const load = () => {
      setLoading(true)
      adminApi
        .getMetrics(range)
        .then((d) => { if (!cancelled) { setData(d); setError("") } })
        .catch((e: Error) => { if (!cancelled) setError(e.message) })
        .finally(() => { if (!cancelled) setLoading(false) })
    }
    load()
    const timer = setInterval(load, 60_000) // 백엔드 캐시 30초 — 1분마다 갱신
    return () => { cancelled = true; clearInterval(timer) }
  }, [range])

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {data && (
            <>
              <span>
                API{" "}
                <span className={data.api_up ? "text-green-600" : "text-red-500"}>
                  {data.api_up === null ? "확인 불가" : data.api_up ? "정상" : "응답 없음"}
                </span>
              </span>
              <span>요청 {Math.round(data.total_requests ?? 0).toLocaleString()}건</span>
              <span>5xx {Math.round(data.total_5xx ?? 0).toLocaleString()}건</span>
            </>
          )}
          {loading && <Loader2 className="h-3 w-3 animate-spin" />}
        </div>
        <div className="flex rounded-md border border-border overflow-hidden text-xs">
          {RANGES.map((r) => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              className={`px-3 py-1.5 transition-colors ${
                range === r.key
                  ? "bg-foreground text-background font-medium"
                  : "bg-card text-muted-foreground hover:text-foreground"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-xs text-red-500 mb-3">메트릭을 불러오지 못했습니다: {error}</p>}

      <div className="grid gap-4 md:grid-cols-3">
        {CHARTS.map((c) => {
          const points = data?.[c.key] ?? []
          const config: ChartConfig = { v: { label: c.title, color: c.color } }
          return (
            <div key={c.key} className="rounded-lg border border-border bg-card p-4">
              <p className="text-xs font-medium text-muted-foreground mb-2">
                {c.title} <span className="font-normal">({c.unit})</span>
              </p>
              {data && !hasValue(points) ? (
                <div className="flex aspect-video items-center justify-center text-xs text-muted-foreground">
                  {c.key === "errors_5xx_rps" ? "에러 없음" : "이 기간 사용자 요청 없음"}
                </div>
              ) : (
                <ChartContainer config={config}>
                  <AreaChart data={points} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
                    <CartesianGrid vertical={false} />
                    <XAxis
                      dataKey="t"
                      tickFormatter={(t: number) => formatTime(t, range)}
                      tickLine={false}
                      axisLine={false}
                      minTickGap={32}
                    />
                    <YAxis width={40} tickLine={false} axisLine={false} />
                    <ChartTooltip
                      content={
                        <ChartTooltipContent
                          labelFormatter={(_, p) => formatTime(Number(p?.[0]?.payload?.t), range)}
                          formatter={(v) => `${Number(v).toFixed(c.digits)} ${c.unit}`}
                        />
                      }
                    />
                    <Area
                      dataKey="v"
                      type="monotone"
                      stroke="var(--color-v)"
                      fill="var(--color-v)"
                      fillOpacity={0.15}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ChartContainer>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
