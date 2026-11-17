"""The three releases (decision 0022): licence gate, release guard and registry."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from htext.release import (
    LICENCE_RELEASE,
    RELEASES,
    S6_LABEL,
    Credit,
    LicenceRefused,
    ReleaseGuard,
    ReleaseMismatch,
    lexicon_eligible,
    release_fields,
    release_for_licence,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "releases.json"
CREDIT = Credit("Some contributors", "https://example.org")


def _entry(label: str, **overrides):
    entry = {"entry_id": label, **release_fields(source_licence=label, credit=CREDIT)}
    entry.update(overrides)
    return entry


# --- licence gate


@pytest.mark.parametrize("label", sorted(LICENCE_RELEASE))
def test_every_listed_label_maps_to_its_release(label):
    assert release_for_licence(label) == LICENCE_RELEASE[label]
    assert LICENCE_RELEASE[label] in RELEASES


def test_public_domain_cc0_and_section_6_are_cc0():
    assert {release_for_licence(label) for label in ("Public Domain", "CC0", "CC0-1.0", S6_LABEL)} == {"cc0"}


@pytest.mark.parametrize(
    "label, reason",
    [
        ("CC-BY-NC", "non_commercial"),
        ("CC BY-NC-SA 4.0", "non_commercial"),
        ("CC BY-NC-ND 4.0", "non_commercial"),
        ("Non-commercial use only", "non_commercial"),
        ("CC-BY-ND", "no_derivatives"),
        ("CC BY-ND 4.0", "no_derivatives"),
        ("unknown", "unlisted_label"),
        ("GFDL", "unlisted_label"),
        ("PD", "unlisted_label"),  # Sefaria's variant label needs a per-version check first
        ("public domain", "unlisted_label"),  # exact match only
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_nc_nd_unknown_and_unlisted_labels_are_refused(label, reason):
    with pytest.raises(LicenceRefused) as refused:
        release_for_licence(label)
    assert refused.value.reason == reason


# --- entry fields


def test_release_is_derived_from_the_licence():
    assert release_fields(source_licence="CC-BY-SA", credit=CREDIT)["htext_release"] == "by-sa"
    assert release_fields(source_licence=S6_LABEL, credit=None) == {
        "source_licence": S6_LABEL,
        "htext_release": "cc0",
        "credit": None,
        "text_quality": "transcription",
    }


@pytest.mark.parametrize("label", ["CC-BY", "CC-BY-SA"])
def test_attribution_releases_need_a_credit_line(label):
    with pytest.raises(ValueError, match="credit"):
        release_fields(source_licence=label, credit=None)
    with pytest.raises(ValueError, match="credit"):
        release_fields(source_licence=label, credit=Credit("  "))


def test_text_quality_is_checked_and_ocr_layers_never_feed_lexicons():
    with pytest.raises(ValueError):
        release_fields(source_licence="Public Domain", credit=None, text_quality="ocr")
    ocr = release_fields(source_licence=S6_LABEL, credit=None, text_quality="ocr_layer")
    assert not lexicon_eligible(ocr)
    assert lexicon_eligible(release_fields(source_licence="Public Domain", credit=None))


# --- no mixing


def test_a_cc0_build_refuses_by_and_by_sa_entries():
    guard = ReleaseGuard("cc0")
    guard.admit(_entry("Public Domain"))
    for label in ("CC-BY", "CC-BY-SA", "CC BY-SA 4.0"):
        with pytest.raises(ReleaseMismatch):
            guard.admit(_entry(label))
    with pytest.raises(ReleaseMismatch):
        guard.admit_all([_entry("CC0"), _entry("CC-BY"), _entry(S6_LABEL)])
    assert guard.summary()["source_licences"] == {"CC0": 1, "Public Domain": 1}


@pytest.mark.parametrize("release", RELEASES)
def test_each_release_admits_only_its_own_entries(release):
    guard = ReleaseGuard(release)
    for label, target in LICENCE_RELEASE.items():
        if target == release:
            guard.admit(_entry(label))
        else:
            with pytest.raises(ReleaseMismatch):
                guard.admit(_entry(label))


def test_a_stated_release_that_disagrees_with_the_licence_is_refused():
    with pytest.raises(ReleaseMismatch):
        ReleaseGuard("cc0").admit(_entry("CC-BY", htext_release="cc0"))
    with pytest.raises(ReleaseMismatch):
        ReleaseGuard("by").admit(_entry("CC-BY", credit=None))
    with pytest.raises(LicenceRefused):
        ReleaseGuard("cc0").admit({"source_licence": "CC-BY-NC", "htext_release": "cc0"})


def test_unknown_release_is_refused():
    with pytest.raises(ValueError):
        ReleaseGuard("by-nc")


# --- the registry of published corpora


def _registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_registry_covers_every_published_card():
    listed = {row["card"] for row in _registry()["corpora"]}
    cards = {str(path.relative_to(ROOT)) for path in (ROOT / "data").glob("*/*/corpus_card.json")}
    assert listed == cards


@pytest.mark.parametrize("row", _registry()["corpora"], ids=lambda row: f"{row['corpus']}-{row['version']}")
def test_registry_rows_agree_with_the_gate_and_the_card(row):
    assert release_for_licence(row["source_licence"]) == row["htext_release"]
    assert row["text_quality"] in ("transcription", "ocr_layer")
    if row["htext_release"] in ("by", "by-sa"):
        assert row["credit"] and row["credit"]["text"]
    card = json.loads((ROOT / row["card"]).read_text(encoding="utf-8"))
    assert card.get("htext_release", row["htext_release"]) == row["htext_release"]
    assert card["credit"] == row["credit"]
    # Rights indexes that carry release fields must all sit in the card's release.
    for index in (ROOT / row["card"]).parent.glob("*rights_index*.jsonl.gz"):
        for line in gzip.decompress(index.read_bytes()).decode("utf-8").splitlines():
            entry = json.loads(line)
            if "source_licence" in entry:
                assert release_for_licence(entry["source_licence"]) == row["htext_release"]
