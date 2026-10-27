"""Compare the new structured fields in bearings TOON tables against the JSON model.

Usage: python3 -I toon-parity.py <bearings.toon> <bearings.json>
"""
import csv
import io
import json
import sys

toon_path, json_path = sys.argv[1], sys.argv[2]
model = json.load(open(json_path))
lines = open(toon_path).read().splitlines()


def table(name):
    for i, line in enumerate(lines):
        if line.startswith(name + '[') and line.endswith(':'):
            keys = line[line.index('{') + 1:line.rindex('}')].split(',')
            rows = []
            for row in lines[i + 1:]:
                if not row.startswith('  '):
                    break
                vals = next(csv.reader(io.StringIO(row[2:]), escapechar='\\', doublequote=False))
                rows.append(dict(zip(keys, vals)))
            return rows
    raise SystemExit(f'no {name} table')


def scal(v):
    return 'null' if v is None else str(v)


ok = True
for section, fields in (('in_flight', ('state', 'state_source', 'wait_until', 'hold_bucket', 'hold_until')),
                        ('gates', ('hold_bucket', 'hold_until', 'blocked_by'))):
    toon_rows = {r['id']: r for r in table(section)}
    for row in model[section]:
        t = toon_rows[row['id']]
        got = {f: t[f] for f in fields}
        want = {f: scal(row.get(f)) for f in fields}
        mark = 'OK ' if got == want else 'BAD'
        ok &= got == want
        print(f'{mark} {section:9} {row["id"]:22} ' + ' '.join(f'{f}={got[f]}' for f in fields))
print('PARITY', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
