"""Score the chat server's retrieval against scripts/eval/retrieval_eval.json.

For each question, runs the same search the chat server uses for a first turn
(ConversationVectorizer.search_passages: ruri-v3 dense + Zilliz BM25 fused with
RRF, best chunk per video, optional reranker) and checks whether any of the
question's relevant videos is returned. --mode hybrid scores the raw
chunk-level hybrid search instead (several chunks of one video can fill the
top k there).

Metrics (per category and overall; no_answer questions are skipped):
  Hit@k  share of questions with a relevant video in the top k results.
         Hit@5 is what the chat answer sees (it uses the top 5 results).
  MRR    mean of 1 / rank of the first relevant result within the top
         --depth results (0 when none is found).
With a reranker, use --depth 10 to match the chat server, which reranks
max(5, RERANK_CANDIDATES) = 10 candidates.

Usage (from the project root):
  python scripts/eval/run_retrieval_eval.py
  python scripts/eval/run_retrieval_eval.py --mode bm25          # BM25 only
  python scripts/eval/run_retrieval_eval.py --reranker cl-nagoya/ruri-v3-reranker-310m --candidates 30
  python scripts/eval/run_retrieval_eval.py --category asr -v    # show misses
  python scripts/eval/run_retrieval_eval.py --out results.json   # save details
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from core.conversation_vectorizer import ConversationVectorizer  # noqa: E402

# sentence-transformers shows a "Batches" progress bar per query whenever its
# logger is at INFO; keep it at WARNING so the per-question output stays readable.
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

DEFAULT_EVAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retrieval_eval.json")
HIT_KS = (1, 3, 5, 10)


def video_id(file_name: str) -> str:
    return re.sub(r"(_transcription)?\.json$", "", file_name)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate retrieval with retrieval_eval.json")
    p.add_argument("--eval-file", default=DEFAULT_EVAL_FILE)
    p.add_argument("--mode", choices=["passages", "hybrid", "bm25"], default="passages",
                   help="passages = what the chat server uses (default: best chunk per video "
                        "+ neighbouring chunks); hybrid = raw chunk-level hybrid search; "
                        "bm25 = BM25 only")
    p.add_argument("--depth", type=int, default=20,
                   help="Chunks retrieved per question; MRR and Hit@k look within this depth")
    p.add_argument("--reranker", default=None,
                   help="CrossEncoder to rerank hybrid results (e.g. cl-nagoya/ruri-v3-reranker-310m); "
                        "default reads RERANKER_MODEL, '' disables")
    p.add_argument("--candidates", type=int, default=None,
                   help="Hybrid results re-scored by the reranker (default: RERANK_CANDIDATES or 10); "
                        "use a value >= --depth")
    p.add_argument("--category", help="Only evaluate one category (keyword/paraphrase/asr)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Print the top 5 videos for every missed question")
    p.add_argument("--out", help="Write per-question results to this JSON file")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    with open(args.eval_file, encoding="utf-8") as f:
        questions = json.load(f)["questions"]
    questions = [q for q in questions if q["category"] != "no_answer"]
    if args.category:
        questions = [q for q in questions if q["category"] == args.category]
    if not questions:
        sys.exit("No questions to evaluate.")

    vectorizer = ConversationVectorizer(
        os.getenv("ZILLIZ_URI"),
        os.getenv("ZILLIZ_TOKEN"),
        reranker_model=args.reranker,
        rerank_candidates=args.candidates,
    )
    if not vectorizer.bm25_client:
        sys.exit("Zilliz client is not available - check ZILLIZ_URI / ZILLIZ_TOKEN.")

    if args.mode == "bm25" and vectorizer.reranker:
        sys.exit("--mode bm25 does not use the reranker; pass --reranker '' or use --mode hybrid.")
    reranker_name = vectorizer.reranker.model_name if vectorizer.reranker else None
    print(f"mode={args.mode} reranker={reranker_name} candidates={vectorizer.rerank_candidates} depth={args.depth}")

    rows = []
    for q in questions:
        started = time.perf_counter()
        if args.mode == "passages":
            results = vectorizer.search_passages(q["question"], limit=args.depth)
        elif args.mode == "hybrid":
            results = vectorizer.hybrid_search_bm25(q["question"], limit=args.depth)
        else:
            results = vectorizer.bm25_client.bm25_search(q["question"], limit=args.depth)

        elapsed = time.perf_counter() - started

        relevant = set(q["relevant_video_ids"])
        ranked = [video_id(r.file_name) for r in results]
        rank = next((i for i, v in enumerate(ranked, 1) if v in relevant), None)
        rows.append({
            "id": q["id"],
            "category": q["category"],
            "question": q["question"],
            "rank": rank,
            "num_results": len(results),
            "seconds": round(elapsed, 3),
            "top_videos": [
                {"video_id": video_id(r.file_name), "title": r.title, "score": r.score}
                for r in results[:5]
            ],
        })
        mark = f"rank {rank}" if rank else f"miss (top {args.depth})"
        print(f"{q['id']} [{q['category']:<10}] {mark:<16} {elapsed:5.2f}s  {q['question']}")
        if args.verbose and (rank is None or rank > 5):
            for i, r in enumerate(results[:5], 1):
                print(f"      {i}. {video_id(r.file_name)} {r.title[:50]}")

    # Search errors are logged and swallowed inside the client (it returns []),
    # so an all-empty run means the search failed, not that retrieval scored 0.
    if all(r["num_results"] == 0 for r in rows):
        sys.exit("Every search returned 0 results - the search failed; see the errors above.")

    groups = defaultdict(list)
    for r in rows:
        groups[r["category"]].append(r)
        groups["ALL"].append(r)

    hit_ks = [k for k in HIT_KS if k <= args.depth]
    header = f"\n{'category':<12}{'n':>4}" + "".join(f"{'Hit@' + str(k):>9}" for k in hit_ks) + f"{'MRR':>8}"
    print(f"{header}\n{'-' * (len(header) - 1)}")
    summary = {}
    for name in [c for c in ("keyword", "paraphrase", "asr") if c in groups] + ["ALL"]:
        g = groups[name]
        hits = {k: sum(1 for r in g if r["rank"] and r["rank"] <= k) / len(g) for k in hit_ks}
        mrr = sum(1 / r["rank"] for r in g if r["rank"]) / len(g)
        summary[name] = {"n": len(g), "mrr": mrr, **{f"hit@{k}": v for k, v in hits.items()}}
        print(f"{name:<12}{len(g):>4}" + "".join(f"{hits[k]:>9.2f}" for k in hit_ks) + f"{mrr:>8.3f}")

    # The first search also warms up the models, so leave it out of the latency.
    times = sorted(r["seconds"] for r in rows[1:]) or [rows[0]["seconds"]]
    print(f"\nSearch time per question (excluding the first): "
          f"median {times[len(times) // 2]:.2f}s, max {times[-1]:.2f}s")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"mode": args.mode, "reranker": reranker_name,
                       "candidates": vectorizer.rerank_candidates, "depth": args.depth, "summary": summary, "questions": rows},
                      f, ensure_ascii=False, indent=2)
        print(f"\nSaved details to {args.out}")


if __name__ == "__main__":
    main()
