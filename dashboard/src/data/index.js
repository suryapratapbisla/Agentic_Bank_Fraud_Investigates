import hhg001 from './HHG-001.json';
import hhg002 from './HHG-002.json';
import hhg003 from './HHG-003.json';
import hhg004 from './HHG-004.json';
import hhg005 from './HHG-005.json';
import hhg006 from './HHG-006.json';
import hhg007 from './HHG-007.json';
import hhg008 from './HHG-008.json';
import hhg009 from './HHG-009.json';
import hhg010 from './HHG-010.json';
import hhg011 from './HHG-011.json';
import hhg012 from './HHG-012.json';
import hhg013 from './HHG-013.json';
import hhg014 from './HHG-014.json';
import hhg015 from './HHG-015.json';
import hhg016 from './HHG-016.json';
import hhg017 from './HHG-017.json';
import hhg018 from './HHG-018.json';
import hhg019 from './HHG-019.json';
import hhg020 from './HHG-020.json';
import { casePack, getCasePackMeta } from './casePack.js';

const rawCases = [
  hhg001,
  hhg002,
  hhg003,
  hhg004,
  hhg005,
  hhg006,
  hhg007,
  hhg008,
  hhg009,
  hhg010,
  hhg011,
  hhg012,
  hhg013,
  hhg014,
  hhg015,
  hhg016,
  hhg017,
  hhg018,
  hhg019,
  hhg020,
];

export const cases = [...rawCases].sort((a, b) =>
  a.case_id.localeCompare(b.case_id)
);

export function getCaseById(id) {
  return cases.find((c) => c.case_id === id) ?? null;
}

export function getAgentStats() {
  let totalToolCalls = 0;
  let totalTokens = 0;
  let latencySum = 0;
  let casesWithMetrics = 0;

  for (const record of cases) {
    if (record.error && !record.case) continue;
    const hasMetrics =
      record.tool_calls != null || record.tokens != null || record.latency_s != null;
    if (!hasMetrics) continue;
    casesWithMetrics += 1;
    totalToolCalls += Number(record.tool_calls) || 0;
    totalTokens += Number(record.tokens) || 0;
    latencySum += Number(record.latency_s) || 0;
  }

  return {
    totalToolCalls,
    totalTokens,
    avgLatencyS: casesWithMetrics > 0 ? latencySum / casesWithMetrics : 0,
    casesWithMetrics,
  };
}

export function getDashboardStats() {
  let fraud = 0;
  let legitimate = 0;
  let uncertain = 0;
  let totalExposure = 0;

  for (const record of cases) {
    if (record.error && !record.case) continue;
    const v = record.case?.verdict ?? 'uncertain';
    if (v === 'fraud') fraud += 1;
    else if (v === 'legitimate') legitimate += 1;
    else uncertain += 1;
    totalExposure += record.case?.exposure_usd ?? 0;
  }

  return {
    total: cases.length,
    fraud,
    legitimate,
    uncertain,
    totalExposure,
  };
}

export { casePack, getCasePackMeta };

export function probabilityColor(p) {
  if (p == null || Number.isNaN(p)) return 'bg-gray-500';
  if (p < 0.3) return 'bg-emerald-500';
  if (p <= 0.7) return 'bg-amber-400';
  return 'bg-red-500';
}

export function verdictStyles(verdict) {
  switch (verdict) {
    case 'fraud':
      return 'bg-red-500/20 text-red-400 border-red-500/40';
    case 'legitimate':
      return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40';
    default:
      return 'bg-amber-400/20 text-amber-300 border-amber-400/40';
  }
}

export function sourceBadgeClass(source) {
  switch (source) {
    case 'graph':
      return 'bg-blue-600/80 text-blue-100';
    case 'customer':
      return 'bg-violet-600/80 text-violet-100';
    case 'document':
      return 'bg-orange-600/80 text-orange-100';
    default:
      return 'bg-gray-600/80 text-gray-200';
  }
}

export function routePillClass(route) {
  switch (route) {
    case 'auto':
      return 'bg-emerald-500/25 text-emerald-300 border-emerald-500/50';
    case 'L1':
      return 'bg-amber-400/25 text-amber-200 border-amber-400/50';
    case 'L2':
      return 'bg-red-500/25 text-red-300 border-red-500/50';
    default:
      return 'bg-gray-600/25 text-gray-300 border-gray-500/50';
  }
}

export function formatUsd(n) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(n ?? 0);
}
