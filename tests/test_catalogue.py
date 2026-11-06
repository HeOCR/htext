from htext.pby.catalogue import read_catalogue


def test_catalogue_parsing(mini_dump):
    works = {work.work_id: work for work in read_catalogue(mini_dump / "pseudocatalogue.csv")}
    assert len(works) == 8
    assert works[1].genre == "prose" and works[1].authors[0].qid == "Q1"
    assert works[3].translators[0].qid == "Q3" and works[3].original_language == "de"
    # Q0 is the catalogue's placeholder for "no Wikidata item".
    assert works[5].authors[0].qid is None
    assert works[2].source_edition == 'ורשה: הוצאה, תרע"ב'
    assert works[1].stem == "p1/m1"


def test_misaligned_uris_leave_every_creator_unresolved(tmp_path):
    path = tmp_path / "c.csv"
    path.write_text(
        "ID,path,title,authors,translators,author_uris,translator_uris,original_language,genre,source_edition\n"
        "9,/p9/m9,t,a; b,,https://wikidata.org/wiki/Q5,,,Translation missing: he.prose,\n",
        encoding="utf-8",
    )
    (work,) = read_catalogue(path)
    assert work.uri_misaligned
    assert [creator.qid for creator in work.authors] == [None, None]
