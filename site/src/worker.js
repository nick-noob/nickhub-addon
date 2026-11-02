// nickhub.com — Cloudflare Worker
// Static dashboard is served from ./public; this handles the two API routes.
//   POST /api/ingest   (Authorization: Bearer <INGEST_TOKEN>) — uploader pushes the latest snapshot
//   GET  /api/data     — dashboard reads it

const MAX_BYTES = 20 * 1024 * 1024;

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...extra },
  });
}

// constant-time string compare so the token can't be guessed byte by byte
function safeEqual(a, b) {
  const enc = new TextEncoder();
  const x = enc.encode(a), y = enc.encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] || 0) ^ (y[i] || 0);
  return diff === 0;
}

async function ingest(request, env) {
  if (!env.INGEST_TOKEN) return json({ error: "INGEST_TOKEN secret not set" }, 500);
  const auth = request.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!safeEqual(token, env.INGEST_TOKEN)) return json({ error: "unauthorized" }, 401);

  const len = Number(request.headers.get("content-length") || 0);
  if (len > MAX_BYTES) return json({ error: "payload too large" }, 413);

  let body;
  try { body = await request.json(); } catch { return json({ error: "invalid JSON" }, 400); }
  if (!body || typeof body.chars !== "object") return json({ error: "missing chars" }, 400);

  // merge with what's stored so uploading from a second WoW install doesn't wipe the other's characters
  const existing = (await env.NICKHUB.get("data", "json")) || { chars: {} };
  for (const [key, c] of Object.entries(body.chars)) {
    const prev = existing.chars[key];
    if (!prev || (c.updatedAt || 0) >= (prev.updatedAt || 0)) existing.chars[key] = c;
  }
  existing.version = body.version;
  existing.receivedAt = Math.floor(Date.now() / 1000);

  await env.NICKHUB.put("data", JSON.stringify(existing));
  const summary = Object.fromEntries(Object.entries(existing.chars).map(([k, c]) => [k, { level: c.level, kills: (c.kills || []).length, quests: (c.quests || []).length }]));
  return json({ ok: true, chars: summary });
}

async function data(env) {
  const raw = await env.NICKHUB.get("data");
  if (!raw) return json({ chars: {} }, 200, { "cache-control": "no-store" });
  return new Response(raw, {
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "public, max-age=15" },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/ingest") {
      if (request.method !== "POST") return json({ error: "POST only" }, 405);
      return ingest(request, env);
    }
    if (url.pathname === "/api/data") return data(env);
    return env.ASSETS.fetch(request);
  },
};
