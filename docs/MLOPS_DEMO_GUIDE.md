# TeleGuard AI MLOps demonstration

This guide runs the local synthetic-data lifecycle: baseline → feature drift → PSI report → real retraining → common-set evaluation → administrator decision → optional rollback. It never uses subscriber data or changes real-world services.

## Start the application

From PowerShell at the repository root:

```powershell
Copy-Item .env.example .env # only for a fresh local setup; keep the file private
# Edit .env and set unique TG_SECRET_KEY, POSTGRES_PASSWORD, TG_ADMIN_USERNAME, and TG_ADMIN_PASSWORD values.
docker compose up --build -d
docker compose exec api python -m app.bootstrap
```

For a database that already has an administrator, skip bootstrap. Open <http://localhost:5173> and sign in with the configured administrator credentials. The API health check is <http://localhost:8000/api/health>; MLflow is internal to Compose.

## Run the demonstration

1. Open **MLOps lifecycle** in the left navigation. The top card shows the active champion and describes the promotion gates.
2. Select **Run Complete MLOps Demo**. This initializes the baseline snapshot if absent, generates a seeded drift dataset, calculates PSI, trains a real challenger through the training pipeline, logs its MLflow run/artifacts, evaluates both models on the same chronological holdout, and stops before a human decision.
3. Review **Versioned datasets**. The baseline is `baseline-v1-seed-2026`; the drift batch shows its seed and the deliberately changed input fields. Fraud labels are retained from the generator; this is feature drift, not manufactured label drift.
4. Review the drift report. PSI ≥ 0.20 is marked as drift. The report shows reference/current counts and dataset versions. Its interpretation explicitly says this does not establish concept drift or performance degradation.
5. Review the challenger run, metrics, confusion matrix, and gate result. Comparison uses threshold 0.30 to prioritize recall for the synthetic fraud exercise; training-run metrics retain their own recorded 0.50 threshold. The comparison requires PR-AUC no more than 0.02 lower, recall no more than 0.03 lower, and false-positive rate no more than 0.03 higher than the champion, all on the same holdout.
6. If the gates pass, an administrator can select **Approve and promote**. The API updates the active model pointer and serving model only after approval. If a gate fails, use **Reject challenger**; the champion stays active. ML Engineer users can run the experiment but cannot approve, reject, or roll back.
7. After a successful promotion, use **Rollback to this approved model** on an older approved version to restore it. The application records the decision and loads that version for inference. Verify the **ACTIVE** version at the top of the page.
8. Review the persisted lifecycle and audit rows at the bottom of the page or in **Administration → Audit history** (administrator/auditor access).

You can run the individual **Simulate Data Drift**, **Detect Drift**, and **Start Retraining + Compare** controls when presenting one stage at a time. The one-click control runs those same backend operations and intentionally pauses for the administrator's decision.

## Reset and repeat

Select **Reset demo data** and confirm. It removes drift snapshots and demo drift/comparison/retraining/rejection records only. It preserves the baseline dataset, model artifacts, registered model runs, active selection, PostgreSQL volume, and MLflow volumes. Run the demo again to create a new versioned drift batch. For a clean baseline champion after testing a promotion, roll back to the approved baseline first.

## Troubleshooting

- **Login fails:** check the local `.env` administrator values. Bootstrap creates only the first admin and must not be rerun when one already exists.
- **API or MLflow not ready:** inspect `docker compose ps` and `docker compose logs api mlflow db`; wait for health checks before signing in.
- **Baseline missing:** use the one-click demo or administrator initialization, which snapshots the fixed generator baseline.
- **Drift not detected:** inspect per-feature PSI. Dataset seeds are reproducible, but only features crossing PSI 0.20 are reported as drifted.
- **Promotion is disabled/fails:** compare gate values. Reject the challenger if a gate fails; approval is intentionally blocked. Do not represent drift alone as model degradation.
- **Tracking unavailable:** check API-to-MLflow health and `MLFLOW_TRACKING_URI`. A training artifact can exist even if tracking failed; the page/API exposes `tracking_error` and it must not be presented as a successful MLflow run.
- **Rollback unavailable:** only a registered and previously approved model can be selected.

All metrics are from synthetic data and are not real-world performance estimates.
