import pytest

from htext.pby.catalogue import Creator, Work
from htext.pby.rights import Creators, hebrew_years, israel_status, rights_record, source_edition_year, us_status


def _creators(manual=()):
    return Creators(
        {
            "schema": "pby_creators.v1",
            "creators": [
                {"qid": "Q1", "death_year": 1900, "death_year_precision": "day", "wikidata_revision": 7},
                {"qid": "Q2", "death_year": 1955, "death_year_precision": "century", "wikidata_revision": 8},
                {"qid": "Q3", "death_year": 1956, "death_year_precision": "day", "wikidata_revision": 9},
                {"qid": "Q4", "death_year": None, "death_year_precision": None, "wikidata_revision": 10},
            ],
            "manual": list(manual),
        }
    )


@pytest.mark.parametrize(
    "note, years",
    [
        ('ווארשא, תרנ"ג', [1893]),
        ("ירושלים: דקל, תר\"ף", [1920]),
        ("ה'תש\"ח", [1948]),
        ('תשל”ח-תשמ"ה', [1978, 1985]),
        ('ת"א: יזרעאל', []),  # Tel Aviv, not 5401
        ('ת"ש', [1940]),
        ("תרבות ושירה", []),
    ],
)
def test_hebrew_years(note, years):
    assert hebrew_years(note) == years


def test_source_edition_year_takes_the_latest_year():
    assert source_edition_year('תל אביב: דביר, תשי"ט 1959', max_year=2026) == 1959
    assert source_edition_year("1880; second edition 1925", max_year=2026) == 1925
    assert source_edition_year("עמוד 3000", max_year=2026) is None
    assert source_edition_year(None, max_year=2026) is None


def _rows(*years):
    return [{"death_year": year} for year in years]


def test_israel_status_rules():
    assert israel_status(_rows(1900, 1955), ["a", "b"], as_of=2026) == (True, "all_creators_died_by:1955")
    assert israel_status(_rows(1900, 1956), ["a", "b"], as_of=2026) == (False, "creator_in_term")
    assert israel_status(_rows(1900, None), ["a", "b"], as_of=2026) == (False, "creator_death_year_unknown")
    assert israel_status(_rows(None), ["אלמוני/ת"], as_of=2026) == (False, "anonymous_unresolved")
    # The term moves with as_of.
    assert israel_status(_rows(1956), ["a"], as_of=2027) == (True, "all_creators_died_by:1956")


def test_us_status_rules():
    assert us_status(first_publication_year=None, edition_year=1930, creators=_rows(1900), as_of=2026) == (True, "published_before:1931")
    assert us_status(first_publication_year=None, edition_year=1931, creators=_rows(1900), as_of=2026) == ("unknown", "unknown")
    assert us_status(first_publication_year=1935, edition_year=1959, creators=_rows(1900), as_of=2026) == ("unknown", "uraa_candidate")
    assert us_status(first_publication_year=1935, edition_year=None, creators=_rows(1950), as_of=2026) == (False, "published_in_term")


def _work(authors, translators=(), edition=None):
    return Work(1, "/p1/m1", "t", "prose", tuple(authors), tuple(translators), "de" if translators else None, edition)


def test_translation_needs_author_and_translator_out_of_term():
    creators = _creators()
    record = rights_record(_work([Creator("a", "Q1")], [Creator("t", "Q3")]), creators, as_of=2026)
    assert (record["pd_israel"], record["pd_israel_basis"]) == (False, "creator_in_term")
    record = rights_record(_work([Creator("a", "Q1")], [Creator("t", "Q1")]), creators, as_of=2026)
    assert record["pd_israel"] is True


def test_rights_record_sources_and_flags():
    record = rights_record(_work([Creator("a", "Q2")], edition="1925"), _creators(), as_of=2026)
    assert record["authors"][0]["death_year_source"] == "wikidata:Q2@8 (precision century; latest year used)"
    assert record["pd_us"] is True and record["pd_us_basis"] == "published_before:1931"
    assert record["pby_public_domain"] is True and record["first_publication_year"] is None
    assert record["as_of"] == 2026


def test_missing_qid_and_manual_rows():
    assert rights_record(_work([Creator("x", None)]), _creators(), as_of=2026)["pd_israel_basis"] == "creator_death_year_unknown"
    assert rights_record(_work([Creator("y", "Q4")]), _creators(), as_of=2026)["pd_israel_basis"] == "creator_death_year_unknown"
    manual = [{"name": "x", "death_year": 1890, "source": "a cited biography"}]
    record = rights_record(_work([Creator("x", None)]), _creators(manual), as_of=2026)
    assert record["pd_israel"] is True
    assert record["authors"][0]["death_year_source"] == "manual:a cited biography"


def test_manual_rows_need_a_source():
    with pytest.raises(ValueError):
        _creators([{"name": "x", "death_year": 1890}])
