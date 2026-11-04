# Remaining submission actions

- Configure the real GitHub remote and authentication. No push has been performed.
- After explicit authorization, push source and publish both verified model archives
  plus checksums on one GitHub Release. No weights belong in Git.
- Run CI against that actual Release and the deliberate untrained-model workflow;
  inspect jobs and insert the actual failed-quality-gate run URL into Task 6 report.
- Verify fresh-clone make up and actual destructive make down on a separate
  disposable environment. The working cluster was deliberately preserved.
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
