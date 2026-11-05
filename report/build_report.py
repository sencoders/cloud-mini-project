"""Typeset seven task sections from preserved results; never invent remote evidence."""
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
publication_path = ROOT / 'results/publication/outcome.json'
publication = json.loads(publication_path.read_text()) if publication_path.exists() else {}
styles = getSampleStyleSheet()
styles['BodyText'].fontSize = 10
styles['BodyText'].leading = 13
styles['BodyText'].spaceAfter = 8
story = []


def text(value):
    escaped = escape(value)
    def link(match):
        value = match.group(0)
        url = value.rstrip('.,;)')
        return '<link href="' + url + '" color="#174f9c">' + url + '</link>' + value[len(url):]
    story.append(Paragraph(re.sub(r'https?://[^\s<>]+', link, escaped), styles['BodyText']))


def title(value):
    if story:
        story.append(PageBreak())
    story.append(Paragraph(escape(value), styles['Title']))
    story.append(Spacer(1, 4 * mm))


def table(rows, widths):
    wrapped = [[Paragraph(escape(str(c)), styles['BodyText']) for c in row] for row in rows]
    element = Table(wrapped, colWidths=widths, repeatRows=1, hAlign='LEFT')
    element.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('GRID', (0, 0), (-1, -1), .4, colors.grey),
        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5)]))
    story.append(element)
    story.append(Spacer(1, 3 * mm))


title('Task 1 — Object storage and parallel teacher labelling')
text('Shreeja Chaudhary | Roll number: 230101089 | Repository: https://github.com/sencoders/cloud-mini-project')
text('CS3081 Mini Project. This report separates measured local results from estimates and pending remote submission evidence. Source, manifests, commands and detailed reports are in the repository; results/ preserves genuine successes and failures.')
text('Architecture: a single-node k3d cluster hosts SeaweedFS S3 in data, two deterministic teacher Jobs in pipeline, and the inference app in app. One native macOS Ollama phi3.5 server serves both teacher workers. Credentials are local ignored files and Kubernetes Secrets; weights are excluded from Git.')
text('The authoritative prompt permits exactly eight intents and four JSON keys. Workers use temperature=0 and seed=42, partition by SHARD_INDEX/SHARD_COUNT, and retain unmodified teacher_raw strings. Per-ID checkpoints, retries and verified aggregate writes provide restart-safe progress without silently replacing labels.')
table([['Measured accounting', 'Records'], ['Input, all IDs accounted exactly once', 3000], ['Invalid JSON / wrong keys', '2 / 2'], ['Invalid intent / invalid slot', '526 / 202'], ['Duplicate commands removed', 43], ['Cleaned records retained', 2225]], [330, 160])
text('Cleaned data: s3://datasets/v1/train.jsonl. SHA-256: 1865c9ddc2a723247e96336c0ef966cd3b669aa904ae03d29f77ef4fe92b03e5. Two independent cleaning runs matched. The workers overlapped for at least 2,173 seconds; 2,349 pre-recovery checkpoints remained byte-identical.')
text('Observed limitation: the initial 768 MiB SeaweedFS limit caused an OOM restart. The final storage manifest uses 2 GiB and a 1 GiB Go memory target. This is laptop-local storage, not multi-machine durability. Improve with replicated/versioned storage and rejection-bias monitoring.')
text('Evidence: results/full/, results/storage.json, report/task1-results.md; original inputs and instructor tools are preserved.')

title('Task 2 — CPU student training and evaluation')
text('The exact EleutherAI/pythia-70m base revision a39f36b100fe8a5377810d56c3f4789b9c53ac42 was trained using CPU-only PyTorch 2.8.0 and Transformers 4.57.2. Training/config.yaml records the authoritative seed, optimizer, sequence length, batch size, epochs and dependency versions. No MPS/GPU, paid API or task-specific pretrained adapter was used.')
text('The downloaded cleaned dataset SHA-256 was verified before selecting the first 1,500 records in ID order. Training uses Command: <command> followed by JSON: <actual teacher response>. Prompt and padding tokens are masked from loss. Validation records are never training examples. This is sequence-level distillation from generated text. Logit-based distillation instead matches soft token distributions; the required Ollama generation setup does not expose the full teacher logits needed here. Teacher and student vocabularies also differ.')
text('Read-only authenticity audit verifies V1: 1,125 CPU optimizer steps (375 per epoch), 103,533 supervised tokens, 145.259 s training loop / 147.99 s whole command. V2: 375 additional updates, 34,511 supervised tokens, 48.472 s loop / 50.98 s command. Sequence lengths are 28–66 with no truncation. V1 loss falls 1.5463 to 0.6813 to 0.36435; V2 is 0.31977. After float32 normalization, 70,426,401 parameters differ base→V1 and 70,426,233 differ V1→V2. Manifests, CPU reloads and saved raw prediction replay pass. Evidence: results/final-audit/ and training/loss.csv; no retraining was performed.')
table([['All 100 validation records (%)', 'JSON', 'Intent', 'Date', 'Time', 'Place', 'Full'], ['Teacher phi3.5', 83, 74, 64, 64, 76, 44], ['Untrained Pythia', 0, 0, 0, 0, 0, 0], ['Student V1', 100, 80, 66, 70, 77, 26]], [190, 48, 50, 48, 48, 48, 48])
text('Raw completions and unchanged score.py reports are preserved. The scorer checks JSON shape but not the permitted-intent enum: strict runtime validation accepts 99/100 V1 validation completions. No invalid prediction is replaced by a gold frame.')
text('Both versions, tokenizer, config, metadata and SHA-256 are in s3://models/v1/ and s3://models/v2/. Local release archives each have nine verified members and match committed models/v*/release.sha256. ' + ('Both archives are remotely verified at ' + publication['release_url'] if publication.get('release_verified') else ('V1 is published and independently checksum-verified; V2 Release archive upload is blocked by network timeouts at ' + publication['release_url'] if publication.get('release_published') else 'GitHub Release publication is pending; no remote publication is claimed.')))
text('Limitation: 26% full-frame accuracy and occasional invalid model outputs remain. More representative clean data and constrained decoding are proposed future experiments, not claimed improvements. See report/task2-results.md and results/task2/evaluation/.')

title('Task 3 — CPU inference service')
text('FastAPI listens on port 8000. POST /parse accepts {text: ...}; success returns exactly intent, date, time and place. X-Model-Version identifies MODEL_VERSION, and X-Served-By identifies the actual Pod hostname. /healthz is process liveness; /readyz stays 503 until model and tokenizer finish loading.')
text('Startup reads MODEL_URI, MODEL_VERSION, S3_ENDPOINT, MAX_NEW_TOKENS and FAULT_INJECT. It downloads and verifies SeaweedFS artifacts using only explicitly supplied credentials, wired through Kubernetes Secrets. The shared student/runtime.py performs CPU greedy generation with bounded input/output tokens and proper EOS handling, consistent with evaluation.')
text('Outputs are checked against the supplied schema. Invalid model completions return exactly HTTP 500 {"error":"invalid_model_output"}. FAULT_INJECT=1 reliably exercises that branch. No prediction repair or ground-truth fallback occurs.')
table([['Real Docker constraint/test', 'Measured result'], ['Limits', '1 CPU; 1 GiB memory'], ['Sequential requests', '50 / 50 HTTP 200'], ['Cgroup peak memory', '845,602,816 bytes (806.43 MiB)'], ['OOM behavior', 'No OOM event'], ['Docker CLI image disk size', '1.33 GB, below 2 GB'], ['Fault injection', 'HTTP 500, exact required error JSON']], [245, 245])
text('Pinned dependencies and CPU-only PyTorch are installed in the Docker image. No model weights are embedded. Image size fields differ by Docker representation; CLI disk size is reported explicitly rather than substituting compressed content size.')
text('Evidence: results/task3/, report/task3-results.md, saved command logs and cgroup measurements. The initial failed measurement harness output is retained alongside the corrected genuine run. Limitation: the 50-request smoke workload is narrower than the full Locust command distribution; its success does not establish zero model errors under load.')

title('Task 4 — Kubernetes, rollout and recovery')
text('The app namespace contains Deployment, Service, Traefik Ingress and HPA. Initially two replicas use readiness/liveness/startup probes with explicit requests and limits. Loading Pods have no ready Service endpoints. HPA is min=1, max=2, target CPU=70%; actual idle/load/idle scaling demonstrated 1→2→1.')
table([['Standard load run', 'Requests / failures', 'Failure %', 'p95 ms'], ['Two-replica baseline', '378 / 4', '1.058', 2000], ['V1→V2→rollback V1', '308 / 24', '7.792', 4500], ['Delete Pod / recover', '320 / 3', '0.938', 2600], ['HPA run', '356 / 3', '0.843', 2300]], [185, 135, 85, 85])
text('Rollout and undo completed under load and verified V2 then V1 headers. Verification waits for asynchronous readiness and matching headers; a model-validation HTTP 500 remains a failure, even when its version header is correct. The ≤0.5% rolling-failure criterion is NOT met. Earlier interrupted rolling evidence remains intact.')
text('After deleting one Pod, two Ready replicas returned automatically in 6.863 seconds. The 0.938% recovery failure rate meets the ≤2% criterion. Exactly two Ready baseline replicas served 188 and 186 successful responses (50.27% / 49.73%), both above 30%.')
text('Three measured cold-start run medians: 5.0, 5.0 and 4.0 seconds; overall median 5.0 seconds. All six individual Pod times have median 4.5 seconds. Corresponding startup logs show authenticated model downloads. These successful experiments were reused, not rerun.')
text('KUBECONFIG=$PWD/.local/kubeconfig addresses the existing API on 127.0.0.1:6550; port 8080 is the app Ingress. This resolved discovery errors without deleting the cluster or storage. Final local verification found one Ready V1 replica managed by the active HPA.')
text('Evidence: results/task4/, report/task4-results.md. All recorded failures are retained HTTP 500 model validation errors. Limitation: one physical laptop/node cannot demonstrate cross-machine fault tolerance. A separately validated candidate model and multiple physical nodes are proposed improvements.')

title('Task 5 — VLSM and stateless public-subnet NACL')
text('Allocate largest to smallest, contiguously from 10.20.0.0/16. For H hosts choose the smallest host-bit count h with 2^h−2 ≥ H, then prefix=32−h. App: h=10, /22; public: h=8, /24; data: h=7, /25; management: h=5, /27.')
table([['Subnet / CIDR', 'Usable range', 'Broadcast', 'Usable'], ['app 10.20.0.0/22', '10.20.0.1–10.20.3.254', '10.20.3.255', 1022], ['public 10.20.4.0/24', '10.20.4.1–10.20.4.254', '10.20.4.255', 254], ['data 10.20.5.0/25', '10.20.5.1–10.20.5.126', '10.20.5.127', 126], ['management 10.20.5.128/27', '10.20.5.129–10.20.5.158', '10.20.5.159', 30]], [140, 175, 105, 70])
text('Total allocated addresses: 1,024+256+128+32=1,440. Remaining: 65,536−1,440=64,096; first unallocated address is 10.20.5.160.')
text('Inbound numbered first-match rules: 100 deny all protocols from abusive 198.51.100.0/24; 200 allow TCP 80 anywhere; 210 allow TCP 443 anywhere; 220 allow TCP 22 only from management /27; 230 allow TCP destination ports 1024–65535 only from app /22. Outbound: 100 allow TCP 8000 to app /22; 200 allow TCP 1024–65535 to clients anywhere. All unmatched packets are implicitly denied.')
text('A stateless NACL remembers no established connection: inbound app replies and outbound client replies require separate rules. The abusive deny must have a smaller number than overlapping web allows, or first-match evaluation would admit that traffic. Port 8000 lies within the ephemeral range; the simulator cannot infer connection state or distinguish a reply from another packet with identical fields.')
text('Measured: the unchanged instructor simulator passed all 6/6 sample packets. Twenty-five focused tests cover allowed/denied web and SSH, abusive CIDR, app replies, ephemeral boundaries, protocols, smallest prefixes and contiguous allocation. Hidden instructor packets have not been run. Evidence: network/subnets.md, network/nacl.json, results/task5/.')

title('Task 6 — Reproducibility, tests and CI/CD')
text('Ordered GitHub Actions: lint → unit tests → actual GitHub Release download and CPU model evaluation → score.py --min-validity 95 → Gitleaks. The secret scan runs even after earlier failure. Release archives and every model/tokenizer member must match committed hashes; there is no cached-weight fallback. A separate deliberate-bad-model workflow evaluates the real untrained pinned Pythia after verifying the downloaded Release.')
text('Local measured verification: 154 tests passed, one optional S3 integration test skipped. Ruff 0.14.4 critical correctness checks pass. Tests exercise network decisions, cost arithmetic, strict artifact integrity/path traversal, preservation of an existing cluster, exact teardown and safe submission ZIP packaging.')
text('make up genuinely verified the existing storage and app without restarting SeaweedFS or changing the HPA replica policy. The fresh-clone path downloads both released models, creates storage, builds/imports images, restores verified models to S3 and deploys the app. It uses at most three documented setup commands after system prerequisites and Release configuration.')
text('Fresh-clone deployment is blocked by the absent V2 Release archive and is NOT end-to-end verified. Real make down was tested with the explicit disposable CLUSTER_NAME=cs3081-teardown-audit: created in 15.852 s and deleted in 0.850 s; original cluster names and SeaweedFS Pod UIDs were preserved. Default working-cluster deletion was deliberately not executed.')
text('Both actual local archives passed archive and nine-member verification. The unchanged scorer accepted genuine preserved V1 predictions at 100% validity (exit 0) and rejected untrained predictions at 0% (exit 1). The new evaluator also ran all 100 V1 examples from the actual local archive in 12.441 seconds; all raw outputs matched Task 2. This proves local evaluation and gating only, not a remote workflow run.')
text('Gitleaks 8.24.3 initially reported six public Docker signing-fingerprint matches. Original diagnostics are retained; a narrowly scoped exception for that exact public GPG fingerprint preserves all default rules. Configured history and current-source scans each reported zero findings; scope and outputs are recorded under results/task6/. AI_USE.md describes assistance and verification.')
if publication.get('passing_ci_url') and publication.get('bad_model_ci_url'):
    text('Verified normal CI: ' + publication['passing_ci_url'] + '. Verified deliberate untrained-model failure at the unchanged 95% quality gate: ' + publication['bad_model_ci_url'] + '. Raw predictions, scores, job logs and GitHub status responses are in results/publication/. The initial Release-download failure is retained; it is not the bad-model demonstration.')
else:
    text('Private source repository: https://github.com/sencoders/cloud-mini-project. Initial CI failed at Release download: release not found, after an interrupted upload. Initial run: https://github.com/sencoders/cloud-mini-project/actions/runs/41866415146. ' + ('Recovery normal CI passed all five stages, including the unchanged 95% gate: ' + publication['passing_ci_url'] + '. The separate bad-model gate demonstration remains in progress.' if publication.get('passing_ci_url') else 'Recovery normal CI and the separate bad-model gate demonstration remain unverified.') + ' Genuine status responses, predictions and logs are in results/publication/.')
text('Submission also requires the student’s own three-page handwritten reflection, scanned as exactly <roll_number>.pdf with name, roll number and actual GitHub URL. This report does not impersonate that reflection. Create/publish the final tag only after the submission is reviewed. See report/submission-checklist.md.')

title('Task 7 — Performance, cost, SLO and review')
text('Measured standard baseline: four users, spawn rate four, two minutes through Traefik. p50=1,100 ms; p95=2,000 ms; throughput=3.331957779810104 req/s; failures=4/378=1.058201%. All failures are model-output HTTP 500. CSV snapshot has 377 requests, final console 378; both originals are preserved. Latency/rate use CSV, failure budget uses final counts.')
text('Per-Pod kubectl top samples (39 each): jnzfg CPU 4–998m, memory 305–430 MiB; wdqlr CPU 6–998m, memory 305–413 MiB. These are sampled working-set values, not continuous peaks. Cold-start medians 5,5,4 s give 5 s overall. Raw Locust CSVs and time series remain results/task4/load-balancing/ and results/loadtest*.')
text('Estimated INR cost using exactly data/rate_card.json and replica limits: each replica=(1 vCPU×3.50)+(1 GiB×0.45)=3.95/hour; two replicas=7.90/hour. Requests/hour=3.331957779810104×3,600=11,995.0480073163744. Cost/1,000=(7.90/11,995.0480073163744)×1,000=0.65860512 INR. Assumptions: sustained observed attempt rate, two app replicas for an hour, includes HTTP 500 attempts; excludes storage/control-plane/teacher. No real cloud charge occurred.')
text('SLO: 99% HTTP 200 over one complete standard two-minute run. Fractional error allowance=378×0.01=3.78; integer budget=floor(3.78)=3 failures. Four consumed 133.33% of the whole-request budget, exceeding it by one; success=98.941799%. SLO and local ≤1% error criterion are NOT met; p95≤5,000 ms is met. Assessor-hardware performance remains unknown.')
table([['Concern', 'Measured evidence', 'Limitation', 'Proposed improvement'], ['Data/storage', '2,225 / 3,000 kept', '775 discarded; local storage', 'Audit bias; replicate storage'], ['Model quality', '80% intent; 26% full', 'Slots/enum failures', 'Validate constrained decoding'], ['Latency/throughput', 'p95 2,000 ms; 3.332/s', 'CPU-bound generation', 'Profile and test batching'], ['Resources', '998m CPU; 430 MiB', 'Sampled maxima only', 'Continuous telemetry'], ['Reliability', '6.863 s recovery; 7.792% rolling errors', 'Single physical failure domain', 'Model gate; multiple nodes'], ['Security/cost', '0 known-key findings (Task 4); estimate INR 0.6586/1,000', 'Narrow scan; hypothetical prices', 'Enforce CI scan; least privilege']], [83, 145, 128, 134])
text('Evidence/calculations: report/task7-results.md, results/task7/summary.json and preserved Task 4 logs. No extra load test was needed. Improvements are proposals, not benchmarked changes.')


def footer(canvas, doc):
    canvas.setFont('Helvetica', 8)
    canvas.drawString(18 * mm, 12 * mm, 'CS3081 | measured evidence; verified publication status in Task 6')
    canvas.drawRightString(192 * mm, 12 * mm, str(doc.page))


if __name__ == '__main__':
    SimpleDocTemplate(str(ROOT / 'report/report.pdf'), pagesize=(210 * mm, 297 * mm),
        rightMargin=18 * mm, leftMargin=18 * mm, topMargin=15 * mm,
        bottomMargin=20 * mm).build(story, onFirstPage=footer, onLaterPages=footer)
