import numpy as np
import torch
from torch.utils.data import Dataset
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable
import lstm_adversarial_attack.dataset_with_index as dsi


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
    epochs: torch.tensor = None
    losses: torch.tensor = None
    perturbations: torch.tensor = None
    device: torch.device = torch.device("cpu")

    def __post_init__(self):
        if self.epochs is None:
            self.epochs = torch.LongTensor()
        if self.losses is None:
            self.losses = torch.FloatTensor()
        if self.perturbations is None:
            self.perturbations = torch.FloatTensor()

    def update(self, batch_examples: RecordedBatchExamples):
        self.epochs = torch.cat((self.epochs, batch_examples.epochs), dim=0)
        self.losses = torch.cat((self.losses, batch_examples.losses), dim=0)
        self.perturbations = torch.cat(
            (self.perturbations, batch_examples.perturbations), dim=0
        )


@dataclass
class RecordedTrainerExamplesNP:
    epochs: np.array
    losses: np.array
    perturbations: np.array

    @classmethod
    def from_recorded_trainer_examples_torch(
        cls,
        recorded_trainer_examples_torch: RecordedTrainerExamples,
    ):
        return cls(
            epochs=recorded_trainer_examples_torch.epochs,
            losses=recorded_trainer_examples_torch.losses,
            perturbations=recorded_trainer_examples_torch.perturbations,
        )


@dataclass
class TrainerResult:
    dataset: dsi.DatasetWithIndex
    dataset_indices: torch.tensor = None
    epochs_run: torch.tensor = None
    input_seq_lengths: torch.tensor = None
    first_examples: RecordedTrainerExamples = None
    best_examples: RecordedTrainerExamples = None

    def __post_init__(self):
        if self.dataset_indices is None:
            self.dataset_indices = torch.LongTensor()
        if self.epochs_run is None:
            self.epochs_run = torch.LongTensor()
        if self.input_seq_lengths is None:
            self.input_seq_lengths = torch.LongTensor()
        if self.first_examples is None:
            self.first_examples = RecordedTrainerExamples()
        if self.best_examples is None:
            self.best_examples = RecordedTrainerExamples()

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


class PerturbationSummaryOld:
    def __init__(
        self, padded_perts: torch.tensor, input_seq_lengths: torch.tensor
    ):
        self.padded_perts = padded_perts
        self.input_seq_lengths = input_seq_lengths

    @property
    def actual_perts(self):
        return [
            self.padded_perts[i, : self.input_seq_lengths[i], :]
            for i in range(self.input_seq_lengths.shape[0])
        ]

    @property
    def abs_perts(self):
        return [torch.abs(item) for item in self.actual_perts]

    @property
    def sum_abs_perts(self):
        return torch.tensor([torch.sum(item) for item in self.abs_perts])

    @property
    def pert_magnitude_mean_vals(self):
        return torch.tensor([torch.mean(item) for item in self.abs_perts])

    @property
    def pert_magnitude_min_vals(self):
        return torch.tensor([torch.min(item) for item in self.abs_perts])

    @property
    def pert_magnitude_max_vals(self):
        return torch.tensor([torch.max(item) for item in self.abs_perts])

    @property
    def pert_magnitude_global_mean(self):
        return torch.mean(self.pert_magnitude_mean_vals)

    @property
    def pert_magnitude_global_mean_max(self):
        return torch.mean(self.pert_magnitude_max_vals)

    @property
    def num_actual_elements(self):
        return self.input_seq_lengths * self.padded_perts.shape[2]

    @property
    def num_nonzero(self):
        return torch.tensor(
            [torch.count_nonzero(item) for item in self.actual_perts]
        )

    def num_examples_with_num_nonzero_less_than(self, cutoff: int):
        return torch.where(self.num_nonzero < cutoff)[0].shape[0]

    @property
    def fraction_nonzero(self):
        return self.num_nonzero.float() / self.num_actual_elements.float()

    @property
    def fraction_nonzero_mean(self):
        return torch.mean(self.fraction_nonzero)

    @property
    def fraction_nonzero_stdev(self):
        return torch.std(self.fraction_nonzero)

    @property
    def fraction_nonzero_min(self):
        if len(self.fraction_nonzero) == 0:
            return torch.tensor([], dtype=torch.float32)
        else:
            return torch.min(self.fraction_nonzero)

    @property
    def sparsity(self):
        if len(self.fraction_nonzero) == 0:
            return torch.tensor([], dtype=torch.float32)
        else:
            return 1 - self.fraction_nonzero

    @property
    def sparsity_mean(self):
        return torch.mean(self.sparsity)

    @property
    def sparsity_stdev(self):
        return torch.std(self.sparsity)

    @property
    def sparse_small_scores(self):
        if len(self.fraction_nonzero) == 0:
            return torch.tensor([], dtype=torch.float32)
        else:
            return (1 - self.fraction_nonzero) / self.sum_abs_perts


class RecordedExampleType(Enum):
    FIRST = auto()
    BEST = auto()


class ExamplesSummary:
    def __init__(
        self,
        discoverty_epoch: np.array,
        losses: np.array,
        seq_lengths: np.array,
        padded_perts: np.array,
    ):
        self.discoverty_epoch = discoverty_epoch
        self.losses = losses
        self.seq_lengths = seq_lengths
        self.padded_perts = padded_perts

    @property
    def mask(self) -> np.array:
        time_indices = np.arange(self.padded_perts.shape[1])
        time_is_in_range = time_indices.reshape(
            1, -1
        ) < self.seq_lengths.reshape(-1, 1)
        time_is_in_range_bcast = np.broadcast_to(
            time_is_in_range,
            (self.padded_perts.shape[2], *time_is_in_range.shape),
        )
        return ~np.moveaxis(time_is_in_range_bcast, 0, -1)

    @property
    def masked_perts(self) -> np.ma.MaskedArray:
        return np.ma.array(self.padded_perts, mask=self.mask)

    @property
    def masked_perts_abs_val(self):
        return np.abs(self.masked_perts)

    @property
    def masked_perts_mean_abs_val(self):
        return np.mean(self.masked_perts_abs_val, axis=(1, 2))

    @property
    def padded_perts_abs_val(self) -> np.array:
        return np.abs(self.padded_perts)

    @property
    def perts_actual(self) -> list[np.array]:
        return [
            self.padded_perts[example_idx, : self.seq_lengths[example_idx], :]
            for example_idx in range(self.seq_lengths.shape[0])
        ]

    @property
    def perts_abs_val(self) -> list[np.array]:
        return [np.abs(perts_array) for perts_array in self.perts_actual]

    @property
    def perts_mean_abs_val(self) -> np.array:
        return np.array(
            [
                np.mean(abs_perts_array)
                for abs_perts_array in self.perts_abs_val
            ]
        )

    # @property
    # def perts_mean_abs_val_no_list(self) -> np.array:

    @property
    def perts_max_abs_val(self) -> np.array:
        return np.array(
            [np.max(abs_perts_array) for abs_perts_array in self.perts_abs_val]
        )

    @property
    def perts_mean_max_abs_val(self) -> float:
        return np.mean(self.perts_max_abs_val).item()

    @property
    def perts_nonzero_indices(self) -> list[tuple[np.array, np.array]]:
        return [
            np.argwhere(abs_val_array) for abs_val_array in self.perts_abs_val
        ]

    # @property
    # def perts_nonzero_vals(self):

    # @property
    # def perts_min_nonzero_abs_val(self) -> np.array:
    #     return np.array(
    #         [np.min(self.perts_abs_val[np.where(self.perts_abs_val != 0)])]
    #     )


class TrainerSuccessSummary:
    def __init__(self, trainer_result: TrainerResult):
        self.trainer_result = trainer_result

    @property
    def indices_dataset_attacked(self) -> np.array:
        return np.array(self.trainer_result.dataset_indices)

    @property
    def indices_trainer_success(self) -> np.array:
        first_indices_success_trainer = np.where(
            self.trainer_result.first_examples.epochs != -1
        )[0]

        best_indices_success_trainer = np.where(
            self.trainer_result.best_examples.epochs != -1
        )[0]

        assert np.all(
            first_indices_success_trainer == best_indices_success_trainer
        )
        return best_indices_success_trainer

    @property
    def indices_dataset_success(self) -> np.array:
        return self.indices_dataset_attacked[self.indices_trainer_success]

    @property
    def orig_labels_attacked(self) -> np.array:
        return np.array(self.trainer_result.dataset[:][2])[
            self.indices_dataset_attacked
        ]

    @property
    def orig_labels_success(self) -> np.array:
        return np.array(self.trainer_result.dataset[:][2])[
            self.indices_dataset_success
        ]

    @property
    def input_seq_lengths_attacked(self) -> np.array:
        return np.array(self.trainer_result.input_seq_lengths)

    @property
    def inputs_seq_lengths_success(self) -> np.array:
        return self.input_seq_lengths_attacked[self.indices_trainer_success]

    @property
    def recorded_examples_first(self) -> RecordedTrainerExamplesNP:
        return RecordedTrainerExamplesNP(
            epochs=np.array(
                self.trainer_result.first_examples.epochs[
                    self.indices_trainer_success
                ]
            ),
            losses=np.array(
                self.trainer_result.first_examples.losses[
                    self.indices_trainer_success
                ]
            ),
            perturbations=np.array(
                self.trainer_result.first_examples.perturbations[
                    self.indices_trainer_success, :, :
                ]
            ),
        )

    @property
    def recorded_examples_best(self) -> RecordedTrainerExamplesNP:
        return RecordedTrainerExamplesNP(
            epochs=np.array(
                self.trainer_result.best_examples.epochs[
                    self.indices_trainer_success
                ]
            ),
            losses=np.array(
                self.trainer_result.best_examples.losses[
                    self.indices_trainer_success
                ]
            ),
            perturbations=np.array(
                self.trainer_result.best_examples.perturbations[
                    self.indices_trainer_success, :, :
                ]
            ),
        )

    @property
    def examples_summary_first(self) -> ExamplesSummary:
        return ExamplesSummary(
            discoverty_epoch=np.array(
                self.trainer_result.first_examples.epochs[
                    self.indices_trainer_success
                ]
            ),
            losses=np.array(
                self.trainer_result.first_examples.losses[
                    self.indices_trainer_success
                ]
            ),
            seq_lengths=self.inputs_seq_lengths_success,
            padded_perts=np.array(
                self.trainer_result.first_examples.perturbations[
                    self.indices_trainer_success, :, :
                ]
            ),
        )

    @property
    def examples_summary_best(self) -> ExamplesSummary:
        return ExamplesSummary(
            discoverty_epoch=np.array(
                self.trainer_result.best_examples.epochs[
                    self.indices_trainer_success
                ]
            ),
            losses=np.array(
                self.trainer_result.best_examples.losses[
                    self.indices_trainer_success
                ]
            ),
            seq_lengths=self.inputs_seq_lengths_success,
            padded_perts=np.array(
                self.trainer_result.best_examples.perturbations[
                    self.indices_trainer_success, :, :
                ]
            ),
        )

    # @property
    # def recorded_examples_best(self) -> RecordedTrainerExamplesNP:
    #     return RecordedTrainerExamplesNP(
    #         epochs=self.trainer_result.best_examples.epochs[
    #             self.indices_trainer_success
    #         ],
    #         losses=self.trainer_result.best_examples.losses[
    #             self.indices_trainer_success
    #         ],
    #         perturbations=self.trainer_result.best_examples.perturbations[
    #                       self.indices_trainer_success, :, :
    #                       ]
    #     )

    # @property
    # def indices_success_trainer(self) -> torch.tensor:
    #     best_indices_success_trainer = torch.where(
    #         self.trainer_result.best_examples.epochs != -1
    #     )[0]
    #     first_indices_success_trainer = torch.where(
    #         self.trainer_result.first_examples.epochs != -1
    #     )[0]
    #     assert (
    #         (best_indices_success_trainer == first_indices_success_trainer)
    #         .all()
    #         .item()
    #     )
    #     return best_indices_success_trainer
    #
    # @property
    # def indices_success_dataset(self) -> torch.tensor:
    #     return self.trainer_result.dataset_indices[
    #         self.indices_success_trainer
    #     ]
    #
    # @property
    # def orig_labels_attacked(self) -> torch.tensor:
    #     return self.trainer_result.dataset[:][2]
    #
    # @property
    # def orig_labels_success(self) -> torch.tensor:
    #
    #
    #
    #
    # @property
    # def input_seq_lengths(self) -> torch.tensor:
    #     return self.trainer_result.input_seq_lengths[
    #         self.indices_success_trainer
    #     ]
    #
    # @property
    # def first_recorded_examples(self) -> RecordedTrainerExamples:
    #     return RecordedTrainerExamples(
    #         epochs=self.trainer_result.first_examples.epochs[
    #             self.indices_success_trainer
    #         ],
    #         losses=self.trainer_result.first_examples.losses[
    #             self.indices_success_trainer
    #         ],
    #         perturbations=self.trainer_result.first_examples.perturbations[
    #             self.indices_success_trainer, :, :
    #         ],
    #     )
    #
    # @property
    # def best_recorded_examples(self) -> RecordedTrainerExamples:
    #     return RecordedTrainerExamples(
    #         epochs=self.trainer_result.best_examples.epochs[
    #             self.indices_success_trainer
    #         ],
    #         losses=self.trainer_result.best_examples.losses[
    #             self.indices_success_trainer
    #         ],
    #         perturbations=self.trainer_result.best_examples.perturbations[
    #             self.indices_success_trainer, :, :
    #         ],
    #     )
    #
    # @property
    # def first_examples_perts_summary(self) -> PerturbationSummary:
    #     return PerturbationSummary(
    #         padded_perts=self.first_recorded_examples.perturbations,
    #         input_seq_lengths=self.input_seq_lengths,
    #     )
    #
    # @property
    # def best_examples_perts_summary(self) -> PerturbationSummary:
    #     return PerturbationSummary(
    #         padded_perts=self.best_recorded_examples.perturbations,
    #         input_seq_lengths=self.input_seq_lengths,
    #     )
    #
    # def trainer_indices_for_samples_of_length(self, n: int) -> torch.tensor:
    #     return self.indices_success_trainer[
    #         torch.where(self.input_seq_lengths == n)[0]
    #     ]

    # def trainer_indices_for_samples_of_orig_label(
    #     self, orig_label: int
    # ) -> torch.tensor:
    #     torch.where[]


# class TrainerSuccessSummary:
#     def __init__(self, trainer_result: TrainerResult):
#         best_success_trainer_indices = torch.where(
#             trainer_result.best_examples.epochs != -1
#         )[0]
#         first_success_trainer_indices = torch.where(
#             trainer_result.first_examples.epochs != -1
#         )[0]
#         assert (
#             (best_success_trainer_indices == first_success_trainer_indices)
#             .all()
#             .item()
#         )
#
#         self.dataset = trainer_result.dataset
#         self.attacked_dataset_indices = trainer_result.dataset_indices
#         self.success_dataset_indices = trainer_result.dataset_indices[
#             best_success_trainer_indices
#         ]
#         self.epochs_run = trainer_result.epochs_run[
#             best_success_trainer_indices
#         ]
#         self.input_seq_lengths = trainer_result.input_seq_lengths[
#             best_success_trainer_indices
#         ]
#         self.first_examples = RecordedTrainerExamples(
#             epochs=trainer_result.first_examples.epochs[
#                 first_success_trainer_indices
#             ],
#             losses=trainer_result.first_examples.losses[
#                 first_success_trainer_indices
#             ],
#             perturbations=trainer_result.first_examples.perturbations[
#                 first_success_trainer_indices, :, :
#             ],
#         )
#         self.best_examples = RecordedTrainerExamples(
#             epochs=trainer_result.best_examples.epochs[
#                 best_success_trainer_indices
#             ],
#             losses=trainer_result.best_examples.losses[
#                 best_success_trainer_indices
#             ],
#             perturbations=trainer_result.best_examples.perturbations[
#                 best_success_trainer_indices, :, :
#             ],
#         )
#         self.first_perts_summary = PerturbationSummary(
#             padded_perts=self.first_examples.perturbations,
#             input_seq_lengths=self.input_seq_lengths,
#         )
#         self.best_perts_summary = PerturbationSummary(
#             padded_perts=self.best_examples.perturbations,
#             input_seq_lengths=self.input_seq_lengths,
#         )
#
#     def get_filtered_perts(
#         self,
#         perts_type: str = None,
#         seq_length: int = None,
#         orig_label: int = None,
#     ) -> torch.tensor:
#         assert perts_type == "first" or perts_type == "best"
#         full_examples = (
#             self.first_examples
#             if perts_type == "first"
#             else self.best_examples
#         )
#
#         if seq_length is not None:
#             match_seq_length_summary_indices = torch.where(
#                 self.input_seq_lengths == seq_length
#             )[0]
#         else:
#             match_seq_length_summary_indices = torch.arange(
#                 len(self.input_seq_lengths)
#             )
#
#         label_tensor = torch.tensor(self.dataset[:][2])
#         success_orig_labels = label_tensor[self.success_dataset_indices]
#         if orig_label is not None:
#             match_label_dataset_indices = torch.where(
#                 success_orig_labels == orig_label
#             )[0]
#         else:
#             match_label_dataset_indices = torch.arange(
#                 len(self.success_dataset_indices)
#             )
#
#         filtered_indices = np.intersect1d(
#             match_seq_length_summary_indices, match_label_dataset_indices
#         )
#
#         filtered_perts = full_examples.perturbations[filtered_indices, :, :]
#         filtered_seq_lengths = self.input_seq_lengths[filtered_indices]
#
#         return filtered_perts
