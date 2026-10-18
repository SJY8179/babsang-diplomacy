const $ = (s) => document.querySelector(s);
const STATUS_KO = {
  idle: "문의 전", asking: "사장님 확인 중", available: "가능", limited: "조금 남음", unavailable: "불가",
  soon: "곧 자리 남", not_offered: "문의 미지원", no_response: "답 없음", closed_now: "영업 시간 아님", error: "오류",
};
const POS = new Set(["available", "limited"]);
const ATTR_KO = { private_room: "룸", parking: "주차", group_friendly: "단체석", corkage_free: "콜키지 프리" };
const SAMPLE = `김대리: 이번 금요일 회식 장소 막내가 좀 알아봐줘
팀장님: 저녁 7시 을지로 쪽으로 하자. 12명
박과장: 1인 3만원 넘지 않게요
김대리: 룸 꼭 있어야 해요 시끄러우면 얘기 못 함
박과장: 팀장님 매운 거 못 드시는 거 알지?`;

const SAMPLE_NOW = `이대리: 1차 끝났는데 을지로에서 지금 바로 8명 들어갈 데 있나
최사원: 룸 있으면 좋겠어요
이대리: 1인 2만원 정도로`;

let session = null;
let es = null;
let selectedPlace = null;
let stars = 4;

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// ---------- 초기화 ----------
async function init() {
  // 버튼부터 연결한다. 데이터 로딩이 실패해도 화면은 눌린다.
  document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === t));
    document.querySelectorAll(".tab-body").forEach((b) => b.classList.toggle("hidden", b.dataset.body !== t.dataset.tab));
  }));
  $("#sample").onclick = () => ($("#chat").value = SAMPLE);
  $("#sample-now").onclick = () => ($("#chat").value = SAMPLE_NOW);
  $("#plan").onclick = plan;
  $("#ask").onclick = () => run($("#ask"), () => api(`/api/sessions/${session.id}/ask`, {}));
  $("#reserve").onclick = reserve;
  $("#copy").onclick = () => navigator.clipboard.writeText($("#notice").value).then(() => flash($("#copy"), "복사됨"));
  $("#headcount").onclick = () => run($("#headcount"), () =>
    api(`/api/sessions/${session.id}/headcount`, { guests: Number($("#new-guests").value) }));
  $("#after").onclick = () => run($("#after"), () => api(`/api/sessions/${session.id}/afterparty`, {}));
  $("#save-fb").onclick = saveFeedback;
  $("#group").onchange = loadMemory;
  $("#dept-form").onsubmit = addDept;
  $("#go-plan").onclick = () => planMeeting({});
  $("#replan").onclick = () => planMeeting(session?.meeting?.relax || {});
  $("#go-step1").onclick = () => $("#step1").scrollIntoView({ behavior: "smooth" });
  $("#add-person").onsubmit = addPerson;
  $("#m-save").onclick = saveMeeting;
  $("#blog-make").onclick = makeBlog;
  $("#blog-copy").onclick = () => navigator.clipboard.writeText($("#blog").value).then(() => flash($("#blog-copy"), "복사됨"));
  $("#log-toggle").onclick = toggleLog;
  $("#d-close").onclick = () => $("#detail").close();
  $("#d-share").onclick = shareLocation;
  renderStars();
  const d = new Date(); d.setHours(19, 0, 0, 0);
  $("#f-when").value = new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

  try {
    const cfg = await api("/api/config");
    $("#mode").textContent = cfg.label || cfg.mode;
    cfg.areas.forEach((a) => { $("#f-area").append(new Option(a, a)); $("#m-area").append(new Option(a, a)); });
    await loadGroups();
  } catch (e) {
    alertLog(`설정을 불러오지 못했어요: ${e.message}`);
  }
  await loadMemory();
}

function groupId() { return $("#group").value || "demo"; }

async function loadGroups(selectId) {
  const groups = await api("/api/groups");
  await Promise.all(groups.map(async (g) => { try { g.meeting = await api(`/api/groups/${g.id}/meeting`); } catch { g.meeting = null; } }));
  if (!groups.length) groups.push({ id: "demo", name: "마케팅팀 정기 회식" });
  $("#group").innerHTML = "";
  groups.forEach((g) => $("#group").append(new Option(g.name, g.id)));
  if (selectId) $("#group").value = selectId;
  renderDeptTabs(groups);
}

function renderDeptTabs(groups) {
  const box = $("#dept-tabs"); box.innerHTML = "";
  groups.forEach((g, i) => {
    const b = el("button", `dept${g.id === groupId() ? " on" : ""}`);
    b.append(el("span", "no", String(i + 1).padStart(2, "0")), el("span", "nm", g.name));
    if (g.meeting) b.append(el("span", "sub", [g.meeting.title, g.meeting.lead, g.meeting.team_size && `${g.meeting.team_size}명`].filter(Boolean).join(" · ")));
    b.onclick = async () => { $("#group").value = g.id; renderDeptTabs(groups); await loadMemory(); };
    box.append(b);
  });
}

async function addDept(e) {
  e.preventDefault();
  const name = $("#dept-name").value.trim();
  if (!name) return;
  try {
    const g = await api("/api/groups", { name });
    $("#dept-name").value = "";
    await loadGroups(g.id);
    await loadMemory();
  } catch (err) { alertLog(err.message); }
}

async function loadMemory() {
  loadMeeting();
  $("#memory").innerHTML = ""; $("#mem-stats").innerHTML = ""; $("#mem-visits").innerHTML = "";
  try {
    const { profile, visits } = await api(`/api/groups/${groupId()}/memory`);
    $("#memory").append(el("b", "", "모임 기억 "), document.createTextNode(profile.summary));
    if (!visits.length) return;
    const spent = visits.filter((v) => v.per_person).map((v) => v.per_person);
    const avg = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
    const stat = (label, value) => { const d = el("div", "stat"); d.append(el("span", "v", value), el("span", "l", label)); $("#mem-stats").append(d); };
    stat(`최근 ${visits.length}회 1인 평균 지출`, spent.length ? `${Math.round(avg(spent) / 1000).toLocaleString()},000원` : "기록 없음");
    stat("평균 만족도", `${avg(visits.map((v) => v.satisfaction)).toFixed(1)} / 5`);
    stat("재방문 희망 장소", `${visits.filter((v) => v.revisit).length}곳`);
    const top = visits.filter((v) => v.satisfaction >= 4.4 && v.per_person).map((v) => v.per_person);
    if (top.length) stat("만족도 높은 가격대", `${(Math.min(...top) / 10000).toFixed(1)}~${(Math.max(...top) / 10000).toFixed(1)}만원`);
    visits.slice(0, 4).forEach((v) => {
      const li = el("li");
      li.append(el("span", "nm", v.place_name),
        el("span", `tag ${v.revisit ? "yes" : "no"}`, v.revisit ? "재방문 희망" : v.satisfaction >= 3 ? "보류" : "다시 안 감"),
        el("span", "meta", [v.visited_at.slice(5).replace("-", "/"), v.per_person && `1인 ${v.per_person.toLocaleString()}원`, `만족 ${v.satisfaction}`].filter(Boolean).join(" · ")));
      $("#mem-visits").append(li);
    });
  } catch (e) {
    $("#memory").append(el("b", "", "모임 기억 "), document.createTextNode(`불러오지 못했어요 (${e.message})`));
  }
}

function toggleLog() {
  const p = $("#log-panel"); const closed = p.classList.toggle("closed");
  $("#log-toggle").setAttribute("aria-expanded", String(!closed));
  $("#log-toggle .caret").textContent = closed ? "펼치기" : "접기";
}

let detailPlace = null;
async function openDetail(placeId) {
  const dlg = $("#detail");
  $("#d-name").textContent = "불러오는 중…"; $("#d-meta").textContent = ""; $("#d-summary").textContent = "";
  $("#d-photos").innerHTML = ""; $("#d-menu").innerHTML = ""; $("#d-addr").textContent = "";
  dlg.showModal();
  try {
    const d = await api(`/api/places/${encodeURIComponent(placeId)}`);
    detailPlace = d;
    $("#d-name").textContent = d.name;
    $("#d-meta").textContent = [d.category, d.price && `메뉴 평균 ${(d.price / 10000).toFixed(1)}만 원`,
      d.station && `${d.station}역${d.walk_min ? ` 도보 ${d.walk_min}분` : ""}`, d.phone].filter(Boolean).join(" · ");
    $("#d-summary").textContent = d.summary || "";
    if (d.photos.length) d.photos.forEach((u) => { const img = el("img"); img.src = u; img.alt = `${d.name} 사진`; img.loading = "lazy"; $("#d-photos").append(img); });
    else $("#d-photos").append(el("p", "muted", "등록된 사진이 없어요."));
    if (d.menu.length) d.menu.forEach((m) => {
      const li = el("li", m.recommend ? "rec" : "");
      li.append(el("span", "nm", m.name + (m.recommend ? " · 추천" : "")), el("span", "pr", m.price ? `${m.price.toLocaleString()}원` : "가격 확인 필요"));
      $("#d-menu").append(li);
    });
    else $("#d-menu").append(el("li", "muted", "메뉴 정보가 없어요."));
    $("#d-addr").textContent = d.address || (d.station ? `${d.station}역 근처` : "주소 확인 필요");
    const q = encodeURIComponent(d.name);
    $("#d-kakao").href = d.lat ? `https://map.kakao.com/link/map/${q},${d.lat},${d.lng}` : `https://map.kakao.com/?q=${q}`;
    $("#d-naver").href = `https://map.naver.com/p/search/${encodeURIComponent(`${d.name} ${d.address || ""}`.trim())}`;
    $("#d-yumi").classList.toggle("hidden", !d.placeUrl);
    if (d.placeUrl) $("#d-yumi").href = d.placeUrl;
  } catch (e) {
    $("#d-name").textContent = "가게 정보를 불러오지 못했어요";
    $("#d-meta").textContent = e.message;
  }
}

async function shareLocation() {
  const d = detailPlace; if (!d) return;
  const map = $("#d-kakao").href;
  const text = `${d.name}\n${d.address || ""}\n${map}`.trim();
  try {
    if (navigator.share) await navigator.share({ title: d.name, text, url: map });
    else { await navigator.clipboard.writeText(text); flash($("#d-share"), "복사됨"); }
  } catch { /* 사용자가 공유 창을 닫음 */ }
}

async function run(btn, fn) {
  btn.disabled = true;
  try { await fn(); } catch (e) { alertLog(e.message); }
  setTimeout(() => (btn.disabled = false), 1500);
}

function flash(btn, text) {
  const old = btn.textContent; btn.textContent = text;
  setTimeout(() => (btn.textContent = old), 1200);
}

function alertLog(msg) {
  addLog({ t: new Date().toTimeString().slice(0, 8), agent: "app", type: "error", msg });
}

// ---------- 흐름 ----------
async function plan() {
  const useText = !$(".tab-body[data-body=text]").classList.contains("hidden");
  const body = { group_id: groupId() };
  if (useText) {
    if (!$("#chat").value.trim()) return alertLog("대화를 붙여 넣어 주세요.");
    body.text = $("#chat").value;
  } else {
    const when = $("#f-when").value ? `${$("#f-when").value}:00+09:00` : null;
    body.form = {
      area: $("#f-area").value, party: Number($("#f-party").value), when,
      max_price: $("#f-price").value ? Math.round(Number($("#f-price").value) * 10000) : null,
      context: $("#f-biz").checked ? "business_meeting" : "group_dining",
      must: $("#f-room").checked ? ["private_room"] : [],
      nice: [$("#f-parking").checked && "parking", Number($("#f-party").value) >= 8 && "group_friendly"].filter(Boolean),
      avoid: $("#f-avoid").value ? $("#f-avoid").value.split(/[ ,]+/).filter(Boolean) : [],
    };
  }
  $("#log").innerHTML = "";
  selectedPlace = null;
  await run($("#plan"), async () => {
    session = await api("/api/plan", body);
    connect(session.id);
    render();
  });
}

function connect(id) {
  if (es) es.close();
  es = new EventSource(`/api/sessions/${id}/events`);
  es.addEventListener("log", (m) => {
    const { ev, session: s } = JSON.parse(m.data);
    session = s;
    addLog(ev);
    if (ev.type === "approval" && ev.data.placeId) selectedPlace = ev.data.placeId;
    render();
  });
}

async function reserve() {
  if (!selectedPlace) return alertLog("예약할 가게를 골라 주세요.");
  const phone = $("#phone").value.trim();
  if (!/^\d{2,3}-?\d{3,4}-?\d{4}$/.test(phone)) return alertLog("연락처 형식을 확인해 주세요.");
  await run($("#reserve"), () => api(`/api/sessions/${session.id}/approve`, {
    place_id: selectedPlace, phone, auto_fallback: $("#fallback").checked,
  }));
}

async function saveFeedback() {
  const r = session.reservation;
  const c = session.candidates.find((x) => x.place.id === r.place_id);
  await run($("#save-fb"), async () => {
    await api("/api/feedback", {
      group_id: groupId(), place_id: r.place_id, place_name: r.place_name, attrs: c ? c.place.attrs : [],
      satisfaction: stars, revisit: $("#revisit").checked, per_person: Number($("#spent").value) || null,
    });
    await loadMemory();
    flash($("#save-fb"), "저장됨 · 다음 추천에 반영돼요");
  });
}

// ---------- 렌더 ----------
function render() {
  if (!session) return;
  renderConditions();
  renderStep2();
  $("#cands-panel").classList.toggle("hidden", !session.candidates.length);
  $("#ask").disabled = !["idle", "exhausted"].includes(session.state);
  $("#ask").textContent = session.state === "asking" ? "사장님 답 기다리는 중"
    : session.nowMode ? "사장님께 지금 자리 묻기 (3곳)" : "예약 요청 준비 (1순위부터)";
  renderCards($("#cands"), session.candidates, true);

  const canApprove = ["await_approval"].includes(session.state);
  $("#approve").classList.toggle("hidden", !canApprove);
  $("#fallback").parentElement.lastChild.textContent = session.nowMode
    ? " 거절되면 '가능'이라고 답한 다음 가게로 바로 넘어가기" : " 거절되면 다음 순위 가게로 바로 넘어가기";
  if (canApprove) {
    const c = session.candidates.find((x) => x.place.id === selectedPlace)
      || session.candidates.find((x) => bookable(x));
    if (c) selectedPlace = c.place.id;
    $("#approve-target").textContent = c ? `${c.place.name} · ${session.constraints.party}명 · ${fmtWhen(session.constraints.when)}` : "";
  }
  renderConfirmed();
}

function bookable(c) {
  return !c.tried_reservation && (session.nowMode ? POS.has(c.status) : true);
}

function renderConditions() {
  const c = session.constraints;
  const box = $("#conditions");
  box.classList.remove("hidden");
  box.innerHTML = "";
  const chip = (t, cls = "") => box.append(el("span", `c ${cls}`, t));
  chip(c.area); chip(`${c.party}명`); chip(fmtWhen(c.when));
  if (c.max_price) chip(`1인 ${c.max_price / 10000}만 원 이하`);
  c.must.forEach((a) => chip(`${ATTR_KO[a] || a} 필수`, "must"));
  c.nice.forEach((a) => chip(`${ATTR_KO[a] || a} 되면 좋음`));
  c.avoid.forEach((a) => chip(`${a} 제외`));
  c.conflicts.forEach((a) => chip(a, "warn"));
}

function renderCards(list, cands, selectable) {
  list.innerHTML = "";
  cands.forEach((c) => {
    const li = el("li", "card");
    if (POS.has(c.status)) li.classList.add("pos");
    if (["unavailable", "not_offered", "no_response", "closed_now", "error"].includes(c.status)) li.classList.add("neg");
    const left = el("div");
    left.append(el("div", "name", c.place.name));
    const meta = [c.place.category, c.place.price && `메뉴 평균 ${(c.place.price / 10000).toFixed(1)}만 원`, c.distance_m != null && `${c.distance_m}m`]
      .filter(Boolean).join(" · ");
    left.append(el("div", "meta", meta));
    const side = el("div", "side");
    const st = el("span", `status ${c.status}${POS.has(c.status) ? " pos" : ""}`,
      STATUS_KO[c.status] + (c.status_at && c.status !== "asking" ? ` · ${c.status_at}` : ""));
    side.append(st);
    if (selectable && bookable(c) && session.state === "await_approval") {
      const b = el("button", "ghost", c.place.id === selectedPlace ? "선택됨" : "이곳으로 예약");
      b.onclick = () => { selectedPlace = c.place.id; render(); };
      side.append(b);
    }
    if (c.total != null) {
      left.prepend(el("div", "rank", `${cands.indexOf(c) + 1}${cands.indexOf(c) === 0 ? " · 1순위 추천" : ""}`));
      side.prepend(el("div", "total", `종합 ${c.total}점`));
    }
    const more = el("button", "link", "사진 · 메뉴 · 위치");
    more.onclick = () => openDetail(c.place.id);
    side.append(more);
    const badges = el("div", "badges");
    c.evidence.forEach((e) => {
      const b = el("span", `badge ${e.kind}`, e.label);
      if (e.kind === "data" && e.source && e.source !== e.label) b.title = e.source;
      badges.append(b);
    });
    li.append(left, side, badges);
    if (c.checks && Object.keys(c.checks).length) {
      const ck = el("div", "checks-row");
      Object.entries(c.checks).forEach(([k, v]) => ck.append(el("span", `ck ${v === "충족" ? "ok" : v === "미충족" ? "no" : "q"}`, `${k} ${v}`)));
      li.append(ck);
    }
    if (c.travel && Object.keys(c.travel).length) {
      const tv = el("div", "travel");
      tv.append(el("span", "tv-title", `참석자별 이동 (${c.travel_source || ""})`));
      Object.entries(c.travel).forEach(([n, m]) => {
        const row = el("div", `tv-row${m > 25 ? " far" : ""}`);
        const bar = el("span", "bar"); bar.style.width = `${Math.min(100, m / 45 * 100)}%`;
        row.append(el("span", "nm", n), el("span", "track"), el("span", "mn", `${m}분`));
        row.querySelector(".track").append(bar);
        tv.append(row);
      });
      li.append(tv);
    }
    if (c.reason) li.append(el("p", "why", `왜 여기? ${c.reason}`));
    list.append(li);
  });
}

async function renderConfirmed() {
  const r = session.reservation;
  $("#confirmed").classList.toggle("hidden", !r);
  if (!r) return;
  $("#confirmed-title").textContent = `${r.place_name} 예약 확정`;
  $("#confirmed-meta").textContent = `${fmtWhen(r.when)} · ${r.guests}명`;
  if (!$("#new-guests").value) $("#new-guests").value = r.guests + 2;
  if (!$("#notice").dataset.for || $("#notice").dataset.for !== r.reservation_id + r.guests) {
    const { text } = await api(`/api/sessions/${session.id}/notice`);
    $("#notice").value = text;
    $("#notice").dataset.for = r.reservation_id + r.guests;
  }
  renderCards($("#after-cands"), session.after, false);
}

function renderStars() {
  const box = $("#stars"); box.innerHTML = "";
  for (let i = 1; i <= 5; i++) {
    const b = el("button", i <= stars ? "on" : "", String(i));
    b.onclick = () => { stars = i; renderStars(); };
    box.append(b);
  }
}

function addLog(ev) {
  const li = el("li", ev.type);
  const KO = { coordinator: "조율", scout: "탐색", negotiator: "교섭", memory: "기억", afterparty: "2차", travel: "이동", app: "앱" };
  li.append(el("span", "t", ev.t), el("span", `a ${ev.agent}`, KO[ev.agent] || ev.agent), el("span", "m", ev.msg));
  $("#log").append(li);
  $("#log").scrollTop = $("#log").scrollHeight;
}

function fmtWhen(iso) {
  if (!iso) return "시간 미정";
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}(${"일월화수목금토"[d.getDay()]}) ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}


// ---------- 회식(참석자) 모드 ----------
let meeting = null;
async function loadMeeting() {
  try { meeting = await api(`/api/groups/${groupId()}/meeting`); } catch { meeting = null; }
  renderMeeting();
}

function renderMeeting() {
  const box = $("#people"); box.innerHTML = "";
  const stats = $("#hero-stats"); stats.innerHTML = "";
  if (!meeting) { $("#s1-title").textContent = "참석자별 조건"; $("#h-title").textContent = "회식"; return; }
  const ps = meeting.participants;
  $("#h-title").textContent = meeting.title;
  $("#s1-title").textContent = `${meeting.title} · 참석자별 조건`;
  $("#s1-sub").textContent = `공유 링크로 로그인 없이 각자 조건을 입력해요. ${ps.length}명 중 ${meeting.done}명 완료.`
    + (meeting.team_size ? ` 팀 전체 ${meeting.team_size}명 중 ${ps.length}명이 참석해요.` : "");
  $("#m-title").value = meeting.title;
  if (meeting.when_at) $("#m-when").value = meeting.when_at.slice(0, 16);
  $("#m-area").value = meeting.area || "";
  const stat = (l, v, s2) => { const d = el("div", "hstat"); d.append(el("span", "l", l), el("span", "v", v), el("span", "s", s2 || "")); stats.append(d); };
  stat("참석", `${ps.length}명`, `${meeting.done}명 입력 완료`);
  stat("일시", meeting.when_at ? fmtWhen(meeting.when_at) : "미정");
  stat("지역", meeting.area || "자동", meeting.area ? `${meeting.area} 일대` : "출발지 중심");
  stat("기억", `${meeting.visits ?? 0}회`, "지난 회식 기록");
  ps.forEach((p, i) => {
    const li = el("li", `person${p.done ? "" : " wait"}`);
    const head = el("div", "p-head");
    head.append(el("span", "av", p.name.slice(0, 1)), el("b", "", p.name), el("span", "muted", p.role || ""),
      el("span", `tag ${p.done ? "yes" : "no"}`, p.done ? "입력 완료" : "대기 중"));
    const body = el("div", "p-body");
    [p.origin && `${p.origin}역`.replace("역역", "역"), p.budget && `${p.budget.toLocaleString()}원`, p.diet || (p.done ? "식단 제한 없음" : ""),
      p.allergy && p.allergy !== "없음" && `${p.allergy} 알레르기`, p.food, p.mood].filter(Boolean).forEach((t) => body.append(el("span", "pill", t)));
    const act = el("div", "p-act");
    const copy = el("button", "link", "공유 링크 복사");
    copy.onclick = () => navigator.clipboard.writeText(p.link).then(() => flash(copy, "복사됨"));
    const open = el("a", "link", "직접 입력"); open.href = `/p/${p.token}`; open.target = "_blank";
    act.append(copy, open);
    li.append(head, body, act);
    box.append(li);
  });
}

async function addPerson(e) {
  e.preventDefault();
  if (!meeting) return alertLog("먼저 회식을 만들어 주세요.");
  const name = $("#ap-name").value.trim(); if (!name) return;
  try { await api(`/api/meetings/${meeting.id}/participants`, { name, role: $("#ap-role").value.trim() || null });
    $("#ap-name").value = ""; $("#ap-role").value = ""; await loadMeeting(); } catch (err) { alertLog(err.message); }
}

async function saveMeeting() {
  const body = { group_id: groupId(), title: $("#m-title").value.trim() || "회식",
    when_at: $("#m-when").value ? `${$("#m-when").value}:00+09:00` : null, area: $("#m-area").value || null };
  try {
    if (meeting) { const r = await fetch(`/api/meetings/${meeting.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); meeting = await r.json(); }
    else meeting = await api("/api/meetings", body);
    renderMeeting(); flash($("#m-save"), "저장됨");
  } catch (err) { alertLog(err.message); }
}

async function planMeeting(relax) {
  if (!meeting) return alertLog("회식과 참석자를 먼저 만들어 주세요.");
  $("#log").innerHTML = ""; selectedPlace = null;
  await run($("#go-plan"), async () => {
    session = await api(`/api/meetings/${meeting.id}/plan`, relax);
    connect(session.id); render();
    $("#step2").scrollIntoView({ behavior: "smooth" });
  });
}

function renderStep2() {
  const m = session.meeting;
  $("#step2").classList.toggle("hidden", !m);
  $("#conditions").classList.toggle("hidden", !!m);
  $("#score-rule").textContent = m ? `점수 기준 · 필수 50% · 이동 균형 30% · 선호 20%. 25분이 넘는 이동은 테라코타로 표시했어요. 이동 시간: ${m.travel_source || "출발지 미입력"}` : "";
  $("#cands-title").textContent = m ? `${m.title} 추천 식당` : "추천 식당";
  if (!m) return;
  const fill = (id, xs) => { const b = $(id); b.innerHTML = ""; xs.forEach((t) => b.append(el("li", "", t))); };
  fill("#c-must", m.must); fill("#c-nice", m.nice);
  const cb = $("#c-conf"); cb.innerHTML = "";
  if (!m.conflicts.length) cb.append(el("li", "muted", "충돌 없음"));
  m.conflicts.forEach((cf) => {
    const li = el("li"); li.append(el("b", "", cf.title), el("p", "", cf.text));
    const b = el("button", "ghost", "완화해보기"); b.title = cf.label;
    b.onclick = () => planMeeting({ ...(m.relax || {}), ...cf.relax });
    li.append(b); cb.append(li);
  });
  $("#c-count").textContent = `현재 후보 ${m.count}곳 · ${m.area} 기준 · 변경은 모임이 결정해요`;
}

async function makeBlog() {
  await run($("#blog-make"), async () => {
    const { text, how } = await api(`/api/groups/${groupId()}/blog`, {});
    $("#blog").value = text; flash($("#blog-make"), how === "llm" ? "AI로 다듬음" : "기록으로 작성");
  });
}

init();
