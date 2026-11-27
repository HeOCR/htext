"""The Birnbaum print-form rule on invented pointed text."""

from htext.linepairs.wikisource import print_form


def test_unambiguous_forms_are_mapped():
    label, why = print_form("כׇּל הַלְלוּ־יָהּ", "כָּל הַלְלוּיָהּ")
    assert why is None and label == "כָּל הַלְלוּיָהּ"


def test_extra_maqaf_and_spelled_name_drop_the_line():
    assert print_form("דְּבַר־אֱמֶת", "דְּבַר אֱמֶת")[1] == "print_form_maqaf"
    assert print_form("בָּרוּךְ יְיָ", "בָּרוּךְ יְהוָֹה")[1] == "print_form_name"


def test_label_digits_the_ocr_did_not_read_drop_the_line():
    from htext.linepairs.wikisource import label_of
    row = {"gt": "שנאמר על ר' יוחנן בן זכאי45 ונתיחס להלל.", "ocr": "שנאמר על ר' יוחנן בן זכאי ונתיחס להלל.",
           "anchored": True, "cer_nomarks": 0.05}
    assert label_of(row, None)[1] == "digits_extra"
