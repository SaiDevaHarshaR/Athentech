from reports.pdf_generator import generate_smart_report

data = {
    "report_title": "PATIENT SUMMARY REPORT",
    "hospital_name": "City Care Hospital",
    "user_role": "Doctor",
    "activation_code": "ATH-1001",
    "normal_count": 2,
    "borderline_count": 0,
    "abnormal_count": 1,
    "tests": [
        {
            "name": "Ramesh Kumar (UHID001)",
            "value": "42 years",
            "unit": "",
            "range": "Age",
            "status": "normal",
            "percentage": 70,
            "comment": "Male patient registered on 2026-08-20"
        },
        {
            "name": "Sita Devi (UHID002)",
            "value": "35 years",
            "unit": "",
            "range": "Age",
            "status": "normal",
            "percentage": 60,
            "comment": "Female patient registered on 2026-08-22"
        },
        {
            "name": "Arjun Reddy (UHID003)",
            "value": "28 years",
            "unit": "",
            "range": "Age",
            "status": "abnormal",
            "percentage": 40,
            "comment": "Youngest patient in current list"
        }
    ]
}

pdf = generate_smart_report(data)

with open("test_smart_report.pdf", "wb") as f:
    f.write(pdf.read())

print("PDF created: test_smart_report.pdf")