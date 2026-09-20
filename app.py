"""Streamlit testbed for the whole Joblyst pipeline, with Opik tracing.

Not a product UI — a way to actually exercise CV extraction, search,
reformulation, tailoring, fabrication checking, and the external-job path,
all sharing one thread_id so Opik groups everything under one trace.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import streamlit as st

from joblyst.profile import extract_profile
from joblyst.runner import run_external_job, run_search, run_tailor
from joblyst.schemas.schemas import RankedJob
from joblyst.tools.cv_reader import extract_cv_content
from joblyst.tracing import opik_url, register_prompts

st.set_page_config(page_title="Joblyst 💼", layout="wide", page_icon="💼")

if "prompts_registered" not in st.session_state:
    register_prompts()  # version any prompt edits in Opik's prompt library
    st.session_state.prompts_registered = True

# --- session state -----------------------------------------------------
if "thread_id" not in st.session_state:
    st.session_state.thread_id = uuid4().hex[:8]
if "profile" not in st.session_state:
    st.session_state.profile = None
if "cv_text" not in st.session_state:
    st.session_state.cv_text = ""
if "search_result" not in st.session_state:
    st.session_state.search_result = None
if "tailor_result" not in st.session_state:
    st.session_state.tailor_result = None


def _render_tailor_result(result) -> None:
    """Shared display for a TailorResult, wherever it came from."""
    if result.errors:
        for e in result.errors:
            st.warning(e)
    if result.pack is None:
        return

    pack = result.pack
    st.subheader(pack.cv.headline)
    st.caption(pack.cv.summary)

    for entry in pack.cv.experience:
        st.markdown(f"**{entry.role} — {entry.company}** {entry.dates}")
        for b in entry.bullets:
            st.markdown(f"- {b.text}  \n  <sub>ref: `{b.corpus_ref}`</sub>", unsafe_allow_html=True)

    for entry in pack.cv.project:
        st.markdown(f"**Project — {entry.project_domain}**")
        for b in entry.project_bullets:
            st.markdown(f"- {b.text}  \n  <sub>ref: `{b.corpus_ref}`</sub>", unsafe_allow_html=True)

    st.markdown("**Skills:** " + ", ".join(pack.cv.skills))
    st.markdown("**Cover letter**")
    st.text_area("cover_letter", pack.cover_letter, height=200, label_visibility="collapsed")
    st.info(f"Honesty note: {pack.honesty_note}")

    st.markdown("### Fabrication check")
    st.metric("Flags", f"{result.fabrication_flags} / {result.fabrication_report.claims_checked if result.fabrication_report else 0}")
    if result.fabrication_report:
        for f in result.fabrication_report.flagged:
            st.error(f"**{f.where}** — {f.reason}\n\n> {f.text}")


# --- sidebar: CV + thread -----------------------------------------------
with st.sidebar:
    st.header("Candidate")
    st.text_input("thread_id (reuse to keep everything on one Opik thread)", key="thread_id")
    st.link_button("Open Opik dashboard", opik_url())

    uploaded = st.file_uploader("Upload resume (PDF)", type=["pdf"])
    if uploaded and st.button("Extract profile"):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = Path(tmp.name)
        with st.spinner("Reading CV and extracting profile..."):
            cv_text = extract_cv_content(tmp_path)
            profile = extract_profile(cv_text, thread_id=st.session_state.thread_id)
        st.session_state.cv_text = cv_text
        st.session_state.profile = profile
        st.session_state.search_result = None
        st.session_state.tailor_result = None

    if st.session_state.profile:
        p = st.session_state.profile
        st.success(f"{p.name or 'Candidate'} — {p.seniority}, {p.years_experience} yrs")
        st.caption(", ".join(p.primary_roles))
        with st.expander("Skills / projects"):
            st.write("**Skills:** " + ", ".join(p.skills))
            for proj in p.projects:
                st.write(f"- {proj}")

st.title("Joblyst 💼")

if not st.session_state.profile:
    st.info("Upload a resume in the sidebar and extract a profile to get started.")
    st.stop()

tab_search, tab_external = st.tabs(["Search", "Paste an external job"])

# --- Search tab ----------------------------------------------------------
with tab_search:
    target_role = st.text_input("Target role override (optional — leave blank to use your CV's own history)")
    if st.button("Run search", type="primary"):
        with st.spinner("Searching, ranking, reformulating if needed..."):
            st.session_state.search_result = run_search(
                st.session_state.profile,
                st.session_state.cv_text,
                thread_id=st.session_state.thread_id,
                target_role=target_role or None,
            )
        st.session_state.tailor_result = None

    result = st.session_state.search_result
    if result:
        st.caption(f"Sources used: {', '.join(result.jobs_sources) or 'none'} · reformulated {result.reformulation_count}x")
        for e in result.errors:
            st.warning(e)

        ranked: list[RankedJob] = result.ranked_jobs
        for r in ranked:
            with st.expander(f"[{r.fit_score}] {r.job.title} @ {r.job.company} ({r.job.source})"):
                st.write(r.fit_explanation)
                st.write("**Matched:** " + ", ".join(r.matched_skills))
                st.write("**Gaps:** " + ", ".join(r.gaps))
                if st.button("Tailor this job", key=f"tailor-{r.job.job_id}"):
                    with st.spinner("Tailoring and checking for fabrication..."):
                        st.session_state.tailor_result = run_tailor(
                            thread_id=st.session_state.thread_id,
                            selected_job_id=r.job.job_id,
                        )

    if st.session_state.tailor_result:
        st.divider()
        _render_tailor_result(st.session_state.tailor_result)

# --- External job tab ------------------------------------------------------
with tab_external:
    job_text = st.text_area("Paste the full job posting", height=250)
    if st.button("Score, tailor, and validate", type="primary"):
        with st.spinner("Extracting fields, scoring, tailoring, validating..."):
            ext_result = run_external_job(
                thread_id=st.session_state.thread_id,
                external_job_text=job_text,
            )
        st.session_state.tailor_result = ext_result

        if ext_result.ranked_jobs:
            scored = ext_result.ranked_jobs[-1]  # the one score_external_job just appended
            st.metric("Fit score", scored.fit_score)
            st.caption(scored.fit_explanation)

    if st.session_state.tailor_result and job_text:
        st.divider()
        _render_tailor_result(st.session_state.tailor_result)
