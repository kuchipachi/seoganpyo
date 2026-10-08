"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Loader2, CheckCircle, XCircle, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ApiMetricsCharts } from "@/components/features/api-metrics-charts"

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080"
// Grafana Cloud (D10) — 차트는 백엔드(/admin/metrics)가 Prometheus 에서 가져와 직접 그린다.
// Grafana 대시보드는 iframe 으로 넣을 수 없어(frame-ancestors 'none') 로그·알림 룰은 링크로 연결 (로그인 필요).
// NEXT_PUBLIC_GRAFANA_URL 은 빌드 인자 — 비어 있으면 링크만 숨긴다.
const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL || ""

const GRAFANA_LINKS = [
  { uid: "seoganpyo-metrics", label: "메트릭 대시보드" },
  { uid: "seoganpyo-overview", label: "로그 대시보드" },
  { uid: "", label: "알림 룰", path: "/alerting/list" },
]

function getAdminToken() {
  if (typeof document === "undefined") return null
  const match = document.cookie.match(/admin_token=([^;]+)/)
  return match ? match[1] : null
}

type HealthData = {
  status: string
  admin: string
  stats: { users: number; posts: number; pending_reports: number }
}

export default function AdminMonitoringPage() {
  const router = useRouter()
  const [health, setHealth] = useState<HealthData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const [error, setError] = useState("")

  const token = getAdminToken()

  useEffect(() => {
    if (!token) { router.replace("/admin/login"); return }
    check()
  }, [])

  const check = () => {
    setIsLoading(true)
    setError("")
    fetch(`${BASE_URL}/admin/health`, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => { if (!res.ok) throw new Error("서버 응답 오류"); return res.json() })
      .then((data) => { setHealth(data); setLastChecked(new Date()) })
      .catch((err) => setError(err.message))
      .finally(() => setIsLoading(false))
  }

  return (
    <div>
      <div className="mb-8 border-l-2 pl-4" style={{ borderColor: "#B0232A" }}>
        <h1 className="text-lg font-bold text-foreground">모니터링</h1>
        <p className="mt-1 text-sm text-muted-foreground">서버 상태를 실시간으로 확인합니다.</p>
      </div>

      <div className="flex items-center gap-3 mb-6">
        <Button size="sm" variant="outline" onClick={check} disabled={isLoading} className="gap-1.5">
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
          새로고침
        </Button>
        {lastChecked && (
          <span className="text-xs text-muted-foreground">
            마지막 확인: {lastChecked.toLocaleTimeString("ko-KR")}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl">
        {/* API 서버 상태 */}
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-xs font-medium text-muted-foreground mb-3">API 서버</p>
          {isLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> 확인 중...
            </div>
          )}
          {!isLoading && health && (
            <div className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              <div>
                <p className="text-sm font-medium text-foreground">정상 운영중</p>
                <p className="text-xs text-muted-foreground mt-0.5">{BASE_URL}</p>
              </div>
            </div>
          )}
          {!isLoading && error && (
            <div className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-red-500" />
              <div>
                <p className="text-sm font-medium text-red-500">응답 없음</p>
                <p className="text-xs text-muted-foreground mt-0.5">{error}</p>
              </div>
            </div>
          )}
        </div>

        {/* DB 상태 (헬스체크 응답으로 간접 확인) */}
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-xs font-medium text-muted-foreground mb-3">데이터베이스</p>
          {isLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> 확인 중...
            </div>
          )}
          {!isLoading && health && (
            <div className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              <div>
                <p className="text-sm font-medium text-foreground">연결됨</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  유저 {health.stats.users}명 · 게시글 {health.stats.posts}건
                </p>
              </div>
            </div>
          )}
          {!isLoading && error && (
            <div className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-red-500" />
              <p className="text-sm text-red-500">연결 실패</p>
            </div>
          )}
        </div>

      </div>

      {/* API 메트릭 차트 (사용자 요청 기준) + Grafana Cloud 바로가기 */}
      <div className="mt-8">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <p className="text-xs font-medium text-muted-foreground">API 메트릭 (사용자 요청 기준)</p>
          {GRAFANA_URL && (
            <div className="flex flex-wrap gap-2 text-xs">
              {GRAFANA_LINKS.map((l) => (
                <a
                  key={l.label}
                  href={`${GRAFANA_URL}${l.path ?? `/d/${l.uid}`}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-md border border-border bg-card px-3 py-1.5 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {l.label} ↗
                </a>
              ))}
            </div>
          )}
        </div>
        <ApiMetricsCharts />
        <p className="mt-2 text-xs text-muted-foreground">
          헬스체크·메트릭 수집 요청은 제외합니다. 로그·알림 룰은 Grafana Cloud 에 로그인해서 확인하세요.
        </p>
      </div>
    </div>
  )
}
