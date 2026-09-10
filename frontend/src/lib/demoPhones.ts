type PhoneMap = Record<string, string>;

let cached: PhoneMap | null = null;

function loadMap(): PhoneMap {
  if (cached) return cached;
  cached = {};
  const raw = import.meta.env.VITE_DEMO_PHONES as string | undefined;
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      for (const [k, v] of Object.entries(parsed)) {
        cached[k.trim().toLowerCase()] = String(v).replace(/\D/g, '');
      }
    } catch {
      // ignore malformed config
    }
  }
  return cached;
}

export function resolvePhone(name?: string | null, fallbackPhone?: string | null): string {
  const map = loadMap();
  if (name) {
    const lower = name.trim().toLowerCase();
    const first = lower.split(/\s+/)[0];
    if (first && map[first]) return map[first];
    if (map[lower]) return map[lower];
  }
  return (fallbackPhone || '').replace(/\D/g, '');
}

export function hasMappedPhone(name?: string | null): boolean {
  const map = loadMap();
  if (!name) return false;
  const lower = name.trim().toLowerCase();
  return Boolean(map[lower] || map[lower.split(/\s+/)[0]]);
}

export function whatsappSendUrl(phone: string, text: string): string {
  const q = new URLSearchParams();
  if (phone) q.set('phone', phone);
  q.set('text', text);
  return `https://web.whatsapp.com/send?${q.toString()}`;
}
