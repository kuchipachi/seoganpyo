"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Loader2, CheckCircle, XCircle, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080"
// 빌드 시 NEXT_PUBLIC_GRAFANA_URL 이 비어 있으면(관측 스택 미연결) Grafana 섹션을 숨긴다.
const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL || ""

const DASHBOARDS = [
  { id: "seoganpyo-overview", label: "로그" },
  { id: "seoganpyo-metrics", label: "메트릭" },
  { id: "jmeter-loadtest", label: "부하 테스트" },
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
  const [activeDashboard, setActiveDashboard] = useState(DASHBOARDS[0].id)

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

      {/* Grafana 대시보드 탭 — 관측 스택 미연결 시 안내만 표시 */}
      {!GRAFANA_URL ? (
        <p className="mt-8 text-xs text-muted-foreground">
          상세 모니터링(Grafana)이 연결되지 않았습니다. 빌드 시 NEXT_PUBLIC_GRAFANA_URL 을 설정하면 대시보드가 표시됩니다.
        </p>
      ) : (
      <div className="mt-8">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs font-medium text-muted-foreground">상세 모니터링 (Grafana)</p>
          <div className="flex rounded-md border border-border overflow-hidden text-xs">
            {DASHBOARDS.map((d) => (
              <button
                key={d.id}
                onClick={() => setActiveDashboard(d.id)}
                className={`px-3 py-1.5 transition-colors ${
                  activeDashboard === d.id
                    ? "bg-foreground text-background font-medium"
                    : "bg-card text-muted-foreground hover:text-foreground"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-border overflow-hidden bg-card">
          <iframe
            key={activeDashboard}
            src={`${GRAFANA_URL}/d/${activeDashboard}/?orgId=1&kiosk=tv&theme=light&refresh=30s`}
            title="서간표 모니터링"
            className="w-full"
            style={{ height: 900, border: 0 }}
          />
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Grafana 직접 접속:{" "}
          <a
            href={GRAFANA_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-foreground"
          >
            {GRAFANA_URL}
          </a>
        </p>
      </div>
      )}
    </div>
  )
}
