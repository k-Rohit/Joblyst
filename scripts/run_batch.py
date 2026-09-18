import json
import os
from pathlib import Path

from joblyst.profile import extract_profile
from joblyst.schemas.schemas import Profile
from joblyst.tools.cv_reader import extract_cv_content
from joblyst.tools.search_job import CacheSource

_CV_DIR = Path(__file__).parent.parent / "data" / "fixture_cvs"
# Dev cache only, not the golden dataset — regenerate anytime by deleting this
# file (e.g. after changing EXTRACT_PROFILE_PROMPT, since a stale cache would
# silently hide the effect of a prompt change).
_PROFILE_CACHE_PATH = Path(__file__).parent.parent / "data" / "fixture_profiles_cache.json"


def _load_or_extract_profiles(cv_dir: Path, cache_path: Path) -> dict[str, Profile]:
    """Extract each fixture CV's profile once, reusing a JSON cache on later runs.

    extract_profile is a real LLM call — re-running this script during
    development shouldn't re-pay for it on every CV that hasn't changed.
    """
    cached_raw: dict[str, dict] = {}
    if cache_path.exists():
        cached_raw = json.loads(cache_path.read_text())

    profiles: dict[str, Profile] = {}
    dirty = False
    for cv in sorted(os.listdir(cv_dir)):
        if not cv.endswith(".pdf"):
            continue
        if cv in cached_raw:
            profiles[cv] = Profile.model_validate(cached_raw[cv])
            continue
        cv_content = extract_cv_content(cv_dir / cv)
        profile = extract_profile(cv_content, thread_id=f"baseline-extract-{cv}", tags=["baseline-batch"])
        profiles[cv] = profile
        cached_raw[cv] = profile.model_dump()
        dirty = True

    if dirty:
        cache_path.write_text(json.dumps(cached_raw, indent=2, ensure_ascii=False))
    return profiles


# load the cached_jobs.json
cached_jobs = CacheSource()

# extract the profiles only once, reusing the disk cache across runs
profiles = _load_or_extract_profiles(_CV_DIR, _PROFILE_CACHE_PATH)
