from xhtml2pdf import pisa
from jinja2 import Environment, FileSystemLoader
from io import BytesIO
from datetime import datetime
import uuid
import os

def generate_smart_report(data: dict) -> BytesIO:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, "templates")

    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("smart_report.html")

    # Defaults
    data.setdefault("report_date", datetime.now().strftime("%d/%m/%Y %H:%M"))
    data.setdefault("report_id", str(uuid.uuid4())[:8].upper())
    data.setdefault("report_title", "SAHASRA AI REPORT")
    data.setdefault("hospital_name", "Demo Hospital")
    data.setdefault("user_role", "Staff")
    data.setdefault("activation_code", "ATH-1001")
    data.setdefault("normal_count", 0)
    data.setdefault("borderline_count", 0)
    data.setdefault("abnormal_count", 0)
    data.setdefault("tests", [])

    html_content = template.render(**data)

    # Convert HTML to PDF
    pdf_file = BytesIO()
    pisa_status = pisa.CreatePDF(html_content, dest=pdf_file)

    if pisa_status.err:
        raise Exception("Error creating PDF")

    pdf_file.seek(0)
    return pdf_file