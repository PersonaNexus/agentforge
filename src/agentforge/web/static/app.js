/* AgentForge Web UI — Frontend Logic */

// ========== DARK MODE ==========
function initTheme() {
    const saved = localStorage.getItem('agentforge-theme');
    const prefer = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    const theme = saved || prefer;
    applyTheme(theme);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('agentforge-theme', theme);
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '\u2600' : '\u263D';
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    applyTheme(current === 'dark' ? 'light' : 'dark');
}

// ========== TAB ROUTING ==========
function showTab(name) {
    document.querySelectorAll('.tab-content').forEach(el => el.hidden = true);
    document.querySelectorAll('.nav-link').forEach(el => el.removeAttribute('aria-current'));
    const tab = document.getElementById('tab-' + name);
    if (tab) {
        tab.hidden = false;
        const link = document.querySelector(`.nav-link[data-tab="${name}"]`);
        if (link) link.setAttribute('aria-current', 'page');
    }
}

window.addEventListener('hashchange', () => {
    const hash = location.hash.slice(1) || 'extract';
    showTab(hash);
});

// ========== EMPTY STATE MANAGEMENT ==========
function hideEmptyState(tabName) {
    const el = document.getElementById(tabName + '-empty');
    if (el) el.hidden = true;
}

function showEmptyState(tabName) {
    const el = document.getElementById(tabName + '-empty');
    if (el) el.hidden = false;
}

// ========== RENDERING HELPERS ==========
function renderRolePanel(role) {
    return `<div class="panel panel-blue">
        <div class="panel-title">Role</div>
        <strong>${esc(role.title)}</strong> (${esc(role.seniority)})<br>
        <small>Domain: ${esc(role.domain)} &mdash; ${esc(role.purpose)}</small>
    </div>`;
}

function renderSkillsTable(skills) {
    if (!skills || !skills.length) return '';
    const tableId = 'skills-table-' + Date.now();
    const rows = skills.map((s, i) => {
        const isHuman = s.category === 'soft';
        const badge = isHuman ? ' <span class="human-badge" title="Requires human judgment">Human</span>' : '';
        return `<tr class="${isHuman ? 'human-row' : ''}" data-idx="${i}">
        <td>${esc(s.name)}${badge}</td>
        <td><span class="cat-${s.category}">${esc(s.category)}</span></td>
        <td>${esc(s.proficiency)}</td>
        <td>${esc(s.importance)}</td>
        <td><small>${esc(s.context || '')}</small></td>
    </tr>`;
    }).join('');
    return `<table id="${tableId}" data-skills='${JSON.stringify(skills).replace(/'/g, "&#39;")}'>
        <thead><tr>
            <th class="sortable-th" data-col="name" onclick="sortSkillsTable('${tableId}','name',this)">Skill <span class="sort-arrow">&#9650;</span></th>
            <th class="sortable-th" data-col="category" onclick="sortSkillsTable('${tableId}','category',this)">Category <span class="sort-arrow">&#9650;</span></th>
            <th class="sortable-th" data-col="proficiency" onclick="sortSkillsTable('${tableId}','proficiency',this)">Proficiency <span class="sort-arrow">&#9650;</span></th>
            <th class="sortable-th" data-col="importance" onclick="sortSkillsTable('${tableId}','importance',this)">Importance <span class="sort-arrow">&#9650;</span></th>
            <th>Context</th>
        </tr></thead>
        <tbody>${rows}</tbody>
    </table>`;
}

// ========== SORTABLE TABLE LOGIC ==========
const PROFICIENCY_ORDER = { beginner: 0, intermediate: 1, advanced: 2, expert: 3 };
const IMPORTANCE_ORDER = { nice_to_have: 0, preferred: 1, required: 2 };

window.sortSkillsTable = function(tableId, col, thEl) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const skills = JSON.parse(table.dataset.skills);

    // Toggle direction
    const currentDir = thEl.getAttribute('data-sort-dir');
    const dir = currentDir === 'asc' ? 'desc' : 'asc';

    // Clear all headers
    table.querySelectorAll('.sortable-th').forEach(th => {
        th.removeAttribute('data-sort-dir');
        th.querySelector('.sort-arrow').innerHTML = '&#9650;';
    });
    thEl.setAttribute('data-sort-dir', dir);
    thEl.querySelector('.sort-arrow').innerHTML = dir === 'asc' ? '&#9650;' : '&#9660;';

    // Sort
    const sorted = [...skills].sort((a, b) => {
        let va, vb;
        if (col === 'proficiency') {
            va = PROFICIENCY_ORDER[a[col]] || 0;
            vb = PROFICIENCY_ORDER[b[col]] || 0;
        } else if (col === 'importance') {
            va = IMPORTANCE_ORDER[a[col]] || 0;
            vb = IMPORTANCE_ORDER[b[col]] || 0;
        } else {
            va = (a[col] || '').toLowerCase();
            vb = (b[col] || '').toLowerCase();
        }
        if (va < vb) return dir === 'asc' ? -1 : 1;
        if (va > vb) return dir === 'asc' ? 1 : -1;
        return 0;
    });

    // Re-render tbody
    const tbody = table.querySelector('tbody');
    tbody.innerHTML = sorted.map(s => {
        const isHuman = s.category === 'soft';
        const badge = isHuman ? ' <span class="human-badge" title="Requires human judgment">Human</span>' : '';
        return `<tr class="${isHuman ? 'human-row' : ''}">
        <td>${esc(s.name)}${badge}</td>
        <td><span class="cat-${s.category}">${esc(s.category)}</span></td>
        <td>${esc(s.proficiency)}</td>
        <td>${esc(s.importance)}</td>
        <td><small>${esc(s.context || '')}</small></td>
    </tr>`;
    }).join('');
};

function renderTraitBars(traits) {
    if (!traits || typeof traits !== 'object') return '';
    const entries = Object.entries(traits).filter(([, v]) => v != null).sort((a, b) => a[0].localeCompare(b[0]));
    if (!entries.length) return '';
    const bars = entries.map(([name, value]) => {
        const pct = Math.round(value * 100);
        return `<div class="trait-bar-container">
            <span class="trait-bar-label">${esc(name)}</span>
            <div class="trait-bar-track"><div class="trait-bar-fill" style="width:${pct}%"></div></div>
            <span class="trait-bar-value">${pct}%</span>
        </div>`;
    }).join('');
    return `<div class="panel"><div class="panel-title">Personality Traits</div>${bars}</div>`;
}

function renderSuggestedTraits(suggested) {
    if (!suggested) return '';
    const traits = {};
    for (const [k, v] of Object.entries(suggested)) {
        if (v != null && typeof v === 'number') traits[k] = v;
    }
    return renderTraitBars(traits);
}

function renderAutomation(potential, rationale) {
    const pct = Math.round((potential || 0) * 100);
    const cls = pct < 30 ? 'auto-low' : pct < 60 ? 'auto-mid' : 'auto-high';

    // SVG progress ring
    const radius = 32;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (pct / 100) * circumference;
    const strokeColor = pct < 30 ? 'var(--af-red)' : pct < 60 ? 'var(--af-yellow)' : 'var(--af-green)';

    return `<div class="panel ${cls}">
        <div class="panel-title">Automation Assessment</div>
        <div class="auto-ring-container">
            <svg class="auto-ring" viewBox="0 0 80 80">
                <circle class="auto-ring-bg" cx="40" cy="40" r="${radius}"/>
                <circle class="auto-ring-fill" cx="40" cy="40" r="${radius}"
                    stroke="${strokeColor}"
                    stroke-dasharray="${circumference}"
                    stroke-dashoffset="${offset}"/>
                <text class="auto-ring-text" x="40" y="40">${pct}%</text>
            </svg>
            <div class="auto-ring-info">
                <strong>Automation Potential</strong><br>
                <small>${esc(rationale || '')}</small>
            </div>
        </div>
    </div>`;
}

// Keywords that flag responsibilities as requiring human judgment
const HUMAN_KEYWORDS = [
    "mentor", "lead", "negotiate", "present", "interview",
    "hire", "fire", "counsel", "coach", "empathize",
    "relationship", "stakeholder", "executive",
];

function renderHumanElements(skills, responsibilities) {
    const humanSkills = (skills || []).filter(s => s.category === 'soft');
    const humanResponsibilities = (responsibilities || []).filter(r =>
        HUMAN_KEYWORDS.some(kw => r.toLowerCase().includes(kw))
    );

    if (!humanSkills.length && !humanResponsibilities.length) return '';

    let content = '';

    if (humanSkills.length) {
        const skillItems = humanSkills.map(s => {
            const importanceCls = s.importance === 'required' ? 'human-critical' : 'human-moderate';
            return `<li class="${importanceCls}">
                <strong>${esc(s.name)}</strong>
                ${s.importance === 'required' ? '<span class="human-critical-tag">Critical</span>' : ''}
                ${s.context ? `<br><small>${esc(s.context)}</small>` : ''}
            </li>`;
        }).join('');
        content += `<div class="human-section">
            <div class="human-section-title">Skills Requiring Human Judgment</div>
            <ul class="human-list">${skillItems}</ul>
        </div>`;
    }

    if (humanResponsibilities.length) {
        const respItems = humanResponsibilities.map(r => {
            const matched = HUMAN_KEYWORDS.filter(kw => r.toLowerCase().includes(kw));
            return `<li>
                ${esc(r)}
                <br><small class="human-keywords">Keywords: ${matched.join(', ')}</small>
            </li>`;
        }).join('');
        content += `<div class="human-section">
            <div class="human-section-title">Responsibilities Requiring Human Element</div>
            <ul class="human-list">${respItems}</ul>
        </div>`;
    }

    const total = (skills || []).length;
    const humanCount = humanSkills.length + humanResponsibilities.length;
    const aiCount = total - humanSkills.length;

    content += `<div class="human-summary">
        <span class="human-stat"><span class="human-stat-icon">&#9679;</span> ${humanSkills.length} human-critical skill${humanSkills.length !== 1 ? 's' : ''}</span>
        <span class="human-stat"><span class="ai-stat-icon">&#9679;</span> ${aiCount} AI-augmentable skill${aiCount !== 1 ? 's' : ''}</span>
        <span class="human-stat"><span class="human-stat-icon">&#9679;</span> ${humanResponsibilities.length} human-dependent responsibilit${humanResponsibilities.length !== 1 ? 'ies' : 'y'}</span>
    </div>`;

    return `<div class="panel panel-human">
        <div class="panel-title">Human Elements</div>
        <small>These areas are best handled by humans and should not be fully delegated to AI agents.</small>
        ${content}
    </div>`;
}

// ========== AGENT VALUE ESTIMATOR (client-side mirror of backend) ==========
const CATEGORY_WEIGHTS = { tool: 0.90, hard: 0.75, domain: 0.60, soft: 0.30 };
const VALUE_IMPORTANCE_WEIGHTS = { required: 1.0, preferred: 0.6, nice_to_have: 0.25 };
const PROFICIENCY_DISCOUNTS = { beginner: 0.0, intermediate: 0.05, advanced: 0.12, expert: 0.20 };

function computeAgentValue(data, salaryMin, salaryMax) {
    const sMin = salaryMin || data.salary_min;
    const sMax = salaryMax || data.salary_max;
    if (!sMin && !sMax) return null;

    const midpoint = (sMin && sMax) ? (sMin + sMax) / 2 : (sMin || sMax);
    const automation = data.automation_potential || 0;
    const baseValue = midpoint * automation;

    // Skill factor
    let skillFactor = 0.5;
    if (data.skills && data.skills.length) {
        let totalW = 0, weightedSum = 0;
        data.skills.forEach(s => {
            const imp = VALUE_IMPORTANCE_WEIGHTS[s.importance] || 0.5;
            const cat = CATEGORY_WEIGHTS[s.category] || 0.5;
            totalW += imp;
            weightedSum += imp * cat;
        });
        skillFactor = totalW > 0 ? weightedSum / totalW : 0.5;
    }

    // Proficiency discount
    let profDiscount = 0;
    if (data.skills && data.skills.length) {
        let total = 0;
        data.skills.forEach(s => { total += PROFICIENCY_DISCOUNTS[s.proficiency] || 0.05; });
        profDiscount = total / data.skills.length;
    }

    // Human penalty
    let humanPenalty = 0;
    if (data.responsibilities && data.responsibilities.length) {
        const humanCount = data.responsibilities.filter(r =>
            HUMAN_KEYWORDS.some(kw => r.toLowerCase().includes(kw))
        ).length;
        humanPenalty = (humanCount / data.responsibilities.length) * 0.5;
    }

    // Availability bonus
    const availBonus = 1.0 + (automation * 0.3);

    const estimated = Math.max(0, baseValue * skillFactor * (1 - profDiscount) * (1 - humanPenalty) * availBonus);

    return {
        estimated_value: Math.round(estimated),
        salary_midpoint: Math.round(midpoint),
        base_value: Math.round(baseValue),
        skill_factor: skillFactor,
        proficiency_discount: profDiscount,
        human_penalty: humanPenalty,
        availability_bonus: availBonus,
    };
}

function formatCurrency(n) {
    return '$' + n.toLocaleString('en-US');
}

function renderAgentValue(valueEstimate) {
    if (!valueEstimate) return '';
    const v = valueEstimate;
    const ratio = v.salary_midpoint > 0 ? (v.estimated_value / v.salary_midpoint * 100).toFixed(0) : 0;

    // Determine color based on value-to-salary ratio
    const cls = ratio >= 50 ? 'value-high' : ratio >= 25 ? 'value-mid' : 'value-low';

    return `<div class="panel panel-value ${cls}">
        <div class="panel-title">Estimated Agent Value</div>
        <div class="value-headline">
            <span class="value-amount">${formatCurrency(v.estimated_value)}</span>
            <span class="value-period">/year</span>
        </div>
        <small>Based on ${formatCurrency(v.salary_midpoint)} salary midpoint</small>
        <div class="value-factors">
            <div class="value-factor">
                <span class="value-factor-label">Base value</span>
                <span class="value-factor-value">${formatCurrency(v.base_value)}</span>
                <small>salary &times; ${Math.round((v.base_value / v.salary_midpoint) * 100)}% automation</small>
            </div>
            <div class="value-factor">
                <span class="value-factor-label">Skill factor</span>
                <span class="value-factor-value">&times;${v.skill_factor.toFixed(2)}</span>
                <small>category automation weight</small>
            </div>
            <div class="value-factor">
                <span class="value-factor-label">Proficiency discount</span>
                <span class="value-factor-value">&minus;${(v.proficiency_discount * 100).toFixed(1)}%</span>
                <small>expert requirements harder to replicate</small>
            </div>
            <div class="value-factor">
                <span class="value-factor-label">Human penalty</span>
                <span class="value-factor-value">&minus;${(v.human_penalty * 100).toFixed(1)}%</span>
                <small>responsibilities requiring judgment</small>
            </div>
            <div class="value-factor">
                <span class="value-factor-label">Availability bonus</span>
                <span class="value-factor-value">&times;${v.availability_bonus.toFixed(2)}</span>
                <small>24/7 operation multiplier</small>
            </div>
        </div>
    </div>`;
}

function renderGapAnalysis(score, gaps) {
    if (score == null) return '';
    const pct = Math.round(score * 100);
    const cls = pct > 70 ? 'coverage-high' : pct > 50 ? 'coverage-mid' : 'coverage-low';
    const gapList = (gaps || []).slice(0, 8).map(g => `<li>${esc(g)}</li>`).join('');
    const more = (gaps || []).length > 8 ? `<li><em>...and ${gaps.length - 8} more</em></li>` : '';
    return `<div class="panel panel-${pct > 70 ? 'green' : pct > 50 ? 'yellow' : 'red'}">
        <div class="panel-title">Gap Analysis</div>
        <span class="coverage-badge ${cls}">${pct}%</span> coverage
        ${gapList || more ? `<ul>${gapList}${more}</ul>` : ''}
    </div>`;
}

function renderSkillScores(scores) {
    if (!scores || !scores.length) return '';
    const rows = scores.map(s => `<tr>
        <td>${esc(s.skill)}</td>
        <td>${Math.round(s.score * 100)}%</td>
        <td><span class="priority-${s.priority}">${esc(s.priority)}</span></td>
    </tr>`).join('');
    return `<h4>Skill-by-Skill Coverage</h4>
    <table><thead><tr><th>Skill</th><th>Score</th><th>Priority</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function renderExtractionResult(data, salaryMin, salaryMax) {
    const valueEstimate = computeAgentValue(data, salaryMin, salaryMax);
    return renderRolePanel(data.role)
        + renderSkillsTable(data.skills)
        + renderHumanElements(data.skills, data.responsibilities)
        + renderSuggestedTraits(data.suggested_traits)
        + renderAutomation(data.automation_potential, data.automation_rationale)
        + renderAgentValue(valueEstimate);
}

function renderCultureProfile(profile) {
    const values = (profile.values || []).map(v => {
        const deltas = Object.entries(v.trait_deltas || {})
            .map(([k, d]) => `${k}: ${d > 0 ? '+' : ''}${d.toFixed(2)}`).join(', ');
        return `<li><strong>${esc(v.name)}</strong>: ${esc(v.description)}
            ${deltas ? `<br><small>Trait deltas: ${esc(deltas)}</small>` : ''}</li>`;
    }).join('');
    return `<div class="panel panel-blue">
        <div class="panel-title">Culture Profile</div>
        <strong>${esc(profile.name)}</strong><br>
        <small>${esc(profile.description || '')}</small><br>
        <small>Tone: ${esc(profile.communication_tone || 'N/A')} &mdash;
        Decision: ${esc(profile.decision_style || 'N/A')}</small>
        <ul>${values}</ul>
    </div>`;
}

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

// ========== EXTRACT ==========
let _lastExtractResult = null;
let _lastForgeResult = null;

function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
}

function jsonToYaml(obj, indent) {
    indent = indent || 0;
    const pad = '  '.repeat(indent);
    if (obj === null || obj === undefined) return pad + 'null';
    if (typeof obj === 'string') return obj.includes('\n') ? `|\n${obj.split('\n').map(l => pad + '  ' + l).join('\n')}` : `"${obj}"`;
    if (typeof obj === 'number' || typeof obj === 'boolean') return String(obj);
    if (Array.isArray(obj)) return obj.map(item => pad + '- ' + (typeof item === 'object' && item !== null ? '\n' + jsonToYaml(item, indent + 2).replace(/^\s+/, '') : jsonToYaml(item, 0))).join('\n');
    if (typeof obj === 'object') return Object.entries(obj).filter(([,v]) => v !== null).map(([k, v]) => {
        const valStr = jsonToYaml(v, indent + 1);
        return typeof v === 'object' && v !== null ? `${pad}${k}:\n${valStr}` : `${pad}${k}: ${valStr}`;
    }).join('\n');
    return String(obj);
}

function renderDownloadBar(prefix) {
    prefix = prefix || 'Extract';
    const tag = prefix.toLowerCase();
    return `<div class="download-bar" style="margin-bottom:1rem;display:flex;gap:0.5rem;">
        <button class="secondary outline" onclick="_download${prefix}JSON()">Download JSON</button>
        <button class="secondary outline" onclick="_download${prefix}YAML()">Download YAML</button>
    </div>`;
}

// Extract page downloads
window._downloadExtractJSON = function() {
    if (!_lastExtractResult) return;
    const name = (_lastExtractResult.role?.title || 'extraction').replace(/\s+/g, '_').toLowerCase();
    downloadFile(JSON.stringify(_lastExtractResult, null, 2), `${name}_extraction.json`, 'application/json');
};

window._downloadExtractYAML = function() {
    if (!_lastExtractResult) return;
    const name = (_lastExtractResult.role?.title || 'extraction').replace(/\s+/g, '_').toLowerCase();
    downloadFile(jsonToYaml(_lastExtractResult), `${name}_extraction.yaml`, 'text/yaml');
};

// Forge page downloads (full pipeline result)
window._downloadForgeJSON = function() {
    if (!_lastForgeResult) return;
    const name = (_lastForgeResult.blueprint?.extraction?.role?.title || 'forge').replace(/\s+/g, '_').toLowerCase();
    downloadFile(JSON.stringify(_lastForgeResult, null, 2), `${name}_forge_result.json`, 'application/json');
};

window._downloadForgeYAML = function() {
    if (!_lastForgeResult) return;
    const name = (_lastForgeResult.blueprint?.extraction?.role?.title || 'forge').replace(/\s+/g, '_').toLowerCase();
    downloadFile(jsonToYaml(_lastForgeResult), `${name}_forge_result.yaml`, 'text/yaml');
};

document.getElementById('extract-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('extract-btn');
    const results = document.getElementById('extract-results');
    btn.setAttribute('aria-busy', 'true');
    btn.disabled = true;
    results.hidden = true;
    _lastExtractResult = null;
    hideEmptyState('extract');

    const formData = new FormData(e.target);
    const userSalaryMin = parseFloat(formData.get('salary_min')) || null;
    const userSalaryMax = parseFloat(formData.get('salary_max')) || null;
    // Remove salary fields from FormData (not needed by backend extract endpoint)
    formData.delete('salary_min');
    formData.delete('salary_max');
    try {
        const resp = await fetch('/api/extract', { method: 'POST', body: formData });
        const data = await resp.json();
        if (!resp.ok) {
            results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Error</div>${esc(data.detail || 'Unknown error')}</div>`;
        } else {
            _lastExtractResult = data;
            results.innerHTML = renderDownloadBar('Extract') + renderExtractionResult(data, userSalaryMin, userSalaryMax);
        }
        results.hidden = false;
    } catch (err) {
        results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Error</div>${esc(err.message)}</div>`;
        results.hidden = false;
    } finally {
        btn.removeAttribute('aria-busy');
        btn.disabled = false;
    }
});

// ========== FORGE ==========
const FORGE_STAGES = ['ingest', 'extract', 'map', 'culture', 'generate', 'analyze', 'deep_analyze'];
const FORGE_STAGE_LABELS = {
    ingest: 'Parse File', extract: 'Extract Skills', map: 'Map Traits',
    culture: 'Apply Culture', generate: 'Generate Identity', analyze: 'Gap Analysis',
    deep_analyze: 'Deep Analysis'
};

function initForgeStages(mode) {
    const container = document.getElementById('forge-stages');
    let stages = ['ingest', 'extract'];
    if (mode === 'default') stages.push('map', 'culture', 'generate', 'analyze');
    else if (mode === 'deep') stages.push('map', 'culture', 'generate', 'deep_analyze');
    else stages.push('generate');

    container.innerHTML = stages.map(s =>
        `<div class="stage-item stage-pending" id="stage-${s}">
            <span class="stage-icon">&#9675;</span>
            <span>${FORGE_STAGE_LABELS[s] || s}</span>
        </div>`
    ).join('');
}

function updateForgeStage(stage) {
    // Mark previous active as done
    document.querySelectorAll('.stage-item.stage-active').forEach(el => {
        el.classList.remove('stage-active');
        el.classList.add('stage-done');
        el.querySelector('.stage-icon').innerHTML = '&#10003;';
    });
    // Mark current as active
    const el = document.getElementById('stage-' + stage);
    if (el) {
        el.classList.remove('stage-pending');
        el.classList.add('stage-active');
        el.querySelector('.stage-icon').innerHTML = '&#8635;';
    }
}

function completeAllStages() {
    document.querySelectorAll('.stage-item.stage-active').forEach(el => {
        el.classList.remove('stage-active');
        el.classList.add('stage-done');
        el.querySelector('.stage-icon').innerHTML = '&#10003;';
    });
}

document.getElementById('forge-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('forge-btn');
    const progress = document.getElementById('forge-progress');
    const results = document.getElementById('forge-results');
    btn.setAttribute('aria-busy', 'true');
    btn.disabled = true;
    results.hidden = true;
    hideEmptyState('forge');

    const formData = new FormData(e.target);
    const forgeSalaryMin = parseFloat(formData.get('salary_min')) || null;
    const forgeSalaryMax = parseFloat(formData.get('salary_max')) || null;
    formData.delete('salary_min');
    formData.delete('salary_max');
    const mode = formData.get('mode');
    initForgeStages(mode);
    progress.hidden = false;

    try {
        const resp = await fetch('/api/forge', { method: 'POST', body: formData });
        const { job_id } = await resp.json();
        if (!resp.ok) throw new Error('Failed to start forge job');

        // Connect SSE
        const es = new EventSource(`/api/forge/${job_id}/stream`);
        es.onmessage = (evt) => {
            const data = JSON.parse(evt.data);
            if (data.event === 'stage') {
                updateForgeStage(data.stage);
            } else if (data.event === 'done') {
                completeAllStages();
                es.close();
                _lastForgeResult = data;
                const bp = data.blueprint;
                let html = renderDownloadBar('Forge');
                html += renderExtractionResult(bp.extraction, forgeSalaryMin, forgeSalaryMax);
                if (data.traits) html += renderTraitBars(data.traits);
                html += renderGapAnalysis(data.coverage_score, data.coverage_gaps);
                if (data.skill_scores) html += renderSkillScores(data.skill_scores);

                // Identity file downloads
                html += `<div class="download-row" style="margin-top:1rem;display:flex;gap:0.5rem;flex-wrap:wrap;">
                    <a href="/api/forge/${job_id}/download/yaml" role="button" class="outline">Download Identity YAML</a>
                    ${data.skill_file ? `<a href="/api/forge/${job_id}/download/skill" role="button" class="outline">Download SKILL.md</a>` : ''}
                    ${data.skill_folder ? `<a href="/api/forge/${job_id}/download/skill-folder" role="button" class="outline">Download Skill Folder (ZIP)</a>` : ''}
                </div>`;

                // Blueprint summary
                html += `<div class="panel panel-green">
                    <div class="panel-title">Agent Forged Successfully</div>
                    <strong>${esc(bp.extraction.role.title)}</strong> &mdash;
                    Skills: ${bp.extraction.skills.length} |
                    Coverage: ${Math.round(bp.coverage_score * 100)}% |
                    Automation: ${Math.round(bp.automation_estimate * 100)}%
                </div>`;

                results.innerHTML = html;
                results.hidden = false;
                btn.removeAttribute('aria-busy');
                btn.disabled = false;
            } else if (data.event === 'error') {
                es.close();
                results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Pipeline Error</div>${esc(data.message)}</div>`;
                results.hidden = false;
                btn.removeAttribute('aria-busy');
                btn.disabled = false;
            }
        };
        es.onerror = () => {
            es.close();
            btn.removeAttribute('aria-busy');
            btn.disabled = false;
        };
    } catch (err) {
        results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Error</div>${esc(err.message)}</div>`;
        results.hidden = false;
        btn.removeAttribute('aria-busy');
        btn.disabled = false;
    }
});

// ========== BATCH ==========
document.getElementById('batch-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('batch-btn');
    const progress = document.getElementById('batch-progress');
    const bar = document.getElementById('batch-bar');
    const status = document.getElementById('batch-status');
    const results = document.getElementById('batch-results');
    btn.setAttribute('aria-busy', 'true');
    btn.disabled = true;
    results.hidden = true;
    progress.hidden = false;
    bar.value = 0;
    hideEmptyState('batch');

    const formData = new FormData(e.target);
    try {
        const resp = await fetch('/api/batch', { method: 'POST', body: formData });
        const { job_id } = await resp.json();
        if (!resp.ok) throw new Error('Failed to start batch job');

        const es = new EventSource(`/api/batch/${job_id}/stream`);
        es.onmessage = (evt) => {
            const data = JSON.parse(evt.data);
            if (data.event === 'progress') {
                const pct = data.total > 0 ? Math.round((data.completed / data.total) * 100) : 0;
                bar.value = pct;
                bar.max = 100;
                status.textContent = `Processing ${data.file} (${data.completed}/${data.total})...`;
            } else if (data.event === 'done') {
                es.close();
                bar.value = 100;
                status.textContent = 'Complete!';

                const res = data.results || [];
                const rows = res.map(r => `<tr>
                    <td>${esc(r.file)}</td>
                    <td>${r.success ? '<span class="badge-ok">OK</span>' : '<span class="badge-fail">FAIL</span>'}</td>
                    <td>${esc(r.agent_title || r.error || '-')}</td>
                    <td>${r.skills_count != null ? r.skills_count : '-'}</td>
                    <td>${r.coverage != null ? r.coverage + '%' : '-'}</td>
                    <td>${r.duration}s</td>
                </tr>`).join('');

                const succeeded = res.filter(r => r.success).length;
                const failed = res.length - succeeded;
                let html = `<table>
                    <thead><tr><th>File</th><th>Status</th><th>Agent</th><th>Skills</th><th>Coverage</th><th>Time</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
                <p><strong>Summary:</strong> ${succeeded} succeeded, ${failed} failed, ${res.length} total</p>`;

                if (Object.keys(data.files || {}).length > 0) {
                    html += `<a href="/api/batch/${job_id}/download/zip" role="button" class="outline">Download All (ZIP)</a>`;
                }

                results.innerHTML = html;
                results.hidden = false;
                btn.removeAttribute('aria-busy');
                btn.disabled = false;
            } else if (data.event === 'error') {
                es.close();
                results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Batch Error</div>${esc(data.message)}</div>`;
                results.hidden = false;
                btn.removeAttribute('aria-busy');
                btn.disabled = false;
            }
        };
    } catch (err) {
        results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Error</div>${esc(err.message)}</div>`;
        results.hidden = false;
        btn.removeAttribute('aria-busy');
        btn.disabled = false;
    }
});

// ========== CULTURE ==========
async function loadCultureTemplates() {
    try {
        const resp = await fetch('/api/culture/list');
        const templates = await resp.json();
        const container = document.getElementById('culture-templates');
        container.innerHTML = templates.map(t => `<article>
            <header>${esc(t.display_name)}</header>
            <p>${esc(t.description)}</p>
            <small>${t.value_count} values</small>
            <footer><details><summary>View YAML</summary><pre class="yaml-preview">${esc(t.yaml)}</pre></details></footer>
        </article>`).join('');
    } catch (err) {
        console.error('Failed to load culture templates:', err);
    }
}

document.getElementById('culture-parse-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const results = document.getElementById('culture-parse-results');
    const formData = new FormData(e.target);
    try {
        const resp = await fetch('/api/culture/parse', { method: 'POST', body: formData });
        const data = await resp.json();
        if (!resp.ok) {
            results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Error</div>${esc(data.detail)}</div>`;
        } else {
            results.innerHTML = renderCultureProfile(data);
        }
        results.hidden = false;
    } catch (err) {
        results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Error</div>${esc(err.message)}</div>`;
        results.hidden = false;
    }
});

document.getElementById('culture-mixin-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const results = document.getElementById('culture-mixin-results');
    const formData = new FormData(e.target);
    try {
        const resp = await fetch('/api/culture/to-mixin', { method: 'POST', body: formData });
        const data = await resp.json();
        if (!resp.ok) {
            results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Error</div>${esc(data.detail)}</div>`;
        } else {
            results.innerHTML = `<div class="panel panel-green">
                <div class="panel-title">PersonaNexus Mixin</div>
                <pre class="yaml-preview">${esc(data.mixin_yaml)}</pre>
            </div>`;
        }
        results.hidden = false;
    } catch (err) {
        results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Error</div>${esc(err.message)}</div>`;
        results.hidden = false;
    }
});

// ========== SETTINGS ==========
async function loadSettings() {
    try {
        const resp = await fetch('/api/settings');
        const data = await resp.json();
        const form = document.getElementById('settings-form');
        form.elements.api_key.placeholder = data.api_key || 'sk-ant-...';
        form.elements.default_model.value = data.default_model;
        form.elements.output_dir.value = data.output_dir;
        form.elements.batch_parallel.value = data.batch_parallel;
    } catch (err) {
        console.error('Failed to load settings:', err);
    }
}

document.getElementById('settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const body = {
        api_key: form.elements.api_key.value,
        default_model: form.elements.default_model.value,
        output_dir: form.elements.output_dir.value,
        batch_parallel: parseInt(form.elements.batch_parallel.value) || 1,
    };
    try {
        const resp = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        document.getElementById('settings-status').innerHTML = data.saved
            ? '<p style="color:var(--af-success-text)">Settings saved successfully.</p>'
            : '<p style="color:var(--af-error-text)">Failed to save settings.</p>';
    } catch (err) {
        document.getElementById('settings-status').innerHTML = `<p style="color:var(--af-error-text)">${esc(err.message)}</p>`;
    }
});

document.getElementById('validate-key-btn').addEventListener('click', async () => {
    const key = document.getElementById('settings-form').elements.api_key.value;
    const status = document.getElementById('key-status');
    status.innerHTML = '<span class="spinner"></span>';
    try {
        const resp = await fetch('/api/settings/validate-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: key }),
        });
        const data = await resp.json();
        status.innerHTML = data.valid
            ? '<small style="color:var(--af-success-text)">Valid</small>'
            : `<small style="color:var(--af-error-text)">Invalid: ${esc(data.error)}</small>`;
    } catch (err) {
        status.innerHTML = `<small style="color:var(--af-error-text)">${esc(err.message)}</small>`;
    }
});

// ========== INIT ==========
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
    const hash = location.hash.slice(1) || 'extract';
    showTab(hash);
    loadCultureTemplates();
    loadSettings();
});
