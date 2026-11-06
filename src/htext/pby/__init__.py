"""Project Ben-Yehuda (PBY) public-domain text intake (S15b).

The design is the ``hocrsyngen`` plan
``docs/pby_public_domain_text_intake_plan.md`` (S15a). The builder reads a local
checkout of ``projectbenyehuda/public_domain_dump`` at a pinned commit and the
pinned ``data/pby/creators.json``; it never uses the network.
"""

PBY_REPOSITORY = "projectbenyehuda/public_domain_dump"
PBY_DUMP_COMMIT = "5e4277fead7b565f32cc4b352abd3565023a77d8"
PBY_DUMP_VERSION = "2026-03"
# The dump README asks reusers who credit PBY to write "Project Ben-Yehuda
# volunteers" with a link to the site.
PBY_CREDIT = "Project Ben-Yehuda volunteers"
PBY_URL = "https://benyehuda.org"
PBY_ATTRIBUTION = f"Text from Project Ben-Yehuda ({PBY_URL}), prepared by {PBY_CREDIT}"
