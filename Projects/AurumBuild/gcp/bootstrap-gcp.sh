#!/usr/bin/env bash
set -euo pipefail

project_id=${1:?usage: bootstrap-gcp.sh PROJECT_ID [--apply]}
mode=${2:---plan}
pool=aurum-github
provider=boxbrain-trunk
service_account=aurum-cloud-build-submit
repository_id=1311353087
branch_ref=refs/heads/aurum/trunk-v0.01

if [ "$mode" != --apply ]; then
  cat <<EOF
AURUM GCP PLAN
Project: $project_id
APIs: Cloud Build, IAM Credentials, Security Token Service
Identity: GitHub OIDC restricted to repository_id=$repository_id and ref=$branch_ref
Submitter: $service_account (Cloud Build builds editor only)
Worker: default-pool E2_STANDARD_2, 15-minute timeout, no image/artifact publication
Monthly guard: refuse at 2,000 of the currently documented 2,500 free build-minutes
No resources were changed. Re-run with --apply only after billing/API approval.
EOF
  exit 0
fi

gcloud config set project "$project_id"
gcloud services enable \
  cloudbuild.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com

project_number=$(gcloud projects describe "$project_id" --format='value(projectNumber)')
service_account_email="$service_account@$project_id.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$service_account_email" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$service_account" \
    --display-name='Aurum Cloud Build submission only'
fi
gcloud projects add-iam-policy-binding "$project_id" \
  --member="serviceAccount:$service_account_email" \
  --role=roles/cloudbuild.builds.editor \
  --condition=None >/dev/null

if ! gcloud iam workload-identity-pools describe "$pool" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$pool" \
    --location=global \
    --display-name='Aurum GitHub Actions'
fi
if ! gcloud iam workload-identity-pools providers describe "$provider" \
  --workload-identity-pool="$pool" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$provider" \
    --location=global \
    --workload-identity-pool="$pool" \
    --issuer-uri='https://token.actions.githubusercontent.com/' \
    --attribute-mapping='google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref' \
    --attribute-condition="assertion.repository_id=='$repository_id' && assertion.ref=='$branch_ref'"
fi

principal="principalSet://iam.googleapis.com/projects/$project_number/locations/global/workloadIdentityPools/$pool/attribute.repository_id/$repository_id"
gcloud iam service-accounts add-iam-policy-binding "$service_account_email" \
  --role=roles/iam.workloadIdentityUser \
  --member="$principal" >/dev/null

provider_name=$(gcloud iam workload-identity-pools providers describe "$provider" \
  --workload-identity-pool="$pool" --location=global --format='value(name)')
cat <<EOF
AURUM_GCP_BOOTSTRAP_OK
Set these GitHub repository variables (values are identifiers, not secrets):
AURUM_GCP_PROJECT_ID=$project_id
AURUM_GCP_WIF_PROVIDER=$provider_name
AURUM_GCP_SERVICE_ACCOUNT=$service_account_email
AURUM_GCP_BURST_ENABLED=true
EOF
