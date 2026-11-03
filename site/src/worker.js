// nickhub.com — Cloudflare Worker
// Static dashboard is served from ./public; this handles the API routes.
//   POST /api/ingest      (Authorization: Bearer <password>) — an uploader pushes its latest snapshot
//   GET  /api/summary     — one small entry per character, for the leaderboard
//   GET  /api/char/<key>  — one character's full log, e.g. /api/char/Forever-Shrim%20Pina
//   GET  /api/data        — every character in full (what the dashboard reads today)
//
// KV layout:
//   char:<realm-name>   one character's log; its metadata holds the summary, so listing is cheap
//   racer:<sha256>      a racer's hashed password -> { character } it may update
// The INGEST_TOKEN secret is the admin password and may update any character.

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

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// racer passwords are stored hashed, so a KV leak doesn't leak them
async function authorize(request, env) {
  const auth = request.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!token) return null;
  if (env.INGEST_TOKEN && safeEqual(token, env.INGEST_TOKEN)) return { admin: true };
  const racer = await env.NICKHUB.get("racer:" + (await sha256(token)), "json");
  return racer && racer.character ? { admin: false, character: racer.character } : null;
}

// keys are "<realm>-<name>"; a racer may only update their own character
function mayUpdate(who, key) {
  return who.admin || key.toLowerCase().endsWith("-" + who.character.toLowerCase());
}

// small enough to fit KV metadata (1 KB), so /api/summary never reads full logs
function summarize(c) {
  return {
    name: c.name, realm: c.realm, class: c.class, race: c.race, faction: c.faction,
    level: c.level, xp: c.xp, xpMax: c.xpMax, played: c.played, updatedAt: c.updatedAt,
    deaths: (c.deaths || []).length,
    reached60: c.levels?.["60"]?.t ?? null,
  };
}

async function ingest(request, env) {
  const who = await authorize(request, env);
  if (!who) return json({ error: "unauthorized" }, 401);

  const len = Number(request.headers.get("content-length") || 0);
  if (len > MAX_BYTES) return json({ error: "payload too large" }, 413);

  let body;
  try { body = await request.json(); } catch { return json({ error: "invalid JSON" }, 400); }
  if (!body || typeof body.chars !== "object") return json({ error: "missing chars" }, 400);

  // each character is its own key, so two uploaders can't overwrite each other
  const saved = {}, skipped = [];
  for (const [key, c] of Object.entries(body.chars)) {
    if (!c || typeof c !== "object" || !mayUpdate(who, key)) { skipped.push(key); continue; }
    const { metadata: prev } = await env.NICKHUB.getWithMetadata("char:" + key);
    if (prev && (c.updatedAt || 0) < (prev.updatedAt || 0)) { skipped.push(key); continue; }
    await env.NICKHUB.put("char:" + key, JSON.stringify(c), { metadata: summarize(c) });
    saved[key] = { level: c.level, kills: (c.kills || []).length, quests: (c.quests || []).length };
  }
  return json({ ok: true, chars: saved, skipped });
}

async function charKeys(env) {
  const keys = [];
  let cursor;
  do {
    const page = await env.NICKHUB.list({ prefix: "char:", cursor });
    keys.push(...page.keys);
    cursor = page.list_complete ? null : page.cursor;
  } while (cursor);
  return keys;
}

async function summary(env) {
  const keys = await charKeys(env);
  return json({ chars: keys.map((k) => ({ key: k.name.slice(5), ...k.metadata })) }, 200, { "cache-control": "public, max-age=15" });
}

async function charData(key, env) {
  const raw = key && (await env.NICKHUB.get("char:" + key));
  if (!raw) return json({ error: "not found" }, 404);
  return new Response(raw, {
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "public, max-age=15" },
  });
}

async function data(env) {
  const keys = await charKeys(env);
  if (!keys.length) return json({ chars: {} }, 200, { "cache-control": "no-store" });
  const logs = await Promise.all(keys.map((k) => env.NICKHUB.get(k.name, "json")));
  const chars = {};
  keys.forEach((k, i) => { if (logs[i]) chars[k.name.slice(5)] = logs[i]; });
  return json({ chars }, 200, { "cache-control": "public, max-age=15" });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/ingest") {
      if (request.method !== "POST") return json({ error: "POST only" }, 405);
      return ingest(request, env);
    }
    if (url.pathname === "/api/summary") return summary(env);
    if (url.pathname.startsWith("/api/char/")) {
      let key;
      try { key = decodeURIComponent(url.pathname.slice("/api/char/".length)); } catch { return json({ error: "bad key" }, 400); }
      return charData(key, env);
    }
    if (url.pathname === "/api/data") return data(env);
    return env.ASSETS.fetch(request);
  },
};
