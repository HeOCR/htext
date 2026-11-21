# Hebrew Wikisource historical works v1

- **Release** `wikisource-v1`, in `htext-by-sa` under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
- **Credit** Hebrew Wikisource contributors. See [NOTICE](NOTICE.md) and the rights index for attribution by revision.
- **Source** The [2026-11-01 Hebrew Wikisource dump](https://dumps.wikimedia.org/hewikisource/20261101/hewikisource-20261101-pages-articles.xml.bz2) supplies unproofread main-namespace transcriptions of *Mesillat Yesharim*, *Reshit Chokhmah* and *Sefer HaChinukh*. [Reviewed works](../works.v1.json) · [Builder](../../../docs/wikisource.md)

## Files

| File | Pages | Lines | Bytes | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| `wikisource_plain_v1.txt` | 685 | 71,452 | 3,328,490 | `f734f6484d767ff6c2f43d049923794756545f4c97349b18338df22ad3069769` |
| `wikisource_niqqud_v1.txt` | 1 | 767 | 60,993 | `057ca4d684ed874d29efded4f9a384ff01465edba8217f9497b4f5c6227d6075` |

The 685 distinct articles contribute 72,219 lines. An article can contribute to both files. The release assets include the rights index with pinned revision links and the line index. Verify the files against [SHA256SUMS](SHA256SUMS).

## Source fidelity

Text as in Wikisource revision X; print edition not collated. The rights index supplies the exact revision ID for each article. All 100 checked lines, including four pointed lines, matched their pinned Wikisource revisions and survive in this release.

## Overlap check

The release pass removed 30 plain lines and retained the baseline article and work coverage. All three works and all pointed lines survive. The independent **line-only** check on 2026-11-21 found **zero shared six-word sequences** across 16 evaluation pools on these two text files. The prior reservation graph exclusions remain in effect.
