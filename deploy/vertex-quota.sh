#!/usr/bin/env bash
# Claude Sonnet 5.5 quota on Vertex AI: show it, or request an increase. Run in Google Cloud Shell (it has gcloud
# and is already signed in as you). Nothing here touches the VPS or any key.
#
#   bash vertex-quota.sh status  PROJECT_ID            # current limits for global, us, eu + your open requests
#   bash vertex-quota.sh request PROJECT_ID [REGION]   # ask for 10 req/min, 100k input + 20k output tokens/min
#
# Sonnet 5.5 uses the shared lineage bucket base_model=anthropic-claude-sonnet (Google: "Quotas for Anthropic
# Claude models"). Its endpoints are: global, us (US multi-region), eu (EU multi-region); each is a separate bucket.
# The exact quota IDs differ by project, so they are looked up from the metric names:
#   global: global_online_prediction_{requests,input_tokens_per_minute,output_tokens_per_minute}_per_base_model
#   us/eu:  {us,eu}_multi_region_online_prediction_..._per_base_model
set -euo pipefail
MODE="${1:-status}"
PROJECT="${2:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${3:-global}"
RPM="${RPM:-10}"; IN_TPM="${IN_TPM:-100000}"; OUT_TPM="${OUT_TPM:-20000}"
BASE=anthropic-claude-sonnet
SERVICE=aiplatform.googleapis.com
[ -n "$PROJECT" ] || { echo "usage: bash vertex-quota.sh status|request PROJECT_ID [global|us|eu]"; exit 1; }
case "$REGION" in global|us|eu) ;; *) echo "REGION must be global, us or eu (Sonnet 5.5 endpoints)"; exit 1;; esac

INFO=$(mktemp)
echo "Reading Vertex AI quotas for $PROJECT (takes ~20 s)..."
gcloud quotas info list --service="$SERVICE" --project="$PROJECT" \
  --filter="metric~online_prediction AND metric~per_base_model" --format=json > "$INFO"

python3 - "$INFO" "$MODE" "$REGION" "$BASE" "$RPM" "$IN_TPM" "$OUT_TPM" > "$INFO.plan" <<'PY'
import json, sys
infos, mode, region, base = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3], sys.argv[4]
want = {"requests_per_base_model": int(sys.argv[5]), "input_tokens_per_minute_per_base_model": int(sys.argv[6]),
        "output_tokens_per_minute_per_base_model": int(sys.argv[7])}
prefix = {"global": "global_online_prediction_", "us": "us_multi_region_online_prediction_",
          "eu": "eu_multi_region_online_prediction_"}

def value_for(info, reg):
    best = None
    for di in info.get("dimensionsInfos", []):
        d = di.get("dimensions", {})
        if d.get("base_model") not in (None, base):
            continue
        if "region" in d and d["region"] not in (reg, "global" if reg == "global" else d["region"]):
            continue
        v = di.get("details", {}).get("value")
        if d.get("base_model") == base:
            return v, d
        best = best or (v, d)
    return best or ("?", {})

for reg in ("global", "us", "eu"):
    for key, n in want.items():
        metric = prefix[reg] + key
        info = next((i for i in infos if i.get("metric", "").endswith("/" + metric)), None)
        if info is None:
            if mode == "status":
                print(f"SHOW {reg:6s} {key:42s} (no such quota in this project)")
            continue
        v, d = value_for(info, reg)
        if mode == "status" or reg != region:
            print(f"SHOW {reg:6s} {key:42s} now={str(v if v not in (None, '?') else 'unknown'):>10s}  id={info['quotaId']}")
            continue
        dims = [f"base_model={base}"]
        if "region" in info.get("dimensions", []):
            dims.append(f"region={d.get('region', reg)}")
        print(f"REQ {info['quotaId']} {n} {','.join(dims)} {reg} {key} {v}")
PY

if [ "$MODE" = "status" ]; then
  sed -n 's/^SHOW //p' "$INFO.plan"
  echo; echo "Your quota requests (preferred = asked, granted = approved so far):"
  gcloud quotas preferences list --project="$PROJECT" \
    --filter="service=$SERVICE AND quotaId~PerBaseModel" \
    --format="table(name.basename(), quotaId, dimensions, quotaConfig.preferredValue:label=ASKED, quotaConfig.grantedValue:label=GRANTED, reconciling:label=PENDING, quotaConfig.stateDetail:label=DETAIL)" || true
  echo; echo "Tip: GLIVARAO can use any region that shows non-zero values: on the VPS run"
  echo "  bash /opt/glivarao/app/deploy/set-key.sh VERTEX_REGION us     (or eu, or global)"
  exit 0
fi

EMAIL=$(gcloud config get-value account 2>/dev/null)
N=0
while read -r _ QID VAL DIMS REG KEY NOW; do
  N=$((N + 1))
  echo "Requesting $KEY = $VAL on $REG (now $NOW) ..."
  PID="glivarao-sonnet-$REG-$(echo "$KEY" | cut -d_ -f1)"   # stable: glivarao-sonnet-global-requests/input/output
  gcloud quotas preferences update "$PID" --allow-missing --quiet \
    --service="$SERVICE" --project="$PROJECT" --quota-id="$QID" --preferred-value="$VAL" \
    --dimensions="$DIMS" --email="$EMAIL" \
    --justification="Small YouTube scripting workload: about 2 long scripts a day with Claude Sonnet 5.5 (few requests per minute). Billing account active." \
    --format="value(quotaConfig.preferredValue, quotaConfig.grantedValue, reconciling)"
done < <(grep '^REQ ' "$INFO.plan")
[ "$N" -gt 0 ] || { echo "No Claude Sonnet quotas found for $REGION. Run: bash vertex-quota.sh status $PROJECT"; exit 1; }
echo
echo "Sent $N requests. Google usually answers within minutes to 2 business days (email to $EMAIL)."
echo "Check:  bash vertex-quota.sh status $PROJECT"
