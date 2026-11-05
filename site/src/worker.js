// nickhub.com — Cloudflare Worker
// Static dashboard is served from ./public; this handles the API routes.
//   POST /api/ingest      (Authorization: Bearer <password>) — an uploader pushes its latest snapshot
//   GET  /api/summary     — one small entry per character, plus its level timeline, for the leaderboard
//   GET  /api/char/<key>  — one character's full log, e.g. /api/char/Forever-Shrim%20Pina
//   GET  /api/data        — every character in full
//   GET  /<racer-name>    — a racer's profile page (racer.html), e.g. /shrim-pina
//
// Storage:
//   D1 table chars (schema.sql): one row per character with its summary, race-chart line and
//     gzipped full log. Unlike KV, a write shows up on the very next request
//   KV racer:<sha256>   a racer's hashed password -> { character }, the one they registered with
// A racer may upload any of their characters. The first upload of a character makes that racer its
// owner, and after that nobody else's password can update it. The INGEST_TOKEN secret is the
// admin password and may update any character.

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

// keys are "<realm>-<name>", so a racer's registered character is the key ending in its name
function isMain(key, main) {
  return !!main && key.toLowerCase().endsWith("-" + main.toLowerCase());
}

// the leaderboard's view of a character, so /api/summary never reads full logs
function summarize(c) {
  return {
    name: c.name, realm: c.realm, class: c.class, race: c.race, faction: c.faction,
    level: c.level, xp: c.xp, xpMax: c.xpMax, played: c.played, updatedAt: c.updatedAt, startedAt: c.startedAt,
    zone: c.zone, kills: (c.kills || []).length, quests: (c.quests || []).length,
    deaths: (c.deaths || []).length,
    reached60: c.levels?.["60"]?.t ?? null,
    addon: c.addonVersion ?? null,  // which release this racer runs, for troubleshooting
  };
}

// a level-60 log can pass 1 MB of JSON, so it's stored gzipped (D1 rows are capped at 2 MB)
async function gzip(text) {
  return new Response(new Blob([text]).stream().pipeThrough(new CompressionStream("gzip"))).arrayBuffer();
}

async function gunzip(bytes) {
  return new Response(new Blob([new Uint8Array(bytes)]).stream().pipeThrough(new DecompressionStream("gzip"))).text();
}

function timeline(c) {
  return Object.entries(c.levels || {})
    .filter(([, v]) => v && v.t)
    .map(([l, v]) => [Number(l), v.t])
    .sort((a, b) => a[0] - b[0]);
}

async function ingest(request, env) {
  const who = await authorize(request, env);
  if (!who) return json({ error: "unauthorized" }, 401);

  const len = Number(request.headers.get("content-length") || 0);
  if (len > MAX_BYTES) return json({ error: "payload too large" }, 413);

  let body;
  try { body = await request.json(); } catch { return json({ error: "invalid JSON" }, 400); }
  if (!body || typeof body.chars !== "object") return json({ error: "missing chars" }, 400);

  // the racer's registered character, or for the admin whatever their uploader names
  const main = who.admin ? (typeof body.main === "string" ? body.main : "") : who.character;
  const owner = (main || "admin").toLowerCase();

  // each character is its own row, so two uploaders can't overwrite each other. The upsert's WHERE
  // skips, in the same step, a snapshot older than the saved one and a character someone else owns.
  // A row from before owners existed goes to whoever uploads it as their main
  const upsert = env.DB.prepare(
    `INSERT INTO chars (key, summary, line, log, updated_at, owner) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
     ON CONFLICT(key) DO UPDATE SET summary = excluded.summary, line = excluded.line,
       log = excluded.log, updated_at = excluded.updated_at, owner = COALESCE(chars.owner, excluded.owner)
     WHERE excluded.updated_at >= chars.updated_at
       AND (?7 OR chars.owner = excluded.owner OR (chars.owner IS NULL AND ?8))`);
  const saved = {}, skipped = [];
  for (const [key, c] of Object.entries(body.chars)) {
    if (!c || typeof c !== "object") { skipped.push(key); continue; }
    const primary = isMain(key, main);
    if (primary && !who.admin) c.name = who.character;
    const res = await upsert.bind(key, JSON.stringify(summarize(c)), JSON.stringify(timeline(c)),
      await gzip(JSON.stringify(c)), c.updatedAt || 0, owner, who.admin ? 1 : 0, primary ? 1 : 0).run();
    if (!res.meta.changes) { skipped.push(key); continue; }
    saved[key] = { level: c.level, kills: (c.kills || []).length, quests: (c.quests || []).length };
  }
  return json({ ok: true, chars: saved, skipped });
}

const FRESH = { "cache-control": "no-store" };

async function summary(env) {
  const { results } = await env.DB.prepare("SELECT key, summary, line FROM chars").all();
  return json({ chars: results.map((r) => ({ key: r.key, ...JSON.parse(r.summary), line: JSON.parse(r.line) })) }, 200, FRESH);
}

async function charData(key, env) {
  const row = key && (await env.DB.prepare("SELECT log FROM chars WHERE key = ?1").bind(key).first());
  if (!row) return json({ error: "not found" }, 404);
  return new Response(await gunzip(row.log), {
    headers: { "content-type": "application/json; charset=utf-8", ...FRESH },
  });
}

async function data(env) {
  const { results } = await env.DB.prepare("SELECT key, log FROM chars").all();
  const chars = {};
  for (const r of results) chars[r.key] = JSON.parse(await gunzip(r.log));
  return json({ chars }, 200, FRESH);
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
    // no file matched, so a single path segment is a racer's profile, e.g. /shrim-pina
    if (/^\/[a-z0-9-]+\/?$/i.test(url.pathname) && !url.pathname.startsWith("/api")) {
      return env.ASSETS.fetch(new Request(new URL("/racer", url), request));
    }
    return env.ASSETS.fetch(request);
  },
};
