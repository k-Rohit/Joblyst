""" 
Run the hybrid validation check for fabricated tailoring
from the tailored resume.
"""

from __future__ import annotations

from joblyst.validation_hybrid import validate_pack_hybrid
from joblyst.graph.state import AgentState
from joblyst.corpus import build_corpus

def validate_tailoring(state: AgentState) -> dict:
    pack = state.get("tailoring")
    if pack is None: # tailor already recorded why in state["errors"]
        return {"fabrication_flags": 0, "fabrication_report": None}
    corpus = build_corpus(state.get("cv_text", ""))
    
    job_id = state.get("selected_job_id")
    ranked = next((r for r in state.get("ranked_jobs", []) if r.job.job_id == job_id), None)
    job_context = [f"{ranked.job.title} at {ranked.job.company}", ranked.job.company] if ranked else []
    
    report = validate_pack_hybrid(pack, corpus, research_notes=state.get("research_notes"), job_context=job_context)
    return {"fabrication_flags": report.flags, "fabrication_report": report}
    

    
    


