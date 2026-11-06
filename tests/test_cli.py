import json

from htext.cli import main


def test_cli_build_without_fit_check(mini_dump, mini_creators, mini_leakage, tmp_path, capsys):
    profile = tmp_path / "profile.txt"
    profile.write_text("".join("א" * length + "\n" for length in range(12, 48)), encoding="utf-8")
    output = tmp_path / "out"
    code = main(
        [
            "pby", "build",
            "--dump", str(mini_dump),
            "--output", str(output),
            "--creators", str(mini_creators),
            "--leakage", str(mini_leakage),
            "--length-profile", str(profile),
            "--no-fit-check",
            "--max-lines-per-work", "0",
        ]
    )
    assert code == 0
    assert "pby_lines_il_plain_v1.txt:" in capsys.readouterr().out
    card = json.loads((output / "corpus_card.json").read_text(encoding="utf-8"))
    assert card["parameters"]["max_lines_per_work"] is None
    assert card["inputs"]["fit_check"] == {"ran": False}
    assert card["inputs"]["length_profile_source"] == str(profile)
