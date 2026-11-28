# p4b by-eye check, 2026-11-28 (htext, a Claude session; TRAIN images)
Sample: a seeded sample (20 dense rows per book, seed "heocr-p4b-byeye-20261128|<book>").
Method: every line read once at line scale (crop beside its label); 3 suspect lines magnified. NOT a mark-by-mark
proofread: single-mark differences can be missed, above all on long lines with small glyphs.

| book | lines | visibly pointed print | clear label error | probable |
|---|---:|---:|---:|---:|
| hatekufah20telauoft | 20 | 20 | 1 (#7: print qamats, label segol) | 1 (#16: the hataf under alef) |
| hatekufah01fris | 20 | 20 | 0 | 0 |
| hatekufah14telauoft | 20 | 20 | 0 | 0 |
| hatekufah19telauoft | 20 | 20 | 0 | 0 |
| shaarshimon00bachuoft | 20 | 20 | 0 | 0 |
| halevdeam00deamuoft | 20 | 20 | 0 | 0 |

Some crops also include parts of the neighbouring lines (tall boxes, mostly halevdeam); the label matches the middle line.

## Decision (lead, 2026-11-28)
p4b CLEARED for new TRAIN scopes, hatekufah20 included, with the card caveat (isolated PBY-vs-print marks). The limit above
stands: this check rules out gross errors, not isolated wrong marks.
