"""Генерирует docxtpl-шаблон templates/dogovor_samozanyatyi.docx (запускать при правке вёрстки)."""
from pathlib import Path
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

OUT = Path(__file__).parent / "templates" / "dogovor_samozanyatyi.docx"

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin, sec.right_margin = Cm(2.5), Cm(1.5)
sec.top_margin, sec.bottom_margin = Cm(1.5), Cm(1.5)

st = doc.styles["Normal"]
st.font.name, st.font.size = "Times New Roman", Pt(12)
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
pf = st.paragraph_format
pf.space_before, pf.space_after, pf.line_spacing = Pt(0), Pt(0), 1.0


def para(text="", bold=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY, before=0, after=0, indent=None, hanging=None):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(before), Pt(after)
    if indent is not None:
        p.paragraph_format.left_indent = Cm(indent)
    if hanging is not None:
        p.paragraph_format.first_line_indent = Cm(-hanging)
    if text:
        r = p.add_run(text)
        r.bold = bold
    return p


para("{{ title }} № {{ number }}", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=6)
p = para("{{ city }}\t{{ date }}", align=WD_ALIGN_PARAGRAPH.LEFT, after=10)
p.paragraph_format.tab_stops.add_tab_stop(Cm(17), WD_TAB_ALIGNMENT.RIGHT)
p = para("{{r preamble }}", after=4)
p.paragraph_format.first_line_indent = Cm(1)

para("{%p for s in sections %}")
para("{{ s.num }}. {{ s.title }}", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, before=8, after=4)
para("{%p for it in s.points %}")
para("{{ it.num }} {{ it.text }}", after=2)
para("{%p for b in it.bullets %}")
para("–\t{{ b }}", indent=1.25, hanging=0.5).paragraph_format.tab_stops.add_tab_stop(Cm(1.25))
para("{%p endfor %}")
para("{%p endfor %}")
para("{%p endfor %}")

para("{{ req_no }}. РЕКВИЗИТЫ И ПОДПИСИ СТОРОН", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, before=8, after=6).paragraph_format.keep_with_next = True

t = doc.add_table(rows=1, cols=2)
t.alignment = WD_TABLE_ALIGNMENT.CENTER
t.autofit = False
for c in t.columns:
    for cell in c.cells:
        cell.width = Cm(8.5)
# без рамок
tblPr = t._tbl.tblPr
b = OxmlElement("w:tblBorders")
for e in ("top", "left", "bottom", "right", "insideH", "insideV"):
    x = OxmlElement(f"w:{e}"); x.set(qn("w:val"), "nil"); b.append(x)
tblPr.append(b)


def cell_fill(cell, role, title, lines, pos, sign):
    cell.paragraphs[0].text = ""
    r = cell.paragraphs[0].add_run("{{ %s }}" % role); r.bold = True
    cell.paragraphs[0].paragraph_format.space_after = Pt(4)
    pp = cell.add_paragraph(); rr = pp.add_run("{{ %s }}" % title); rr.bold = True
    cell.add_paragraph("{%%p for l in %s %%}" % lines)
    cell.add_paragraph("{{ l }}")
    cell.add_paragraph("{%p endfor %}")
    pp2 = cell.add_paragraph("{{ %s }}" % pos); pp2.paragraph_format.space_before = Pt(14)
    sp = cell.add_paragraph("{{ %s }}" % sign); sp.paragraph_format.space_before = Pt(10)


trPr = t.rows[0]._tr.get_or_add_trPr()
cs = OxmlElement("w:cantSplit"); trPr.append(cs)
cell_fill(t.rows[0].cells[0], "role_c", "cust_title", "cust_lines", "cust_pos", "cust_sign")
cell_fill(t.rows[0].cells[1], "role_e", "ex_title", "ex_lines", "ex_pos", "ex_sign")

OUT.parent.mkdir(exist_ok=True)
doc.save(OUT)
print("ok", OUT)
