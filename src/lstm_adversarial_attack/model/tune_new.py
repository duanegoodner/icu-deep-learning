import sys
from pathlib import Path

import optuna

sys.path.append(str(Path(__file__).parent.parent.parent))
import lstm_adversarial_attack.gpu_helpers as gh
import lstm_adversarial_attack.model.model_data_structs as mds
import lstm_adversarial_attack.model.model_tuner_driver as td
import lstm_adversarial_attack.path_searches as ps
import lstm_adversarial_attack.session_id_generator as sig
from lstm_adversarial_attack.config import CONFIG_READER


def main(preprocess_id: str = None) -> optuna.Study:
    """
    Runs a new optuna study consisting of multiple trials to find
    optimized hyperparameters for use when generating a model with a
    X19LSTMBuilder and training it with a StandardModelTrainer. Results will be
    saved in a newly created director under
    data/model/hyperparameter_tuning/. If overall study is killed early,
    data from completed trials is still saved.
    :return: an optuna.Study object with results of completed trials.
    """
    cur_device = gh.get_device()

    # We are running new tuning, so need new model_tuning_id
    model_tuning_id = sig.generate_session_id()

    print(
        f"Starting new model hyperparameter tuning session {model_tuning_id}"
    )

    # If no preprocess_id provided, use ID of latest preprocess run
    if preprocess_id is None:
        preprocess_output_root = Path(
            CONFIG_READER.read_path("preprocess.output_root")
        )
        preprocess_id = ps.get_latest_sequential_child_dirname(
            root_dir=preprocess_output_root
        )

    tuner_driver = td.ModelTunerDriver(
        device=cur_device,
        settings=mds.ModelTunerDriverSettings.from_config(),
        paths=mds.ModelTunerDriverPaths.from_config(),
        preprocess_id=preprocess_id,
        model_tuning_id=model_tuning_id,
    )

    study = tuner_driver(
        num_trials=CONFIG_READER.get_config_value(
            "model.tuner_driver.num_trials"
        )
    )

    return study


if __name__ == "__main__":
    completed_study = main()
