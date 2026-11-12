from app.db import Base, engine, SessionLocal
from app.models import ModelRun
from app.ml import train_model, track_training_run


def main():
    Base.metadata.create_all(engine)
    result = train_model()
    try:
        track_training_run(result)
    except Exception as exc:
        print(f"MLflow tracking unavailable; model artifact was still trained: {exc}")
    with SessionLocal() as db:
        db.merge(
            ModelRun(
                version=result["version"],
                algorithm=result["algorithm"],
                dataset_version="scenario-v1-seed-2026",
                metrics=result["metrics"],
                artifact_path=result["artifact_path"],
            )
        )
        db.commit()
    print(result)


if __name__ == "__main__":
    main()
