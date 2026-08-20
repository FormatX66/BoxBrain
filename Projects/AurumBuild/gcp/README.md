# Google Cloud Build burst lane

This lane is optional `BUILD-ONLY` capacity. It verifies an exact GitHub source manifest, runs selected deterministic work in a digest-pinned alternate container, emits evidence to the build log, and never participates in mandatory promotion.

The default pool is fixed to `E2_STANDARD_2`, the build times out after 15 minutes, queued work expires after five minutes, and the GitHub submission workflow refuses new work after 2,000 measured monthly build-minutes. It creates no private pool, VM, image, artifact repository, cache bucket, or recurring resource.

`bash Projects/AurumBuild/gcp/bootstrap-gcp.sh PROJECT_ID` is plan-only. Adding `--apply` enables APIs and configures GitHub OIDC restricted to the numeric BoxBrain repository ID and `aurum/trunk-v0.01`. It creates no service-account key. Billing must already be enabled; do not apply it until that user-controlled step is approved.
