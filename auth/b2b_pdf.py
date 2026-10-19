"""Report status summary PDF for a B2B client's own bill (used when the lab has not exported signed report PDFs).
It is built only from the verified organisation's data and says clearly that it is a status summary, not the clinical report."""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether


def _hex(v, default):
    try:
        v = (v or "").strip().lstrip("#")
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        return colors.HexColor("#" + v) if len(v) == 6 else colors.HexColor(default)
    except Exception:
        return colors.HexColor(default)


def _t(s, n=60):
    s = str(s if s is not None else "")
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s[:n]


def _d(v):
    return str(v)[:10] if v else "-"


def _inr(v):
    try:
        x = float(v or 0)
    except Exception:
        return "-"
    neg = x < 0
    x = abs(x)
    whole, frac = ("%.2f" % x).split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("-" if neg else "") + "INR " + whole + ("" if frac == "00" else "." + frac)


def build_summary_pdf(conn, org_code, bill_no, brand_name="Laboratory", primary="#F26B21"):
    """conn: LIS connection. The caller has already verified that bill_no belongs to org_code."""
    pri = conn.execute("SELECT TOP 1 BILLNO, BILLDATE, Name, TOTALCHARGES FROM trnINVLABPRI WHERE BILLNO = ? AND ORGANISATIONCODE = ?", (bill_no, org_code)).fetchone()
    org = conn.execute("SELECT TOP 1 ORGANISATIONNAME FROM mstOrganisation WHERE ORGANISATIONCODE = ?", (org_code,)).fetchone()
    tests = conn.execute(
        "SELECT ISNULL(m.INVNAME, s.TCODE), s.STATUS, s.SAMPLECOLLECTEDDATE, s.ACKNOWLEDGEDDATE, s.AUTHENTICATEDATE FROM trnInvStatus s "
        "LEFT JOIN mstInvestigations m ON m.INVCODE COLLATE DATABASE_DEFAULT = s.TCODE COLLATE DATABASE_DEFAULT WHERE s.BILLNO = ? ORDER BY s.ID", (bill_no,)).fetchall()
    brand = _hex(primary, "#F26B21")
    ink, mute, line = colors.HexColor("#1F2937"), colors.HexColor("#6B7280"), colors.HexColor("#E5E7EB")
    soft = colors.Color(brand.red, brand.green, brand.blue, alpha=0.08)
    ok_c, wait_c, bad_c = colors.HexColor("#15803D"), colors.HexColor("#B45309"), colors.HexColor("#B91C1C")
    org_name = _t(org[0] if org else org_code, 70)
    patient = _t(pri[2] if pri else "-", 50)
    done = sum(1 for r in tests if str(r[1] or "").lower().startswith("authent"))
    total = len(tests)
    buf = io.BytesIO()
    W, H = A4
    gen = datetime.now().strftime("%d %b %Y, %H:%M")

    def frame(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(brand)
        canvas.rect(0, H - 34 * mm, W, 34 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.14))
        canvas.circle(W - 18 * mm, H - 8 * mm, 26 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 19)
        canvas.drawString(18 * mm, H - 17 * mm, _t(brand_name, 48))
        canvas.setFont("Helvetica", 9.5)
        canvas.drawString(18 * mm, H - 24 * mm, "Report Status Summary")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.85))
        canvas.drawRightString(W - 18 * mm, H - 28.5 * mm, "Generated " + gen)
        canvas.setStrokeColor(line)
        canvas.line(18 * mm, 16 * mm, W - 18 * mm, 16 * mm)
        canvas.setFillColor(mute)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(18 * mm, 11 * mm, "Status summary from the laboratory system. It is not the signed clinical report - use the authorised report for clinical decisions.")
        canvas.drawRightString(W - 18 * mm, 11 * mm, "Page %d" % doc.page)
        canvas.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=40 * mm, bottomMargin=22 * mm,
                          title="Report summary " + bill_no, author=_t(brand_name, 60))
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(doc.leftMargin, doc.bottomMargin, W - 36 * mm, H - 62 * mm, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=frame)])
    lab = ParagraphStyle("lab", fontName="Helvetica", fontSize=7.5, textColor=mute, leading=9)
    val = ParagraphStyle("val", fontName="Helvetica-Bold", fontSize=10.5, textColor=ink, leading=13)
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.8, textColor=ink, leading=11)
    head = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=10)
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, textColor=ink, leading=14, spaceBefore=6, spaceAfter=6)
    story = []

    def kv(l, v):
        return [Paragraph(l.upper(), lab), Paragraph(_t(v, 60), val)]
    info = Table([[kv("Patient", patient), kv("Bill number", bill_no), kv("Bill date", _d(pri[1] if pri else None))],
                  [kv("Client", org_name), kv("Client code", org_code), kv("Billed amount", _inr(pri[3] if pri else 0))]],
                 colWidths=[(W - 36 * mm) * 0.42, (W - 36 * mm) * 0.28, (W - 36 * mm) * 0.30])
    info.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), soft), ("BOX", (0, 0), (-1, -1), 0.6, line), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                              ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [info, Spacer(1, 9)]

    pct = (done * 100.0 / total) if total else 0
    bar_w = W - 36 * mm - 175
    fill = max(bar_w * pct / 100.0, 0.01)
    track = Table([["", ""]], colWidths=[fill, max(bar_w - fill, 0.01)], rowHeights=[7])
    track.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), brand), ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#E5E7EB")),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    prog = Table([[Paragraph("<b>%d of %d</b> reports ready" % (done, total), ParagraphStyle("p", fontName="Helvetica", fontSize=10, textColor=ink)), track,
                   Paragraph("%d%%" % round(pct), ParagraphStyle("pp", fontName="Helvetica-Bold", fontSize=10, textColor=brand, alignment=2))]],
                 colWidths=[130, bar_w, 45])
    prog.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [prog, Spacer(1, 6), Paragraph("Tests on this bill", h2)]

    rows = [[Paragraph(x, head) for x in ("#", "Test", "Status", "Sample collected", "Received at lab", "Report ready")]]
    for i, r in enumerate(tests, 1):
        st = str(r[1] or "-")
        low = st.lower()
        col = ok_c if low.startswith("authent") else (bad_c if "reject" in low else wait_c)
        rows.append([Paragraph(str(i), cell), Paragraph(_t(r[0], 52), cell),
                     Paragraph('<font color="%s"><b>%s</b></font>' % (col.hexval().replace("0x", "#"), _t(st if not low.startswith("authent") else "Ready", 20)), cell),
                     Paragraph(_d(r[2]), cell), Paragraph(_d(r[3]), cell), Paragraph(_d(r[4]), cell)])
    if not tests:
        rows.append([Paragraph("-", cell), Paragraph("No test status has been recorded for this bill yet.", cell), "", "", "", ""])
    cw = W - 36 * mm
    tbl = Table(rows, colWidths=[cw * 0.06, cw * 0.36, cw * 0.12, cw * 0.15, cw * 0.15, cw * 0.16], repeatRows=1)
    sty = [("BACKGROUND", (0, 0), (-1, 0), brand), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
           ("LEFTPADDING", (0, 0), (-1, -1), 6), ("LINEBELOW", (0, 1), (-1, -1), 0.4, line), ("BOX", (0, 0), (-1, -1), 0.6, line)]
    for i in range(2, len(rows), 2):
        sty.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FAFAFA")))
    tbl.setStyle(TableStyle(sty))
    story.append(tbl)
    doc.build(story)
    return buf.getvalue()
