export default async function handler(req: any, res: any) {
  if (req.method !== 'POST') {
    return res.status(405).json({ ok: false, error: 'Method not allowed' });
  }

  let body: Record<string, unknown> = {};
  if (req.body && typeof req.body === 'object' && !Array.isArray(req.body)) {
    body = req.body;
  } else {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    try {
      body = raw ? JSON.parse(raw) : {};
    } catch {
      return res.status(400).json({ ok: false, error: 'Некорректный формат данных' });
    }
  }

  const phone = String(body.phone ?? '').trim();
  const email = String(body.email ?? '').trim();
  if (!phone && !email) {
    return res.status(400).json({ ok: false, error: 'Укажите телефон или email' });
  }

  if (phone && !/^\+?[0-9\s\-()]{6,20}$/.test(phone)) {
    return res.status(400).json({ ok: false, error: 'Проверьте номер телефона' });
  }

  console.log('[lead]', JSON.stringify({ ...body, phone, email }));

  return res.status(200).json({ ok: true });
}