import io
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

def generate_koyambedu_bill_pdf(bill_data):
    """
    Generates a pixel-perfect PDF replicating the physical Koyambedu market bill.
    bill_data is a dict containing:
    - shop_name: 'AVT'
    - devotional_motto: 'ARULMIGU VINAYAGA THUNAI  ARULMIGU VEERUCHINNAMMAL THUNAI'
    - market_address: 'FB-78, Kamarajar Flower Market, Koyambedu, Chennai-92'
    - phone: '9360188707'
    - posting_upto: '02/11/2026'
    - party_name: 'HMS DOLL DPS - SALEM'
    - advance: '0.00'
    - items: list of dicts (date, flower, weight, rate, box, luggage, coolie, total_amt)
    - totals: dict (total_weight, total_boxes, total_luggage, total_coolie, total_amt)
    - deductions: dict (commission_pct, commission_amt, total_luggage, coolie, total_expense, adv_deducted, total_less)
    - settlement: dict (total_amt, total_less, net_balance)
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    motto_style = ParagraphStyle(
        'DevotionalMotto',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1e293b')
    )
    title_style = ParagraphStyle(
        'ShopTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=26,
        leading=28,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#0f172a')
    )
    subhead_style = ParagraphStyle(
        'Subhead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#0f172a')
    )
    address_style = ParagraphStyle(
        'Address',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#334155')
    )
    posting_style = ParagraphStyle(
        'PostingTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#0f172a')
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11
    )
    body_bold = ParagraphStyle(
        'BodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11
    )
    body_right = ParagraphStyle(
        'BodyRight',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        alignment=TA_RIGHT
    )
    body_right_bold = ParagraphStyle(
        'BodyRightBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        alignment=TA_RIGHT
    )

    story = []

    # 1. Top row: Date | Motto | Page
    top_meta = [
        [
            Paragraph(bill_data.get('posting_upto', '02/11/2026'), body_style),
            Paragraph(bill_data.get('devotional_motto', 'ARULMIGU VINAYAGA THUNAI   ARULMIGU VEERUCHINNAMMAL THUNAI'), motto_style),
            Paragraph('Page 1', body_right)
        ]
    ]
    t_top = Table(top_meta, colWidths=[35*mm, 110*mm, 35*mm])
    t_top.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(t_top)
    story.append(Spacer(1, 2*mm))

    # 2. Main Shop Banner
    story.append(Paragraph(bill_data.get('shop_name', 'AVT'), title_style))
    story.append(Paragraph('FLOWER MERCHANT &amp; COMMISSION AGENT', subhead_style))
    story.append(Paragraph(bill_data.get('market_address', 'FB-78, Kamarajar Flower Market, Koyambedu, Chennai-92'), address_style))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph(f"<u>PURCHASE POSTING upto {bill_data.get('posting_upto', '02/11/2026')}</u>", posting_style))
    story.append(Spacer(1, 2*mm))

    # 3. Party & Advance Meta Box
    party_meta = [
        [
            Paragraph(f"<b>Party :</b> {bill_data.get('party_name', 'HMS DOLL DPS - SALEM')}", body_style),
            Paragraph(f"Phone: {bill_data.get('phone', '9360188707')}&nbsp;&nbsp;&nbsp;&nbsp;<b>Advance :</b> {bill_data.get('advance', '0.00')}", body_right_bold)
        ]
    ]
    t_party = Table(party_meta, colWidths=[100*mm, 80*mm])
    t_party.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,-1), 0.75, colors.black),
        ('LINEBELOW', (0,0), (-1,-1), 0.75, colors.black),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_party)
    story.append(Spacer(1, 2*mm))

    # 4. Itemized Purchases Table
    table_data = [
        [
            Paragraph('<b>Date</b>', body_style),
            Paragraph('<b>Flower</b>', body_style),
            Paragraph('<b>Weight &nbsp; X &nbsp; Rate</b>', body_right_bold),
            Paragraph('<b>Box</b>', body_right_bold),
            Paragraph('<b>Luggage</b>', body_right_bold),
            Paragraph('<b>Coolie</b>', body_right_bold),
            Paragraph('<b>Total Amount</b>', body_right_bold),
        ]
    ]

    for item in bill_data.get('items', []):
        table_data.append([
            Paragraph(item.get('date', ''), body_style),
            Paragraph(item.get('flower', ''), body_bold),
            Paragraph(f"{item.get('weight', '')} X {item.get('rate', '')}", body_right),
            Paragraph(str(item.get('box', '')), body_right),
            Paragraph(item.get('luggage', ''), body_right),
            Paragraph(item.get('coolie', ''), body_right),
            Paragraph(item.get('total_amt', ''), body_right_bold),
        ])

    # Totals Row
    totals = bill_data.get('totals', {})
    table_data.append([
        Paragraph('<b>Total</b>', body_bold),
        Paragraph('', body_style),
        Paragraph(f"<b>{totals.get('total_weight', '600.000')}</b>", body_right_bold),
        Paragraph(f"<b>{totals.get('total_boxes', '40')}</b>", body_right_bold),
        Paragraph(f"<b>{totals.get('total_luggage', '6000.00')}</b>", body_right_bold),
        Paragraph(f"<b>{totals.get('total_coolie', '600.00')}</b>", body_right_bold),
        Paragraph(f"<b>{totals.get('total_amt', '24000.00')}</b>", body_right_bold),
    ])

    col_widths = [24*mm, 42*mm, 36*mm, 15*mm, 21*mm, 18*mm, 24*mm]
    t_items = Table(table_data, colWidths=col_widths)
    t_items.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,0), 0.75, colors.black),
        ('LINEBELOW', (0,0), (-1,0), 0.75, colors.black),
        ('LINEABOVE', (0,-1), (-1,-1), 0.5, colors.black),
        ('LINEBELOW', (0,-1), (-1,-1), 0.75, colors.black),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
    ]))
    story.append(t_items)
    story.append(Spacer(1, 3*mm))

    # 5. Deduction & Settlement Summary Block
    ded = bill_data.get('deductions', {})
    settle = bill_data.get('settlement', {})

    summary_data = [
        [
            Paragraph(f"Commission ({ded.get('commission_pct', '15')}%)", body_style),
            Paragraph(f": &nbsp; {ded.get('commission_amt', '3600.00')}", body_right),
            Paragraph('Total Amount', body_bold),
            Paragraph(f": &nbsp; {settle.get('total_amt', '24000.00')}", body_right_bold),
        ],
        [
            Paragraph('Total Luggage', body_style),
            Paragraph(f": &nbsp; {ded.get('total_luggage', '6000.00')}", body_right),
            Paragraph('Total Less', body_bold),
            Paragraph(f": &nbsp; {settle.get('total_less', '10200.00')}", body_right_bold),
        ],
        [
            Paragraph('Total Expense', body_style),
            Paragraph(f": &nbsp; {ded.get('total_expense', '0.00')}", body_right),
            Paragraph('<b>Net Balance</b>', body_bold),
            Paragraph(f"<b>: &nbsp; Rs. {settle.get('net_balance', '13800.00')}</b>", body_right_bold),
        ],
        [
            Paragraph('Coolie', body_style),
            Paragraph(f": &nbsp; {ded.get('coolie', '600.00')}", body_right),
            Paragraph('', body_style),
            Paragraph('', body_style),
        ],
        [
            Paragraph('Advance Deduction', body_style),
            Paragraph(f": &nbsp; {ded.get('adv_deducted', '0.00')}", body_right),
            Paragraph('', body_style),
            Paragraph('', body_style),
        ],
        [
            Paragraph('<b>Total Less</b>', body_bold),
            Paragraph(f"<b>: &nbsp; {ded.get('total_less', '10200.00')}</b>", body_right_bold),
            Paragraph('', body_style),
            Paragraph('', body_style),
        ],
    ]

    t_summary = Table(summary_data, colWidths=[45*mm, 45*mm, 45*mm, 45*mm])
    t_summary.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,-1), 0.5, colors.transparent),
        ('TOPPADDING', (0,0), (-1,-1), 1.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5),
        ('LINEBELOW', (0,-1), (1,-1), 0.75, colors.black),
        ('LINEBELOW', (2,2), (3,2), 0.75, colors.black),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 6*mm))

    # 6. Footer Note
    footer_text = Paragraph(
        'Software by : ABILITY SOFTWARE - 9789085818 (Faithfully Reproduced for AVT Web)',
        ParagraphStyle('Footer', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, alignment=TA_CENTER, textColor=colors.HexColor('#64748b'))
    )
    story.append(footer_text)

    # Build document
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
