"""Add the empty human-label fields to every ranking dataset item in Opik.

Run once after build_eval_dataset.py --push, then fill the fields in the Opik UI.
Idempotent: a field that already exists (i.e. one you filled) is never overwritten.

Usage:
    uv run python scripts/add_label_fields.py
"""

import sys

from joblyst.tracing import configure_opik

RANKING_DATASET = "joblyst-ranking-cases"

# fit_ok: "yes"/"no" (is the model's fit_score reasonable)
# matched_skills_real: "yes"/"no" (are all matched_skills really in the profile)
# verified: "true" once you have finished labeling the item
LABEL_FIELDS = {"fit_ok": "", "matched_skills_real": "", "notes": "", "verified": ""}


def main() -> None:
    if not configure_opik():
        sys.exit("Opik is not configured!")

    import opik

    dataset = opik.Opik().get_dataset(name=RANKING_DATASET)
    items = dataset.get_items()

    updated = []
    for item in items:
        missing = {k: v for k, v in LABEL_FIELDS.items() if k not in item}
        if missing:
            updated.append({**item, **missing})

    if not updated:
        print("all items already have the label fields")
        return

    # update() replaces the whole item, so each dict carries the full original content.
    dataset.update(updated, deduplication=False)
    print(f"added label fields to {len(updated)}/{len(items)} items")
    print(f"items now in dataset: {len(dataset.get_items())}")


if __name__ == "__main__":
    main()
