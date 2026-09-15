function getCsrf(){const m=document.cookie.match(/(?:^|;\\s*)elite_csrf=([^;]+)/);return m?decodeURIComponent(m[1]):""}\n
const state = { me:null, sports:[], careers:[], news:[] };

async function api(path, options={}){
  const opts = {
    credentials:"same-origin",
    headers:{"Accept":"application/json","Content-Type":"application/json", ...(options.headers||{})},
    ...options
  };
  const r = await fetch(path, opts);
  let data = {};
  try { data = await r.json(); } catch {}
  if(!r.ok){
    const err = new Error(data.error || `${path} -> ${r.status}`);
    err.code = data.error || "REQUEST_FAILED";
    throw err;
  }
  return data;
}

function setAuthMode(mode){
  const login = mode === "login";
  document.getElementById("loginForm").classList.toggle("hidden", !login);
  document.getElementById("registerForm").classList.toggle("hidden", login);
  document.getElementById("loginTab").classList.toggle("active", login);
  document.getElementById("registerTab").classList.toggle("active", !login);
  document.getElementById("authMessage").textContent = "";
}

function showAuth(){ document.getElementById("authOverlay").classList.remove("hidden"); }
function hideAuth(){ document.getElementById("authOverlay").classList.add("hidden"); }

function humanAuthError(code){
  return ({
    INVALID_CREDENTIALS:"That username/email or password did not match.",
    INVALID_USERNAME:"Use 3–24 letters, numbers, underscores, or hyphens.",
    INVALID_EMAIL:"Enter a valid email address.",
    PASSWORD_TOO_SHORT:"Password must be at least 10 characters.",
    INVALID_DISPLAY_NAME:"Display name must be 2–50 characters.",
    USERNAME_OR_EMAIL_TAKEN:"That username or email is already in use.",
    LEGAL_ACCEPTANCE_REQUIRED:"Please accept the Terms, Privacy Policy, and Community Rules.",
    EMAIL_VERIFICATION_REQUIRED:"Verify your email before entering a sport.",
    INVITE_REQUIRED:"This alpha currently requires an invitation."
  })[code] || "Something went wrong. Try again.";
}

async function login(identity,password){
  return api("/api/auth/login",{
    method:"POST",
    body:JSON.stringify({identity,password})
  });
}

async function register(payload){
  return api("/api/auth/register",{
    method:"POST",
    body:JSON.stringify(payload)
  });
}

async function logout(){
  try{ await api("/api/auth/logout",{method:"POST",body:"{}"}); }catch{}
  state.me=null; state.careers=[]; state.news=[]; state.sports=[];
  showAuth();
}

function statusDetail(s){
  if(s.slug === "baseball" && s.status === "LIVE") return "Season 3 • Regular Season";
  if(s.slug === "racing" && s.status === "ALPHA") return "Season 1 • Alpha";
  return "League foundation underway";
}

function renderSports(){
  const grid = document.getElementById("sportsGrid");
  grid.innerHTML = state.sports.map(s => {
    const active = ["LIVE","ALPHA","BETA"].includes(s.status);
    return `
      <article class="sport-card">
        <div class="sport-top">
          <div class="sport-icon">${s.icon}</div>
          <span class="status ${active ? "" : "dev"}">${s.status}</span>
        </div>
        <h3>${s.name}</h3>
        <p>${statusDetail(s)}</p>
        <div class="sport-actions">
          <button class="sport-link sport-enter" data-sport="${s.slug}" ${active ? "" : "disabled"}>${active ? "ENTER LEAGUE →" : "COMING SOON"}</button>
          <span class="dev-note">${active ? "Elite account recognized" : "Awaiting sport service"}</span>
        </div>
      </article>`;
  }).join("");
}

function renderCareers(){
  const list = document.getElementById("careersList");
  if(!state.careers.length){
    list.innerHTML = `<div class="empty-state">No active careers yet. Pick a sport to begin one.</div>`;
    return;
  }
  list.innerHTML = state.careers.map(c => `
    <article class="career-card">
      <div class="career-badge">${c.icon}</div>
      <div>
        <h3>${c.display_name}</h3>
        <p>${c.sport_name} • ${c.team_name || "Free Agent"}</p>
      </div>
      <div class="career-meta">
        <strong>${c.role_name || "Player"}</strong>
        <span>${c.season_label || ""}</span>
      </div>
    </article>`).join("");
}

function renderNews(){
  const grid = document.getElementById("newsGrid");
  grid.innerHTML = state.news.map(n => `
    <article class="news-card">
      <div class="tag">${n.icon || "🏆"} ${(n.sport_name || "ELITE SPORTS").toUpperCase()}</div>
      <h3>${n.headline}</h3>
      <p>${n.summary}</p>
    </article>`).join("");
}

function renderMe(){
  const data = state.me;
  if(!data) return;
  const {user,legacy} = data;

  document.querySelectorAll("[data-user-name]").forEach(el => el.textContent = user.display_name);
  document.querySelectorAll("[data-legacy-points]").forEach(el => el.textContent = legacy.points.toLocaleString());
  document.querySelectorAll("[data-legacy-level]").forEach(el => el.textContent = `Level ${legacy.level}`);
  document.querySelector("[data-championships]").textContent = legacy.championships;
  document.querySelector("[data-major-awards]").textContent = legacy.major_awards;
  document.querySelector("[data-seasons-played]").textContent = legacy.seasons_played;
  document.querySelector("[data-sports-entered]").textContent = legacy.sports_entered;

  const remaining = Math.max(0, legacy.next_level_at - legacy.points);
  document.querySelector("[data-next-level]").textContent = `${remaining.toLocaleString()} points to Level ${legacy.level + 1}`;
  const prev = (legacy.level - 1) * 250;
  const pct = Math.max(0, Math.min(100, ((legacy.points - prev) / 250) * 100));
  document.querySelector("[data-progress]").style.width = `${pct}%`;

  const stats = document.querySelectorAll(".stat-row strong");
  if(stats.length >= 4){
    stats[0].textContent = state.careers.length;
    stats[1].textContent = legacy.seasons_played;
    stats[2].textContent = legacy.championships;
    stats[3].textContent = legacy.points.toLocaleString();
  }

  document.getElementById("profileRole").textContent =
    user.email_verified ? "Verified Elite Member" : "Elite Member";
}

async function loadHub(){
  const errorBox = document.getElementById("systemStatus");
  try{
    const auth = await api("/api/auth/me");
    if(!auth.user){
      showAuth();
      errorBox.textContent = "Sign in required";
      errorBox.className = "system-status";
      return;
    }

    const [me,sports,careers,news] = await Promise.all([
      api("/api/hub/me"),
      api("/api/hub/sports"),
      api("/api/hub/careers"),
      api("/api/hub/news")
    ]);

    state.me = me;
    state.sports = sports.sports || [];
    state.careers = careers.careers || [];
    state.news = news.news || [];

    renderSports();
    renderCareers();
    renderNews();
    renderMe();
    hideAuth();

    errorBox.textContent = "Elite Core Connected";
    errorBox.className = "system-status ok";
  }catch(err){
    console.error(err);
    if(err.code === "AUTH_REQUIRED") showAuth();
    errorBox.textContent = "Elite Core Offline";
    errorBox.className = "system-status bad";
  }
}

document.getElementById("menuBtn").addEventListener("click", () => {
  document.getElementById("mainNav").classList.toggle("open");
});
document.getElementById("toggleDev").addEventListener("click", () => {
  document.body.classList.toggle("show-dev");
});
document.getElementById("loginTab").addEventListener("click",()=>setAuthMode("login"));
document.getElementById("registerTab").addEventListener("click",()=>setAuthMode("register"));
document.getElementById("logoutBtn").addEventListener("click",logout);

document.getElementById("loginForm").addEventListener("submit", async e => {
  e.preventDefault();
  const msg = document.getElementById("authMessage");
  msg.textContent = "";
  try{
    await login(
      document.getElementById("loginIdentity").value,
      document.getElementById("loginPassword").value
    );
    await loadHub();
  }catch(err){
    msg.textContent = humanAuthError(err.code);
  }
});

document.getElementById("registerForm").addEventListener("submit", async e => {
  e.preventDefault();
  const msg = document.getElementById("authMessage");
  msg.textContent = "";
  try{
    await register({
      username:document.getElementById("regUsername").value,
      display_name:document.getElementById("regDisplayName").value,
      email:document.getElementById("regEmail").value,
      password:document.getElementById("regPassword").value,
      accept_terms:document.getElementById("acceptTerms").checked,
      accept_privacy:document.getElementById("acceptPrivacy").checked,
      accept_community_rules:document.getElementById("acceptCommunity").checked
    });
    window.location.href="/verify.html";
  }catch(err){
    msg.textContent = humanAuthError(err.code);
  }
});


async function enterSport(slug){
  const status = document.getElementById("systemStatus");
  try{
    status.textContent = "Creating secure sport handoff…";
    status.className = "system-status";
    const data = await api(`/api/gateway/enter/${encodeURIComponent(slug)}`);
    window.location.href = data.entry_url;
  }catch(err){
    console.error(err);
    status.textContent = "Sport gateway error";
    status.className = "system-status bad";
  }
}

document.addEventListener("click", e => {
  const btn = e.target.closest(".sport-enter");
  if(!btn || btn.disabled) return;
  enterSport(btn.dataset.sport);
});


async function loadBaseballConnection(){
  try{
    const data = await api("/api/integrations/baseball/status");
    const cards = [...document.querySelectorAll(".sport-card")];
    const baseball = cards.find(card => card.querySelector("h3")?.textContent.includes("Baseball"));
    if(!baseball) return;

    let note = baseball.querySelector(".integration-note");
    if(!note){
      note = document.createElement("div");
      note.className = "integration-note";
      baseball.appendChild(note);
    }

    note.textContent = data.connected
      ? `EBL linked as ${data.link.external_username || data.link.external_user_id} • ${data.link.sport_role}`
      : "EBL account not linked yet";
    note.classList.toggle("connected", !!data.connected);
  }catch(err){
    console.warn("Baseball integration status unavailable", err);
  }
}

setAuthMode("login");
loadHub();
setTimeout(loadBaseballConnection, 300);
