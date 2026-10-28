# CLAUDE.md

This file guides Claude Code (claude.ai/code) when working in this repository.

## What this project is

An end-to-end ML pipeline that classifies websites as **phishing or legitimate**. It uses the
UCI-style phishing dataset (`Network_Data/phisingData.csv`, ~11k rows, 30 features + target).
Every feature is already encoded as `-1`, `0` or `1` (e.g. `having_IP_Address`, `SSLfinal_State`,
`URL_Length`). The target column is `Result` (`-1` = phishing, `1` = legitimate; mapped to `0/1`
during transformation).

The code follows a modular "components + config + artifact" MLOps layout. The planned flow
(see README.md) is:

```
MongoDB → Ingestion → Validation → Transformation → Model Trainer → Model Evaluation → Model Pusher
```

**Status:** Ingestion, Validation, Transformation and Model Trainer are done. Evaluation, Pusher,
`networksecurity/pipeline/`, `networksecurity/cloud/`, `Dockerfile` and
`.github/workflows/main.yml` are empty placeholders.

## Commands

```bash
pip install -r requirements.txt     # deps (uncomment "-e ." to install the package in editable mode)
python push_data.py                 # one-time: load the CSV into MongoDB (SATISHDB.NetworkData)
python main.py                      # run the training pipeline (ingestion → validation → transformation → model trainer, ~3 min)
```

There are no tests or linters configured.

Environment: `.env` (git-ignored) must define `MONGO_DB_URL`. If MongoDB is unreachable or empty,
ingestion falls back to reading `Network_Data/phisingData.csv` directly.

## Architecture

Each pipeline stage is made of three pieces that live in separate modules:

| Piece | Location | Role |
|---|---|---|
| Constants | `networksecurity/constant/training_pipeline/__init__.py` | All names, dirs, split ratio, imputer params, DB/collection names |
| Config | `networksecurity/entity/config_entity.py` | Builds file paths for a stage from the constants |
| Artifact | `networksecurity/entity/artifact_entity.py` | Dataclass of output paths a stage hands to the next stage |
| Component | `networksecurity/components/*.py` | The stage logic; exposes `initiate_<stage>()` returning its artifact |

`main.py` wires them together: each component takes the previous stage's artifact plus its own
config. `TrainingPipelineConfig` creates a timestamped run folder, so every run writes to
`Artifacts/<MM_DD_YYYY_HH_MM_SS>/<stage>/...`.

### Stages

1. **Data Ingestion** (`data_ingestion.py`) — reads MongoDB (drops `_id`, converts `"na"` → NaN)
   or the CSV fallback, saves `feature_store/phisingData.csv`, then an 80/20 split into
   `ingested/train.csv` and `ingested/test.csv`.
2. **Data Validation** (`data_validation.py`) — checks column count against
   `data_schema/schema.yaml`, runs a KS test (`scipy.stats.ks_2samp`, p < 0.05 = drift) per column
   between train and test, writes `drift_report/report.yaml`, copies data to `validated/`.
3. **Data Transformation** (`data_transformation.py`) — splits off `Result`, maps `-1 → 0`, fits a
   `KNNImputer(n_neighbors=3)` inside an sklearn `Pipeline` on train, saves `train.npy`/`test.npy`
   (features + target as last column) and the pickled preprocessor to
   `transformed_object/preprocessing.pkl` **and** `final_model/preprocessor.pkl`.
4. **Model Trainer** (`model_trainer.py`) — `evaluate_models` grid-searches 5 classifiers (RF, DT, GB,
   LogReg, AdaBoost) and picks the best by test F1. Fails if test F1 < `MODEL_TRAINER_EXPECTED_SCORE`,
   warns if the train/test F1 gap exceeds the over/underfitting threshold. Logs metrics + model to
   MLflow (local `mlflow.db`/`mlruns/`, `serialization_format="cloudpickle"`), saves a `NetworkModel`
   (preprocessor + model) to `model_trainer/trained_model/model.pkl` and the bare model to
   `final_model/model.pkl`.

### Shared helpers

- `networksecurity/exception/exception.py` — `NetworkSecurityException(e, sys)` adds file name and
  line number. Wrap every method body in `try/except Exception as e: raise NetworkSecurityException(e, sys)`.
- `networksecurity/logging/logger.py` — importing it configures the root logger to write to
  `logs/<timestamp>.log` (relative to the current working directory). Use
  `from networksecurity.logging.logger import logging`.
- `networksecurity/utils/main_utils/utils.py` — `read_yaml_file`, `write_yaml_file`,
  `save_numpy_array_data`, `save_object` (pickle).

## Why the `constant` folder exists

`networksecurity/constant/training_pipeline/__init__.py` holds every fixed name, path and setting
in one place. Other files refer to these constants instead of typing the values again. This means:

- **Change once, apply everywhere.** Renaming the database means editing
  `DATA_INGESTION_DATABASE_NAME = "SATISHDB"` only. Without it, `"SATISHDB"` would be repeated in
  `push_data.py`, `data_ingestion.py`, etc., and missing one breaks the code.
- **No mismatches between stages.** Ingestion writes `TRAIN_FILE_NAME` ("train.csv") and Validation
  reads the same constant, so the names always match (no `"train.csv"` vs `"Train.csv"` bugs).
- **Settings in one place.** `DATA_INGESTION_TRAIN_TEST_SPLIT_RATION = 0.2`, `TARGET_COLUMN = "Result"`
  and `DATA_TRANSFORMATION_IMPUTER_PARAMS` (`n_neighbors: 3`) can be changed for experiments
  without opening component code.

How the layers fit together:

```
constant/          →  WHAT the names and values are   ("SATISHDB", 0.2, "train.csv")
      ↓
config_entity.py   →  BUILDS full paths from them     ("Artifacts/<timestamp>/data_ingestion/ingested/train.csv")
      ↓
components/        →  USES the config to do the work  (read, split, validate, transform, save)
```

Rule: never hard-code names, paths or settings in components. Add a constant (grouped under its
stage's section, prefixed with the stage name, e.g. `MODEL_TRAINER_*`) and read it through the
config class.

## Why paths use `os.path.join`

All file paths are built with `os.path.join(...)` instead of joining strings with `/` or `+`:

- **Works on any OS.** It uses `/` on Linux/Mac and `\` on Windows, so the same code runs locally,
  in Docker and in CI.
- **No missing or doubled slashes.** `"Artifacts" + "data_ingestion"` gives
  `"Artifactsdata_ingestion"`; `os.path.join("Artifacts", "data_ingestion")` gives
  `"Artifacts/data_ingestion"`.
- **Builds paths in steps**, which matches the constants → config layering:

```python
artifact_dir  = os.path.join("Artifacts", timestamp)
ingestion_dir = os.path.join(artifact_dir, DATA_INGESTION_DIR_NAME)
train_path    = os.path.join(ingestion_dir, DATA_INGESTION_INGESTED_DIR, TRAIN_FILE_NAME)
# → "Artifacts/<timestamp>/data_ingestion/ingested/train.csv"
```

Its partner `os.path.dirname(path)` gets the folder part, so components can create the folder
before saving: `os.makedirs(os.path.dirname(path), exist_ok=True)`.

Rules:
- Never start a piece with `/` (e.g. `"/ingested"`), because `os.path.join` then discards everything
  before it. Constants hold bare names like `"ingested"`.
- Prefer `os.path.join` for consistency with existing code (`pathlib` is used only once, for the CSV
  fallback in `data_ingestion.py`).

## Why `artifact_entity.py` exists

An artifact is the labelled "delivery box" a stage hands to the next stage, saying where it saved
its outputs. It's needed because every run writes into a new timestamped folder, so the next stage
cannot hard-code paths. It has to be told them.

Returning a plain tuple (`return train_path, test_path`) is fragile: swapping the order silently
feeds test data as training data, and `result[0]` says nothing about what it holds. A dataclass
gives every value a name:

```python
@dataclass
class DataIngestionArtifact:
    trained_file_path: str
    test_file_path: str

# Ingestion fills it in…
return DataIngestionArtifact(trained_file_path=cfg.training_file_path,
                             test_file_path=cfg.testing_file_path)
# …Validation reads it by name
train_file_path = self.data_ingestion_artifact.trained_file_path
```

Flow through the pipeline (`main.py`):

```
DataIngestion      ──► DataIngestionArtifact      ──► DataValidation
DataValidation     ──► DataValidationArtifact     ──► DataTransformation
DataTransformation ──► DataTransformationArtifact ──► ModelTrainer
ModelTrainer       ──► ModelTrainerArtifact       ──► Model Evaluation (next to build)
```

Each component takes exactly two inputs: the previous stage's artifact and its own config.

Config vs Artifact:

| | `config_entity.py` | `artifact_entity.py` |
|---|---|---|
| Answers | "Where **should** I save?" | "Where **did** I save?" |
| Used | Before the stage runs | After the stage runs |
| Created by | `main.py` | The component itself |
| Type | Normal class | `@dataclass` (data only) |

Rules: artifacts hold only output paths/results, with no logic. Every new stage gets its own
`<Stage>Artifact` dataclass, and its `initiate_<stage>()` returns it.

### What `@dataclass` does

`@dataclass` is a shortcut for classes that only hold data: you list the fields and Python writes
the repetitive methods. These 4 lines replace about 12 lines of hand-written `__init__`,
`__repr__` and `__eq__`:

```python
@dataclass
class DataIngestionArtifact:
    trained_file_path: str
    test_file_path: str
```

It generates:
- **`__init__`**: `DataIngestionArtifact(trained_file_path=..., test_file_path=...)`.
- **`__repr__`**: `print(artifact)` shows
  `DataIngestionArtifact(trained_file_path='Artifacts/.../train.csv', ...)` instead of
  `<... object at 0x7f3a...>`. This is why the `print(...)` calls in `main.py` are useful.
- **`__eq__`**: two artifacts with the same values are `==`.

Extras: default values (`accuracy: float = 0.0`) and `@dataclass(frozen=True)` for read-only
objects, so a later stage can't change paths it was given.

Type hints are labels only and are not checked at runtime. `DataValidationArtifact` passes `None`
into `str` fields for the invalid paths; `Optional[str]` would be the accurate hint.

Use `@dataclass` for classes that **store data** (artifacts). Use normal classes for classes
that **do work** (components like `DataIngestion`).

## Conventions for new stages

To add a stage (e.g. Model Trainer), follow the existing pattern:
1. Add `MODEL_TRAINER_*` constants to `constant/training_pipeline/__init__.py`.
2. Add a `ModelTrainerConfig(training_pipeline_config)` class in `config_entity.py`.
3. Add a `ModelTrainerArtifact` dataclass in `artifact_entity.py`.
4. Add `components/model_trainer.py` with a class taking `(previous_artifact, config)` and an
   `initiate_model_trainer()` method returning the artifact.
5. Wire it into `main.py` (and later into `networksecurity/pipeline/`).

Run scripts from the repo root — paths like `data_schema/schema.yaml`, `final_model/` and `logs/`
are relative to the working directory.

## Known issues / gotchas

- `validate_number_of_columns` compares against `len(self._schema_config)`, which is the number of
  top-level YAML keys (2), not the 31 columns under `columns:`. The result (and `error_message`) is
  then ignored, so validation never actually blocks the pipeline. `validation_status` only reflects
  drift.
- `invalid_train_file_path` / `invalid_test_file_path` are always `None`.
- `get_data_transformer_object` is written like a classmethod (`cls`) but has no decorator; it works
  as an instance method.
- `push_data.py` has a hard-coded absolute `FILE_PATH` and prints the Mongo URL and all records.
- `__pycache__/` folders are committed; `.gitignore` only covers `venv` and `.env`.
- `requirements.txt` relies on `scikit-learn` pulling in `scipy` and on `pyaml` pulling in `PyYAML`.
