"""Two-column Hebrew reading order."""

from htext.linepairs.wikisource import order_columns


def test_right_column_first_then_left_within_bands():
    head = ((0, 0, 1000, 40), ["כותרת"])
    r1, r2 = ((520, 60, 1000, 90), ["ימין1"]), ((520, 100, 1000, 130), ["ימין2"])
    l1, l2 = ((0, 60, 480, 90), ["שמאל1"]), ((0, 100, 480, 130), ["שמאל2"])
    mid = ((0, 150, 1000, 180), ["רוחב מלא"])
    r3, l3 = ((520, 200, 1000, 230), ["ימין3"]), ((0, 200, 480, 230), ["שמאל3"])
    got = [ws[0] for _, ws in order_columns([l1, r2, head, l2, r1, mid, l3, r3])]
    assert got == ["כותרת", "ימין1", "ימין2", "שמאל1", "שמאל2", "רוחב מלא", "ימין3", "שמאל3"]


def test_single_column_keeps_top_to_bottom():
    a, b = ((0, 0, 900, 30), ["א"]), ((0, 40, 900, 70), ["ב"])
    assert [ws[0] for _, ws in order_columns([b, a])] == ["א", "ב"]


def _ln(x0, y0, x1, y1, w):
    return ((x0, y0, x1, y1), [w])


def test_four_columns_with_an_ad_across_two_columns():
    from htext.linepairs.wikisource import order_columns_n
    head = _ln(0, 0, 1000, 30, "כותרת")
    cols = {1: (760, 1000), 2: (510, 740), 3: (260, 490), 4: (0, 240)}  # 1 is the rightmost
    lines = [head]
    for c, (a, b) in cols.items():
        rows = 5 if c in (1, 2) else 3  # columns 3-4 end above the ad
        lines += [_ln(a, 50 + 30 * r, b, 70 + 30 * r, f"ט{c}ש{r}") for r in range(rows)]
    ad = [_ln(0, 160, 490, 180, "מודעה1"), _ln(0, 190, 490, 210, "מודעה2")]
    got = [ws[0] for _, ws in order_columns_n(lines + ad)]
    want = ["כותרת"] + [f"ט{c}ש{r}" for c in (1, 2) for r in range(5)] + [f"ט{c}ש{r}" for c in (3, 4) for r in range(3)] + ["מודעה1", "מודעה2"]
    assert got == want


def test_rtl2_stays_byte_identical_and_rtln_agrees_on_two_columns():
    from htext.linepairs.wikisource import order_columns, order_columns_n
    page = [_ln(520, 60, 1000, 90, "ימין1"), _ln(0, 60, 480, 90, "שמאל1"), _ln(520, 100, 1000, 130, "ימין2"),
            _ln(0, 100, 480, 130, "שמאל2"), _ln(0, 0, 1000, 40, "כותרת")]
    two = [ws[0] for _, ws in order_columns(page)]
    assert two == ["כותרת", "ימין1", "ימין2", "שמאל1", "שמאל2"]
    assert [ws[0] for _, ws in order_columns_n(page)] == two
