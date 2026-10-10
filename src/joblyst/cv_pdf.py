"""Render a tailored CV as a PDF."""

from __future__ import annotations

from fpdf import FPDF

from joblyst.schemas.schemas import CVContent

# fpdf2's built-in Helvetica only knows Latin-1 characters. LLM text often has
# curly quotes and dashes, which would crash the render, so swap them for plain ones.
_PLAIN = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "•": "-", "…": "...", " ": " "})


def _plain(text: str) -> str:
    # Anything still outside Latin-1 (e.g. emoji) becomes "?" instead of crashing.
    return text.translate(_PLAIN).encode("latin-1", "replace").decode("latin-1")


def render_cv_pdf(cv: CVContent, name: str | None) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_title("CV")
    width = pdf.epw

    def heading(text: str) -> None:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(width, 7, _plain(text), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9.5)

    def line(text: str, indent: str = "") -> None:
        # new_x/new_y put the cursor back at the left margin; multi_cell's default
        # leaves it at the right edge and the next line overlaps.
        pdf.multi_cell(width, 4.6, _plain(indent + text), new_x="LMARGIN", new_y="NEXT")

    if name:
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(width, 9, _plain(name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10.5)
    line(cv.headline)

    heading("SUMMARY")
    line(cv.summary)

    if cv.experience:
        heading("EXPERIENCE")
        for role in cv.experience:
            pdf.set_font("Helvetica", "B", 9.5)
            line(f"{role.role}, {role.company}" + (f" ({role.dates})" if role.dates else ""))
            pdf.set_font("Helvetica", "", 9.5)
            for bullet in role.bullets:
                line(bullet.text, indent="- ")
            pdf.ln(1)

    if cv.project:
        heading("PROJECTS")
        for project in cv.project:
            pdf.set_font("Helvetica", "B", 9.5)
            line(project.project_domain)
            pdf.set_font("Helvetica", "", 9.5)
            if project.project_skills:
                line(", ".join(project.project_skills))
            for bullet in project.project_bullets:
                line(bullet.text, indent="- ")
            pdf.ln(1)

    if cv.skills:
        heading("SKILLS")
        line(", ".join(cv.skills))

    if cv.education:
        heading("EDUCATION")
        for entry in cv.education:
            line(entry)

    return bytes(pdf.output())
