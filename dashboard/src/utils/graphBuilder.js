import { shortCardLabel } from './cardLabel';

export const NODE_COLORS = {
  customer: '#3b82f6',
  card: '#8b5cf6',
  flagged_txn: '#ef4444',
  txn: '#991b1b',
  device: '#f97316',
  connected_card: '#ec4899',
  prior_case: '#7f1d1d',
  region_card: '#6366f1',
  email_card: '#14b8a6',
};

/** Keep the force layout readable (live TG can return thousands of neighbor cards). */
const VIZ_LIMITS = {
  cardTxns: 12,
  deviceNeighbors: 12,
  regionCards: 8,
  emailCards: 8,
  priorCases: 10,
  fraudOnDevice: 10,
};

function listOf(values) {
  return Array.isArray(values) ? values : [];
}

function uniqueTake(items, max, idFn = (x) => String(x?.v_id ?? x)) {
  const out = [];
  const seen = new Set();
  for (const item of listOf(items)) {
    const key = idFn(item);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(item);
    if (out.length >= max) break;
  }
  return out;
}

function sortTxnsChronologically(txns) {
  return [...txns].sort((a, b) => {
    const ta = String(a?.attributes?.ts ?? a?.ts ?? '');
    const tb = String(b?.attributes?.ts ?? b?.ts ?? '');
    return ta.localeCompare(tb);
  });
}

function createGraphBuilder() {
  const nodes = [];
  const links = [];
  const seen = new Set();

  const addNode = (node) => {
    if (seen.has(node.id)) {
      const existing = nodes.find((n) => n.id === node.id);
      if (existing && node.meta) existing.meta = { ...existing.meta, ...node.meta };
      return;
    }
    seen.add(node.id);
    nodes.push(node);
  };

  const link = (source, target, color = '#4b5563', dashed = false) => {
    const s = String(source);
    const t = String(target);
    if (!s || !t || s === t) return;
    links.push({ source: s, target: t, color, dashed });
  };

  const hasNode = (id) => seen.has(String(id));

  return { nodes, links, addNode, link, hasNode, seen };
}

/** Drop links whose endpoints are missing (force-graph throws otherwise). */
export function sanitizeGraph({ nodes, links }) {
  const ids = new Set(nodes.map((n) => String(n.id)));
  return {
    nodes,
    links: links.filter(
      (l) => ids.has(String(l.source)) && ids.has(String(l.target))
    ),
  };
}

/** Shallow clone so force-graph can mutate link source/target without corrupting React state. */
export function cloneGraphForRender({ nodes, links }) {
  return {
    nodes: nodes.map((n) => ({ ...n })),
    links: links.map((l) => ({ ...l })),
  };
}

function deviceLabel(device) {
  if (!device) return null;
  const attrs = device.attributes ?? device;
  const id = device.v_id ?? attrs.device_id;
  if (typeof device === 'string') return { id: device, label: device.slice(0, 40) };
  const parts = [
    attrs.device_info,
    attrs.os,
    attrs.browser,
    attrs.device_status ? `Status=${attrs.device_status}` : null,
  ].filter(Boolean);
  const label = parts.length ? parts.join(' | ').slice(0, 48) : String(id ?? 'device');
  return { id: String(id ?? label), label, meta: attrs };
}

/** Normalize REST or cached bundle into a flat evidence object. */
export function normalizeEvidenceBundle(raw) {
  if (!raw || typeof raw !== 'object') return null;

  const flagged = raw.flagged_txn ?? listOf(raw.start)[0] ?? null;

  const deviceRaw = raw.device;
  let device = null;
  if (Array.isArray(deviceRaw) && deviceRaw.length) device = deviceRaw[0];
  else if (deviceRaw && typeof deviceRaw === 'object' && !Array.isArray(deviceRaw)) {
    device = deviceRaw;
  }

  let card_transactions = listOf(raw.card_transactions);
  if (!card_transactions.length) {
    card_transactions = sortTxnsChronologically([
      ...listOf(raw.tx_before),
      ...listOf(raw.tx_after),
    ]);
  }

  const customer_prior = listOf(raw.customer_prior_cases ?? raw.prior_cases);

  return {
    flagged_txn: flagged,
    owner_cards: listOf(raw.owner_cards),
    card_transactions,
    device,
    device_neighbors: listOf(raw.device_neighbors),
    fraud_cases_on_device: listOf(raw.fraud_cases_on_device),
    customer_prior_cases: customer_prior,
    prior_cases: customer_prior,
    region_neighbor_cards: listOf(raw.region_neighbor_cards),
    email_neighbor_cards: listOf(raw.email_neighbor_cards),
  };
}

export function buildGraphFromCase(record, pack) {
  const { nodes, links, addNode, link } = createGraphBuilder();
  const c = record?.case ?? {};

  const customerId = pack?.customer_id ?? 'customer';
  addNode({ id: customerId, type: 'customer', label: customerId, val: 8 });

  const cardId = pack?.card_id ?? 'card';
  addNode({ id: cardId, type: 'card', label: cardId, val: 6 });
  link(customerId, cardId, NODE_COLORS.card);

  const flagged = c.first_suspicious_txn_id || pack?.flagged_txn_id;
  if (flagged) {
    addNode({
      id: String(flagged),
      type: 'flagged_txn',
      label: `TXN ${flagged}`,
      val: 7,
    });
    link(cardId, String(flagged), NODE_COLORS.flagged_txn);
  }

  for (const txnId of c.affected_txn_ids ?? []) {
    const tid = String(txnId);
    if (tid === String(flagged)) continue;
    addNode({ id: tid, type: 'txn', label: tid, val: 4 });
    link(cardId, tid, NODE_COLORS.txn);
  }

  const deviceProfiles = c.connected_device_profiles ?? [];
  for (const dev of deviceProfiles) {
    const d = deviceLabel(typeof dev === 'string' ? { v_id: dev } : dev);
    if (!d) continue;
    addNode({ id: d.id, type: 'device', label: d.label, val: 5, meta: d.meta });
    if (flagged) link(String(flagged), d.id, NODE_COLORS.device);
    else link(cardId, d.id, NODE_COLORS.device);
  }

  for (const cc of c.connected_card_ids ?? []) {
    const cid = String(cc);
    addNode({ id: cid, type: 'connected_card', label: shortCardLabel(cid), val: 5 });
    const deviceId = deviceProfiles[0]
      ? deviceLabel(typeof deviceProfiles[0] === 'string' ? { v_id: deviceProfiles[0] } : deviceProfiles[0])?.id
      : null;
    if (deviceId) link(deviceId, cid, NODE_COLORS.connected_card);
    else link(cardId, cid, NODE_COLORS.connected_card);
  }

  for (const pc of c.similar_prior_cases ?? []) {
    addNode({ id: String(pc), type: 'prior_case', label: String(pc), val: 3 });
    link(customerId, String(pc), NODE_COLORS.prior_case, true);
  }

  return sanitizeGraph({ nodes, links });
}

export function buildGraphFromEvidenceBundle(bundle, pack, record) {
  const b = normalizeEvidenceBundle(bundle);
  if (!b) return buildGraphFromCase(record, pack);

  const { nodes, links, addNode, link, hasNode } = createGraphBuilder();
  const c = record?.case ?? {};

  const customerId = pack?.customer_id ?? 'customer';
  addNode({ id: customerId, type: 'customer', label: customerId, val: 8 });

  const packCardId = pack?.card_id ? String(pack.card_id) : null;
  let primaryCard = packCardId;

  for (const card of b.owner_cards ?? []) {
    const cid = String(card.v_id ?? card);
    if (!primaryCard) primaryCard = cid;
    addNode({
      id: cid,
      type: 'card',
      label: cid.length > 24 ? `${cid.slice(0, 22)}…` : cid,
      val: 6,
      meta: card.attributes,
    });
    link(customerId, cid, NODE_COLORS.card);
  }

  if (packCardId && !hasNode(packCardId)) {
    addNode({
      id: packCardId,
      type: 'card',
      label: packCardId,
      val: 6,
    });
    link(customerId, packCardId, NODE_COLORS.card);
    if (!primaryCard) primaryCard = packCardId;
  }

  if (!primaryCard) {
    primaryCard = 'card';
    if (!hasNode(primaryCard)) {
      addNode({ id: primaryCard, type: 'card', label: primaryCard, val: 6 });
      link(customerId, primaryCard, NODE_COLORS.card);
    }
  }

  const drvOwner = b.owner_cards?.[0]
    ? String(b.owner_cards[0].v_id ?? b.owner_cards[0])
    : null;
  if (packCardId && drvOwner && packCardId !== drvOwner && hasNode(drvOwner)) {
    link(packCardId, drvOwner, NODE_COLORS.card, true);
  }

  const flaggedVtx = b.flagged_txn;
  const flaggedId = String(
    flaggedVtx?.v_id ?? flaggedVtx?.attributes?.transaction_id ?? pack?.flagged_txn_id ?? ''
  );
  if (flaggedId) {
    addNode({
      id: flaggedId,
      type: 'flagged_txn',
      label: `TXN ${flaggedId}`,
      val: 7,
      meta: flaggedVtx?.attributes,
    });
    link(primaryCard, flaggedId, NODE_COLORS.flagged_txn);
  }

  const devInfo = deviceLabel(b.device);
  if (devInfo) {
    addNode({
      id: devInfo.id,
      type: 'device',
      label: devInfo.label,
      val: 6,
      meta: devInfo.meta,
    });
    if (flaggedId) link(flaggedId, devInfo.id, NODE_COLORS.device);
    else link(primaryCard, devInfo.id, NODE_COLORS.device);

    for (const neighbor of uniqueTake(b.device_neighbors, VIZ_LIMITS.deviceNeighbors)) {
      const nid = String(neighbor.v_id ?? neighbor);
      addNode({
        id: nid,
        type: 'connected_card',
        label: shortCardLabel(nid),
        val: 5,
      });
      link(devInfo.id, nid, NODE_COLORS.connected_card);
    }
  }

  const recentTxns = sortTxnsChronologically(listOf(b.card_transactions)).slice(
    -VIZ_LIMITS.cardTxns
  );
  for (const txn of recentTxns) {
    const tid = String(txn.v_id ?? txn);
    if (tid === flaggedId) continue;
    addNode({ id: tid, type: 'txn', label: tid, val: 3, meta: txn.attributes });
    link(primaryCard, tid, NODE_COLORS.txn);
  }

  for (const pc of uniqueTake(
    b.customer_prior_cases ?? b.prior_cases,
    VIZ_LIMITS.priorCases
  )) {
    const pid = String(pc.v_id ?? pc);
    addNode({
      id: pid,
      type: 'prior_case',
      label: pid,
      val: 3,
      meta: pc.attributes,
    });
    link(customerId, pid, NODE_COLORS.prior_case, true);
  }

  for (const fc of uniqueTake(b.fraud_cases_on_device, VIZ_LIMITS.fraudOnDevice)) {
    const fid = String(fc.v_id ?? fc);
    addNode({ id: fid, type: 'prior_case', label: fid, val: 4, meta: fc.attributes });
    if (devInfo) link(devInfo.id, fid, NODE_COLORS.prior_case, true);
  }

  for (const rc of uniqueTake(b.region_neighbor_cards, VIZ_LIMITS.regionCards)) {
    const rid = String(rc.v_id ?? rc);
    addNode({ id: `region:${rid}`, type: 'region_card', label: rid.slice(0, 20), val: 4 });
    if (flaggedId) link(flaggedId, `region:${rid}`, NODE_COLORS.region_card, true);
  }

  for (const ec of uniqueTake(b.email_neighbor_cards, VIZ_LIMITS.emailCards)) {
    const eid = String(ec.v_id ?? ec);
    addNode({ id: `email:${eid}`, type: 'email_card', label: eid.slice(0, 20), val: 4 });
    if (flaggedId) link(flaggedId, `email:${eid}`, NODE_COLORS.email_card, true);
  }

  for (const cc of c.connected_card_ids ?? []) {
    const cid = String(cc);
    if (nodes.some((n) => n.id === cid)) continue;
    addNode({ id: cid, type: 'connected_card', label: shortCardLabel(cid), val: 5 });
    link(primaryCard, cid, NODE_COLORS.connected_card);
  }

  return sanitizeGraph({ nodes, links });
}
