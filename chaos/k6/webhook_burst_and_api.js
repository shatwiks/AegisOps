import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    health_and_readiness: {
      executor: 'constant-vus',
      vus: 5,
      duration: '10s',
      exec: 'checkHealth',
    },
    webhook_burst_dedup: {
      executor: 'shared-iterations',
      vus: 10,
      iterations: 30,
      maxDuration: '20s',
      exec: 'burstWebhook',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1500'],
  },
};

const BASE_URL = __ENV.AEGISOPS_API_URL || 'http://127.0.0.1:58000';
const BEARER = __ENV.AEGISOPS_WEBHOOK_BEARER_TOKEN || '';
const FINGERPRINT = __ENV.K6_FINGERPRINT || `k6-burst-${Date.now()}`;

export function checkHealth() {
  const res = http.get(`${BASE_URL}/readyz`);
  check(res, {
    'readyz status 200': (r) => r.status === 200,
    'readyz body ready': (r) => r.json('status') === 'ready',
  });
  sleep(0.5);
}

export function burstWebhook() {
  const payload = JSON.stringify({
    receiver: 'k6-burst-benchmark',
    status: 'firing',
    alerts: [
      {
        status: 'firing',
        fingerprint: FINGERPRINT,
        startsAt: new Date().toISOString(),
        labels: {
          alertname: 'K6BurstDeduplicationCheck',
          severity: 'warning',
          service: 'provider-directory',
          namespace: 'aegisops-healthcare',
          cluster: 'kind-aegisops-local',
        },
        annotations: {
          summary: 'k6 concurrent webhook burst deduplication test (SSN 123-45-6789 scrubbed)',
        },
      },
    ],
  });

  const res = http.post(`${BASE_URL}/api/v1/webhooks/alertmanager`, payload, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${BEARER}`,
      'X-AegisOps-Provenance': 'automated_test',
    },
  });

  check(res, {
    'webhook accepted 202': (r) => r.status === 202,
    'single action created or deduplicated': (r) => {
      const action = r.json('results.0.action');
      return action === 'created' || action === 'deduplicated';
    },
  });
}
