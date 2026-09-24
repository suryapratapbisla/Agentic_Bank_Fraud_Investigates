import { normalizeEvidenceBundle } from '../utils/graphBuilder';

/** Live TG is opt-in only (set VITE_TG_LIVE=true). Hosted/static builds use bundled JSON. */
export function isLiveGraphEnabled() {
  const v = String(import.meta.env.VITE_TG_LIVE ?? '').trim().toLowerCase();
  return v === 'true' || v === '1';
}

export async function fetchEvidenceBundle({
  flaggedTxnId,
  customerId,
  cardTxnLimit = 30,
}) {
  const params = new URLSearchParams({
    flagged_txn_id: String(flaggedTxnId),
    customer_id: String(customerId),
    card_txn_limit: String(cardTxnLimit),
  });
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const res = await fetch(
      `/api/tg/restpp/query/FraudInvestigationGraph/get_evidence_bundle?${params}`,
      { signal: controller.signal }
    );
    if (!res.ok) {
      throw new Error(`TigerGraph HTTP ${res.status}`);
    }
    const data = await res.json();
    const payload = Array.isArray(data) ? data[0] : data;
    return normalizeEvidenceBundle(payload);
  } finally {
    clearTimeout(timer);
  }
}

const bundleModules = import.meta.glob('../data/bundles/HHG-*.json');

export async function loadCachedBundle(caseId) {
  const key = `../data/bundles/${caseId}.json`;
  const loader = bundleModules[key];
  if (!loader) return null;
  const mod = await loader();
  return normalizeEvidenceBundle(mod.default ?? mod);
}

/** Bundle first, then case JSON — no network required. */
export async function loadOfflineGraphPayload(caseId) {
  const bundle = await loadCachedBundle(caseId);
  if (bundle) return { evidenceBundle: bundle, source: 'bundle' };
  return { evidenceBundle: null, source: 'case' };
}
