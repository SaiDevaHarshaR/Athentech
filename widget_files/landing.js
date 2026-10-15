/* Sahasra — cinematic landing: real-time 3D DNA helix (three.js, bloom), scroll scenes, chat dock.
   Loaded only on the standalone page by premium.js (never inside the embedded widget iframe). */
import * as THREE from 'three';
import { EffectComposer } from './vendor/three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from './vendor/three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from './vendor/three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from './vendor/three/examples/jsm/postprocessing/OutputPass.js';

const root = document.documentElement;
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const isDark = () => root.getAttribute('data-pz-theme') !== 'light';
const $ = (s, r) => (r || document).querySelector(s), $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
function h(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
const clamp = (v, a, b) => Math.min(b, Math.max(a, v)), lerp = (a, b, t) => a + (b - a) * t, sm = t => t * t * (3 - 2 * t);

/* ================= DOM ================= */
const SC = [
  { t: 'Ask in plain English.', p: 'Type the question the way you would ask a colleague. Sahasra turns it into a query, runs it on your database and answers with the numbers.' },
  { t: 'Only your records.', p: 'An activation code links the assistant to your hospital’s own database. Queries are read-only, and it will not answer your data questions from general knowledge.' },
  { t: 'Every answer is checked.', p: 'Each answer gets a confidence score computed from checks on the data it used. A low score shows a warning, and the reasons are one tap away.' },
  { t: 'Your AI, your key.', p: 'Connect your own AI provider key from more than twenty providers. Your usage stays on your account, and nothing falls back to shared AI unless you allow it.' }
];
const ICON = {
  key: '<svg viewBox="0 0 24 24"><circle cx="8" cy="15" r="4"/><path d="M10.8 12.2 20 3m-3 3 3 3m-6 0 2 2"/></svg>',
  db: '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></svg>',
  ans: '<svg viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/></svg>',
  chat: '<svg viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4z"/></svg>'
};
const MARQ = ['Collections', 'Doctor referrals', 'Report turnaround', 'Pending reports', 'Branch comparison', 'Patient reports', 'Excel exports', 'Corporate billing', 'Department revenue', 'Refunds and cancellations'];
const PROV = ['OpenAI', 'Google Gemini', 'Anthropic Claude', 'Groq', 'Mistral AI', 'Cohere', 'OpenRouter', 'Together AI', 'DeepSeek', 'xAI Grok', 'Cerebras', 'NVIDIA NIM', 'Qwen', 'Hugging Face', 'Local Ollama'];

const L = h('div', '', ''); L.id = 'pzl';
L.innerHTML =
  '<canvas id="pzl-canvas" aria-hidden="true"></canvas><div class="pzl-veil" aria-hidden="true"></div><div class="pzl-vignette" aria-hidden="true"></div>' +
  '<header class="pzl-nav pzl-z"><a class="pzl-brand" href="#top"><img src="Favicon.ico" alt="">Sahasra AI</a>' +
  '<nav class="pzl-links" aria-label="Sections"><a href="#how" data-scene="0">How it works</a><a href="#trust" data-scene="1">Your data</a><a href="#keys" data-scene="3">Your AI</a></nav>' +
  '<div class="pzl-nav-r"><button class="pzl-btn pzl-btn-sm" data-open-chat type="button">Open assistant</button></div></header>' +
  '<main class="pzl-z"><section class="pzl-hero" id="top"><div><h1 aria-label="Ask your hospital. Know the answer."></h1>' +
  '<p class="pzl-sub">Sahasra AI answers from your own records, and shows how it got there.</p>' +
  '<div class="pzl-cta"><button class="pzl-btn" data-open-chat type="button">Open the assistant</button><a class="pzl-link" href="#how" data-scene="0">See how it works</a></div></div>' +
  '<div class="pzl-ticker" aria-hidden="true"><span class="pzl-ticker-q"></span></div><div class="pzl-scroll" aria-hidden="true">Scroll</div></section>' +
  '<section class="pzl-marquee" aria-hidden="true"><div class="pzl-marquee-track">' + MARQ.concat(MARQ).map(x => '<span>' + x + '</span>').join('') + '</div></section>' +
  '<section class="pzl-scenes" id="how"><div class="pzl-stick"><div class="pzl-rail" aria-hidden="true"><i></i></div><div class="pzl-copy">' +
  SC.map((s, i) => '<div class="pzl-sc" data-i="' + i + '"' + (i === 1 ? ' id="trust"' : '') + (i === 3 ? ' id="keys"' : '') + '><h2>' + s.t + '</h2><p>' + s.p + '</p></div>').join('') + '</div>' +
  '<div class="pzl-stage">' +
  /* 1 */ '<div class="pzl-mock" data-i="0"><div class="pzl-card"><div class="m-q"></div><div class="m-a"><div class="m-stats"><div class="m-stat"><b>₹4,82,310</b><small>This month, to date</small></div><div class="m-stat"><b>₹4,29,150</b><small>Same days last month</small></div></div><div class="m-bar"><i></i></div></div><p class="pzl-note">Sample data</p></div></div>' +
  /* 2 */ '<div class="pzl-mock" data-i="1"><div class="pzl-card"><div class="m-flow"><div class="m-node"><span class="ic">' + ICON.key + '</span><span>Activation code<small>Identifies your hospital</small></span></div><div class="m-wire"></div>' +
         '<div class="m-node"><span class="ic">' + ICON.db + '</span><span>Your database only<small>Read-only queries</small></span></div><div class="m-wire"></div><div class="m-node"><span class="ic">' + ICON.ans + '</span><span>Answer from your data<small>Never from guesswork</small></span></div></div><div class="m-deny">General knowledge</div></div></div>' +
  /* 3 */ '<div class="pzl-mock" data-i="2"><div class="pzl-card"><div class="m-conf"><div class="m-ring"><svg viewBox="0 0 120 120"><defs><linearGradient id="pzl-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="var(--w-accent)"/><stop offset="1" stop-color="#2de1c2"/></linearGradient></defs><circle class="bg" cx="60" cy="60" r="54"/><circle class="fg" cx="60" cy="60" r="54"/></svg><b>0</b></div>' +
         '<div class="m-checks"><div>Figures match the query results</div><div>Branch and period confirmed</div><div>Nothing truncated</div></div></div><div class="m-warn">⚠️ When a score is low you see this marker. Tap it to see why.</div></div></div>' +
  /* 4 */ '<div class="pzl-mock" data-i="3"><div class="pzl-card"><div class="m-keys">' + PROV.map((p, i) => '<span style="--d:' + i + '">' + p + '</span>').join('') + '</div><div class="m-field"><span>sk-••••••••••••</span><em>✓ Verified</em></div><p class="pzl-note">Your key is stored encrypted and used only for your hospital.</p></div></div>' +
  '</div></div></section>' +
  '<section class="pzl-end"><div><h2>Ready when<br>you are.</h2><button class="pzl-btn" data-open-chat type="button">Open the assistant</button></div></section></main>' +
  '<footer class="pzl-foot pzl-z"><span>Sahasra AI Assistant</span><span>Powered by <a href="https://athentech.in" target="_blank" rel="noopener">AthenTech</a></span></footer>' +
  '<button class="pzl-fab" data-open-chat type="button" aria-label="Open the assistant"><span class="dot">' + ICON.chat + '</span><span class="lbl">Ask Sahasra</span></button>';
document.body.insertBefore(L, document.body.firstChild);
root.classList.add('pz-land');

/* hero headline letters */
(function () {
  const hh = $('.pzl-hero h1'); let i = 0;
  ['Ask your hospital.', 'Know the answer.'].forEach((line, li) => {
    line.split(' ').forEach((word, wi, arr) => {
      const w = h('span', 'w'); word.split('').forEach(ch => { const s = h('span', 'l'); s.style.setProperty('--i', i++); s.textContent = ch; w.appendChild(s); });
      hh.appendChild(w); if (wi < arr.length - 1) { hh.appendChild(document.createTextNode(' ')); i++; }
    });
    if (li === 0) hh.appendChild(document.createElement('br'));
  });
})();
const tg = window.__pzToggle; if (tg) { tg.classList.add('pz-toggle'); $('.pzl-nav-r', L).insertBefore(tg, $('.pzl-nav-r', L).firstChild); }

/* ================= interaction ================= */
const nav = $('.pzl-nav', L), scenes = $('.pzl-scenes', L), copies = $$('.pzl-sc', L), mocks = $$('.pzl-mock', L), rail = $('.pzl-rail', L);
function openChat(open) {
  const want = open == null ? !root.classList.contains('pz-chat-open') : open;
  root.classList.toggle('pz-chat-open', want);
  const fab = $('.pzl-fab', L); $('.lbl', fab).textContent = want ? 'Close' : 'Ask Sahasra';
  fab.setAttribute('aria-label', want ? 'Close the assistant' : 'Open the assistant');
  if (want) setTimeout(() => { const m = document.getElementById('msg'); if (m) m.focus({ preventScroll: true }); }, 500);
}
L.addEventListener('click', e => {
  const o = e.target.closest('[data-open-chat]'); if (o) { e.preventDefault(); openChat(o.classList.contains('pzl-fab') ? null : true); return; }
  const a = e.target.closest('a[href^="#"]'); if (a) {
    e.preventDefault(); const sc = a.getAttribute('data-scene');
    if (sc != null) scrollToScene(+sc); else window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
  }
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && root.classList.contains('pz-chat-open')) openChat(false); });
function sceneSpan() { return scenes.offsetHeight - innerHeight; }
function scrollToScene(i) { const top = scenes.offsetTop + (i + .5) / SC.length * sceneSpan() - 2; window.scrollTo({ top, behavior: reduce ? 'auto' : 'smooth' }); }

/* typed hero ticker */
(function () {
  const el = $('.pzl-ticker-q', L), Q = ['Total collection this month for Kompally branch?', 'Which doctor referred the most patients last month?', 'How many reports are pending today?', 'Compare this week with last week.'];
  if (reduce) { el.textContent = Q[0]; return; }
  let qi = 0, ci = 0, del = false;
  (function tick() {
    const q = Q[qi]; if (!del) { ci++; el.textContent = q.slice(0, ci); if (ci === q.length) { del = true; return setTimeout(tick, 2200); } return setTimeout(tick, 38 + Math.random() * 40); }
    ci -= 2; if (ci <= 0) { ci = 0; del = false; qi = (qi + 1) % Q.length; el.textContent = ''; return setTimeout(tick, 380); } el.textContent = q.slice(0, ci); setTimeout(tick, 16);
  })();
})();

/* scene activation + mock animations */
let activeScene = -1, typeTimer = 0, countTimer = 0;
function activate(i) {
  if (i === activeScene) return; activeScene = i;
  copies.forEach((c, k) => c.classList.toggle('on', k === i)); mocks.forEach((m, k) => m.classList.toggle('on', k === i));
  clearTimeout(typeTimer); clearInterval(countTimer);
  const q = $('.m-q', L), a = $('.m-a', L), ring = $('.m-ring .fg', L), num = $('.m-ring b', L);
  if (i === 0) {
    const txt = 'Total collection this month for Kompally branch?'; q.textContent = ''; a.classList.remove('show'); let n = 0;
    if (reduce) { q.textContent = txt; a.classList.add('show'); } else (function t() { n++; q.textContent = txt.slice(0, n); if (n < txt.length) typeTimer = setTimeout(t, 32); else typeTimer = setTimeout(() => a.classList.add('show'), 350); })();
  }
  if (i === 2) {
    ring.style.strokeDashoffset = 339.3; num.textContent = '0'; requestAnimationFrame(() => requestAnimationFrame(() => { ring.style.strokeDashoffset = (339.3 * (1 - .92)).toFixed(1); }));
    let v = 0; countTimer = setInterval(() => { v += 2; if (v >= 92) { v = 92; clearInterval(countTimer); } num.textContent = v; }, 24);
  }
}

/* ================= 3D scene ================= */
const canvas = $('#pzl-canvas', L);
let renderer;
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' }); } catch (e) { renderer = null; }
const state = { t: 0, typing: false, energy: 0, mx: .5, my: .5, tmx: .5, tmy: .5 };
function readAccent() { const c = new THREE.Color(); try { c.set(getComputedStyle(root).getPropertyValue('--w-accent').trim() || '#6a5cf6'); } catch (e) { c.set('#6a5cf6'); } return c; }
let scene, camera, composer, bloom, group, matA, matB, rungs, nodes, packets, dust, dustMat, accent = readAccent();
const teal = new THREE.Color('#2de1c2');
const TURNS = 3.4, HEIGHT = 12, RAD = 1.35, RUNGS = 46;
function hp(u, phase) { const a = u * TURNS * Math.PI * 2 + phase; return new THREE.Vector3(Math.cos(a) * RAD, (u - .5) * HEIGHT, Math.sin(a) * RAD); }
function paintInstances() {
  const dark = isDark(), k = dark ? 1.25 : .62, c = new THREE.Color();
  for (let r = 0; r < RUNGS; r++) {
    c.copy(accent).lerp(teal, r / (RUNGS - 1)).multiplyScalar(k); rungs.setColorAt(r, c); nodes.setColorAt(r * 2, c); nodes.setColorAt(r * 2 + 1, c);
  }
  rungs.instanceColor.needsUpdate = true; nodes.instanceColor.needsUpdate = true;
}
function applyTheme() {
  if (!renderer) return; const dark = isDark(); accent = readAccent();
  scene.background = new THREE.Color(dark ? 0x03050c : 0xeef1fa); scene.fog = new THREE.FogExp2(dark ? 0x03050c : 0xeef1fa, dark ? .026 : .008); renderer.toneMapping = dark ? THREE.ACESFilmicToneMapping : THREE.NoToneMapping;
  matA.color.copy(accent); matA.emissive.copy(accent); matA.emissiveIntensity = dark ? .6 : 0; matB.emissiveIntensity = dark ? .6 : 0; matA.roughness = matB.roughness = dark ? .26 : .32; matA.metalness = matB.metalness = dark ? .55 : .25;
  if (!dark) { matA.color.multiplyScalar(.7); matB.color.set('#0a8f7a'); matB.emissive.set('#0a8f7a'); } else { matB.color.copy(teal); matB.emissive.copy(teal); }
  bloom.strength = dark ? .55 : .2; bloom.threshold = dark ? .3 : .6; bloom.radius = dark ? .45 : .3; renderer.toneMappingExposure = dark ? 1 : .95;
  dustMat.color.set(dark ? '#2de1c2' : '#3a46a8'); dustMat.blending = dark ? THREE.AdditiveBlending : THREE.NormalBlending; dustMat.opacity = dark ? .75 : .45; dustMat.needsUpdate = true;
  paintInstances();
  if (packets) packets.forEach(m => m.material.color.set(dark ? new THREE.Color(2.2, 2.2, 2.2) : new THREE.Color('#141a52')));
}
function build() {
  scene = new THREE.Scene(); camera = new THREE.PerspectiveCamera(38, innerWidth / innerHeight, .1, 100); camera.position.set(0, 0, 15);
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.75)); renderer.setSize(innerWidth, innerHeight, false); renderer.toneMapping = THREE.ACESFilmicToneMapping;
  scene.add(new THREE.AmbientLight(0xffffff, .35));
  const p1 = new THREE.PointLight(0xffffff, 90, 40); p1.position.set(5, 4, 7); scene.add(p1); const p2 = new THREE.PointLight(0x2de1c2, 70, 40); p2.position.set(-6, -3, 5); scene.add(p2);
  group = new THREE.Group(); scene.add(group);
  const pa = [], pb = []; for (let i = 0; i <= 420; i++) { const u = i / 420; pa.push(hp(u, 0)); pb.push(hp(u, Math.PI)); }
  matA = new THREE.MeshStandardMaterial({ color: accent, emissive: accent, emissiveIntensity: 1.1, metalness: .55, roughness: .26 });
  matB = new THREE.MeshStandardMaterial({ color: teal, emissive: teal, emissiveIntensity: 1.1, metalness: .55, roughness: .26 });
  group.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pa), 420, .075, 12, false), matA));
  group.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pb), 420, .075, 12, false), matB));
  const basic = new THREE.MeshBasicMaterial({ color: 0xffffff });
  rungs = new THREE.InstancedMesh(new THREE.CylinderGeometry(.03, .03, 1, 8), basic, RUNGS);
  nodes = new THREE.InstancedMesh(new THREE.SphereGeometry(.12, 16, 16), basic.clone(), RUNGS * 2);
  const d = new THREE.Object3D(), up = new THREE.Vector3(0, 1, 0);
  for (let r = 0; r < RUNGS; r++) {
    const u = (r + .5) / RUNGS, A = hp(u, 0), B = hp(u, Math.PI), mid = A.clone().add(B).multiplyScalar(.5), dir = B.clone().sub(A), len = dir.length();
    d.position.copy(mid); d.scale.set(1, len, 1); d.quaternion.setFromUnitVectors(up, dir.normalize()); d.updateMatrix(); rungs.setMatrixAt(r, d.matrix);
    d.quaternion.identity(); d.scale.set(1, 1, 1); d.position.copy(A); d.updateMatrix(); nodes.setMatrixAt(r * 2, d.matrix); d.position.copy(B); d.updateMatrix(); nodes.setMatrixAt(r * 2 + 1, d.matrix);
  }
  group.add(rungs); group.add(nodes);
  packets = []; const pg = new THREE.SphereGeometry(.17, 16, 16);
  for (let i = 0; i < 6; i++) { const m = new THREE.Mesh(pg, new THREE.MeshBasicMaterial({ color: new THREE.Color(2.2, 2.2, 2.2) })); m.userData = { phase: i % 2 ? Math.PI : 0, u: i / 6, sp: .05 + i * .006 }; group.add(m); packets.push(m); }
  const N = 1700, pos = new Float32Array(N * 3); for (let i = 0; i < N; i++) { pos[i * 3] = (Math.random() - .5) * 34; pos[i * 3 + 1] = (Math.random() - .5) * 22; pos[i * 3 + 2] = (Math.random() - .5) * 20 - 2; }
  const dg = new THREE.BufferGeometry(); dg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  dustMat = new THREE.PointsMaterial({ size: .05, transparent: true, opacity: .7, depthWrite: false, sizeAttenuation: true }); dust = new THREE.Points(dg, dustMat); scene.add(dust);
  composer = new EffectComposer(renderer); composer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5)); composer.setSize(innerWidth, innerHeight);
  composer.addPass(new RenderPass(scene, camera)); bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), .55, .45, .3); composer.addPass(bloom); composer.addPass(new OutputPass());
  applyTheme();
}

/* keyframes: where the helix lives as you scroll */
function layoutTarget() {
  const mobile = innerWidth / innerHeight < .95, vh = innerHeight, y = scrollY;
  const sTop = scenes.offsetTop, sEnd = sTop + scenes.offsetHeight - vh, endTop = $('.pzl-end', L).offsetTop;
  const K = mobile
    ? { hero: { x: 0, y: -2.6, rz: -.2, s: .85 }, scn: { x: 0, y: -4.3, rz: -1.5, s: .6 }, end: { x: 0, y: 0, rz: -.05, s: 1 } }
    : { hero: { x: 4.6, y: 0, rz: -.26, s: 1 }, scn: { x: 0, y: -3.5, rz: -1.5, s: .78 }, end: { x: 0, y: .2, rz: -.05, s: 1.25 } };
  let a, b, t;
  if (y < sTop - vh * .6) { a = K.hero; b = K.hero; t = 0; } else if (y < sTop + vh * .2) { a = K.hero; b = K.scn; t = sm(clamp((y - (sTop - vh * .6)) / (vh * .8), 0, 1)); }
  else if (y < endTop - vh * 1.0) { a = K.scn; b = K.scn; t = 0; } else { a = K.scn; b = K.end; t = sm(clamp((y - (endTop - vh)) / vh, 0, 1)); }
  return { x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t), rz: lerp(a.rz, b.rz, t), s: lerp(a.s, b.s, t), veil: y < sTop - vh * .2 ? 1 : y > endTop - vh * .5 ? 0 : .55 };
}
const cur = { x: 4.6, y: 0, rz: -.26, s: 1 }; let spin = 0, last = 0, raf = 0;
function frame(ts) {
  raf = requestAnimationFrame(frame);
  const dt = Math.min(.05, (ts - last) / 1000 || .016); last = ts; state.t += dt;
  state.energy += ((state.typing ? 1 : 0) - state.energy) * Math.min(1, dt * 3);
  state.mx += (state.tmx - state.mx) * .05; state.my += (state.tmy - state.my) * .05;
  const T = layoutTarget(), k = Math.min(1, dt * 3.2);
  cur.x = lerp(cur.x, T.x, k); cur.y = lerp(cur.y, T.y, k); cur.rz = lerp(cur.rz, T.rz, k); cur.s = lerp(cur.s, T.s, k);
  spin += dt * (.28 + state.energy * 1.6);
  group.position.set(cur.x, cur.y + Math.sin(state.t * .6) * .12, 0); group.rotation.set(0, spin + (state.mx - .5) * .8, cur.rz); group.scale.setScalar(cur.s * (1 + Math.sin(state.t * 3) * .004 * (1 + state.energy * 3)));
  packets.forEach(m => { const d = m.userData; d.u = (d.u + dt * (d.sp + state.energy * .25)) % 1; m.position.copy(hp(d.u, d.phase)); });
  dust.rotation.y = state.t * .02 + (state.mx - .5) * .1; dust.position.y = Math.sin(state.t * .15) * .3;
  camera.position.x = (state.mx - .5) * 1.1; camera.position.y = -(state.my - .5) * .7; camera.lookAt(0, 0, 0);
  bloom.strength = (isDark() ? .55 : .2) + state.energy * (isDark() ? .5 : .15);
  composer.render();
}
function resize() { if (!renderer) return; renderer.setSize(innerWidth, innerHeight, false); composer.setSize(innerWidth, innerHeight); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); }

/* ================= scroll / events ================= */
function onScroll() {
  nav.classList.toggle('stuck', scrollY > 24);
  const span = sceneSpan(), p = clamp((scrollY - scenes.offsetTop) / Math.max(1, span), 0, .9999), inScenes = scrollY > scenes.offsetTop - innerHeight * .4 && scrollY < scenes.offsetTop + scenes.offsetHeight;
  if (inScenes) activate(clamp(Math.floor(p * SC.length), 0, SC.length - 1)); else if (activeScene !== -1) { activeScene = -1; copies.forEach(c => c.classList.remove('on')); mocks.forEach(m => m.classList.remove('on')); }
  rail.style.setProperty('--prog', (p * 100).toFixed(1) + '%');
  L.style.setProperty('--veil', layoutTarget().veil); if (reduce && renderer) frame2();
}
function frame2() { composer.render(); }
addEventListener('scroll', onScroll, { passive: true }); addEventListener('resize', () => { resize(); onScroll(); });
addEventListener('pointermove', e => { state.tmx = e.clientX / innerWidth; state.tmy = e.clientY / innerHeight; }, { passive: true });
document.addEventListener('visibilitychange', () => { if (!renderer) return; if (document.hidden) cancelAnimationFrame(raf); else if (!reduce) { last = performance.now(); raf = requestAnimationFrame(frame); } });
new MutationObserver(() => { if (renderer) { applyTheme(); if (reduce) frame2(); } }).observe(root, { attributes: true, attributeFilter: ['data-pz-theme'] });
(function watchChat() {
  const chat = document.getElementById('chat'); if (!chat) return void setTimeout(watchChat, 300);
  new MutationObserver(() => { state.typing = !!chat.querySelector('.typing-indicator'); }).observe(chat, { childList: true, subtree: true });
})();

if (renderer) { build(); resize(); { const T0 = layoutTarget(); cur.x = T0.x; cur.y = T0.y; cur.rz = T0.rz; cur.s = T0.s; } onScroll(); if (reduce) frame2(); else { last = performance.now(); raf = requestAnimationFrame(frame); } } else { L.classList.add('pz-nogl'); onScroll(); }
