import sys

import mlflow
import mlflow.sklearn
from sklearn.ensemble import (
    AdaBoostClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

from networksecurity.entity.artifact_entity import (
    ClassificationMetricArtifact,
    DataTransformationArtifact,
    ModelTrainerArtifact,
)
from networksecurity.entity.config_entity import ModelTrainerConfig
from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging
from networksecurity.utils.main_utils.utils import (
    evaluate_models,
    load_numpy_array_data,
    load_object,
    save_object,
)
from networksecurity.utils.ml_utils.metric.classification_metric import get_classification_score
from networksecurity.utils.ml_utils.model.estimator import NetworkModel


class ModelTrainer:
    def __init__(self, data_transformation_artifact: DataTransformationArtifact,
                 model_trainer_config: ModelTrainerConfig):
        try:
            self.data_transformation_artifact = data_transformation_artifact
            self.model_trainer_config = model_trainer_config
        except Exception as e:
            raise NetworkSecurityException(e, sys)

    def track_mlflow(self, model_name: str, best_model,
                     train_metric: ClassificationMetricArtifact,
                     test_metric: ClassificationMetricArtifact):
        """Log the best model and its train/test metrics as one MLflow run (stored locally by default)."""
        try:
            with mlflow.start_run():
                mlflow.set_tag("model_name", model_name)
                mlflow.log_params(best_model.get_params())
                for prefix, metric in (("train", train_metric), ("test", test_metric)):
                    mlflow.log_metric(f"{prefix}_f1_score", metric.f1_score)
                    mlflow.log_metric(f"{prefix}_precision", metric.precision_score)
                    mlflow.log_metric(f"{prefix}_recall", metric.recall_score)
                # cloudpickle: we trust our own model, and it matches how the project pickles objects.
                # (MLflow's default "skops" format rejects tree models unless their types are whitelisted.)
                mlflow.sklearn.log_model(best_model, name="model", serialization_format="cloudpickle")
        except Exception as e:
            raise NetworkSecurityException(e, sys)

    def train_model(self, x_train, y_train, x_test, y_test) -> ModelTrainerArtifact:
        try:
            models = {
                "Random Forest": RandomForestClassifier(),
                "Decision Tree": DecisionTreeClassifier(),
                "Gradient Boosting": GradientBoostingClassifier(),
                "Logistic Regression": LogisticRegression(max_iter=1000),
                "AdaBoost": AdaBoostClassifier(),
            }
            params = {
                "Decision Tree": {
                    "criterion": ["gini", "entropy", "log_loss"],
                },
                "Random Forest": {
                    "n_estimators": [8, 16, 32, 128, 256],
                },
                "Gradient Boosting": {
                    "learning_rate": [0.1, 0.01, 0.05, 0.001],
                    "subsample": [0.6, 0.7, 0.75, 0.85, 0.9],
                    "n_estimators": [8, 16, 32, 64, 128, 256],
                },
                "Logistic Regression": {},
                "AdaBoost": {
                    "learning_rate": [0.1, 0.01, 0.001],
                    "n_estimators": [8, 16, 32, 64, 128, 256],
                },
            }

            model_report: dict = evaluate_models(X_train=x_train, y_train=y_train,
                                                 X_test=x_test, y_test=y_test,
                                                 models=models, param=params)
            logging.info(f"Model report (test F1): {model_report}")

            best_model_name = max(model_report, key=model_report.get)
            best_model = models[best_model_name]
            logging.info(f"Best model: {best_model_name} (test F1 {model_report[best_model_name]:.4f})")

            train_metric = get_classification_score(y_true=y_train, y_pred=best_model.predict(x_train))
            test_metric = get_classification_score(y_true=y_test, y_pred=best_model.predict(x_test))

            # Quality gates
            if test_metric.f1_score < self.model_trainer_config.expected_score:
                raise Exception(
                    f"Best model {best_model_name} test F1 {test_metric.f1_score:.4f} is below "
                    f"expected score {self.model_trainer_config.expected_score}"
                )
            gap = abs(train_metric.f1_score - test_metric.f1_score)
            if gap > self.model_trainer_config.overfitting_underfitting_threshold:
                logging.warning(
                    f"Train/test F1 gap {gap:.4f} exceeds threshold "
                    f"{self.model_trainer_config.overfitting_underfitting_threshold}: possible over/underfitting"
                )

            self.track_mlflow(best_model_name, best_model, train_metric, test_metric)

            # Bundle preprocessor + model so prediction works on raw features
            preprocessor = load_object(file_path=self.data_transformation_artifact.transformed_object_file_path)
            network_model = NetworkModel(preprocessor=preprocessor, model=best_model)
            save_object(self.model_trainer_config.trained_model_file_path, obj=network_model)

            # Copy of the bare model next to final_model/preprocessor.pkl
            save_object(self.model_trainer_config.final_model_file_path, obj=best_model)

            model_trainer_artifact = ModelTrainerArtifact(
                trained_model_file_path=self.model_trainer_config.trained_model_file_path,
                train_metric_artifact=train_metric,
                test_metric_artifact=test_metric,
            )
            logging.info(f"Model trainer artifact: {model_trainer_artifact}")
            return model_trainer_artifact
        except Exception as e:
            raise NetworkSecurityException(e, sys)

    def initiate_model_trainer(self) -> ModelTrainerArtifact:
        try:
            train_arr = load_numpy_array_data(self.data_transformation_artifact.transformed_train_file_path)
            test_arr = load_numpy_array_data(self.data_transformation_artifact.transformed_test_file_path)

            x_train, y_train, x_test, y_test = (
                train_arr[:, :-1],
                train_arr[:, -1],
                test_arr[:, :-1],
                test_arr[:, -1],
            )
            return self.train_model(x_train, y_train, x_test, y_test)
        except Exception as e:
            raise NetworkSecurityException(e, sys)
