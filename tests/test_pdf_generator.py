from reports.pdf_generator import generate_smart_report, build_findings_from_content_lines, _add_link_targets


def test_empty_data_does_not_crash():
    pdf = generate_smart_report({})
    assert len(pdf.getvalue()) > 0


def test_none_data_does_not_crash():
    pdf = generate_smart_report(None)
    assert len(pdf.getvalue()) > 0


def test_partial_data_with_none_field_does_not_crash():
    pdf = generate_smart_report({"patient_name": None, "hospital_name": "City Care", "health_score": 820})
    assert len(pdf.getvalue()) > 0


def test_content_lines_fallback_produces_findings():
    findings = build_findings_from_content_lines(["Line one", "Line two", "", "  "])
    # blank/whitespace-only lines should be skipped
    assert len(findings) == 2
    assert findings[0]["simple_explanation"] == "Line one"


def test_add_link_targets_inserts_before_tag_not_inside_it():
    html = '<div id="finding-1" class="card">content</div>'
    result = _add_link_targets(html)
    assert '<a name="finding-1"></a>' in result
    # the anchor must come BEFORE the tag, not get injected into its attributes
    assert '<div <a name=' not in result
    assert result.index('<a name="finding-1">') < result.index('<div id="finding-1"')


def test_full_pdf_generates_clickable_internal_links():
    from pypdf import PdfReader
    from io import BytesIO

    data = {
        "priority_findings": [{"icon": "", "name": "Glucose", "value": "110", "unit": "mg/dL", "anchor": "finding-glucose"}],
        "all_findings": [{"anchor": "finding-glucose", "icon": "", "name": "Glucose", "category": "Metabolism",
                           "value": "110", "unit": "mg/dL", "status": "watch", "label": "Borderline",
                           "simple_explanation": "Blood sugar slightly high."}],
    }
    pdf = generate_smart_report(data)
    reader = PdfReader(BytesIO(pdf.getvalue()))

    link_count = 0
    for page in reader.pages:
        annots = page.get("/Annots")
        if annots:
            for a in annots:
                if a.get_object().get("/Subtype") == "/Link":
                    link_count += 1

    assert link_count >= 2  # forward "View details" link + "Back to Health Map" link
