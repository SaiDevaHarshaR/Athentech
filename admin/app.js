const KEY = 'sahasraAdminState';
const API_BASE = "http://127.0.0.1:8000";
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

        time: 'Just now',

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


function navigate(page) {

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

    const active =
        activeLicenses();


    const licenseCount =
        active.length;


    const hospitals =
        state.institutions.filter(
            x => x.status === 'Active'
        ).length;


    const queries =
        state.licenses.reduce(
            (sum, license) =>
                sum + license.usage,
            0
        ) + 18420;


    const failed =
        Math.max(
            2,
            Math.round(
                licenseCount * 0.18
            )
        );


    $('activeLicenses')
        .textContent =
        licenseCount;


    $('activeHospitals')
        .textContent =
        hospitals;


    $('queriesToday')
        .textContent =
        queries.toLocaleString();


    $('totalQueries')
        .textContent =
        queries.toLocaleString();


    $('failedValidations')
        .textContent =
        failed;


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
                        ${activity.time}
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

            const object = {

                id:
                    institution
                        ? institution.id
                        : Date.now(),

                name:
                    data.name.trim(),

                code:
                    data.code
                        .trim()
                        .toUpperCase(),

                type:
                    data.type,

                city:
                    data.city.trim(),

                status:
                    data.status

            };


            if (institution) {

                Object.assign(
                    institution,
                    object
                );


                addActivity(

                    'Institution updated',

                    `${object.name} was updated`

                );


                toast(
                    'Institution updated'
                );

            }

            else {

                state.institutions.push(
                    object
                );


                addActivity(

                    'Institution registered',

                    `${object.name} was added`

                );


                toast(
                    'Institution added'
                );

            }


            save();

            closeModal();

            renderInstitutions();

            renderDashboard();

        }

    );

}


window.editInstitution =
    id => {

        openInstitution(
            inst(id)
        );

    };


window.toggleInstitution =
    id => {

        const institution =
            inst(id);


        institution.status =

            institution.status ===
            'Inactive'

                ? 'Active'
                : 'Inactive';


        addActivity(

            institution.status === 'Active'
                ? 'Institution activated'
                : 'Institution deactivated',

            institution.name

        );


        save();

        renderInstitutions();

        renderDashboard();


        toast(

            `${institution.name} is ` +
            `${institution.status}`

        );

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

            if (
                option.value !== 'all'
            ) {

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
                    const response = await fetch(`${API_BASE}/admin/licenses/generate`, {
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


window.licenseAction =
    (id, action) => {

        const license =
            state.licenses.find(
                x => x.id === id
            );


        if (!license) return;


        if (action === 'Suspend') {

            license.status =
                'Suspended';

        }


        addActivity(

            `License ${action.toLowerCase()}`,

            license.code

        );


        save();

        renderLicenses();

        renderDashboard();


        toast(
            `License ${action.toLowerCase()}ed`
        );

    };


// =========================================================
// ANALYTICS
// =========================================================

function renderAnalytics() {

    fillSelect(

        'analyticsInstitution',

        state.institutions.map(
            institution =>
                String(institution.id)
        ),

        'Institution'

    );


    const institutionSelect =
        $('analyticsInstitution');


    [...institutionSelect.options]
        .forEach(option => {

            if (
                option.value !== 'all'
            ) {

                option.textContent =
                    inst(option.value)
                        ?.name ||
                    option.value;

            }

        });


    fillSelect(
        'analyticsRole',
        roles,
        'Role'
    );


    fillSelect(

        'analyticsPlan',

        [
            'Standard',
            'Professional',
            'Enterprise'
        ],

        'Plan'

    );


    const range =
        Number(
            $('analyticsRange').value
        );


    const institution =
        institutionSelect.value;


    const role =
        $('analyticsRole').value;


    const plan =
        $('analyticsPlan').value;


    const licenses =
        state.licenses.filter(
            license =>

                (
                    institution === 'all' ||

                    String(
                        license.institutionId
                    ) === institution
                )

                &&

                (
                    role === 'all' ||

                    license.role === role
                )

                &&

                (
                    plan === 'all' ||

                    license.plan === plan
                )
        );


    const base =
        licenses.reduce(
            (sum, license) =>
                sum + license.usage,
            0
        );


    const queries =
        base + range * 730;


    const codes =
        licenses.length;


    const average =
        codes
            ? (queries / codes).toFixed(1)
            : '0.0';


    $('analyticsQueries')
        .textContent =
        queries.toLocaleString();


    $('analyticsCodes')
        .textContent =
        codes;


    $('analyticsAverage')
        .textContent =
        average;


    $('analyticsPeak')
        .textContent =
        '11 AM';


    drawLineChart(
        queries,
        range
    );


    renderRoleBars(
        licenses
    );


    renderTopInstitutions(
        licenses
    );


    renderFailureChart();

}


// =========================================================
// LINE CHART
// =========================================================

function drawLineChart(
    total,
    days
) {

    const canvas =
        $('queryChart');


    const ctx =
        canvas.getContext('2d');


    const dpr =
        window.devicePixelRatio || 1;


    const width =
        canvas.clientWidth;


    const height =
        220;


    canvas.width =
        width * dpr;


    canvas.height =
        height * dpr;


    ctx.scale(
        dpr,
        dpr
    );


    ctx.clearRect(
        0,
        0,
        width,
        height
    );


    const points =

        days <= 7
            ? 7
            : days <= 30
                ? 12
                : 15;


    const values =

        Array.from(
            { length: points },

            (_, index) =>

                Math.round(

                    total *

                    (
                        0.55 +

                        Math.sin(
                            index * 1.15
                        ) * 0.12 +

                        index /
                        (points * 2)
                    )

                    /

                    points

                )

        );


    const max =
        Math.max(...values) * 1.18;


    const min =
        0;


    // Grid

    ctx.strokeStyle =
        '#ececf1';


    ctx.lineWidth =
        1;


    for (
        let y = 0;
        y < 5;
        y++
    ) {

        const yy =
            20 +
            y *
            (height - 50) /
            4;


        ctx.beginPath();

        ctx.moveTo(
            35,
            yy
        );

        ctx.lineTo(
            width - 10,
            yy
        );

        ctx.stroke();

    }


    // Line

    ctx.beginPath();


    values.forEach(
        (value, index) => {

            const x =
                35 +

                index *
                (width - 50) /
                (points - 1);


            const y =

                height -
                30 -

                (
                    value - min
                )

                /

                (
                    max - min
                )

                *

                (
                    height - 60
                );


            if (index === 0) {

                ctx.moveTo(
                    x,
                    y
                );

            }

            else {

                ctx.lineTo(
                    x,
                    y
                );

            }

        }
    );


    ctx.strokeStyle =
        '#6756e8';


    ctx.lineWidth =
        3;


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

    const reasons = [

        ['Invalid code', 42],

        ['Rate limit', 26],

        ['Expired license', 18],

        ['Other', 14]

    ];


    const colors = [

        '#6756e8',

        '#43a7e9',

        '#f0a44c',

        '#dc6269'

    ];


    let current = 0;

    const parts = [];


    reasons.forEach(
        (reason, index) => {

            parts.push(

                `${colors[index]} ` +

                `${current}% ` +

                `${current + reason[1]}%`

            );


            current +=
                reason[1];

        }
    );


    $('failurePie').style.background =

        `conic-gradient(${parts.join(',')})`;


    $('failureLegend').innerHTML =

        reasons
            .map(
                (reason, index) => `

                    <div class="legend-item">

                        <span
                            class="legend-dot"
                            style="
                                background:
                                ${colors[index]}
                            "
                        ></span>

                        <span>
                            ${reason[0]}
                        </span>

                        <span class="legend-value">
                            ${reason[1]}%
                        </span>

                    </div>

                `
            )
            .join('');

}


// =========================================================
// ROLES & PERMISSIONS
// =========================================================

function renderRoles() {

    $('roleRows').innerHTML =

        roles
            .map(
                role => `

                    <div class="role-row">

                        <div class="role-name">
                            ${role}
                        </div>

                        <div class="chips">

                            ${
                                rolePermissions[role]
                                    .map(
                                        permission => `

                                            <span class="chip">
                                                ${permission}
                                            </span>

                                        `
                                    )
                                    .join('')
                            }

                        </div>

                        <button
                            class="row-action"
                            onclick="
                                editRole(
                                    '${role}'
                                )
                            "
                        >
                            Edit
                        </button>

                    </div>

                `
            )
            .join('');

}


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


    $('webhook')
        .value =
        settings.webhook;


    $('adminUsers').innerHTML =

        state.admins
            .map(
                (admin, index) => `

                    <div class="admin-user">

                        <div>

                            <strong>
                                ${admin.name}
                            </strong>

                            <small>
                                ${admin.email}
                                ·
                                ${admin.role}
                            </small>

                        </div>

                        <button
                            class="row-action"
                            onclick="
                                removeAdmin(
                                    ${index}
                                )
                            "
                        >
                            Remove
                        </button>

                    </div>

                `
            )
            .join('');

}


window.removeAdmin =
    index => {

        state.admins.splice(
            index,
            1
        );


        save();

        renderSettings();

        toast(
            'Admin user removed'
        );

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
                            ${activity.time}
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

        state.settings = {

            validity:
                $('licenseValidity')
                    .value,

            normalMode:
                $('normalMode')
                    .checked,

            rateLimit:
                Number(
                    $('rateLimit')
                        .value
                ),

            blockedPatterns:
                $('blockedPatterns')
                    .value,

            redaction:
                $('redaction')
                    .checked,

            emailAlerts:
                $('emailAlerts')
                    .checked,

            webhook:
                $('webhook')
                    .value

        };


        save();


        addActivity(

            'Settings updated',

            'Administrative configuration changed'

        );


        toast(
            'Settings saved'
        );

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

                        <label>
                            Name
                        </label>

                        <input
                            name="name"
                            required
                        >

                    </div>


                    <div class="form-group">

                        <label>
                            Email
                        </label>

                        <input
                            name="email"
                            type="email"
                            required
                        >

                    </div>


                    <div class="form-group">

                        <label>
                            Role
                        </label>

                        <select name="role">

                            <option>
                                Admin
                            </option>

                            <option>
                                Super Admin
                            </option>

                        </select>

                    </div>

                </div>

            `,

            data => {

                state.admins.push(
                    data
                );


                save();

                closeModal();

                renderSettings();

                toast(
                    'Admin user added'
                );

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

$('globalSearch')
    .addEventListener(
        'input',
        event => {

            const query =
                event.target.value.trim();


            if (!query) return;


            navigate(
                'institutions'
            );


            $('registrySearch')
                .value =
                query;


            renderInstitutions();

        }
    );


// =========================================================
// KEYBOARD SHORTCUTS
// =========================================================

document.addEventListener(
    'keydown',
    event => {

        if (

            (event.ctrlKey ||
                event.metaKey)

            &&

            event.key.toLowerCase()
                === 'k'

        ) {

            event.preventDefault();

            $('globalSearch')
                .focus();

        }


        if (
            event.key ===
            'Escape'
        ) {

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