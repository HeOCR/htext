"""Project Ben-Yehuda (PBY) public-domain text intake (S15b).

The design is the ``hocrsyngen`` plan
``docs/pby_public_domain_text_intake_plan.md`` (S15a). The builder reads a local
checkout of ``projectbenyehuda/public_domain_dump`` at a pinned commit and the
pinned ``data/pby/creators.json``; it never uses the network.
"""

PBY_REPOSITORY = "projectbenyehuda/public_domain_dump"
PBY_DUMP_COMMIT = "5e4277fead7b565f32cc4b352abd3565023a77d8"
PBY_DUMP_VERSION = "2026-03"
PBY_ATTRIBUTION = "Text from Project Ben-Yehuda (https://benyehuda.org), prepared by Project Ben-Yehuda volunteers"
