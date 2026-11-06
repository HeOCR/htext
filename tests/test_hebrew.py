from htext.hebrew import has_medial_final_form, has_other_marks, pointing_density, strip_marks


def test_pointing_density_counts_letters_with_s10b_marks():
    # Fully pointed text still has bare letters: here the final mem, and the
    # lamed whose holam sits on the vav.
    assert pointing_density("שָׁלוֹם") == 0.5
    assert pointing_density("בְּרָכָה") == 0.75
    assert pointing_density("שלום") == 0.0
    # One of four letters pointed (dagesh counts as a mark).
    assert pointing_density("סבּות") == 0.25
    assert pointing_density("123") == 0.0


def test_strip_marks_keeps_maqaf_and_punctuation():
    assert strip_marks("עֲלִילַת־הַדָּם.") == "עלילת־הדם."
    assert strip_marks("ארגׇמן") == "ארגמן"


def test_other_marks_are_cantillation_meteg_rafe_and_paseq():
    assert has_other_marks("הַמַּיִם֙")
    assert has_other_marks("בֽית")
    assert has_other_marks("אפֿסי")
    assert has_other_marks("א ׀ ב")
    assert not has_other_marks("שָׁלוֹם")


def test_medial_final_form():
    assert has_medial_final_form("םאם")
    assert not has_medial_final_form("שלום עולם")
