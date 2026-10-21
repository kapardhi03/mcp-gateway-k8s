/* Dashboard. React 18 via htm, so there is no build step and no node_modules
   in the image. React is vendored into the image at build time, not pulled
   from a CDN at runtime, so the dashboard works on a cluster with no
   internet access. */
const { useState, useEffect, useCallback } = React;
const html = htm.bind(React.createElement);

async function api(path, opts = {}) {
  const r = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const text = await r.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { raw: text }; }
  if (!r.ok) throw new Error((body && body.error) || `HTTP ${r.status}`);
  return body;
}

function Err({ e }) {
  return e ? html`<div class="note err">${e}</div>` : null;
}

/* ------------------------------------------------------------ Servers */
function Servers({ me }) {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState(null);
  const load = useCallback(async () => {
    try { setRows(await api("/admin/upstreams")); setErr(null); }
    catch (e) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  const toggle = async (slug, enabled) => {
    try {
      await api(`/admin/upstreams/${slug}/enabled`, {
        method: "POST", body: JSON.stringify({ enabled }),
      });
      load();
    } catch (e) { setErr(e.message); }
  };

  return html`
    <h2>MCP servers</h2>
    <${Err} e=${err} />
    <table><thead><tr>
      <th>Slug</th><th>URL</th><th>Status</th><th>Credential</th><th>Tools</th><th></th>
    </tr></thead><tbody>
    ${rows.map(u => html`<tr key=${u.slug}>
      <td><code>${u.slug}</code></td>
      <td class="mut">${u.url}</td>
      <td class=${u.status === "Connected" ? "ok" : u.status === "Disabled" ? "mut" : "bad"}>
        ${u.status}${u.last_error ? html` <span class="mut">(${u.last_error})</span>` : null}
      </td>
      <td>${u.has_credential ? html`<span class="pill">set</span>` : html`<span class="mut">none</span>`}</td>
      <td>${(u.tools || []).length ? (u.tools || []).map(t => html`<code>${t}</code> `) : html`<span class="mut">—</span>`}</td>
      <td>${me.role === "admin"
        ? html`<button class="act" onClick=${() => toggle(u.slug, !u.enabled)}>
                 ${u.enabled ? "Disable" : "Enable"}</button>`
        : html`<span class="mut">admin only</span>`}</td>
    </tr>`)}
    </tbody></table>
    <div class="note">Credential values are never sent to this page. Only whether one is set.</div>`;
}

/* ------------------------------------------------------------ Members */
function Members({ me }) {
  const [users, setUsers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [link, setLink] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    try {
      setUsers(await api("/admin/users"));
      setInvites(await api("/admin/invites"));
      setErr(null);
    } catch (e) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (me.role !== "admin") return html`<h2>Members</h2><div class="note">Admins only.</div>`;

  const invite = async () => {
    try {
      const r = await api("/admin/invites", { method: "POST", body: JSON.stringify({ email, role }) });
      setLink(location.origin + r.invite_path);
      setEmail(""); load();
    } catch (e) { setErr(e.message); }
  };

  return html`
    <h2>Members</h2>
    <${Err} e=${err} />
    <div class="row">
      <input placeholder="email to invite" value=${email} onInput=${e => setEmail(e.target.value)} />
      <select value=${role} onChange=${e => setRole(e.target.value)}>
        <option value="member">member</option><option value="admin">admin</option>
      </select>
      <button class="act primary" onClick=${invite}>Send invite</button>
    </div>
    ${link ? html`<div class="note">
      Invite link, shown once. Give it to them yourself; nothing is emailed.<br/>
      <code>${link}</code></div>` : null}
    <table><thead><tr><th>Email</th><th>Name</th><th>Role</th><th>Password set</th></tr></thead><tbody>
      ${users.map(u => html`<tr key=${u.id}>
        <td>${u.email}</td><td>${u.name}</td>
        <td><span class="pill">${u.role}</span></td>
        <td>${u.has_password ? html`<span class="ok">yes</span>` : html`<span class="mut">pending</span>`}</td>
      </tr>`)}
    </tbody></table>
    <h2 style=${{ marginTop: "1.5rem" }}>Invites</h2>
    <table><thead><tr><th>Email</th><th>Role</th><th>Expires</th><th>Used</th></tr></thead><tbody>
      ${invites.map(i => html`<tr key=${i.id}>
        <td>${i.email}</td><td>${i.role}</td>
        <td class="mut">${i.expires_at.slice(0, 16).replace("T", " ")}</td>
        <td>${i.consumed ? html`<span class="mut">used</span>` : html`<span class="ok">open</span>`}</td>
      </tr>`)}
    </tbody></table>`;
}

/* ------------------------------------------------------------ My keys */
function Keys() {
  const [rows, setRows] = useState([]);
  const [fresh, setFresh] = useState(null);
  const [name, setName] = useState("");
  const [err, setErr] = useState(null);
  const load = useCallback(async () => {
    try { setRows(await api("/me/keys")); setErr(null); } catch (e) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    try {
      const r = await api("/me/keys", { method: "POST", body: JSON.stringify({ name: name || "default" }) });
      setFresh(r.api_key); setName(""); load();
    } catch (e) { setErr(e.message); }
  };
  const revoke = async (id) => {
    try { await api(`/me/keys/${id}/revoke`, { method: "POST" }); load(); }
    catch (e) { setErr(e.message); }
  };

  return html`
    <h2>My API keys</h2>
    <${Err} e=${err} />
    <div class="row">
      <input placeholder="name, e.g. laptop" value=${name} onInput=${e => setName(e.target.value)} />
      <button class="act primary" onClick=${create}>Create key</button>
    </div>
    ${fresh ? html`<div class="note">
      <b>Copy this now. It is not stored and will never be shown again.</b><br/>
      <code>${fresh}</code><br/>
      Use it as <code>Authorization: Bearer ...</code> against <code>${location.origin}/mcp</code>.
    </div>` : null}
    <table><thead><tr><th>Name</th><th>Prefix</th><th>Created</th><th>State</th><th></th></tr></thead><tbody>
      ${rows.map(k => html`<tr key=${k.id}>
        <td>${k.name}</td><td><code>${k.prefix}</code></td>
        <td class="mut">${k.created_at.slice(0, 16).replace("T", " ")}</td>
        <td>${k.revoked ? html`<span class="bad">revoked</span>` : html`<span class="ok">active</span>`}</td>
        <td>${k.revoked ? null : html`<button class="act" onClick=${() => revoke(k.id)}>Revoke</button>`}</td>
      </tr>`)}
    </tbody></table>
    <div class="note">Only a SHA-256 of each key is stored, so a lost key cannot be recovered. Create a new one.</div>`;
}

/* ------------------------------------------------------------ Audit */
function Audit() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState(null);
  const load = useCallback(async () => {
    try { setRows(await api("/admin/audit?limit=100")); setErr(null); } catch (e) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);
  return html`
    <h2>Audit log</h2>
    <${Err} e=${err} />
    <table><thead><tr>
      <th>When</th><th>User</th><th>Server</th><th>Tool</th><th>ms</th>
      <th>Tokens</th><th>Outcome</th><th>Detail</th>
    </tr></thead><tbody>
      ${rows.map((a, i) => html`<tr key=${i}>
        <td class="mut">${a.ts.slice(0, 19).replace("T", " ")}</td>
        <td>${a.user}</td><td>${a.server || "—"}</td><td>${a.tool || "—"}</td>
        <td>${a.duration_ms}</td>
        <td class="mut">${a.tokens_in != null
          ? `${a.tokens_in}/${a.tokens_out ?? 0}` : "—"}</td>
        <td class=${a.outcome === "ok" ? "ok" : "bad"}>${a.outcome}</td>
        <td class="mut">${a.detail || ""}</td>
      </tr>`)}
    </tbody></table>`;
}

/* ------------------------------------------------------------ Chat */
/* Every `style` here is an OBJECT. React requires that, and htm passes a
   string straight through, so `style="margin-top:1rem"` renders the whole
   dashboard as a blank page with React error #62. Caught only by opening a
   real browser: every HTTP check passed while the page showed nothing. */
function Chat() {
  const [cfg, setCfg] = useState(null);
  const [turns, setTurns] = useState([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const loadCfg = useCallback(async () => {
    try { setCfg(await api("/chat/config")); } catch (e) { setErr(e.message); }
  }, []);
  useEffect(() => { loadCfg(); }, [loadCfg]);

  const ask = async (e) => {
    e.preventDefault();
    const question = q.trim();
    if (!question || busy) return;
    setBusy(true); setErr(null);
    setTurns(t => [...t, { question, pending: true }]);
    setQ("");
    try {
      const r = await api("/chat", { method: "POST", body: JSON.stringify({ question }) });
      setTurns(t => t.map((x, i) => i === t.length - 1 ? { question, ...r } : x));
      loadCfg();
    } catch (e2) {
      setErr(e2.message);
      setTurns(t => t.map((x, i) => i === t.length - 1 ? { question, failed: e2.message } : x));
      loadCfg();
    } finally { setBusy(false); }
  };

  if (!cfg) return html`<h2>Chat</h2><${Err} e=${err} />`;
  if (!cfg.configured) return html`
    <h2>Chat</h2>
    <div class="note">No model API key is configured, so the chat agent is switched off.
    Everything else on this dashboard works. Create the Secret with
    <code>scripts/dev-secrets.sh --llm</code> and restart the gateway.</div>`;

  return html`
    <h2>Chat</h2>
    <div class="note">
      Asked as <b>you</b>. The agent reaches its tools through this gateway's own
      <code>/mcp</code> with a key minted for you and deleted when the answer comes back,
      so every tool call below is in the Audit log under your name.<br/>
      <span class="mut">${cfg.model} · effort low · at most ${cfg.max_steps} tool steps per
      question · ${cfg.used_today} of ${cfg.daily_cap} turns used today</span>
    </div>
    <${Err} e=${err} />
    ${turns.map((t, i) => html`<div class="turn" key=${i}>
      <div class="q">${t.question}</div>
      ${t.pending ? html`<div class="mut">thinking…</div>` : null}
      ${t.failed ? html`<div class="note err">${t.failed}</div>` : null}
      ${(t.steps || []).length ? html`<div class="steps">
        ${t.steps.map((s, j) => html`<div key=${j} class="step">
          <code>${s.tool}</code>
          <span class="mut">${JSON.stringify(s.input)}</span>
          <span class=${s.outcome === "ok" ? "ok" : "bad"}>${s.outcome}</span>
          <span class="mut">${s.duration_ms} ms</span>
        </div>`)}
      </div>` : null}
      ${t.answer ? html`<div class="a">${t.answer}</div>` : null}
      ${t.tokens ? html`<div class="mut tok">
        ${t.tokens.in} in / ${t.tokens.out} out tokens${(t.steps || []).length
          ? ` · ${t.steps.length} tool call${t.steps.length === 1 ? "" : "s"}` : " · no tools called"}
      </div>` : null}
    </div>`)}
    <form class="row" onSubmit=${ask} style=${{ marginTop: "1rem" }}>
      <input placeholder="e.g. what orders came in today?" value=${q}
             maxLength=${cfg.max_question_chars}
             onInput=${e => setQ(e.target.value)} />
      <button class="act primary" type="submit" disabled=${busy}>
        ${busy ? "Asking…" : "Ask"}</button>
    </form>`;
}

/* ------------------------------------------------------------ shell */
const TABS = [
  ["servers", "Servers", Servers],
  ["members", "Members", Members],
  ["keys", "My API keys", Keys],
  ["audit", "Audit log", Audit],
  ["chat", "Chat", Chat],
];

function Dashboard({ me, onOut }) {
  const [tab, setTab] = useState("servers");
  const Body = (TABS.find(t => t[0] === tab) || TABS[0])[2];
  const out = async () => { await api("/auth/logout", { method: "POST" }); onOut(); };
  return html`
    <header>
      <h1>MCP Gateway</h1>
      <div class="who">${me.name} · ${me.email} · <span class="pill">${me.role}</span>
        <button class="act" style=${{ marginLeft: ".6rem" }} onClick=${out}>Sign out</button></div>
    </header>
    <nav>${TABS.map(([k, label]) => html`
      <button key=${k} class=${tab === k ? "on" : ""} onClick=${() => setTab(k)}>${label}</button>`)}
    </nav>
    <main><${Body} me=${me} /></main>`;
}

function Login({ onIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState(null);
  const go = async (e) => {
    e.preventDefault();
    try { onIn(await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) })); }
    catch (e) { setErr(e.message); }
  };
  return html`<form class="login" onSubmit=${go}>
    <h1>MCP Gateway</h1>
    <${Err} e=${err} />
    <input placeholder="email" value=${email} onInput=${e => setEmail(e.target.value)} />
    <input placeholder="password" type="password" value=${password} onInput=${e => setPassword(e.target.value)} />
    <button class="act primary" type="submit">Sign in</button>
  </form>`;
}

function Accept({ token, onIn }) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState(null);
  const go = async (e) => {
    e.preventDefault();
    try {
      const me = await api("/auth/accept", {
        method: "POST", body: JSON.stringify({ token, name, password }),
      });
      history.replaceState({}, "", "/");
      onIn(me);
    } catch (e) { setErr(e.message); }
  };
  return html`<form class="login" onSubmit=${go}>
    <h1>Accept invite</h1>
    <${Err} e=${err} />
    <input placeholder="your name" value=${name} onInput=${e => setName(e.target.value)} />
    <input placeholder="choose a password (12+ chars)" type="password"
           value=${password} onInput=${e => setPassword(e.target.value)} />
    <button class="act primary" type="submit">Set password and sign in</button>
  </form>`;
}

function App() {
  const [me, setMe] = useState(undefined);   // undefined = still checking
  const token = new URLSearchParams(location.search).get("token");
  useEffect(() => {
    api("/auth/me").then(setMe).catch(() => setMe(null));
  }, []);
  if (me === undefined) return html`<main><p class="mut">Loading…</p></main>`;
  if (!me && token) return html`<${Accept} token=${token} onIn=${setMe} />`;
  if (!me) return html`<${Login} onIn=${setMe} />`;
  return html`<${Dashboard} me=${me} onOut=${() => setMe(null)} />`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
