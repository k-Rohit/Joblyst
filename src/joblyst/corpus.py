"""

The candidate corpus: the ONLY permissible content source for tailoring.

Every bullet, skill, and claim in a tailored application must trace back to a
``CorpusItem`` here. Segmentation is a deliberately simple line/keyword
heuristic — no LLM, no NLP libraries. It must stay deterministic and faithful
to the CV's literal text, because it's the ground truth the fabrication
validator checks generated content against: an LLM-built corpus would let a
tailoring hallucination "match" a corpus-building hallucination.

Known limitation, left alone on purpose: a bullet that wraps across two PDF
lines starting with a capitalized word (e.g. a line ending mid-sentence, the
next starting with "PostgreSQL") can split into two corpus items instead of
one. Splitting on full stops instead was considered and rejected — periods
also appear in abbreviations and decimals ("B.Tech", "1.5+ years"), which a
naive split would tear apart worse than the problem it fixes.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

CorpusKind = Literal["bullet", "skill", "education", "summary"]
CorpusSource = Literal["cv", "linkedin"]

# Section-heading keywords -> the kind of items the section yields. Anything
# unmatched (including these) is treated as experience (bullets) — the safest
# default — so this set only exists to help _looks_like_heading recognize a
# non-all-caps "Experience"/"Projects" line as a heading at all.
_SUMMARY_HEADINGS = {"summary", "profile", "about", "objective"}
_SKILL_HEADINGS = {"skills", "technologies", "tools", "competencies", "skills & tools"}
_EDUCATION_HEADINGS = {"education"}
_EXPERIENCE_HEADINGS = {"experience", "work experience", "employment", "professional experience", "projects"}
# A heading containing any of these words is a skills section even when it's
# not an exact match ("Technical Skills", "Tech Stack", "Skills & Tools").
_SKILL_HEADING_WORDS = {"skills", "skill", "technologies", "tools", "competencies", "stack"}

_BULLET_GLYPHS = ("-", "•", "*", "-", "◦")
_TERMINAL_PUNCT = (".", "!", "?", ":", ";")
_PHONEISH = re.compile(r"\+?\d[\d\s().\-/]{6,}")
_PIPES = re.compile(r"\s*\|\s*")


class CorpusItem(BaseModel):
    """One verifiable unit of the candidate's real experience."""

    id: str
    text: str
    kind: CorpusKind
    source: CorpusSource
    section: str  # the heading it came from


class CandidateCorpus(BaseModel):
    """All corpus items, addressable by id for grounding checks."""

    items: list[CorpusItem] = Field(default_factory=list)

    def get(self, item_id: str) -> CorpusItem | None:
        """Look up one item by its id, or ``None``."""
        return next((item for item in self.items if item.id == item_id), None)

    def skills(self) -> list[str]:
        """Texts of every skill item (the allowed skill vocabulary)."""
        return [item.text for item in self.items if item.kind == "skill"]

    def render_for_prompt(self) -> str:
        """Render as ``[id] (section) text`` lines the tailor LLM selects from.

        The section is included so the model can tell a PROJECTS-sourced bullet
        apart from an EXPERIENCE-sourced one — needed to route each into
        CVContent.project vs CVContent.experience correctly.
        """
        return "\n".join(f"[{item.id}] ({item.section}) {item.text}" for item in self.items)


def build_corpus(cv_text: str) -> CandidateCorpus:
    """Build the corpus from CV text.

    LinkedIn export parsing isn't implemented yet — ``CorpusSource`` allows for
    it so the schema doesn't need to change later, but only "cv" is ever
    produced right now.
    """
    return CandidateCorpus(items=_segment_cv(cv_text))


def _looks_like_heading(line: str) -> bool:
    """A short standalone line reads as a section heading.

    Word-count/punctuation alone can't tell a real heading ("PROJECTS") from a
    short project or company name ("AgentCare") — both are one word with no
    comma or trailing period. Real headings in practice are shouted in caps;
    a short mixed-case line that isn't a recognized keyword is left alone.
    """
    words = line.split()
    shape_ok = 0 < len(words) <= 3 and not line.startswith(_BULLET_GLYPHS) and "," not in line and not line.rstrip().endswith(".")
    if not shape_ok:
        return False
    if line.isupper():
        return True
    lowered = line.lower().strip(" :")
    known = lowered in _SUMMARY_HEADINGS | _SKILL_HEADINGS | _EDUCATION_HEADINGS | _EXPERIENCE_HEADINGS
    return known or any(word.strip("&/") in _SKILL_HEADING_WORDS for word in lowered.split())


def _section_kind(heading: str) -> CorpusKind:
    """Map a section heading to the kind of items it yields."""
    lowered = heading.lower().strip(" :")
    if lowered in _SUMMARY_HEADINGS:
        return "summary"
    if lowered in _EDUCATION_HEADINGS:
        return "education"
    if lowered in _SKILL_HEADINGS or any(word.strip("&/") in _SKILL_HEADING_WORDS for word in lowered.split()):
        return "skill"
    return "bullet"


def _logical_lines(cv_text: str) -> list[str]:
    """Re-join PDF-wrapped lines into logical ones.

    A line continues the previous one when that previous line ends mid-sentence
    (no terminal punctuation) and the new line reads as a continuation: it does
    not open a bullet, does not look like a heading, and either the previous
    line ends with a comma or the new line starts lowercase. Blank lines are
    hard barriers, so paragraphs never merge across them.
    """
    lines: list[str] = []
    for raw in cv_text.splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        prev = lines[-1] if lines else ""
        if (
            prev
            and not prev.endswith(_TERMINAL_PUNCT)
            and not line.startswith(_BULLET_GLYPHS)
            and not _looks_like_heading(line)
            and (prev.endswith(",") or line[:1].islower())
        ):
            lines[-1] = f"{prev} {line}"
        else:
            lines.append(line)
    return [line for line in lines if line]


def _segment_cv(cv_text: str) -> list[CorpusItem]:
    """Split raw CV text into corpus items using line/keyword heuristics."""
    items: list[CorpusItem] = []
    counters: dict[str, int] = {}
    section = ""
    kind: CorpusKind = "summary"  # leading paragraph before any heading

    def add(text: str, item_kind: CorpusKind, item_section: str) -> None:
        text = text.strip()
        if len(text) < 3:
            return
        counters[item_kind] = counters.get(item_kind, 0) + 1
        items.append(
            CorpusItem(
                id=f"cv-{item_kind}-{counters[item_kind]:03d}",
                text=text,
                kind=item_kind,
                source="cv",
                section=item_section or "(top)",
            )
        )

    for line in _logical_lines(cv_text):
        # Contact/header noise: emails, and pipe rows that read as contact
        # details (phone numbers, profile links). Pipe rows that carry real
        # content survive with the pipes turned into commas.
        if "@" in line or ("|" in line and (_PHONEISH.search(line) or "linkedin.com" in line.lower())):
            continue
        line = _PIPES.sub(", ", line)
        if _looks_like_heading(line):
            section = line
            kind = _section_kind(line)
            continue
        if kind == "skill":
            skill_line = line.rstrip(".")
            if ":" in skill_line:
                # Drop a leading category label ("AI/ML & GenAI: LangChain, ...")
                # so it doesn't glue onto the first skill in the line.
                skill_line = skill_line.split(":", 1)[1]
            for skill in skill_line.split(","):
                add(skill, "skill", section)
        elif kind in ("summary", "education"):
            add(line, kind, section)
        else:
            add(line.lstrip("".join(_BULLET_GLYPHS)).strip(), "bullet", section)
    return items


if __name__ == "__main__":
    import sys

    from joblyst.tools.cv_reader import extract_cv_content

    path = sys.argv[1] if len(sys.argv) > 1 else "data/Kumar_Rohit_Resume.pdf"
    corpus = build_corpus(extract_cv_content(path))
    print(f"{len(corpus.items)} corpus items\n")
    for item in corpus.items:
        print(f"[{item.id}] ({item.kind}, section={item.section!r}) {item.text}")
