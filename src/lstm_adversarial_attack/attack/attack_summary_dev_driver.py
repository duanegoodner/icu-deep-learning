import lstm_adversarial_attack.attack.attack_summary as asu
import lstm_adversarial_attack.config_paths as cfg_paths
import lstm_adversarial_attack.resource_io as rio
import lstm_adversarial_attack.attack.attack_results_analyzer as ara
import lstm_adversarial_attack.attack.susceptibility_plotter as ssp

# build attack summary
result_path = (
    cfg_paths.FROZEN_HYPERPARAMETER_ATTACK
    / "2023-06-28_17_50_46.701620"
    / "2023-06-28_19_02_16.499026_final_attack_result.pickle"
)

# result_path = (
#     cfg_paths.FROZEN_HYPERPARAMETER_ATTACK
#     / "2023-06-30_12_05_34.834996"
#     / "2023-06-30_14_20_57.875925_final_attack_result.pickle"
# )


trainer_result = rio.ResourceImporter().import_pickle_to_object(
    path=result_path
)
attack_summary = asu.AttackResults(trainer_result=trainer_result)


# get measurement names
measurement_names_path = (
    cfg_paths.PREPROCESS_OUTPUT_DIR / "measurement_col_names.pickle"
)
measurement_names = rio.ResourceImporter().import_pickle_to_object(
    path=measurement_names_path
)

attack_result_analyzer = ara.AttackResultAnalyzer(
    attack_summary=attack_summary
)


zto_48hr_all_pert_counts_first = attack_result_analyzer.get_attack_analysis(
    example_type=asu.RecordedExampleType.FIRST, seq_length=48, orig_label=0
)

otz_48hr_all_pert_counts_first = attack_result_analyzer.get_attack_analysis(
    example_type=asu.RecordedExampleType.FIRST, seq_length=48, orig_label=1
)

zto_48hr_all_pert_counts_best = attack_result_analyzer.get_attack_analysis(
    example_type=asu.RecordedExampleType.BEST, seq_length=48, orig_label=0
)

otz_48hr_all_pert_counts_best = attack_result_analyzer.get_attack_analysis(
    example_type=asu.RecordedExampleType.BEST, seq_length=48, orig_label=1
)




# KEEP THIS. Just commenting out while work on other plots
# df_zto_first = zto_48hr_all_pert_counts_first.susceptibility_metrics.s_ij
# df_zto_best = zto_48hr_all_pert_counts_best.susceptibility_metrics.s_ij
# df_otz_first = otz_48hr_all_pert_counts_first.susceptibility_metrics.s_ij
# df_otz_best = otz_48hr_all_pert_counts_best.susceptibility_metrics.s_ij

# plotter = ssp.SusceptibilityPlotter(
#     susceptibility_dfs=[
#         [df_zto_first, df_zto_best],
#         [df_otz_first, df_otz_best],
#     ],
#     df_titles=[
#             [
#                 "0 \u2192 1 Attack, First Examples",
#                 "0 \u2192 1 Attack, Best Examples",
#             ],
#             [
#                 "1 \u2192 0 Attack, First Examples",
#                 "1 \u2192 0 Attack, Best Examples",
#             ],
#         ],
#     main_plot_title="Perturbation Susceptibility Scores"
# )
# plotter.plot_susceptibilities()

