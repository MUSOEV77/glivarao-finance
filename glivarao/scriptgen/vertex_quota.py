"""`python -m glivarao claude-quota`: is Claude on Vertex usable yet? (run it from Termius on the VPS)

1. A tiny real Claude call (a few tokens, well under one cent): "OK" means production can run; a 429 means the
   quota is still 0.
2. The quota limits for the shared Sonnet bucket (base_model=anthropic-claude-sonnet) in your VERTEX_REGION and your
   increase requests (asked / granted / pending), read with the service account through the Cloud Quotas API.
   That needs read access once (Cloud Shell):
     gcloud projects add-iam-policy-binding PROJECT --member=serviceAccount:EMAIL --role=roles/cloudquotas.viewer
"""
from __future__ import annotations

from pathlib import Path

PREFIX = {"global": "global_online_prediction_", "us": "us_multi_region_online_prediction_",
          "eu": "eu_multi_region_online_prediction_"}
KEYS = ("requests_per_base_model", "input_tokens_per_minute_per_base_model", "output_tokens_per_minute_per_base_model")
BASE_MODEL = "anthropic-claude-sonnet"
API = "https://cloudquotas.googleapis.com/v1"


def live_test(settings) -> tuple[bool, str]:
    from .backends import WriterUnavailable, claude_client, openrouter_chat
    from .claude import ClaudeSpendLedger, usage_cost

    if settings.writer == "claude_openrouter":
        try:
            text, u = openrouter_chat(settings, "You are a test.", "Reply with the single word OK.", max_tokens=16,
                                      attempts=2)
            tin, tout = u["prompt_tokens"], u["completion_tokens"]
            usd = float(u["cost"]) if u.get("cost") is not None else (
                tin * settings.openrouter_price_in + tout * settings.openrouter_price_out) / 1e6
            ClaudeSpendLedger(Path(settings.claude_spend_ledger_path)).add(usd, tin, tout)
            return True, f"Claude {u.get('model')} via OpenRouter answered '{text.strip()[:20]}' (${usd:.5f})"
        except WriterUnavailable as exc:
            return False, str(exc)
    try:
        client, platform, model, p_in, p_out = claude_client(settings)
        msg = client.messages.create(model=model, max_tokens=256, output_config={"effort": "low"},
                                     messages=[{"role": "user", "content": "Reply with the single word OK."}])
        usd, tin, tout = usage_cost(msg.usage, p_in, p_out)
        ClaudeSpendLedger(Path(settings.claude_spend_ledger_path)).add(usd, tin, tout)
        return True, f"Claude {model} on Vertex ({settings.vertex_region}) answered: quota is working (${usd:.4f})"
    except WriterUnavailable as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "status_code", "")
        if code == 429 or "429" in str(exc):
            return False, (f"429 quota: Claude Sonnet still has no quota in region {settings.vertex_region} "
                           "(production stays on hold and retries hourly)")
        return False, f"{type(exc).__name__} {code}: {str(exc)[:300]}"


def quota_status(settings, session=None) -> list[str]:
    """Lines describing limits and increase requests; never raises (explains how to get access instead)."""
    from google.auth.transport.requests import AuthorizedSession

    from .backends import vertex_credentials

    out = []
    try:
        http = session or AuthorizedSession(vertex_credentials(settings))
    except Exception as exc:  # noqa: BLE001
        return [f"can't read quotas: {exc}"]
    proj, region = settings.vertex_project_id, settings.vertex_region
    infos, token = [], ""
    for _ in range(10):
        r = http.get(f"{API}/projects/{proj}/locations/global/services/aiplatform.googleapis.com/quotaInfos",
                     params={"pageSize": 500, **({"pageToken": token} if token else {})}, timeout=60)
        if r.status_code != 200:
            return _access_hint(r, settings)
        data = r.json()
        infos += data.get("quotaInfos", [])
        token = data.get("nextPageToken", "")
        if not token:
            break
    want = {PREFIX.get(region, PREFIX["global"]) + k: k for k in KEYS}
    out.append(f"Limits for {BASE_MODEL} in region {region}:")
    for info in infos:
        metric = info.get("metric", "").split("/")[-1]
        if metric not in want:
            continue
        value = "0 (not granted)"
        for di in info.get("dimensionsInfos", []):
            dims = di.get("dimensions", {})
            if dims.get("base_model") in (BASE_MODEL, None):
                value = di.get("details", {}).get("value", value)
                if dims.get("base_model") == BASE_MODEL:
                    break
        out.append(f"  {want[metric].split('_per_')[0].replace('_', ' '):24s} {value}")
    r = http.get(f"{API}/projects/{proj}/locations/global/quotaPreferences",
                 params={"filter": 'service="aiplatform.googleapis.com"'}, timeout=60)
    if r.status_code == 200:
        prefs = [p for p in r.json().get("quotaPreferences", []) if "BaseModel" in p.get("quotaId", "")]
        out.append("Your increase requests:" if prefs else "No increase request found (run vertex-quota.sh in Cloud Shell)")
        for p in prefs:
            cfg = p.get("quotaConfig", {})
            out.append(f"  {p['name'].split('/')[-1]:34s} asked {cfg.get('preferredValue', '?'):>8} granted "
                       f"{cfg.get('grantedValue', '0'):>8}  {'PENDING' if p.get('reconciling') else 'decided'}"
                       + (f"  ({cfg['stateDetail']})" if cfg.get("stateDetail") else ""))
    else:
        out += _access_hint(r, settings)
    return out


def _access_hint(r, settings) -> list[str]:
    import json

    email = ""
    try:
        email = json.loads(Path(settings.vertex_credentials_file).read_text()).get("client_email", "")
    except Exception:  # noqa: BLE001
        pass
    text = getattr(r, "text", "")[:300]
    if r.status_code == 403 and ("SERVICE_DISABLED" in text or "has not been used" in text):
        return ["The Cloud Quotas API is off for this project. In Cloud Shell run once:",
                f"  gcloud services enable cloudquotas.googleapis.com --project={settings.vertex_project_id}"]
    if r.status_code == 403:
        return ["The service account can't read quotas yet. In Cloud Shell run once:",
                f"  gcloud projects add-iam-policy-binding {settings.vertex_project_id} "
                f"--member=serviceAccount:{email or 'glivarao-vps@...'} --role=roles/cloudquotas.viewer"]
    return [f"can't read quotas: HTTP {r.status_code} {text}"]


__all__ = ["live_test", "quota_status"]
