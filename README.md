# Oracle Error Database

A machine-readable copy of Oracle's error message catalog (the data behind
`oerr`), with hand-written remediation runbooks for commonly seen errors. It is
built for agent lookup: every record is flat, every field is a single-line
string, and absent fields are the literal `"NA"` rather than missing.

- 26 facilities (`ora`, `rman`, `ogg`, `dia`, `kup`, ...), 45,906 errors.
- 71 errors with a remediation runbook (69 `ora`, 2 `rman`).
- 8 ORA-00600 first-argument variants, classified in a separate table.

The source `*.msg` files are from Oracle 26ai.

## Files

| File | Contents |
|---|---|
| `oracle-errors.ndjson` | All errors, one record per line. Best for streaming and bulk load. |
| `oracle-errors.json` | All errors, as an object keyed by facility. |
| `json/<facility>.json` | One array of records per facility. |
| `ora-internal-variants.ndjson` | ORA-00600 / ORA-07445 first-argument classifications. |
| `remediation.json` | Hand-written runbooks, keyed `"<facility>-<error_code>"`. Source of truth. |
| `ora-internal-variants.json` | Hand-written variant classifications, keyed `"ora-<code>:<lowercased argument>"`. Source of truth. |
| `msg2json.py` | Generator: parses `msg/*.msg` and merges in the two hand-written files. |
| `JQ-EXAMPLES.md` | jq queries for every file shape. |
| `CREATE-OERR-JSON.md` | Original requirements for the conversion. |
| `ADDITIONAL-ERRORS-FOR-REMEDIATION.md` | Errors selected for runbooks. |

Everything except `remediation.json`, `ora-internal-variants.json` and
`msg2json.py` is generated output.

## Record format

```json
{"facility": "ora", "error_number": "01017", "error_code": 1017,
 "description": "invalid credential or not authorized; logon denied",
 "cause": "...", "action": "...", "params": "NA", "note": "NA",
 "info": "NA", "remediation": "1) ... 2) ..."}
```

- `error_number` is verbatim from the source, and its zero padding differs by
  facility (`ora` uses `"01017"`, `rman` uses `"6059"`). Match on the integer
  `error_code` instead.
- `description`, `cause`, `action`, `params`, `note` and `info` are extracted
  from the `*.msg` files. `remediation` comes from `remediation.json`.
- Remediation text is numbered steps (`1) ... 2) ...`) on one line, with SQL in
  backticks.

### ORA-00600 and ORA-07445 variants

The first argument of an internal error (`ORA-00600: ... [KGHFRE3]`) names a
defect, not an error code, and does not appear in the `*.msg` files. Those are
kept in `ora-internal-variants.ndjson`, with fields `key`, `error_code`,
`argument`, `subsystem`, `confidence`, `note`, `related` and `remediation`.
The base ORA-00600 runbook holds the common workflow; a variant holds what is
specific to that argument. See the ORA-00600 section of `JQ-EXAMPLES.md` for
resolving an alert log line.

## Querying

```bash
# One error
jq -c 'select(.facility == "ora" and .error_code == 1017)' oracle-errors.ndjson

# All errors that have a runbook
jq -r 'select(.remediation != "NA") | "\(.facility|ascii_upcase)-\(.error_number)  \(.description)"' \
   oracle-errors.ndjson
```

`JQ-EXAMPLES.md` has many more examples.

## Regenerating

Requires Python 3 (standard library only). The `*.msg` files and
`facility.lis` are not committed (see `.gitignore`); copy them into `msg/` from
an Oracle home first (the `mesg` directories, for example
`$ORACLE_HOME/rdbms/mesg`).

```bash
python3 msg2json.py --srcdir msg \
   --remediation remediation.json \
   --variants ora-internal-variants.json
```

Pass `--remediation` and `--variants` explicitly. By default the script looks
for both files beside the `*.msg` files (`msg/`), and if it does not find them
it builds without remediation, saying only "from none found" in the summary.

Other options: `--format json|ndjson|both` (default `both`), `--outdir`
(default: the script's directory), `--include-oci` (also emit `ocius.msg`,
which duplicates `oraus.msg` and is skipped by default).

The script warns, without failing, about remediation keys or variant
references that match no error.

## Adding a runbook

1. Add an entry to `remediation.json` keyed `"<facility>-<error_code>"`, for
   example `"ora-1017"` (no zero padding).
2. Regenerate with the command above.
3. Check the summary line for the new remediation count and for orphan-key
   warnings.

New ORA-00600 / ORA-07445 arguments go in `ora-internal-variants.json` the
same way.
