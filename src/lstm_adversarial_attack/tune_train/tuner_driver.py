from datetime import datetime

import optuna
import sys
import torch
from pathlib import Path

from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler
from sklearn.model_selection import StratifiedKFold
import sklearn.model_selection
from typing import Any, Callable

sys.path.append(str(Path(__file__).parent.parent.parent))
import lstm_adversarial_attack.config_paths as cfp
import lstm_adversarial_attack.config_settings as cfg_set
import lstm_adversarial_attack.preprocess.encode_decode as edc
import lstm_adversarial_attack.preprocess.encode_decode_structs as eds
import lstm_adversarial_attack.resource_io as rio
import lstm_adversarial_attack.tune_train.hyperparameter_tuner as htu
import lstm_adversarial_attack.tune_train.tuner_helpers as tuh
import lstm_adversarial_attack.x19_mort_general_dataset as xmd
import lstm_adversarial_attack.tuning_db.tuning_studies_database as tsd


def validate_existing_output(
    storage: optuna.storages.RDBStorage, study_name: str
):
    existing_study_summaries = optuna.study.get_all_study_summaries(
        storage=storage
    )
    existing_study_names = [
        item.study_name for item in existing_study_summaries
    ]

    study_in_db = study_name in existing_study_names
    local_study_output_exists = (
        cfp.HYPERPARAMETER_OUTPUT_DIR / study_name
    ).exists()

    assert study_in_db == local_study_output_exists


def has_rdb_output(
    study_name: str, storage: optuna.storages.RDBStorage
) -> bool:
    """
    Determines if output exists for study named study_name in storage.
    :param study_name: name of study
    :param storage: RDB storage where we look for study
    :return: bool indicating presence of output
    """
    existing_study_summaries = optuna.study.get_all_study_summaries(
        storage=storage
    )
    existing_study_names = [
        item.study_name for item in existing_study_summaries
    ]
    return study_name in existing_study_names


def has_local_output(study_name: str) -> bool:
    """
    Determines if local output exists for study named study_name
    :param study_name: name of study
    :return:
    """
    return (cfp.HYPERPARAMETER_OUTPUT_DIR / study_name).exists()


class TunerDriver:
    """
    Instantiates and runs a HyperparameterTuner
    """

    def __init__(
        self,
        device: torch.device,
        study_name: str = None,
        collate_fn_name: str = "x19m_collate_fn",
        # continue_tuning_dir: Path | str = None,
        tuning_ranges: tuh.X19MLSTMTuningRanges = None,
        num_folds: int = cfg_set.TUNER_NUM_FOLDS,
        num_cv_epochs: int = cfg_set.TUNER_NUM_CV_EPOCHS,
        epochs_per_fold: int = cfg_set.TUNER_EPOCHS_PER_FOLD,
        fold_class_name: str = "StratifiedKFold",
        kfold_random_seed: int = cfg_set.TUNER_KFOLD_RANDOM_SEED,
        cv_mean_metrics_of_interest: tuple[
            str, ...
        ] = cfg_set.TUNER_CV_MEAN_TENSORBOARD_METRICS,
        performance_metric: str = cfg_set.TUNER_PERFORMANCE_METRIC,
        optimization_direction_label: str = cfg_set.TUNER_OPTIMIZATION_DIRECTION,
        pruner_name: str = "MedianPruner",
        pruner_kwargs: dict[str, Any] = None,
        sampler_name: str = "TPESampler",
        sampler_kwargs: dict[str, Any] = None,
    ):
        self.device = device
        self.collate_fn = getattr(xmd, collate_fn_name)
        if study_name is None:
            timestamp = "".join(
                char for char in str(datetime.now()) if char.isdigit()
            )
            study_name = f"model_tuning_{timestamp}"
        self.study_name = study_name
        self.has_pre_existing_rdb_output = has_rdb_output(
            study_name=self.study_name, storage=tsd.TUNING_STUDIES_STORAGE
        )
        self.output_dir = cfp.HYPERPARAMETER_OUTPUT_DIR / self.study_name
        self.has_pre_existing_local_output = self.output_dir.exists()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if tuning_ranges is None:
            tuning_ranges = tuh.X19MLSTMTuningRanges()
        self.tuning_ranges = tuning_ranges
        self.num_folds = num_folds
        self.num_cv_epochs = num_cv_epochs
        self.epochs_per_fold = epochs_per_fold
        self.fold_class = getattr(sklearn.model_selection, fold_class_name)
        self.kfold_random_seed = kfold_random_seed
        self.performance_metric = performance_metric
        assert (
            optimization_direction_label == "minimize"
            or optimization_direction_label == "maximize"
        )
        self.optimization_direction_label = optimization_direction_label
        self.optimization_direction = (
            optuna.study.StudyDirection.MINIMIZE
            if optimization_direction_label == "minimize"
            else optuna.study.StudyDirection.MAXIMIZE
        )
        if pruner_kwargs is None:
            pruner_kwargs = {
                "n_startup_trials": cfg_set.TUNER_PRUNER_NUM_STARTUP_TRIALS,
                "n_warmup_steps": cfg_set.TUNER_PRUNER_NUM_WARMUP_STEPS,
            }
        self.pruner_kwargs = pruner_kwargs
        self.pruner = getattr(optuna.pruners, pruner_name)(
            **self.pruner_kwargs
        )
        self.cv_mean_metrics_of_interest = cv_mean_metrics_of_interest
        if sampler_kwargs is None:
            sampler_kwargs = {}
        self.sampler_kwargs = sampler_kwargs
        self.hyperparameter_sampler = getattr(optuna.samplers, sampler_name)(
            **self.sampler_kwargs
        )

    @property
    def summary(self) -> eds.TunerDriverSummary:
        return eds.TunerDriverSummary(
            collate_fn_name=self.collate_fn.__name__,
            study_name=self.study_name,
            # TODO should continuation check be for local, RDB, or both?
            is_continuation=self.has_pre_existing_local_output,
            cv_mean_metrics_of_interest=self.cv_mean_metrics_of_interest,
            device_name=str(self.device),
            epochs_per_fold=self.epochs_per_fold,
            fold_class_name=self.fold_class.__name__,
            output_dir=str(self.output_dir),
            sampler_name=self.hyperparameter_sampler.__class__.__name__,
            sampler_kwargs=self.sampler_kwargs,
            kfold_random_seed=self.kfold_random_seed,
            num_cv_epochs=self.num_cv_epochs,
            num_folds=self.num_folds,
            optimization_direction_label=self.optimization_direction_label,
            performance_metric=self.performance_metric,
            pruner_name=self.pruner.__class__.__name__,
            tuning_ranges=self.tuning_ranges,
        )

    def run(self, num_trials: int) -> optuna.Study:
        """
        Runs an optuna study for num_trials
        :param num_trials: number of trials to run
        :return: completed optuna study
        """
        if not self.summary.is_continuation:
            summary_output_path = rio.create_timestamped_filepath(
                parent_path=self.output_dir,
                file_extension="json",
                prefix="tuner_driver_summary_",
            )
            edc.TunerDriverSummaryWriter().export(
                obj=self.summary, path=summary_output_path
            )

        study = optuna.create_study(
            study_name=self.study_name,
            storage=tsd.TUNING_STUDIES_STORAGE,
            load_if_exists=True,
            direction=self.optimization_direction_label,
            sampler=self.hyperparameter_sampler,
            pruner=self.pruner,
        )

        tuner = htu.HyperParameterTuner(
            device=self.device,
            dataset=xmd.X19MGeneralDataset.from_feature_finalizer_output(),
            collate_fn=self.collate_fn,
            tuning_ranges=self.tuning_ranges,
            num_folds=self.num_folds,
            num_cv_epochs=self.num_cv_epochs,
            epochs_per_fold=self.epochs_per_fold,
            fold_class=self.fold_class,
            output_dir=self.output_dir,
            kfold_random_seed=self.kfold_random_seed,
            cv_mean_metrics_of_interest=self.cv_mean_metrics_of_interest,
            performance_metric=self.performance_metric,
            optimization_direction=self.optimization_direction,
            pruner=self.pruner,
            hyperparameter_sampler=self.hyperparameter_sampler,
            study=study,
        )
        # completed_study = self.tuner.tune(num_trials=num_trials)
        completed_study = tuner.tune(num_trials=num_trials)
        return completed_study

    def __call__(self, num_trials: int) -> optuna.Study:
        completed_study = self.run(num_trials=num_trials)
        return completed_study
