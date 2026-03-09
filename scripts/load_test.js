import http from 'k6/http';
import { check, sleep } from 'k6';

// Arkashri Production Load Testing Script (k6)
export const options = {
    stages: [
        { duration: '30s', target: 50 },  // Ramp-up to 50 concurrent users
        { duration: '1m', target: 200 },  // Spike to 200 concurrent auditors
        { duration: '30s', target: 0 },   // Scale down
    ],
    thresholds: {
        http_req_duration: ['p(95)<500'], // 95% of requests must complete below 500ms
        http_req_failed: ['rate<0.01'],   // Error rate must be < 1%
    },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_TOKEN = __ENV.API_TOKEN || 'test-token';

export default function () {
    const params = {
        headers: {
            'Authorization': `Bearer ${API_TOKEN}`,
            'Content-Type': 'application/json',
        },
    };

    // 1. Health Check
    let res = http.get(`${BASE_URL}/health`);
    check(res, { 'health returned 200': (r) => r.status === 200 });

    // 2. Fetch Engagements
    res = http.get(`${BASE_URL}/api/v1/engagements/?tenant_id=tenant_a&jurisdiction=us_ny`, params);
    check(res, { 'engagements returned 200': (r) => r.status === 200 });

    // 3. Trigger Risk Engine Scoring
    const scorePayload = JSON.stringify({
        tenant_id: 'tenant_a',
        jurisdiction: 'us_ny',
        transaction_id: 'txn_123',
        evidence: { amount: 50000, risk_country: 'FR' }
    });

    res = http.post(`${BASE_URL}/api/v1/risks/compute`, scorePayload, params);
    check(res, { 'risk compute returned 200': (r) => r.status === 200 });

    sleep(1);
}
