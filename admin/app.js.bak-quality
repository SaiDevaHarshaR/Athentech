const KEY = 'sahasraAdminState';
const API_BASE = "https://api.athentech.in";

// ---------- Admin auth ----------
const TOKEN_KEY = 'sahasraAdminToken';

function getAdminToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setAdminToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearAdminToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function showLoginOverlay(message) {
  const overlay = document.getElementById('adminLoginOverlay');
  if (overlay) overlay.classList.remove('hidden');
  const errEl = document.getElementById('adminLoginError');
  if (errEl) errEl.textContent = message || '';
}

function hideLoginOverlay() {
  const overlay = document.getElementById('adminLoginOverlay');
  if (overlay) overlay.classList.add('hidden');
}

// Wraps fetch(): attaches the admin bearer token, and on 401 clears the
// stored token and re-shows the login screen instead of silently failing.
async function authFetch(url, options = {}) {
  const token = getAdminToken();
  const headers = Object.assign({}, options.headers || {}, {
    'Authorization': token ? `Bearer ${token}` : ''
  });
  const res = await fetch(url, Object.assign({}, options, { headers }));

  if (res.status === 401) {
    clearAdminToken();
    showLoginOverlay('Session expired. Please sign in again.');
    throw new Error('Not authenticated');
  }
  return res;
}

async function handleAdminLogin(e) {
  e.preventDefault();
  const username = document.getElementById('adminUsername').value.trim();
  const password = document.getElementById('adminPassword').value;
  const btn = document.getElementById('adminLoginBtn');
  const errEl = document.getElementById('adminLoginError');

  btn.disabled = true;
  errEl.textContent = '';

  try {
    const res = await fetch(`${API_BASE}/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      errEl.textContent = data.detail || 'Invalid username or password.';
      btn.disabled = false;
      return;
    }

    setAdminToken(data.token);
    hideLoginOverlay();
    bootstrapAdmin();
  } catch (err) {
    errEl.textContent = 'Could not reach the server. Is the API running?';
  } finally {
    btn.disabled = false;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('adminLoginForm');
  if (form) form.addEventListener('submit', handleAdminLogin);

  if (!getAdminToken()) {
    showLoginOverlay();
  } else {
    hideLoginOverlay();
    const initialPage = window.location.hash.replace('#', '') || 'dashboard';
    navigate(pages[initialPage] ? initialPage : 'dashboard');
  }
});
const roles = [
    'Admin',
    'Doctor',
    'Nurse',
    'Lab Tech',
    'Pharmacist',
    'Reception',
    'Viewer'
];

const rolePermissions = {
    Admin: [
        'patients',
        'admissions',
        'labs',
        'pharmacy',
        'wards'
    ],

    Doctor: [
        'patients',
        'admissions',
        'labs',
        'wards'
    ],

    Nurse: [
        'patients',
        'admissions',
        'wards',
        'labs'
    ],

    'Lab Tech': [
        'patients',
        'labs'
    ],

    Pharmacist: [
        'patients',
        'pharmacy',
        'prescriptions'
    ],

    Reception: [
        'patients',
        'admissions'
    ],

    Viewer: [
        'patients',
        'admissions'
    ]
};


async function loadInstitutionsFromAPI() {
  const res = await authFetch(`${API_BASE}/admin/institutions`);
  const data = await res.json();
  if (data.status !== "success") throw new Error("Failed to load institutions");

  state.institutions = data.institutions.map(i => ({
    id: i.id,
    name: i.name,
    type: i.type,
    code: i.client_prefix,
    city: i.city,
    status: i.status,
    db_name: i.db_name,
    db_server: i.db_server || '',
    db_user: i.db_user || '',
    has_db_password: Boolean(i.has_db_password),
    // Only public configuration metadata is retained. Secret keys never leave the API.
    has_llm_key: Boolean(i.has_llm_key),
    llm_provider_count: Number(i.llm_provider_count || (i.has_llm_key ? 1 : 0)),
    allow_athentech_fallback: i.allow_athentech_fallback === true || i.allow_athentech_fallback === 1,
    llm_provider: i.llm_provider || '',
    llm_model: i.llm_model || '',
    llm_base_url: i.llm_base_url || '',
    llm_key_status: i.llm_key_status || '',
    llm_key_checked_at: i.llm_key_checked_at || ''
  }));
  save();
}

async function loadLicensesFromAPI() {
  const res = await authFetch(`${API_BASE}/admin/licenses`);
  const data = await res.json();
  if (data.status !== "success") throw new Error("Failed to load licenses");

  state.licenses = data.licenses.map(l => ({
    id: l.id,
    code: l.code,
    institutionId: l.institution_id,
    role: l.role,
    plan: l.plan,
    status: l.status,
    expiry: l.expiry_date,
    usage: 0,
    phone: l.phone,
    dobYear: l.dob_year,
    email: l.email,
    twoFactorMethod: l.two_factor_method,
  }));
  save();
}

function formatRelativeTime(isoString) {
  if (!isoString) return '';
  const then = new Date(isoString).getTime();
  if (Number.isNaN(then)) return '';
  const diffSeconds = Math.max(0, Math.floor((Date.now() - then) / 1000));

  if (diffSeconds < 60) return 'Just now';
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes} min ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} hr ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
}

// Converts one real audit/audit.log record into the same shape the
// activity feed / audit table already render ({icon, title, description,
// ts, actor}) — same shape addActivity() produces, so both real events
// and local admin-action notices can be merged and sorted together.
function auditEventToActivity(e) {
  const roleLabel = e.role ? e.role.toUpperCase() : null;

  if (e.event === 'premium_query') {
    return {
      icon: '◇',
      title: 'Premium query',
      description: `${roleLabel || 'Unknown role'} at ${e.meta?.hospital || 'unknown hospital'} asked: "${e.question || ''}"`,
      ts: e.ts,
      actor: roleLabel || 'Staff'
    };
  }

  if (e.event === 'invalid_code_attempt') {
    return {
      icon: '!',
      title: 'Invalid activation attempt',
      description: `Code ${e.code || 'unknown'} was rejected (${e.meta?.reason || 'invalid'})`,
      ts: e.ts,
      actor: 'System'
    };
  }

  return {
    icon: '•',
    title: e.event || 'Event',
    description: e.question || '',
    ts: e.ts,
    actor: roleLabel || 'System'
  };
}

// Real audit trail from the backend (audit/audit.log) — this is what
// actually matters for compliance: who queried what, and every rejected
// activation attempt. Kept separately from state.activities (which mixes
// this in with local admin-action notices for the dashboard/audit views)
// so callers that specifically need the raw real events still can.
async function loadAuditFromAPI() {
  const res = await authFetch(`${API_BASE}/admin/audit?limit=500`);
  const data = await res.json();
  if (data.status !== "success") throw new Error("Failed to load audit log");

  state.auditEvents = data.events;

  // Merge real events into the activity feed alongside local admin-action
  // notices (institution registered, etc.), sorted newest-first by real
  // timestamp, so the dashboard/audit page shows one true timeline
  // instead of two disconnected fake/real feeds.
  // Only keep local notices that have a real timestamp (i.e. created by
  // addActivity() after this fix) — filters out the old static seed
  // entries like '8 min ago' that have no ts and would otherwise show a
  // blank time forever.
  const localOnly = state.activities.filter(a => !a.fromAudit && a.ts);
  const realOnes = state.auditEvents.map(e => ({ ...auditEventToActivity(e), fromAudit: true }));

  state.activities = [...localOnly, ...realOnes]
    .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())
    .slice(0, 100);

  // Real usage-per-license count, replacing the old hardcoded seed numbers.
  const usageByCode = {};
  for (const e of state.auditEvents) {
    if (e.event === 'premium_query' && e.code) {
      usageByCode[e.code] = (usageByCode[e.code] || 0) + 1;
    }
  }
  state.licenses.forEach(l => {
    l.usage = usageByCode[l.code] || 0;
  });

  save();
}

async function loadSettingsFromAPI() {
  const res = await authFetch(`${API_BASE}/admin/settings`);
  const data = await res.json();
  if (data.status !== "success") throw new Error("Failed to load settings");

  state.settings = {
    validity: String(data.settings.license_validity_days),
    normalMode: data.settings.normal_mode_enabled,
    rateLimit: data.settings.rate_limit_per_minute,
    blockedPatterns: data.settings.extra_blocked_patterns.join(', '),
    redaction: data.settings.output_redaction_enabled,
    emailAlerts: data.settings.email_alerts_enabled,
    webhook: data.settings.webhook_url,
    alertSmtpHost: data.settings.alert_smtp_host,
    alertSmtpPort: data.settings.alert_smtp_port,
    alertSmtpUser: data.settings.alert_smtp_user,
    alertSmtpPassword: data.settings.alert_smtp_password,
    llmProviderOrder: data.settings.llm_provider_order,
    llmCustomProviders: data.settings.llm_custom_providers,
    otpSmtpHost: data.settings.otp_smtp_host,
    otpSmtpPort: data.settings.otp_smtp_port,
    otpSmtpUser: data.settings.otp_smtp_user,
    otpSmtpPassword: data.settings.otp_smtp_password,
    alertEmailTo: data.settings.alert_email_to,
  };
  save();
}


const seed = {

    institutions: [

        {
            id: 1,
            name: 'City Care Hospital',
            type: 'Hospital',
            code: 'CCARE',
            city: 'Hyderabad',
            status: 'Active'
        },

        {
            id: 2,
            name: 'Apollo Vizag',
            type: 'Hospital',
            code: 'APOL-VIZ',
            city: 'Vizag',
            status: 'Active'
        },

        {
            id: 3,
            name: 'NIMS Medical College',
            type: 'Medical College',
            code: 'NIMS-HYD',
            city: 'Hyderabad',
            status: 'Active'
        },

        {
            id: 4,
            name: 'PathCare Diagnostics',
            type: 'Diagnostic',
            code: 'PATHCARE',
            city: 'Bangalore',
            status: 'Trial'
        },

        {
            id: 5,
            name: 'MedPlus Pharma Chain',
            type: 'Pharmacy',
            code: 'MEDPLUS',
            city: 'Vijayawada',
            status: 'Active'
        }

    ],


    licenses: [

        {
            id: 1,
            code: 'ATH-DOC-8742-49',
            institutionId: 1,
            role: 'Doctor',
            plan: 'Professional',
            status: 'Active',
            expiry: '15-Dec',
            usage: 1284
        },

        {
            id: 2,
            code: 'ATH-NURSE-1123',
            institutionId: 1,
            role: 'Nurse',
            plan: 'Standard',
            status: 'Active',
            expiry: '15-Dec',
            usage: 921
        },

        {
            id: 3,
            code: 'ATH-ADMIN-002',
            institutionId: 2,
            role: 'Admin',
            plan: 'Enterprise',
            status: 'Active',
            expiry: '01-Mar',
            usage: 1840
        },

        {
            id: 4,
            code: 'ATH-LAB-0091',
            institutionId: 4,
            role: 'Lab Tech',
            plan: 'Standard',
            status: 'Trial',
            expiry: '30-Sep',
            usage: 488
        },

        {
            id: 5,
            code: 'ATH-PHAR-0211',
            institutionId: 5,
            role: 'Pharmacist',
            plan: 'Professional',
            status: 'Active',
            expiry: '21-Jan',
            usage: 760
        },

        {
            id: 6,
            code: 'ATH-DOC-3112',
            institutionId: 3,
            role: 'Doctor',
            plan: 'Professional',
            status: 'Active',
            expiry: '10-Feb',
            usage: 1330
        }

    ],


    activities: [

        {
            icon: '◇',
            title: 'License activated',
            description: 'City Care Hospital activated 3 licenses',
            time: '8 min ago',
            actor: 'Admin'
        },

        {
            icon: '▦',
            title: 'Institution registered',
            description: 'NIMS Medical College was added',
            time: '24 min ago',
            actor: 'Admin'
        },

        {
            icon: '⌁',
            title: 'Usage threshold reached',
            description: 'Apollo Vizag crossed 1,000 queries',
            time: '1 hr ago',
            actor: 'System'
        },

        {
            icon: '!',
            title: 'Validation failed',
            description: 'Invalid activation attempt detected',
            time: '2 hrs ago',
            actor: 'System'
        }

    ],


    settings: {

        validity: '90',

        normalMode: true,

        rateLimit: 60,

        blockedPatterns:
            'DROP TABLE, DELETE FROM, UNION SELECT',

        redaction: true,

        emailAlerts: true,

        webhook: ''

    },


    admins: [

        {
            name: 'Admin',
            email: 'admin@sahasra.ai',
            role: 'Super Admin'
        },

        {
            name: 'Operations',
            email: 'ops@sahasra.ai',
            role: 'Admin'
        }

    ]

};


let state =
    JSON.parse(
        localStorage.getItem(KEY) || 'null'
    ) || structuredClone(seed);


// =========================================================
// HELPERS
// =========================================================

const $ = id =>
    document.getElementById(id);


function save() {

    localStorage.setItem(
        KEY,
        JSON.stringify(state)
    );

}


function toast(message) {

    const t = $('toast');

    t.textContent = message;

    t.classList.add('show');

    clearTimeout(window.__toast);

    window.__toast =
        setTimeout(
            () => t.classList.remove('show'),
            2400
        );

}


function inst(id) {

    return state.institutions.find(
        x => x.id === Number(id)
    );

}


function activeLicenses() {

    return state.licenses.filter(
        x =>
            ['Active', 'Trial']
                .includes(x.status)
    );

}


function addActivity(
    title,
    description,
    actor = 'Admin'
) {

    state.activities.unshift({

        icon: '✦',

        title,

        description,

        ts: new Date().toISOString(),

        actor

    });

    state.activities =
        state.activities.slice(0, 30);

    save();

}


// =========================================================
// PAGE NAVIGATION
// =========================================================

const pages = {

    dashboard:
        $('dashboardPage'),

    licenses:
        $('licensesPage'),

    institutions:
        $('institutionsPage'),

    audit:
        $('auditPage'),

    analytics:
        $('analyticsPage'),

    roles:
        $('rolesPage'),

    settings:
        $('settingsPage'),

    chatbotSettings:
        $('chatbotSettingsPage')

};


let currentAdminPage = 'dashboard';

function navigate(page) {

    currentAdminPage = page;
    window.location.hash = page;

    Object.values(pages).forEach(
        p => p.classList.remove('active-page')
    );


    pages[page].classList.add(
        'active-page'
    );


    document
        .querySelectorAll('.nav-item')
        .forEach(button => {

            button.classList.toggle(
                'active',
                button.dataset.page === page
            );

        });


     const renderers = {

        dashboard: renderDashboard,

        licenses: renderLicenses,

        institutions: renderInstitutions,

        audit: renderAudit,

        analytics: renderAnalytics,

        roles: renderRoles,

        settings: async () => { await loadSettingsFromAPI(); renderSettings(); },

        chatbotSettings: loadChatbotSettings

    };


    renderers[page]();

}

// "X min ago" labels were computed once at render time and then frozen —
// they'd only update on your next click/refresh, so "10 secs ago" could
// sit there for 20 minutes looking wrong. This just re-renders the
// time-sensitive bits every 30s if you're actually looking at them,
// without refetching anything from the server.
setInterval(() => {
    if (currentAdminPage === 'dashboard') {
        renderDashboardActivities();
    } else if (currentAdminPage === 'audit') {
        renderAudit();
    }
}, 30000);


document
    .querySelectorAll('.nav-item')
    .forEach(button => {

        button.onclick = () =>
            navigate(button.dataset.page);

    });


document
    .querySelectorAll('[data-goto]')
    .forEach(button => {

        button.onclick = () =>
            navigate(button.dataset.goto);

    });


// =========================================================
// DASHBOARD
// =========================================================

function renderDashboard() {
    loadOpenAIUsage();
    const active = activeLicenses();
    const licenseCount = active.length;

    const hospitals = state.institutions.filter(
        x => x.status === 'Active'
    ).length;

    // Real totals from actual audit events — previously this added a
    // hardcoded +18420 fake padding on top of the real number, and
    // "failed validations" was a fabricated formula (licenseCount * 0.18)
    // with no connection to anything that actually happened.
    const events = state.auditEvents || [];

    const totalQueries = events.filter(e => e.event === 'premium_query').length;

    const todayStr = new Date().toDateString();
    const queriesToday = events.filter(e =>
        e.event === 'premium_query' && new Date(e.ts).toDateString() === todayStr
    ).length;

    const failed = events.filter(e => e.event === 'invalid_code_attempt').length;

    $('activeLicenses').textContent = licenseCount;
    $('activeHospitals').textContent = hospitals;
    $('queriesToday').textContent = queriesToday.toLocaleString();
    $('totalQueries').textContent = totalQueries.toLocaleString();
    $('failedValidations').textContent = failed;

    renderDashboardChart();
    renderDashboardActivities();
}


// =========================================================
// DASHBOARD CHART
// =========================================================

function renderDashboardChart() {

    const colors = [

    '#6a5cf6',
    '#38bdf8',
    '#34d399',
    '#fbbf24',
    '#f87171',
    '#a78bfa',
    '#2dd4bf',
    '#fb923c'

    ];


    const values =
        state.institutions.map(
            institution =>

                state.licenses

                    .filter(
                        license =>
                            license.institutionId ===
                            institution.id
                    )

                    .reduce(
                        (sum, license) =>
                            sum + license.usage,
                        0
                    ) + 1
        );


    const total =
        values.reduce(
            (a, b) => a + b,
            0
        );


    let current = 0;

    const parts = [];


    state.institutions.forEach(
        (institution, index) => {

            const percentage =
                values[index] /
                total *
                100;


            parts.push(

                `${colors[index % colors.length]} ` +
                `${current}% ` +
                `${current + percentage}%`

            );


            current += percentage;

        }
    );


    $('dashboardDonut').style.background =

        `conic-gradient(${parts.join(',')})`;


    $('chartLegend').innerHTML =

        state.institutions.map(
            (institution, index) => {

                const percentage =
                    Math.round(
                        values[index] /
                        total *
                        100
                    );


                return `

                    <div class="legend-item">

                        <span
                            class="legend-dot"
                            style="
                                background:
                                ${colors[index % colors.length]}
                            "
                        ></span>

                        <span>
                            ${institution.name}
                        </span>

                        <span class="legend-value">
                            ${percentage}%
                        </span>

                    </div>

                `;

            }
        ).join('');

}


// =========================================================
// DASHBOARD ACTIVITY
// =========================================================

function renderDashboardActivities() {

    $('activityList').innerHTML =

        state.activities
            .slice(0, 8)
            .map(activity => `

                <div class="activity">

                    <div class="activity-icon">
                        ${activity.icon}
                    </div>

                    <div class="activity-content">

                        <strong>
                            ${activity.title}
                        </strong>

                        <p>
                            ${activity.description}
                        </p>

                    </div>

                    <span class="activity-time">
                        ${formatRelativeTime(activity.ts)}
                    </span>

                </div>

            `)
            .join('')

        ||

        '<div class="empty">No activity yet.</div>';

}


// =========================================================
// SELECT HELPERS
// =========================================================

function fillSelect(
    id,
    items,
    label = 'All'
) {

    const element = $(id);

    const previous =
        element.value;


    element.innerHTML =

        `<option value="all">
            ${label}
        </option>`;


    items.forEach(item => {

        element.innerHTML +=

            `<option value="${item}">
                ${item}
            </option>`;

    });


    if (items.includes(previous)) {

        element.value =
            previous;

    }

}


// =========================================================
// INSTITUTION REGISTRY
// =========================================================

function renderInstitutions() {

    fillSelect(

        'cityFilter',

        [
            ...new Set(
                state.institutions
                    .map(i => i.city)
            )
        ],

        'All Cities'

    );


    const search =
        $('registrySearch')
            .value
            .toLowerCase();


    const type =
        $('typeFilter').value;


    const status =
        $('statusFilter').value;


    const city =
        $('cityFilter').value;


    const rows =
        state.institutions.filter(
            institution => {

                const matchesSearch =

                    !search ||

                    `${institution.name}
                    ${institution.code}
                    ${institution.city}`
                        .toLowerCase()
                        .includes(search);


                const matchesType =

                    type === 'all' ||

                    institution.type === type;


                const matchesStatus =

                    status === 'all' ||

                    institution.status === status;


                const matchesCity =

                    city === 'all' ||

                    institution.city === city;


                return (

                    matchesSearch &&

                    matchesType &&

                    matchesStatus &&

                    matchesCity

                );

            }
        );


    $('institutionCount')
        .textContent =

        `${rows.length} result` +

        (
            rows.length !== 1
                ? 's'
                : ''
        );


    $('institutionTable').innerHTML =

        rows.map(institution => {

            const licenseCount =

                state.licenses.filter(
                    license =>
                        license.institutionId ===
                        institution.id
                ).length;


            const initials =

                institution.name
                    .split(' ')
                    .slice(0, 2)
                    .map(word => word[0])
                    .join('')
                    .toUpperCase();


            return `

<tr>
    <td>#${institution.id}</td>
    <td>
        <div class="institution-name">

                            <div class="institution-logo">
                                ${initials}
                            </div>

                            <div>

                                <strong>
                                    ${institution.name}
                                </strong>

                                <small>
                                    ${institution.city}
                                </small>

                            </div>

                        </div>

                    </td>


                    <td>
                        ${institution.type}
                    </td>


                    <td>
                        <strong>
                            ${institution.code}
                        </strong>
                    </td>


                    <td>
                        ${institution.city}
                    </td>


                    <td>

                        <span
                            class="status
                            ${institution.status.toLowerCase()}"
                        >
                            ${institution.status}
                        </span>

                    </td>


                    <td>
                        ${licenseCount}
                    </td>


                    <td>

                        <div class="row-actions">

                            <button
                                class="row-action"
                                onclick="
                                    editInstitution(
                                        ${institution.id}
                                    )
                                "
                            >
                                ✎
                            </button>

                            <button type="button" class="row-action ra" data-ra="1" data-c="indigo"
                                title="AI provider"
                                data-tip="AI provider"
                                aria-label="AI provider settings for institution ${institution.id}"
                                onclick="openInstitutionAiSettings(${institution.id})">
                                <svg viewBox="0 0 24 24" aria-hidden="true" style="width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round">
                                    <path d="M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1M7.7 16.3l-2.1 2.1"/>
                                    <circle cx="12" cy="12" r="4"/>
                                </svg>
                            </button>

                            <button
                                class="row-action"
                                onclick="
                                    viewInstitutionLicenses(
                                        ${institution.id}
                                    )
                                "
                            >
                                ◇
                            </button>

                            <button
                                class="row-action"
                                onclick="
                                    toggleInstitution(
                                        ${institution.id}
                                    )
                                "
                            >
                                ◉
                            </button>

                              <button
                                 class="row-action"
                                 title="Set request limit"
                                 onclick="
                                     manageLimit(
                                         ${institution.id}, '${institution.code}'
                                     )
                                 "
                             >
                                 ⏱
                             </button>
                              <button
                                 class="row-action"
                                 title="Delete institution and all its licenses"
                                 onclick="
                                     deleteInstitution(
                                         ${institution.id}
                                     )
                                 "
                             >
                                 🗑
                             </button>

                        </div>

                    </td>

                </tr>

            `;

        })
        .join('')

        ||

        `

            <tr>

                <td colspan="7">

                    <div class="empty">
                        No institutions match the filters.
                    </div>

                </td>

            </tr>

        `;

}


// =========================================================
// INSTITUTION MODAL
// =========================================================

function institutionFields(
    institution = {}
) {

    return `

        <div class="form-grid">

            <div class="form-group">

                <label>
                    Institution Name
                </label>

                <input
                    name="name"
                    value="${institution.name || ''}"
                    required
                >

            </div>


            <div class="form-group">

                <label>
                    Institution Code
                </label>

                <input
                    name="code"
                    value="${institution.code || ''}"
                    required
                >

            </div>

                <div class="form-group">
                <label>
                    Database Name
                </label>

                <input
                    name="db_name"
                    value="${institution.db_name || ''}"
                    placeholder="e.g. H022-KonnectLIS_Test"
                    required
                >

            </div>


            <div class="form-group">

                <label>
                    DB Server(host,port)
                </label>

                <input
                    name="db_server"
                    value="${institution.db_server || ''}"
                    placeholder="e.g. p2.athentech.in,52434"
                >

            </div>


            <div class="form-group">

                <label>
                    DB Username
                </label>

                <input
                    name="db_user"
                    value="${institution.db_user || ''}"
                    placeholder="e.g. readonly_user"
                >

            </div>


            <div class="form-group">

                <label>
                    DB Password
                </label>

                <input
                    name="db_password"
                    type="password"
                    value=""
                    placeholder="${institution.has_db_password ? '(saved — leave blank to keep)' : 'DB password'}"
                >

            </div>

            <div class="form-group" style="grid-column:1/-1">
                ${institution.id ? `
                <div style="display:flex;align-items:center;justify-content:space-between;gap:14px;border:1px solid var(--border,#e2e8f0);background:var(--surface-2,#f8fafc);border-radius:12px;padding:13px 14px">
                    <div style="min-width:0">
                        <strong style="display:block;font-size:12px">AI Provider &amp; API Key</strong>
                        <small style="display:block;margin-top:3px;color:var(--muted,#64748b);font-size:11px">
                            ${institution.has_llm_key ? `Configured · ${institution.llm_provider_count>1?`${institution.llm_provider_count} providers`:escapeAiText(institution.llm_provider || 'provider')}` : (institution.allow_athentech_fallback ? 'AthenTech AI fallback enabled by admin' : 'AI disabled · no key / no fallback consent')}
                        </small>
                    </div>
                    <button type="button" class="secondary-btn" onclick="openInstitutionAiSettings(${institution.id})"
                            aria-label="Manage institution AI settings">✨ AI Settings</button>
                </div>` : `
                <div style="border:1px dashed var(--border,#cbd5e1);border-radius:11px;padding:11px 14px;color:var(--muted,#64748b);font-size:11px">
                    ✨ AI Settings can be configured after creating the institution, using its AI button.
                </div>`}
            </div>


            <div class="form-group">

                <label>
                    Type
                </label>

                <select name="type">

                    ${
                        [
                            'Hospital',
                            'Medical College',
                            'Diagnostic',
                            'Pharmacy'
                        ]

                        .map(type => `

                            <option
                                ${
                                    institution.type === type
                                        ? 'selected'
                                        : ''
                                }
                            >
                                ${type}
                            </option>

                        `)
                        .join('')
                    }

                </select>

            </div>


            <div class="form-group">

                <label>
                    City
                </label>

                <input
                    name="city"
                    value="${institution.city || ''}"
                    required
                >

            </div>


            <div class="form-group">

                <label>
                    Status
                </label>

                <select name="status">

                    ${
                        [
                            'Active',
                            'Trial',
                            'Inactive'
                        ]

                        .map(status => `

                            <option
                                ${
                                    institution.status === status
                                        ? 'selected'
                                        : ''
                                }
                            >
                                ${status}
                            </option>

                        `)
                        .join('')
                    }

                </select>

            </div>

        </div>

    `;

}

async function openTokensModal() {
  const data = await loadOpenAIUsage();
  if (!data || !data.available) {
    toast(data?.reason || 'Could not load OpenAI usage');
    return;
  }

  let allQuotas = {};
  try {
    const res = await authFetch(`${API_BASE}/admin/all-quotas`);
    allQuotas = await res.json();
  } catch (err) {
    console.error(err);
  }

  const maxTokens = Math.max(...data.daily.map(d => d.total_tokens), 1);
  const CHART_MAX_PX = 80;
  const chartBars = data.daily.map(d => {
    const heightPx = Math.max(Math.round((d.total_tokens / maxTokens) * CHART_MAX_PX), 2);
    const date = new Date(d.start_time * 1000);
    const label = `${date.getMonth() + 1}/${date.getDate()}`;
    return `
      <div style="display:flex; flex-direction:column; align-items:center; flex:1; min-width:14px;">
        <div style="width:12px; height:${heightPx}px; background:#8B008B; border-radius:2px 2px 0 0;" title="${d.total_tokens.toLocaleString()} tokens"></div>
        <div style="font-size:9px; color:#94a3b8; margin-top:4px;">${label}</div>
      </div>
    `;
  }).join('');

  const dailyRows = data.daily.map(d => {
    const date = new Date(d.start_time * 1000).toLocaleDateString();
    return `<tr><td>${date}</td><td>${d.input_tokens.toLocaleString()}</td><td>${d.output_tokens.toLocaleString()}</td><td>${d.total_tokens.toLocaleString()}</td><td>${d.requests}</td></tr>`;
  }).join('');

  const providerCard = (name, icon, content) => `
    <div style="border:1px solid #e2e8f0; border-radius:10px; padding:14px; flex:1; min-width:180px;">
      <div style="font-size:12px; font-weight:700; color:#475569; margin-bottom:8px;">${icon} ${name}</div>
      ${content}
    </div>
  `;

  const groqContent = allQuotas.groq?.available
    ? `<div style="font-size:11px; color:#64748b;">TPM (per-minute)</div>
       <div style="background:#f1f5f9; border-radius:6px; height:6px; overflow:hidden; margin:4px 0;"><div style="width:${allQuotas.groq.tpm_pct_used}%; height:100%; background:${allQuotas.groq.tpm_pct_used > 90 ? '#dc2626' : allQuotas.groq.tpm_pct_used > 70 ? '#f59e0b' : '#22c55e'};"></div></div>
       <div style="font-size:11px;">${allQuotas.groq.tpm_remaining.toLocaleString()} / ${allQuotas.groq.tpm_limit.toLocaleString()} remaining</div>
       ${allQuotas.groq.rpd_limit ? `<div style="font-size:11px; color:#64748b; margin-top:8px;">Requests/day: ${allQuotas.groq.rpd_remaining.toLocaleString()} / ${allQuotas.groq.rpd_limit.toLocaleString()} left</div>` : ''}`
    : `<div style="font-size:11px; color:#94a3b8;">${allQuotas.groq?.reason || 'Unavailable'}</div>`;

  const openrouterContent = allQuotas.openrouter?.available
    ? `<div style="font-size:11px; color:#64748b;">${allQuotas.openrouter.is_free_tier ? 'Free tier' : 'Paid'}</div>
       <div style="font-size:11px;">Credits used: $${Number(allQuotas.openrouter.credits_used).toFixed(4)}</div>
       ${allQuotas.openrouter.credit_limit ? `<div style="font-size:11px;">Limit: $${allQuotas.openrouter.credit_limit}</div>` : '<div style="font-size:11px; color:#94a3b8;">No credit cap</div>'}
       <div style="font-size:11px; color:#64748b; margin-top:8px;">Rate: ${allQuotas.openrouter.rate_limit_requests} req / ${allQuotas.openrouter.rate_limit_interval}</div>`
    : `<div style="font-size:11px; color:#94a3b8;">${allQuotas.openrouter?.reason || 'Unavailable'}</div>`;


  openModal('TOKENS', 'AI Provider Usage', `
    <div style="max-height:70vh; overflow-y:auto;">
      <div style="font-size:12px; font-weight:700; color:#475569; margin-bottom:10px;">OpenAI (last 30 days)</div>
      <div style="display:flex; gap:16px; margin-bottom:20px; flex-wrap:wrap;">
        <div><div style="font-size:11px; color:#64748b;">TOTAL TOKENS</div><strong>${data.total_tokens.toLocaleString()}</strong></div>
        <div><div style="font-size:11px; color:#64748b;">INPUT</div><strong>${data.total_input_tokens.toLocaleString()}</strong></div>
        <div><div style="font-size:11px; color:#64748b;">OUTPUT</div><strong>${data.total_output_tokens.toLocaleString()}</strong></div>
        <div><div style="font-size:11px; color:#64748b;">REQUESTS</div><strong>${data.total_requests.toLocaleString()}</strong></div>
        <div><div style="font-size:11px; color:#64748b;">SPEND (USD)</div><strong>${data.total_usd != null ? '$' + data.total_usd.toFixed(2) : 'N/A'}</strong></div>
      </div>
      <div style="display:flex; align-items:flex-end; gap:2px; height:${CHART_MAX_PX}px; border-bottom:1px solid #e2e8f0; padding-bottom:4px; margin-bottom:20px; overflow-x:auto;">
        ${chartBars}
      </div>

      <div style="font-size:12px; font-weight:700; color:#475569; margin-bottom:10px;">Free-tier providers (live)</div>
      <div style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px;">
        ${providerCard('Groq', '⚡', groqContent)}
        ${providerCard('OpenRouter', '🔀', openrouterContent)}
      </div>

      <table style="width:100%; font-size:12px;">
        <thead><tr><th>Date</th><th>Input</th><th>Output</th><th>Total</th><th>Requests</th></tr></thead>
        <tbody>${dailyRows}</tbody>
      </table>
    </div>
  `, null);
}

// ---- Multi-provider institution AI workspace ----
// The first provider slot always exists. Others are opt-in, independently
// enabled, and collapsible. Keys are write-only, stored encrypted by backend.
function escapeAiText(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));
}
const aiEl = id => document.getElementById(id);
let _institutionAiId = null;
let _institutionAiReady = false;
let _institutionAiBusy = false;
let _institutionAiSlots = [];
let _institutionAiCatalog = [];
let _institutionAiExpanded = 1;

function aiFeedback(text, kind = '') {
  const e = aiEl('institutionAiResult');
  if (!e) return;
  e.textContent = text || '';
  e.dataset.kind = kind;
}
function aiValidationMessage(data, fallback) {
  if (!data || typeof data !== 'object') return fallback;
  const parts = [data.message || data.detail || fallback];
  if (data.http_status) parts.push('Provider HTTP ' + data.http_status);
  if (data.detail && data.message) parts.push(data.detail);
  return parts.filter(Boolean).join(' · ');
}
function aiBusy(busy) {
  _institutionAiBusy = Boolean(busy);
  const panel = aiEl('institutionAiOverlay');
  panel?.classList.toggle('busy', _institutionAiBusy);
  ['institutionAiSave','institutionAiAdd','institutionAiFallback'].forEach(id => {
    const item = aiEl(id); if (item) item.disabled = busy || !_institutionAiReady;
  });
  panel?.querySelectorAll('.ai-slot-area button, .ai-slot-area input, .ai-slot-area select').forEach(e => {
    e.disabled = busy || !_institutionAiReady || (e.dataset.primary === 'mandatory');
  });
}
function ensureInstitutionAiDialog() {
  if (aiEl('institutionAiOverlay')) return;
  const style = document.createElement('style');
  style.id = 'institutionAiStyles';
  style.textContent = `
  #institutionAiOverlay {position:fixed;inset:0;z-index:450;display:none;align-items:center;justify-content:center;
    background:rgba(10,18,33,.58);backdrop-filter:blur(8px);padding:20px}
  #institutionAiOverlay.open {display:flex;animation:aiFade .19s ease}
  @keyframes aiFade {from{opacity:0}to{opacity:1}}
  #institutionAiOverlay [hidden] {display:none!important}
  #institutionAiOverlay .ai-window{width:min(720px,100%);max-height:calc(100vh - 40px);display:flex;flex-direction:column;
    border:1px solid var(--border,#e2e8f0);border-radius:22px;background:var(--surface,#fff);
    color:var(--text,#1f2937);box-shadow:0 32px 95px rgba(9,22,40,.28);overflow:hidden;
    animation:aiIn .24s cubic-bezier(.2,.75,.2,1)}
  @keyframes aiIn{from{transform:translateY(9px) scale(.986)}to{transform:none}}
  #institutionAiOverlay .ai-head{display:flex;gap:16px;align-items:center;justify-content:space-between;
    padding:23px 27px 21px;border-bottom:1px solid var(--border,#e2e8f0)}
  #institutionAiOverlay .ai-eyebrow{font-size:10px;letter-spacing:.13em;font-weight:750;color:var(--muted,#64748b)}
  #institutionAiOverlay h2{font-size:22px;line-height:1.25;margin:6px 0 5px;color:var(--ink,#111827);letter-spacing:-.03em}
  #institutionAiOverlay .ai-muted{color:var(--muted,#64748b);font-size:12px;line-height:1.6}
  #institutionAiOverlay .ai-exit{border:1px solid var(--border,#e2e8f0);border-radius:50%;background:transparent;
    color:var(--muted,#64748b);width:32px;height:32px;display:grid;place-items:center;font-size:21px;cursor:pointer}
  #institutionAiOverlay .ai-scroll{overflow-y:auto;min-height:0;overscroll-behavior:contain;padding:22px 27px 25px}
  #institutionAiOverlay .ai-summary{padding:12px 14px;border-radius:11px;background:var(--surface-2,#f8fafc);
    color:var(--muted,#475569);font-size:12px;border:1px solid var(--border,#e2e8f0);line-height:1.5;margin-bottom:22px}
  #institutionAiOverlay .ai-section-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:6px}
  #institutionAiOverlay .ai-section-title strong{font-size:14px;letter-spacing:-.012em;color:var(--ink,#111827)}
  #institutionAiOverlay .ai-slot-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:14px 0 17px}
  #institutionAiOverlay .ai-slot-chip{display:inline-flex;gap:9px;align-items:center;padding:10px 13px;border-radius:11px;
    cursor:pointer;border:1px solid var(--border,#e2e8f0);background:var(--surface,#fff);font-size:12px;font-weight:700;
    color:var(--text,#334155);transition:background .16s,border-color .16s;user-select:none}
  #institutionAiOverlay .ai-slot-chip.is-on{border-color:var(--primary,#635bce);background:color-mix(in srgb,var(--primary,#635bce) 7%,var(--surface,#fff))}
  #institutionAiOverlay .ai-slot-chip input{accent-color:var(--primary,#635bce);width:15px;height:15px;margin:0;cursor:pointer}
  #institutionAiOverlay .ai-slot-chip input:disabled{cursor:not-allowed;opacity:1}
  #institutionAiOverlay .ai-slot-chip small{font-size:10px;color:var(--muted,#64748b);font-weight:500}
  #institutionAiOverlay button.ai-add{border:1px dashed var(--border,#cbd5e1);border-radius:11px;padding:10px 13px;
    color:var(--primary,#635bce);font-size:12px;font-weight:700;background:transparent;cursor:pointer}
  #institutionAiOverlay .ai-panels{display:grid;gap:10px}
  #institutionAiOverlay details.ai-provider{border:1px solid var(--border,#e2e8f0);border-radius:13px;background:var(--surface,#fff);
    overflow:hidden;transition:border-color .18s}
  #institutionAiOverlay details.ai-provider[open]{border-color:color-mix(in srgb,var(--primary,#635bce) 35%,var(--border,#e2e8f0))}
  #institutionAiOverlay details.ai-provider > summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:12px;
    padding:14px 15px;min-height:40px}
  #institutionAiOverlay details.ai-provider > summary::-webkit-details-marker{display:none}
  #institutionAiOverlay .ai-slot-num{flex:0 0 31px;height:31px;border:1px solid var(--border,#e2e8f0);border-radius:9px;
    display:grid;place-items:center;color:var(--muted,#64748b);font-weight:750;font-size:12px}
  #institutionAiOverlay .ai-slot-copy{min-width:0;flex:1}
  #institutionAiOverlay .ai-slot-copy strong{font-size:12px;display:block;color:var(--ink,#111827)}
  #institutionAiOverlay .ai-slot-copy span{font-size:11px;color:var(--muted,#64748b);display:block;margin-top:2px}
  #institutionAiOverlay .ai-status-pill{font-size:10px;font-weight:750;border-radius:15px;padding:4px 8px;
    background:var(--surface-2,#f1f5f9);color:var(--muted,#64748b);white-space:nowrap}
  #institutionAiOverlay .ai-status-pill.good{background:#e9f8ef;color:#147444}
  #institutionAiOverlay .ai-status-pill.off{background:var(--surface-2,#f1f5f9);color:var(--muted,#64748b)}
  #institutionAiOverlay .ai-chevron{color:var(--muted,#94a3b8);font-size:18px;transition:transform .2s}
  #institutionAiOverlay details[open] .ai-chevron{transform:rotate(180deg)}
  #institutionAiOverlay .ai-panel-body{padding:17px 17px 15px;border-top:1px solid var(--border,#e2e8f0);display:grid;gap:15px}
  #institutionAiOverlay .ai-field{display:grid;gap:6px;min-width:0}
  #institutionAiOverlay .ai-field label{font-size:12px;font-weight:650;color:var(--text,#334155)}
  #institutionAiOverlay .ai-field input,#institutionAiOverlay .ai-field select{box-sizing:border-box;width:100%;height:42px;
    padding:9px 12px;border:1px solid var(--border,#cbd5e1);border-radius:10px;font-size:13px;
    background:var(--surface,#fff);color:var(--ink,#111827)}
  #institutionAiOverlay .ai-field input:focus,#institutionAiOverlay .ai-field select:focus{
    outline:2px solid var(--primary,#635bce);outline-offset:1px}
  #institutionAiOverlay .ai-row2{display:grid;grid-template-columns:1fr 1fr;gap:13px}
  #institutionAiOverlay .ai-provider-actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
  #institutionAiOverlay .ai-lite{border:1px solid var(--border,#cbd5e1);color:var(--text,#334155);
    background:var(--surface,#fff);padding:8px 11px;border-radius:9px;font-size:11px;font-weight:650;cursor:pointer}
  #institutionAiOverlay .ai-lite.danger{color:#c03940;border-color:#f7c6cc}
  #institutionAiOverlay .ai-mini-state{font-size:11px;color:var(--muted,#64748b);line-height:1.5}
  #institutionAiOverlay .ai-toggle-row{display:flex;gap:16px;align-items:center;justify-content:space-between;
    margin-top:22px;border-radius:14px;border:1px solid var(--border,#e2e8f0);
    padding:18px;background:var(--surface-2,#f8fafc)}
  #institutionAiOverlay .ai-toggle-row strong{display:block;font-size:13px;color:var(--ink,#111827);margin-bottom:4px}
  #institutionAiOverlay .ai-switch{position:relative;display:block;width:42px;height:24px;flex-shrink:0}
  #institutionAiOverlay .ai-switch input{opacity:0;width:100%;height:100%;position:absolute;inset:0;cursor:pointer;z-index:2}
  #institutionAiOverlay .ai-track{position:absolute;inset:0;border-radius:20px;background:#cbd5e1;transition:background .18s}
  #institutionAiOverlay .ai-track:after{content:"";position:absolute;top:3px;left:3px;width:18px;height:18px;
    background:#fff;border-radius:50%;transition:transform .18s;box-shadow:0 1px 4px #0002}
  #institutionAiOverlay .ai-switch input:checked + .ai-track{background:var(--primary,#635bce)}
  #institutionAiOverlay .ai-switch input:checked + .ai-track:after{transform:translateX(18px)}
  #institutionAiOverlay .ai-switch input:focus-visible + .ai-track{outline:2px solid var(--primary,#635bce);outline-offset:3px}
  #institutionAiOverlay .ai-result{font-size:12px;line-height:1.6;white-space:pre-line;min-height:17px;margin-top:14px;color:var(--muted,#64748b)}
  #institutionAiOverlay .ai-result[data-kind="success"]{color:#15803d}
  #institutionAiOverlay .ai-result[data-kind="error"]{color:#cc3e45}
  #institutionAiOverlay .ai-footer{border-top:1px solid var(--border,#e2e8f0);padding:14px 27px;
    display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--surface,#fff)}
  #institutionAiOverlay .ai-footnote{font-size:11px;color:var(--muted,#64748b)}
  #institutionAiOverlay .ai-footer-buttons{display:flex;gap:9px}
  #institutionAiOverlay .ai-footer button{border-radius:9px;font-size:12px;font-weight:700;padding:10px 15px;cursor:pointer}
  #institutionAiOverlay .ai-footer .ai-save{border:1px solid var(--primary,#635bce);background:var(--primary,#635bce);color:white}
  #institutionAiOverlay .ai-footer .ai-cancel{border:1px solid var(--border,#cbd5e1);background:transparent;color:var(--text,#334155)}
  #institutionAiOverlay.busy button{opacity:.68;cursor:wait}
  @media(max-width:570px){#institutionAiOverlay{padding:8px}#institutionAiOverlay .ai-window{max-height:calc(100vh - 16px)}
    #institutionAiOverlay .ai-head{padding:18px}#institutionAiOverlay .ai-scroll{padding:16px}
    #institutionAiOverlay .ai-row2{grid-template-columns:1fr}#institutionAiOverlay .ai-footer{padding:14px 16px}
    #institutionAiOverlay .ai-footnote{display:none}}
  `;
  document.head.appendChild(style);
  const overlay = document.createElement('div');
  overlay.id = 'institutionAiOverlay';
  overlay.innerHTML = `
   <section class="ai-window" role="dialog" aria-modal="true" aria-labelledby="institutionAiTitle">
    <header class="ai-head"><div><div class="ai-eyebrow">INSTITUTION  /  AI CONFIGURATION</div>
      <h2 id="institutionAiTitle">AI Providers</h2>
      <div class="ai-muted" id="institutionAiSub"></div></div>
      <button type="button" class="ai-exit" id="institutionAiClose" aria-label="Close dialog">×</button></header>
    <div class="ai-scroll"><div class="ai-summary" id="institutionAiStatus">Loading configuration…</div>
     <div class="ai-section-title"><strong>Provider slots</strong><span class="ai-muted">Priority: 1 → 2 → 3 → ...</span></div>
     <div class="ai-muted">Provider 1 is required. Check more slots to enable them. Expand a card to configure its key.</div>
     <div class="ai-slot-area"><div class="ai-slot-bar" id="institutionAiSlotBar"></div>
       <div class="ai-panels" id="institutionAiPanels"></div></div>
     <div class="ai-toggle-row"><div><strong>Allow AthenTech AI fallback</strong>
       <div class="ai-muted">Optional · Off by default. Used <b>only when no institution provider is enabled with a key</b>.
       A failing or exhausted institution key never switches to AthenTech automatically.</div></div>
       <label class="ai-switch" title="Explicitly allow AthenTech AI when no client key is configured">
         <input id="institutionAiFallback" type="checkbox" aria-label="Allow AthenTech AI fallback"/><span class="ai-track"></span></label></div>
     <div class="ai-result" id="institutionAiResult" role="status" aria-live="polite"></div>
    </div>
    <footer class="ai-footer"><div class="ai-footnote">Keys are encrypted · Client databases untouched</div>
     <div class="ai-footer-buttons"><button type="button" class="ai-cancel" id="institutionAiCancel">Cancel</button>
     <button type="button" class="ai-save" id="institutionAiSave">Save settings</button></div></footer>
   </section>`;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', e => {if(e.target===overlay) closeInstitutionAiSettings();});
  aiEl('institutionAiClose').onclick = closeInstitutionAiSettings;
  aiEl('institutionAiCancel').onclick = closeInstitutionAiSettings;
  aiEl('institutionAiSave').onclick = saveInstitutionAiSettings;
  overlay.addEventListener('change', onInstitutionAiChange);
  overlay.addEventListener('input', onInstitutionAiInput);
  overlay.addEventListener('click', onInstitutionAiClick);
  overlay.addEventListener('toggle', e => {
    if (e.target?.matches?.('details.ai-provider') && e.target.open) _institutionAiExpanded = Number(e.target.dataset.position);
  }, true);
  document.addEventListener('keydown', e => {
    if (e.key==='Escape' && aiEl('institutionAiOverlay')?.classList.contains('open')) {
      e.stopPropagation(); closeInstitutionAiSettings();
    }
  });
}

function makeEmptyAiSlot(position) {
  return {position,enabled:position===1,provider:'',model:'',base_url:'',key_status:'not_configured',
          has_key:false,clear_key:false,new_key:'',legacy:false};
}
function aiSlotLabel(slot) {
  const info = _institutionAiCatalog.find(p => p.id === slot.provider);
  return info?.label || slot.provider || 'Not configured';
}
function renderInstitutionAiSlots() {
  const bar = aiEl('institutionAiSlotBar');
  const panels = aiEl('institutionAiPanels');
  if (!bar || !panels) return;
  bar.innerHTML = _institutionAiSlots.map((s,i) => `
    <label class="ai-slot-chip ${s.enabled?'is-on':''}" title="${i===0?'Required primary provider':'Enable / disable this provider'}">
      <input type="checkbox" data-ai-enabled="${i}" ${s.enabled?'checked':''}
        ${i===0?'disabled data-primary="mandatory"':''} aria-label="Enable provider ${i+1}"/>
      <span>${i+1}${i===0?'<small> · required</small>':''}</span>
    </label>`).join('') + `<button id="institutionAiAdd" type="button" class="ai-add" data-ai-action="add"
      ${_institutionAiSlots.length>=25?'disabled':''}>＋ Add provider</button>`;
  panels.innerHTML = _institutionAiSlots.map((s,i) => {
    const opts = _institutionAiCatalog.map(p => `<option value="${escapeAiText(p.id)}" ${p.id===s.provider?'selected':''}
      ${p.disabled?'disabled':''}>${escapeAiText(p.label)}${p.disabled?' (unavailable)':''}</option>`).join('');
    const fallbackModel = _institutionAiCatalog.find(p => p.id===s.provider)?.default_model || 'Provider default';
    const local = s.provider === 'ollama_local';
    const status = local ? 'Local model · no API key' : s.clear_key ? 'Will remove key' : s.new_key ? 'New key entered' : s.has_key ? (s.key_status==='valid'?'Verified key saved':'Saved key · '+s.key_status) : 'No key yet';
    const state = !s.enabled ? 'Disabled' : local || s.has_key || s.new_key ? 'Configured' : 'Set up';
    return `<details class="ai-provider" data-position="${i+1}" ${_institutionAiExpanded===i+1?'open':''}>
       <summary><div class="ai-slot-num">${String(i+1).padStart(2,'0')}</div>
         <div class="ai-slot-copy"><strong>Provider ${i+1} · ${escapeAiText(aiSlotLabel(s))}</strong>
           <span>${escapeAiText(status)}</span></div>
         <span class="ai-status-pill ${s.enabled&&(local||s.has_key||s.new_key)?'good':(!s.enabled?'off':'')}">${escapeAiText(state)}</span>
         <span class="ai-chevron" aria-hidden="true">⌄</span></summary>
       <div class="ai-panel-body">
         <div class="ai-field"><label for="aiProvider${i}">Provider</label>
           <select id="aiProvider${i}" data-ai-field="provider" data-index="${i}">
             <option value="">Choose a provider…</option>${opts}</select></div>
         <div class="ai-row2"><div class="ai-field"><label for="aiModel${i}">Model <span class="ai-muted">(optional)</span></label>
             <input id="aiModel${i}" data-ai-field="model" data-index="${i}" spellcheck="false"
                value="${escapeAiText(s.model)}" placeholder="${escapeAiText(fallbackModel)}"/></div>
           <div class="ai-field" data-ai-url-wrap="${i}" ${s.provider!=='custom'?'hidden':''}>
             <label for="aiUrl${i}">Custom HTTPS URL</label><input id="aiUrl${i}" data-ai-field="base_url" data-index="${i}"
               value="${escapeAiText(s.base_url)}" placeholder="https://api.example.com/v1" spellcheck="false"/></div></div>
         <div class="ai-field" ${local?'hidden':''}><label for="aiKey${i}">API key</label>
           <input id="aiKey${i}" data-ai-field="new_key" data-index="${i}" type="password"
             autocomplete="new-password" placeholder="${s.has_key?'•••••••• (saved — leave blank to keep)':'Paste API key'}" spellcheck="false"/>
           <div class="ai-muted">Saved keys are never shown. New keys are tested before saving.</div></div>
         <div class="ai-provider-actions">
           ${local ? `<button type="button" class="ai-lite" data-ai-action="recheck" data-index="${i}">Check local model</button>` : `<button type="button" class="ai-lite" data-ai-action="test" data-index="${i}">Test new key</button>`}
           ${!local&&s.has_key&&!s.clear_key?`<button type="button" class="ai-lite" data-ai-action="recheck" data-index="${i}">Recheck saved</button>
              <button type="button" class="ai-lite danger" data-ai-action="clear" data-index="${i}">Remove key</button>`:''}
           ${i>=3&&i===_institutionAiSlots.length-1?`<button type="button" class="ai-lite danger" data-ai-action="remove" data-index="${i}">Remove slot</button>`:''}
         </div>
         <div class="ai-mini-state" id="aiSlotResult${i}" role="status" aria-live="polite"></div>
       </div></details>`;
  }).join('');
  if (_institutionAiBusy || !_institutionAiReady) aiBusy(_institutionAiBusy);
}
function onInstitutionAiInput(e) {
  const el=e.target, i=Number(el.dataset.index), field=el.dataset.aiField;
  if (!field || !_institutionAiSlots[i]) return;
  _institutionAiSlots[i][field] = el.value;
  if (field==='new_key' && el.value) _institutionAiSlots[i].clear_key=false;
}
function onInstitutionAiChange(e) {
  const el=e.target;
  if (el.dataset.aiEnabled!==undefined) {
    const i=Number(el.dataset.aiEnabled);if(i===0){el.checked=true;return;}
    _institutionAiSlots[i].enabled=el.checked;
    if (el.checked) _institutionAiExpanded=i+1;
    renderInstitutionAiSlots();
  }
  if (el.dataset.aiField==='provider') {
    const i=Number(el.dataset.index), s=_institutionAiSlots[i];
    s.provider=el.value;s.model='';s.base_url='';s.new_key='';
    // A saved key cannot be reassigned to another provider without replacing it.
    if (s.has_key) { s.clear_key=true; s.has_key=false; }
    _institutionAiExpanded=i+1;
    renderInstitutionAiSlots();
    aiFeedback(s.provider==='ollama_local'?'Local Ollama needs no API key. Enable only for approved institutions.':'Changing a provider requires a new API key.', '');
  }
}
async function aiProviderCall(endpoint, method='POST', body=undefined) {
  const r=await authFetch(`${API_BASE}${endpoint}`,{
    method, ...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  });
  const data=await r.json().catch(()=>({}));
  return {ok:r.ok&&data.status==='success'&&data.ok!==false,data};
}
async function onInstitutionAiClick(e) {
  const button=e.target.closest('[data-ai-action]');
  if (!button || _institutionAiBusy) return;
  const action=button.dataset.aiAction, i=Number(button.dataset.index);
  if(action==='add') {
    if(_institutionAiSlots.length>=25) return aiFeedback('Maximum 25 provider slots.','error');
    _institutionAiSlots.push(makeEmptyAiSlot(_institutionAiSlots.length+1));
    _institutionAiExpanded=_institutionAiSlots.length;
    renderInstitutionAiSlots();return;
  }
  const slot=_institutionAiSlots[i];if(!slot) return;
  if(action==='remove') {
    if(i<3||i!==_institutionAiSlots.length-1) return;
    if(slot.has_key&&!confirm('Remove this provider slot and its saved key when you save?')) return;
    _institutionAiSlots.pop();_institutionAiExpanded=Math.min(i,3);
    renderInstitutionAiSlots();return;
  }
  if(action==='clear') {
    if(!confirm('Remove only Provider '+(i+1)+' saved key when you save?')) return;
    slot.clear_key=true;slot.has_key=false;slot.new_key='';
    _institutionAiExpanded=i+1;renderInstitutionAiSlots();
    aiFeedback('Key will be removed when you click Save settings.','');return;
  }
  if(action==='test' || action==='recheck') {
    if(!_institutionAiReady) return;
    if(action==='test'&&(!slot.provider||!slot.new_key.trim())) {
      aiFeedback('Select a provider and enter a new key in Provider '+(i+1)+'.','error');return;
    }
    aiBusy(true);aiFeedback('Checking Provider '+(i+1)+'…');
    try {
      const {ok,data}=action==='test'
       ?await aiProviderCall('/admin/llm-providers/validate','POST',{
          provider:slot.provider,model:slot.model||null,api_key:slot.new_key.trim(),
          base_url:slot.provider==='custom'?slot.base_url||null:null})
       :await aiProviderCall(`/admin/institutions/${_institutionAiId}/ai-providers/${i+1}/revalidate`);
      const msg=aiValidationMessage(data,ok?'Validated successfully.':'Verification failed.');
      aiFeedback('Provider '+(i+1)+': '+msg,ok?'success':'error');
      if(ok){slot.key_status='valid';if(action==='recheck'&&slot.provider!=='ollama_local')slot.has_key=true;}
    } catch(err){aiFeedback('Cannot reach the provider-validation service. Check network connectivity.','error');}
    finally{aiBusy(false);}
  }
}
function closeInstitutionAiSettings() {
  if (_institutionAiBusy) return;
  aiEl('institutionAiOverlay')?.classList.remove('open');
  _institutionAiSlots.forEach(s => {s.new_key='';});
  _institutionAiId=null;
}
async function openInstitutionAiSettings(id) {
  const institution=inst(id);
  if(!institution) return toast('Institution not found. Refresh the registry.');
  ensureInstitutionAiDialog();
  if(_institutionAiBusy)return;
  _institutionAiId=Number(id); _institutionAiReady=false; _institutionAiExpanded=1;
  aiEl('institutionAiOverlay').classList.add('open');
  aiEl('institutionAiSub').textContent=institution.name+' · '+institution.code;
  aiEl('institutionAiStatus').textContent='Loading saved institution settings…';
  aiEl('institutionAiFallback').checked=!!institution.allow_athentech_fallback;
  aiFeedback('');
  _institutionAiSlots=[makeEmptyAiSlot(1),makeEmptyAiSlot(2),makeEmptyAiSlot(3)];
  renderInstitutionAiSlots();aiBusy(false);
  try {
    const [catalogResponse,settingsResponse]=await Promise.all([
      authFetch(`${API_BASE}/admin/llm-providers`),
      authFetch(`${API_BASE}/admin/institutions/${id}/ai-providers`)
    ]);
    const catalog=await catalogResponse.json(),settings=await settingsResponse.json();
    if(_institutionAiId!==Number(id))return;
    if(!catalogResponse.ok || !settingsResponse.ok || catalog.status!=='success'||settings.status!=='success')
       throw new Error(settings.message||'AI provider settings could not be loaded');
    _institutionAiCatalog=catalog.providers||[];
    _institutionAiReady=!!catalog.byok_ready;
    _institutionAiSlots=(settings.slots||[]).map(s=>({...makeEmptyAiSlot(s.position),...s,new_key:'',clear_key:false}));
    while(_institutionAiSlots.length<3)_institutionAiSlots.push(makeEmptyAiSlot(_institutionAiSlots.length+1));
    _institutionAiSlots[0].enabled=true;
    aiEl('institutionAiFallback').checked=!!settings.allow_athentech_fallback;
    const n=_institutionAiSlots.filter(s=>s.enabled&&(s.has_key||s.provider==='ollama_local')).length;
    aiEl('institutionAiStatus').textContent=n
      ?`${n} enabled institution provider${n===1?'':'s'} · Uses client's own credentials`
      :(settings.allow_athentech_fallback?'No client key · AthenTech AI explicitly allowed':'No client key · AI disabled until a key is saved or fallback is enabled');
    renderInstitutionAiSlots();aiBusy(false);
    if(!_institutionAiReady)aiFeedback('AI-key storage is unavailable. Nothing can be saved.','error');
  } catch(error) {
    _institutionAiReady=false;aiBusy(false);
    aiFeedback('Could not load AI settings: '+(error.message||'server unreachable'),'error');
  }
}
window.openInstitutionAiSettings=openInstitutionAiSettings;

async function saveInstitutionAiSettings() {
  if(!_institutionAiReady||_institutionAiBusy||_institutionAiId===null)return;
  const slots=_institutionAiSlots.map((s,i)=>({
    position:i+1,enabled:i===0?true:!!s.enabled,
    provider:s.provider,model:s.model,base_url:s.provider==='custom'?s.base_url:'',
    ...(s.new_key.trim()?{api_key:s.new_key.trim()}:{}),
    ...(s.clear_key?{clear_key:true}:{})
  }));
  // The UI's primary checkbox is intentionally locked ON. The primary key
  // itself is optional only when AI should remain disabled or consent is ON.
  for(const [i,s] of slots.entries()) {
    if(s.enabled&&i>0&&s.provider!=='ollama_local'&&!s.api_key&&!_institutionAiSlots[i].has_key) {
      aiFeedback(`Provider ${i+1} is enabled but has no key. Enter one or uncheck it.`,'error');
      _institutionAiExpanded=i+1;renderInstitutionAiSlots();return;
    }
  }
  aiBusy(true);aiFeedback('Validating and saving settings securely…');
  try {
    const {ok,data}=await aiProviderCall(`/admin/institutions/${_institutionAiId}/ai-providers`,'PUT',{
      slots,allow_athentech_fallback:!!aiEl('institutionAiFallback').checked
    });
    if(!ok){aiFeedback(data.message||'Save failed; previous settings remain unchanged.','error');return;}
    _institutionAiSlots=(data.slots||[]).map(s=>({...makeEmptyAiSlot(s.position),...s,new_key:'',clear_key:false}));
    while(_institutionAiSlots.length<3)_institutionAiSlots.push(makeEmptyAiSlot(_institutionAiSlots.length+1));
    _institutionAiSlots[0].enabled=true;
    const n=_institutionAiSlots.filter(s=>s.enabled&&(s.has_key||s.provider==='ollama_local')).length;
    aiEl('institutionAiStatus').textContent=`${n} enabled client provider${n===1?'':'s'} · ${data.allow_athentech_fallback?'Shared fallback permitted only with no client keys':'No AthenTech shared fallback'}`;
    renderInstitutionAiSlots();
    aiFeedback('Saved successfully · provider order, enabled keys and fallback preference updated.','success');
    try{await loadInstitutionsFromAPI();renderInstitutions();}catch(_e){/* successful write remains successful */}
    toast('AI provider settings saved');
  } catch(error){aiFeedback('The server could not save these settings. Previous settings remain unchanged.','error');}
  finally{aiBusy(false);}
}

function openInstitution(
    institution = null
) {

    openModal(

        'INSTITUTION',

        institution
            ? 'Edit Institution'
            : 'Add Institution',

        institutionFields(
            institution || {}
        ),

        data => {

            if (institution) {
                // Now wired to the real PATCH endpoint.
                (async () => {
                    try {
                        const res = await authFetch(`${API_BASE}/admin/institutions/${institution.id}`, {
                            method: 'PATCH',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                name: data.name.trim(),
                                client_prefix: data.code.trim().toUpperCase(),
                                db_name: data.db_name.trim(),
                                db_server: data.db_server || null,
                                db_user: data.db_user || null,
                                db_password: data.db_password || null,
                                type: data.type,
                                city: data.city.trim(),
                                status: data.status,
                                
                            }),
                        });
                        const result = await res.json();

                        if (!res.ok || result.status !== 'success') {
                            toast(result.message || 'Failed to update institution');
                            return;
                        }

                        addActivity('Institution updated', `${data.name.trim()} was updated`);
                        toast('Institution updated');
                        closeModal();

                        await loadInstitutionsFromAPI();
                        renderInstitutions();
                        renderDashboard();
                    } catch (err) {
                        console.error(err);
                        toast('Could not reach the server to update the institution');
                    }
                })();
                return;
            }

            // Create: call the real backend so this institution actually
            // exists in licenses.db and can be used for license generation.
            (async () => {
                try {
                    const res = await authFetch(`${API_BASE}/admin/institutions`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: data.name.trim(),
                            client_prefix: data.code.trim().toUpperCase(),
                            db_name: data.db_name.trim(),
                            db_server: data.db_server || null,
                            db_user: data.db_user || null,
                            db_password: data.db_password || null,
                            type: data.type,
                            city: data.city.trim(),
                            status: data.status,
                            
                        }),
                    });
                    const result = await res.json();

                    if (!res.ok || result.status !== 'success') {
                        toast(result.message || 'Failed to create institution');
                        return;
                    }

                    addActivity('Institution registered', `${data.name.trim()} was added`);
                    toast('Institution added');
                    closeModal();

                    await loadInstitutionsFromAPI();
                    renderInstitutions();
                    renderDashboard();
                } catch (err) {
                    console.error(err);
                    toast('Could not reach the server to create the institution');
                }
            })();
        }
    );
}
window.editInstitution =
    id => {
        openInstitution(inst(id) );
    };
window.toggleInstitution =
    id => {
        const institution = inst(id);
        const newStatus = institution.status === 'Inactive' ? 'Active' : 'Inactive';

        (async () => {
            try {
                const res = await authFetch(`${API_BASE}/admin/institutions/${id}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: newStatus }),
                });
                const result = await res.json();

                if (!res.ok || result.status !== 'success') {
                    toast(result.message || 'Failed to update status');
                    return;
                }

                await loadInstitutionsFromAPI();
                addActivity(
                    newStatus === 'Active' ? 'Institution activated' : 'Institution deactivated',
                    institution.name
                );
                renderInstitutions();
                renderDashboard();
                toast(`${institution.name} is ${newStatus}`);
            } catch (err) {
                console.error(err);
                toast('Could not reach the server to update status');
            }
        })();
    };
window.deleteInstitution =
    id => {
        const institution = inst(id);
        if (!institution) return;

        const licenseCount = state.licenses.filter(l => l.institutionId === id).length;
        const warning = licenseCount > 0
            ? `Delete "${institution.name}" AND its ${licenseCount} license(s)? This cannot be undone.`
            : `Delete "${institution.name}"? This cannot be undone.`;

        if (!confirm(warning)) return;

        (async () => {
            try {
                const res = await authFetch(`${API_BASE}/admin/institutions/${id}`, {
                    method: 'DELETE',
                });
                const result = await res.json();

                if (!res.ok || result.status !== 'success') {
                    toast(result.message || 'Failed to delete institution');
                    return;
                }

                addActivity('Institution deleted', `${institution.name} and ${result.deleted.licenses_removed} license(s) removed`);
                await loadInstitutionsFromAPI();
                await loadLicensesFromAPI();
                renderInstitutions();
                renderLicenses();
                renderDashboard();
                toast(`${institution.name} deleted`);
            } catch (err) {
                console.error(err);
                toast('Could not reach the server to delete the institution');
            }
        })();
    };
window.viewInstitutionLicenses =
    id => {
        const institution =
            inst(id);
        const count =
            state.licenses.filter(
                license =>
                    license.institutionId ===
                    id
            ).length;
        toast(
            `${institution.name}: ` +
            `${count} license` +
            (
                count !== 1
                    ? 's'
                    : ''
            )
        );
    };
// =========================================================
// LICENSE MANAGEMENT
// =========================================================
function renderLicenses() {
    fillSelect(
        'licenseInstitutionFilter',
        state.institutions.map(
            institution =>
                String(institution.id)
        ),
        'Institution'
    );
    const institutionSelect =
        $('licenseInstitutionFilter');
    [...institutionSelect.options]
        .forEach(option => {
            if (option.value !== 'all') {
                const institution =
                    inst(option.value);
                option.textContent =
                    institution?.name ||
                    option.value;
            }
        });
    fillSelect(
        'licenseRoleFilter',
        roles,
        'Role'
    );
    const search =
        $('licenseSearch')
            .value
            .toLowerCase();
    const institution =
        institutionSelect.value;
    const role =
        $('licenseRoleFilter').value;
    const status =
        $('licenseStatusFilter').value;
    const plan =
        $('licensePlanFilter').value;
    const rows =
        state.licenses.filter(
            license => {

                const matchesSearch =

                    !search ||

                    `${license.code}
                    ${inst(license.institutionId)?.name}
                    ${license.role}`
                        .toLowerCase()
                        .includes(search);


                const matchesInstitution =

                    institution === 'all' ||

                    String(
                        license.institutionId
                    ) === institution;


                const matchesRole =

                    role === 'all' ||

                    license.role === role;


                const matchesStatus =

                    status === 'all' ||

                    license.status === status;


                const matchesPlan =

                    plan === 'all' ||

                    license.plan === plan;


                return (

                    matchesSearch &&

                    matchesInstitution &&

                    matchesRole &&

                    matchesStatus &&

                    matchesPlan

                );

            }
        );


    $('licenseCount')
        .textContent =

        `${rows.length} result` +

        (
            rows.length !== 1
                ? 's'
                : ''
        );


    $('licenseTable').innerHTML =

        rows.map(license => {

            const institution =
                inst(license.institutionId);


            return `

                <tr>

                    <td>#${license.id}</td>

                    <td>

                        <strong>
                            ${license.code}
                        </strong>

                    </td>


                    <td>
                        ${institution?.name || 'Unknown'}
                    </td>


                    <td>
                        ${license.role}
                    </td>


                    <td>
                        ${license.plan}
                    </td>


                    <td>

                        <span
                            class="status
                            ${license.status.toLowerCase()}"
                        >
                            ${license.status}
                        </span>

                    </td>


                    <td>
                        ${license.expiry}
                    </td>


                    <td>

                        <div class="row-actions">

                            <button
                                class="row-action"
                                title="Copy activation code"
                                onclick="
                                    copyLicense(
                                        '${license.code}'
                                    )
                                "
                            >
                                📋
                            </button>

                            <button
                                class="row-action"
                                title="Edit license"
                                onclick="
                                    editLicense(
                                        ${license.id}
                                    )
                                "
                            >
                                ✎
                            </button>

                            <button
                                class="row-action"
                                title="Suspend license"
                                onclick="
                                    licenseAction(
                                        ${license.id},
                                        'Suspend'
                                    )
                                "
                            >
                                ⏸
                            </button>

                            <button
                                class="row-action"
                                title="Show QR / manual code"
                                onclick="generateTotpQr('${license.code}')"
                                style="${license.twoFactorMethod === 'totp' ? '' : 'visibility:hidden;'}"
                            >
                                ▦
                            </button>

                            <button
                                class="row-action"
                                title="Permanently delete this license"
                                onclick="
                                    deleteLicense(
                                        '${license.code}'
                                    )
                                "
                            >
                                🗑
                            </button>

                        </div>

                    </td>

                </tr>

            `;

        })
        .join('')

        ||

        `

            <tr>

                <td colspan="8">

                    <div class="empty">
                        No licenses found.
                    </div>

                </td>

            </tr>

        `;

}


function licenseFields(license = {}) {
    return `
        <div class="form-grid">
            <div class="form-group">
                <label>Institution</label>
                <select name="institutionId">
                    ${state.institutions.map(institution => `
                        <option value="${institution.id}" ${license.institutionId === institution.id ? 'selected' : ''}>
                            ${institution.name}
                        </option>
                    `).join('')}
                </select>
            </div>

            <div class="form-group">
                <label>Role</label>
                <select name="role">
                    ${roles.map(role => `
                        <option ${license.role === role ? 'selected' : ''}>${role}</option>
                    `).join('')}
                </select>
            </div>

            <div class="form-group">
                <label>Phone</label>
                <input name="phone" placeholder="9876543210" value="${license.phone || ''}" required>
            </div>

            <div class="form-group">
                <label>DOB Year</label>
                <input name="dobYear" placeholder="1995" value="${license.dobYear || ''}" required>
            </div>

            <div class="form-group">
                <label>Two-Factor Method</label>
                <select name="twoFactorMethod">
                    <option value="email" ${(!license.twoFactorMethod || license.twoFactorMethod === 'email') ? 'selected' : ''}>Email OTP</option>
                    <option value="totp" ${license.twoFactorMethod === 'totp' ? 'selected' : ''}>Authenticator App (TOTP)</option>
                </select>
            </div>

            <div class="form-group">
                <label>Email (used if Email OTP selected)</label>
                <input name="email" type="email" placeholder="admin@hospital.com" value="${license.email || ''}">
            </div>

          
            <div class="form-group">
                <label>Plan</label>
                <select name="plan">
                    ${['Standard', 'Professional', 'Enterprise'].map(plan => `
                        <option ${license.plan === plan ? 'selected' : ''}>${plan}</option>
                    `).join('')}
                </select>
            </div>
        </div>
    `;
}


function openLicense(license = null) {
    openModal(
        'LICENSE',
        license ? 'Edit License' : 'Generate License',
        licenseFields(license || {}),
        data => {
            // ===== EDIT existing license =====
            if (license) {
                (async () => {
                    try {
                        const res = await authFetch(`${API_BASE}/admin/licenses/${license.code}`, {
                            method: 'PATCH',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                role: data.role,
                                plan: data.plan,
                                phone: data.phone,
                                dob_year: data.dobYear,
                                email: data.email,
                                two_factor_method: data.twoFactorMethod,
                            }),
                        });
                        const result = await res.json();

                        if (result.status !== 'success') {
                            toast(result.message || 'Failed to update license');
                            return;
                        }

                        Object.assign(license, {
                            role: data.role,
                            plan: data.plan,
                            phone: data.phone,
                            dobYear: data.dobYear,
                            email: data.email,
                        });

                        addActivity('License updated', license.code);
                        toast('License updated');
                        save();
                        closeModal();
                        renderLicenses();
                        renderDashboard();
                    } catch (err) {
                        console.error(err);
                        toast('Could not reach the server to update the license');
                    }
                })();
                return;
            }

            // ===== GENERATE new license via API =====
            if (!data.phone || !data.dobYear) {
                toast('Phone and DOB Year are required');
                return;
            }

            (async () => {
                try {
                    const response = await authFetch(`${API_BASE}/admin/licenses/generate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            institution_id: Number(data.institutionId),
                            role: data.role,
                            phone: data.phone,
                            dob_year: data.dobYear,
                            email: data.email,
                            plan: data.plan || 'Standard',
                            valid_days: 90
                        })
                    });

                    const result = await response.json();

                    if (result.status !== 'success') {
                        toast(result.message || 'Failed to generate license');
                        return;
                    }

                    const created = result.license;

                    state.licenses.unshift({
                        id: created.id,
                        code: created.code,
                        institutionId: Number(data.institutionId),
                        role: data.role,
                        plan: created.plan,
                        status: created.status,
                        expiry: created.expiry_date,
                        usage: 0,
                        phone: data.phone,
                        dobYear: data.dobYear
                    });

                    addActivity('License generated', created.code);
                    save();
                    closeModal();
                    renderLicenses();
                    renderDashboard();
                    toast(`Generated: ${created.code}`);
                    alert(`Activation Code:\n${created.code}`);
                } catch (err) {
                    console.error(err);
                    toast('Could not reach license API. Is backend running?');
                }
            })();
        }
    );
}

window.editLicense =
    id => {

        openLicense(

            state.licenses.find(
                license =>
                    license.id === id
            )

        );

    };


window.copyLicense =
    code => {

        navigator.clipboard
            ?.writeText(code);


        toast(
            `License ${code} copied`
        );

    };


window.licenseAction = async (id, action) => {
  const license = state.licenses.find(x => x.id === id);
  if (!license) return;

  const statusMap = {
    Suspend: "Suspended",
    Revoke: "Revoked",
    Activate: "Active"
  };
  const newStatus = statusMap[action] || action;

  try {
    const res = await authFetch(`${API_BASE}/admin/licenses/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: license.code, status: newStatus })
    });
    const data = await res.json();
    if (data.status !== "success") {
      toast(data.message || "Failed");
      return;
    }
    license.status = newStatus;
    save();
    addActivity(`License ${newStatus}`, license.code);
    renderLicenses();
    renderDashboard();
    toast(`License ${newStatus}`);
  } catch (e) {
    console.error(e);
    toast("Could not update license status");
  }
};

window.deleteLicense = async (code) => {
  if (!confirm(`Permanently delete license ${code}? This cannot be undone.`)) return;

  try {
    const res = await authFetch(`${API_BASE}/admin/licenses/${code}`, {
      method: "DELETE",
    });
    const data = await res.json();
    if (data.status !== "success") {
      toast(data.message || "Failed to delete license");
      return;
    }
    addActivity("License deleted", code);
    await loadLicensesFromAPI();
    renderLicenses();
    renderDashboard();
    toast(`License ${code} deleted`);
  } catch (e) {
    console.error(e);
    toast("Could not reach the server to delete the license");
  }
};
// =========================================================
// ANALYTICS
// =========================================================

async function generateTotpQr(code) {
    try {
        const res = await authFetch(`${API_BASE}/admin/licenses/${code}/totp-qr`);
        const result = await res.json();
        if (result.status !== 'success') {
            toast(result.message || 'Failed to generate QR code');
            return;
        }
        openModal('TOTP SETUP', `Authenticator Setup for ${code}`, `
            <div style="text-align:center;">
                <img src="${result.qr_code}" style="max-width:250px;" />
                <p style="font-size:12px; color:#64748b; margin-top:12px;">Scan with Google Authenticator, Authy, or any TOTP app.</p>
                <div style="margin-top:16px; padding:12px; background:#f8fafc; border-radius:8px; display:flex; align-items:center; justify-content:space-between; gap:10px;">
                    <div>
                        <div style="font-size:11px; color:#64748b; margin-bottom:4px;">Can't scan? Enter manually:</div>
                        <div style="font-family:monospace; font-size:14px; font-weight:700; letter-spacing:1px;">${result.manual_code}</div>
                    </div>
                    <button type="button" class="secondary-btn" onclick="navigator.clipboard.writeText('${result.manual_code.replace(/ /g, '')}'); toast('Code copied');" style="flex-shrink:0;">Copy</button>
                </div>
            </div>
        `, null);
    } catch (err) {
        console.error(err);
        toast('Could not reach the server to generate QR code');
    }
}


function renderAnalytics() {

    fillSelect(
        'analyticsInstitution',
        state.institutions.map(institution => String(institution.id)),
        'Institution'
    );

    const institutionSelect = $('analyticsInstitution');

    [...institutionSelect.options].forEach(option => {
        if (option.value !== 'all') {
            option.textContent = inst(option.value)?.name || option.value;
        }
    });

    fillSelect('analyticsRole', roles, 'Role');
    fillSelect('analyticsPlan', ['Standard', 'Professional', 'Enterprise'], 'Plan');

    const range = Number($('analyticsRange').value);
    const institution = institutionSelect.value;
    const role = $('analyticsRole').value;
    const plan = $('analyticsPlan').value;

    const licenses = state.licenses.filter(license =>
        (institution === 'all' || String(license.institutionId) === institution) &&
        (role === 'all' || license.role === role) &&
        (plan === 'all' || license.plan === plan)
    );

    // Real analytics: derived from actual audit/audit.log events
    // (state.auditEvents, loaded by loadAuditFromAPI), not fabricated
    // numbers. Previously this synthesized fake totals via
    // `base + range * 730` — that line invented up to 730 fake queries
    // per day regardless of what actually happened.
    const licenseCodes = new Set(licenses.map(l => l.code));
    const rangeStartMs = Date.now() - range * 24 * 60 * 60 * 1000;

    const relevantEvents = (state.auditEvents || []).filter(e =>
        e.event === 'premium_query' &&
        licenseCodes.has(e.code) &&
        new Date(e.ts).getTime() >= rangeStartMs
    );

    const queries = relevantEvents.length;
    const codes = licenses.length;
    const average = codes ? (queries / codes).toFixed(1) : '0.0';

    $('analyticsQueries').textContent = queries.toLocaleString();
    $('analyticsCodes').textContent = codes;
    $('analyticsAverage').textContent = average;

    // Real peak hour from actual query timestamps, instead of a
    // hardcoded '11 AM'. Shows 'N/A' when there's not enough data yet
    // rather than pretending to know.
    if (relevantEvents.length === 0) {
        $('analyticsPeak').textContent = 'N/A';
    } else {
        const hourCounts = {};
        relevantEvents.forEach(e => {
            const hour = new Date(e.ts).getHours();
            hourCounts[hour] = (hourCounts[hour] || 0) + 1;
        });
        const peakHour = Number(
            Object.entries(hourCounts).sort((a, b) => b[1] - a[1])[0][0]
        );
        const displayHour = ((peakHour % 12) || 12) + (peakHour < 12 ? ' AM' : ' PM');
        $('analyticsPeak').textContent = displayHour;
    }

    drawLineChart(relevantEvents, range);
    renderRoleBars(licenses);
    renderTopInstitutions(licenses);
    renderFailureChart();
    loadInstitutionsUsage();
}


// =========================================================
// LINE CHART
// =========================================================

function drawLineChart(events, days) {

    const canvas = $('queryChart');
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = 220;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const points = days <= 7 ? 7 : days <= 30 ? 12 : 15;

    // Real day-bucketed counts from actual audit events, instead of a
    // fabricated sine-wave curve derived from one fake total number.
    const bucketMs = (days * 24 * 60 * 60 * 1000) / points;
    const rangeStartMs = Date.now() - days * 24 * 60 * 60 * 1000;

    const values = Array.from({ length: points }, (_, index) => {
        const bucketStart = rangeStartMs + index * bucketMs;
        const bucketEnd = bucketStart + bucketMs;
        return events.filter(e => {
            const t = new Date(e.ts).getTime();
            return t >= bucketStart && t < bucketEnd;
        }).length;
    });

    const max = Math.max(...values, 1) * 1.18;
    const min = 0;

    // Grid
    ctx.strokeStyle = '#ececf1';
    ctx.lineWidth = 1;
    for (let y = 0; y < 5; y++) {
        const yy = 20 + y * (height - 50) / 4;
        ctx.beginPath();
        ctx.moveTo(35, yy);
        ctx.lineTo(width - 10, yy);
        ctx.stroke();
    }

    // Line
    ctx.beginPath();
    values.forEach((value, index) => {
        const x = 35 + index * (width - 50) / (points - 1);
        const y = height - 30 - (value - min) / (max - min) * (height - 60);
        if (index === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    ctx.strokeStyle = '#6a5cf6';
    ctx.lineWidth = 3;
    ctx.stroke();

}



// =========================================================
// ROLE BARS
// =========================================================

function renderRoleBars(
    licenses
) {

    const map = {};


    roles.forEach(
        role => {
            map[role] = 0;
        }
    );


    licenses.forEach(
        license => {

            map[license.role] =
                (
                    map[license.role] || 0
                ) +

                license.usage;

        }
    );


    const max =
        Math.max(
            ...Object.values(map),
            1
        );


    $('roleBars').innerHTML =

        Object.entries(map)
            .map(
                ([role, value]) => `

                    <div class="bar-row">

                        <span>
                            ${role}
                        </span>

                        <div class="bar-track">

                            <div
                                class="bar-fill"
                                style="
                                    width:
                                    ${
                                        value /
                                        max *
                                        100
                                    }%
                                "
                            ></div>

                        </div>

                        <b>
                            ${value}
                        </b>

                    </div>

                `
            )
            .join('');

}


// =========================================================
// TOP INSTITUTIONS
// =========================================================

function renderTopInstitutions(
    licenses
) {

    const map = {};


    licenses.forEach(
        license => {

            map[license.institutionId] =

                (
                    map[license.institutionId]
                    || 0
                )

                +

                license.usage;

        }
    );


    const rows =

        Object.entries(map)

            .sort(
                (a, b) =>
                    b[1] - a[1]
            )

            .slice(0, 5);


    $('topInstitutions').innerHTML =

        rows
            .map(
                ([id, value]) => `

                    <div class="mini-row">

                        <span>
                            ${
                                inst(id)?.name ||
                                'Unknown'
                            }
                        </span>

                        <span>
                            ${value.toLocaleString()}
                        </span>

                    </div>

                `
            )
            .join('')

        ||

        '<div class="empty">No usage data.</div>';

}


// =========================================================
// FAILURE CHART
// =========================================================

function renderFailureChart() {

    // Real breakdown of why activation attempts failed, from
    // invalid_code_attempt events in the real audit log — previously
    // this was 4 completely hardcoded percentages (42/26/18/14) that
    // never reflected anything that actually happened.
    const failureEvents = (state.auditEvents || []).filter(e => e.event === 'invalid_code_attempt');

    const reasonLabels = {
        invalid_code: 'Invalid code',
        inactive: 'Inactive license',
        expired: 'Expired license',
    };

   const colors = ['#6a5cf6', '#38bdf8', '#fbbf24', '#f87171', '#a1a1aa'];

    if (failureEvents.length === 0) {
        $('failurePie').style.background = '#e5e7eb';
        $('failureLegend').innerHTML = '<div class="empty">No failed activation attempts recorded yet.</div>';
        return;
    }

    const counts = {};
    failureEvents.forEach(e => {
        const reason = e.meta?.reason || 'other';
        counts[reason] = (counts[reason] || 0) + 1;
    });

    const total = failureEvents.length;
    const reasons = Object.entries(counts).map(([reason, count]) => [
        reasonLabels[reason] || reason,
        Math.round((count / total) * 100)
    ]);

    let current = 0;
    const parts = [];
    reasons.forEach((reason, index) => {
        const color = colors[index % colors.length];
        parts.push(`${color} ${current}% ${current + reason[1]}%`);
        current += reason[1];
    });

    $('failurePie').style.background = `conic-gradient(${parts.join(',')})`;

    $('failureLegend').innerHTML = reasons.map((reason, index) => `
        <div class="legend-item">
            <span class="legend-dot" style="background: ${colors[index % colors.length]}"></span>
            <span>${reason[0]}</span>
            <span class="legend-value">${reason[1]}%</span>
        </div>
    `).join('');

}
// =========================================================
// ROLES & PERMISSIONS
// =========================================================
async function manageLimit(institutionId, hospitalCode) {
  const [planRes, usageRes] = await Promise.all([
authFetch(`${API_BASE}/admin/institutions/${hospitalCode}/limit`),
authFetch(`${API_BASE}/admin/institutions/${hospitalCode}/usage`),
  ]);
  const current = await planRes.json();
  const usage = await usageRes.json();
  const pct = usage.limit ? Math.round((usage.used / usage.limit) * 100) : 0;

  $('modalEyebrow').textContent = 'TOKEN LIMIT';
  $('modalTitle').textContent = `Token Limit — ${hospitalCode}`;
  $('modalFields').innerHTML = `
    <div style="grid-column:1/-1;font-size:11px;color:#64748b;margin-bottom:10px;">
      Used <strong>${usage.used.toLocaleString()}</strong> / ${usage.limit.toLocaleString()} tokens this ${usage.period_type} (${pct}%)
    </div>
    <div class="form-grid">
      <div class="form-group">
        <label>Period</label>
        <select id="limitPeriodType">
          <option value="day" ${current.period_type === 'day' ? 'selected' : ''}>Per Day</option>
          <option value="month" ${current.period_type === 'month' ? 'selected' : ''}>Per Month</option>
          <option value="year" ${current.period_type === 'year' ? 'selected' : ''}>Per Year</option>
        </select>
      </div>
      <div class="form-group">
        <label>Token Limit</label>
        <input id="limitValue" type="number" min="1" value="${current.token_limit}">
      </div>
    </div>
  `;

  $('modalOverlay').classList.add('show');

  $('modalForm').onsubmit = async (e) => {
    e.preventDefault();
    const period_type = $('limitPeriodType').value;
    const token_limit = parseInt($('limitValue').value, 10);

    const saveRes = await authFetch(`${API_BASE}/admin/institutions/${hospitalCode}/limit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ period_type, token_limit }),
    });

    if (saveRes.ok) {
      $('modalOverlay').classList.remove('show');
      try { showToast('Token limit updated.'); } catch (e) { console.log('Token limit saved.'); }
    } else {
      try { showToast('Failed to update.'); } catch (e) { console.log('Failed to update.'); }
    }
  };
}
async function renderRoles() {
  try {
    const res = await authFetch(`${API_BASE}/admin/roles`);
    const data = await res.json();
    if (data.status !== "success") throw new Error("Failed to load roles");
    const rolesData = data.roles;
    const container = $("roleRows");
    container.innerHTML = Object.entries(rolesData).map(([role, tables]) => `
      <div class="role-row" style="display:flex;gap:10px;align-items:center;margin:8px 0;">
        <span style="width:120px;"><b>${role}</b></span>
        <input class="role-tables" data-role="${role}" value="${tables.join(", ")}" style="flex:1;padding:8px;" />
        <button class="secondary-btn" onclick="saveRole('${role}')">Save</button>
      </div>
    `).join("");
  } catch (e) {
    console.error(e);
    toast("Could not load roles");
  }
}
window.saveRole = async (role) => {
  const input = document.querySelector(`.role-tables[data-role="${role}"]`);
  const tables = input.value.split(",").map(t => t.trim()).filter(Boolean);
  try {
    const res = await authFetch(`${API_BASE}/admin/roles`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, tables })
    });
    const data = await res.json();
    toast(data.status === "success" ? `Saved ${role}` : "Failed to save role");
  } catch (e) {
    console.error(e);
    toast("Could not save role");
  }
};
window.editRole =
    role => {

        const current =
            rolePermissions[role]
                .join(', ');


        openModal(

            'PERMISSIONS',

            `Edit ${role} Permissions`,

            `

                <div class="form-grid">

                    <div
                        class="form-group"
                        style="grid-column:1/-1"
                    >

                        <label>
                            Allowed modules / tables
                        </label>

                        <input
                            name="permissions"
                            value="${current}"
                        >

                        <small>
                            Use commas between permissions.
                        </small>

                    </div>

                </div>

            `,

            data => {

                rolePermissions[role] =

                    data.permissions

                        .split(',')

                        .map(
                            item =>
                                item.trim()
                        )

                        .filter(Boolean);


                closeModal();

                renderRoles();

                toast(
                    `${role} permissions updated`
                );

            }

        );

    };


// =========================================================
// SETTINGS
// =========================================================

const LLM_PROVIDERS = ['groq', 'gemini', 'mistral', 'cohere', 'openrouter', 'openai'];
let llmOrderState = [...LLM_PROVIDERS];

function populateLlmOrderDropdowns(currentOrder) {
    llmOrderState = (currentOrder && currentOrder.length === 6) ? [...currentOrder] : [...LLM_PROVIDERS];
    renderLlmOrderList();
}

function renderLlmOrderList() {
    $('llmOrderList').innerHTML = llmOrderState.map((p, i) => `
        <div class="setting" draggable="true" data-index="${i}"
             ondragstart="llmDragStart(event)" ondragover="llmDragOver(event)" ondrop="llmDrop(event)"
             style="cursor:grab; user-select:none;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="color:#94a3b8; font-size:14px;">☰</span>
                <strong>${i + 1}. ${p.charAt(0).toUpperCase() + p.slice(1)}</strong>
            </div>
        </div>
    `).join('');
}

let llmDragIndex = null;
function llmDragStart(e) {
    llmDragIndex = Number(e.currentTarget.dataset.index);
}
function llmDragOver(e) {
    e.preventDefault();
}
function llmDrop(e) {
    e.preventDefault();
    const dropIndex = Number(e.currentTarget.dataset.index);
    if (llmDragIndex === null || llmDragIndex === dropIndex) return;
    const [moved] = llmOrderState.splice(llmDragIndex, 1);
    llmOrderState.splice(dropIndex, 0, moved);
    llmDragIndex = null;
    renderLlmOrderList();
}

function getLlmOrderFromDropdowns() {
    return llmOrderState;
}

function renderSettings() {

    const settings =
        state.settings;


    $('licenseValidity')
        .value =
        settings.validity;


    $('normalMode')
        .checked =
        settings.normalMode;


    $('rateLimit')
        .value =
        settings.rateLimit;


    $('blockedPatterns')
        .value =
        settings.blockedPatterns;


    $('redaction')
        .checked =
        settings.redaction;


    $('emailAlerts')
        .checked =
        settings.emailAlerts;


    $('alertSmtpHost').value = settings.alertSmtpHost || '';
    $('alertSmtpPort').value = settings.alertSmtpPort || 587;
    $('alertSmtpUser').value = settings.alertSmtpUser || '';
    $('alertSmtpPassword').value = settings.alertSmtpPassword || '';
    $('otpSmtpHost').value = settings.otpSmtpHost || '';
    $('otpSmtpPort').value = settings.otpSmtpPort || 587;
    $('otpSmtpUser').value = settings.otpSmtpUser || '';
    $('otpSmtpPassword').value = settings.otpSmtpPassword || '';
    $('alertEmailTo').value = settings.alertEmailTo || '';


    $('webhook')
        .value =
        settings.webhook;


      populateLlmOrderDropdowns(settings.llmProviderOrder);
      customProvidersState = settings.llmCustomProviders || [];
      renderCustomProvidersList();
      $('llmKeyGroq').value = '';
      $('llmKeyGemini').value = '';
      $('llmKeyMistral').value = '';
      $('llmKeyCohere').value = '';
      $('llmKeyOpenRouter').value = '';
      $('llmKeyOpenAI').value = '';
      renderAdminUsersList();


}

let customProvidersState = [];

function renderCustomProvidersList() {
    $('customProvidersList').innerHTML = customProvidersState.map((p, i) => `
        <div class="setting" style="flex-direction:column; align-items:stretch; gap:8px;">
            <div style="display:flex; justify-content:space-between;">
                <strong>${p.name || 'New Provider'}</strong>
                <button type="button" class="row-action" onclick="removeCustomProviderRow(${i})">🗑</button>
            </div>
            <input placeholder="Name (e.g. TogetherAI)" class="setting-input" value="${p.name || ''}" oninput="updateCustomProvider(${i}, 'name', this.value)">
            <input placeholder="Base URL (e.g. https://api.together.xyz/v1)" class="setting-input" value="${p.base_url || ''}" oninput="updateCustomProvider(${i}, 'base_url', this.value)">
            <input placeholder="Model name" class="setting-input" value="${p.model || ''}" oninput="updateCustomProvider(${i}, 'model', this.value)">
            <input type="password" placeholder="API key" class="setting-input" value="${p.api_key || ''}" oninput="updateCustomProvider(${i}, 'api_key', this.value)">
        </div>
    `).join('') || '<div class="empty">No custom providers added yet.</div>';
}

function addCustomProviderRow() {
    customProvidersState.push({ name: '', base_url: '', model: '', api_key: '' });
    renderCustomProvidersList();
}

function removeCustomProviderRow(i) {
    customProvidersState.splice(i, 1);
    renderCustomProvidersList();
}

function updateCustomProvider(i, field, value) {
    customProvidersState[i][field] = value;
}
async function loadOpenAIUsage() {
  try {
    const res = await authFetch(`${API_BASE}/admin/openai-usage?days=30`);
    const data = await res.json();
    const settingsRes = await authFetch(`${API_BASE}/admin/settings`);
    const settingsData = await settingsRes.json();
    const tokenBudget = parseInt(settingsData.settings?.openai_token_budget) || null;
    const tokenBaseline = parseInt(settingsData.settings?.openai_token_baseline) || 0;
    

    if (!data.available) {
      $('openaiTokenTotal').textContent = 'N/A';
      $('openaiRequestCount').textContent = data.reason || 'Not configured';
      return data;
    }

    const displayTokens = tokenBudget ? Math.max(0, (data.total_tokens || 0) - tokenBaseline) : data.total_tokens;
    $('openaiTokenTotal').textContent = displayTokens.toLocaleString();
    $('openaiRequestCount').textContent = `${data.total_requests.toLocaleString()} requests`;

    if (tokenBudget) {
      const used = Math.max(0, (data.total_tokens || 0) - tokenBaseline);
      const pct = Math.min(100, Math.round((used / tokenBudget) * 100));
      const barColor = pct > 90 ? '#dc2626' : pct > 70 ? '#f59e0b' : '#22c55e';
      $('openaiCreditBar').innerHTML = `
        <div style="background:#f1f5f9; border-radius:6px; height:8px; overflow:hidden; margin-top:8px;">
          <div style="width:${pct}%; height:100%; background:${barColor}; transition:width 0.3s ease;"></div>
        </div>
        <div style="font-size:11px; color:#64748b; margin-top:4px;">${pct}% used (${used.toLocaleString()} / ${tokenBudget.toLocaleString()} tokens)</div>
      `;
    }

    return data;
  } catch (err) {
    console.error(err);
    return null;
  }
}

function renderAdminUsersList() {
    $('adminUsers').innerHTML =
        (state.admins || [])
            .map(admin => `
                <div class="admin-user">
                    <div>
                        <strong>${admin.display_name || admin.username}</strong>
                        <small>${admin.username} · ${admin.status}${admin.last_login_at ? ' · last login ' + formatRelativeTime(admin.last_login_at) : ' · never logged in'}</small>
                    </div>
                    <button
                        class="row-action"
                        onclick="toggleAdminStatus('${admin.username}', '${admin.status === 'Active' ? 'Inactive' : 'Active'}')"
                    >
                        ${admin.status === 'Active' ? 'Deactivate' : 'Reactivate'}
                    </button>
                </div>
            `)
            .join('') || '<div class="empty">No admin accounts yet.</div>';
}


async function loadAdminsFromAPI() {
    const res = await authFetch(`${API_BASE}/admin/users`);
    const data = await res.json();
    if (data.status !== "success") throw new Error("Failed to load admin users");
    state.admins = data.admins;
    save();
}


window.toggleAdminStatus = (username, newStatus) => {
    (async () => {
        try {
            const res = await authFetch(`${API_BASE}/admin/users/${username}/status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus }),
            });
            const result = await res.json();
            if (!res.ok || result.status !== 'success') {
                toast(result.message || 'Failed to update admin status');
                return;
            }
            await loadAdminsFromAPI();
            renderAdminUsersList();
            toast(`${username} is now ${newStatus}`);
        } catch (err) {
            console.error(err);
            toast('Could not reach the server');
        }
    })();
};


// =========================================================
// AUDIT LOGS
// =========================================================

async function renderAudit() {
    const search = $('auditSearch').value;
    const eventType = $('auditEventFilter').value;
    const range = $('auditDateRange').value;
    const institutionId = $('auditInstitutionFilter').value;
    let dateFrom = '', dateTo = '';
    const today = new Date();
    const iso = d => d.toISOString().split('T')[0];

    if (range === 'today') {
      dateFrom = dateTo = iso(today);
    } else if (range === 'yesterday') {
      const y = new Date(today); y.setDate(y.getDate() - 1);
      dateFrom = dateTo = iso(y);
    } else if (range === 'last_week') {
      const w = new Date(today); w.setDate(w.getDate() - 7);
      dateFrom = iso(w); dateTo = iso(today);
    } else if (range === 'last_month') {
      const m = new Date(today); m.setMonth(m.getMonth() - 1);
      dateFrom = iso(m); dateTo = iso(today);
    } else if (range === 'last_year') {
      const y = new Date(today); y.setFullYear(y.getFullYear() - 1);
      dateFrom = iso(y); dateTo = iso(today);
    } else if (range === 'custom') {
      dateFrom = $('auditDateFrom').value;
      dateTo = $('auditDateTo').value;
    }

    const params = new URLSearchParams({ limit: 500 });
    if (search) params.set('search', search);
    if (eventType && eventType !== 'all') params.set('event_type', eventType);
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    if (institutionId && institutionId !== 'all') params.set('institution_id', institutionId);

    let events = [];
    try {
        const res = await authFetch(`${API_BASE}/admin/audit?${params.toString()}`);
        const data = await res.json();
        events = data.events || [];
    } catch (err) {
        console.error(err);
        $('auditTable').innerHTML = `<tr><td colspan="5"><div class="empty">Could not load audit log.</div></td></tr>`;
        return;
    }

    $('auditCount').textContent = `${events.length} events`;

    $('auditTable').innerHTML = events.map(ev => `
        <tr class="audit-row" onclick="toggleAuditDetail(${ev.id})" style="cursor:pointer;">
            <td>#${ev.id}</td>
            <td>${formatRelativeTime(ev.ts)}</td>
            <td><strong>${ev.event}</strong></td>
            <td>${(ev.question || '').slice(0, 60)}${(ev.question || '').length > 60 ? '…' : ''}</td>
            <td style="text-align:center;">
                <span id="audit-chevron-${ev.id}" style="display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; border-radius:50%; background:#f1f5f9; font-size:16px; font-weight:700; color:#475569; transition:transform 0.2s ease;">›</span>
            </td>
        </tr>
        <tr id="audit-detail-${ev.id}" style="display:none;">
            <td colspan="5" style="background:#f8fafc; padding:16px 20px;">
                <div style="font-size:12px; color:#64748b; margin-bottom:4px;">ROLE / CODE</div>
                <div style="margin-bottom:12px;">${ev.role || '-'} ${ev.code ? '· ' + ev.code : ''}</div>

                <div style="font-size:12px; color:#64748b; margin-bottom:4px;">QUESTION</div>
                <div style="margin-bottom:12px; white-space:pre-wrap;">${ev.question || '-'}</div>

                <div style="font-size:12px; color:#64748b; margin-bottom:4px;">ANSWER</div>
                <div style="margin-bottom:12px; white-space:pre-wrap; max-height:200px; overflow-y:auto;">${ev.answer || '-'}</div>

                <div style="display:flex; gap:24px;">
                    <div>
                        <div style="font-size:12px; color:#64748b;">TOKENS USED</div>
                        <div style="font-weight:700;">${ev.tokens_used != null ? ev.tokens_used : '-'}</div>
                    </div>
                    <div>
                        <div style="font-size:12px; color:#64748b;">TIMESTAMP</div>
                        <div>${ev.ts}</div>
                    </div>
                </div>
            </td>
        </tr>
    `).join('') || `<tr><td colspan="5"><div class="empty">No matching events.</div></td></tr>`;
}


async function loadChatbotSettings() {
    const res = await authFetch(`${API_BASE}/admin/settings`);
    const data = await res.json();
    const s = data.settings;
    $('cbTitle').value = s.widget_title || '';
    $('cbSubtitle').value = s.widget_subtitle || '';
    $('cbWelcome').value = s.widget_welcome_message || '';
    $('cbIconUrl').value = s.widget_icon_url || '';
    $('cbFooter').value = s.widget_footer_text || '';
    $('cbDisclaimer').value = s.widget_disclaimer_text || '';
    $('cbPrimaryColor').value = s.widget_primary_color || '#8B008B';
    $('cbSecondaryColor').value = s.widget_secondary_color || '#1e293b';
    $('cbBgColor').value = s.widget_bg_color || '#ffffff';
    $('cbWidth').value = s.widget_width_px || 420;
    $('cbHeight').value = s.widget_height_px || 700;
    $('cbMaxHistory').value = s.widget_max_history || 50;
    $('cbSessionTimeout').value = s.widget_session_timeout_min || 0;
    $('cbPreviewToast').checked = !!s.widget_preview_toast_enabled;
    $('cbEscalatePhone').value = s.widget_escalate_phone || '';
    $('cbEscalateMsg').value = s.widget_escalate_message || '';
    $('cbIdleNudgeEnabled').checked = !!s.widget_idle_nudge_enabled;
    $('cbIdleMinutes').value = s.widget_idle_nudge_minutes || 3;
    $('cbIdleMsg').value = s.widget_idle_nudge_message || '';
}

$('saveChatbotSettings').onclick = async () => {
    try {
        const res = await authFetch(`${API_BASE}/admin/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                widget_title: $('cbTitle').value,
                widget_subtitle: $('cbSubtitle').value,
                widget_welcome_message: $('cbWelcome').value,
                widget_icon_url: $('cbIconUrl').value,
                widget_footer_text: $('cbFooter').value,
                widget_disclaimer_text: $('cbDisclaimer').value,
                widget_primary_color: $('cbPrimaryColor').value,
                widget_secondary_color: $('cbSecondaryColor').value,
                widget_bg_color: $('cbBgColor').value,
                widget_width_px: Number($('cbWidth').value) || 420,
                widget_height_px: Number($('cbHeight').value) || 700,
                widget_max_history: Number($('cbMaxHistory').value) || 50,
                widget_session_timeout_min: Number($('cbSessionTimeout').value) || 0,
                widget_preview_toast_enabled: $('cbPreviewToast').checked,
                widget_escalate_phone: $('cbEscalatePhone').value,
                widget_escalate_message: $('cbEscalateMsg').value,
                widget_idle_nudge_enabled: $('cbIdleNudgeEnabled').checked,
                widget_idle_nudge_minutes: Number($('cbIdleMinutes').value) || 3,
                widget_idle_nudge_message: $('cbIdleMsg').value,
            }),
        });
        const result = await res.json();
        if (result.status !== 'success') { toast(result.message || 'Failed to save'); return; }
        toast('ChatBot settings saved');
    } catch (err) {
        console.error(err);
        toast('Could not reach the server');
    }
};

function populateAuditInstitutionFilter() {
    const sel = $('auditInstitutionFilter');
    sel.innerHTML = '<option value="all">Institution</option>' +
        state.institutions.map(i => `<option value="${i.id}">${i.name}</option>`).join('');
}

$('auditDateRange').addEventListener('change', () => {
    const isCustom = $('auditDateRange').value === 'custom';
    $('auditDateFrom').style.display = isCustom ? 'inline-block' : 'none';
    $('auditDateTo').style.display = isCustom ? 'inline-block' : 'none';
    renderAudit();
});
$('auditInstitutionFilter').addEventListener('change', renderAudit);
let roleSuggestionsCache = {};

async function openRoleSuggestionsModal() {
    const res = await authFetch(`${API_BASE}/admin/settings`);
    const data = await res.json();
    roleSuggestionsCache = data.settings.widget_role_suggestions || {};
    renderRoleSuggestionsForm('diagnostic', null);
}

function renderRoleSuggestionsForm(instType, role) {
    const key = instType === 'hospital' ? `hospital_${role}` : 'diagnostic';
    const current = roleSuggestionsCache[key] || [{ label: '', query: '' }, { label: '', query: '' }];

    openModal('CHATBOT', 'Role-Based Quick Prompts', `
        <div class="form-group">
            <label>Institution Type</label>
            <select id="rsInstType" onchange="renderRoleSuggestionsForm(this.value, $('rsRole') ? $('rsRole').value : 'admin')">
                <option value="diagnostic" ${instType === 'diagnostic' ? 'selected' : ''}>Diagnostic / LIS</option>
                <option value="hospital" ${instType === 'hospital' ? 'selected' : ''}>Hospital / HIS</option>
            </select>
        </div>
        ${instType === 'hospital' ? `
        <div class="form-group">
            <label>Role</label>
            <select id="rsRole" onchange="renderRoleSuggestionsForm('hospital', this.value)">
                <option value="admin" ${role === 'admin' ? 'selected' : ''}>Admin</option>
                <option value="doctor" ${role === 'doctor' ? 'selected' : ''}>Doctor</option>
                <option value="reception" ${role === 'reception' ? 'selected' : ''}>Reception</option>
            </select>
        </div>
        ` : ''}
        <div class="form-group"><label>Prompt 1 Label</label><input id="rsLabel1" value="${current[0]?.label || ''}"></div>
        <div class="form-group"><label>Prompt 1 Query</label><input id="rsQuery1" value="${current[0]?.query || ''}"></div>
        <div class="form-group"><label>Prompt 2 Label</label><input id="rsLabel2" value="${current[1]?.label || ''}"></div>
        <div class="form-group"><label>Prompt 2 Query</label><input id="rsQuery2" value="${current[1]?.query || ''}"></div>
        <button type="button" class="secondary-btn" onclick="saveRoleSuggestion('${key}')">Save This Combination</button>
    `, null);
}

async function saveRoleSuggestion(key) {
    roleSuggestionsCache[key] = [
        { label: $('rsLabel1').value, query: $('rsQuery1').value },
        { label: $('rsLabel2').value, query: $('rsQuery2').value },
    ];

    try {
        const res = await authFetch(`${API_BASE}/admin/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ widget_role_suggestions: roleSuggestionsCache }),
        });
        const result = await res.json();
        if (result.status !== 'success') { toast(result.message || 'Failed to save'); return; }
        toast(`Saved prompts for ${key}`);
    } catch (err) {
        console.error(err);
        toast('Could not reach the server');
    }
}

let AVAILABLE_TABLES = [];

async function loadAvailableModules() {
    try {
        const res = await authFetch(`${API_BASE}/admin/available-modules`);
        const data = await res.json();
        AVAILABLE_TABLES = data.modules || [];
    } catch (err) {
        console.error('Could not load available modules', err);
    }
}

async function loadRolesFromAPI() {
    const res = await authFetch(`${API_BASE}/admin/roles`);
    const data = await res.json();
    state.rolePermissions = data.roles || {};
}

async function renderRoles() {
    await loadRolesFromAPI();
    const roles = state.rolePermissions;
    const roleNames = Object.keys(roles);

    $('roleRows').innerHTML = roleNames.map(role => `
        <div class="role-row">
            <div class="role-name">${role}</div>
            <div class="chips">${roles[role].map(t => `<span class="chip">${t}</span>`).join('')}</div>
            <div class="row-actions">
                <button class="row-action" onclick="openRoleModal('${role}')">✎</button>
                <button class="row-action" onclick="deleteRole('${role}')">🗑</button>
            </div>
        </div>
    `).join('') || `<div class="empty">No roles configured yet.</div>`;
}

async function openRoleModal(role = null) {
    if (AVAILABLE_TABLES.length === 0) await loadAvailableModules();
    const currentTables = role ? state.rolePermissions[role] : [];
    openModal('ROLES', role ? `Edit ${role}` : 'Add Role', `
        <div class="form-group">
            <label>Role Name</label>
            <input name="roleName" value="${role || ''}" ${role ? 'readonly' : ''} required>
        </div>
        <div class="form-group">
            <label>Allowed Tables / Modules</label>
            <div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:6px;">
                ${AVAILABLE_TABLES.map(t => `
                    <label style="display:flex; align-items:center; gap:4px; font-size:11px; background:#f8fafc; border:1px solid #e2e2e7; border-radius:8px; padding:6px 10px;">
                        <input type="checkbox" name="table_${t}" ${currentTables.includes(t) ? 'checked' : ''}> ${t}
                    </label>
                `).join('')}
            </div>
        </div>
    `, async (data) => {
        const selectedTables = AVAILABLE_TABLES.filter(t => data[`table_${t}`]);
        try {
            const res = await authFetch(`${API_BASE}/admin/roles`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ role: data.roleName, tables: selectedTables }),
            });
            const result = await res.json();
            if (result.status !== 'success') { toast(result.message || 'Failed to save role'); return; }
            toast('Role saved');
            closeModal();
            renderRoles();
        } catch (err) {
            console.error(err);
            toast('Could not reach the server');
        }
    });
}

async function deleteRole(role) {
    if (!confirm(`Delete role "${role}"? This cannot be undone.`)) return;
    try {
        const res = await authFetch(`${API_BASE}/admin/roles/${role}`, { method: 'DELETE' });
        const result = await res.json();
        if (result.status !== 'success') { toast(result.message || 'Failed to delete'); return; }
        toast('Role deleted');
        renderRoles();
    } catch (err) {
        console.error(err);
        toast('Could not reach the server');
    }
}
function toggleAuditDetail(id) {
    const row = document.getElementById(`audit-detail-${id}`);
    const chevron = document.getElementById(`audit-chevron-${id}`);
    const isOpen = row.style.display !== 'none';
    row.style.display = isOpen ? 'none' : 'table-row';
    chevron.style.transform = isOpen ? 'rotate(0deg)' : 'rotate(90deg)';
}

async function loadInstitutionsUsage() {
    try {
        const res = await authFetch(`${API_BASE}/admin/institutions-usage`);
        const data = await res.json();
        if (data.status !== 'success') return;

        $('usageTableCount').textContent = `${data.usage.length} institutions`;

        $('institutionsUsageTable').innerHTML = data.usage.map(u => {
            const initials = u.institution_name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase();
            const statusClass = u.pct_used > 90 ? 'revoked' : u.pct_used > 70 ? 'trial' : 'active';
            const fillColor = u.pct_used > 90 ? 'linear-gradient(90deg,#dc5b62,#e88c90)'
                             : u.pct_used > 70 ? 'linear-gradient(90deg,#e7a044,#f0c078)'
                             : 'linear-gradient(90deg,#6756e8,#9285ff)';
            return `
                <tr>
                    <td>
                        <div class="institution-name">
                            <div class="institution-logo">${initials}</div>
                            <div><strong>${u.institution_name}</strong></div>
                        </div>
                    </td>
                    <td>${u.institution_code}</td>
                    <td>${u.used.toLocaleString()}</td>
                    <td>${u.limit.toLocaleString()}</td>
                    <td>${u.remaining.toLocaleString()}</td>
                    <td>
                        <div class="bar-row" style="grid-template-columns:1fr 35px; min-width:140px;">
                            <div class="bar-track"><div class="bar-fill" style="width:${u.pct_used}%; background:${fillColor};"></div></div>
                            <span class="status ${statusClass}" style="padding:3px 6px;">${u.pct_used}%</span>
                        </div>
                    </td>
                </tr>
            `;
        }).join('') || `<tr><td colspan="6"><div class="empty">No usage data yet.</div></td></tr>`;
    } catch (err) {
        console.error(err);
    }
}
// =========================================================
// MODAL SYSTEM
// =========================================================

let modalSubmit = null;


function openModal(
    eyebrow,
    title,
    fields,
    onSubmit
) {

    $('modalEyebrow')
        .textContent =
        eyebrow;


    $('modalTitle')
        .textContent =
        title;


    $('modalFields')
        .innerHTML =
        fields;


    $('modalOverlay')
        .classList
        .add('show');


    modalSubmit =
        onSubmit;

}


function closeModal() {

    $('modalOverlay')
        .classList
        .remove('show');


    modalSubmit =
        null;

}


$('closeModal')
    .onclick =
    closeModal;


$('cancelModal')
    .onclick =
    closeModal;


$('modalOverlay')
    .onclick =
    event => {

        if (
            event.target ===
            $('modalOverlay')
        ) {

            closeModal();

        }

    };


$('modalForm')
    .onsubmit =
    event => {

        event.preventDefault();


        const data =
            Object.fromEntries(
                new FormData(
                    event.target
                )
            );


        modalSubmit?.(
            data
        );

    };


// =========================================================
// BUTTONS
// =========================================================

const _on = (id, fn) => {
    const el = $(id);
    if (el) el.onclick = fn;
};

_on('addInstitution', () => openInstitution());
_on('dashboardAdd', () => openInstitution());
_on('generateLicense', () => openLicense());
_on('editPermissions', () => editRole('Admin'));
_on('refreshDashboard', () => {
    renderDashboard();
    toast('Dashboard refreshed');
});


// =========================================================
// SETTINGS SAVE
// =========================================================

$('saveSettings')
    .onclick =
    () => {

        // Add inside saveSettings, before the fetch call
const chosenOrder = getLlmOrderFromDropdowns();
console.log('[DEBUG] chosenOrder at save time:', chosenOrder, 'llmOrderState:', llmOrderState);
if (new Set(chosenOrder).size !== chosenOrder.length) {
    toast('Each provider can only appear once in the priority list');
    return;
}

        const payload = {
            license_validity_days: Number($('licenseValidity').value),
            normal_mode_enabled: $('normalMode').checked,
            rate_limit_per_minute: Number($('rateLimit').value),
            extra_blocked_patterns: $('blockedPatterns').value
                .split(',')
                .map(p => p.trim())
                .filter(Boolean),
            output_redaction_enabled: $('redaction').checked,
            email_alerts_enabled: $('emailAlerts').checked,
            webhook_url: $('webhook').value,
            alert_smtp_host: $('alertSmtpHost').value,
            alert_smtp_port: Number($('alertSmtpPort').value) || 587,
            alert_smtp_user: $('alertSmtpUser').value,
            llm_custom_providers: customProvidersState.filter(p => p.name && p.base_url && p.model && p.api_key),
            alert_smtp_password: $('alertSmtpPassword').value,
            otp_smtp_host: $('otpSmtpHost').value,
            otp_smtp_port: Number($('otpSmtpPort').value) || 587,
            otp_smtp_user: $('otpSmtpUser').value,
            otp_smtp_password: $('otpSmtpPassword').value,
            llm_provider_order: getLlmOrderFromDropdowns(),
            llm_groq_key_override: $('llmKeyGroq').value,
            llm_gemini_key_override: $('llmKeyGemini').value,
            llm_mistral_key_override: $('llmKeyMistral').value,
            llm_cohere_key_override: $('llmKeyCohere').value,
            llm_openrouter_key_override: $('llmKeyOpenRouter').value,
            llm_openai_key_override: $('llmKeyOpenAI').value,
            alert_email_to: $('alertEmailTo').value,
            openai_token_budget: Number($('openaiCreditLimit').value) || 0,
        };
        (async () => {
            try {
                const res = await authFetch(`${API_BASE}/admin/settings`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const result = await res.json();

                if (!res.ok || result.status !== 'success') {
                    toast(result.message || 'Failed to save settings');
                    return;
                }

                await loadSettingsFromAPI();
                addActivity('Settings updated', 'Administrative configuration changed');
                toast('Settings saved');
            } catch (err) {
                console.error(err);
                toast('Could not reach the server to save settings');
            }
        })();

    };


$('testNotifications')
    .onclick = () => {
        (async () => {
            const btn = $('testNotifications');
            btn.disabled = true;
            btn.textContent = 'Sending...';
            try {
                const res = await authFetch(`${API_BASE}/admin/notifications/test`, { method: 'POST' });
                const result = await res.json();
                if (!res.ok) {
                    toast('Failed to send test alert');
                    return;
                }
                const parts = [];
                parts.push(`Email: ${result.email.success ? 'sent' : 'failed - ' + result.email.message}`);
                parts.push(`Webhook: ${result.webhook.success ? 'sent' : 'failed - ' + result.webhook.message}`);
                toast(parts.join(' | '));
            } catch (err) {
                console.error(err);
                toast('Could not reach the server');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Send Test Alert';
            }
        })();
    };


$('resetTokenBaseline').onclick = async () => {
  try {
    const res = await authFetch(`${API_BASE}/admin/openai-usage?days=30`);
    const data = await res.json();
    if (!data.available) { toast('Could not load current usage to reset against'); return; }

    await authFetch(`${API_BASE}/admin/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ openai_token_baseline: data.total_tokens }),
    });
    toast('Counter reset — tracking from current usage forward');
    loadOpenAIUsage();
  } catch (err) {
    console.error(err);
    toast('Could not reset counter');
  }
};


// =========================================================
// ADD ADMIN
// =========================================================

$('addAdmin')
    .onclick =
    () => {

        openModal(

            'ADMIN USER',

            'Add Admin User',

            `
                <div class="form-grid">

                    <div class="form-group">
                        <label>Username</label>
                        <input name="username" required autocomplete="off">
                    </div>

                    <div class="form-group">
                        <label>Display Name</label>
                        <input name="display_name">
                    </div>

                    <div class="form-group">
                        <label>Password</label>
                        <input name="password" type="password" required minlength="8">
                        <small>At least 8 characters.</small>
                    </div>

                </div>
            `,

            data => {
                (async () => {
                    try {
                        const res = await authFetch(`${API_BASE}/admin/users`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                username: data.username.trim(),
                                password: data.password,
                                display_name: (data.display_name || '').trim(),
                            }),
                        });
                        const result = await res.json();

                        if (!res.ok || result.status !== 'success') {
                            toast(result.message || 'Failed to create admin user');
                            return;
                        }

                        closeModal();
                        await loadAdminsFromAPI();
                        renderAdminUsersList();
                        toast('Admin user added');
                    } catch (err) {
                        console.error(err);
                        toast('Could not reach the server');
                    }
                })();
            }

        );

    };

// =========================================================
// EXPORT INSTITUTIONS
// =========================================================
$('exportInstitutions')
    .onclick =
    () => {

        const csv = [

            'Name,Type,Code,City,Status,Licenses',

            ...state.institutions.map(
                institution =>

                    `${institution.name},` +

                    `${institution.type},` +

                    `${institution.code},` +

                    `${institution.city},` +

                    `${institution.status},` +

                    `${
                        state.licenses.filter(
                            license =>
                                license.institutionId ===
                                institution.id
                        ).length
                    }`

            )

        ].join('\n');
        const blob =
            new Blob(
                [csv],
                {
                    type:
                        'text/csv'
                }
            );
        const link =
            document.createElement(
                'a'
            );
        link.href =
            URL.createObjectURL(
                blob
            );
        link.download =
            'sahasra-institutions.csv';
        link.click();
        toast(
            'CSV exported'
        );
    };
// =========================================================
// FILTER EVENTS
// =========================================================
[
    'registrySearch',
    'typeFilter',
    'statusFilter',
    'cityFilter'
]
.forEach(
    id => {

        $(id).addEventListener(
            'input',
            renderInstitutions
        );

    }
);
[
    'licenseSearch',
    'licenseInstitutionFilter',
    'licenseRoleFilter',
    'licenseStatusFilter',
    'licensePlanFilter'
]
.forEach(
    id => {
        $(id).addEventListener(
            'input',
            renderLicenses
        );
    }
);
[
    'analyticsRange',
    'analyticsInstitution',
    'analyticsRole',
    'analyticsPlan'
]
.forEach(
    id => {
        $(id).addEventListener(
            'change',
            renderAnalytics
        );
    }
);
$('auditSearch')
    .addEventListener(
        'input',
        renderAudit
    );
// =========================================================
// GLOBAL SEARCH
// =========================================================
// Previously only ever searched institutions, even though the
// placeholder promised "institutions, licenses". Now checks license
// codes too and routes to whichever page actually has a match.

$('globalSearch')
    .addEventListener(
        'input',
        event => {
            const query = event.target.value.trim();
            if (!query) return;

            const q = query.toLowerCase();
            const matchesInstitution = state.institutions.some(i =>
                i.name.toLowerCase().includes(q) || i.code.toLowerCase().includes(q)
            );
            const matchesLicense = state.licenses.some(l =>
                l.code.toLowerCase().includes(q)
            );

            if (!matchesInstitution && matchesLicense) {
                navigate('licenses');
                $('licenseSearch').value = query;
                renderLicenses();
            } else {
                navigate('institutions');
                $('registrySearch').value = query;
                renderInstitutions();
            }
        }
    );

// =========================================================
// TOPBAR: NOTIFICATIONS + ADMIN PROFILE MENU
// =========================================================

async function checkSystemStatus() {
    const dot = $('systemStatusDot'), text = $('systemStatusText'), sub = $('systemStatusSub');
    if (!dot || !text || !sub) return;
    const set = (color, t, s) => { dot.style.background = color; text.textContent = t; sub.textContent = s; };
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 8000);
    try {
        const res = await fetch(`${API_BASE}/health`, { cache: 'no-store', signal: ctrl.signal });
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.status === 'ok') set('#4ade80', 'System Online', 'All services operational');
        else if (res.ok) set('#f59e0b', 'Degraded', 'Some checks failing');
        else throw new Error('HTTP ' + res.status);
    } catch (err) {
        dot.style.animation = 'none';
        set('#dc2626', 'System Offline', err.name === 'AbortError' ? 'Backend not responding' : 'Backend unreachable');
    } finally {
        clearTimeout(timer);
    }
}

checkSystemStatus();
setInterval(checkSystemStatus, 15000);

function closeTopbarDropdowns() {
    $('notificationPanel').classList.add('hidden');
    $('adminProfileMenu').classList.add('hidden');
}

function updateNotificationDot() {
    const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
    const hasRecentFailure = (state.auditEvents || []).some(e =>
        e.event === 'invalid_code_attempt' && new Date(e.ts).getTime() >= dayAgo
    );
    $('notificationDot').style.display = hasRecentFailure ? 'inline-block' : 'none';
}

function renderNotificationPanel() {
    const events = (state.auditEvents || []).slice(0, 5);
    const listEl = $('notificationList');

    if (events.length === 0) {
        listEl.innerHTML = '<div class="topbar-empty">No recent activity yet.</div>';
    } else {
        listEl.innerHTML = events.map(e => {
            const item = auditEventToActivity(e);
            return `
                <div class="topbar-notification-item">
                    <strong>${item.title}</strong>
                    <small>${item.description} — ${formatRelativeTime(item.ts)}</small>
                </div>
            `;
        }).join('');
    }

    updateNotificationDot();
}

$('notificationBell').addEventListener('click', event => {
    event.stopPropagation();
    $('adminProfileMenu').classList.add('hidden');
    renderNotificationPanel();
    $('notificationPanel').classList.toggle('hidden');
});

$('notificationViewAll').addEventListener('click', () => {
    closeTopbarDropdowns();
    navigate('audit');
});

$('adminProfileBtn').addEventListener('click', event => {
    event.stopPropagation();
    $('notificationPanel').classList.add('hidden');
    $('adminProfileMenu').classList.toggle('hidden');
});

$('adminLogoutBtn').addEventListener('click', () => {
    clearAdminToken();
    bootstrapped = false;
    closeTopbarDropdowns();
    showLoginOverlay();
});

document.addEventListener('click', () => closeTopbarDropdowns());

// =========================================================
// KEYBOARD SHORTCUTS
// =========================================================
document.addEventListener(
    'keydown',
    event => {

        if ( (event.ctrlKey ||event.metaKey)  &&  event.key.toLowerCase() === 'k' ) {
            event.preventDefault();
            $('globalSearch')
                .focus();
        } if ( event.key ==='Escape') {
            closeModal();
        }
    }
);
// =========================================================
// RESPONSIVE CHART
// =========================================================
window.addEventListener(
    'resize',
    () => {
        if (
            $('analyticsPage')
                .classList
                .contains(
                    'active-page'
                )
        ) {
            renderAnalytics();
        }
    }
);
// =========================================================
// INITIAL LOAD
// =========================================================
renderDashboard();
loadOpenAIUsage();
renderInstitutions();
renderLicenses();
renderAnalytics();
renderRoles();
renderSettings();
populateAuditInstitutionFilter();
renderAudit();
let bootstrapped = false;
async function bootstrapAdmin() {
  if (!getAdminToken()) {
    // Not logged in yet — the login overlay is already shown.
    // handleAdminLogin() will call bootstrapAdmin() again after sign-in.
    return;
  }

  if (bootstrapped) return;
  bootstrapped = true;

  try {
    await loadInstitutionsFromAPI();
    await loadLicensesFromAPI();
    await loadAuditFromAPI();     // real audit events + real per-license usage counts
    await loadSettingsFromAPI();  // real admin-configured settings
    await loadAdminsFromAPI();    // real multi-admin accounts
    renderInstitutions();
    renderLicenses();
    updateNotificationDot();
  } catch (e) {
    console.error("Bootstrap failed:", e);
    bootstrapped = false; // allow retry after re-login
  }

  const initialPage = window.location.hash.replace('#', '') || 'dashboard';
  navigate(pages[initialPage] ? initialPage : 'dashboard');
}
bootstrapAdmin();