function titleCase(value) {
  const text = String(value ?? '').trim();
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * DRV::customer::card1::card2::card3::network::issuer::type
 * EXT::C01234-K1 is a historical case-pack card id.
 */
export function formatConnectedCard(raw) {
  const id = String(raw ?? '');
  if (id.startsWith('EXT::')) {
    return {
      title: id.slice(5),
      detail: 'Case card',
      full: id,
    };
  }
  if (id.startsWith('DRV::')) {
    const parts = id.split('::');
    const customer = parts[1] || 'Card';
    const network = titleCase(parts[5]);
    const type = titleCase(parts[7]);
    const detail = [network, type].filter(Boolean).join(' · ') || 'Linked card';
    return { title: customer, detail, full: id };
  }
  return { title: id, detail: '', full: id };
}

export function shortCardLabel(raw) {
  const card = formatConnectedCard(raw);
  return card.detail ? `${card.title} · ${card.detail}` : card.title;
}
