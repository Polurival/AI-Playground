"""Comparison report: fixed-size vs structural chunking statistics."""


def _stats(chunks: list[dict]) -> dict:
    lengths = [len(c["text"]) for c in chunks]
    return {
        "count": len(lengths),
        "avg": sum(lengths) / len(lengths) if lengths else 0,
        "min": min(lengths) if lengths else 0,
        "max": max(lengths) if lengths else 0,
    }


PROS_CONS = {
    "fixed": {
        "pros": [
            "Predictable chunk size — embedding model never sees oversized input.",
            "Simple to implement and tune (one size parameter).",
            "Works on any text regardless of structure.",
        ],
        "cons": [
            "Cuts mid-sentence or mid-dialogue, losing narrative coherence.",
            "Scene/chapter boundaries ignored — a single dialogue can span two chunks.",
            "Overlap helps but doesn't fully restore context at cuts.",
        ],
    },
    "structural": {
        "pros": [
            "Each chunk = one chapter, preserving full scene and dialogue context.",
            "Metadata (chapter title) maps directly to the content.",
            "Retrieval returns self-contained narrative units.",
        ],
        "cons": [
            "Highly variable length — short chapters ~500 chars, long ones ~6000+.",
            "Large chapters may exceed embedding model token limits.",
            "Paragraph-split fallback partially breaks structural integrity.",
        ],
    },
}


def print_report(fixed_chunks: list[dict], struct_chunks: list[dict]) -> None:
    fs = _stats(fixed_chunks)
    ss = _stats(struct_chunks)

    print("\n" + "=" * 60)
    print("  CHUNKING STRATEGY COMPARISON REPORT")
    print("=" * 60)

    print(f"\n{'Metric':<22} {'Fixed-size':>15} {'Structural':>15}")
    print("-" * 54)
    print(f"{'Total chunks':<22} {fs['count']:>15} {ss['count']:>15}")
    print(f"{'Avg length (chars)':<22} {fs['avg']:>15.1f} {ss['avg']:>15.1f}")
    print(f"{'Min length (chars)':<22} {fs['min']:>15} {ss['min']:>15}")
    print(f"{'Max length (chars)':<22} {fs['max']:>15} {ss['max']:>15}")

    for strategy, label in [("fixed", "FIXED-SIZE"), ("structural", "STRUCTURAL")]:
        pc = PROS_CONS[strategy]
        print(f"\n  [{label}]")
        print("  Pros:")
        for p in pc["pros"]:
            print(f"    + {p}")
        print("  Cons:")
        for c in pc["cons"]:
            print(f"    - {c}")

    print("\n  RECOMMENDATION FOR LITERARY TEXT:")
    print("  Structural chunking preserves scene and dialogue coherence better,")
    print("  making it preferable for Q&A over narrative content. Fixed-size")
    print("  chunking suits keyword-heavy or factual documents where sentence")
    print("  boundaries matter less.")
    print("=" * 60 + "\n")
