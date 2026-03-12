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

// Token cost estimation constants
const CATEGORY_DAILY_INTERACTIONS = { tool: 80, hard: 40, domain: 20, soft: 15 };
const CATEGORY_TOKENS_PER_CALL = { tool: 800, hard: 1500, domain: 2500, soft: 3000 };
const PROFICIENCY_TOKEN_MULTIPLIERS = { beginner: 0.7, intermediate: 1.0, advanced: 1.3, expert: 1.6 };
const DEFAULT_COST_PER_1K_TOKENS = 0.008;
const DEFAULT_MONTHLY_INFRA = 200;
const WORKING_DAYS_PER_MONTH = 22;

function estimateMonthlyTokens(data) {
    const skills = data.skills || [];
    if (!skills.length) return 1000000;

    let totalDaily = 0;
    skills.forEach(s => {
        const dailyCalls = CATEGORY_DAILY_INTERACTIONS[s.category] || 30;
        const tokensPerCall = CATEGORY_TOKENS_PER_CALL[s.category] || 1500;
        const profMult = PROFICIENCY_TOKEN_MULTIPLIERS[s.proficiency] || 1.0;
        const impWeight = VALUE_IMPORTANCE_WEIGHTS[s.importance] || 0.5;
        totalDaily += dailyCalls * tokensPerCall * profMult * impWeight;
    });

    const numSkills = skills.length;
    let effectiveDaily;
    if (numSkills > 1) {
        const avgDaily = totalDaily / numSkills;
        effectiveDaily = avgDaily * (1.0 + 0.6 * (numSkills - 1));
    } else {
        effectiveDaily = totalDaily;
    }

    const automation = data.automation_potential || 0;
    effectiveDaily *= Math.max(0.1, automation);

    return Math.round(effectiveDaily * WORKING_DAYS_PER_MONTH);
}

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

    const grossValue = Math.max(0, baseValue * skillFactor * (1 - profDiscount) * (1 - humanPenalty) * availBonus);

    // Cost modeling
    const monthlyTokens = estimateMonthlyTokens(data);
    const monthlyTokenCost = (monthlyTokens / 1000) * DEFAULT_COST_PER_1K_TOKENS;
    const monthlyTotalCost = monthlyTokenCost + DEFAULT_MONTHLY_INFRA;
    const annualTotalCost = monthlyTotalCost * 12;
    const netAnnualValue = grossValue - annualTotalCost;
    const roiMultiple = annualTotalCost > 0 ? netAnnualValue / annualTotalCost : 0;
    const paybackMonths = grossValue > 0 ? annualTotalCost / (grossValue / 12) : 0;

    return {
        estimated_value: Math.round(grossValue),
        salary_midpoint: Math.round(midpoint),
        base_value: Math.round(baseValue),
        skill_factor: skillFactor,
        proficiency_discount: profDiscount,
        human_penalty: humanPenalty,
        availability_bonus: availBonus,
        monthly_token_cost: Math.round(monthlyTokenCost),
        monthly_infra_cost: DEFAULT_MONTHLY_INFRA,
        monthly_total_cost: Math.round(monthlyTotalCost),
        annual_total_cost: Math.round(annualTotalCost),
        net_annual_value: Math.round(netAnnualValue),
        roi_multiple: roiMultiple,
        payback_months: paybackMonths,
        estimated_monthly_tokens: monthlyTokens,
    };
}

function formatCurrency(n) {
    return '$' + n.toLocaleString('en-US');
}

function formatTokens(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(0) + 'K';
    return n.toString();
}

function renderAgentValue(valueEstimate) {
    if (!valueEstimate) return '';
    const v = valueEstimate;
    const ratio = v.salary_midpoint > 0 ? (v.estimated_value / v.salary_midpoint * 100).toFixed(0) : 0;

    // Determine color based on value-to-salary ratio
    const cls = ratio >= 50 ? 'value-high' : ratio >= 25 ? 'value-mid' : 'value-low';
    const roiCls = v.roi_multiple >= 5 ? 'value-high' : v.roi_multiple >= 2 ? 'value-mid' : 'value-low';

    return `<div class="panel panel-value ${cls}">
        <div class="panel-title">Agent Value &amp; Cost Analysis</div>
        <div class="value-headline">
            <span class="value-amount">${formatCurrency(v.estimated_value)}</span>
            <span class="value-period">/year gross</span>
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
        <div class="value-cost-section">
            <div class="panel-title">Operating Costs</div>
            <div class="value-factors">
                <div class="value-factor">
                    <span class="value-factor-label">Token usage</span>
                    <span class="value-factor-value">${formatTokens(v.estimated_monthly_tokens)}/mo</span>
                    <small>based on skill mix &amp; proficiency</small>
                </div>
                <div class="value-factor">
                    <span class="value-factor-label">Token cost</span>
                    <span class="value-factor-value">${formatCurrency(v.monthly_token_cost)}/mo</span>
                    <small>at $${DEFAULT_COST_PER_1K_TOKENS}/1K tokens</small>
                </div>
                <div class="value-factor">
                    <span class="value-factor-label">Infrastructure</span>
                    <span class="value-factor-value">${formatCurrency(v.monthly_infra_cost)}/mo</span>
                    <small>monitoring, orchestration, maintenance</small>
                </div>
                <div class="value-factor">
                    <span class="value-factor-label">Annual operating cost</span>
                    <span class="value-factor-value">${formatCurrency(v.annual_total_cost)}/yr</span>
                    <small>${formatCurrency(v.monthly_total_cost)}/mo total</small>
                </div>
            </div>
        </div>
        <div class="value-net-section ${roiCls}">
            <div class="value-headline">
                <span class="value-amount">${formatCurrency(v.net_annual_value)}</span>
                <span class="value-period">/year net value</span>
            </div>
            <div class="value-factors">
                <div class="value-factor">
                    <span class="value-factor-label">ROI</span>
                    <span class="value-factor-value">${v.roi_multiple.toFixed(1)}x</span>
                    <small>net value / operating cost</small>
                </div>
                <div class="value-factor">
                    <span class="value-factor-label">Payback period</span>
                    <span class="value-factor-value">${v.payback_months.toFixed(1)} months</span>
                    <small>time to recoup annual costs</small>
                </div>
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

// ========== AGENT TEAM COMPOSITION ==========
// Archetype definitions for client-side team composition (mirrors backend)
const TEAM_ARCHETYPES = {
    research_analyst: {
        label: 'Research Analyst', icon: '\uD83D\uDD0D',
        categories: ['domain'],
        keywords: ['research','analysis','data','insight','market','competitive','trend','report','survey','benchmark'],
        personality: { rigor: 0.85, creativity: 0.60, patience: 0.75, directness: 0.70 },
        benefit: 'Continuously surfaces insights so {role} can make faster, data-informed decisions',
    },
    technical_builder: {
        label: 'Technical Builder', icon: '\uD83D\uDEE0\uFE0F',
        categories: ['hard'],
        keywords: ['develop','build','code','engineer','implement','architect','design','test','debug','deploy','software','programming'],
        personality: { rigor: 0.90, directness: 0.80, creativity: 0.55, patience: 0.60 },
        benefit: 'Handles technical implementation so {role} can focus on architecture and strategy',
    },
    ops_automator: {
        label: 'Ops Automator', icon: '\u2699\uFE0F',
        categories: ['tool'],
        keywords: ['automate','pipeline','workflow','process','monitor','ci/cd','devops','cloud','integration','platform','tool'],
        personality: { rigor: 0.85, directness: 0.85, patience: 0.50, creativity: 0.40 },
        benefit: 'Manages tooling and automation so {role} spends less time on repetitive tasks',
    },
    content_crafter: {
        label: 'Content Crafter', icon: '\u270D\uFE0F',
        categories: [],
        keywords: ['write','draft','document','content','copy','edit','report','proposal','presentation','communication','spec','prd'],
        personality: { creativity: 0.80, verbosity: 0.75, warmth: 0.60, rigor: 0.65 },
        benefit: 'Drafts and polishes documents and communications so {role} can iterate quickly',
    },
    data_navigator: {
        label: 'Data Navigator', icon: '\uD83D\uDCCA',
        categories: [],
        keywords: ['data','analytics','metrics','dashboard','sql','database','visualization','reporting','statistics','bi','etl'],
        personality: { rigor: 0.90, directness: 0.75, patience: 0.65, creativity: 0.45 },
        benefit: 'Wrangles data and surfaces key metrics so {role} always has the numbers',
    },
    stakeholder_liaison: {
        label: 'Stakeholder Liaison', icon: '\uD83E\uDD1D',
        categories: ['soft'],
        keywords: ['stakeholder','client','customer','communicate','present','negotiate','relationship','collaborate','meeting'],
        personality: { warmth: 0.85, empathy: 0.80, patience: 0.80, directness: 0.55 },
        benefit: 'Prepares briefs and tracks action items so {role} can focus on relationships',
    },
    quality_guardian: {
        label: 'Quality Guardian', icon: '\uD83D\uDEE1\uFE0F',
        categories: [],
        keywords: ['quality','test','review','audit','compliance','security','standard','validation','risk','governance'],
        personality: { rigor: 0.95, directness: 0.80, epistemic_humility: 0.75, patience: 0.70 },
        benefit: 'Reviews and validates work against standards so {role} can ship with confidence',
    },
};

function composeAgentTeam(data) {
    const skills = data.skills || [];
    if (!skills.length) return null;

    const roleTitle = (data.role && data.role.title) || 'this role';
    const roleShort = roleTitle.split(',')[0].trim();

    // Score each archetype
    const scored = [];
    for (const [key, arch] of Object.entries(TEAM_ARCHETYPES)) {
        let matchedSkills = [];
        let score = 0;
        skills.forEach(s => {
            let pts = 0;
            if (arch.categories.includes(s.category)) pts += 2;
            const text = `${s.name} ${s.context || ''} ${s.genai_application || ''}`.toLowerCase();
            arch.keywords.forEach(kw => { if (text.includes(kw)) pts += 0.5; });
            if (pts > 0) { matchedSkills.push(s); score += pts; }
        });
        if (matchedSkills.length) scored.push({ key, score, skills: matchedSkills });
    }
    scored.sort((a, b) => b.score - a.score);

    // Greedy assignment
    const assigned = new Set();
    const teammates = [];
    for (const entry of scored) {
        if (teammates.length >= 5) break;
        const unassigned = entry.skills.filter(s => !assigned.has(s.name));
        if (!unassigned.length) continue;
        const arch = TEAM_ARCHETYPES[entry.key];
        teammates.push({
            _key: entry.key,
            name: arch.label,
            archetype: arch.label,
            icon: arch.icon,
            skills: unassigned.map(s => s.name),
            personality: arch.personality,
            benefit: arch.benefit.replace('{role}', roleShort),
        });
        unassigned.forEach(s => assigned.add(s.name));
    }

    // Sweep remaining into closest-matching teammate
    const remaining = skills.filter(s => !assigned.has(s.name));
    if (remaining.length && teammates.length) {
        remaining.forEach(s => {
            let best = 0, bestScore = 0;
            teammates.forEach((tm, i) => {
                const arch = TEAM_ARCHETYPES[tm._key];
                if (!arch) return;
                let sc = 0;
                if (arch.categories.includes(s.category)) sc += 2;
                const txt = `${s.name} ${s.context || ''} ${s.genai_application || ''}`.toLowerCase();
                arch.keywords.forEach(kw => { if (txt.includes(kw)) sc += 0.5; });
                if (sc > bestScore) { bestScore = sc; best = i; }
            });
            teammates[best].skills.push(s.name);
        });
    }

    if (!teammates.length) return null;

    return {
        role_title: roleTitle,
        teammates,
        team_benefit: `A team of ${teammates.length} specialized AI agents designed to amplify the ${roleShort}'s impact — handling the heavy lifting while keeping humans in the driver's seat.`,
    };
}

function renderAgentTeam(team) {
    if (!team || !team.teammates || !team.teammates.length) return '';

    const cards = team.teammates.map(t => {
        const topTraits = Object.entries(t.personality || {})
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(([name, val]) => `<span class="team-trait">${esc(name.replace('_',' '))} <strong>${Math.round(val*100)}%</strong></span>`)
            .join('');

        const skillTags = (t.skills || []).slice(0, 6).map(s =>
            `<span class="team-skill-tag">${esc(s)}</span>`
        ).join('');
        const moreSkills = (t.skills || []).length > 6 ? `<span class="team-skill-tag team-skill-more">+${t.skills.length - 6}</span>` : '';

        return `<div class="team-card">
            <div class="team-card-header">
                <span class="team-card-icon">${esc(t.icon || '\uD83E\uDD16')}</span>
                <div>
                    <div class="team-card-name">${esc(t.name)}</div>
                    <div class="team-card-archetype">${esc(t.archetype)}</div>
                </div>
            </div>
            <div class="team-card-benefit">${esc(t.benefit)}</div>
            <div class="team-card-skills">${skillTags}${moreSkills}</div>
            <div class="team-card-traits">${topTraits}</div>
        </div>`;
    }).join('');

    return `<div class="panel panel-team">
        <div class="panel-title">Your Agent Team</div>
        <small>${esc(team.team_benefit)}</small>
        <div class="team-grid">${cards}</div>
    </div>`;
}

function renderExtractionResult(data, salaryMin, salaryMax) {
    const valueEstimate = computeAgentValue(data, salaryMin, salaryMax);
    const team = composeAgentTeam(data);
    return renderRolePanel(data.role)
        + renderAgentTeam(team)
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

// ========== FORGE WIZARD ==========
const FORGE_STAGE_LABELS = {
    ingest: 'Parsing file', extract: 'Extracting skills', methodology: 'Extracting methodology',
    map: 'Mapping traits', culture: 'Applying culture', generate: 'Generating skill',
    analyze: 'Running gap analysis', deep_analyze: 'Running deep analysis', team_compose: 'Composing agent team'
};

// Wizard step navigation
let _forgeCurrentStep = 1;

function forgeShowStep(step) {
    _forgeCurrentStep = step;
    for (let i = 1; i <= 4; i++) {
        const panel = document.getElementById('forge-step-' + i);
        if (panel) panel.hidden = (i !== step);
    }
    // Update step indicators
    document.querySelectorAll('.wizard-step').forEach(el => {
        const s = parseInt(el.dataset.step);
        el.classList.remove('active', 'done');
        if (s === step) el.classList.add('active');
        else if (s < step) el.classList.add('done');
    });
}

function initForgeWizard() {
    // Prevent default form submission (wizard handles it)
    document.getElementById('forge-form').addEventListener('submit', (e) => e.preventDefault());

    // File input -> dropzone
    const dropzone = document.getElementById('forge-dropzone');
    const fileInput = document.getElementById('forge-file-input');
    const filenameEl = document.getElementById('forge-filename');
    const nextBtn = document.getElementById('forge-next-1');

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            const name = fileInput.files[0].name;
            filenameEl.textContent = name;
            filenameEl.hidden = false;
            dropzone.classList.add('has-file');
            nextBtn.disabled = false;
        }
    });

    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('drag-over'); });
    dropzone.addEventListener('dragleave', () => { dropzone.classList.remove('drag-over'); });
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            fileInput.dispatchEvent(new Event('change'));
        }
    });

    // Step navigation
    nextBtn.addEventListener('click', () => forgeShowStep(2));
    document.getElementById('forge-back-2').addEventListener('click', () => forgeShowStep(1));
    document.getElementById('forge-next-2').addEventListener('click', () => startForge());

    // Personality sliders
    initTraitSliders();
}

// ========== PERSONALITY TRAIT SLIDERS ==========
const TRAIT_DEFS = [
    { key: 'rigor',              label: 'Rigor',              tip: 'How precise and detail-oriented. High = meticulous, low = big-picture.' },
    { key: 'directness',         label: 'Directness',         tip: 'How straightforward in communication. High = blunt and clear, low = diplomatic.' },
    { key: 'warmth',             label: 'Warmth',             tip: 'How friendly and approachable the tone. High = warm, low = professional/detached.' },
    { key: 'creativity',         label: 'Creativity',         tip: 'How inventive in problem-solving. High = novel approaches, low = proven methods.' },
    { key: 'verbosity',          label: 'Verbosity',          tip: 'How detailed responses are. High = thorough explanations, low = concise.' },
    { key: 'patience',           label: 'Patience',           tip: 'How much step-by-step explanation. High = patient teaching, low = expects expertise.' },
    { key: 'empathy',            label: 'Empathy',            tip: 'How much emotional context is considered. High = emotionally aware, low = purely logical.' },
    { key: 'epistemic_humility', label: 'Epistemic Humility', tip: 'How readily the agent acknowledges uncertainty. High = cautious, low = confident.' },
];

const TRAIT_DEFAULT = 0.5;
let _traitModified = {};  // track which traits user has touched

function initTraitSliders() {
    const container = document.getElementById('trait-sliders');
    container.innerHTML = TRAIT_DEFS.map(t => `
        <div class="trait-slider-row">
            <label class="trait-slider-label" title="${t.tip}">
                ${t.label} <span class="info-icon">&#9432;</span>
            </label>
            <input type="range" class="trait-slider-input" id="trait-${t.key}"
                   data-trait="${t.key}" min="0" max="100" value="50" step="1">
            <span class="trait-slider-value" id="trait-val-${t.key}">auto</span>
        </div>
    `).join('');

    // Slider event listeners
    container.querySelectorAll('.trait-slider-input').forEach(slider => {
        slider.addEventListener('input', () => {
            const trait = slider.dataset.trait;
            const pct = parseInt(slider.value);
            document.getElementById('trait-val-' + trait).textContent = pct + '%';
            slider.classList.add('modified');
            _traitModified[trait] = pct / 100;
            updateTraitOverridesInput();
        });
    });

    // Reset button
    document.getElementById('trait-reset-btn').addEventListener('click', resetTraitSliders);
}

function resetTraitSliders() {
    _traitModified = {};
    document.querySelectorAll('.trait-slider-input').forEach(slider => {
        slider.value = 50;
        slider.classList.remove('modified');
    });
    document.querySelectorAll('.trait-slider-value').forEach(el => {
        el.textContent = 'auto';
    });
    document.getElementById('trait-overrides-input').value = '';
}

function updateTraitOverridesInput() {
    const input = document.getElementById('trait-overrides-input');
    if (Object.keys(_traitModified).length > 0) {
        input.value = JSON.stringify(_traitModified);
    } else {
        input.value = '';
    }
}

function initForgeStages(mode) {
    const container = document.getElementById('forge-stages');
    let stages = ['ingest', 'extract', 'methodology'];
    if (mode === 'default') stages.push('map', 'culture', 'generate', 'analyze', 'team_compose');
    else if (mode === 'deep') stages.push('map', 'culture', 'generate', 'deep_analyze', 'team_compose');
    else stages.push('generate', 'team_compose');

    container.innerHTML = stages.map(s =>
        `<div class="forge-stage-row stage-pending" id="stage-${s}">
            <span class="forge-stage-icon">&#9675;</span>
            <span class="forge-stage-name">${FORGE_STAGE_LABELS[s] || s}</span>
        </div>`
    ).join('');
}

function updateForgeStage(stage) {
    document.querySelectorAll('.forge-stage-row.stage-active').forEach(el => {
        el.classList.remove('stage-active');
        el.classList.add('stage-done');
        el.querySelector('.forge-stage-icon').innerHTML = '&#10003;';
    });
    const el = document.getElementById('stage-' + stage);
    if (el) {
        el.classList.remove('stage-pending');
        el.classList.add('stage-active');
        el.querySelector('.forge-stage-icon').innerHTML = '&#8635;';
    }
}

function completeAllStages() {
    document.querySelectorAll('.forge-stage-row.stage-active').forEach(el => {
        el.classList.remove('stage-active');
        el.classList.add('stage-done');
        el.querySelector('.forge-stage-icon').innerHTML = '&#10003;';
    });
}

async function startForge() {
    forgeShowStep(3);

    const form = document.getElementById('forge-form');
    const formData = new FormData(form);
    const forgeSalaryMin = parseFloat(formData.get('salary_min')) || null;
    const forgeSalaryMax = parseFloat(formData.get('salary_max')) || null;
    formData.delete('salary_min');
    formData.delete('salary_max');
    const mode = formData.get('mode');
    initForgeStages(mode);

    try {
        const resp = await fetch('/api/forge', { method: 'POST', body: formData });
        const { job_id } = await resp.json();
        if (!resp.ok) throw new Error('Failed to start forge job');

        const es = new EventSource(`/api/forge/${job_id}/stream`);
        es.onmessage = (evt) => {
            const data = JSON.parse(evt.data);
            if (data.event === 'stage') {
                updateForgeStage(data.stage);
            } else if (data.event === 'done') {
                completeAllStages();
                es.close();
                _lastForgeResult = data;
                renderForgeResults(data, job_id, forgeSalaryMin, forgeSalaryMax);
                forgeShowStep(4);
            } else if (data.event === 'error') {
                es.close();
                const results = document.getElementById('forge-results');
                results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Pipeline Error</div>${esc(data.message)}</div>
                    <button type="button" class="forge-restart-btn secondary outline" onclick="forgeReset()">Try Again</button>`;
                forgeShowStep(4);
            }
        };
        es.onerror = () => { es.close(); };
    } catch (err) {
        const results = document.getElementById('forge-results');
        results.innerHTML = `<div class="panel panel-red"><div class="panel-title">Error</div>${esc(err.message)}</div>
            <button type="button" class="forge-restart-btn secondary outline" onclick="forgeReset()">Try Again</button>`;
        forgeShowStep(4);
    }
}

function renderForgeResults(data, jobId, salaryMin, salaryMax) {
    const bp = data.blueprint;
    const results = document.getElementById('forge-results');
    const skillName = data.skill_folder ? data.skill_folder.skill_name : 'skill';
    const skillMd = data.skill_folder ? data.skill_folder.skill_md : '';

    let html = '';

    // Success hero
    html += `<div class="forge-success-hero">
        <div class="forge-success-icon">&#10003;</div>
        <div class="forge-success-title">${esc(bp.extraction.role.title)}</div>
        <div class="forge-success-subtitle">${data.clawhub_skill && data.skill_folder ? 'Your Claude Code &amp; ClawHub skills are' : data.clawhub_skill ? 'Your ClawHub skill is' : 'Your Claude Code skill <code>' + esc(skillName) + '</code> is'} ready</div>
    </div>`;

    // Stats bar
    html += `<div class="forge-stats">
        <div class="forge-stat">
            <span class="forge-stat-value">${bp.extraction.skills.length}</span>
            <span class="forge-stat-label">Skills</span>
        </div>
        <div class="forge-stat">
            <span class="forge-stat-value">${data.coverage_score != null ? Math.round(data.coverage_score * 100) + '%' : '-'}</span>
            <span class="forge-stat-label">Coverage</span>
        </div>
        <div class="forge-stat">
            <span class="forge-stat-value">${Math.round(bp.automation_estimate * 100)}%</span>
            <span class="forge-stat-label">Automation</span>
        </div>
    </div>`;

    // Primary download(s)
    if (data.skill_folder) {
        html += `<div class="forge-download-hero">
            <a href="/api/forge/${jobId}/download/skill" role="button">Download SKILL.md</a>
            <div class="forge-download-hint">Save to <code>.claude/skills/${esc(skillName)}/SKILL.md</code></div>
        </div>`;
    }

    if (data.clawhub_skill) {
        const chName = data.clawhub_skill.skill_name;
        html += `<div class="forge-download-hero" style="margin-top:0.5rem;">
            <a href="/api/forge/${jobId}/download/clawhub" role="button" class="secondary">Download ClawHub SKILL.md</a>
            <div class="forge-download-hint">ClawHub/OpenClaw format &mdash; <code>${esc(chName)}</code></div>
        </div>`;
    }

    // Skill preview(s)
    if (skillMd) {
        html += `<details class="forge-skill-preview">
            <summary>Preview SKILL.md</summary>
            <pre>${esc(skillMd)}</pre>
        </details>`;
    }
    if (data.clawhub_skill) {
        html += `<details class="forge-skill-preview">
            <summary>Preview ClawHub SKILL.md</summary>
            <pre>${esc(data.clawhub_skill.skill_md)}</pre>
        </details>`;
    }

    // Detailed analysis (collapsible)
    html += `<details style="margin-top:1rem;"><summary style="font-weight:600;">Detailed Analysis</summary>`;
    html += renderRolePanel(bp.extraction.role);
    const forgeTeam = data.agent_team || composeAgentTeam(bp.extraction);
    html += renderAgentTeam(forgeTeam);
    html += renderSkillsTable(bp.extraction.skills);
    html += renderHumanElements(bp.extraction.skills, bp.extraction.responsibilities);
    html += renderSuggestedTraits(bp.extraction.suggested_traits);
    html += renderAutomation(bp.extraction.automation_potential, bp.extraction.automation_rationale);
    const forgeValue = computeAgentValue(bp.extraction, salaryMin, salaryMax);
    html += renderAgentValue(forgeValue);
    if (data.traits) html += renderTraitBars(data.traits);
    html += renderGapAnalysis(data.coverage_score, data.coverage_gaps);
    if (data.skill_scores) html += renderSkillScores(data.skill_scores);
    html += `</details>`;

    // Export raw data
    html += renderDownloadBar('Forge');

    // Restart
    html += `<div style="text-align:center;margin-top:1.5rem;">
        <button type="button" class="forge-restart-btn secondary outline" onclick="forgeReset()">Forge Another</button>
    </div>`;

    results.innerHTML = html;
}

window.forgeReset = function() {
    _lastForgeResult = null;
    document.getElementById('forge-form').reset();
    document.getElementById('forge-filename').hidden = true;
    document.getElementById('forge-dropzone').classList.remove('has-file');
    document.getElementById('forge-next-1').disabled = true;
    document.getElementById('forge-results').innerHTML = '';
    document.getElementById('forge-stages').innerHTML = '';
    resetTraitSliders();
    forgeShowStep(1);
};

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

                const fileCount = Object.keys(data.files || {}).length;
                if (fileCount > 0) {
                    html += `<a href="/api/batch/${job_id}/download/zip" role="button" class="outline">Download All ${fileCount} Skills (ZIP)</a>`;
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
    initForgeWizard();
});
