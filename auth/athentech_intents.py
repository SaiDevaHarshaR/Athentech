"""Fast AthenTech FAQ intents — fuller answers, zero LLM/scrape."""
from __future__ import annotations
import re
from typing import Optional

A = {}
A['contact'] = '📞 **Contact AthenTech**\n\nYou can reach AthenTech through sales, support, or the website contact form.\n• **Sales:** +91 970 5480 699 · sales@athentech.co.in\n• **Support / IVR:** +91 8096 247 365 · support@athentech.co.in\n• **Head office:** Flat No. 102, Shiva Sai Sannidhi, Opp. Sai Baba Temple, Dwarakapuri, Punjagutta, Hyderabad, Telangana 500082\n• **Cities:** Hyderabad · Bangalore · Vijayawada · Vizag\nUse sales for demos and new projects; use support for existing client issues.\n\n🔗 https://www.athentech.co.in/contact/'
A['sales'] = '💼 **Sales team**\n\nFor product demos, pricing, and new hospital or lab projects, contact the sales team.\n• Phone: **+91 970 5480 699**\n• Email: **sales@athentech.co.in**\nShare your facility type (hospital, diagnostic chain, college), approximate size, and whether you need HIS, LIS, or both.\nYou can also submit **Request Demo** or **Get a Quote** on the website.\nSales will typically schedule a walkthrough of Sahasra on your use case.\n\n🔗 https://www.athentech.co.in/contact/'
A['support'] = '🛠️ **Support**\n\nExisting clients can reach Athentech support on the published support lines.\n• **Support / IVR:** +91 8096 247 365\n• **Email:** support@athentech.co.in\nThe platform messaging includes **24×7** support as part of the service model.\nFor new purchases or demos, use sales instead: +91 970 5480 699 · sales@athentech.co.in\nHave your institution name and a short description of the issue ready when you call.\n\n🔗 https://www.athentech.co.in/contact/'
A['address'] = '📍 **Head office address**\n\nAthenTech’s head office is in Hyderabad:\nFlat No. 102, Shiva Sai Sannidhi,\nOpposite Sai Baba Temple, Dwarakapuri,\nPunjagutta, Hyderabad, Telangana **500082**.\nThe company also operates from Bangalore, Vijayawada and Vizag.\nFor visits or courier, confirm with sales or support before you travel.\n\n🔗 https://www.athentech.co.in/contact/'
A['cities'] = '🗺️ **Where AthenTech operates**\n\nAthenTech is headquartered in **Hyderabad** and is also present in:\n• Bangalore\n• Vijayawada\n• Vizag (Visakhapatnam)\nThe site also refers to coverage across **18+ districts**.\nMulti-location hospitals and lab chains can be managed from one Sahasra console.\n\n🔗 https://www.athentech.co.in/contact/'
A['about'] = '🏥 **About AthenTech**\n\n**ATHEN TECH India Pvt Ltd** (brand: Athentech / Sahasra) is a healthcare IT company based in Hyderabad.\nThey have **20+ years** of experience building hospital and laboratory software.\nPublic figures on the site include **592+ healthcare clients**, **43 integrated modules**, and **950+ diagnostic report formats**.\nThe Sahasra suite runs HIS, LIS, RIS, EMR, pharmacy and ERP on **one patient record**.\nFocus areas include hospitals, diagnostic centres, medical colleges, clinics and fertility centres.\nPrimary website and company story are published on athentech.co.in.\n\n🔗 https://www.athentech.co.in/about/'
A['mission'] = '🎯 **Mission**\n\nAthenTech’s stated mission is to provide smart business solutions so customers become more competitive.\nThe goal is to help organisations reach the next level of operational excellence.\nIn healthcare, that means unified clinical and administrative workflows on Sahasra.\nImplementation is positioned as configuration and training, not only software delivery.\nVision and mission details are on the corporate About section of the website.\nFor how this applies to your hospital or lab, speak with sales on a demo call.\n\n🔗 https://www.athentech.co.in/about/vision-mission/'
A['vision'] = '🔭 **Vision**\n\nAthenTech’s vision is to transform healthcare through technology with strong customer care.\nThey emphasise innovative process frameworks and reusable knowledge so clients stay ahead.\nPractically, Sahasra aims to keep clinical, lab, pharmacy and finance data on one record.\nStandards such as ABDM, NABH/NABL orientation and HL7/FHIR/DICOM support that direction.\nFull vision/mission text is published on the website About pages.\nAsk sales how the roadmap maps to your accreditation or multi-branch plans.\n\n🔗 https://www.athentech.co.in/about/vision-mission/'
A['why'] = '✅ **Why choose AthenTech**\n\nLong domain focus: **20+ years** in healthcare IT from Hyderabad.\nScale signals on the site: **592+ clients**, **43 modules**, **950+ diagnostic report formats**.\nOne platform story: HIS, LIS, RIS, EMR, pharmacy and ERP share a patient record.\nCompliance-oriented features: ABDM V3, NABH/NABL/CAP workflow support, HL7/FHIR/DICOM.\nDeployment flexibility: cloud or on-premise, single site or multi-location.\nImplementation stance: Athentech teams handle configuration, training and go-live support.\n\n🔗 https://www.athentech.co.in/about/why-choose-us/'
A['stats'] = '📊 **AthenTech at a glance**\n\nPublic numbers highlighted on athentech.co.in include:\n• **592+** healthcare clients\n• **20+** years in the market\n• **43** integrated Sahasra modules\n• **950+** diagnostic report formats\n• **18+** districts · ABDM (V3) · NABH / NABL / CAP oriented workflows\n\n🔗 https://www.athentech.co.in/about/'
A['demo'] = '🚀 **Request a demo**\n\nTo see Sahasra in action, request a guided demo from the sales team.\n• Call **+91 970 5480 699** or email **sales@athentech.co.in**\n• Or use **Request Demo** on the website contact page\nMention whether you are a hospital, diagnostic chain, clinic or medical college.\nShare approximate size (beds, branches, daily samples) and priority modules (HIS, LIS, RIS…).\nSales will usually schedule a walkthrough tailored to that workflow.\n\n🔗 https://www.athentech.co.in/contact/'
A['quote'] = '📝 **Get a quote**\n\nCommercial proposals are prepared after understanding your scope.\nTypical inputs: modules required, number of users, number of locations, cloud vs on-prem.\nInterfaces (lab analyzers, Tally, PACS, WhatsApp) also affect sizing.\nContact **sales@athentech.co.in** or **+91 970 5480 699** with those details.\nYou can also submit **Get a Quote** on the public contact form.\nThere is no single public price list; quotes are facility-specific.\n\n🔗 https://www.athentech.co.in/contact/'
A['pricing'] = '💰 **Pricing**\n\nAthenTech does not publish a fixed public price card for Sahasra.\nCost depends on product mix (HIS, LIS, RIS, ERP, Campus), user counts and sites.\nHosting model (cloud vs on-premise) and third-party interfaces change the commercial picture.\nAccreditation, multi-branch and analyzer integration needs should be called out early.\nFor a realistic estimate, speak to sales with your facility profile.\nSales: +91 970 5480 699 · sales@athentech.co.in\n\n🔗 https://www.athentech.co.in/contact/'
A['website'] = '🌐 **Website**\n\nThe official company website is **https://www.athentech.co.in/**.\nKey sections include About, Solutions, Modules, Products, Features, Industries, Clients, Support and Contact.\nYou can request a demo or quote from the Contact / Request Demo actions on the site.\nProduct detail for HIS, LIS, RIS and related solutions is linked from Solutions and Products.\nFor live help, use the published sales and support numbers on the site header.\nBookmark the contact page if you are evaluating Sahasra for your organisation.\n\n🔗 https://www.athentech.co.in/'
A['products'] = '📦 **Sahasra product family**\n\nAthenTech’s healthcare line is the **Sahasra** suite:\n1. **HISGenX** — full hospital information system (43 modules)\n2. **LIS GenX** — laboratory information system for labs and chains\n3. **RIS** — radiology with PACS / DICOM / tele-radiology\n4. **ERP** — finance, HR, procurement, inventory, MIS\n5. **Campus 360** — medical college + teaching hospital (MCHIMS)\n6. **Mobile apps** — doctor, patient and management experiences\n\n🔗 https://www.athentech.co.in/products/'
A['his'] = '🏨 **Sahasra HISGenX**\n\nHISGenX is Athentech’s web **Hospital Information System** for nursing homes through super-specialty hospitals.\nIt is built around **one patient record** shared by front desk, doctors, lab, pharmacy and accounts.\nCoverage includes OPD, IPD, OT, nursing, billing, insurance and EMR-style clinical documentation.\nIt supports multi-location groups and can run cloud-hosted or on-premise.\nABDM (V3) integration and NABH-oriented workflows are part of the platform story.\nAsk sales for a hospital-focused demo with your bed strength and department list.\n\n🔗 https://www.athentech.co.in/solutions/hospital-information-system/'
A['lis'] = '🧪 **Sahasra LIS GenX**\n\nLIS GenX is the **Laboratory Information System** for pathology labs, hospital labs and multi-branch networks.\nCapabilities called out include barcode samples, bi-directional analyzers and auto-validation.\nLabs get TAT monitoring and NABL-oriented reporting workflows.\nResults can be delivered via portal, WhatsApp and SMS in the engagement layer.\nABDM integration is documented for LIS GenX alongside HISGenX.\nDiagnostic chains often start here, optionally with RIS for imaging centres.\n\n🔗 https://www.athentech.co.in/solutions/laboratory-information-system/'
A['ris'] = '📡 **Sahasra RIS**\n\nSahasra **RIS** is the Radiology Information System in the Athentech suite.\nIt is described with **PACS**, **DICOM** and tele-radiology support.\nImaging workflows connect to the wider hospital or diagnostic platform rather than standing alone.\nHospitals typically pair RIS with HIS; imaging centres may pair RIS with LIS.\nIntegration details (modalities, PACS vendor) should be confirmed in a technical demo.\nContact sales to scope radiology for your centre.\n\n🔗 https://www.athentech.co.in/solutions/radiology-information-system/'
A['erp'] = '📒 **Sahasra ERP**\n\nSahasra ERP covers finance, HR and payroll, procurement, inventory and assets for healthcare organisations.\nThe site highlights **250+ MIS reports** and **Tally** integration.\nMulti-location roll-ups help groups see consolidated operations and finance.\nERP is part of the same Sahasra platform as clinical modules, not a disconnected package.\nUseful when hospitals want clinical activity and accounts on aligned data.\nDiscuss chart of accounts and Tally hand-off with sales during evaluation.\n\n🔗 https://www.athentech.co.in/products/'
A['campus'] = '🎓 **Campus 360 (MCHIMS)**\n\nCampus 360 is Athentech’s **Medical College & Hospital** information management offering.\nIt combines teaching-hospital clinical care with academic administration needs.\nMedical colleges that run attached hospitals use this to keep both sides aligned.\nIt sits in the Sahasra family so clinical modules remain consistent with HIS-style workflows.\nScope (students, departments, hospital beds) should be shared for a proper demo.\nSales: +91 970 5480 699 · sales@athentech.co.in\n\n🔗 https://www.athentech.co.in/'
A['mobile'] = '📱 **Sahasra mobile apps**\n\nSahasra includes mobile experiences for doctors, patients and management.\nApps are described for Android, iOS and tablet use cases.\nLeadership can use management / MD-style dashboards for branch ops and finance visibility.\nPatients get digital access patterns such as appointments and reports via the experience layer.\nMobile is part of the broader platform (portal, WhatsApp, kiosks) rather than a standalone app only.\nConfirm which apps are licensed in your proposal with sales.\n\n🔗 https://www.athentech.co.in/solutions/mobile-applications/'
A['pharmacy'] = '💊 **Pharmacy management**\n\nPharmacy in Sahasra is integrated with the patient record, not a siloed counter system only.\nDispensing links to clinical orders, stock and billing where those modules are deployed.\nHospitals use it to keep medication history aligned with OPD/IPD care.\nStores and procurement modules complement pharmacy for inventory control.\nExact formulary and GST/billing rules should be configured at implementation time.\nAsk for a pharmacy walkthrough in your HIS demo.\n\n🔗 https://www.athentech.co.in/solutions/pharmacy-management/'
A['emr'] = '📋 **EMR / EHR**\n\nElectronic medical records in Sahasra sit on the **same patient record** as registration, IP care, lab and pharmacy.\nThe aim is continuity of notes and history without a separate disconnected EMR product.\nClinicians work inside the hospital workflows already used for OPD and wards.\nThis supports the “one patient record” message used across the AI/platform pages.\nDepth of clinical templates depends on configuration during implementation.\nSee the EMR solution page and validate screens in a live demo.\n\n🔗 https://www.athentech.co.in/solutions/electronic-medical-records/'
A['bloodbank'] = '🩸 **Blood bank management**\n\nSahasra includes a blood bank management solution for hospital blood bank workflows.\nIt is positioned as integrated with the wider hospital platform.\nTypical needs—donor/component tracking and issue to wards—should be confirmed in discovery.\nPair it with HIS inpatient and OT modules when the hospital runs a full surgical load.\nRegulatory and labelling practices must be configured to local policy.\nRequest blood bank in your module list when speaking to sales.\n\n🔗 https://www.athentech.co.in/solutions/blood-bank-management/'
A['ot'] = '수술실 **OT management**\n\nOperation theatre management is part of Sahasra HIS clinical/ops modules.\nIt supports theatre scheduling and coordination tied to the inpatient and billing record.\nHospitals use it so surgical activity is not tracked on spreadsheets outside the system.\nCombine with IPD, nursing, pharmacy and billing for end-to-end operative care.\nDetailed checklist and preference-card setup happens during implementation.\nInclude OT in demo scenarios if surgery is a major revenue line for you.\n\n🔗 https://www.athentech.co.in/solutions/ot-management/'
A['nursing'] = '👩\u200d⚕️ **Nursing station**\n\nThe nursing station module supports ward-level documentation and care coordination in HIS.\nNurses work against the same patient record as doctors, lab and pharmacy.\nThis reduces duplicate charts between nursing and medical notes.\nIt fits inpatient and day-care ward operations in multi-specialty hospitals.\nTraining for ward staff is part of Athentech’s implementation emphasis.\nAsk for a nursing workflow demo with your ward structure.\n\n🔗 https://www.athentech.co.in/solutions/nursing-station-management/'
A['opd'] = '🚶 **OPD management**\n\nOPD covers registration, appointments, consultation and outpatient billing.\nOrders flow toward lab, radiology and pharmacy on the shared patient record.\nIt is a core HISGenX module for high-volume outpatient departments.\nAppointment and portal options extend OPD into digital front-door channels.\nTariffs and doctor schedules are configured in masters during setup.\nDemo OPD with your specialty mix when evaluating Sahasra.\n\n🔗 https://www.athentech.co.in/modules/opd-management/'
A['ipd'] = '🛏️ **IPD management**\n\nIPD handles admission, bed allocation, ward care, investigations, billing and discharge.\nIt connects nursing, OT, pharmacy and diagnostics around one inpatient stay.\nBed occupancy and ward operations are visible to management dashboards on the platform story.\nInsurance/credit billing can follow the clinical activity when finance modules are enabled.\nSuitable for nursing homes up to large multi-specialty hospitals.\nShare bed strength and ward list with sales for sizing.\n\n🔗 https://www.athentech.co.in/modules/ipd-management/'
A['modules'] = '🧩 **43 integrated modules**\n\nSahasra is marketed with **43 integrated modules** on one platform.\nExamples span masters, admin, OPD, IPD, OT, nursing, EMR, laboratory, radiology and pharmacy.\nBack-office coverage includes stores, procurement, billing/insurance, finance, HR and payroll.\nDigital channels include patient portal, mobile apps, messaging and MIS/analytics.\nYou rarely deploy all 43 on day one—modules are selected for your facility type.\nBrowse the full catalogue on the modules page, then prioritise with sales.\n\n🔗 https://www.athentech.co.in/modules/'
A['inventory'] = '📦 **Inventory & procurement**\n\nInventory and procurement cover medical/general stores, indents, purchase orders and GRN.\nVendor management and stock valuation support hospital supply chains.\nThese modules align with pharmacy and finance so stock and accounts stay consistent.\nMulti-location groups can standardise item masters while operating per site.\nImplementation defines item categories, approval chains and valuation method.\nRaise inventory needs early if consumables are a major cost centre for you.\n\n🔗 https://www.athentech.co.in/solutions/inventory-procurement/'
A['hr'] = '👥 **HR & payroll**\n\nHR and payroll modules sit inside Sahasra ERP for healthcare workforces.\nThey support staff administration alongside finance rather than as a pure standalone HRMS story.\nHospitals benefit when roster and pay data align with the same organisational masters.\nExact statutory payroll rules must be configured for your state and policies.\nDiscuss employee count and pay cycles in the commercial discovery call.\nSales: +91 970 5480 699 · sales@athentech.co.in\n\n🔗 https://www.athentech.co.in/solutions/hr-payroll/'
A['finance'] = '💳 **Finance & accounts**\n\nFinance modules handle credit billing, taxation-oriented processes and management reporting.\nTally-ready integration is highlighted for accounting hand-off.\nMIS packages (250+ reports called out on ERP) support leadership reviews.\nClinical activity can drive billing when HIS/LIS modules are in the same deployment.\nChart of accounts and tax setup are implementation tasks with your finance team.\nRequest a finance-focused demo if accounts is your buying sponsor.\n\n🔗 https://www.athentech.co.in/solutions/finance-accounts/'
A['portal'] = '🌐 **Patient portal**\n\nThe patient portal is part of Sahasra’s experience layer for consumers of care.\nFeatures described include appointments, online reports, e-prescriptions and payments.\nTeleconsultation is also referenced as part of the digital front door.\nIt works with the same platform that runs clinical and lab operations behind the scenes.\nBranding and service catalogue for the portal are configured per institution.\nUseful for hospitals and labs that want fewer phone-only report queries.\n\n🔗 https://www.athentech.co.in/solutions/patient-portal/'
A['industries'] = '🏛️ **Industries served**\n\nAthenTech positions Sahasra across several care settings:\n• Multi-specialty **hospitals** — full department unification\n• **Diagnostic centres / chains** — LIS, RIS, multi-branch, home collection patterns\n• **Medical colleges** — Campus 360 for academics + hospital\n• **Clinics & polyclinics** — lighter HIMS footprint with room to grow\n• **IVF & fertility** centres — specialised industry workflows\n\n🔗 https://www.athentech.co.in/industries/'
A['hospital'] = '🏥 **For hospitals**\n\nHospitals are a primary Sahasra HISGenX audience—from nursing homes to super-specialty centres.\nOne patient record connects OPD, IPD, OT, nursing, diagnostics, pharmacy and billing.\nMulti-location groups can standardise processes while operating each branch.\nABDM and NABH-oriented features support national and quality programmes.\nImplementation includes workflow setup and training, not only installation.\nBook a hospital demo with bed strength and specialty mix ready.\n\n🔗 https://www.athentech.co.in/solutions/hospital-information-system/'
A['diagnostic'] = '🧬 **For diagnostic centres**\n\nDiagnostic labs and chains use **LIS GenX**, optionally with **RIS** for imaging.\nStrengths include analyzer interfacing, TAT control, multi-branch operations and digital report delivery.\nHome collection style operations are part of the diagnostic industry narrative on the site.\nNABL-oriented reporting and ABDM support are relevant for organised lab networks.\nPortal and WhatsApp channels reduce manual report dispatch effort.\nShare daily sample volume and branch count when requesting a lab demo.\n\n🔗 https://www.athentech.co.in/solutions/laboratory-information-system/'
A['college'] = '🎓 **For medical colleges**\n\nMedical colleges with attached hospitals are addressed via **Campus 360 (MCHIMS)**.\nThe idea is to keep academic administration and clinical hospital operations on one stack.\nTeaching hospitals still need robust HIS-style clinical modules for patient care.\nDiscovery should cover student/admin scope and hospital bed strength together.\nAthentech can walk through college-specific screens in a tailored demo.\nContact sales to evaluate Campus 360 for your campus.\n\n🔗 https://www.athentech.co.in/'
A['clinic'] = '🏠 **For clinics & polyclinics**\n\nClinics and polyclinics can start with a lighter Sahasra HIMS footprint.\nThe site describes affordable options that can run online or offline depending on setup.\nAs the practice grows, modules can expand toward fuller hospital capability.\nOPD, billing and basic diagnostics connectivity are common starting points.\nConfirm exact starter packs with sales—packaging is commercial, not only technical.\nCall +91 970 5480 699 to match a clinic-sized deployment.\n\n🔗 https://www.athentech.co.in/industries/'
A['ivf'] = '🌱 **IVF & fertility centres**\n\nIVF and fertility centres are listed among Sahasra industry solutions.\nThese centres need specialised clinical and operational workflows beyond generic OPD.\nEvaluate module fit during a discovery call rather than assuming a generic hospital pack.\nIntegration with lab processes may matter when andrology/embryology labs are on site.\nCommercial scope depends on cycle volume and multi-site plans.\nAsk sales for the fertility industry walkthrough.\n\n🔗 https://www.athentech.co.in/industries/'
A['abdm'] = '🛡️ **ABDM (Ayushman Bharat Digital Mission) V3**\n\nSahasra **HISGenX** and **LIS GenX** support documentation-based **ABDM V3** integration.\nCapabilities described include ABHA-enabled registration and verification.\nHospital and lab records can be linked to ABHA with consent-based digital sharing.\nThis aligns Sahasra with national digital health directions in India.\nExact facility registration and ABDM workspace setup are project tasks at go-live.\nRead the ABDM page and confirm scope in your implementation plan.\n\n🔗 https://www.athentech.co.in/abdm-integrated-his/'
A['nabh'] = '🏅 **NABH / NABL / CAP**\n\nAthenTech markets accreditation support inside daily workflows, not only year-end paperwork.\nHospitals lean on **NABH**-oriented process support in HIS workflows.\nLaboratories lean on **NABL**-oriented lab quality and reporting practices.\n**CAP** support is also referenced in platform feature messaging.\nQuality boards and operational discipline still depend on how you configure and use the system.\nRaise accreditation goals explicitly during demo and implementation planning.\n\n🔗 https://www.athentech.co.in/features/'
A['hl7'] = '🔗 **HL7, FHIR and open APIs**\n\nSahasra platform features include **HL7** clinical data exchange and **FHIR** support.\n**DICOM/PACS** covers imaging interoperability with radiology workflows.\nOpen APIs are described for Tally, biometric devices, medical equipment and third-party apps.\nLab analyzer bi-directional interfacing is a major LIS integration theme.\nEach interface needs vendor details and test plans during implementation.\nBring your device/vendor list to the technical discovery session.\n\n🔗 https://www.athentech.co.in/features/'
A['pacs'] = '🖼️ **PACS / DICOM**\n\nImaging is delivered into clinician workflows using **PACS** and **DICOM** standards.\nThis pairs with Sahasra RIS and the broader hospital or diagnostic deployment.\nRadiologists and referring doctors stay inside connected operational processes.\nPACS vendor choice and network design remain part of the project architecture.\nTele-radiology is referenced alongside RIS capabilities on the site.\nSchedule a radiology-focused demo if imaging is central to your business.\n\n🔗 https://www.athentech.co.in/features/'
A['cloud'] = '☁️ **Cloud or on-premise**\n\nSahasra can be deployed on **cloud** infrastructure or **on your own servers**.\nThe product family is positioned as the same offering either way.\nMulti-location hospitals and labs still manage branches from a central console model.\nHosting choice affects IT ownership, uptime responsibility and commercial structure.\nDiscuss data residency and backup/DR expectations during contracting.\nSales can recommend a model after understanding your IT constraints.\n\n🔗 https://www.athentech.co.in/features/'
A['security'] = '🔒 **Security**\n\nPlatform security messaging includes role-based access control and encryption.\nTamper-evident audit trails support accountability on sensitive clinical and billing actions.\nBackups and disaster-recovery posture are part of the operational story.\nISO 27001–oriented security is referenced in feature communications.\nActual controls depend on deployment (cloud vs on-prem) and your admin policies.\nRequest a security questionnaire response from sales for formal RFPs.\n\n🔗 https://www.athentech.co.in/features/'
A['whatsapp'] = '💬 **WhatsApp & messaging**\n\nSahasra includes messaging integrations such as **WhatsApp Business API** for engagement.\nLabs especially use digital channels to deliver reports and reduce queue pressure.\nMessaging sits in the experience layer with portal and mobile apps.\nTemplates, opt-in and TRAI/WhatsApp policy compliance must be handled at project time.\nThe public site header also promotes WhatsApp Business Signup for business onboarding.\nAsk sales how WhatsApp is licensed and operated in your region.\n\n🔗 https://www.athentech.co.in/'
A['ai'] = '🤖 **AI on Sahasra HISGenX**\n\nSahasra HISGenX is positioned as an AI-aware “Digital Brain of Modern Healthcare.”\nExamples include clinical report auto-drafts and coding suggestions (ICD/CPT style).\nRevenue intelligence and predictive dashboards (footfall, beds, inventory) are described.\nVoice documentation and clinical decision-support hints (allergies, interactions, protocols) appear in messaging.\nAI is meant to show up **inside existing screens**, not only as a separate chatbot.\nValidate which AI features are in your licensed package during demo.\n\n🔗 https://www.athentech.co.in/ai-healthcare-platform/'
A['platform'] = '🧠 **AI Healthcare Platform**\n\nThe platform story unifies HIS, LIS, RIS, EMR, pharmacy, finance, analytics and engagement.\nSix pillars are emphasised: one patient record, AI in workflows, cloud or own servers,\nclinical operations (OPD/wards/OT/ER), live management numbers, and standards (ABDM, HL7, FHIR, DICOM).\nExperience channels include portal, WhatsApp, apps, kiosks and displays.\nIntelligence layers sit above the clinical/ops core and data/security foundation.\nUse this page when explaining Sahasra to leadership sponsors.\n\n🔗 https://www.athentech.co.in/ai-healthcare-platform/'
A['implementation'] = '🛠️ **Implementation approach**\n\nAthentech stresses that software alone is not enough without workflow setup.\nTheir teams handle configuration, training and go-live support.\nProjects are not positioned as a pure “install and disappear” license drop.\nYou should plan master data, tariff, user roles and interface testing in the timeline.\nTraining coverage for front desk, clinical and accounts users matters for adoption.\nAsk for a sample implementation plan in your proposal discussions.\n\n🔗 https://www.athentech.co.in/about/'
A['clients'] = '🤝 **Clients**\n\nAthenTech publishes **592+ healthcare clients** as a scale indicator.\nCoverage across **18+ districts** is also mentioned in company materials.\nClient logos and success narratives appear on the Clients section of the website.\nReferences span hospitals, diagnostics and related care organisations.\nFor reference calls, request introductions through sales after NDA as needed.\nUse client stories as proof points alongside a live product demo.\n\n🔗 https://www.athentech.co.in/clients/'
A['careers'] = '💼 **Careers**\n\nOpen roles and culture information are listed on the Careers page under About.\nThe company is headquartered in Hyderabad with presence in other cities.\nHealthcare product, implementation and support roles are typical for this domain.\nApply only via official channels on the website—not through chat passwords or fees.\nRecruitment processes should be confirmed on the careers listing itself.\nThis assistant cannot process job applications.\n\n🔗 https://www.athentech.co.in/about/careers/'
A['management'] = '👔 **Leadership / management**\n\nLeadership and management profiles are published on the corporate Management page.\nUse that page for names, roles and official biographies.\nFor partnership or enterprise deals, sales can route you to the right leader.\nDo not rely on unofficial social profiles when verifying company officers.\nCombine management context with product demos for serious evaluations.\nContact sales if you need a leadership meeting in the buying cycle.\n\n🔗 https://www.athentech.co.in/management/'
A['banking'] = '🏦 **Beyond healthcare**\n\nAthenTech’s primary public focus is **healthcare software** via the Sahasra suite.\nCompany materials also note experience in **banking and insurance** technology.\nIf you need non-healthcare systems, clarify scope directly with sales.\nMost website depth—modules, ABDM, NABL—targets hospitals and labs.\nDo not assume Sahasra hospital modules apply unchanged to banking products.\nStart the conversation at +91 970 5480 699 with your domain stated clearly.\n\n🔗 https://www.athentech.co.in/'
A['tally'] = '🧮 **Tally integration**\n\nSahasra ERP highlights integration with **Tally** for accounting hand-off.\nThis helps finance teams keep operational billing aligned with books.\nERP also references **250+ MIS reports** and multi-location roll-ups.\nChart mapping and voucher patterns are configured during implementation.\nConfirm Tally version and company structure in technical discovery.\nFinance sponsors should join the demo when Tally is a must-have.\n\n🔗 https://www.athentech.co.in/products/'
A['multibranch'] = '🏢 **Multi-location / multi-branch**\n\nSahasra is built for groups that run multiple hospitals, branches or labs.\nCentral masters with location-level operations are part of the multi-location story.\nDiagnostic chains and hospital networks use this to standardise yet operate locally.\nMIS and management dashboards help leadership see across sites.\nNetwork connectivity and hosting model should match your branch footprint.\nBring a branch list to the demo for a realistic rollout discussion.\n\n🔗 https://www.athentech.co.in/features/'
A['reports'] = '📈 **Reports & MIS**\n\nOn the ERP side, Athentech cites **250+ MIS reports** for management needs.\nOn the lab side, **950+ diagnostic report formats** support diverse test menus.\nLive management dashboards appear in the AI/platform narrative (footfall, beds, collections).\nReport packs are refined during implementation to match your KPIs.\nExport and scheduling options should be validated in UAT before go-live.\nAsk for sample MIS outputs relevant to your CFO or medical director.\n\n🔗 https://www.athentech.co.in/products/'
A['analyzers'] = '🔬 **Lab analyzer interfacing**\n\nLIS GenX supports **bi-directional analyzer** interfacing for automated result flow.\nBarcode sample identification reduces manual accession errors at volume.\nAuto-validation and TAT monitoring help labs control turnaround discipline.\nEach analyzer brand/model needs interface effort and test plans.\nShare your instrument list early so commercial and technical scope stay accurate.\nThis is a core reason diagnostic chains evaluate Sahasra LIS.\n\n🔗 https://www.athentech.co.in/solutions/laboratory-information-system/'
A['home_collection'] = '🚗 **Home collection**\n\nDiagnostic industry messaging includes support for chain operations with home collection patterns.\nLIS workflows still need clear sample logistics, barcode tracking and branch reconciliation.\nDigital report delivery (portal/WhatsApp/SMS) complements field collection.\nProcess design matters as much as software—phlebotomy routes and cut-offs.\nConfirm home-collection features in a lab-chain demo, not only a hospital HIS demo.\nProvide daily home-collection volume estimates to sales for sizing.\n\n🔗 https://www.athentech.co.in/industries/'
A['billing'] = '🧾 **Billing & insurance**\n\nBilling and insurance/credit modules sit with finance on the Sahasra stack.\nCharges can follow clinical activity when HIS/LIS modules share the patient record.\nUseful for hospitals with mixed cash, credit and insurer workflows.\nTariff masters and package definitions are configured at implementation.\nStatutory invoices and insurer formats must be validated with your accounts team.\nInclude billing scenarios in UAT before go-live.\n\n🔗 https://www.athentech.co.in/modules/'
A['appointment'] = '📅 **Appointments**\n\nOutpatient appointments are part of OPD management in HISGenX.\nPatient portal and apps extend booking beyond the front-desk queue.\nDoctor schedules and service calendars are maintained in masters.\nSMS/WhatsApp reminders may be available depending on messaging setup.\nMulti-location groups can route appointments per branch rules.\nDemo booking flows for your highest-volume specialties.\n\n🔗 https://www.athentech.co.in/solutions/patient-portal/'
A['tele'] = '📹 **Teleconsultation**\n\nTeleconsultation is referenced on the patient portal / digital experience layer.\nIt extends care access beyond purely physical OPD queues.\nClinical documentation should still land on the unified patient record where enabled.\nConnectivity, consent and prescribing rules must follow local regulations.\nConfirm teleconsult packaging in your commercial proposal.\nAsk for a portal demo if virtual consults are a priority channel.\n\n🔗 https://www.athentech.co.in/solutions/patient-portal/'
A['housekeeping'] = '🧹 **Housekeeping management**\n\nHousekeeping is listed among Sahasra hospital operations solutions.\nIt supports facility cleanliness and ward-readiness processes alongside clinical modules.\nHospitals evaluating full ops automation often include housekeeping in scope.\nTask checklists and ward mapping are configured during implementation.\nPair with IPD bed management for discharge-turnaround discipline.\nMention housekeeping when building your module shortlist with sales.\n\n🔗 https://www.athentech.co.in/solutions/housekeeping-management/'
A['mrd'] = '📁 **MRD (Medical Records)**\n\nMedical records department workflows are part of the integrated module set.\nMRD benefits when EMR/IPD documentation already lives on the same platform.\nRecord completeness and retrieval improve versus paper-only charts.\nRetention policies and audit needs should be defined with hospital policy owners.\nNABH-oriented process support complements disciplined MRD practice.\nInclude MRD users in training plans at go-live.\n\n🔗 https://www.athentech.co.in/modules/'
A['masters'] = '⚙️ **Masters & configuration**\n\nMasters are the configuration foundation of Sahasra: departments, doctors, services, wards, beds, tariffs, tests, users and categories.\nClean masters determine billing accuracy, lab menus and appointment schedules.\nMulti-location groups often centralise masters with location-level overrides.\nImplementation projects invest heavily here before transactional go-live.\nPoor master data is a common cause of delayed rollouts in any HIMS/LIS.\nPlan master workshops with department heads early.\n\n🔗 https://www.athentech.co.in/modules/masters/'
A['compare_his_lis'] = '⚖️ **HIS vs LIS in Sahasra**\n\n**HISGenX** is the hospital system—OPD, IPD, OT, nursing, billing, pharmacy, EMR and more.\n**LIS GenX** is the laboratory system—samples, analyzers, TAT, lab reporting and lab-centric delivery channels.\nMany hospitals run **both** so clinical orders and lab results share one patient record.\nStandalone diagnostic chains often start with **LIS** (and RIS if imaging-heavy).\nChoosing only one depends on whether you operate beds/wards or a pure lab network.\nSales can map a package after you describe facilities and daily volumes.\n\n🔗 https://www.athentech.co.in/products/'
A['deploy'] = '🖥️ **Deployment options**\n\nYou can run Sahasra on **cloud** hosting or **on-premises** servers you control.\nSingle-facility and **multi-location** topologies are both supported in the product story.\nHosting choice affects IT staffing, uptime ownership and compliance discussions.\nInterface servers (analyzers, PACS) need network planning regardless of cloud vs on-prem.\nDisaster recovery and backup targets should be written into the contract.\nDecide hosting with both clinical sponsors and IT, guided by sales engineering.\n\n🔗 https://www.athentech.co.in/features/'
A['hours'] = '⏰ **How to reach the team**\n\nUse the published national contact channels (India):\n• **Sales:** +91 970 5480 699 · sales@athentech.co.in\n• **Support / IVR:** +91 8096 247 365 · support@athentech.co.in\nSupport is described with a **24×7** service model in platform materials.\nFor demos and commercials, sales during business engagement is the usual path.\nAlways verify the latest numbers on the official contact page if lines change.\n\n🔗 https://www.athentech.co.in/contact/'
A['email_only'] = '✉️ **Email contacts**\n\nOfficial emails published for Athentech engagement:\n• **sales@athentech.co.in** — demos, pricing, new implementations\n• **support@athentech.co.in** — support for existing customers\nPair email with phone when urgent: sales +91 970 5480 699, support +91 8096 247 365.\nInclude your organisation name, city and requirement summary in the first mail.\nAvoid sending passwords or patient data over unsolicited email threads.\n\n🔗 https://www.athentech.co.in/contact/'
A['whatsapp_signup'] = '🟢 **WhatsApp Business Signup**\n\nThe athentech.co.in header promotes **WhatsApp Business Signup** for business onboarding.\nSeparately, Sahasra messaging features can use WhatsApp Business API for patient engagement.\nSignup and API use are related but not identical—confirm which you need with sales.\nTemplate approvals and opt-in rules apply under WhatsApp/TRAI policies.\nLabs often care about report notifications; hospitals may care about appointment updates.\nStart from the website header or ask sales to guide the correct track.\n\n🔗 https://www.athentech.co.in/'
A['iso'] = '📜 **Compliance posture**\n\nFeature communications reference ISO 27001–oriented security practices.\nABDM V3 support addresses national digital health integration for HIS and LIS.\nNABH, NABL and CAP oriented workflows support quality programmes in hospitals and labs.\nHL7, FHIR and DICOM support interoperability expectations in formal tenders.\nCertificates, scope and audit evidence should be requested formally for RFPs.\nSales can route compliance questionnaires to the right internal owners.\n\n🔗 https://www.athentech.co.in/features/'
A['partner'] = '🤝 **Engaging AthenTech**\n\nA typical path is discovery → product demo → commercial proposal → implementation.\nAthentech emphasises configuration, training and go-live with their own teams.\nPrepare facility profile: type, locations, volumes, must-have modules and interfaces.\nInvolve clinical, lab, IT and finance sponsors so scope stays realistic.\nStart with sales on +91 970 5480 699 or sales@athentech.co.in.\nUse the website contact form if you prefer a structured web enquiry.\n\n🔗 https://www.athentech.co.in/contact/'
A['hello'] = '👋 **Hello**\n\nI’m the **AthenTech Assistant** for questions about AthenTech and the **Sahasra** platform.\nI can help with contact details, products (HIS, LIS, RIS, ERP), modules, demos and company facts.\nI do not access hospital live data in this mode—only public company/product information.\nTry asking about pricing, ABDM, modules, or how to request a demo.\nFor urgent human help, call sales +91 970 5480 699 or support +91 8096 247 365.\nOfficial site: athentech.co.in\n\n🔗 https://www.athentech.co.in/'

A['services'] = '🛠️ **Services & solutions AthenTech provides**\n\nAthenTech builds and implements **healthcare software** for hospitals, diagnostic centres and multi-location groups under the **Sahasra** brand.\n\n**Core software**\n• **HIS GenX** — hospital information system (OPD, IPD, OT, nursing, billing, pharmacy, EMR…)\n• **LIS GenX** — laboratory information system (samples, analyzers, TAT, reports)\n• **RIS GenX** — radiology / imaging workflows\n• **ERP / finance** — hospital ERP, Tally-oriented finance links where applicable\n\n**Platform strengths (public figures)**\n• **43** integrated modules · **592+** healthcare clients · **950+** diagnostic report formats\n• **One patient record** across clinical, lab and admin modules\n• **ABDM V3**, NABH/NABL-oriented workflows, HL7 / FHIR / DICOM interoperability themes\n\n**How they engage**\nDiscovery → product demo → proposal → configuration, training and go-live with AthenTech teams.\n\nSales: **+91 970 5480 699** · sales@athentech.co.in\n\n🔗 https://www.athentech.co.in/products/\n'

_INTENTS = [
    ((' his ',), A['his']),
    ((' lis ',), A['lis']),
    ((' ris ',), A['ris']),
    ((' sahasra ',), A['products']),
    ((' about athentech ',), A['about']),
    ((' about you ',), A['about']),
    ((' who are you ',), A['about']),
    ((' company ',), A['about']),
    # --- high priority product/services ---
    (('services provided',), A['services']),
    (('service provided',), A['services']),
    (('what services',), A['services']),
    (('your services',), A['services']),
    (('services',), A['services']),
    (('solutions',), A['services']),
    (('offerings',), A['services']),
    (('what do you provide',), A['services']),
    (('what do you offer',), A['services']),
    (('what can you provide',), A['services']),
    (('software you provide',), A['services']),
    (('products you offer',), A['products']),
    (('what products',), A['products']),
    (('product list',), A['products']),
    (('products',), A['products']),
    (('sahasra suite',), A['products']),
    (('what do you sell',), A['products']),
    (('hello',), A['hello']),
    (('hi ',), A['hello']),
    (('hey',), A['hello']),
    (('good morning',), A['hello']),
    (('good evening',), A['hello']),
    (('contact',), A['contact']),
    (('phone number',), A['contact']),
    (('mobile number',), A['contact']),
    (('call you',), A['contact']),
    (('reach you',), A['contact']),
    (('get in touch',), A['contact']),
    (('how to contact',), A['contact']),
    (('how can i contact',), A['contact']),
    (('sales number',), A['sales']),
    (('sales team',), A['sales']),
    (('support number',), A['support']),
    (('support team',), A['support']),
    (('helpdesk',), A['support']),
    (('help desk',), A['support']),
    (('24x7',), A['support']),
    (('24/7',), A['support']),
    (('address',), A['address']),
    (('head office',), A['address']),
    (('punjagutta',), A['address']),
    (('dwarakapuri',), A['address']),
    (('where is your office',), A['address']),
    (('email id',), A['email_only']),
    (('email address',), A['email_only']),
    (('mail id',), A['email_only']),
    (('which cities',), A['cities']),
    (('cities',), A['cities']),
    (('locations',), A['cities']),
    (('hyderabad',), A['cities']),
    (('bangalore',), A['cities']),
    (('bengaluru',), A['cities']),
    (('vijayawada',), A['cities']),
    (('vizag',), A['cities']),
    (('visakhapatnam',), A['cities']),
    (('where are you based',), A['cities']),
    (('where are you located',), A['cities']),
    (('about athentech',), A['about']),
    (('about athen',), A['about']),
    (('who are you',), A['about']),
    (('what is athentech',), A['about']),
    (('what is athen tech',), A['about']),
    (('company info',), A['about']),
    (('tell me about athentech',), A['about']),
    (('in 3 lines',), A['about']),
    (('in three lines',), A['about']),
    (('mission',), A['mission']),
    (('vision',), A['vision']),
    (('why choose',), A['why']),
    (('why athentech',), A['why']),
    (('how many clients',), A['stats']),
    (('592',), A['stats']),
    (('at a glance',), A['stats']),
    (('years of experience',), A['stats']),
    (('20 years',), A['stats']),
    (('request a demo',), A['demo']),
    (('request demo',), A['demo']),
    (('book a demo',), A['demo']),
    (('schedule a demo',), A['demo']),
    (('demo',), A['demo']),
    (('get a quote',), A['quote']),
    (('quotation',), A['quote']),
    (('pricing',), A['pricing']),
    (('price list',), A['pricing']),
    (('how much does',), A['pricing']),
    (('cost of',), A['pricing']),
    (('product list',), A['products']),
    (('products',), A['products']),
    (('sahasra suite',), A['products']),
    (('what do you sell',), A['products']),
    (('hisgenx',), A['his']),
    (('sahasra his',), A['his']),
    (('hospital information system',), A['his']),
    (('what is his',), A['his']),
    (('hims',), A['his']),
    (('hospital software',), A['his']),
    (('lis genx',), A['lis']),
    (('sahasra lis',), A['lis']),
    (('laboratory information',), A['lis']),
    (('what is lis',), A['lis']),
    (('lab software',), A['lis']),
    (('sahasra ris',), A['ris']),
    (('radiology information',), A['ris']),
    (('what is ris',), A['ris']),
    (('teleradiology',), A['ris']),
    (('tele-radiology',), A['ris']),
    (('sahasra erp',), A['erp']),
    (('campus 360',), A['campus']),
    (('campus360',), A['campus']),
    (('mchims',), A['campus']),
    (('medical college software',), A['campus']),
    (('mobile app',), A['mobile']),
    (('android app',), A['mobile']),
    (('doctor app',), A['mobile']),
    (('patient app',), A['mobile']),
    (('pharmacy',), A['pharmacy']),
    (('emr',), A['emr']),
    (('ehr',), A['emr']),
    (('electronic medical',), A['emr']),
    (('blood bank',), A['bloodbank']),
    (('ot management',), A['ot']),
    (('operation theatre',), A['ot']),
    (('nursing station',), A['nursing']),
    (('outpatient',), A['opd']),
    (('out patient',), A['opd']),
    (('inpatient',), A['ipd']),
    (('in patient',), A['ipd']),
    (('modules',), A['modules']),
    (('43 module',), A['modules']),
    (('module list',), A['modules']),
    (('how many modules',), A['modules']),
    (('inventory',), A['inventory']),
    (('procurement',), A['inventory']),
    (('hr payroll',), A['hr']),
    (('payroll',), A['hr']),
    (('finance',), A['finance']),
    (('patient portal',), A['portal']),
    (('housekeeping',), A['housekeeping']),
    (('mrd',), A['mrd']),
    (('medical records',), A['mrd']),
    (('masters',), A['masters']),
    (('industries',), A['industries']),
    (('for hospitals',), A['hospital']),
    (('diagnostic centre',), A['diagnostic']),
    (('diagnostic center',), A['diagnostic']),
    (('pathology lab',), A['diagnostic']),
    (('lab chain',), A['diagnostic']),
    (('medical college',), A['college']),
    (('teaching hospital',), A['college']),
    (('polyclinic',), A['clinic']),
    (('clinic',), A['clinic']),
    (('ivf',), A['ivf']),
    (('fertility',), A['ivf']),
    (('abdm',), A['abdm']),
    (('abha',), A['abdm']),
    (('ayushman bharat',), A['abdm']),
    (('nabh',), A['nabh']),
    (('nabl',), A['nabh']),
    (('hl7',), A['hl7']),
    (('fhir',), A['hl7']),
    (('pacs',), A['pacs']),
    (('dicom',), A['pacs']),
    (('cloud',), A['cloud']),
    (('on-prem',), A['cloud']),
    (('on prem',), A['cloud']),
    (('deployment',), A['deploy']),
    (('hosting',), A['deploy']),
    (('security',), A['security']),
    (('iso 27001',), A['iso']),
    (('whatsapp business',), A['whatsapp_signup']),
    (('whatsapp',), A['whatsapp']),
    (('ai healthcare',), A['ai']),
    (('artificial intelligence',), A['ai']),
    (('digital brain',), A['platform']),
    (('healthcare platform',), A['platform']),
    (('implementation',), A['implementation']),
    (('go-live',), A['implementation']),
    (('go live',), A['implementation']),
    (('clients',), A['clients']),
    (('testimonial',), A['clients']),
    (('careers',), A['careers']),
    (('hiring',), A['careers']),
    (('management team',), A['management']),
    (('leadership',), A['management']),
    (('banking',), A['banking']),
    (('tally',), A['tally']),
    (('multi location',), A['multibranch']),
    (('multi-location',), A['multibranch']),
    (('multi branch',), A['multibranch']),
    (('multi-branch',), A['multibranch']),
    (('mis report',), A['reports']),
    (('dashboard',), A['reports']),
    (('analyzer',), A['analyzers']),
    (('analyser',), A['analyzers']),
    (('home collection',), A['home_collection']),
    (('billing',), A['billing']),
    (('appointment',), A['appointment']),
    (('teleconsult',), A['tele']),
    (('telemedicine',), A['tele']),
    (('his vs lis',), A['compare_his_lis']),
    (('difference between his',), A['compare_his_lis']),
    (('website',), A['website']),
    (('partner with',), A['partner']),
]

def try_athentech_intent(question: str) -> Optional[str]:
    q = (question or "").strip().lower()
    if not q or len(q) > 500:
        return None
    qn = re.sub(r"[^\w\s\+@\./-]", " ", q)
    qn = re.sub(r"\s+", " ", qn).strip()
    qn_pad = f" {qn} "

    def key_hit(k: str) -> bool:
        k = k.strip()
        if not k:
            return False
        # short tokens / acronyms → whole word only
        if len(k) <= 4 or k in {"his", "lis", "ris", "erp", "emr", "ot", "ipd", "opd"}:
            return f" {k} " in qn_pad
        return k in qn

    # Prefer longer key-sets first (more specific phrases)
    ranked = sorted(_INTENTS, key=lambda pair: -sum(len(k) for k in pair[0]))
    for keys, answer in ranked:
        if all(key_hit(k) for k in keys):
            return answer
    return None
