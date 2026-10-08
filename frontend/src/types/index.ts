export interface User {
  student_id: number
  name: string
  email: string
  current_semester: number | null
  interests: string
  target_careers: string
  major_credits: number
  common_credits: number
  total_credits: number
  total_english: number
}

export interface CourseDetail {
  required_skills: string | null
  evaluation_method: string | null
  teaching_method: string | null
  track_id: number | null
  keyword: string | null
  overview: string | null
  pdf_hash: string | null
  recommendation: string | null
}

export interface SyllabusSummary {
  course_id: number
  course_code: string | null
  year: number | null
  semester: number | null
  overview: string | null
  goals: string | null
  evaluation_method: string | null
  cached: boolean
}

export interface ProfessorDetail {
  email: string | null
  specialty: string | null
  research_area: string | null
  research_summary: string | null
  homepage: string | null
}

export interface Professor {
  professor_id: number
  name: string
  lab: string | null
  department: string | null
  details: ProfessorDetail | null
}

export interface Course {
  course_id: number
  course_code: string
  course_name: string
  credits: number | null
  target_grade: string | null
  is_english: boolean
  class_days: string | null
  class_start_time: string | null
  class_end_time: string | null
  professor_id: number | null
  professor: Professor | null
  year: number | null
  semester: number | null
  course_category: string | null
  details: CourseDetail | null
}

export interface CartItem {
  id: number
  student_id: number
  course_id: number
  course: Course | null
}

export interface Token {
  access_token: string
  token_type: string
}

export interface HistoryItem {
  id: number
  student_id: number
  course_code: string
  year: number | null
  semester: number | null
  is_retake: boolean
  course: Course | null
}

export interface Post {
  id: number
  category: string
  title: string
  content: string
  student_id: number
  author_name: string | null
  is_anonymous: boolean
  created_at: string
  comment_count: number
  likes: number
  file_path: string | null
  file_name: string | null
}

export interface Comment {
  id: number
  post_id: number
  content: string
  student_id: number
  author_name: string | null
  created_at: string
  likes: number
}

export interface PostDetail extends Post {
  comments: Comment[]
}

// 관리자 모니터링 — 사용자 요청 기준 API 메트릭 (GET /admin/metrics, Grafana Cloud Prometheus)
export type MetricsRange = "1h" | "24h" | "7d"

export interface MetricPoint {
  t: number           // epoch 초
  v: number | null    // 데이터 없음이면 null
}

export interface AdminMetrics {
  range: MetricsRange
  step_seconds: number
  rps: MetricPoint[]
  p95_ms: MetricPoint[]
  errors_5xx_rps: MetricPoint[]
  total_requests: number | null
  total_5xx: number | null
  api_up: boolean | null
}
