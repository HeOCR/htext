"""Book-level alignment on invented text: the anchor chain and per-page slices."""

from htext.linepairs.book import anchors, page_direction, page_slices

WORDS = ("אבן בית גמל דלת הר ורד זית חלב טל יין כוס לחם מים נר סלע עץ פרי צל קול רוח שמש תות "
         "אגם ברק גשם דשא הד ותיק זרע חול טרף ילד כתר לוח מלח נחל סוס ענן פרח צמח קיר רחוב שיר תבן").split()


def _book():
    text = WORDS * 1  # the transcription
    pages = [WORDS[0:16], WORDS[16:32], WORDS[32:]]
    ocr, page_of = [], []
    for p, ws in enumerate(pages, 1):
        ws = list(ws)
        if p == 2:
            ws[5] = "שגוי"  # an OCR misreading
        ocr += ws
        page_of += [p] * len(ws)
    return text, ocr, page_of


def test_chain_is_increasing_and_slices_cover_each_page():
    text, ocr, page_of = _book()
    chain = anchors(ocr, ["מבוא", "נוסף"] + text)  # the transcription has an extra opening
    assert chain and all(a[0] < b[0] and a[1] < b[1] for a, b in zip(chain, chain[1:]))
    slices = page_slices(page_of, len(text) + 2, chain, margin=2, min_anchors=1)
    assert [s.page for s in slices] == [1, 2, 3]
    s2 = slices[1]
    assert s2.start <= 16 + 2 and s2.end >= 32 + 2 - 1  # page 2 text sits at 18..33 in the shifted transcription


def test_page_direction_detects_a_book_stored_back_to_front():
    text, ocr, page_of = _book()
    assert page_direction(ocr, page_of, text, min_shared=5) == 1
    # The same pages stored in reverse order: page 3 first.
    pages = {}
    for w, p in zip(ocr, page_of):
        pages.setdefault(p, []).append(w)
    rev_ocr, rev_pages = [], []
    for new, old in enumerate(sorted(pages, reverse=True), 1):
        rev_ocr += pages[old]; rev_pages += [new] * len(pages[old])
    assert page_direction(rev_ocr, rev_pages, text, min_shared=5) == -1
    assert len(anchors(rev_ocr, text)) < len(anchors(ocr, text))  # why the reversal matters
    assert page_direction(ocr[:6], page_of[:6], text, min_shared=50) == 1  # too little evidence: order kept
