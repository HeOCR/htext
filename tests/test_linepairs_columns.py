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
