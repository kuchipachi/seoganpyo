"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import {
    ShieldAlert, Loader2, ExternalLink, RefreshCw,
    AlertTriangle, AlertOctagon, Info, CheckCircle2,
    Package, FileCode, Container, MoreHorizontal,
    Bug, Globe,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { SecurityChatSidebar } from "@/components/features/security-chat-sidebar"

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080"

function getAdminToken(): string | null {
    if (typeof document === "undefined") return null
    const match = document.cookie.match(/admin_token=([^;]+)/)
    return match ? match[1] : null
}

type Summary = {
    critical: number
    high: number
    medium: number
    low: number
    info: number
    total: number
    by_category: { pip: number; npm: number; dockerfile: number; sast: number; dast: number; other: number }
    last_updated: string | null
    engagement_url: string
}

type Finding = {
    id: number
    title: string
    severity: "Critical" | "High" | "Medium" | "Low" | "Info" | string
    cve: string | null
    cwe: number | null
    component_name: string | null
    component_version: string | null
    file_path: string | null
    description: string | null
    mitigation: string | null
    references: string | null
    found_date: string | null
    is_mitigated: boolean
    risk_accepted: boolean
    dd_url: string
    category: "pip" | "npm" | "dockerfile" | "sast" | "dast" | "other" | string
}

type Health = { connected: boolean; reason?: string; url?: string; engagement_id?: number }

const SEVERITY_TABS = ["전체", "Critical", "High", "Medium", "Low"] as const
const CATEGORY_TABS = [
    { key: "all",        label: "전체",            icon: ShieldAlert },
    { key: "pip",        label: "Python 의존성",   icon: Package },
    { key: "npm",        label: "Frontend 의존성", icon: FileCode },
    { key: "dockerfile", label: "Dockerfile",      icon: Container },
    { key: "sast",       label: "코드 결함 (SAST)", icon: Bug },
    { key: "dast",       label: "실행 결함 (DAST)", icon: Globe },
    { key: "other",      label: "기타",            icon: MoreHorizontal },
] as const

const SEVERITY_STYLE: Record<string, { bg: string; border: string; text: string; chip: string; icon: React.ElementType }> = {
    Critical: { bg: "bg-red-50 dark:bg-red-950/30",      border: "border-red-300 dark:border-red-800",      text: "text-red-700 dark:text-red-300",       chip: "bg-red-600 text-white",      icon: AlertOctagon },
    High:     { bg: "bg-orange-50 dark:bg-orange-950/30", border: "border-orange-300 dark:border-orange-800", text: "text-orange-700 dark:text-orange-300", chip: "bg-orange-500 text-white",   icon: AlertTriangle },
    Medium:   { bg: "bg-yellow-50 dark:bg-yellow-950/30", border: "border-yellow-300 dark:border-yellow-800", text: "text-yellow-800 dark:text-yellow-300", chip: "bg-yellow-500 text-black",   icon: AlertTriangle },
    Low:      { bg: "bg-blue-50 dark:bg-blue-950/30",     border: "border-blue-300 dark:border-blue-800",     text: "text-blue-700 dark:text-blue-300",     chip: "bg-blue-500 text-white",     icon: Info },
    Info:     { bg: "bg-gray-50 dark:bg-gray-800/30",     border: "border-gray-300 dark:border-gray-700",     text: "text-gray-700 dark:text-gray-300",     chip: "bg-gray-400 text-white",     icon: Info },
}

const CATEGORY_LABEL: Record<string, string> = {
    pip:        "Python 의존성",
    npm:        "Frontend 의존성",
    dockerfile: "Dockerfile",
    sast:       "코드 결함 (SAST)",
    dast:       "실행 결함 (DAST)",
    other:      "기타",
}

export default function AdminSecurityPage() {
    const router = useRouter()
    const [summary, setSummary] = useState<Summary | null>(null)
    const [findings, setFindings] = useState<Finding[]>([])
    const [health, setHealth] = useState<Health | null>(null)
    const [severityFilter, setSeverityFilter] = useState<typeof SEVERITY_TABS[number]>("전체")
    const [categoryFilter, setCategoryFilter] = useState<string>("all")
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState("")
    const [expandedId, setExpandedId] = useState<number | null>(null)

    const token = getAdminToken()

    const fetchAll = useCallback(async () => {
        if (!token) return
        setLoading(true)
        setError("")
        try {
            const headers = { Authorization: `Bearer ${token}` }
            const sevQs = severityFilter === "전체" ? "" : `?severity=${severityFilter}`
            const catQs = categoryFilter === "all" ? "" : (sevQs ? `&category=${categoryFilter}` : `?category=${categoryFilter}`)
            const [sumRes, findRes, healthRes] = await Promise.all([
                fetch(`${BASE_URL}/admin/security/summary`, { headers }),
                fetch(`${BASE_URL}/admin/security/findings${sevQs}${catQs}`, { headers }),
                fetch(`${BASE_URL}/admin/security/health`, { headers }),
            ])
            if (!sumRes.ok || !findRes.ok) throw new Error(`API 오류 (${sumRes.status})`)
            setSummary(await sumRes.json())
            const findData = await findRes.json()
            setFindings(findData.items || [])
            setHealth(healthRes.ok ? await healthRes.json() : { connected: false, reason: "헬스체크 실패" })
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "보안 데이터를 불러올 수 없습니다.")
            setHealth({ connected: false, reason: "API 응답 실패" })
        } finally {
            setLoading(false)
        }
    }, [token, severityFilter, categoryFilter])

    useEffect(() => {
        if (!token) { router.replace("/admin/login"); return }
        fetchAll()
    }, [token, router, fetchAll])

    return (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6 items-start">
            <div>
            {/* 헤더 */}
            <div className="mb-8 border-l-2 pl-4 flex items-start justify-between" style={{ borderColor: "#B0232A" }}>
                <div>
                    <h1 className="text-lg font-bold text-foreground flex items-center gap-2">
                        <ShieldAlert className="h-5 w-5" style={{ color: "#B0232A" }} />
                        보안 모니터링
                    </h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        DefectDojo의 자동 스캔 결과 — 운영 코드의 알려진 취약점·미스컨피그를 추적합니다.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <ConnectionStatus health={health} />
                    <Button size="sm" variant="outline" onClick={fetchAll} disabled={loading} className="gap-1.5">
                        <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                        새로고침
                    </Button>
                </div>
            </div>

            {error && (
                <div className="mb-6 rounded-lg border border-red-300 bg-red-50 dark:bg-red-950/30 p-4 text-sm text-red-700 dark:text-red-300">
                    <p className="font-semibold mb-1">데이터를 불러올 수 없습니다.</p>
                    <p className="text-xs">{error}</p>
                    <p className="text-xs mt-2 text-red-600/70">
                        DefectDojo 서버가 켜져있는지, DEFECTDOJO_URL·토큰이 .env에 있는지 확인하세요.
                    </p>
                </div>
            )}

            {/* 한 줄 위험 요약 — 사용자가 가장 먼저 봐야 하는 정보 */}
            {summary && (
                <RiskHeadline summary={summary} />
            )}

            {/* 심각도별 큰 카드 */}
            {summary && (
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
                    <SeverityCard label="CRITICAL" count={summary.critical} severity="Critical" />
                    <SeverityCard label="HIGH"     count={summary.high}     severity="High" />
                    <SeverityCard label="MEDIUM"   count={summary.medium}   severity="Medium" />
                    <SeverityCard label="LOW"      count={summary.low}      severity="Low" />
                    <SeverityCard label="INFO"     count={summary.info}     severity="Info" />
                </div>
            )}

            {/* 카테고리 분류 */}
            {summary && (
                <div className="mb-6 rounded-lg border border-border bg-card p-4">
                    <p className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wide">
                        영역별 분포
                    </p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                        <CategoryRow label="Python 의존성"   count={summary.by_category.pip}        icon={Package}            color="#3B82F6" />
                        <CategoryRow label="Frontend 의존성" count={summary.by_category.npm}        icon={FileCode}           color="#10B981" />
                        <CategoryRow label="Dockerfile"      count={summary.by_category.dockerfile} icon={Container}          color="#F59E0B" />
                        <CategoryRow label="코드 결함 (SAST)" count={summary.by_category.sast}      icon={Bug}                color="#A855F7" />
                        <CategoryRow label="실행 결함 (DAST)" count={summary.by_category.dast}      icon={Globe}              color="#EC4899" />
                        <CategoryRow label="기타"            count={summary.by_category.other}      icon={MoreHorizontal}     color="#6B7280" />
                    </div>
                </div>
            )}

            {/* 필터 */}
            <div className="mb-4 flex items-center justify-between flex-wrap gap-2">
                <div className="flex gap-1 rounded-lg border border-border bg-muted p-1">
                    {SEVERITY_TABS.map((s) => {
                        const active = severityFilter === s
                        return (
                            <button
                                key={s}
                                onClick={() => setSeverityFilter(s)}
                                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                                    active ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                                }`}
                            >
                                {s}
                            </button>
                        )
                    })}
                </div>

                <div className="flex flex-wrap gap-1 rounded-lg border border-border bg-muted p-1">
                    {CATEGORY_TABS.map(({ key, label, icon: Icon }) => {
                        const active = categoryFilter === key
                        return (
                            <button
                                key={key}
                                onClick={() => setCategoryFilter(key)}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                                    active ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                                }`}
                            >
                                <Icon className="h-3 w-3" />
                                {label}
                            </button>
                        )
                    })}
                </div>

                {summary && (
                    <a
                        href={summary.engagement_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs flex items-center gap-1 text-muted-foreground hover:text-foreground"
                    >
                        DefectDojo 전체 보기 <ExternalLink className="h-3 w-3" />
                    </a>
                )}
            </div>

            {/* Findings 리스트 */}
            {loading && (
                <div className="rounded-lg border border-dashed border-border py-16 text-center">
                    <Loader2 className="h-6 w-6 text-muted-foreground/50 animate-spin mx-auto" />
                </div>
            )}

            {!loading && findings.length === 0 && !error && (
                <div className="rounded-lg border border-dashed border-border py-16 text-center">
                    <CheckCircle2 className="h-8 w-8 text-green-500 mx-auto mb-3" />
                    <p className="text-sm text-foreground font-medium">현재 조건에 해당하는 취약점이 없습니다.</p>
                    <p className="text-xs text-muted-foreground mt-1">필터를 바꿔서 다른 항목을 조회해 보세요.</p>
                </div>
            )}

            {!loading && findings.length > 0 && (
                <div className="flex flex-col gap-2">
                    {findings.map((f) => (
                        <FindingCard
                            key={f.id}
                            finding={f}
                            expanded={expandedId === f.id}
                            onToggle={() => setExpandedId(expandedId === f.id ? null : f.id)}
                        />
                    ))}
                </div>
            )}
            </div>
            <SecurityChatSidebar />
        </div>
    )
}

// ── 컴포넌트들 ────────────────────────────────────────────────────────────

function ConnectionStatus({ health }: { health: Health | null }) {
    if (!health) return null
    const ok = health.connected
    return (
        <span
            className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full ${
                ok
                    ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                    : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
            }`}
        >
            <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-green-500" : "bg-red-500"}`} />
            {ok ? "DefectDojo 연결됨" : `연결 실패 — ${health.reason || "알 수 없음"}`}
        </span>
    )
}

function RiskHeadline({ summary }: { summary: Summary }) {
    const urgent = summary.critical + summary.high
    if (urgent === 0) {
        return (
            <div className="mb-6 rounded-lg border border-green-300 bg-green-50 dark:bg-green-950/30 px-4 py-3 flex items-center gap-3">
                <CheckCircle2 className="h-5 w-5 text-green-600 flex-shrink-0" />
                <p className="text-sm text-green-800 dark:text-green-300">
                    <strong>현재 즉시 조치가 필요한 취약점이 없습니다.</strong>
                </p>
            </div>
        )
    }
    return (
        <div className="mb-6 rounded-lg border border-red-300 bg-red-50 dark:bg-red-950/30 px-4 py-3 flex items-start gap-3">
            <AlertOctagon className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="text-sm">
                <p className="text-red-800 dark:text-red-300 font-semibold">
                    즉시 조치가 필요한 취약점 <span className="text-base">{urgent}건</span>
                </p>
                <p className="text-red-700/80 dark:text-red-400/80 text-xs mt-0.5">
                    {summary.critical > 0 && `CRITICAL ${summary.critical}건 (인증·실행 흐름 영향 가능). `}
                    {summary.high > 0 && `HIGH ${summary.high}건 (다음 릴리스 전 fix 권장). `}
                    아래 리스트에서 상세 확인 후 패키지 업그레이드 PR을 올려주세요.
                </p>
            </div>
        </div>
    )
}

function SeverityCard({ label, count, severity }: { label: string; count: number; severity: string }) {
    const s = SEVERITY_STYLE[severity] || SEVERITY_STYLE.Info
    const Icon = s.icon
    return (
        <div className={`rounded-lg border p-4 ${s.bg} ${s.border}`}>
            <div className="flex items-center gap-2 mb-2">
                <Icon className={`h-3.5 w-3.5 ${s.text}`} />
                <p className={`text-[10px] font-bold tracking-wide ${s.text}`}>{label}</p>
            </div>
            <p className={`text-3xl font-bold ${s.text}`}>{count}</p>
        </div>
    )
}

function CategoryRow({ label, count, icon: Icon, color }: { label: string; count: number; icon: React.ElementType; color: string }) {
    return (
        <div className="flex items-center gap-3 rounded-md bg-muted/50 px-3 py-2">
            <div className="rounded-md p-1.5" style={{ backgroundColor: `${color}20` }}>
                <Icon className="h-3.5 w-3.5" style={{ color }} />
            </div>
            <div className="flex-1 min-w-0">
                <p className="text-xs text-muted-foreground truncate">{label}</p>
                <p className="text-base font-semibold text-foreground">{count}</p>
            </div>
        </div>
    )
}

function FindingCard({ finding, expanded, onToggle }: { finding: Finding; expanded: boolean; onToggle: () => void }) {
    const s = SEVERITY_STYLE[finding.severity] || SEVERITY_STYLE.Info
    return (
        <div className={`rounded-lg border bg-card transition-shadow ${expanded ? "shadow-sm" : ""} ${s.border}`}>
            {/* 요약 행 (접힌 상태) */}
            <button
                onClick={onToggle}
                className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-muted/30 transition-colors"
            >
                <span className={`flex-shrink-0 rounded px-2 py-0.5 text-[10px] font-bold ${s.chip}`}>
                    {finding.severity.toUpperCase()}
                </span>
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                        {finding.title}
                    </p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap text-xs text-muted-foreground">
                        {finding.component_name && (
                            <span className="inline-flex items-center gap-1">
                                <Package className="h-3 w-3" />
                                {finding.component_name}
                                {finding.component_version && <span className="text-muted-foreground/70">{finding.component_version}</span>}
                            </span>
                        )}
                        {finding.cve && <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">{finding.cve}</span>}
                        {finding.category && <span className="text-muted-foreground/70">· {CATEGORY_LABEL[finding.category] || finding.category}</span>}
                    </div>
                </div>
                <span className="text-xs text-muted-foreground flex-shrink-0">
                    {expanded ? "접기" : "상세"}
                </span>
            </button>

            {/* 펼친 상태 */}
            {expanded && (
                <div className="border-t border-border px-4 py-4 flex flex-col gap-4 bg-muted/10">
                    {/* 핵심 정보 */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                        <InfoRow label="영향받는 파일" value={finding.file_path || "—"} mono />
                        <InfoRow label="패키지" value={finding.component_name ? `${finding.component_name} ${finding.component_version || ""}` : "—"} mono />
                        <InfoRow label="CVE" value={finding.cve || "—"} mono />
                        <InfoRow label="CWE" value={finding.cwe ? `CWE-${finding.cwe}` : "—"} mono />
                        <InfoRow label="발견일" value={finding.found_date || "—"} />
                        <InfoRow label="상태" value={finding.is_mitigated ? "완료" : finding.risk_accepted ? "수용" : "미해결"} />
                    </div>

                    {/* 설명 */}
                    {finding.description && (
                        <Section title="무엇이 문제인가">
                            <pre className="whitespace-pre-wrap text-xs text-foreground/80 leading-relaxed font-sans">
                                {truncate(finding.description, 800)}
                            </pre>
                        </Section>
                    )}

                    {/* 권장 조치 */}
                    {finding.mitigation && (
                        <Section title="권장 조치 (Mitigation)" highlight>
                            <pre className="whitespace-pre-wrap text-xs text-foreground/90 leading-relaxed font-sans">
                                {truncate(finding.mitigation, 600)}
                            </pre>
                        </Section>
                    )}

                    {/* 액션 */}
                    <div className="flex items-center justify-end gap-2">
                        <a
                            href={finding.dd_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                        >
                            <ExternalLink className="h-3 w-3" />
                            DefectDojo에서 상세 보기
                        </a>
                    </div>
                </div>
            )}
        </div>
    )
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
    return (
        <div className="flex flex-col gap-0.5">
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
            <span className={`text-foreground break-all ${mono ? "font-mono text-[11px]" : ""}`}>{value}</span>
        </div>
    )
}

function Section({ title, children, highlight }: { title: string; children: React.ReactNode; highlight?: boolean }) {
    return (
        <div className={`rounded-md ${highlight ? "border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/20" : "bg-muted/30"} px-3 py-2`}>
            <p className={`text-[10px] font-semibold uppercase tracking-wide mb-1 ${highlight ? "text-amber-800 dark:text-amber-300" : "text-muted-foreground"}`}>
                {title}
            </p>
            {children}
        </div>
    )
}

function truncate(text: string, maxLen: number): string {
    if (!text) return ""
    if (text.length <= maxLen) return text
    return text.slice(0, maxLen) + "…"
}
