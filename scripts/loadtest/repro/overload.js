import http from 'k6/http';
export const options = {
  scenarios: { hit: { executor: 'constant-arrival-rate', rate: Number(__ENV.RATE || 60), timeUnit: '1s',
    duration: __ENV.DUR || '60s', preAllocatedVUs: 100, maxVUs: 2000 } },
  discardResponseBodies: true,
};
export default function () {
  http.get('http://localhost:18000/api/v1/courses?year=2026&semester=1', { timeout: '60s' });
}
