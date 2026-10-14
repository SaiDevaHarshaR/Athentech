# Sahasra Stage 4 — Grafana configuration only

No Grafana or Prometheus installation, migration or deployment is included. The files target Stage 3's **exact metric names** and the Prometheus job `sahasra-api`.

## Files
- `provisioning/datasources/prometheus.yaml`: one Prometheus datasource, UID `sahasra-prometheus`.
- `provisioning/dashboards/providers.yaml`: filesystem dashboard loader.
- `dashboards/sahasra-dark.json` and `sahasra-light.json`: two importable dashboards with the same verified PromQL; both render in the viewer's Grafana UI theme. **Grafana does not support forcing dark vs light UI theme per dashboard JSON**, so names are logical layout variants; use Grafana user theme settings for actual appearance.
- `provisioning/alerting/rules.yaml`: target-down, HTTP 5xx ratio, P95 latency alerts.
- `tests/test_stage4_grafana.py`: offline syntax/metric/security tests.

## Paths when installing later (not now)
- Map `deployment/grafana/provisioning` to `/etc/grafana/provisioning` (read-only).
- Map `deployment/grafana/dashboards` to `/var/lib/grafana/dashboards/sahasra` (read-only).
- Grafana must share a private Docker network with a Prometheus service named `prometheus`. Otherwise edit datasource `url` to an internal reachable address.
- Prometheus Stage 3 `job_name: sahasra-api` and metric authorization token remain unchanged; Grafana queries Prometheus, **not the secured Sahasra endpoint directly**.
- For manual dashboard imports Grafana can prompt for a Prometheus datasource; default UID is `sahasra-prometheus`.

## Operational precautions
- Do not expose Grafana/Prometheus admin interfaces or `/internal/metrics` publicly. Enable authentication and HTTPS at the gateway if used externally.
- These files do not store patient names, phone numbers, UHIDs, OTP values, transcripts, institutional IDs or API secrets.
- Stage 3 **did not wire** `record_ai_provider` and `record_b2b_otp_outcome` into the currently deployed BYOK/OTP backend. Corresponding dashboard panels correctly display **No data** until these are hooked and executed. No fake values.
- Alert threshold tuning is necessary after collecting staging baselines. Rate errors when there is almost no traffic can be misleading.
- Grafana alert provisioning file uses org 1, references datasource by fixed UID and expects Grafana's default notification policy unless administrators configure routing/contact points.
- Grafana OSS schema varies across versions. Offline JSON/YAML and query consistency were tested, but no live Grafana import or rule evaluation has occurred.
- Preserve existing IIS gateway, SQL Server databases, and exact BYOK/fallback controls. No source changes or LIS writes required for Stage 4.

## Compatibility notes
Stage 4 is an **additive** package. Keep all Stage 1–3 files; do not replace `main.py` or institution-specific modules. Do not assume the prior Stage 3 Prometheus service is deployed: Stage 3 only supplied config.
