#!/usr/bin/env python3
"""Convert Oracle *.msg error message files to JSON and/or NDJSON.

Outputs (under --outdir, default the script's directory):
  json/<facility>.json           one array per facility
  oracle-errors.json             object keyed by facility
  oracle-errors.ndjson           one error record per line
  ora-internal-variants.ndjson   ORA-00600/07445 first-argument classification

Record shape:
  facility, error_number (verbatim), error_code (int), description,
  cause, action, params, note, info, remediation   -- "NA" when absent

Everything but `remediation` is extracted from the *.msg files. `remediation`
is hand-written and lives in remediation.json, keyed "<facility>-<error_code>",
so regenerating never overwrites it.

ORA-00600 and ORA-07445 carry a first argument that identifies a defect rather
than data. Those are classified in ora-internal-variants.json, keyed
"ora-<code>:<lowercased argument>", and emitted as their own table -- they are
not error codes and are deliberately not merged into the error records.
"""

import argparse
import json
import os
import re
import sys

# "00001, 00000, "text"" -- tolerant of the odd spacing/tabs seen across files
ENTRY_RE = re.compile(r'^[ \t]*(\d+)[ \t]*,[ \t]*\d+[ \t]*,[ \t]*"')
# "// *Cause:", "//*Action:", "// *ACTION:" ...
DIRECTIVE_RE = re.compile(r'^[ \t]*//[ \t]*\*[ \t]*([A-Za-z]+)[ \t]*:[ \t]?(.*)$')
# GoldenGate's parameter dialect: "// *{0}: errorCode (String)"
OGG_PARAM_RE = re.compile(r'^[ \t]*//[ \t]*\*[ \t]*(\{\d+\})[ \t]*:[ \t]?(.*)$')
COMMENT_RE = re.compile(r'^[ \t]*//[ \t]?(.*)$')

WANTED = {'cause', 'action', 'params', 'note', 'info'}

# ocius.msg is byte-identical to oraus.msg; it only exists so OCI-generated
# errors resolve. Skipping it avoids duplicating ~27k records.
SKIP_FILES = {'ocius.msg'}

REMEDIATION_FILE = 'remediation.json'
VARIANTS_FILE = 'ora-internal-variants.json'


def read_quoted(lines, i, start):
    """Read a double-quoted string beginning at lines[i][start], which may span
    lines. Returns (text, index_of_line_after)."""
    parts = []
    buf = []
    pos = start + 1
    while True:
        line = lines[i]
        while pos < len(line):
            ch = line[pos]
            if ch == '\\' and pos + 1 < len(line):
                nxt = line[pos + 1]
                # \n and \t are formatting in the original message; the rest
                # (\", \\, \%, \@ ...) just escape a literal character.
                buf.append(' ' if nxt in 'nt' else nxt)
                pos += 2
                continue
            if ch == '"':
                parts.append(''.join(buf))
                return ' '.join(p.strip() for p in parts if p.strip()), i + 1
            buf.append(ch)
            pos += 1
        parts.append(''.join(buf))
        buf = []
        # A few source messages leave the quote unterminated (e.g. ORA-31973).
        # Only continue onto the next line if it can actually be message text.
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if nxt is None or nxt.lstrip().startswith('/') or ENTRY_RE.match(nxt):
            return ' '.join(p.strip() for p in parts if p.strip()), i + 1
        i += 1
        pos = 0


def squash(text):
    return re.sub(r'\s+', ' ', text).strip()


def parse(path, facility):
    with open(path, encoding='utf-8', errors='replace') as fh:
        lines = fh.read().splitlines()

    errors = []
    i = 0
    while i < len(lines):
        m = ENTRY_RE.match(lines[i])
        if not m:
            i += 1
            continue
        number = m.group(1)
        description, i = read_quoted(lines, i, m.end() - 1)

        fields = {}
        current = None
        while i < len(lines):
            line = lines[i]
            if ENTRY_RE.match(line):
                break
            p = OGG_PARAM_RE.match(line)
            if p:
                current = 'params'
                fields.setdefault(current, []).append(
                    '%s: %s' % (p.group(1), p.group(2)))
                i += 1
                continue
            d = DIRECTIVE_RE.match(line)
            if d:
                key = d.group(1).lower()
                current = key if key in WANTED else None
                if current:
                    fields.setdefault(current, []).append(d.group(2))
                i += 1
                continue
            c = COMMENT_RE.match(line)
            if c:
                if current:
                    fields[current].append(c.group(1))
                i += 1
                continue
            break

        record = {
            'facility': facility,
            'error_number': number,
            'error_code': int(number),
            'description': squash(description),
        }
        for key in ('cause', 'action', 'params', 'note', 'info'):
            record[key] = squash(' '.join(fields.get(key, []))) or 'NA'
        record['remediation'] = 'NA'
        errors.append(record)
    return errors


def load_sidecar(path):
    """Hand-written JSON kept alongside the *.msg files. Absent is not an error."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def check_keys(keys, known, label):
    """Warn about hand-written keys that resolve to no error. Never fatal."""
    orphans = sorted(set(keys) - known)
    if orphans:
        print('WARNING: %d %s match no error: %s'
              % (len(orphans), label, ', '.join(orphans)), file=sys.stderr)
    return orphans


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--format', choices=('json', 'ndjson', 'both'),
                    default='both', help='output format (default: both)')
    ap.add_argument('--srcdir', default=here, help='directory holding *.msg')
    ap.add_argument('--outdir', default=here, help='where to write output')
    ap.add_argument('--include-oci', action='store_true',
                    help='also emit ocius.msg (a duplicate of oraus.msg)')
    ap.add_argument('--remediation', default=None,
                    help='remediation JSON (default: %s beside the *.msg files)'
                         % REMEDIATION_FILE)
    ap.add_argument('--variants', default=None,
                    help='ORA-00600/07445 argument JSON (default: %s beside the '
                         '*.msg files)' % VARIANTS_FILE)
    args = ap.parse_args()

    skip = set() if args.include_oci else SKIP_FILES
    os.makedirs(args.outdir, exist_ok=True)
    rem_path = args.remediation or os.path.join(args.srcdir, REMEDIATION_FILE)
    remediation = load_sidecar(rem_path)
    var_path = args.variants or os.path.join(args.srcdir, VARIANTS_FILE)
    variants = load_sidecar(var_path)

    combined = {}
    for name in sorted(os.listdir(args.srcdir)):
        if not name.endswith('.msg') or name in skip:
            continue
        base = name[:-4]
        facility = base[:-2] if base.endswith('us') else base
        errors = parse(os.path.join(args.srcdir, name), facility)
        applied = 0
        for record in errors:
            text = remediation.get('%s-%d' % (facility, record['error_code']))
            if text:
                record['remediation'] = text
                applied += 1
        combined[facility] = errors
        print('%-14s -> %-8s (%d errors%s)'
              % (name, facility, len(errors),
                 ', %d remediated' % applied if applied else ''),
              file=sys.stderr)

    if args.format in ('json', 'both'):
        perdir = os.path.join(args.outdir, 'json')
        os.makedirs(perdir, exist_ok=True)
        for facility, errors in combined.items():
            with open(os.path.join(perdir, facility + '.json'), 'w') as fh:
                json.dump(errors, fh, indent=2)
                fh.write('\n')
        path = os.path.join(args.outdir, 'oracle-errors.json')
        with open(path, 'w') as fh:
            json.dump(combined, fh, indent=2)
            fh.write('\n')
        print('wrote %s and %s/' % (path, perdir), file=sys.stderr)

    if args.format in ('ndjson', 'both'):
        path = os.path.join(args.outdir, 'oracle-errors.ndjson')
        with open(path, 'w') as fh:
            for errors in combined.values():
                for record in errors:
                    fh.write(json.dumps(record) + '\n')
        print('wrote %s' % path, file=sys.stderr)

        if variants:
            path = os.path.join(args.outdir, 'ora-internal-variants.ndjson')
            with open(path, 'w') as fh:
                for key in sorted(variants):
                    record = dict(variants[key], key=key)
                    fh.write(json.dumps(record) + '\n')
            print('wrote %s (%d variants)' % (path, len(variants)),
                  file=sys.stderr)

    total = sum(len(v) for v in combined.values())
    done = sum(1 for v in combined.values() for e in v
               if e['remediation'] != 'NA')
    print('%d facilities, %d errors, %d with remediation (from %s)'
          % (len(combined), total, done,
             rem_path if remediation else 'none found'), file=sys.stderr)

    known = {'%s-%d' % (e['facility'], e['error_code'])
             for v in combined.values() for e in v}
    check_keys(remediation, known, 'remediation keys')
    # A variant's own error must exist, and so must everything it points at.
    check_keys(('ora-%s' % v.get('error_code') for v in variants.values()),
               known, 'variant error_code values')
    check_keys((rel for v in variants.values() for rel in v.get('related', ())),
               known, 'variant related entries')


if __name__ == '__main__':
    main()
