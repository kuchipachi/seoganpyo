// 서간표 부하 테스트 (k6) — 측정 방법은 docs/performance.md §2
//
// open model(도착률 고정): 서버가 느려져도 요청 발생률이 줄지 않아 꼬리 지연이 숨지 않는다
// (closed model 의 coordinated omission 회피). 1 iteration = 사용자 행동 1회.
//
// 사용법:
//   k6 run -e PROFILE=smoke  infra/loadtest/k6/seoganpyo.js
//   k6 run -e PROFILE=load   -e BASE=https://<EC2_IP>.nip.io infra/loadtest/k6/seoganpyo.js
//   PROFILE: smoke | load | stress | breakpoint
//   (scripts/loadtest/run.sh 가 서버 지표 수집·결과 저장까지 묶어서 실행)
import http from 'k6/http';
import { check } from 'k6';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.1.0/index.js';

const BASE = __ENV.BASE;  // 공개 레포라 운영 주소를 코드에 두지 않음 — run.sh 가 넘긴다
if (!BASE) throw new Error('BASE 필요 — 예) -e BASE=https://<EC2_IP>.nip.io');
const API = `${BASE}${__ENV.API_PREFIX ?? '/backend'}`;
const PROFILE = __ENV.PROFILE || 'smoke';
const RUN_ID = __ENV.RUN_ID || `${PROFILE}-local`;

// 적재된 데이터 기준 (2026-1, 강의 37개 / 교수 28명) — 캐시 착시를 줄이려고 요청마다 무작위 선택
const COURSE_IDS = Array.from({ length: 37 }, (_, i) => i + 1);
const SEARCH_TERMS = ['프로그래밍', '자료구조', '머신러닝', '시스템', '네트워크', '데이터베이스',
  '알고리즘', '캡스톤', '그래픽스', '김지환', '박성용', 'CSE4', 'CSE3'];

// 사용자 행동 비율 (합 100) — 조회 위주. 로그인이 필요한 흐름은 2차에 추가
const ACTIONS = [
  { weight: 20, run: home },
  { weight: 30, run: courseList },
  { weight: 20, run: courseSearch },
  { weight: 20, run: courseDetail },
  { weight: 10, run: professorList },
];

// 부하 프로필 — 모두 arrival-rate(open model). 단위: iteration/초
const PROFILES = {
  smoke: {
    executor: 'constant-arrival-rate', rate: 1, timeUnit: '1s', duration: '1m',
    preAllocatedVUs: 5, maxVUs: 20,
  },
  load: { // 평상시 부하 — 튜닝 전후 비교의 주 지표. 분석 시 앞 2분(램프+안정화) 제외
    executor: 'ramping-arrival-rate', startRate: 0, timeUnit: '1s',
    stages: [{ target: 5, duration: '1m' }, { target: 5, duration: '10m' }],
    preAllocatedVUs: 20, maxVUs: 100,
  },
  stress: { // 단계별 증가 — 단계마다 p95·자원 변화, 급격히 나빠지는 지점(knee) 확인
    executor: 'ramping-arrival-rate', startRate: 5, timeUnit: '1s',
    stages: [5, 10, 20, 30, 40].flatMap((r) => [
      { target: r, duration: '10s' }, { target: r, duration: '2m50s' },
    ]),
    preAllocatedVUs: 50, maxVUs: 300,
  },
  breakpoint: { // 한계 탐색 — 실패할 때까지 선형 증가, 아래 abort 기준으로 운영 서버 보호
    executor: 'ramping-arrival-rate', startRate: 1, timeUnit: '1s',
    stages: [{ target: 150, duration: '20m' }],
    preAllocatedVUs: 100, maxVUs: 600,
  },
};

// 합격 기준(SLO) — docs/performance.md §2.4
const thresholds = {
  'http_req_failed': ['rate<0.01'],
  'http_req_duration{kind:api}': ['p(95)<500', 'p(99)<1500'],
  'http_req_duration{kind:page}': ['p(95)<1000'],
};
if (PROFILE === 'smoke' || PROFILE === 'load') {
  // 생성기가 목표 도착률을 못 냈으면 결과 무효 (VU 부족 = 측정 누락)
  thresholds['dropped_iterations'] = ['count==0'];
}
if (PROFILE === 'breakpoint') {
  // 에러율 10% 초과가 30초 이어지면 즉시 중단 — 운영 서버 보호
  thresholds['http_req_failed'] = [{ threshold: 'rate<0.10', abortOnFail: true, delayAbortEval: '30s' }];
}

export const options = {
  scenarios: { [PROFILE]: { ...PROFILES[PROFILE], exec: 'userAction' } },
  thresholds,
  discardResponseBodies: true, // 생성기 메모리 절약 (전송량은 줄지 않음)
  summaryTrendStats: ['min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
  tags: { run: RUN_ID, profile: PROFILE },
};

function get(url, name, kind) {
  const res = http.get(url, { tags: { name, kind } });
  check(res, { 'status 2xx/3xx': (r) => r.status >= 200 && r.status < 400 });
  return res;
}
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

function home() { get(`${BASE}/`, 'page_home', 'page'); }
function courseList() { get(`${API}/api/v1/courses?year=2026&semester=1`, 'api_course_list', 'api'); }
function courseSearch() {
  get(`${API}/api/v1/courses?q=${encodeURIComponent(pick(SEARCH_TERMS))}`, 'api_course_search', 'api');
}
function courseDetail() { // 강의 상세 화면은 강의 정보 + 강의계획서 요약을 함께 부른다
  const id = pick(COURSE_IDS);
  get(`${API}/api/v1/courses/${id}`, 'api_course_detail', 'api');
  get(`${API}/api/v1/syllabus/${id}`, 'api_syllabus', 'api');
}
function professorList() { get(`${API}/api/v1/professors`, 'api_professor_list', 'api'); }

const TOTAL_WEIGHT = ACTIONS.reduce((s, a) => s + a.weight, 0);
export function userAction() {
  let r = Math.random() * TOTAL_WEIGHT;
  for (const a of ACTIONS) {
    if ((r -= a.weight) < 0) { a.run(); return; }
  }
}

export function handleSummary(data) {
  const out = __ENV.OUT_DIR || '.';
  return {
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
    [`${out}/summary.json`]: JSON.stringify(data, null, 2),
  };
}
