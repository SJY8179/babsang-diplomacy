// 밥상외교 — Readdy 시안을 그대로 옮기고 실제 API(/api/*)에 연결한 화면.
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const won = (n) => (n == null ? "—" : `${Number(n).toLocaleString()}원`);
const man = (n) => `${(n / 10000).toFixed(n % 10000 ? 1 : 0)}만원`;
const pad2 = (n) => String(n).padStart(2, "0");
const STATUS_KO = { idle: "문의 전", asking: "사장님 확인 중", available: "가능", limited: "조금 남음", unavailable: "불가",
  soon: "곧 자리 남", not_offered: "문의 미지원", no_response: "답 없음", closed_now: "영업 시간 아님", error: "오류" };
const POS = new Set(["available", "limited"]);
const NEG = new Set(["unavailable", "not_offered", "no_response", "closed_now", "error"]);
const AGENT_KO = { coordinator: "조율", scout: "탐색", negotiator: "교섭", memory: "기억", afterparty: "2차", travel: "이동", app: "앱" };
// 일러스트는 저장소에 포함된 SVG (외부 이미지 서비스에 의존하지 않음)
const ART = { korean: "/static/img/korean.svg", western: "/static/img/western.svg", grill: "/static/img/grill.svg" };
const HERO_IMG = "/static/img/table.svg";

// 시안의 반복 클래스
const BTN_PRIMARY = "inline-flex items-center justify-center gap-2 bg-primary-500 hover:bg-primary-600 text-background-50 px-5 py-2.5 rounded-[3px] text-[12.5px] whitespace-nowrap cursor-pointer transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
const BTN_LINE = "inline-flex items-center justify-center gap-2 border border-foreground-900 text-foreground-950 hover:bg-foreground-950 hover:text-background-50 px-5 py-2.5 rounded-[3px] text-[12.5px] whitespace-nowrap cursor-pointer transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
const BTN_SM = "inline-flex items-center justify-center gap-1.5 border border-foreground-900 text-foreground-950 hover:bg-foreground-950 hover:text-background-50 transition-colors text-[11.5px] px-3 py-1.5 rounded-[3px] whitespace-nowrap cursor-pointer disabled:opacity-50";
const BTN_TXT = "inline-flex items-center justify-center gap-1.5 text-[11.5px] text-foreground-700 hover:text-primary-700 transition-colors whitespace-nowrap cursor-pointer px-1";
const circle = (t, size = "w-8 h-8 text-[12px]", extra = "") =>
  `<span class="${size} shrink-0 inline-flex items-center justify-center rounded-full border border-foreground-900/80 font-heading text-foreground-950 bg-background-50 ${extra}" aria-hidden="true">${esc(t)}</span>`;
const head = (kicker, title, right) => `<div class="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-foreground-900/70 pb-4">
  <div><p class="kicker mb-3">${kicker}</p><h2 class="text-[1.55rem] md:text-[2rem] leading-[1.4]">${title}</h2></div>${right || ""}</div>`;
const hand = (html) => `<p class="font-hand text-[16px] md:text-[18px] text-primary-600 leading-tight md:text-right">${html}</p>`;

const S = { cfg: null, groups: [], gid: null, meeting: null, mem: null, session: null, es: null, selected: null,
  stars: 4, planCount: {}, booked: {}, log: [], dev: false, lab: null, labEs: null, labResults: [], blog: "" };

async function api(path, body, method) {
  const r = await fetch(path, body === undefined && !method ? {} : {
    method: method || "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : r.statusText);
  return data;
}
function toast(msg, ms = 2600) {
  const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.add("hidden"), ms);
}
function fail(e) { toast(e.message || String(e)); logLocal("error", e.message || String(e)); }
function fmtWhen(iso, long) {
  if (!iso) return "시간 미정";
  const d = new Date(iso);
  const day = "일월화수목금토"[d.getDay()];
  return long ? `${d.getMonth() + 1}월 ${d.getDate()}일 (${day}) ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
    : `${d.getMonth() + 1}/${d.getDate()}(${day}) ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}
const station = (o) => (!o ? "" : o.endsWith("역") ? o : `${o}역`);
const group = () => S.groups.find((g) => g.id === S.gid) || { id: S.gid, name: "모임" };
async function copy(text, okMsg = "복사했어요") {
  try { await navigator.clipboard.writeText(text); toast(okMsg); } catch { toast("복사하지 못했어요. 직접 선택해 복사해 주세요."); }
}

// ---------- 초기화 ----------
async function init() {
  $$("[data-logo]").forEach((n) => n.replaceWith($("#logo").content.cloneNode(true)));
  $$("#nav a").forEach((a) => (a.className = "group relative text-[13px] transition-colors cursor-pointer whitespace-nowrap py-1 text-foreground-700 hover:text-foreground-950"));
  window.addEventListener("scroll", onScroll, { passive: true });
  $("#dept").onchange = () => selectGroup($("#dept").value);
  $("#new-meeting").onclick = () => openMeetingDialog(false);
  $("#meeting-form").onsubmit = saveMeeting;
  $("#dev-toggle").onclick = () => setDev(!S.dev);
  S.dev = location.hash === "#lab" || localGet("dev") === "1";
  try {
    S.cfg = await api("/api/config");
    $("#mode").innerHTML = `<i class="ri-shield-check-line"></i>${esc(S.cfg.label)}`;
    if (S.cfg.live) $("#mode").className = $("#mode").className.replace(/secondary/g, "primary");
    S.cfg.areas.forEach((a) => $("#md-area").append(new Option(a, a)));
    await loadGroups();
    await selectGroup(S.groups.find((g) => g.id === localGet("gid"))?.id || S.groups.find((g) => g.name.startsWith("마케팅"))?.id || S.groups[0]?.id || "demo");
  } catch (e) { fail(e); }
  renderLog(); setDev(S.dev);
}
function localGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem(k, v); } catch { /* 저장소 없음 */ } }

function onScroll() {
  $("#hdr").className = `fixed top-0 inset-x-0 z-50 transition-colors duration-300 ${scrollY > 40 ? "bg-background-50/95 backdrop-blur border-b border-background-300" : "bg-transparent"}`;
  let cur = "top";
  for (const id of ["top", "participants", "candidates", "log", "memory"]) { const s = document.getElementById(id); if (s && s.getBoundingClientRect().top < 120) cur = id; }
  $$("#nav a").forEach((a) => {
    const on = a.dataset.nav === cur;
    a.classList.toggle("text-foreground-950", on); a.classList.toggle("text-foreground-700", !on);
    if (!a.querySelector("span")) a.insertAdjacentHTML("beforeend", '<span class="absolute left-0 -bottom-0.5 h-px bg-primary-500 transition-all duration-300"></span>');
    a.querySelector("span").style.width = on ? "100%" : "0";
  });
}

async function loadGroups() {
  const gs = await api("/api/groups");
  await Promise.all(gs.map(async (g) => { try { g.meeting = await api(`/api/groups/${g.id}/meeting`); } catch { g.meeting = null; } }));
  S.groups = gs;
  $("#dept").innerHTML = gs.map((g) => `<option value="${esc(g.id)}">${esc(g.name)}</option>`).join("");
  if (S.gid) $("#dept").value = S.gid;
}

async function selectGroup(id) {
  S.gid = id; $("#dept").value = id; localSet("gid", id);
  if (S.session && S.session.groupId !== id) { S.session = null; S.selected = null; if (S.es) S.es.close(); }
  S.meeting = group().meeting || null;
  try { S.mem = await api(`/api/groups/${id}/memory`); } catch { S.mem = { profile: { summary: "", visits: 0 }, visits: [] }; }
  S.blog = "";
  renderAll();
}

async function refreshMeeting() {
  if (!S.meeting) return;
  S.meeting = await api(`/api/meetings/${S.meeting.id}`);
  const g = group(); g.meeting = S.meeting;
}

function renderAll() { renderHero(); renderDepts(); renderPeople(); renderConditions(); renderCandidates(); renderMemory(); renderFooter(); onScroll(); }

// ---------- HERO ----------
function renderHero() {
  const g = group(), m = S.meeting, ps = m?.participants || [], sm = S.session?.meeting;
  const budgets = ps.map((p) => p.budget).filter(Boolean);
  const top = S.session?.candidates?.[0];
  const far = top && Object.keys(top.travel || {}).length ? Math.max(...Object.values(top.travel)) : null;
  const note = far != null ? `1순위 기준<br>가장 먼 사람도 ${far}분` : ps.length ? `${ps.length}명 중<br>${m.done}명 입력 끝` : "링크만<br>보내면 돼요";
  const dl = [
    ["참석", `${ps.length}명`, `${m?.done ?? 0}명 입력 완료`],
    ["일시", m?.when_at ? fmtWhen(m.when_at) : "미정", m?.when_at ? (new Date(m.when_at) - Date.now() < 90 * 60000 ? "지금 자리 문의" : "예약 요청으로 확인") : ""],
    ["지역", m?.area || "자동", m?.area ? `${m.area} 일대` : "출발지 가운데"],
    ["예산", budgets.length ? `${man(Math.min(...budgets))}~${man(Math.max(...budgets))}` : "입력 전", "1인 기준"],
  ];
  const stat4 = [
    ["참석자", ps.length, "명", `${m?.done ?? 0}명 입력 완료`],
    ["필수 조건", sm ? sm.must.length : "—", sm ? "개" : "", "완화 불가"],
    ["선호 조건", sm ? sm.nice.length : "—", sm ? "개" : "", "조율 가능"],
    ["조건 충족 후보", sm ? sm.count : "—", sm ? "곳" : "", sm ? `${sm.area} 기준` : "후보 찾기 전"],
  ];
  $("#top").innerHTML = `<div class="relative mx-auto max-w-[1280px] paper-grain bg-background-50 border border-background-300 px-5 md:px-10 pt-5 md:pt-6 pb-7 md:pb-9 fade-up">
  <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-foreground-900/75 pb-2">
    <span class="text-[9.5px] md:text-[10px] tracking-[0.26em] text-foreground-700">BAPSANG DIPLOMACY — 부서별 회식 운영 노트</span>
    <span class="text-[9.5px] md:text-[10px] tracking-[0.16em] text-foreground-500 whitespace-nowrap">NO. ${pad2((S.mem?.visits?.length || 0) + 1)} · 2026 가을</span></div>
  <div class="relative pt-6 md:pt-8">
    <h1 class="font-heading font-bold text-foreground-950 leading-[1.06] tracking-[-0.05em] text-[2.3rem] md:text-[3.4rem] lg:text-[4.5rem] xl:text-[5rem]">회식 하루를,<span class="block mt-1 md:mt-2"><span class="text-primary-600">막내 대신</span> 꼼꼼하게</span></h1>
    <p class="font-hand text-primary-600 text-[17px] md:text-[21px] leading-[1.3] mt-3 lg:mt-0 lg:absolute lg:right-0 lg:bottom-2 lg:text-right">* 예산도, 취향도<br class="hidden lg:block"> 다 챙겼어요</p></div>
  <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-10 mt-8 md:mt-10 items-start">
    <div class="lg:col-span-5">
      <p class="text-[13.5px] font-semibold text-foreground-950"><span class="hand-underline">${esc(g.name)} 회식</span>, 이 순서로 끝내요</p>
      <p class="text-[12.5px] text-foreground-600 leading-[1.95] mt-2.5 max-w-md">단톡방에 흩어진 출발지·예산·식단·취향을 모아 정리하고, 지난 회식의 기억까지 반영해 공평한 식당을 찾아 예약까지 챙겨요.</p>
      <div class="flex flex-col sm:flex-row gap-2.5 mt-5">
        <button type="button" class="${BTN_PRIMARY}" data-act="plan">추천 후보 보기<i class="ri-arrow-right-line"></i></button>
        <a href="#participants" class="${BTN_LINE}">조건 입력하기</a></div>
      <dl class="grid grid-cols-2 gap-x-5 gap-y-3.5 mt-7 border-t border-foreground-900/70 pt-4">
        ${dl.map(([t, v, s]) => `<div class="min-w-0"><dt class="text-[9.5px] tracking-[0.18em] text-foreground-500">${t}</dt><dd class="mt-1"><span class="block font-heading text-[15px] text-foreground-950 truncate">${esc(v)}</span><span class="block text-[10.5px] text-foreground-500 mt-0.5 truncate">${esc(s)}</span></dd></div>`).join("")}</dl>
      <div class="flex flex-wrap items-center gap-x-3 gap-y-2 mt-5 text-[11px] text-foreground-600">
        <span class="flex -space-x-1.5">${ps.slice(0, 6).map((p) => `<span class="w-6 h-6 rounded-full border border-foreground-400 bg-background-50 text-[9.5px] text-foreground-800 flex items-center justify-center">${esc(p.name[0])}</span>`).join("")}</span>
        <span>${sm ? `필수 ${sm.must.length} · 선호 ${sm.nice.length}` : "조건 모으는 중"}</span><span class="w-px h-3 bg-background-300"></span><span>${sm ? `후보 ${sm.count}곳` : `기억 ${S.mem?.visits?.length || 0}회`}</span></div>
    </div>
    <figure class="relative lg:col-span-7 lg:pl-8">
      <span aria-hidden="true" class="pointer-events-none absolute left-4 md:left-12 right-3 md:right-4 top-8 bottom-9 bg-primary-200"></span>
      <div class="relative rotate-[-1.3deg] border border-background-300 bg-background-100 p-2 md:p-2.5">
        <span class="tape -top-2 left-8 md:left-12 rotate-[-7deg]"></span><span class="tape -bottom-2 right-10 md:right-16 rotate-[6deg]"></span>
        <div class="w-full aspect-[16/10] overflow-hidden bg-background-50"><img alt="네 명이 함께 밥상을 나누는 일러스트" class="w-full h-full object-cover object-top" src="${HERO_IMG}" onerror="this.remove()"></div></div>
      <span class="absolute -top-3 right-4 md:right-8">${circle("01", "w-10 h-10 md:w-11 md:h-11 text-[14px] md:text-[16px]")}</span>
      <div class="hidden md:block absolute -left-1 bottom-4 rotate-[-3deg] border border-foreground-900/60 bg-accent-100 px-3 py-2 w-[132px]"><p class="font-hand text-[16px] leading-[1.25] text-foreground-900">${note}</p></div>
      <figcaption class="mt-3 flex items-start justify-between gap-4 text-[10.5px] text-foreground-600"><span>${esc(m?.title || `${g.name} 회식`)}</span><span class="tracking-[0.18em] text-foreground-400 whitespace-nowrap">FIG. 01</span></figcaption>
    </figure>
  </div>
  <div class="grid grid-cols-2 md:grid-cols-4 gap-y-4 mt-7 md:mt-9 border-t border-foreground-900/70 pt-4">
    ${stat4.map(([t, v, u, s], i) => `<div class="px-0 md:px-5 ${i ? "md:border-l md:border-dotted md:border-foreground-400/60" : "md:pl-0"}"><p class="text-[9.5px] tracking-[0.18em] text-foreground-500 mb-1">${t}</p><p class="font-heading text-[22px] md:text-[26px] leading-none text-foreground-950">${esc(v)}<span class="text-[11px] text-foreground-500 ml-1 font-sans">${u}</span></p><p class="text-[10.5px] text-foreground-500 mt-1.5">${esc(s)}</p></div>`).join("")}
  </div></div>`;
  bindActs($("#top"));
}

// ---------- 부서 ----------
function renderDepts() {
  const rows = S.groups.map((g, i) => {
    const on = g.id === S.gid, m = g.meeting, n = m?.participants?.length || 0, done = m?.done || 0;
    const pct = n ? Math.round(done / n * 100) : 0;
    const state = S.booked[g.id] ? "예약 확정" : !m ? "회식 없음" : done < n ? "입력 대기" : S.planCount[g.id] != null ? "확인 대기" : "후보 찾기 전";
    const stats = [["후보", S.planCount[g.id] != null ? `${S.planCount[g.id]}곳` : "—"], ["기억", `${m?.visits ?? 0}회`], ["상태", state]];
    return `<li class="border-b border-background-300"><button type="button" data-g="${esc(g.id)}" class="w-full text-left grid grid-cols-[auto_1fr_auto] md:grid-cols-[auto_1.5fr_1fr_auto] items-center gap-x-4 md:gap-x-6 gap-y-2 py-5 md:py-6 px-2 cursor-pointer transition-colors ${on ? "bg-background-50" : "hover:bg-background-50/60"}">
      ${circle(pad2(i + 1), "w-10 h-10 md:w-11 md:h-11 text-[14px] md:text-[16px]", on ? "border-primary-600 text-primary-700" : "")}
      <div class="min-w-0 px-1"><div class="flex flex-wrap items-baseline gap-x-3 gap-y-1"><h3 class="font-heading text-[1.15rem] md:text-[1.55rem] leading-none ${on ? "text-primary-700" : "text-foreground-950"}">${esc(g.name)}</h3>${on ? '<span class="font-hand text-[15px] text-primary-600">지금 보는 중</span>' : ""}</div>
        <p class="text-[11px] md:text-[12px] text-foreground-600 mt-1.5 truncate">${esc([m?.title, m?.lead, m?.team_size && `${m.team_size}명`].filter(Boolean).join(" · ") || "아직 회식이 없어요")}</p>
        <div class="flex md:hidden flex-wrap items-center gap-x-2.5 gap-y-1 mt-2 text-[10.5px] text-foreground-600">${stats.map(([, v]) => `<span>${esc(v)}</span>`).join('<span class="text-background-400">/</span>')}</div></div>
      <div class="hidden md:grid grid-cols-3 gap-x-4 text-[11px]">${stats.map(([k, v]) => `<div><p class="text-[9.5px] tracking-[0.14em] text-foreground-500">${k}</p><p class="font-heading text-[15px] text-foreground-950 mt-1 whitespace-nowrap">${esc(v)}</p></div>`).join("")}</div>
      <div class="hidden md:flex items-center gap-4 justify-self-end"><div class="w-[86px]"><div class="flex items-baseline justify-between text-[10px] text-foreground-500 mb-1"><span>입력</span><span>${pct}%</span></div><span class="block h-[2px] w-full bg-background-300"><span class="block h-full bg-primary-500" style="width:${pct}%"></span></span></div><i class="text-[18px] ri-arrow-right-line ${on ? "text-primary-600" : "text-foreground-400"}"></i></div>
      <span class="md:hidden justify-self-end text-foreground-400"><i class="ri-arrow-right-s-line text-lg"></i></span></button></li>`;
  }).join("");
  $("#departments").innerHTML = `<div class="flex flex-col md:flex-row md:items-end justify-between gap-4"><div><p class="kicker mb-3">CONTENTS — 부서별 식탁</p><h2 class="text-[1.6rem] md:text-[2.1rem] leading-[1.35]">${S.groups.length}개 팀의 회식은, ${S.groups.length}권의 노트</h2></div>
    <p class="font-hand text-[17px] md:text-[19px] text-primary-600 leading-tight md:text-right">팀을 고르면<br>이 지면이 통째로 바뀌어요</p></div>
    <ul class="mt-7 md:mt-9 border-t border-foreground-900/70">${rows}
      <li class="py-4"><form id="dept-add" class="flex flex-wrap items-center gap-2.5"><span class="kicker">ADD</span><input id="dept-name" class="field max-w-[220px]" maxlength="30" placeholder="새 부서 이름 (예: 디자인팀)"><button class="${BTN_SM}"><i class="ri-add-line"></i>부서 추가</button></form></li></ul>`;
  $$("#departments [data-g]").forEach((b) => (b.onclick = () => { selectGroup(b.dataset.g); $("#top").scrollIntoView({ behavior: "smooth" }); }));
  $("#dept-add").onsubmit = async (e) => {
    e.preventDefault(); const name = $("#dept-name").value.trim(); if (!name) return;
    try { const g = await api("/api/groups", { name }); await loadGroups(); await selectGroup(g.id); openMeetingDialog(false); } catch (err) { fail(err); }
  };
}

// ---------- STEP 01 명단 ----------
function renderPeople() {
  const g = group(), m = S.meeting, ps = m?.participants || [];
  const rows = ps.map((p, i) => {
    const prefs = [p.food, p.mood, p.allergy && p.allergy !== "없음" && `${p.allergy} 제외`].filter(Boolean).flatMap((x) => String(x).split(/\s*,\s*/)).filter(Boolean);
    const pill = p.done ? "border-secondary-300 bg-secondary-100 text-secondary-900" : "border-accent-300 bg-accent-100 text-accent-900";
    return `<li class="grid grid-cols-[auto_1fr_auto] md:grid-cols-[36px_1.25fr_0.9fr_0.7fr_0.85fr_auto] items-center gap-x-4 gap-y-1.5 py-4 border-b border-background-300 ink-in">
      <span class="font-heading text-[11px] text-foreground-400">${pad2(i + 1)}</span>
      <div class="flex items-center gap-2.5 min-w-0"><span class="w-8 h-8 shrink-0 rounded-full flex items-center justify-center font-heading text-[12px] ${p.done ? "bg-secondary-100 text-secondary-900 border border-secondary-300" : "bg-background-100 text-foreground-600 border border-background-400"}">${esc(p.name[0])}</span><span class="min-w-0"><strong class="block text-[13px] font-medium text-foreground-950 truncate">${esc(p.name)}</strong><span class="block text-[10px] text-foreground-500 mt-0.5">${esc(p.role || "팀원")}</span></span></div>
      <p class="hidden md:flex items-center gap-1.5 text-[11.5px] text-foreground-700 truncate"><i class="ri-map-pin-line text-foreground-400"></i>${esc(station(p.origin) || "—")}</p>
      <p class="hidden md:flex items-center gap-1.5 text-[11.5px] text-foreground-700">${p.budget ? `<span class="font-heading text-[12.5px]">${p.budget.toLocaleString()}</span>원` : "—"}</p>
      <p class="hidden md:flex items-center gap-1.5 text-[11.5px] text-foreground-700 truncate"><i class="ri-leaf-line text-foreground-400"></i>${esc(p.diet || (p.done ? "없음" : "—"))}</p>
      <div class="flex items-center gap-2 justify-self-end"><span class="text-[10px] px-2 py-0.5 rounded-full border whitespace-nowrap ${pill}">${p.done ? "입력 완료" : "입력 대기"}</span>
        <button type="button" title="이 사람 링크 복사" data-copy="${esc(p.link)}" class="w-7 h-7 inline-flex items-center justify-center text-foreground-500 hover:text-primary-700 cursor-pointer"><i class="ri-link"></i></button>
        <a title="대신 입력하기" href="/p/${esc(p.token)}" target="_blank" class="w-7 h-7 inline-flex items-center justify-center text-foreground-500 hover:text-primary-700"><i class="ri-edit-line"></i></a></div>
      <div class="col-span-3 md:hidden flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-[11px] text-foreground-600"><span class="flex items-center gap-1"><i class="ri-map-pin-line text-foreground-400"></i>${esc(station(p.origin) || "—")}</span>${p.budget ? `<span>${p.budget.toLocaleString()}원</span>` : ""}<span>${esc(p.diet || "")}</span></div>
      <div class="col-span-3 md:col-span-6 flex flex-wrap gap-1.5 mt-1 md:mt-1.5 md:pl-[52px]">${prefs.map((t) => `<span class="text-[10.5px] text-foreground-600 whitespace-nowrap"><span class="text-background-400 mr-1">/</span>${esc(t)}</span>`).join("")}</div></li>`;
  }).join("");
  $("#participants").innerHTML = `<div class="grid grid-cols-1 lg:grid-cols-[0.85fr_1.65fr] gap-8 lg:gap-12">
    <div class="lg:sticky lg:top-24 self-start"><p class="kicker mb-3">STEP 01 — 명단</p><h2 class="text-[1.55rem] md:text-[2rem] leading-[1.4]">${esc(g.name)}<br>참석자별 조건</h2>
      <p class="text-[12.5px] text-foreground-600 leading-[1.95] mt-3 max-w-sm">공유 링크로 로그인 없이 각자 조건을 입력해요.<strong class="text-foreground-900 font-medium"> ${ps.length}명 중 ${m?.done ?? 0}명 완료.</strong></p>
      <div class="flex flex-wrap gap-2 mt-5"><button type="button" id="share-all" class="inline-flex items-center gap-2 border border-foreground-900 text-foreground-950 hover:bg-foreground-950 hover:text-background-50 transition-colors text-[12.5px] px-4 py-2 rounded-[3px] whitespace-nowrap cursor-pointer" ${ps.length ? "" : "disabled"}><i class="ri-link"></i>공유 링크 복사</button>
        <button type="button" id="edit-meeting" class="${BTN_TXT}"><i class="ri-calendar-event-line"></i>${m ? "회식 정보 고치기" : "회식 만들기"}</button></div>
      <p class="font-hand text-[16px] text-primary-600 mt-4 leading-snug">단톡방에 붙여 넣으면<br>각자 링크만 누르면 돼요</p></div>
    <div><div class="hidden md:grid grid-cols-[36px_1.25fr_0.9fr_0.7fr_0.85fr_auto] gap-x-4 pb-2 border-b border-foreground-900/70">${["NO.", "이름", "출발지", "예산", "식단", "상태"].map((t) => `<span class="text-[9.5px] tracking-[0.18em] text-foreground-500">${t}</span>`).join("")}</div>
      <ul>${rows || `<li class="py-8 text-[12px] text-foreground-500">${m ? "아직 참석자가 없어요. 아래에서 이름을 추가하면 개인 링크가 만들어져요." : "먼저 회식을 만들어 주세요."}</li>`}</ul>
      <form id="add-person" class="flex flex-wrap items-center gap-2 mt-4 ${m ? "" : "hidden"}"><input id="ap-name" class="field max-w-[160px]" maxlength="20" placeholder="이름"><input id="ap-role" class="field max-w-[120px]" maxlength="20" placeholder="직함 (선택)"><button class="${BTN_SM}"><i class="ri-user-add-line"></i>참석자 추가</button></form>
      <p class="mt-4 text-[11px] text-foreground-500 flex items-start gap-2 leading-relaxed"><i class="ri-information-line mt-0.5"></i>${m?.team_size ? `${esc(g.name)} 전체 ${m.team_size}명 중 ${ps.length}명이 참석해요. ` : ""}조건이 바뀌면 후보와 예약 확인도 다시 계산돼요.</p></div></div>`;
  $$("#participants [data-copy]").forEach((b) => (b.onclick = () => copy(b.dataset.copy, "개인 링크를 복사했어요")));
  $("#share-all").onclick = () => copy(`[${m.title}] 회식 조건 입력 (로그인 없음, 1분)\n${fmtWhen(m.when_at, true)}${m.area ? ` · ${m.area}` : ""}\n\n${ps.map((p) => `${p.name}: ${p.link}`).join("\n")}`, "단톡방용 링크 묶음을 복사했어요");
  $("#edit-meeting").onclick = () => openMeetingDialog(!!m);
  $("#add-person").onsubmit = async (e) => {
    e.preventDefault(); const name = $("#ap-name").value.trim(); if (!name) return;
    try { await api(`/api/meetings/${m.id}/participants`, { name, role: $("#ap-role").value.trim() || null }); await refreshMeeting(); renderAll(); toast(`${name}님 링크를 만들었어요`); } catch (err) { fail(err); }
  };
}

function openMeetingDialog(edit) {
  const m = edit ? S.meeting : null;
  $("#md-title").textContent = edit ? "회식 정보 고치기" : `${group().name} 새 회식`;
  $("#md-name").value = m?.title || `${group().name} ${new Date().getMonth() + 1}월 회식`;
  $("#md-when").value = m?.when_at ? m.when_at.slice(0, 16) : "";
  $("#md-area").value = m?.area || "";
  $("#meeting-form").dataset.edit = edit ? "1" : "";
  $("#meeting-dlg").showModal();
}
async function saveMeeting(e) {
  if (e.submitter?.value !== "ok") return;
  const body = { group_id: S.gid, title: $("#md-name").value.trim() || "회식",
    when_at: $("#md-when").value ? `${$("#md-when").value}:00+09:00` : null, area: $("#md-area").value || null };
  try {
    S.meeting = $("#meeting-form").dataset.edit ? await api(`/api/meetings/${S.meeting.id}`, body, "PATCH") : await api("/api/meetings", body);
    group().meeting = S.meeting; S.session = null; renderAll(); toast("회식 정보를 저장했어요");
  } catch (err) { fail(err); }
}

// ---------- STEP 02 조건 ----------
function renderConditions() {
  const sm = S.session?.meeting;
  const col = (no, icon, title, body, foot, cls) => `<div class="${cls}"><div class="flex items-center gap-3 mb-4">${circle(no, "w-8 h-8 text-[12px]", no === "03" ? "border-primary-600 text-primary-700" : "")}<h3 class="text-[14px] font-semibold text-foreground-950 flex items-center gap-2"><i class="${icon}"></i>${title}</h3></div>${body}${foot}</div>`;
  const list = (xs, icon) => xs.length ? `<ul class="space-y-2.5">${xs.map((t) => `<li class="text-[12.5px] text-foreground-800 flex gap-2 leading-[1.8]"><i class="${icon} mt-[3px]"></i>${esc(t)}</li>`).join("")}</ul>` : '<p class="text-[12px] text-foreground-500">없음</p>';
  const waiting = '<p class="text-[12px] text-foreground-500 leading-[1.8]">참석자 조건이 모이면 여기서 나눠요.</p>';
  const relaxOn = sm && Object.keys(sm.relax || {}).length;
  const conf = !sm ? `${waiting}<button type="button" data-act="plan" class="${BTN_PRIMARY} mt-4">조건으로 후보 찾기<i class="ri-arrow-right-line"></i></button>`
    : `<div class="space-y-2.5">${sm.conflicts.length ? sm.conflicts.map((c, i) => `<div class="border-l-2 border-primary-300 pl-3 py-1"><div class="flex flex-wrap items-center justify-between gap-2 mb-1"><strong class="text-[12.5px] text-foreground-950 font-medium">${esc(c.title)}</strong><button type="button" data-relax="${i}" title="${esc(c.label || "")}" class="text-[10.5px] px-2 py-0.5 rounded-full whitespace-nowrap cursor-pointer transition-colors border border-primary-400 text-primary-700 hover:bg-primary-100">완화해보기</button></div><p class="text-[11.5px] text-foreground-700 leading-[1.8]">${esc(c.text)}</p></div>`).join("") : '<p class="text-[12px] text-foreground-500">부딪히는 조건이 없어요.</p>'}</div>
      <p class="mt-4 pt-3 border-t border-dotted border-foreground-400/60 text-[11.5px] text-foreground-800">현재 후보 <strong class="font-heading text-[19px] text-primary-700 mx-1">${sm.count}</strong>곳 · 변경은 모임이 결정해요</p>
      <button type="button" data-act="${relaxOn ? "reset" : "plan"}" class="inline-flex items-center gap-1.5 mt-3 text-[11.5px] text-foreground-800 hover:text-primary-700 transition-colors cursor-pointer whitespace-nowrap"><i class="ri-chat-3-line"></i>${relaxOn ? "완화 되돌리고 다시 정리하기" : "조건 다시 정리하기"}<i class="ri-arrow-right-line"></i></button>`;
  $("#conditions").innerHTML = head("STEP 02 — 조건 정리", "필수는 지키고, 선호는 조율해요", hand("다 같이 정하는 거예요<br>혼자 정하지 않아요")) +
    `<div class="grid grid-cols-1 lg:grid-cols-3 mt-6 md:mt-8">
      ${col("01", "ri-shield-check-line text-primary-600", "필수 조건", sm ? list(sm.must, "ri-checkbox-circle-fill text-primary-500") : waiting, '<p class="mt-5 text-[10.5px] text-foreground-500 leading-relaxed">완화 불가 · 하나라도 지켜지지 않으면 후보에서 제외</p>', "py-5 lg:pr-10 lg:py-0")}
      ${col("02", "ri-heart-line text-secondary-600", "선호 조건", sm ? list(sm.nice, "ri-checkbox-blank-circle-line text-secondary-500") : waiting, '<p class="mt-5 text-[10.5px] text-foreground-500 leading-relaxed">조율 가능 · 만족도를 높이는 조건</p>', "py-5 border-t lg:border-t-0 lg:border-l border-dotted border-foreground-400/60 lg:px-10 lg:py-0")}
      ${col("03", "ri-scales-3-line text-primary-600", "충돌과 완화 제안", conf, "", "py-5 border-t lg:border-t-0 lg:border-l border-dotted border-foreground-400/60 lg:pl-10 lg:py-0")}
    </div>${sm?.notes?.length ? `<p class="mt-6 text-[11px] text-foreground-500 flex gap-2"><i class="ri-information-line mt-0.5"></i>${sm.notes.map(esc).join(" · ")}</p>` : ""}`;
  $$("#conditions [data-relax]").forEach((b) => (b.onclick = () => { const c = sm.conflicts[+b.dataset.relax]; planMeeting({ ...(sm.relax || {}), ...c.relax }); }));
  bindActs($("#conditions"));
}

function bindActs(root) {
  $$("[data-act]", root).forEach((b) => (b.onclick = () => {
    const a = b.dataset.act;
    if (a === "plan") planMeeting(S.session?.meeting?.relax || {});
    if (a === "reset") planMeeting({});
  }));
}

async function planMeeting(relax) {
  if (!S.meeting) { openMeetingDialog(false); return toast("먼저 회식을 만들어 주세요"); }
  if (!S.meeting.done) return toast("조건을 입력한 참석자가 아직 없어요");
  S.selected = null; S.log = []; renderLog();
  logLocal("coordinator", "참석자 조건을 모아 후보를 찾는 중…");
  $$("[data-act=plan]").forEach((b) => { b.disabled = true; b.innerHTML = '<i class="ri-loader-4-line animate-spin"></i>찾는 중'; });
  try {
    S.session = await api(`/api/meetings/${S.meeting.id}/plan`, relax);
    S.planCount[S.gid] = S.session.meeting.count;
    connect(S.session.id); renderAll();
    $("#conditions").scrollIntoView({ behavior: "smooth" });
  } catch (e) { fail(e); renderAll(); }
}

function connect(id) {
  if (S.es) S.es.close();
  S.es = new EventSource(`/api/sessions/${id}/events`);
  S.es.addEventListener("log", (m) => {
    const { ev, session } = JSON.parse(m.data);
    if (S.session?.id !== session.id) return;
    S.session = session;
    S.log.push(ev); renderLog();
    if (ev.type === "approval" && ev.data?.placeId) S.selected = ev.data.placeId;
    if (session.reservation) S.booked[S.gid] = session.reservation;
    renderCandidates(); renderHero();
  });
}

// ---------- STEP 03·04 후보 ----------
function art(p) {
  const s = `${p.subtype || ""} ${p.category || ""}`;
  if (/bbq|grill|고기|구이|숯불|정육/.test(s)) return ART.grill;
  if (/western|italian|이탈리|양식|파스타|비스트로|와인/.test(s)) return ART.western;
  return ART.korean;
}
function bookable(c) { return !c.tried_reservation && (S.session.nowMode ? POS.has(c.status) : true); }

function statusBadge(c) {
  const t = STATUS_KO[c.status] || c.status;
  const r = S.session?.reservation || S.lab?.reservation;
  if (r && r.place_id === c.place.id) return '<span class="text-[10.5px] px-2 py-0.5 border whitespace-nowrap bg-primary-100 text-primary-800 border-primary-300"><i class="ri-checkbox-circle-fill mr-1"></i>예약 확정</span>';
  if (c.tried_reservation) return '<span class="text-[10.5px] px-2 py-0.5 border whitespace-nowrap border-primary-300 text-primary-700">예약 거절 · 다음 곳으로</span>';
  if (POS.has(c.status)) return `<span class="text-[10.5px] px-2 py-0.5 border whitespace-nowrap bg-secondary-100 text-secondary-900 border-secondary-300">사장님 확인 완료 · ${t}${c.status_at ? ` · ${esc(c.status_at)}` : ""}</span>`;
  if (c.status === "asking") return `<span class="text-[10.5px] px-2 py-0.5 border whitespace-nowrap bg-accent-100 text-accent-900 border-accent-300"><span class="pulse-dot inline-block w-1.5 h-1.5 rounded-full bg-accent-600 mr-1 align-middle"></span>사장님 확인 중</span>`;
  if (NEG.has(c.status) || c.status === "soon") return `<span class="text-[10.5px] px-2 py-0.5 border whitespace-nowrap border-primary-300 text-primary-700">${t}</span>`;
  return `<span class="text-[10.5px] px-2 py-0.5 border whitespace-nowrap border-background-400 text-foreground-600">사장님 확인 전</span>`;
}

function candArticle(c, i) {
  const p = c.place, flip = i % 2 === 1, sel = S.selected === p.id;
  const mem = c.evidence.find((e) => e.kind === "memory");
  const data = c.evidence.filter((e) => e.kind === "data").map((e) => e.label);
  const travel = Object.entries(c.travel || {});
  const canPick = S.session.state === "await_approval" && bookable(c);
  const checkIcon = (v) => (v === "충족" ? "ri-check-line text-secondary-600" : v === "미충족" ? "ri-close-line text-primary-600" : "ri-question-line text-accent-700");
  return `<article class="grid grid-cols-1 lg:grid-cols-[0.92fr_1.08fr] gap-6 md:gap-10 items-center py-8 md:py-10 border-b border-background-300 fade-up ${NEG.has(c.status) ? "opacity-60" : ""}">
    <figure class="relative ${flip ? "lg:order-2" : ""}">
      <span aria-hidden="true" class="pointer-events-none absolute inset-y-8 w-[72%] ${flip ? "bg-secondary-200/80 left-0" : "bg-primary-200/80 right-0"}"></span>
      <div class="relative ${flip ? "rotate-[1deg]" : "rotate-[-1.1deg]"} border border-background-300 bg-background-100 p-2 md:p-2.5"><span class="tape -top-2 ${flip ? "right-10 rotate-[6deg]" : "left-10 rotate-[-6deg]"}"></span>
        <div class="w-full aspect-[4/3] overflow-hidden bg-background-50"><img alt="${esc(p.category || "식당")} 손그림 일러스트" title="실제 매장 사진은 '사진·메뉴·위치'에서 볼 수 있어요" class="w-full h-full object-cover object-top" src="${art(p)}" loading="lazy" onerror="this.remove()"></div></div>
      <span class="absolute -top-3 -left-2">${circle(i + 1, "w-10 h-10 md:w-11 md:h-11 text-[14px] md:text-[16px]", i === 0 ? "border-primary-600 text-primary-700" : "")}</span>
      ${i === 0 ? '<span class="absolute -bottom-2.5 left-1/2 -translate-x-1/2 bg-accent-500 text-foreground-950 text-[10px] tracking-[0.14em] px-2.5 py-1 whitespace-nowrap rotate-[-2deg]">1순위 추천</span>' : ""}
    </figure>
    <div>
      <p class="kicker">NO.${pad2(i + 1)} · ${esc(p.category || "식당")}${p.station ? ` · ${esc(station(p.station))}${p.walk_min ? ` ${p.walk_min}분` : ""}` : ""}</p>
      <h3 class="font-heading font-bold text-[1.5rem] md:text-[2rem] leading-[1.25] text-foreground-950 mt-2 tracking-[-0.04em]">${esc(p.name)}</h3>
      <div class="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 mt-2.5"><span class="text-[10.5px] tracking-[0.16em] text-foreground-500">메뉴 평균</span><span class="font-heading text-[1.35rem] md:text-[1.6rem] text-primary-600 leading-none">${p.price ? won(p.price) : "가격 확인 필요"}</span>${p.address ? `<span class="text-[11px] text-foreground-500 truncate max-w-[60%]">/ ${esc(p.address)}</span>` : ""}</div>
      <div class="flex flex-wrap items-center gap-2 mt-3.5">
        ${mem ? `<span class="text-[10.5px] px-2 py-0.5 border border-background-400 bg-background-100 text-foreground-700 whitespace-nowrap"><i class="ri-history-line mr-1"></i>${esc(mem.label)}</span>` : ""}
        ${statusBadge(c)}${p.reservable_here ? '<span class="text-[10.5px] px-2 py-0.5 border whitespace-nowrap border-secondary-300 text-secondary-800"><i class="ri-calendar-check-line mr-1"></i>앱에서 예약</span>' : ""}
        ${c.total != null ? `<span class="text-[10.5px] text-foreground-500 whitespace-nowrap">종합 <strong class="font-heading text-[13px] text-foreground-950">${c.total}</strong>점</span>` : ""}</div>
      <div class="flex flex-wrap gap-x-3 gap-y-1.5 mt-3">${Object.entries(c.checks || {}).map(([k, v]) => `<span class="text-[10.5px] text-foreground-700 flex items-center gap-1 whitespace-nowrap"><i class="${checkIcon(v)}"></i>${esc(k)} ${esc(v)}<span class="text-background-400 ml-1">/</span></span>`).join("")}</div>
      ${travel.length ? `<div class="mt-5 pt-4 border-t border-dotted border-foreground-400/60"><p class="text-[9.5px] tracking-[0.18em] text-foreground-500 mb-2.5">참석자별 이동 · ${esc(c.travel_source || "")}</p><div class="grid grid-cols-2 gap-x-5 gap-y-2">
        ${travel.map(([n, mnt]) => `<div class="flex items-center gap-2 text-[11px]"><span class="w-10 text-foreground-700 shrink-0 truncate">${esc(n)}</span><span class="flex-1 h-[2px] bg-background-300 overflow-hidden"><span class="block h-full ${mnt > 25 ? "bg-primary-500" : "bg-secondary-500"}" style="width:${Math.min(100, mnt / 35 * 100)}%"></span></span><span class="w-7 text-right shrink-0 ${mnt > 25 ? "text-primary-700" : "text-foreground-500"}">${mnt}분</span></div>`).join("")}</div></div>` : ""}
      ${c.reason ? `<p class="mt-4 text-[11.5px] text-foreground-700 leading-[1.9]"><span class="font-hand text-[15px] text-primary-600 mr-1.5">왜 여기?</span>${esc(c.reason)}</p>` : ""}
      ${data.length ? `<p class="mt-2 text-[10.5px] text-foreground-500 leading-relaxed">유미 데이터 · ${data.map(esc).join(" / ")}</p>` : ""}
      <div class="flex flex-wrap items-center gap-2 mt-4">
        <button type="button" data-detail="${esc(p.id)}" class="${BTN_SM}"><i class="ri-image-line"></i>사진 · 메뉴 · 위치</button>
        ${canPick ? `<button type="button" data-pick="${esc(p.id)}" class="${sel ? "inline-flex items-center gap-1.5 bg-foreground-950 text-background-50 text-[11.5px] px-3 py-1.5 rounded-[3px] cursor-pointer" : BTN_SM}">${sel ? '<i class="ri-check-line"></i>예약할 곳' : "이곳으로 예약"}</button>` : ""}
      </div></div></article>`;
}

function actionBar() {
  const s = S.session; if (!s) return "";
  const last = [...S.log].reverse().find((e) => e.agent === "negotiator");
  const asking = s.state === "asking", canAsk = ["idle", "exhausted"].includes(s.state);
  const live = S.cfg?.live;
  const label = asking ? "사장님 답 기다리는 중" : s.nowMode ? "사장님께 지금 자리 묻기 (상위 3곳)" : "예약 요청 준비 (1순위부터)";
  return `<div class="mt-6 border border-foreground-900/70 bg-background-100 px-4 md:px-5 py-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
    <div class="min-w-0"><p class="kicker">AGENT · 교섭</p><p class="text-[12.5px] text-foreground-800 mt-1.5 leading-[1.7]">${esc(last?.msg || (s.nowMode ? "90분 안의 회식이라 사장님께 실시간으로 자리를 물어요. 먼저 '가능'이라고 답한 곳부터 예약을 권해요." : "날짜가 남은 회식이라 예약 요청 자체가 사장님 확인이 돼요. 거절되면 다음 순위로 자동으로 넘어가요."))}</p>
      <p class="text-[10.5px] mt-1 ${live ? "text-primary-700" : "text-foreground-500"}"><i class="${live ? "ri-alarm-warning-line" : "ri-shield-check-line"} mr-1"></i>${live ? "실제 요청 모드 — 사장님 휴대폰으로 갑니다" : `${esc(S.cfg?.label || "")} · 사장님께 아무것도 가지 않아요`}</p></div>
    <div class="flex flex-col items-stretch md:items-end gap-2 shrink-0">${live ? '<label class="text-[11px] text-primary-700 flex items-center gap-1.5"><input type="checkbox" id="live-ok"> 실제로 보내는 것에 동의</label>' : ""}
      <button type="button" id="ask" class="${BTN_PRIMARY}" ${canAsk ? "" : "disabled"}>${asking ? '<i class="ri-loader-4-line animate-spin"></i>' : '<i class="ri-customer-service-2-line"></i>'}${label}</button></div></div>`;
}

function approvePanel() {
  const s = S.session; if (s.state !== "await_approval") return "";
  const c = s.candidates.find((x) => x.place.id === S.selected && bookable(x)) || s.candidates.find(bookable);
  if (!c) return "";
  S.selected = c.place.id;
  return `<div class="mt-4 relative border border-primary-400 bg-primary-50 px-4 md:px-5 py-4 ink-in"><span class="tape -top-2 right-8 rotate-[4deg]"></span>
    <p class="kicker text-primary-700">APPROVAL — 막내 확인</p>
    <p class="text-[13px] text-foreground-950 mt-1.5"><strong class="font-heading text-[16px]">${esc(c.place.name)}</strong> · ${s.constraints.party}명 · ${fmtWhen(s.constraints.when)}</p>
    <div class="flex flex-wrap items-center gap-2.5 mt-3"><input id="phone" class="field max-w-[180px]" inputmode="tel" placeholder="예약자 연락처 010-0000-0000" autocomplete="tel">
      <label class="text-[11.5px] text-foreground-700 flex items-center gap-1.5"><input type="checkbox" id="fallback" checked>${s.nowMode ? "거절되면 '가능'이라 답한 다음 가게로" : "거절되면 다음 순위로 바로"}</label>
      <button type="button" id="reserve" class="${BTN_PRIMARY}"><i class="ri-send-plane-line"></i>예약 요청 보내기</button></div>
    <p class="text-[10.5px] text-foreground-500 mt-2">연락처는 이번 예약 요청에만 쓰고 저장하지 않아요. 기록에는 가운데를 가려서 남겨요.</p></div>`;
}

function confirmedPanel() {
  const r = S.session.reservation; if (!r) return "";
  return `<div class="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
    <div class="relative border border-secondary-400 bg-secondary-50 p-5"><span class="absolute right-5 top-4 stamp border-2 border-primary-600 text-primary-700 font-heading text-[13px] px-2.5 py-1 rotate-[-4deg]">예약 확정</span>
      <p class="kicker">CONFIRMED — 단톡방 공지</p><h3 class="font-heading text-[1.3rem] mt-2">${esc(r.place_name)}</h3><p class="text-[12px] text-foreground-600 mt-1">${fmtWhen(r.when, true)} · ${r.guests}명</p>
      <textarea id="notice" rows="7" class="field mt-3 font-body leading-[1.8]" readonly>불러오는 중…</textarea>
      <div class="flex flex-wrap gap-2 mt-3"><button type="button" id="copy-notice" class="${BTN_SM}"><i class="ri-file-copy-line"></i>공지 복사</button><button type="button" data-detail="${esc(r.place_id)}" class="${BTN_TXT}"><i class="ri-map-pin-line"></i>위치 공유</button></div></div>
    <div class="space-y-5">
      <div class="border-t border-foreground-900/70 pt-3"><p class="kicker">인원 변경</p><div class="flex flex-wrap items-center gap-2 mt-2"><input id="new-guests" type="number" min="1" max="50" value="${r.guests + 2}" class="field max-w-[90px]"><span class="text-[12px] text-foreground-600">명으로</span><button type="button" id="headcount" class="${BTN_SM}">가게에 다시 확인</button></div><p class="text-[10.5px] text-foreground-500 mt-1.5">확정한 가게부터 다시 묻고, 안 되면 다른 후보를 찾아요.</p></div>
      <div class="border-t border-foreground-900/70 pt-3"><p class="kicker">2차</p><button type="button" id="after" class="${BTN_SM} mt-2"><i class="ri-goblet-line"></i>1차 근처 2차 찾기</button>
        <ul class="mt-2">${S.session.after.map((c) => `<li class="flex items-center justify-between gap-3 py-2 border-b border-background-300 text-[12px]"><span class="truncate">${esc(c.place.name)} <span class="text-foreground-500">· ${esc(c.place.category || "")}${c.distance_m != null ? ` · ${c.distance_m}m` : ""}</span></span>${statusBadge(c)}</li>`).join("")}</ul></div>
      <div class="border-t border-foreground-900/70 pt-3"><p class="kicker">다녀와서 · 모임 기억에 남기기</p>
        <div class="flex items-center gap-1 mt-2" id="stars">${[1, 2, 3, 4, 5].map((i) => `<button type="button" data-star="${i}" class="text-[20px] cursor-pointer ${i <= S.stars ? "text-primary-500" : "text-background-400"}"><i class="ri-star-fill"></i></button>`).join("")}</div>
        <div class="flex flex-wrap items-center gap-2.5 mt-2"><input id="spent" type="number" step="1000" class="field max-w-[140px]" placeholder="1인 지출(원)"><label class="text-[11.5px] text-foreground-700 flex items-center gap-1.5"><input type="checkbox" id="revisit" checked>다시 가고 싶어요</label><button type="button" id="save-fb" class="${BTN_SM}">기록 저장</button></div></div>
    </div></div>`;
}

function renderCandidates() {
  const s = S.session, g = group();
  const sm = s?.meeting;
  const right = `<p class="text-[10.5px] text-foreground-500 leading-relaxed md:text-right">점수 기준 · 필수 50% · 이동 균형 30% · 선호 20%<br class="hidden md:block">25분이 넘는 이동은 테라코타로 표시했어요${sm?.travel_source ? `<br class="hidden md:block">이동 시간 · ${esc(sm.travel_source)}` : ""}</p>`;
  if (!s || s.lab) {
    $("#candidates").innerHTML = head("STEP 03·04 — 후보 비교", `${esc(g.name)} 추천 식당`, right) +
      `<div class="py-14 text-center"><p class="font-hand text-[20px] text-primary-600">아직 후보를 찾지 않았어요</p><p class="text-[12px] text-foreground-500 mt-2">입력한 참석자 조건으로 Hey Yumi에서 가게를 찾고, 기억·이동·조건으로 줄을 세워요.</p><button type="button" data-act="plan" class="${BTN_PRIMARY} mt-5">조건으로 후보 찾기<i class="ri-arrow-right-line"></i></button></div>`;
    return bindActs($("#candidates"));
  }
  const main = s.candidates.slice(0, 5), rest = s.candidates.slice(5);
  $("#candidates").innerHTML = head("STEP 03·04 — 후보 비교", `${esc(g.name)} 추천 식당`, right) + actionBar() + approvePanel() + confirmedPanel() +
    `<div class="mt-4">${main.length ? main.map(candArticle).join("") : '<p class="py-10 text-[12.5px] text-foreground-500">조건을 모두 지키는 가게가 없어요. 위 충돌에서 완화해보기를 눌러 보세요.</p>'}</div>
    ${rest.length ? `<details class="mt-4"><summary class="cursor-pointer text-[12px] text-foreground-700">그 밖의 후보 ${rest.length}곳</summary><ul class="mt-2">${rest.map((c, i) => `<li class="flex flex-wrap items-center justify-between gap-2 py-2.5 border-b border-background-300 text-[12px]"><span>${pad2(i + 6)} · <strong class="font-medium">${esc(c.place.name)}</strong> <span class="text-foreground-500">${esc(c.place.category || "")} · ${c.place.price ? won(c.place.price) : "가격 확인 필요"}</span></span><span class="flex items-center gap-2">${c.total != null ? `<span class="text-foreground-500">${c.total}점</span>` : ""}<button type="button" data-detail="${esc(c.place.id)}" class="${BTN_TXT}">상세</button></span></li>`).join("")}</ul></details>` : ""}
    <p class="mt-5 text-[11px] text-foreground-500 flex items-start gap-2 leading-relaxed"><i class="ri-information-line mt-0.5"></i>‘확인 필요’로 남은 항목은 매장에 직접 확인이 필요해요. 사장님이 답하면 이 화면이 바로 바뀌어요.</p>`;
  bindCandidates();
}

function bindCandidates() {
  const s = S.session;
  $$("#candidates [data-detail]").forEach((b) => (b.onclick = () => openDetail(b.dataset.detail)));
  $$("#candidates [data-pick]").forEach((b) => (b.onclick = () => { S.selected = b.dataset.pick; renderCandidates(); $("#phone")?.focus(); }));
  const ask = $("#ask");
  if (ask) ask.onclick = async () => {
    if (S.cfg.live && !$("#live-ok")?.checked) return toast("실제 요청 모드예요. 동의 체크 후 눌러 주세요");
    ask.disabled = true;
    try { await api(`/api/sessions/${s.id}/ask`, {}); } catch (e) { fail(e); ask.disabled = false; }
  };
  const res = $("#reserve");
  if (res) res.onclick = async () => {
    const phone = $("#phone").value.trim();
    if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phone)) return toast("연락처 형식을 확인해 주세요");
    if (S.cfg.live && !$("#live-ok")?.checked) return toast("실제 요청 모드예요. 위의 동의 체크가 필요해요");
    res.disabled = true;
    try { await api(`/api/sessions/${s.id}/approve`, { place_id: S.selected, phone, auto_fallback: $("#fallback").checked }); } catch (e) { fail(e); res.disabled = false; }
  };
  if (s.reservation) {
    const key = `${s.reservation.reservation_id}:${s.reservation.guests}`;
    if (S.noticeKey === key && S.notice) $("#notice").value = S.notice;
    else api(`/api/sessions/${s.id}/notice`).then(({ text }) => { S.notice = text; S.noticeKey = key; const n = $("#notice"); if (n) n.value = text; }).catch(fail);
    $("#copy-notice").onclick = () => copy($("#notice").value, "공지문을 복사했어요");
    $("#headcount").onclick = () => api(`/api/sessions/${s.id}/headcount`, { guests: Number($("#new-guests").value) }).then(() => toast("가게에 다시 물어보는 중")).catch(fail);
    $("#after").onclick = () => api(`/api/sessions/${s.id}/afterparty`, {}).then(() => toast("1차 근처에서 2차를 찾는 중")).catch(fail);
    $$("#stars [data-star]").forEach((b) => (b.onclick = () => { S.stars = +b.dataset.star; $$("#stars [data-star]").forEach((x) => x.className = `text-[20px] cursor-pointer ${+x.dataset.star <= S.stars ? "text-primary-500" : "text-background-400"}`); }));
    $("#save-fb").onclick = saveFeedback;
  }
}

async function saveFeedback() {
  const r = S.session.reservation, c = S.session.candidates.find((x) => x.place.id === r.place_id);
  try {
    await api("/api/feedback", { group_id: S.gid, place_id: r.place_id, place_name: r.place_name, attrs: c ? c.place.attrs : [],
      satisfaction: S.stars, revisit: $("#revisit").checked, per_person: Number($("#spent").value) || null });
    S.mem = await api(`/api/groups/${S.gid}/memory`);
    await refreshMeeting(); renderMemory(); renderDepts(); renderHero();
    toast("기록했어요 · 다음 추천부터 반영돼요");
    $("#memory").scrollIntoView({ behavior: "smooth" });
  } catch (e) { fail(e); }
}

// ---------- 가게 상세 ----------
async function openDetail(id) {
  const dlg = $("#detail");
  dlg.innerHTML = '<div class="p-8 text-[12px] text-foreground-500">불러오는 중…</div>'; dlg.showModal();
  try {
    const d = await api(`/api/places/${encodeURIComponent(id)}`);
    const q = encodeURIComponent(d.name);
    const kakao = d.lat ? `https://map.kakao.com/link/map/${q},${d.lat},${d.lng}` : `https://map.kakao.com/?q=${q}`;
    const naver = `https://map.naver.com/p/search/${encodeURIComponent(`${d.name} ${d.address || ""}`.trim())}`;
    dlg.innerHTML = `<div class="p-5 md:p-7"><div class="flex items-start justify-between gap-4 border-b border-foreground-900/70 pb-3"><div><p class="kicker">PLACE — Hey Yumi</p><h3 class="font-heading text-[1.5rem] mt-1.5">${esc(d.name)}</h3>
      <p class="text-[11.5px] text-foreground-600 mt-1">${esc([d.category, d.price && `메뉴 평균 ${won(d.price)}`, d.station && `${station(d.station)}${d.walk_min ? ` 도보 ${d.walk_min}분` : ""}`, d.phone].filter(Boolean).join(" · "))}</p></div>
      <button type="button" id="d-close" class="w-8 h-8 inline-flex items-center justify-center text-foreground-600 hover:text-foreground-950 cursor-pointer" aria-label="닫기"><i class="ri-close-line text-xl"></i></button></div>
      ${d.summary ? `<p class="text-[12px] text-foreground-700 leading-[1.9] mt-3">${esc(d.summary)}</p>` : ""}
      <div class="grid grid-cols-3 gap-2 mt-4">${d.photos?.length ? d.photos.slice(0, 6).map((u) => `<img src="${esc(u)}" alt="${esc(d.name)} 사진" loading="lazy" class="w-full aspect-square object-cover border border-background-300">`).join("") : '<p class="col-span-3 text-[11.5px] text-foreground-500 py-3">사장님이 올린 사진이 아직 없어요.</p>'}</div>
      <p class="kicker mt-5 mb-1">MENU</p><ul>${d.menu?.length ? d.menu.slice(0, 10).map((m) => `<li class="flex items-baseline justify-between gap-3 py-2 border-b border-dotted border-foreground-400/60 text-[12.5px]"><span>${esc(m.name)}${m.recommend ? ' <span class="text-[10px] text-primary-700 ml-1">추천</span>' : ""}</span><span class="font-heading">${m.price ? won(m.price) : "가격 확인 필요"}</span></li>`).join("") : '<li class="text-[11.5px] text-foreground-500 py-2">메뉴 정보가 없어요.</li>'}</ul>
      <p class="kicker mt-5 mb-1">LOCATION</p><p class="text-[12.5px] text-foreground-800">${esc(d.address || (d.station ? `${station(d.station)} 근처` : "주소 확인 필요"))}</p>
      <div class="flex flex-wrap gap-2 mt-3"><a target="_blank" rel="noopener" href="${kakao}" class="${BTN_SM}">카카오맵</a><a target="_blank" rel="noopener" href="${naver}" class="${BTN_SM}">네이버지도</a>${d.placeUrl ? `<a target="_blank" rel="noopener" href="${esc(d.placeUrl)}" class="${BTN_SM}">Hey Yumi</a>` : ""}<button type="button" id="d-share" class="inline-flex items-center gap-1.5 bg-primary-500 hover:bg-primary-600 text-background-50 text-[11.5px] px-3 py-1.5 rounded-[3px] cursor-pointer"><i class="ri-share-forward-line"></i>위치 공유</button></div></div>`;
    $("#d-share").onclick = async () => {
      const text = `${d.name}\n${d.address || ""}\n${kakao}`.trim();
      try { if (navigator.share) await navigator.share({ title: d.name, text, url: kakao }); else await copy(text, "위치를 복사했어요"); } catch { /* 공유 창 닫음 */ }
    };
  } catch (e) {
    dlg.innerHTML = `<div class="p-6"><p class="text-[13px]">가게 정보를 불러오지 못했어요</p><p class="text-[11.5px] text-foreground-500 mt-1">${esc(e.message)}</p><button id="d-close" class="${BTN_SM} mt-4">닫기</button></div>`;
  }
  $("#d-close").onclick = () => dlg.close();
}

// ---------- 작업 로그 ----------
function logLocal(agent, msg) { S.log.push({ t: new Date().toTimeString().slice(0, 8), agent: agent === "error" ? "app" : agent, type: agent === "error" ? "error" : "info", msg }); renderLog(); }
function renderLog() {
  const tag = (a) => ({ coordinator: "bg-secondary-100 text-secondary-900 border-secondary-300", scout: "bg-background-50 text-foreground-800 border-background-400", negotiator: "bg-primary-100 text-primary-800 border-primary-300", memory: "bg-accent-100 text-accent-900 border-accent-300", travel: "bg-secondary-50 text-secondary-800 border-secondary-300", afterparty: "bg-accent-50 text-accent-800 border-accent-300" }[a] || "bg-background-50 text-foreground-700 border-background-400");
  $("#log").innerHTML = head("AGENT LOG — 작업 로그", "에이전트가 한 일, 그대로", hand("숨기는 단계 없이<br>전부 남겨요")) +
    `<div class="grid grid-cols-1 lg:grid-cols-[1fr_2.2fr] gap-6 mt-6"><div class="text-[11.5px] text-foreground-600 leading-[1.95] space-y-2">
      <p><strong class="text-foreground-900 font-medium">조율</strong> 참석자 조건을 필수·선호로 나누고 부딪히는 곳을 찾아요.</p>
      <p><strong class="text-foreground-900 font-medium">탐색</strong> Hey Yumi에서 지역·조건으로 가게를 찾아요.</p>
      <p><strong class="text-foreground-900 font-medium">이동</strong> 참석자별 출발지에서 걸리는 시간을 재요.</p>
      <p><strong class="text-foreground-900 font-medium">교섭</strong> 사장님께 자리를 묻고, 예약을 요청하고, 거절되면 다음 곳으로.</p>
      <p><strong class="text-foreground-900 font-medium">기억</strong> 다녀온 평가를 다음 추천에 반영해요.</p></div>
      <ol class="log-scroll max-h-[340px] overflow-y-auto border-t border-foreground-900/70">${S.log.length ? S.log.map((e) => `<li class="grid grid-cols-[64px_44px_1fr] gap-3 items-baseline py-2 border-b border-background-300 text-[11.5px] ${e.type === "error" ? "text-primary-700" : "text-foreground-800"}"><span class="font-mono text-[10.5px] text-foreground-500">${esc(e.t)}</span><span class="text-[10px] text-center border px-1 ${tag(e.agent)}">${esc(AGENT_KO[e.agent] || e.agent)}</span><span class="leading-[1.7]">${esc(e.msg)}</span></li>`).join("") : '<li class="py-6 text-[12px] text-foreground-500">후보를 찾으면 여기에 한 줄씩 쌓여요.</li>'}</ol></div>`;
  const ol = $("#log ol"); ol.scrollTop = ol.scrollHeight;
}

// ---------- STEP 05·06 기억 ----------
function renderMemory() {
  const g = group(), v = S.mem?.visits || [], prof = S.mem?.profile || {};
  const avg = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
  const spent = v.filter((x) => x.per_person).map((x) => x.per_person);
  const top = v.filter((x) => x.satisfaction >= 4.4 && x.per_person).map((x) => x.per_person);
  const stats = v.length ? [
    [`최근 ${v.length}회 1인 평균 지출`, spent.length ? won(Math.round(avg(spent) / 1000) * 1000) : "기록 없음"],
    ["평균 만족도", `${avg(v.map((x) => x.satisfaction)).toFixed(1)} / 5`],
    ["재방문 희망 장소", `${v.filter((x) => x.revisit).length}곳`],
    ["만족도 높은 가격대", top.length ? `${man(Math.min(...top))}~${man(Math.max(...top))}` : "—"],
  ] : [["기록된 회식", "0회"]];
  const draft = S.blog || (v[0] ? "다녀온 회식 기록으로 후기 초안을 만들어요. 기록에 없는 맛 평가나 숫자는 쓰지 않아요." : "아직 다녀온 기록이 없어요.");
  $("#memory").innerHTML = head("STEP 05·06 — 모임 기억", `${esc(g.name)}은 이렇게 먹어왔어요`, hand("남긴 기록이<br>다음 회식을 가볍게 해요")) +
    `<div class="grid grid-cols-1 lg:grid-cols-[0.8fr_1.7fr] gap-8 lg:gap-12 mt-6 md:mt-8"><div>
      <ul class="border-t border-secondary-300">${stats.map(([k, val]) => `<li class="flex items-baseline justify-between gap-3 py-3.5 border-b border-secondary-300"><span class="text-[11px] text-foreground-600 leading-snug max-w-[58%]">${k}</span><span class="font-heading text-[17px] md:text-[19px] whitespace-nowrap text-foreground-950">${esc(val)}</span></li>`).join("")}</ul>
      <p class="mt-3 text-[10.5px] text-foreground-500 leading-relaxed">지출과 만족도는 방문 기록에서 자동으로 계산돼요.${prof.summary ? `<br>${esc(prof.summary)}` : ""}</p></div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-8"><div><div class="flex items-baseline justify-between gap-3 pb-2 border-b border-foreground-900/70"><h3 class="text-[13px] font-semibold text-foreground-950">최근 방문 기록</h3><span class="text-[10px] text-foreground-500">최근 ${Math.min(4, v.length)}회</span></div>
      <ul>${v.slice(0, 4).map((x) => { const tag = x.revisit ? ["재방문 희망", "text-secondary-700"] : x.satisfaction >= 3 ? ["보류", "text-accent-700"] : ["다시 안 감", "text-primary-700"]; const d = new Date(x.visited_at);
        return `<li class="py-3 border-b border-secondary-300"><div class="flex items-baseline justify-between gap-2"><p class="text-[12.5px] text-foreground-900 truncate">${esc(x.place_name)}</p><span class="text-[10px] whitespace-nowrap ${tag[1]}">${tag[0]}</span></div><div class="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-[10.5px] text-foreground-500"><span>${d.getMonth() + 1}월 ${d.getDate()}일</span>${x.per_person ? `<span class="text-background-400">/</span><span>1인 ${x.per_person.toLocaleString()}원</span>` : ""}<span class="text-background-400">/</span><span class="flex items-center gap-1"><i class="ri-star-fill text-primary-400"></i>${x.satisfaction}</span></div></li>`; }).join("") || '<li class="py-4 text-[12px] text-foreground-500">예약을 마치고 평가를 남기면 여기에 쌓여요.</li>'}</ul></div>
      <div class="relative rotate-[-0.8deg] border border-secondary-300 bg-background-50 p-4 md:p-5"><span class="tape -top-2 right-6 rotate-[5deg]"></span>
        <div class="flex items-baseline justify-between gap-3 pb-2 border-b border-dotted border-foreground-400/60"><h3 class="text-[13px] font-semibold text-foreground-950 flex items-center gap-1.5"><i class="ri-quill-pen-line text-primary-600"></i>블로그 초안</h3><span class="text-[9px] tracking-[0.18em] text-foreground-400">DRAFT</span></div>
        <p id="blog" class="font-hand text-[17px] md:text-[18px] text-foreground-800 leading-[1.65] mt-3 min-h-[90px] focus:outline-none" ${S.blog ? 'contenteditable="true"' : ""}>${esc(draft)}</p>
        <div class="flex flex-wrap gap-2 mt-4 pt-3 border-t border-dotted border-foreground-400/60"><button type="button" id="blog-make" class="${BTN_SM}" ${v.length ? "" : "disabled"}>초안 만들기</button><button type="button" id="blog-copy" class="${BTN_TXT}" ${S.blog ? "" : "disabled"}><i class="ri-file-copy-line"></i>복사</button></div></div>
    </div></div>`;
  $("#blog-make").onclick = async () => {
    $("#blog-make").disabled = true;
    try { const { text, how } = await api(`/api/groups/${S.gid}/blog`, {}); S.blog = text; renderMemory(); toast(how === "llm" ? "기록을 바탕으로 문장을 다듬었어요" : "기록으로 초안을 만들었어요"); } catch (e) { fail(e); $("#blog-make").disabled = false; }
  };
  $("#blog-copy").onclick = () => copy($("#blog").innerText, "초안을 복사했어요");
}

function renderFooter() {
  $("#f-depts").innerHTML = S.groups.map((g) => `<li><button type="button" data-fg="${esc(g.id)}" class="text-[12px] cursor-pointer transition-colors whitespace-nowrap ${g.id === S.gid ? "text-primary-700" : "text-foreground-700 hover:text-foreground-950"}">${esc(g.name)}<span class="text-[10px] text-foreground-500 ml-1.5">기억 ${pad2(g.meeting?.visits || 0)}</span></button></li>`).join("");
  $$("#f-depts [data-fg]").forEach((b) => (b.onclick = () => { selectGroup(b.dataset.fg); scrollTo({ top: 0, behavior: "smooth" }); }));
}

// ---------- 개발자 모드 · 실매장 테스트 ----------
function setDev(on) {
  S.dev = on; localSet("dev", on ? "1" : "0");
  $("#lab").classList.toggle("hidden", !on);
  $("#dev-toggle").textContent = on ? "개발자 모드 끄기" : "개발자 모드 · 실매장 테스트";
  if (on) renderLab();
}

function defaultLabWhen() {
  const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(15, 0, 0, 0);
  return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function renderLab() {
  const live = S.cfg?.live || (S.cfg?.livePlaces || []).length > 0, L = S.lab;
  const modeLine = !S.cfg ? "" : S.cfg.mode !== "rest" ? "지금은 데모 데이터(YUMI_MODE=mock)라 실제 가게는 검색되지 않아요. .env에서 YUMI_MODE=rest로 바꾸면 실제 Hey Yumi에서 찾습니다."
    : S.cfg.livePlaces?.length ? `실제 요청은 이 가게만: ${S.cfg.livePlaces.join(", ")} — 사장님 휴대폰으로 갑니다. 메인 화면의 다른 가게는 전부 시뮬레이션.`
    : live ? "실제 요청 모드 — 문의·예약이 사장님 휴대폰으로 갑니다." : `${S.cfg.label} — 검색은 실제, 문의·예약은 사장님께 가지 않아요.`;
  const results = S.labResults.map((r) => {
    const p = r.place, today = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"][new Date().getDay()];
    const h = r.hours.find((x) => x.day === today);
    return `<li class="py-3.5 border-b border-accent-200 flex flex-col md:flex-row md:items-center justify-between gap-3"><div class="min-w-0"><p class="text-[13px]"><strong class="font-heading text-[15px]">${esc(p.name)}</strong> <span class="text-foreground-500 text-[11px]">${esc(p.category || "")}</span>${r.demo ? ' <span class="text-[10px] text-accent-800 border border-accent-300 px-1">데모</span>' : ""}</p>
      <p class="text-[11px] text-foreground-600 mt-0.5">${esc(p.address || "")}${h ? ` · 오늘 ${h.closed ? "휴무" : `${h.open}~${h.close}`}` : ""} · <span class="font-mono">${esc(p.id)}</span></p>
      <p class="text-[10.5px] mt-1 ${r.reservable ? "text-secondary-700" : "text-primary-700"}">${r.reservable ? "유미 파트너 — 앱 안에서 문의·예약 가능" : "유미 파트너가 아니라 앱 안에서 예약할 수 없어요"}</p></div>
      <button type="button" data-lab="${esc(p.id)}" class="${BTN_SM}" ${r.reservable || r.demo ? "" : "disabled"}>이 가게 하나로 테스트</button></li>`;
  }).join("");
  const sess = L ? (() => {
    const c = L.candidates[0], ev = (S.labLog || []).slice(-6);
    return `<div class="mt-5 border border-foreground-900/70 bg-background-50 p-4 md:p-5"><p class="kicker">TEST SESSION · ${esc(L.id)}</p>
      <p class="text-[13px] mt-1.5"><strong class="font-heading text-[16px]">${esc(c.place.name)}</strong> · ${L.constraints.party}명 · ${fmtWhen(L.constraints.when)} · ${L.nowMode ? "지금 자리 문의" : "예약 요청으로 확인"} · 상태 <strong>${esc(L.state)}</strong> ${statusBadge(c)}</p>
      ${L.reservation ? `<p class="mt-2 text-[12.5px] text-secondary-800"><i class="ri-checkbox-circle-fill mr-1"></i>예약 확정 · ${esc(L.reservation.reservation_id || "")}</p>` : ""}
      <div class="flex flex-wrap items-center gap-2.5 mt-3">
        <button type="button" id="lab-ask" class="${BTN_SM}" ${["idle", "exhausted"].includes(L.state) ? "" : "disabled"}>${L.nowMode ? "1) 사장님께 지금 자리 묻기" : "1) 예약 요청 준비"}</button>
        <input id="lab-phone" class="field max-w-[170px]" inputmode="tel" placeholder="010-0000-0000">
        <button type="button" id="lab-reserve" class="${BTN_SM}" ${L.state === "await_approval" ? "" : "disabled"}>2) 예약 요청 (다음 가게로 안 넘어감)</button></div>
      <ol class="mt-3 text-[11px] text-foreground-700 space-y-1">${ev.map((e) => `<li><span class="font-mono text-foreground-500 mr-2">${esc(e.t)}</span>${esc(e.msg)}</li>`).join("")}</ol></div>`;
  })() : "";
  $("#lab").innerHTML = head("DEV — 실매장 테스트", "가게 하나만 골라 끝까지 확인", hand("자동으로 다른 가게로<br>넘어가지 않아요")) +
    `<div class="mt-5 text-[11.5px] leading-[1.9] ${live ? "text-primary-700" : "text-foreground-700"}"><i class="${live ? "ri-alarm-warning-line" : "ri-shield-check-line"} mr-1"></i>${esc(modeLine)}</div>
    <form id="lab-form" class="flex flex-wrap items-end gap-2.5 mt-4 text-[11px] text-foreground-600">
      <label>가게 이름 (영문 가능)<input id="lab-q" class="field mt-1 min-w-[240px]" value="${esc(S.labQ || "Hide Me Please Euljiro")}"></label>
      <label>인원<input id="lab-party" type="number" min="1" max="50" value="${S.labParty || 2}" class="field mt-1 w-[80px]"></label>
      <label>방문 시간 (영업시간 안으로)<input id="lab-when" type="datetime-local" value="${S.labWhen || defaultLabWhen()}" class="field mt-1"></label>
      <button class="${BTN_SM}"><i class="ri-search-line"></i>검색 (읽기 전용)</button></form>
    ${live ? '<label class="mt-3 text-[11.5px] text-primary-700 flex items-center gap-1.5"><input type="checkbox" id="lab-live-ok"> 이 가게 사장님께 실제로 보내는 것에 동의해요</label>' : ""}
    <ul class="mt-3">${results}</ul>${sess}`;
  $("#lab-form").onsubmit = async (e) => {
    e.preventDefault(); S.labQ = $("#lab-q").value; S.labParty = $("#lab-party").value; S.labWhen = $("#lab-when").value;
    try { const r = await api(`/api/lab/lookup?q=${encodeURIComponent(S.labQ)}`); S.labResults = r.results; if (!r.results.length) toast("찾은 가게가 없어요"); renderLab(); } catch (err) { fail(err); }
  };
  $$("#lab [data-lab]").forEach((b) => (b.onclick = async () => {
    S.labParty = $("#lab-party").value; S.labWhen = $("#lab-when").value;
    try {
      S.lab = await api("/api/lab/session", { place_id: b.dataset.lab, party: Number(S.labParty), when: `${S.labWhen}:00+09:00` });
      S.labLog = []; if (S.labEs) S.labEs.close();
      S.labEs = new EventSource(`/api/sessions/${S.lab.id}/events`);
      S.labEs.addEventListener("log", (m) => { const { ev, session } = JSON.parse(m.data); S.lab = session; S.labLog.push(ev); S.log.push(ev); renderLog(); renderLab(); });
      renderLab();
    } catch (err) { fail(err); }
  }));
  const okLive = () => !live || $("#lab-live-ok")?.checked;
  if ($("#lab-ask")) $("#lab-ask").onclick = () => { if (!okLive()) return toast("동의 체크가 필요해요"); api(`/api/sessions/${L.id}/ask`, {}).catch(fail); };
  if ($("#lab-reserve")) $("#lab-reserve").onclick = () => {
    const phone = $("#lab-phone").value.trim();
    if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phone)) return toast("연락처 형식을 확인해 주세요");
    if (!okLive()) return toast("동의 체크가 필요해요");
    api(`/api/sessions/${L.id}/approve`, { place_id: L.candidates[0].place.id, phone, auto_fallback: false }).catch(fail);
  };
}

init();
