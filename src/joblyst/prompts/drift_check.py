DRIFT_CHECK_PROMPT_NAME = "drift_check"

# The worked examples are deliberately synthetic and from other domains. Pairs
# lifted from the fixture CVs would let the eval re-run pass by memorising the
# exact claims it is measuring.
DRIFT_CHECK_PROMPT = """

A rewritten CV claim and its real source(s) are given below. Decide whether the rewrite
says anything the source does not support.

The one rule: flag a rewrite only for something it STATES that the source does not
support — a tool, a number, an outcome, or a level of responsibility that is new or
changed. Leaving things out is ALWAYS fine: dropping a number, a detail or a count,
shortening, generalising, or rephrasing with a synonym never makes a rewrite ungrounded.

Examples that are GROUNDED (do not flag):
  Source:  Cut API p95 latency from 800ms to 120ms by adding a Redis cache.
  Rewrite: Cut API latency significantly by adding a Redis cache.
  -> grounded. The numbers were dropped, and "significantly" is supported by 800ms to 120ms.

  Source:  Processed 40M shipment events daily through a Kafka pipeline.
  Rewrite: Processed millions of shipment events daily through a Kafka pipeline.
  -> grounded. 40M is millions; a truthful generalisation adds nothing.

  Source:  Migrated three legacy billing services to Kubernetes.
  Rewrite: Migrated legacy billing services to Kubernetes.
  -> grounded. The count was dropped, not changed.

  Source:  Set up on-call paging for the payments team.
  Rewrite: Set up on-call alerting for the payments team.
  -> grounded. A synonym, not a different tool.

Examples that are NOT GROUNDED (flag):
  Source:  Built weekly sales dashboards in Tableau.
  Rewrite: Built weekly sales dashboards in Tableau and Power BI.
  -> not grounded. Power BI is a tool the source never mentions.

  Source:  Reduced cloud costs by 18% through instance right-sizing.
  Rewrite: Reduced cloud costs by 30% through instance right-sizing.
  -> not grounded. The number was changed.

  Source:  Taught statistics to 120 students per year.
  Rewrite: Taught statistics to 120 students per year, raising pass rates by 20%.
  -> not grounded. The pass-rate outcome is invented.

  Source:  Contributed to the migration of the mobile app to React Native.
  Rewrite: Led the migration of the mobile app to React Native.
  -> not grounded. "Led" claims responsibility the source does not.

Now judge this one. In your reason, quote the exact phrase from the REWRITE that is
unsupported. If you cannot point to such a phrase, it is grounded.

Rewrite:
{rewrite}

Real source(s):
{sources}
"""
