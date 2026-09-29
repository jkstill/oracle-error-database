# Querying the error data with jq

Three shapes are produced, all holding the same records:

| File | Shape | Best for |
|---|---|---|
| `json/<facility>.json` | array of records | one facility at a time |
| `oracle-errors.json` | object: facility -> array | whole set, keyed lookup |
| `oracle-errors.ndjson` | one record per line | streaming / grep prefilter / bulk load |

Record fields: `facility`, `error_number` (verbatim, may be zero-padded),
`error_code` (int), `description`, `cause`, `action`, `params`, `note`, `info`,
`remediation`. Absent text fields are the string `"NA"`. Every field is a
single-line string -- newlines in the source are collapsed to spaces, so
`info`'s fenced code blocks keep their backticks but the SQL sits on one line.

Sparse fields, worth knowing before you filter on them: `params` 4,865 records
(`ora`, `ogg`, `dia`), `note` 24 (`dia`, `ora`), `info` 13 (`ora`, `dia`),
`remediation` 66 (`ora` only).

`description`, `cause`, `action`, `params`, `note` and `info` are extracted from
the `*.msg` files. `remediation` is hand-written and lives in `remediation.json`,
keyed `"<facility>-<error_code>"`; `msg2json.py` merges it in at build time, so
regenerating never overwrites it. To add or edit remediation text, edit that file
and re-run `python3 msg2json.py`. Keys that match no error are reported as a
warning rather than silently dropped.

`error_number` padding is inconsistent across facilities (`ora` uses `"01017"`,
`rman` uses `"6059"`). **Match on `error_code` unless you need the literal.**

---

## Single error lookup

Per-facility array:

    jq '.[] | select(.error_code == 1017)' json/ora.json

Combined object — index the facility first, which avoids scanning the rest:

    jq '.ora[] | select(.error_code == 1017)' oracle-errors.json

NDJSON — `-c` keeps one record per line:

    jq -c 'select(.facility == "ora" and .error_code == 1017)' oracle-errors.ndjson

NDJSON with a grep prefilter (much faster on the 17 MB file):

    grep '"facility": *"ora"' oracle-errors.ndjson | jq -c 'select(.error_code == 1017)'

Parameterised, the way a script would call it:

    jq --arg f ora --argjson n 1017 \
       'select(.facility == $f and .error_code == $n)' oracle-errors.ndjson

## oerr-style output

    jq -r '.[] | select(.error_code == 1017)
           | "ORA-\(.error_number): \(.description)\n*Cause:  \(.cause)\n*Action: \(.action)"' \
       json/ora.json

## Search descriptions

Case-insensitive substring across everything:

    jq -c 'select(.description | test("tablespace"; "i"))' oracle-errors.ndjson

Same against the combined object — `.[]` flattens the facility arrays:

    jq -c '.[][] | select(.description | test("tablespace"; "i"))' oracle-errors.json

Search cause and action too:

    jq -c 'select([.description, .cause, .action] | join(" ") | test("ORA-00060|deadlock"; "i"))' \
       oracle-errors.ndjson

Just the identifiers:

    jq -r 'select(.description | test("snapshot too old"; "i"))
           | "\(.facility|ascii_upcase)-\(.error_number)  \(.description)"' \
       oracle-errors.ndjson

## Ranges and sets

A numeric range:

    jq -c 'select(.facility == "ora" and .error_code >= 600 and .error_code <= 700)' \
       oracle-errors.ndjson

A list of codes:

    jq -c --argjson want '[1017,1555,942,60]' \
       'select(.facility == "ora" and (.error_code | IN($want[])))' oracle-errors.ndjson

## Entries with real content

Errors that document a cause:

    jq -c 'select(.cause != "NA")' oracle-errors.ndjson

Errors that carry a parameter glossary (`ora` and `ogg` only):

    jq -r 'select(.params != "NA") | "\(.facility)-\(.error_number): \(.params)"' \
       oracle-errors.ndjson

Errors flagged internal by a `*Note`:

    jq -c 'select(.note != "NA") | {facility, error_number, note}' oracle-errors.ndjson

Errors carrying an `*Info` block -- the diagnostic queries and usage notes Oracle
attaches to a handful of errors, `ORA-00001` among them:

    jq -r 'select(.info != "NA") | "\(.facility|ascii_upcase)-\(.error_number)"' \
       oracle-errors.ndjson

    jq -r '.[] | select(.error_code == 1) | .info' json/ora.json

Everything Oracle documents for one error, in one blob:

    jq -r '.[] | select(.error_code == 1)
           | [.description, .cause, .action, .params, .info]
           | map(select(. != "NA")) | join("\n\n")' json/ora.json

## Counts

Per facility, from the combined object:

    jq 'map_values(length)' oracle-errors.json

Per facility, from NDJSON:

    jq -s 'group_by(.facility) | map({facility: .[0].facility, n: length})' \
       oracle-errors.ndjson

Facility names only:

    jq -r 'keys[]' oracle-errors.json

## Reshaping

Flatten the combined object to NDJSON (same records as the generated
`.ndjson`; jq's compact spacing differs, so the files are not byte-identical):

    jq -c '.[][]' oracle-errors.json > flat.ndjson

Build an NDJSON file for one facility:

    jq -c '.[]' json/ora.json > ora.ndjson

Lookup table keyed `facility-code`, for loading into a KV store:

    jq -s 'map({key: "\(.facility)-\(.error_code)", value: .}) | from_entries' \
       oracle-errors.ndjson > oracle-errors-keyed.json

CSV for a relational load (embedded newlines are already squashed out):

    jq -r '[.facility, .error_number, .error_code, .description,
            .cause, .action, .params, .note, .info, .remediation] | @csv' \
       oracle-errors.ndjson > oracle-errors.csv

Trim to the fields an agent needs, dropping `NA` noise. `with_entries` removes
the empty fields; do **not** use `select` inside the object constructor, as that
drops the whole record rather than the one field:

    jq -c '{facility, error_code, description, cause, action, info}
           | with_entries(select(.value != "NA"))' oracle-errors.ndjson

## Remediation

Which errors have a runbook:

    jq -r 'select(.remediation != "NA")
           | "\(.facility|ascii_upcase)-\(.error_number)  \(.description)"' \
       oracle-errors.ndjson

The runbook for one error:

    jq -r 'select(.facility == "ora" and .error_code == 257) | .remediation' \
       oracle-errors.ndjson

To split the steps onto separate lines, do *not* break on any `N)` -- that
pattern also occurs inside the SQL (`ROUND(x, 1)`, `VARCHAR2(10)`). Break only
on the next expected step number:

    jq -r 'select(.facility == "ora" and .error_code == 257) | .remediation' \
       oracle-errors.ndjson \
      | awk '{n=2; s=$0
              while (i = index(s, " " n ") ")) { s = substr(s,1,i-1) "\n" substr(s,i+1); n++ }
              print s}'

Everything an agent needs to respond to an error, in one object:

    jq -c --arg f ora --argjson n 1653 \
       'select(.facility == $f and .error_code == $n)
        | {id: "\(.facility|ascii_upcase)-\(.error_number)", description,
           cause, action, remediation}' oracle-errors.ndjson

Remediation coverage by theme -- useful for spotting gaps:

    jq -r 'select(.remediation != "NA") | .error_code' oracle-errors.ndjson \
      | sort -n | tr '\n' ' '

Errors referenced by your own code that have no runbook yet:

    grep -rhoE 'ORA-[0-9]{4,5}' <your source dir> | sed -E 's/ORA-0*//' \
      | sort -u > /tmp/seen.txt
    jq -r 'select(.facility == "ora" and .remediation != "NA") | .error_code' \
       oracle-errors.ndjson | sort -u > /tmp/have.txt
    comm -23 /tmp/seen.txt /tmp/have.txt     # comm needs plain sort, not sort -n

Validate `remediation.json` keys against the data before rebuilding:

    jq -r 'keys[]' remediation.json | sed 's/^ora-//' | sort -u > /tmp/keys.txt
    jq -r 'select(.facility == "ora") | .error_code' oracle-errors.ndjson \
      | sort -u > /tmp/codes.txt
    comm -23 /tmp/keys.txt /tmp/codes.txt    # keys matching no error; empty is good

(`msg2json.py` performs this same check on every run and warns if a key is
orphaned, so this is only needed when editing `remediation.json` by hand.)
