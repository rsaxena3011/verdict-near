# Fixture schema

Each source file is JSON:

```json
{
  "unreachable": false,          // set true to simulate a down source (engine -> REVIEW)
  "findings": [
    {
      "id": "LK-001",
      "claim": "what this finding asserts, in one line",
      "evidence": [
        {"quote": "verbatim line from the source", "document_id": "locks-v3", "locator": "section 2"}
      ],
      "contradicts": ["DR-014"],  // ids of findings this one contradicts
      "unanswerable": false        // true when the source has nothing on this
    }
  ]
}
```

Rules:
- `quote` is verbatim. A paraphrase is not evidence; the engine treats
  empty/blank quotes as unquoted (contradiction degrades to REVIEW).
- `contradicts` is the investigator's suggestion; the engine only honors it
  when BOTH sides carry quotes (locks x drafts => BLOCK, reviews x reviews
  => REVIEW, anything else => REVIEW).
- These `.sample.json` files are STRUCTURAL SAMPLES with fictional content.
  The real fixtures (boss's locked facts, drafts, review notes, plus
  planted-error variants) land Oct 22-23 and replace them.
