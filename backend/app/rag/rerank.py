"""The reranker — a second, closer read of the passages the search found, so the best ones come first.

Plain English: the vector search (store.search) is fast but rough: it compares the question and each passage
separately, as lists of numbers. For "can I take lisinopril while pregnant?" it ranked an angioedema warning
level with the fetal-toxicity warning. The reranker is a small "cross-encoder" model that reads the question
and a passage TOGETHER and scores how well that passage answers that question. We fetch a few more passages
than we need, let the reranker score them, keep the best and hand them to the AI best-first.

Free and local: ms-marco-MiniLM-L-6-v2 (about 23 MB, ONNX), run with onnxruntime and tokenizers, which
ChromaDB already installs. Downloaded once from Hugging Face into its cache. About 0.05 s per passage on a
laptop CPU (0.6-0.9 s for 15 passages). If the model can't be loaded or fails, we keep the search's order —
never an error.

Chosen by trying three free rerankers on our own label passages: this one put the right passage first for all
four test questions; the larger bge-reranker-base was 4x slower and no better.
"""

import logging
from collections.abc import Callable, Sequence

from app.config import Settings
from app.rag.store import Chunk

log = logging.getLogger(__name__)

RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
MODEL_FILE = "onnx/model_quantized.onnx"
TOKENIZER_FILE = "tokenizer.json"
MAX_TOKENS = 512

Scorer = Callable[[str, Sequence[str]], Sequence[float]]


class Reranker:
    def __init__(self, score: Scorer):
        self.score = score

    def rerank(self, query: str, chunks: list[Chunk], k: int) -> list[Chunk]:
        """The k passages that best answer `query`, best first. Equal scores keep the search's order."""
        if not chunks:
            return []
        try:
            scores = [float(s) for s in self.score(query, [c.text for c in chunks])]
        except Exception:  # noqa: BLE001 — a reranker problem must never break an answer
            log.warning("reranker failed; using the search order", exc_info=True)
            return chunks[:k]
        order = sorted(range(len(chunks)), key=lambda i: -scores[i])  # sorted() is stable: ties keep search order
        return [chunks[i].model_copy(update={"score": round(scores[i], 3)}) for i in order[:k]]


def model_cached(repo: str) -> bool:
    """Is the model already downloaded (so a test can use it without the internet)?"""
    from huggingface_hub import try_to_load_from_cache

    return all(isinstance(try_to_load_from_cache(repo, f), str) for f in (MODEL_FILE, TOKENIZER_FILE))


def _onnx_scorer(repo: str) -> Scorer:
    import os
    import numpy as np
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(hf_hub_download(repo, TOKENIZER_FILE))
    tokenizer.enable_truncation(MAX_TOKENS)  # long passages: the start is read, the rest cut off
    tokenizer.enable_padding()
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.intra_op_num_threads = min(4, os.cpu_count() or 1)
    session = ort.InferenceSession(hf_hub_download(repo, MODEL_FILE), sess_options=opts, providers=["CPUExecutionProvider"])
    wanted = {i.name for i in session.get_inputs()}

    def score(query: str, texts: Sequence[str]) -> list[float]:
        encoded = tokenizer.encode_batch([(query, t) for t in texts])
        inputs = {"input_ids": [e.ids for e in encoded], "attention_mask": [e.attention_mask for e in encoded],
                  "token_type_ids": [e.type_ids for e in encoded]}
        feed = {name: np.array(v, dtype=np.int64) for name, v in inputs.items() if name in wanted}
        return session.run(None, feed)[0][:, 0].tolist()  # one relevance score per (question, passage) pair

    return score


def load_reranker(settings: Settings) -> Reranker | None:
    """The reranker, or None when it is switched off (RAG_RERANK=false) or can't be loaded (e.g. offline on the
    very first run) — drug-label questions then use the search's own order."""
    if not settings.rag_rerank:
        return None
    try:
        return Reranker(_onnx_scorer(settings.rag_rerank_model))
    except Exception:  # noqa: BLE001
        log.warning("reranker unavailable (%s); drug-label passages keep the search order",
                    settings.rag_rerank_model, exc_info=True)
        return None
