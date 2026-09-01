const KEY = 'sahasraAdminState';
const API_BASE = "http://127.0.0.1:8000";

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
    db_name: i.db_name
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
    usage: 0
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
    smtpHost: data.settings.smtp_host,
    smtpPort: data.settings.smtp_port,
    smtpUser: data.settings.smtp_user,
    smtpPassword: data.settings.smtp_password,
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
        $('settingsPage')

};


let currentAdminPage = 'dashboard';

function navigate(page) {

    currentAdminPage = page;

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

        settings: renderSettings

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

        '#6756e8',
        '#43a7e9',
        '#4bc39b',
        '#f0a44c',
        '#dc6269'

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
                                onclick="
                                    copyLicense(
                                        '${license.code}'
                                    )
                                "
                            >
                                Copy
                            </button>

                            <button
                                class="row-action"
                                onclick="
                                    editLicense(
                                        ${license.id}
                                    )
                                "
                            >
                                Edit
                            </button>

                            <button
                                class="row-action"
                                onclick="
                                    licenseAction(
                                        ${license.id},
                                        'Suspend'
                                    )
                                "
                            >
                                Suspend
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
                Object.assign(license, {
                    institutionId: Number(data.institutionId),
                    role: data.role,
                    plan: data.plan
                });

                addActivity('License updated', license.code);
                toast('License updated');
                save();
                closeModal();
                renderLicenses();
                renderDashboard();
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
// =========================================================
// ANALYTICS
// =========================================================

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
    ctx.strokeStyle = '#6756e8';
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

    const colors = ['#6756e8', '#43a7e9', '#f0a44c', '#dc6269', '#8a8a8a'];

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


    $('smtpHost').value = settings.smtpHost || '';
    $('smtpPort').value = settings.smtpPort || 587;
    $('smtpUser').value = settings.smtpUser || '';
    $('smtpPassword').value = settings.smtpPassword || '';
    $('alertEmailTo').value = settings.alertEmailTo || '';


    $('webhook')
        .value =
        settings.webhook;


    renderAdminUsersList();

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

function renderAudit() {

    const search =
        $('auditSearch')
            .value
            .toLowerCase();


    const rows =
        state.activities.filter(
            activity =>

                !search ||

                `${activity.title}
                ${activity.description}
                ${activity.actor}`
                    .toLowerCase()
                    .includes(search)
        );


    $('auditCount')
        .textContent =
        `${rows.length} events`;


    $('auditTable').innerHTML =

        rows
            .map(
                activity => `

                    <tr>

                        <td>
                            ${formatRelativeTime(activity.ts)}
                        </td>

                        <td>
                            <strong>
                                ${activity.title}
                            </strong>
                        </td>

                        <td>
                            ${activity.description}
                        </td>

                        <td>
                            ${activity.actor}
                        </td>

                    </tr>

                `
            )
            .join('')

        ||

        `

            <tr>

                <td colspan="4">

                    <div class="empty">
                        No matching events.
                    </div>

                </td>

            </tr>

        `;

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

$('addInstitution')
    .onclick =
    () => openInstitution();


$('dashboardAdd')
    .onclick =
    () => openInstitution();


$('generateLicense')
    .onclick =
    () => openLicense();


$('editPermissions')
    .onclick =
    () => editRole('Admin');


$('refreshDashboard')
    .onclick =
    () => {

        renderDashboard();

        toast(
            'Dashboard refreshed'
        );

    };


// =========================================================
// SETTINGS SAVE
// =========================================================

$('saveSettings')
    .onclick =
    () => {

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
            smtp_host: $('smtpHost').value,
            smtp_port: Number($('smtpPort').value) || 587,
            smtp_user: $('smtpUser').value,
            smtp_password: $('smtpPassword').value,
            alert_email_to: $('alertEmailTo').value,
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
renderInstitutions();
renderLicenses();
renderAnalytics();
renderRoles();
renderSettings();
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

  navigate("dashboard");
}
bootstrapAdmin();