"""The Birnbaum print-form rule on invented pointed text."""

from htext.linepairs.wikisource import print_form


def test_unambiguous_forms_are_mapped():
    label, why = print_form("כׇּל הַלְלוּ־יָהּ", "כָּל הַלְלוּיָהּ")
    assert why is None and label == "כָּל הַלְלוּיָהּ"


def test_extra_maqaf_and_spelled_name_drop_the_line():
    assert print_form("דְּבַר־אֱמֶת", "דְּבַר אֱמֶת")[1] == "print_form_maqaf"
    assert print_form("בָּרוּךְ יְיָ", "בָּרוּךְ יְהוָֹה")[1] == "print_form_name"
