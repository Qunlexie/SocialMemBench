/* ─── SocialMemBench Viewer — app.js ─────────────────────────────────────────
   Vanilla JS, no build tools.
   Views: Chat | Graph | QA
   Depends on D3 v7 loaded via CDN in index.html.
─────────────────────────────────────────────────────────────────────────────── */

// ── State ──────────────────────────────────────────────────────────────────────
const state = {
  networks: [],
  activeNetworkId: null,
  activeTab: 'chat',
  network: null,       // EgoNetwork
  conversations: null, // ConversationCorpus
  qa: [],              // QAPair[]
  qaFilter: 'all',
  graphSim: null,
};

// ── Speaker color palette ──────────────────────────────────────────────────────
const SPEAKER_COLORS = [
  '#0071e3','#34c759','#ff9500','#af52de',
  '#ff3b30','#5ac8fa','#ff6b35','#30d158',
  '#bf5af2','#ffd60a',
];
const speakerColorMap = new Map();

function getSpeakerColor(name) {
  if (!speakerColorMap.has(name)) {
    speakerColorMap.set(name, SPEAKER_COLORS[speakerColorMap.size % SPEAKER_COLORS.length]);
  }
  return speakerColorMap.get(name);
}

function getInitials(name) {
  return name.split(' ').map(w => w[0]).join('').slice(0,2).toUpperCase();
}

// ── API helpers ────────────────────────────────────────────────────────────────
async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ── Bootstrap ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  bindTabs();
  bindRefresh();
  await loadNetworks();
});

// ── Network list ───────────────────────────────────────────────────────────────
async function loadNetworks() {
  const list = document.getElementById('network-list');
  list.innerHTML = '<div class="loading-state">Loading…</div>';

  try {
    state.networks = await api('/api/networks');
  } catch (e) {
    state.networks = [];
  }

  const hint = document.getElementById('welcome-hint');
  if (state.networks.length === 0) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">◌</div>
        <div class="empty-text">No networks yet</div>
      </div>`;
    if (hint) hint.textContent = '/smb-generate-network close_friends 5';
    return;
  }

  if (hint) hint.style.display = 'none';

  list.innerHTML = state.networks.map(n => `
    <div class="network-item" data-id="${n.network_id}">
      <div class="network-item-name">${esc(n.group_name)}</div>
      <div class="network-item-meta">
        <span class="net-badge">${fmtGroupType(n.group_type)}</span>
        <span class="net-badge">${n.group_size}p</span>
        <div class="net-indicators">
          <div class="net-dot ${n.has_conversations ? 'has-conv' : ''}" title="Conversations"></div>
          <div class="net-dot ${n.has_qa ? 'has-qa' : ''}" title="QA Pairs"></div>
        </div>
      </div>
    </div>`).join('');

  list.querySelectorAll('.network-item').forEach(el => {
    el.addEventListener('click', () => selectNetwork(el.dataset.id));
  });

  // Update header meta
  const meta = document.getElementById('header-meta');
  if (meta) meta.textContent = `${state.networks.length} network${state.networks.length !== 1 ? 's' : ''}`;
}

function bindRefresh() {
  document.getElementById('refresh-btn')?.addEventListener('click', loadNetworks);
}

// ── Select network ─────────────────────────────────────────────────────────────
async function selectNetwork(id) {
  if (state.activeNetworkId === id) return;

  // Clear speaker colors for fresh network
  speakerColorMap.clear();

  state.activeNetworkId = id;

  // Sidebar highlight
  document.querySelectorAll('.network-item').forEach(el => {
    el.classList.toggle('active', el.dataset.id === id);
  });

  // Show view, hide welcome
  document.getElementById('welcome').style.display = 'none';
  const view = document.getElementById('network-view');
  view.style.display = 'flex';
  view.style.flexDirection = 'column';

  // Reset panels
  showTab('chat');

  // Load data concurrently
  const [network, conversations, qa] = await Promise.allSettled([
    api(`/api/network/${id}`),
    api(`/api/conversations/${id}`),
    api(`/api/qa/${id}`),
  ]);

  state.network       = network.status === 'fulfilled'       ? network.value       : null;
  state.conversations = conversations.status === 'fulfilled' ? conversations.value : null;
  state.qa            = qa.status === 'fulfilled'            ? qa.value            : [];

  // Pre-assign colors from personas for consistency
  if (state.network?.personas) {
    state.network.personas.forEach(p => getSpeakerColor(p.display_name));
  }

  renderTitlebar();
  renderChat();
  renderGraph();
  renderQA();
}

// ── Titlebar ───────────────────────────────────────────────────────────────────
function renderTitlebar() {
  const n = state.network;
  document.getElementById('network-name').textContent = n?.group_name ?? state.activeNetworkId;
  const badges = document.getElementById('network-badges');
  if (n) {
    badges.innerHTML = `
      <span class="badge badge-type">${fmtGroupType(n.group_type)}</span>
      <span class="badge badge-size">${n.group_size} members</span>
      ${state.conversations ? `<span class="badge badge-size">${state.conversations.sessions?.length ?? 0} sessions</span>` : ''}
      ${state.qa.length ? `<span class="badge badge-size">${state.qa.length} QA</span>` : ''}
    `;
  } else {
    badges.innerHTML = '';
  }
}

// ── Tabs ───────────────────────────────────────────────────────────────────────
function bindTabs() {
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => showTab(tab.dataset.tab));
  });
}

function showTab(name) {
  state.activeTab = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `panel-${name}`));

  // Render graph lazily (needs SVG dimensions)
  if (name === 'graph' && state.network) renderGraph();
}

// ═══════════════════════════════════════════════════════════════════════════════
// CHAT VIEW
// ═══════════════════════════════════════════════════════════════════════════════
function renderChat() {
  const container = document.getElementById('chat-container');

  if (!state.conversations) {
    container.innerHTML = `
      <div class="empty-state" style="margin:auto">
        <div class="empty-icon">💬</div>
        <div class="empty-text">No conversations for this network yet.</div>
      </div>`;
    return;
  }

  const sessions = state.conversations.sessions ?? [];
  if (!sessions.length) {
    container.innerHTML = '<div class="empty-state" style="margin:auto"><div class="empty-text">No sessions found.</div></div>';
    return;
  }

  const html = [];

  sessions.forEach(session => {
    html.push(`
      <div class="session-header">
        <div class="session-line"></div>
        <div class="session-label">${esc(session.date_label ?? `Session ${session.session_index}`)}</div>
        ${session.topic ? `<div class="session-topic">${esc(session.topic)}</div>` : ''}
        <div class="session-line"></div>
      </div>`);

    const turns = session.turns ?? [];
    let prevSpeaker = null;

    turns.forEach((turn, i) => {
      const isNewSpeaker = turn.speaker_display_name !== prevSpeaker;
      prevSpeaker = turn.speaker_display_name;

      const color    = getSpeakerColor(turn.speaker_display_name);
      const initials = getInitials(turn.speaker_display_name);
      const challenges = turn.planted_challenges ?? [];
      const hasChallenge = challenges.length > 0;

      const challengeBadges = challenges.map(c =>
        `<span class="challenge-badge">⚡ ${fmtChallengeType(c.challenge_type)}</span>`
      ).join('');

      html.push(`
        <div class="msg-group ${isNewSpeaker ? 'new-speaker' : ''}">
          ${isNewSpeaker
            ? `<div class="msg-avatar" style="background:${color}">${initials}</div>`
            : `<div class="msg-avatar spacer"></div>`}
          <div class="msg-body">
            ${isNewSpeaker ? `
              <div class="msg-meta">
                <span class="msg-speaker" style="color:${color}">${esc(turn.speaker_display_name)}</span>
                <span class="msg-time">${esc(turn.timestamp_label ?? '')}</span>
              </div>` : ''}
            <div class="message-bubble ${hasChallenge ? 'has-challenge' : ''}">
              ${esc(turn.message)}
              ${hasChallenge ? `<div class="challenge-badges">${challengeBadges}</div>` : ''}
            </div>
          </div>
        </div>`);
    });
  });

  container.innerHTML = html.join('');
  container.scrollTop = 0;
}

// ═══════════════════════════════════════════════════════════════════════════════
// GRAPH VIEW (D3)
// ═══════════════════════════════════════════════════════════════════════════════
function renderGraph() {
  const svg = d3.select('#graph-svg');
  svg.selectAll('*').remove();

  if (state.graphSim) { state.graphSim.stop(); state.graphSim = null; }

  if (!state.network) {
    renderGraphEmpty();
    return;
  }

  const personas = state.network.personas ?? [];
  const edges    = state.network.edges    ?? [];

  if (!personas.length) { renderGraphEmpty(); return; }

  // Build lookup
  const personaById = new Map(personas.map(p => [p.persona_id, p]));

  // SVG dimensions
  const el  = document.getElementById('graph-svg');
  const W   = el.clientWidth  || 700;
  const H   = el.clientHeight || 500;

  // Defs: arrowhead
  const defs = svg.append('defs');
  defs.append('marker')
    .attr('id', 'arrow')
    .attr('viewBox', '0 -4 8 8')
    .attr('refX', 30).attr('refY', 0)
    .attr('markerWidth', 6).attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-4L8,0L0,4')
    .attr('fill', '#c7c7cc');

  // Background for zoom/pan
  const bg = svg.append('rect')
    .attr('width', W).attr('height', H)
    .attr('fill', 'transparent');

  const g = svg.append('g').attr('class', 'graph-root');

  // Zoom behavior
  const zoom = d3.zoom()
    .scaleExtent([.3, 3])
    .on('zoom', e => g.attr('transform', e.transform));
  svg.call(zoom);

  // ── Data prep ──────────────────────────────────────────────────────────────
  const nodes = personas.map(p => ({ ...p, id: p.persona_id }));

  const links = edges.map(e => ({
    ...e,
    source: e.persona_a_id,
    target: e.persona_b_id,
  }));

  // Closeness → width
  const linkWidth = { High: 3, Medium: 2, Low: 1 };

  // Sentiment → color
  const sentColor = {
    positive: '#34c759',
    neutral:  '#aeaeb2',
    mixed:    '#ff9500',
    tense:    '#ff3b30',
  };

  // ── Links ──────────────────────────────────────────────────────────────────
  const link = g.append('g').attr('class', 'links')
    .selectAll('.link')
    .data(links).join('line')
    .attr('class', 'link')
    .attr('stroke', d => sentColor[d.sentiment] ?? '#aeaeb2')
    .attr('stroke-width', d => linkWidth[d.closeness] ?? 1.5)
    .attr('stroke-opacity', .6)
    .attr('marker-end', 'url(#arrow)')
    .attr('stroke-linecap', 'round')
    .on('click', (event, d) => {
      event.stopPropagation();
      showEdgeDetail(d, personaById);
    });

  // ── Nodes ──────────────────────────────────────────────────────────────────
  const node = g.append('g').attr('class', 'nodes')
    .selectAll('.node')
    .data(nodes).join('g')
    .attr('class', 'node')
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) sim.alphaTarget(.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag',  (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end',   (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }))
    .on('click', (event, d) => {
      event.stopPropagation();
      showNodeDetail(d);
      node.classed('selected', n => n.id === d.id);
    });

  node.append('circle')
    .attr('r', 28)
    .attr('fill', d => getSpeakerColor(d.display_name));

  // Initials inside circle
  node.append('text')
    .attr('y', 5)
    .attr('font-size', 13)
    .attr('font-weight', '700')
    .attr('fill', 'rgba(255,255,255,0.95)')
    .attr('text-anchor', 'middle')
    .attr('pointer-events', 'none')
    .text(d => getInitials(d.display_name));

  // Name label below circle
  node.append('text')
    .attr('y', 46)
    .text(d => d.display_name);

  // ── Simulation ─────────────────────────────────────────────────────────────
  const sim = d3.forceSimulation(nodes)
    .force('link',   d3.forceLink(links).id(d => d.id).distance(160))
    .force('charge', d3.forceManyBody().strength(-450))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide(44))
    .on('tick', () => {
      link
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

  state.graphSim = sim;

  // Click background to deselect
  svg.on('click', () => {
    node.classed('selected', false);
    showGraphDetailEmpty();
  });

  // ── Legend ─────────────────────────────────────────────────────────────────
  const legendData = [
    { label: 'Positive', color: sentColor.positive },
    { label: 'Neutral',  color: sentColor.neutral },
    { label: 'Mixed',    color: sentColor.mixed },
    { label: 'Tense',    color: sentColor.tense },
  ];

  const legend = svg.append('g').attr('transform', 'translate(16,16)');
  legendData.forEach((d, i) => {
    const row = legend.append('g').attr('transform', `translate(0, ${i * 20})`);
    row.append('line').attr('x1', 0).attr('x2', 18).attr('y1', 8).attr('y2', 8)
      .attr('stroke', d.color).attr('stroke-width', 2);
    row.append('text').attr('x', 24).attr('y', 12)
      .attr('font-size', 10).attr('fill', '#6e6e73').text(d.label);
  });
}

function renderGraphEmpty() {
  const detail = document.getElementById('graph-detail');
  detail.innerHTML = `
    <div class="detail-empty">
      <p>No graph data for this network.</p>
    </div>`;
}

function showGraphDetailEmpty() {
  document.getElementById('graph-detail').innerHTML = `
    <div class="detail-empty">
      <p>Click a <strong>node</strong> to see persona details.</p>
      <p>Click an <strong>edge</strong> to see relationship details.</p>
    </div>`;
}

function showNodeDetail(persona) {
  const color = getSpeakerColor(persona.display_name);
  const prefs = persona.preferences ?? {};
  const allPrefs = [
    ...(prefs.food         ?? []),
    ...(prefs.activities   ?? []),
    ...(prefs.social       ?? []),
    ...(prefs.domain_specific ?? []),
  ];
  const bf  = persona.big_five ?? {};
  const cp  = persona.communication_profile ?? {};

  document.getElementById('graph-detail').innerHTML = `
    <div class="detail-section">
      <div class="detail-title">Persona</div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
        <div style="width:40px;height:40px;border-radius:50%;background:${color};display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:14px;flex-shrink:0">${getInitials(persona.display_name)}</div>
        <div>
          <div class="detail-name">${esc(persona.display_name)}</div>
          <div class="detail-sub">${persona.age ? `Age ${persona.age}` : ''}${persona.occupation ? ` · ${esc(persona.occupation)}` : ''}</div>
        </div>
      </div>
      ${persona.background ? `<p class="detail-bio">${esc(persona.background)}</p>` : ''}
    </div>

    ${Object.keys(bf).length ? `
    <div class="divider"></div>
    <div class="detail-section">
      <div class="detail-title">Big Five</div>
      ${Object.entries(bf).map(([k,v]) => `
        <div class="detail-row">
          <span class="detail-key">${capitalize(k)}</span>
          <span class="detail-val" style="color:${bfColor(v)}">${v}</span>
        </div>`).join('')}
    </div>` : ''}

    ${Object.keys(cp).length ? `
    <div class="divider"></div>
    <div class="detail-section">
      <div class="detail-title">Communication</div>
      ${Object.entries(cp).map(([k,v]) => `
        <div class="detail-row">
          <span class="detail-key">${capitalize(k.replace(/_/g,' '))}</span>
          <span class="detail-val">${v}</span>
        </div>`).join('')}
    </div>` : ''}

    ${allPrefs.length ? `
    <div class="divider"></div>
    <div class="detail-section">
      <div class="detail-title">Preferences</div>
      <div class="pref-tags">
        ${allPrefs.map(p => `<span class="pref-tag ${p.implicit ? 'implicit' : ''}">${esc(p.value)}</span>`).join('')}
      </div>
    </div>` : ''}

    ${(persona.speaking_quirks ?? []).length ? `
    <div class="divider"></div>
    <div class="detail-section">
      <div class="detail-title">Speaking Quirks</div>
      <div class="pref-tags">
        ${persona.speaking_quirks.map(q => `<span class="pref-tag">${esc(q)}</span>`).join('')}
      </div>
    </div>` : ''}
  `;
}

function showEdgeDetail(edge, personaById) {
  const a = personaById.get(edge.persona_a_id);
  const b = personaById.get(edge.persona_b_id);
  const sentColors = { positive:'#34c759', neutral:'#aeaeb2', mixed:'#ff9500', tense:'#ff3b30' };

  document.getElementById('graph-detail').innerHTML = `
    <div class="detail-section">
      <div class="detail-title">Relationship</div>
      <div class="detail-name" style="font-size:15px">
        ${esc(a?.display_name ?? edge.persona_a_id)} → ${esc(b?.display_name ?? edge.persona_b_id)}
      </div>
      <div class="detail-sub" style="margin-bottom:12px">${esc(edge.relationship_type ?? '')}</div>
      <div class="detail-row">
        <span class="detail-key">Closeness</span>
        <span class="detail-val">${edge.closeness}</span>
      </div>
      <div class="detail-row">
        <span class="detail-key">Sentiment</span>
        <span class="detail-val" style="color:${sentColors[edge.sentiment] ?? '#1d1d1f'}">${edge.sentiment}</span>
      </div>
    </div>
    ${edge.history_summary ? `
    <div class="divider"></div>
    <div class="detail-section">
      <div class="detail-title">History</div>
      <p class="detail-bio">${esc(edge.history_summary)}</p>
    </div>` : ''}
    ${(edge.shared_events ?? []).length ? `
    <div class="divider"></div>
    <div class="detail-section">
      <div class="detail-title">Shared Events</div>
      <div class="pref-tags">
        ${edge.shared_events.map(e => `<span class="pref-tag">${esc(e)}</span>`).join('')}
      </div>
    </div>` : ''}
  `;
}

// ═══════════════════════════════════════════════════════════════════════════════
// QA VIEW
// ═══════════════════════════════════════════════════════════════════════════════
const QA_LABELS = {
  Q1:'single_contact_recall', Q2:'group_decision_recall', Q3:'multi_contact_aggregation',
  Q4:'contamination_probe',   Q5:'theory_of_mind_reference', Q6:'norm_vs_individual',
  Q7:'relational_edge_query', Q8:'temporal_preference_evolution',
};

function renderQA() {
  const list    = document.getElementById('qa-list');
  const filters = document.getElementById('qa-filters');
  const count   = document.getElementById('qa-count');

  if (!state.qa.length) {
    filters.innerHTML = '';
    count.textContent = '';
    list.innerHTML = `
      <div class="empty-state" style="margin:auto">
        <div class="empty-icon">📋</div>
        <div class="empty-text">No QA pairs for this network yet.</div>
      </div>`;
    return;
  }

  // Build filter buttons
  const types = [...new Set(state.qa.map(q => q.query_type))].sort();
  filters.innerHTML = `
    <button class="filter-btn ${state.qaFilter === 'all' ? 'active' : ''}" data-filter="all">All</button>
    ${types.map(t => `<button class="filter-btn ${state.qaFilter === t ? 'active' : ''}" data-filter="${t}">${t}</button>`).join('')}
  `;
  filters.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      state.qaFilter = btn.dataset.filter;
      renderQA();
    });
  });

  const visible = state.qaFilter === 'all'
    ? state.qa
    : state.qa.filter(q => q.query_type === state.qaFilter);

  count.textContent = `${visible.length} of ${state.qa.length}`;

  list.innerHTML = visible.map((qa, i) => renderQACard(qa, i)).join('');

  // Toggle expand
  list.querySelectorAll('.qa-card-header').forEach(header => {
    header.addEventListener('click', () => {
      header.closest('.qa-card').classList.toggle('expanded');
    });
  });
}

function renderQACard(qa, i) {
  const opts = qa.options ?? {};
  const hasOpts = Object.keys(opts).length > 0;

  const optionsHtml = hasOpts
    ? `<div class="qa-options">
        ${Object.entries(opts).map(([key, val]) =>
          `<div class="qa-option ${qa.correct_option === key ? 'correct' : ''}">
            <span class="qa-option-key">${key}.</span>
            <span>${esc(val)}</span>
          </div>`).join('')}
       </div>`
    : `<div class="qa-answer">${esc(qa.answer)}</div>`;

  const evidenceHtml = (qa.evidence_anchors ?? []).map(e => `
    <div class="evidence-item">
      <div class="evidence-item-meta">
        <span class="evidence-speaker">${esc(e.speaker_display_name)}</span>
        <span class="evidence-sep">·</span>
        <span class="evidence-session">Session ${e.session_index}</span>
      </div>
      <div class="evidence-quote">"${esc(e.message_excerpt)}"</div>
      <div class="evidence-relevance">${esc(e.relevance)}</div>
    </div>`).join('');

  const qcHtml = buildQCBadges(qa);

  return `
    <div class="qa-card" data-qa-id="${esc(qa.qa_id ?? i)}">
      <div class="qa-card-header">
        <div class="qa-type-badge qtype-${qa.query_type}">${qa.query_type}</div>
        <div class="qa-card-meta">
          <div class="qa-question">${esc(qa.question)}</div>
          <div class="qa-badges">
            <span class="badge badge-${qa.difficulty ?? 'medium'}">${qa.difficulty ?? ''}</span>
            <span class="badge" style="background:var(--bg);color:var(--text-2);border:1px solid var(--border-light)">${fmtQTypeLabel(qa.query_type_label)}</span>
            ${qa.answer_format ? `<span class="badge" style="background:var(--bg);color:var(--text-3);border:1px solid var(--border-light)">${qa.answer_format.replace('_',' ')}</span>` : ''}
          </div>
        </div>
        <svg class="qa-chevron" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
        </svg>
      </div>
      <div class="qa-card-body">
        <div>
          <div class="qa-section-label">Answer</div>
          ${optionsHtml}
        </div>
        ${evidenceHtml ? `<div>
          <div class="qa-section-label">Evidence (${qa.evidence_anchors?.length ?? 0})</div>
          <div class="evidence-list">${evidenceHtml}</div>
        </div>` : ''}
        ${qcHtml ? `<div>
          <div class="qa-section-label">QC</div>
          <div class="qc-row">${qcHtml}</div>
        </div>` : ''}
      </div>
    </div>`;
}

function buildQCBadges(qa) {
  const parts = [];
  if (qa.qc_phase1_score != null) {
    const score = (qa.qc_phase1_score * 100).toFixed(0);
    const cls = qa.qc_phase1_score >= .7 ? 'qc-pass' : 'qc-fail';
    parts.push(`<span class="qc-badge ${cls}">P1 ${score}%</span>`);
  }
  if (qa.qc_phase2_grounded != null) {
    parts.push(`<span class="qc-badge ${qa.qc_phase2_grounded ? 'qc-pass' : 'qc-fail'}">P2 ${qa.qc_phase2_grounded ? 'Grounded' : 'Ungrounded'}</span>`);
  }
  if (qa.qc_phase3_flagged != null) {
    parts.push(`<span class="qc-badge ${qa.qc_phase3_flagged ? 'qc-fail' : 'qc-pass'}">P3 ${qa.qc_phase3_flagged ? '⚑ Flagged' : '✓ Clean'}</span>`);
  }
  return parts.join('');
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
}

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
}

function fmtGroupType(t) {
  return (t ?? '').replace(/_/g,' ');
}

function fmtChallengeType(t) {
  return (t ?? '').replace(/_/g,' ');
}

function fmtQTypeLabel(label) {
  if (!label) return '';
  return label.replace(/_/g,' ');
}

function bfColor(level) {
  return { High: '#34c759', Medium: '#ff9500', Low: '#ff3b30' }[level] ?? '#1d1d1f';
}
