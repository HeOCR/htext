"""Licence bases for scans, from Commons-style licence fields."""

import pytest

from htext.linepairs.release import licence_basis


@pytest.mark.parametrize(("short", "cats", "basis"), [
    (["Public domain"], ["PD-old-70-expired"], "pd_il"),
    (["Public domain"], ["PD US not renewed"], "pd_us_only"),
    (["CC0"], ["CC-Zero"], "cc0"),  # the two lists must not run together
    (["CC BY-SA 4.0"], [], "cc_by_sa"),
    (["CC BY 4.0"], [], "cc_by"),
    ([], [], "unclear"),
    (["Public domain"], ["PD-scan"], "unclear"),
])
def test_licence_basis(short, cats, basis):
    assert licence_basis({"licence_short": short, "licence_categories": cats}) == basis
