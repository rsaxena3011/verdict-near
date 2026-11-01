"""Admin tool: edit a lock in the federated store (the live-edit demo beat).

The VERDICT stores are CSV filestores behind Zetaris. Editing a lock means
rewriting the locks CSV and re-running ingestion tagging for the findings
that referenced it: a draft finding only keeps its `contradicts` tag if
its quoted line still conflicts with the new lock text. After an edit the
driver must be restarted so its catalog cache re-reads the files (the
runner script does that); the next VERDICT run then reads its own prior
decision from memory and shows the verdict responding to the new lock.

Usage:
  python3 edit_lock.py flip     (LK-001: closing time 22:00 -> 23:30)
  python3 edit_lock.py restore  (put the backed-up seed CSVs back)
"""
import csv
import io
import os
import sys

VOL = "/var/lib/docker/volumes/zetaris_customer-data/_data/shared/verdict"
BACKUP = os.path.expanduser("~/verdict/seed_backup")


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f)), ["finding_id", "claim", "quote", "document_id", "locator", "contradicts", "unanswerable"]


def write_csv(path, rows, fields):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: (r.get(k) or "") for k in fields})
    with open(path, "w", newline="") as f:  # in place: keeps file ownership
        f.write(buf.getvalue())


def flip():
    locks_path = os.path.join(VOL, "locks", "findings.csv")
    drafts_path = os.path.join(VOL, "drafts", "findings.csv")
    locks, fields = read_csv(locks_path)
    for r in locks:
        if r["finding_id"] == "LK-001":
            r["claim"] = "The cafe's closing time is 23:30."
            r["quote"] = "The cafe closes at 23:30 sharp, every day."
    write_csv(locks_path, locks, fields)
    drafts, fields = read_csv(drafts_path)
    for r in drafts:
        if r["finding_id"] == "DR-002":
            # Re-ingestion against the new lock: a 23:15 departure no
            # longer conflicts with a 23:30 close, so the tag is removed.
            r["claim"] = "Draft says the last customer left at 23:15, before the 23:30 close."
            r["contradicts"] = ""
    write_csv(drafts_path, drafts, fields)
    print("flip applied: LK-001 now closes 23:30; DR-002 re-tagged (no contradiction)")


def restore():
    for name, sub in [("locks", "locks"), ("drafts", "drafts"), ("reviews", "reviews")]:
        src = os.path.join(BACKUP, f"{name}_findings.csv")
        dst = os.path.join(VOL, sub, "findings.csv")
        with open(src) as f:
            data = f.read()
        with open(dst, "w") as f:
            f.write(data)
    print("restore applied: seed CSVs back in place")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("flip", "restore"):
        print(__doc__)
        sys.exit(2)
    flip() if sys.argv[1] == "flip" else restore()
