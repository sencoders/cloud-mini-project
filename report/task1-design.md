# Task 1 architecture and sharding

The single k3d node hosts SeaweedFS in `data` and two teacher worker Jobs in
`pipeline`. Each worker connects to the same native macOS Ollama server and to
SeaweedFS through its S3 API. The original pool is in the `datasets` bucket; the
`models` bucket is reserved for later tasks. No student training is performed.

For zero-based physical line number n, worker i processes the record exactly when
n modulo SHARD_COUNT equals i. SHARD_COUNT is 2, and the two distinct Jobs use
SHARD_INDEX 0 and 1. Each receives 1,500 records. Every source line belongs to one
and only one remainder class, so the partitions are exhaustive and disjoint.
Repeated command text under different IDs is labelled independently. Input IDs
are checked for uniqueness before labelling.

Workers store the unmodified teacher response string in per-ID S3 checkpoints
and publish separate raw shard objects. Retries use the same prompt/settings;
restarts verify a run fingerprint and recover existing checkpoints. The pipeline
claims one durable output record per ID, rather than exactly-once remote model
execution. A crash before checkpoint persistence can repeat an inference call.

Before cleaning, each shard's IDs and source texts must match its expected
partition with no gaps or repeats. Cleaning assigns the first applicable rejection
reason in PDF order, then removes duplicate command texts among valid records,
keeping the smallest ID. It sorts retained records by ID, preserves teacher_raw,
and verifies the uploaded dataset against its SHA-256 checksum. Final measured
counts are generated in `task1-results.md` only after the complete run succeeds.

The cluster is a local single-machine demonstration. Its persistent volume
survives Pod restarts, but deleting the k3d node destroys that local storage.
