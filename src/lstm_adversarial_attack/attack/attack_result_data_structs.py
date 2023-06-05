import numpy as np
import torch
from torch.utils.data import Dataset
from dataclasses import dataclass
from typing import Callable
import lstm_adversarial_attack.resource_io as rio
from lstm_adversarial_attack.config_paths import ATTACK_OUTPUT_DIR
from lstm_adversarial_attack.dataset_with_index import DatasetWithIndex


@dataclass
class EpochSuccesses:
    epoch_num: int
    batch_indices: torch.tensor
    losses: torch.tensor
    perturbations: torch.tensor


def has_no_entry(loss_vals: torch.tensor, *args, **kwargs) -> torch.tensor:
    return loss_vals == float("inf")


def is_greater_than_new_val(
    loss_vals: torch.tensor, new_loss_vals: torch.tensor
) -> torch.tensor:
    return loss_vals > new_loss_vals.to("cpu")


class RecordedBatchExamples:
    def __init__(
        self,
        batch_size_actual: int,
        max_seq_length: int,
        input_size: int,
        comparison_funct: Callable[..., torch.tensor],
    ):
        self.epochs = torch.empty(batch_size_actual, dtype=torch.long).fill_(
            -1
        )
        self.losses = torch.empty(batch_size_actual).fill_(float("inf"))
        self.perturbations = self.perturbation_first_ex = torch.zeros(
            size=(batch_size_actual, max_seq_length, input_size)
        )
        self.comparison_funct = comparison_funct

    def update(self, epoch_successes: EpochSuccesses):
        loss_values_to_check = self.losses[
            epoch_successes.batch_indices.to("cpu")
        ]

        epoch_indices_to_copy_from = self.comparison_funct(
            loss_values_to_check, epoch_successes.losses
        )

        batch_indices_to_copy_to = epoch_successes.batch_indices[
            epoch_indices_to_copy_from
        ]
        self.epochs[batch_indices_to_copy_to] = epoch_successes.epoch_num
        self.losses[batch_indices_to_copy_to] = epoch_successes.losses[
            epoch_indices_to_copy_from
        ].to("cpu")
        self.perturbations[batch_indices_to_copy_to, :, :] = (
            epoch_successes.perturbations[epoch_indices_to_copy_from, :, :].to(
                "cpu"
            )
        )


class BatchResult:
    def __init__(
        self,
        dataset_indices: torch.tensor,
        input_seq_lengths: torch.tensor,
        max_seq_length: int,
        input_size: int,
    ):
        self.epochs_run = 0
        self.dataset_indices = dataset_indices
        self.input_seq_lengths = input_seq_lengths
        self.first_examples = RecordedBatchExamples(
            batch_size_actual=dataset_indices.shape[0],
            max_seq_length=max_seq_length,
            input_size=input_size,
            comparison_funct=has_no_entry,
        )
        self.best_examples = RecordedBatchExamples(
            batch_size_actual=dataset_indices.shape[0],
            max_seq_length=max_seq_length,
            input_size=input_size,
            comparison_funct=is_greater_than_new_val,
        )

    def update(self, epoch_successes: EpochSuccesses):
        self.epochs_run += 1
        self.first_examples.update(epoch_successes=epoch_successes)
        self.best_examples.update(epoch_successes=epoch_successes)


@dataclass
class RecordedTrainerExamples:
    epochs: torch.tensor = torch.LongTensor()
    losses: torch.tensor = torch.FloatTensor()
    perturbations: torch.tensor = torch.FloatTensor()
    device: torch.device = torch.device("cpu")

    def update(self, batch_examples: RecordedBatchExamples):
        self.epochs = torch.cat((self.epochs, batch_examples.epochs), dim=0)
        self.losses = torch.cat((self.losses, batch_examples.losses), dim=0)
        self.perturbations = torch.cat(
            (self.perturbations, batch_examples.perturbations), dim=0
        )


@dataclass
class TrainerResult:
    dataset: DatasetWithIndex
    dataset_indices: torch.tensor = torch.LongTensor()
    epochs_run: torch.tensor = torch.LongTensor()
    input_seq_lengths: torch.tensor = torch.LongTensor()
    first_examples: RecordedTrainerExamples = RecordedTrainerExamples()
    best_examples: RecordedTrainerExamples = RecordedTrainerExamples()

    def update(self, batch_result: BatchResult):
        self.first_examples.update(batch_examples=batch_result.first_examples)
        self.best_examples.update(batch_examples=batch_result.best_examples)
        self.dataset_indices = torch.cat(
            (self.dataset_indices, batch_result.dataset_indices)
        )
        self.input_seq_lengths = torch.cat(
            (self.input_seq_lengths, batch_result.input_seq_lengths)
        )
        self.epochs_run = torch.cat(
            (
                self.epochs_run,
                torch.empty(
                    batch_result.input_seq_lengths.shape[0],
                    dtype=torch.long,
                ).fill_(batch_result.epochs_run),
            )
        )


@dataclass
class AttackSummary:
    dataset: DatasetWithIndex
    epochs_run: np.ndarray
    dataset_indices_attacked: np.ndarray
    dataset_indices_success: np.ndarray
    first_epoch: np.ndarray
    first_loss: np.ndarray
    first_perturbation: list[np.ndarray]
    best_epoch: np.ndarray
    best_loss: np.ndarray
    best_perturbation: list[np.ndarray]

    @classmethod
    def from_trainer_result(cls, trainer_result: TrainerResult):
        success_trainer_indices = torch.where(
            trainer_result.first_examples.epochs != -1
        )[0]

        success_first_perts_list = [
            np.array(
                trainer_result.first_examples.perturbations[
                    i, : trainer_result.input_seq_lengths[i], :
                ]
            )
            for i in success_trainer_indices
        ]

        success_best_perts_list = [
            np.array(
                trainer_result.first_examples.perturbations[
                    i, : trainer_result.input_seq_lengths[i], :
                ]
            )
            for i in success_trainer_indices
        ]

        return cls(
            dataset=trainer_result.dataset,
            dataset_indices_attacked=np.array(trainer_result.dataset_indices),
            epochs_run=np.array(
                trainer_result.epochs_run[success_trainer_indices]
            ),
            dataset_indices_success=np.array(
                trainer_result.dataset_indices[success_trainer_indices]
            ),
            first_epoch=np.array(
                trainer_result.first_examples.epochs[success_trainer_indices]
            ),
            first_loss=np.array(
                trainer_result.first_examples.losses[success_trainer_indices]
            ),
            first_perturbation=success_first_perts_list,
            best_epoch=np.array(
                trainer_result.best_examples.epochs[success_trainer_indices]
            ),
            best_loss=np.array(
                trainer_result.best_examples.losses[success_trainer_indices]
            ),
            best_perturbation=success_best_perts_list,
        )

    # @property
    # def best_perturbation_sparsity(self) -> np.array:



@dataclass
class DatasetAttackSummary:
    dataset: Dataset
    attack_summary: AttackSummary


# def run_batch(
#     dataset_start_idx: int,
#     batch_size: int = 10,
#     epochs_per_batch: int = 50,
#     successes_per_batch: int = 3,
# ):
#     batch_result = BatchResult(
#         dataset_indices=torch.arange(
#             start=dataset_start_idx, end=dataset_start_idx + batch_size
#         ),
#         input_seq_lengths=torch.randint(low=2, high=6, size=(batch_size,)),
#         max_seq_length=5,
#         input_size=7,
#     )
#
#     for epoch_idx in range(epochs_per_batch):
#         epoch_successes = EpochSuccesses(
#             epoch_num=epoch_idx,
#             batch_indices=torch.tensor(
#                 np.random.choice(
#                     np.arange(batch_size),
#                     size=successes_per_batch,
#                     replace=False,
#                 )
#             ),
#             losses=5 * torch.abs(torch.randn(3)),
#             perturbations=torch.randn(successes_per_batch, 5, 7),
#         )
#         batch_result.update(epoch_successes=epoch_successes)
#
#     return batch_result
#
#
# if __name__ == "__main__":
#     if torch.cuda.is_available():
#         cur_device = torch.device("cuda:0")
#     else:
#         cur_device = torch.device("cpu")
#
#     my_trainer_result = TrainerResult()
#
#     my_batch_size = 10
#     for batch_idx in range(5):
#         my_batch_result = run_batch(
#             dataset_start_idx=batch_idx * my_batch_size
#         )
#         my_trainer_result.update(batch_result=my_batch_result)
