# Task 1 measured results

All 3,000 source IDs are accounted for exactly once across two shards.

| Category | Count |
|---|---:|
| input | 3000 |
| a_invalid_json | 2 |
| b_wrong_keys | 2 |
| c_invalid_intent | 526 |
| d_invalid_slot | 202 |
| duplicates | 43 |
| kept | 2225 |

SHA-256: `1865c9ddc2a723247e96336c0ef966cd3b669aa904ae03d29f77ef4fe92b03e5`.

Two independent cleaning runs produced the same checksum.
See results/full/ for raw shards, logs, ID accounting and concurrency evidence.
No Task 2 training was started.

The workers overlapped for at least 2,173 seconds (36 minutes 13 seconds), as
measured from container intervals for different shard indices. Retried Pods and
original failure logs are preserved. All 2,349 checkpoints present before recovery
are byte-identical in the final raw shards. Two malformed replies were retained
unchanged for rejection; no teacher labels were repaired or substituted.

SeaweedFS's initial 768 MiB limit caused an OOM restart. The final manifest uses
2 GiB maximum memory and a 1 GiB Go memory target, and aggregate shard writes are
batched while each per-ID checkpoint remains immediate. All 3,041 bucket objects
were exported and restored with matching SHA-256 hashes into a fresh persistent
directory; the original directory was retained. Full cleaning after migration
produced the same checksum. See results/storage-migration.json and results/recovery/.

All 39 tests passed, including real S3 put/read/overwrite/delete checks. The
single-node cluster demonstrates local orchestration, not multi-machine fault
tolerance. Teacher quality remains limited: structurally rejected labels were
removed automatically, and retained labels have not been manually corrected.

A final restart of restored SeaweedFS preserved all output: full cleaning and checksum
verification passed again. The final Pod is Ready with zero restarts and no startup
volume-integrity errors. No remaining execution blockers were observed.
