import { Course, CartItem, Token, User, HistoryItem, SyllabusSummary, Post, PostDetail, Comment, Professor, AdminMetrics, MetricsRange } from "@/types"

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080"

function getToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem("access_token")
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  isMultipart = false
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  }
  // multipart/form-data는 브라우저가 Content-Type + boundary를 자동으로 설정
  if (!isMultipart) {
    headers["Content-Type"] = "application/json"
  }
  if (token) headers["Authorization"] = `Bearer ${token}`

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined" && path !== "/auth/login") {
      localStorage.removeItem("access_token")
      document.cookie = "access_token=; path=/; max-age=0"
      window.location.href = "/login"
    }
    const body = await res.json().catch(() => ({}))
    // FastAPI HTTPException(detail=dict) 형태 — 구조화된 에러
    if (body.detail && typeof body.detail === "object" && body.detail.title) {
      const err = new Error(body.detail.message || body.detail.title) as ApiError
      err.code = body.detail.code
      err.title = body.detail.title
      err.suggestion = body.detail.suggestion
      err.status = res.status
      throw err
    }
    throw new Error(body.detail || body.message || "요청에 실패했습니다.")
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export interface ApiError extends Error {
  code?: string
  title?: string
  suggestion?: string
  status?: number
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof Error && "title" in e
}

// ── Auth ──────────────────────────────────────────────
export const authApi = {
  sendEmail: (email: string) =>
    request<{ message: string }>("/auth/send-email", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  verifyCode: (email: string, code: string) =>
    request<{ message: string }>("/auth/verify-code", {
      method: "POST",
      body: JSON.stringify({ email, code }),
    }),

  register: (data: {
    student_id: number
    name: string
    email: string
    password: string
    current_semester?: number
  }) =>
    request<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  login: (email: string, password: string) =>
    request<Token>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  sendResetEmail: (email: string) =>
    request<{ message: string }>("/auth/reset-password/send-email", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  resetPassword: (email: string, code: string, new_password: string) =>
    request<{ message: string }>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ email, code, new_password }),
    }),
}

// ── Courses ───────────────────────────────────────────
export const coursesApi = {
  list: (params?: {
    q?: string
    category?: string
    division?: "major" | "liberal"
    year?: number
    semester?: number
    limit?: number
    offset?: number
  }) => {
    const qs = new URLSearchParams()
    if (params?.q) qs.set("q", params.q)
    if (params?.category) qs.set("category", params.category)
    if (params?.division) qs.set("division", params.division)
    if (params?.year) qs.set("year", String(params.year))
    if (params?.semester) qs.set("semester", String(params.semester))
    if (params?.limit) qs.set("limit", String(params.limit))
    if (params?.offset) qs.set("offset", String(params.offset))
    const query = qs.toString() ? `?${qs}` : ""
    return request<Course[]>(`/api/v1/courses${query}`)
  },

  get: (courseId: number) =>
    request<Course>(`/api/v1/courses/${courseId}`),

  getByCode: (courseCode: string) =>
    request<Course>(`/api/v1/courses/code/${courseCode}`),
}

// ── Cart ──────────────────────────────────────────────
export const cartApi = {
  get: () => request<CartItem[]>("/api/v1/cart"),

  add: (course_id: number) =>
    request<CartItem>("/api/v1/cart", {
      method: "POST",
      body: JSON.stringify({ course_id }),
    }),

  remove: (cartId: number) =>
    request<void>(`/api/v1/cart/${cartId}`, { method: "DELETE" }),
}

// ── Timetables (4-슬롯 후보 시간표) ───────────────────
export type SlotChar = "A" | "B" | "C" | "D"

// 슬롯 기본 라벨. 사용자가 별명 지정(Timetable.name) 하면 그쪽이 우선.
// 표시 헬퍼 displaySlotName 으로 항상 이쪽을 거치게 한다.
export const SLOT_LABELS: Record<SlotChar, string> = {
  A: "A",
  B: "B",
  C: "C",
  D: "D",
}

// 좁은 공간(검색 결과 카드의 슬롯 선택 dropdown 등) 용 — 현재는 길이가 같지만
// 따로 두어 UI 마다 표시 정책 다르게 갈 여지 남김.
export const SLOT_SHORT_LABELS: Record<SlotChar, string> = {
  A: "A",
  B: "B",
  C: "C",
  D: "D",
}

/** Timetable.name 이 있으면 그걸, 없으면 기본 라벨(A/B/C/D)을 돌려준다. */
export function displaySlotName(slot: SlotChar, name?: string | null): string {
  const trimmed = name?.trim()
  return trimmed ? trimmed : SLOT_LABELS[slot]
}

export interface TimetableCourseItem {
  course_id: number
  course?: Course | null
}

export interface Timetable {
  id: number
  slot: SlotChar
  name: string | null
  courses: TimetableCourseItem[]
}

export const timetablesApi = {
  // A/B/C/D 4 슬롯 모두 (없으면 백엔드가 자동 생성)
  list: () => request<Timetable[]>("/api/v1/timetables"),

  get: (slot: SlotChar) =>
    request<Timetable>(`/api/v1/timetables/${slot}`),

  addCourse: (slot: SlotChar, course_id: number) =>
    request<Timetable>(`/api/v1/timetables/${slot}/courses`, {
      method: "POST",
      body: JSON.stringify({ course_id }),
    }),

  removeCourse: (slot: SlotChar, course_id: number) =>
    request<void>(`/api/v1/timetables/${slot}/courses/${course_id}`, {
      method: "DELETE",
    }),

  rename: (slot: SlotChar, name: string) =>
    request<Timetable>(`/api/v1/timetables/${slot}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),

  // 비교 화면용 — 여러 슬롯을 한 번에. body 는 ["A","B"] 형태 배열.
  compare: (slots: SlotChar[]) =>
    request<Timetable[]>("/api/v1/timetables/compare", {
      method: "POST",
      body: JSON.stringify(slots),
    }),
}

// ── Users ─────────────────────────────────────────────
export const usersApi = {
  me: () => request<User>("/api/v1/users/me"),

  update: (data: { current_semester?: number; interests?: string[] }) =>
    request<User>("/api/v1/users/me", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  deleteMe: () =>
    request<void>("/api/v1/users/me", { method: "DELETE" }),
}

// ── History ───────────────────────────────────────────
export const historyApi = {
  getMyHistories: () => request<HistoryItem[]>("/history/me"),

  add: (data: { course_code: string; year: number; semester: number; is_retake?: boolean }) =>
    request<HistoryItem>("/history", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (historyId: number, data: { year?: number; semester?: number; is_retake?: boolean }) =>
    request<HistoryItem>(`/history/${historyId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  remove: (historyId: number) =>
    request<void>(`/history/${historyId}`, { method: "DELETE" }),

  removeAll: () =>
    request<{ message: string; deleted: number }>("/history/me", { method: "DELETE" }),
}

// ── Syllabus ──────────────────────────────────────────
export const syllabusApi = {
  summarize: (file: File) => {
    const formData = new FormData()
    formData.append("file", file)
    return request<SyllabusSummary>("/api/v1/syllabus/summarize", {
      method: "POST",
      body: formData,
    }, true)
  },

  get: (courseId: number) =>
    request<SyllabusSummary>(`/api/v1/syllabus/${courseId}`),
}

// ── Community ─────────────────────────────────────────
export const communityApi = {
  getPosts: (category: string) =>
    request<Post[]>(`/api/v1/community/${encodeURIComponent(category)}`),

  createPost: (category: string, title: string, content: string, isAnonymous: boolean, file?: File | null) => {
    const formData = new FormData()
    formData.append("title", title)
    formData.append("content", content)
    formData.append("is_anonymous", String(isAnonymous))
    if (file) formData.append("file", file)
    return request<Post>(`/api/v1/community/${encodeURIComponent(category)}`, {
      method: "POST",
      body: formData,
    }, true)
  },

  getPost: (category: string, postId: number) =>
    request<PostDetail>(`/api/v1/community/${encodeURIComponent(category)}/${postId}`),

  deletePost: (category: string, postId: number) =>
    request<void>(`/api/v1/community/${encodeURIComponent(category)}/${postId}`, { method: "DELETE" }),

  createComment: (category: string, postId: number, content: string) =>
    request<Comment>(`/api/v1/community/${encodeURIComponent(category)}/${postId}/comments`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  deleteComment: (category: string, postId: number, commentId: number) =>
    request<void>(`/api/v1/community/${encodeURIComponent(category)}/${postId}/comments/${commentId}`, { method: "DELETE" }),

  toggleLike: (category: string, postId: number) =>
    request<{ liked: boolean; likes: number }>(`/api/v1/community/${encodeURIComponent(category)}/${postId}/like`, { method: "POST" }),

  updatePost: (category: string, postId: number, data: { title?: string; content?: string }) =>
    request<Post>(`/api/v1/community/${encodeURIComponent(category)}/${postId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  toggleCommentLike: (category: string, postId: number, commentId: number) =>
    request<{ liked: boolean; likes: number }>(`/api/v1/community/${encodeURIComponent(category)}/${postId}/comments/${commentId}/like`, { method: "POST" }),

  reportPost: (category: string, postId: number, reason: string, detail?: string) =>
    request<{ message: string }>(`/api/v1/community/${encodeURIComponent(category)}/${postId}/report`, {
      method: "POST",
      body: JSON.stringify({ reason, detail }),
    }),
}

// ── Contact ───────────────────────────────────────────
export const contactApi = {
  send: (subject: string, content: string) =>
    request<{ message: string }>("/api/v1/contact", {
      method: "POST",
      body: JSON.stringify({ subject, content }),
    }),
}

// ── Professors ────────────────────────────────────────
export const professorsApi = {
  list: (params?: { q?: string }) => {
    const qs = new URLSearchParams()
    if (params?.q) qs.set("q", params.q)
    const query = qs.toString() ? `?${qs}` : ""
    return request<Professor[]>(`/api/v1/professors${query}`)
  },

  get: (professorId: number) =>
    request<Professor>(`/api/v1/professors/${professorId}`),
}

// ── User Messages ─────────────────────────────────────
export const messagesApi = {
  getUnread: () => request<AdminMessageItem[]>("/api/v1/users/me/messages/unread"),
  markRead: (id: number) =>
    request<void>(`/api/v1/users/me/messages/${id}/read`, { method: "PATCH" }),
}

// ── Admin ─────────────────────────────────────────────
function getAdminToken(): string | null {
  if (typeof document === "undefined") return null
  const match = document.cookie.match(/admin_token=([^;]+)/)
  return match ? match[1] : null
}

async function adminRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAdminToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  }
  if (token) headers["Authorization"] = `Bearer ${token}`
  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || "요청에 실패했습니다.")
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export interface AdminReport {
  id: number
  reporter_id: number | null
  reporter_name: string | null
  target_type: string
  target_id: number
  target_title: string | null
  target_content: string | null
  target_author: string | null
  target_category: string | null
  reason: string
  detail: string | null
  status: string
  created_at: string
}

export interface AdminContact {
  id: number
  student_id: number | null
  sender_name: string | null
  sender_email: string | null
  subject: string
  content: string
  status: string
  created_at: string
}

export interface AdminUser {
  student_id: number
  name: string
  email: string
  role: string
  can_post: boolean
  can_comment: boolean
  current_semester: number | null
}

export interface AdminMessageItem {
  id: number
  content: string
  sender_name: string | null
  created_at: string
}

export interface AdminPost {
  id: number
  category: string
  title: string
  content: string
  author_name: string | null
  is_anonymous: boolean
  student_id: number | null
  comment_count: number
  like_count: number
  file_path: string | null
  file_name: string | null
  created_at: string
}

export interface AdminPostComment {
  id: number
  content: string
  author_name: string | null
  student_id: number | null
  created_at: string
}

export const adminApi = {
  // 모니터링 차트 — 백엔드가 Grafana Cloud Prometheus 에서 가져온 사용자 요청 메트릭 (30초 캐시)
  getMetrics: (range: MetricsRange = "1h") =>
    adminRequest<AdminMetrics>(`/admin/metrics?range=${range}`),

  // 신고 관리
  getReportCounts: () =>
    adminRequest<{ total: number; 욕설: number; 스팸: number; 기타: number }>("/admin/reports/counts"),

  getReports: (params?: { status?: string; reason?: string }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set("status", params.status)
    if (params?.reason) qs.set("reason", params.reason)
    return adminRequest<AdminReport[]>(`/admin/reports?${qs}`)
  },

  resolveReport: (id: number) =>
    adminRequest<{ message: string; report_id: number }>(`/admin/reports/${id}`, { method: "PATCH" }),

  dismissReport: (id: number) =>
    adminRequest<{ message: string; report_id: number }>(`/admin/reports/${id}/dismiss`, { method: "PATCH" }),

  // 문의 관리
  getContactCounts: () =>
    adminRequest<{ total: number }>("/admin/contacts/counts"),

  getContacts: (params?: { status?: string }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set("status", params.status)
    return adminRequest<AdminContact[]>(`/admin/contacts?${qs}`)
  },

  resolveContact: (id: number) =>
    adminRequest<{ message: string }>(`/admin/contacts/${id}/resolve`, { method: "PATCH" }),

  dismissContact: (id: number) =>
    adminRequest<{ message: string }>(`/admin/contacts/${id}/dismiss`, { method: "PATCH" }),

  // 사용자 관리
  getUsers: (q?: string) => {
    const qs = q ? `?q=${encodeURIComponent(q)}` : ""
    return adminRequest<AdminUser[]>(`/admin/users${qs}`)
  },

  toggleCanPost: (studentId: number) =>
    adminRequest<{ student_id: number; can_post: boolean }>(`/admin/users/${studentId}/can-post`, { method: "PATCH" }),

  toggleCanComment: (studentId: number) =>
    adminRequest<{ student_id: number; can_comment: boolean }>(`/admin/users/${studentId}/can-comment`, { method: "PATCH" }),

  sendMessage: (studentId: number, content: string) =>
    adminRequest<{ message: string }>(`/admin/users/${studentId}/message`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  // 게시글 관리
  getPostCategories: () =>
    adminRequest<{ category: string; count: number }[]>("/admin/posts/categories"),

  getAllPosts: (category?: string) => {
    const qs = category ? `?category=${encodeURIComponent(category)}` : ""
    return adminRequest<AdminPost[]>(`/admin/posts${qs}`)
  },

  getPostComments: (postId: number) =>
    adminRequest<AdminPostComment[]>(`/admin/posts/${postId}/comments`),

  deletePost: (postId: number) =>
    adminRequest<{ message: string }>(`/admin/posts/${postId}`, { method: "DELETE" }),

  deleteComment: (commentId: number) =>
    adminRequest<{ message: string }>(`/admin/comments/${commentId}`, { method: "DELETE" }),

  deleteUser: (studentId: number) =>
    adminRequest<{ message: string }>(`/admin/users/${studentId}`, { method: "DELETE" }),

  updateUserInfo: (studentId: number, data: {
    new_student_id?: number
    name?: string
    email?: string
    current_semester?: number | null
  }) =>
    adminRequest<{ student_id: number; name: string; email: string; current_semester: number | null }>(
      `/admin/users/${studentId}/info`,
      { method: "PATCH", body: JSON.stringify(data) }
    ),

  resetPassword: (studentId: number, newPassword: string) =>
    adminRequest<{ message: string }>(`/admin/users/${studentId}/password`, {
      method: "PATCH",
      body: JSON.stringify({ new_password: newPassword }),
    }),

  // 운영 어시스턴트 (Gemini tool use)
  askAssistant: (message: string, history: AssistantMessage[] = []) =>
    adminRequest<AssistantAskResponse>("/admin/chat/ask", {
      method: "POST",
      body: JSON.stringify({ message, history }),
    }),

  listAssistantTools: () =>
    adminRequest<AssistantToolMeta[]>("/admin/chat/tools"),

  // 보안 모니터링 사이드바 챗 (Gemini tool use, DefectDojo 전용 도구 5개)
  askSecurityChat: (message: string, history: AssistantMessage[] = []) =>
    adminRequest<AssistantAskResponse>("/admin/security/chat/ask", {
      method: "POST",
      body: JSON.stringify({ message, history }),
    }),

  listSecurityChatTools: () =>
    adminRequest<AssistantToolMeta[]>("/admin/security/chat/tools"),
}

export interface AssistantMessage {
  role: "user" | "model"
  content: string
}

export interface AssistantToolCall {
  name: string
  args: Record<string, unknown>
  result: unknown
  duration_ms: number
}

export interface AssistantAskResponse {
  answer: string
  tool_calls: AssistantToolCall[]
  iterations: number
  model: string
}

export interface AssistantToolMeta {
  name: string
  description: string
  params: Record<string, { type: string; required?: boolean; description: string }>
}

// ── Portfolio ─────────────────────────────────────────
export type PortfolioKind =
  | "campus_activity"
  | "external_activity"
  | "certificate"
  | "award"
  | "project"

export interface PortfolioEntry {
  id: number
  kind: PortfolioKind
  title: string | null
  content: string | null
  entry_date: string | null
  order_index: number
  created_at: string
  updated_at: string
}

export type PortfolioBySection = Record<PortfolioKind, PortfolioEntry[]>

export interface PortfolioBulkItem {
  id?: number | null
  title?: string | null
  content?: string | null
  entry_date?: string | null
  order_index?: number
}

export type EvaluationStatus = "pending" | "running" | "completed" | "failed"

export interface PortfolioEvaluation {
  id: number
  status: EvaluationStatus
  error_message: string | null
  // 0~6 정수 — UI 에서 /2 해서 0~3 별점(0.5 단위) 표시.
  alignment_score: number | null
  // 4 차원 별점 — { skill_fit, depth, concreteness, breadth } 각 0~6.
  rubric: Record<string, number>
  // 5 섹션 별점 — { campus_activity, external_activity, ... } 각 0~6.
  section_scores: Record<string, number>
  summary: string | null
  strengths: string[]
  weaknesses: string[]
  suggestions: string[]
  by_section: Record<string, string>
  model_name: string | null
  created_at: string
  completed_at: string | null
}

export const portfolioApi = {
  getMine: () => request<PortfolioBySection>("/api/v1/portfolio"),

  bulkSave: (sections: Record<PortfolioKind, PortfolioBulkItem[]>) =>
    request<PortfolioBySection>("/api/v1/portfolio/bulk", {
      method: "PUT",
      body: JSON.stringify(sections),
    }),

  // 전체 초기화 — 모든 항목과 평가 이력 삭제
  resetAll: () =>
    request<void>("/api/v1/portfolio/all", {
      method: "DELETE",
    }),

  // 평가 요청 — 즉시 pending 응답 반환 (백그라운드 처리)
  evaluate: () =>
    request<PortfolioEvaluation>("/api/v1/portfolio/evaluate", {
      method: "POST",
    }),

  // 특정 평가 폴링용
  getEvaluation: (id: number) =>
    request<PortfolioEvaluation>(`/api/v1/portfolio/evaluate/${id}`),

  getLatestEvaluation: () =>
    request<PortfolioEvaluation | null>("/api/v1/portfolio/evaluate/latest"),
}
