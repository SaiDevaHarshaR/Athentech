from weasyprint import HTML, CSS
from jinja2 import Environment, FileSystemLoader
from io import BytesIO
from datetime import datetime
import uuid

def generate_smart_report(data: dict) -> BytesIO:
    env = Environment(loader=FileSystemLoader("reports/templates"))
    template = env.get_template("smart_report.html")

    # Default values
    data.setdefault("report_date", datetime.now().strftime("%d/%m/%Y %H:%M"))
    data.setdefault("report_id", str(uuid.uuid4())[:8].upper())
    data.setdefault("report_title", "SAHASRA AI REPORT")
    data.setdefault("normal_count", 0)
    data.setdefault("borderline_count", 0)
    data.setdefault("abnormal_count", 0)

    html_content = template.render(**data)

    pdf_file = BytesIO()
    HTML(string=html_content).write_pdf(
        pdf_file,
        stylesheets=[CSS(filename="reports/templates/styles.css")]
    )
    pdf_file.seek(0)
    return pdf_file