"""Book-level alignment: give each scanned page its slice of a whole-book transcription, then align it as Rivok does.

Rivok's method needs a transcription per page. A whole-edition transcription (a PBY work, a Sefaria exact-edition
version, a Wikisource main-namespace work) has none, so the book-level step maps text to pages first:

1. OCR every page (Tesseract hOCR, the line cutter) and flatten the OCR into one word stream with page numbers;
2. anchors: word 4-grams (letter keys, no marks or punctuation) that occur exactly once in the OCR stream and exactly
   once in the transcription;
3. keep the longest chain of anchors that is increasing in both streams (patience LIS), so a repeated or misread
   passage cannot pull the alignment out of order;
4. each page's slice is the transcription from its first to its last anchored word, widened by ``margin`` words on
   both sides (the page aligner leaves the unmatched margin outside the lines);
5. the page and its slice then go through ``rivok_align.align_page`` and the same label rules as Wikisource pages.

Pages with fewer than ``min_anchors`` anchors get no slice (front matter, plates, pages of another work).
"""

from __future__ import annotations

import bisect
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Sequence

from htext.linepairs.rivok_align import key

N = 4


def _grams(keys: Sequence[str]) -> dict[tuple[str, ...], list[int]]:
    out: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for i in range(len(keys) - N + 1):
        g = tuple(keys[i:i + N])
        if all(len(k) >= 2 for k in g):
            out[g].append(i)
    return out


def anchors(ocr_words: Sequence[str], text_words: Sequence[str]) -> list[tuple[int, int]]:
    """Increasing (ocr index, text index) pairs from unique shared 4-grams."""
    ko = [key(w) for w in ocr_words]
    kt = [key(w) for w in text_words]
    go, gt = _grams(ko), _grams(kt)
    pairs = sorted((go[g][0], gt[g][0]) for g in go.keys() & gt.keys() if len(go[g]) == 1 and len(gt[g]) == 1)
    # longest chain increasing in both coordinates (pairs sorted by ocr index; LIS over text index)
    tails: list[int] = []
    tail_idx: list[int] = []
    prev = [-1] * len(pairs)
    for i, (_, t) in enumerate(pairs):
        k = bisect.bisect_left(tails, t)
        if k == len(tails):
            tails.append(t)
            tail_idx.append(i)
        else:
            tails[k] = t
            tail_idx[k] = i
        prev[i] = tail_idx[k - 1] if k else -1
    chain, i = [], tail_idx[-1] if tail_idx else -1
    while i >= 0:
        chain.append(pairs[i])
        i = prev[i]
    return chain[::-1]


@dataclass(frozen=True)
class PageSlice:
    page: int
    start: int  # text word index, inclusive
    end: int  # exclusive
    anchors: int



def page_direction(ocr_words: Sequence[str], page_of_ocr_word: Sequence[int], text_words: Sequence[str], min_shared: int = 20) -> int:
    """+1 if the pages follow the transcription in the order given, -1 if the text runs backwards over them.

    Some scans store a Hebrew book back to front (the archive's page order is the reverse of the reading order). The
    unique 4-grams shared by OCR and text then have text positions that fall as the page number rises, and the anchor
    chain (which must increase in both) finds almost nothing. The sign of the rank correlation between page and text
    position decides; with fewer than ``min_shared`` shared grams the order is left as given (+1).
    """
    ko = [key(w) for w in ocr_words]
    kt = [key(w) for w in text_words]
    go, gt = _grams(ko), _grams(kt)
    pts = sorted((page_of_ocr_word[go[g][0]], gt[g][0]) for g in go.keys() & gt.keys() if len(go[g]) == 1 and len(gt[g]) == 1)
    if len(pts) < min_shared:
        return 1
    n = len(pts)
    rank_t = {t: r for r, t in enumerate(sorted(t for _, t in pts))}
    xs = list(range(n)); ys = [rank_t[t] for _, t in pts]
    mx, my = (n - 1) / 2, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return -1 if cov < 0 else 1

def page_slices(page_of_ocr_word: Sequence[int], text_len: int, chain: Sequence[tuple[int, int]],
                margin: int = 12, min_anchors: int = 3) -> list[PageSlice]:
    """Each page's transcription slice from the anchor chain."""
    per_page: dict[int, list[int]] = defaultdict(list)
    for o, t in chain:
        for d in range(N):  # all words of the anchoring 4-gram
            per_page[page_of_ocr_word[o + d]].append(t + d)
    out = []
    for page in sorted(per_page):
        ts = per_page[page]
        if len(ts) < min_anchors * N:
            continue
        out.append(PageSlice(page, max(0, min(ts) - margin), min(text_len, max(ts) + 1 + margin), len(ts) // N))
    return out


def coverage(slices: Sequence[PageSlice], pages: int) -> dict[str, float]:
    c = Counter(s.page for s in slices)
    return {"pages": pages, "pages_with_slice": len(c), "share": round(len(c) / max(1, pages), 4)}
