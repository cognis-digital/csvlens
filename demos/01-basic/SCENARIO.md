# Demo 01 — Profile and clean a messy sales export

`sales.csv` is a small but realistic export with the warts you see in the
wild: a duplicate order row (1006), a fully empty row, padded whitespace
(` West `), missing `units`, and string nulls (`NA`).

## Profile the file

```
python -m csvlens profile demos/01-basic/sales.csv
python -m csvlens --format json profile demos/01-basic/sales.csv
```

You get per-column inferred types (`order_id`→int, `date`→date,
`unit_price`→float), null counts, distinct estimates, and numeric min/max/mean.
Note that `region` shows extra distinct values because ` West ` is treated raw —
which is exactly why you clean before analysis.

## Clean it

```
python -m csvlens --format json clean demos/01-basic/sales.csv -o clean.csv --fill-null "UNKNOWN"
```

This trims whitespace (so ` West ` collapses into `West`), drops the duplicate
1006 row, removes the all-empty row, and fills remaining null cells with
`UNKNOWN`. The JSON report tells you exactly how many rows and cells changed:

```json
{
  "rows_in": 11,
  "rows_out": 9,
  "duplicates_removed": 1,
  "empty_rows_removed": 1,
  "cells_filled": 6
}
```

## Peek and project

```
python -m csvlens head demos/01-basic/sales.csv -n 3
python -m csvlens select demos/01-basic/sales.csv -c region,units
```

## Exit codes

`0` success, `1` runtime error, `2` file not found, `3` unknown column — so
`csvlens` drops cleanly into a CI / data-pipeline gate.
