import argparse
import sys
from pathlib import Path

import torch

sys.path.append(str(Path(__file__).parent.parent.parent))
import lstm_adversarial_attack.attack.adv_attack_trainer as aat
import lstm_adversarial_attack.attack.attack_data_structs as ads
import lstm_adversarial_attack.attack.attack_result_data_structs as ards
import lstm_adversarial_attack.attack.attack_tuner_driver as atd
import lstm_adversarial_attack.config_paths as cfg_paths
import lstm_adversarial_attack.config_settings as cfg_settings
import lstm_adversarial_attack.data_provenance as dpr
import lstm_adversarial_attack.path_searches as ps
import lstm_adversarial_attack.resource_io as rio
from lstm_adversarial_attack.x19_mort_general_dataset import (
    X19MGeneralDatasetWithIndex,
    x19m_with_index_collate_fn,
)
import lstm_adversarial_attack.data_structures as ds
import lstm_adversarial_attack.tune_train.tuner_helpers as tuh
import lstm_adversarial_attack.tuning_db.tuning_studies_database as tsd
import lstm_adversarial_attack.preprocess.encode_decode as edc


class AttackDriver(dpr.HasDataProvenance):
    """
    Instantiates and runs an AdversarialAttackTrainer
    """

    def __init__(
        self,
        device: torch.device,
        model_hyperparameters: tuh.X19LSTMHyperParameterSettings,
        checkpoint: ds.TrainingCheckpoint,
        attack_hyperparameters: ads.AttackHyperParameterSettings,
        epochs_per_batch: int,
        max_num_samples=None,
        sample_selection_seed=None,
        attack_misclassified_samples: bool = False,
        output_dir: Path = None,
        result_file_prefix: str = "",
        save_attack_driver: bool = False,
        checkpoint_interval: int = None,
        hyperparameter_tuning_result_dir: Path = None,
    ):
        """
        :param device: device to run on
        :param checkpoint: Info saved during training classifier. Contents
        include model params.
        :param epochs_per_batch: number of attack iterations per batch
        (https://arxiv.org/abs/1802.04822). Defines a margin by which alternate
        class logit value needs to exceed original class logit value in order
        to reduce loss function.
        searching for adversarial example_data
        constructor
        :param max_num_samples: Number candidate samples to take from a dataset
        for attack. Default behavior of AdversarialAttackTrainer is to not
        attack samples misclassified by target model, so not all candidate
        samples get attacked.
        :param sample_selection_seed: random seed to use when selecting subset
        of samples from original dataset
        :param attack_misclassified_samples: whether to run attacks on samples
        that original model misclassifies
        :param output_dir: directory where attack results are saved
        :param result_file_prefix: prefix to use in result file output
        :param save_attack_driver: whether to save AttackDriver .pickle
        :param checkpoint_interval: number of batches per checkpoint
        """
        self.device = device
        self.model_hyperparameters = model_hyperparameters
        self.checkpoint = checkpoint
        self.attack_hyperparameters = attack_hyperparameters
        self.epochs_per_batch = epochs_per_batch
        self.max_num_samples = max_num_samples
        self.sample_selection_seed = sample_selection_seed
        if self.sample_selection_seed is not None:
            torch.manual_seed(self.sample_selection_seed)
        self.dataset = (
            X19MGeneralDatasetWithIndex.from_feature_finalizer_output(
                max_num_samples=max_num_samples,
                random_seed=sample_selection_seed,
            )
        )
        self.collate_fn = x19m_with_index_collate_fn
        self.attack_misclassified_samples = attack_misclassified_samples
        self.result_file_prefix = result_file_prefix
        self.save_attack_driver = save_attack_driver
        self.checkpoint_interval = checkpoint_interval
        self.output_dir = self.initialize_output_dir(output_dir=output_dir)
        self.hyperparameter_tuning_results_dir = (
            hyperparameter_tuning_result_dir
        )
        self.export(filename="attack_driver_dict.pickle")

    @property
    def provenance_info(self) -> dpr.ProvenanceInfo:
        return dpr.ProvenanceInfo(
            previous_info=(
                self.hyperparameter_tuning_results_dir / "provenance.pickle"
                if self.hyperparameter_tuning_results_dir is not None
                and (
                    self.hyperparameter_tuning_results_dir
                    / "provenance.pickle"
                ).exists()
                else None
            ),
            category_name="attack_driver",
            new_items={
                "epochs_per_batch": self.epochs_per_batch,
                "attack_hyperparameter_settings": self.attack_hyperparameters,
                "hyperparameter_tuning_result_dir": (
                    self.hyperparameter_tuning_results_dir
                ),
            },
            output_dir=self.output_dir,
        )

    @staticmethod
    def initialize_output_dir(output_dir: Path | None):
        """
        Initializes directory where results of attacked will be saved
        :param output_dir: Path of output directory. If None, a directory
        will be created
        :return: path to output dir (either same as output_dir in arg, or
        path to newly create directory)
        """
        if output_dir is None:
            output_dir = rio.create_timestamped_dir(
                parent_path=cfg_paths.FROZEN_HYPERPARAMETER_ATTACK
            )
        return output_dir

    @classmethod
    def from_attack_hyperparameter_tuning(
        cls,
        device: torch.device,
        tuning_result_dir: Path = None,
        max_num_samples: int = None,
        epochs_per_batch: int = None,
        sample_selection_seed: int = None,
        save_attack_driver: bool = True,
        checkpoint_interval: int = None,
    ):
        """
        Creates AttackDriver using output from previous hyperparameter tuning
        :param device: device to run on
        :param tuning_result_dir: directory where tuning data is saved
        :param max_num_samples: number of candidate samples for attack
        :param epochs_per_batch: num attack iterations per batch
        :param sample_selection_seed: random seed to use when selecting subset
        of samples from original dataset
        :param save_attack_driver: whether to save AttackDriver .pickle
        :param checkpoint_interval: number of batches per checkpoint
        :return:
        """
        if tuning_result_dir is None:
            tuning_result_dir = ps.latest_modified_file_with_name_condition(
                component_string="optuna_study.pickle",
                root_dir=cfg_paths.ATTACK_HYPERPARAMETER_TUNING,
            ).parent
        optuna_study = rio.ResourceImporter().import_pickle_to_object(
            path=tuning_result_dir / "optuna_study.pickle"
        )
        tuner_driver_dict = rio.ResourceImporter().import_pickle_to_object(
            path=tuning_result_dir / "attack_tuner_driver_dict.pickle"
        )
        tuner_driver = atd.AttackTunerDriver(**tuner_driver_dict)

        # attack can have different # epochs per batch than tuner if specified
        if epochs_per_batch is None:
            epochs_per_batch = tuner_driver.epochs_per_batch

        return cls(
            device=device,
            # model_path=tuner_driver.target_model_path,
            checkpoint=tuner_driver.target_model_checkpoint,
            attack_hyperparameters=ads.AttackHyperParameterSettings(
                **optuna_study.best_params
            ),
            epochs_per_batch=epochs_per_batch,
            max_num_samples=max_num_samples,
            sample_selection_seed=sample_selection_seed,
            save_attack_driver=save_attack_driver,
            checkpoint_interval=checkpoint_interval,
            hyperparameter_tuning_result_dir=tuning_result_dir,
        )

    def __call__(self) -> aat.AdversarialAttackTrainer | ards.TrainerResult:
        """
        Imports model to attack, then trains and runs attack driver
        :return: TrainerResult (dataclass with attack results)
        """
        # model = rio.ResourceImporter().import_pickle_to_object(
        #     path=self.model_path
        # )

        model = tuh.X19LSTMBuilder(settings=self.model_hyperparameters).build()
        model.load_state_dict(state_dict=self.checkpoint.state_dict)

        attack_trainer = aat.AdversarialAttackTrainer(
            device=self.device,
            model=model,
            state_dict=self.checkpoint.state_dict,
            attack_hyperparameters=self.attack_hyperparameters,
            epochs_per_batch=self.epochs_per_batch,
            dataset=self.dataset,
            collate_fn=self.collate_fn,
            attack_misclassified_samples=self.attack_misclassified_samples,
            output_dir=self.output_dir,
            checkpoint_interval=self.checkpoint_interval,
        )

        train_result = attack_trainer.train_attacker()

        train_result_output_path = rio.create_timestamped_filepath(
            parent_path=self.output_dir,
            file_extension="pickle",
            suffix=f"{self.result_file_prefix}_final_attack_result",
        )

        rio.ResourceExporter().export(
            resource=train_result, path=train_result_output_path
        )
        return train_result


def main(study_name: str) -> ards.TrainerSuccessSummary:
    """
    Runs attack on dataset
    :param study_name: name of tuning study to use for hyperparameter selection
    """
    if torch.cuda.is_available():
        cur_device = torch.device("cuda:0")
    else:
        cur_device = torch.device("cpu")

    if study_name is None:
        study_name = tsd.ATTACK_TUNING_DB.get_latest_study().study_name

    attack_hyperparameters = tsd.ATTACK_TUNING_DB.get_best_params(
        study_name=study_name
    )

    tuning_result_dir_path = (
        cfg_paths.ATTACK_HYPERPARAMETER_TUNING / study_name
    )

    model_hyperparameters = (
        edc.X19LSTMHyperParameterSettingsReader().import_struct(
            path=tuning_result_dir_path / "model_hyperparameters.json"
        )
    )

    attack_tuner_driver_summary_path = (
        ps.latest_modified_file_with_name_condition(
            component_string="attack_tuner_driver_summary_",
            root_dir=tuning_result_dir_path,
            comparison_type=ps.StringComparisonType.PREFIX,
        )
    )

    attack_tuner_driver_summary = (
        edc.AttackTunerDriverSummaryReader().import_struct(
            path=attack_tuner_driver_summary_path
        )
    )

    # TODO resume work here on delay targetmodel instantiation after modify
    #  ModelRetriever to also provide checkpt Path. (& move call to
    #  get_representative_checkpoint back to tune_attack_new.py)
    # attack_driver = AttackDriver(
    #     device=cur_device,
    #     model_hyperparameters=model_hyperparameters,
    #     checkpoint=attack_tuner_driver_summary.
    #
    # )

    # tuning_result_dir_path = (
    #     Path(tuning_result_dir) if tuning_result_dir is not None else None
    # )

    attack_driver = AttackDriver.from_attack_hyperparameter_tuning(
        device=cur_device,
        sample_selection_seed=cfg_settings.ATTACK_SAMPLE_SELECTION_SEED,
        checkpoint_interval=cfg_settings.ATTACK_CHECKPOINT_INTERVAL,
        tuning_result_dir=tuning_result_dir_path,
    )
    trainer_result = attack_driver()
    success_summary = ards.TrainerSuccessSummary(trainer_result=trainer_result)

    return success_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s",
        "--study_name",
        action="store",
        nargs="?",
        help=(
            "Name of attack tuning study to use for attack hyperparameter "
            "selection"
        ),
    )
    args_namespace = parser.parse_args()
    # args_namespace.tuning_result_dir = str(
    #     cfg_paths.ATTACK_HYPERPARAMETER_TUNING / "2023-07-01_11_03_13.591090"
    # )
    cur_success_summary = main(**args_namespace.__dict__)
