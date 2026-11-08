# Remaining submission actions

- Private GitHub source is published; normal CI passed and the separate untrained
  run failed at the quality gate. Actual URLs/logs are in results/publication/.
- V1 Release is downloaded/hash/member/version verified. On a faster reliable uplink, complete and independently
  verify the blocked V2 upload before claiming both versions available.
- Verify full fresh-clone make up on a disposable environment once V2 is available.
  Actual make down passed on an isolated audit cluster; the working cluster and
  SeaweedFS Pod identities were preserved.
- Task 4 rolling error rate is 7.792%, exceeding 0.5%; Task 7 baseline errors
  1.058%, exceeding 1%. These are genuine model validation failures, not hidden.
  Improvements would need a separately validated candidate model and new evidence;
  no model was retrained or modified to invent a passing result.
- Student supplies the mandatory **three-page handwritten personal reflection**,
  scans it as exactly `<roll_number>.pdf`, including their name, roll number and
  actual GitHub assignment URL. An AI-generated/typeset reflection is not a substitute.
- Review the seven-section `report/report.pdf` (at most eight pages).
- Tag the final reviewed submission commit `final`, and publish that tag only when
  ready. No final tag is created automatically while mandatory evidence is missing.

## Student and archive procedure

Student-provided details: **Shreeja Chaudhary**, **230101089**. The actual scan
`230101089.pdf` has been supplied and visually reviewed on all three handwritten pages. Page 1 contains the correct name, roll number and repository URL. The unchanged scan is ZIP-only. Final ZIP integrity, hashes, manifest/commit equality and remote tag verification are saved under `submission/` after committing the source. No commits follow the final tag.

Follow docs/final-submission.md. `make submission-plan` is safe now;
`make submission-zip REVIEWED=1` is reserved for a real reviewed scan and clean,
committed source. Final outputs are ignored `submission/230101089.zip` and its hash.
The PDF does not specify ZIP format; this filename follows the student's added request.

## Verified closeout update

The receipt/review supersedes the earlier request for a missing scan. Main report: seven pages/seven task sections. Latest verified pre-closeout normal CI: https://github.com/sencoders/cloud-mini-project/actions/runs/42080057058. Failed gate: https://github.com/sencoders/cloud-mini-project/actions/runs/42030357782. V2 Release archive is still absent after the final bounded retry; V1 fulfills the PDF model Release requirement, and the V2-dependent fresh bootstrap remains a disclosed grading gap. The one-ZIP instruction places the real reflection at ZIP root. Portal upload remains the student's action.
