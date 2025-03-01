# ICU Deep Learning  

## Project Overview  

This project implements and optimizes **Long Short-Term Memory (LSTM)** time series models of intensive care unit (ICU) patient lab and vital sign data to predict patient outcomes. Additionally, an **adversarial attack** algorithm is used to discover adversarial examples for trained models.  

Raw data were obtained from the [Medical Information Mart for Intensive Care (MIMIC-III)](https://physionet.org/content/mimiciii/1.4/) database [[1](#ref_01), [2](#ref_02)]. The predictive model input consists of data from 13 lab measurements and 6 vital signs collected during the first 48 hours after patient admission to the ICU. The prediction target is a binary variable representing in-hospital mortality. This type of model can supplement standard heuristics used by care providers in identifying high-risk patients.  

The results of adversarial attacks on trained LSTM models provide a gauge of model stability. Additionally, these results offer an opportunity to compare adversarial vulnerabilities in LSTMs with the well-documented [[3](#ref_03), [4](#ref_04)] adversarial behaviors observed in Convolutional Neural Networks (CNNs) used for computer vision. Unlike the adversarial examples found in CNNs — where perturbations imperceptible to the human eye can drastically alter model predictions — the adversarial examples discovered for our LSTM models exhibit a higher degree of plausibility, aligning more closely with human intuition.  

## Getting Started  

### 📌 Viewing Documentation  
The full documentation, including detailed descriptions of the methodology and implementation, is contained in the project Jupyter notebook. If using the notebook purely for informational purposes (without running the code), you can:
- View the [notebook file directly on GitHUb](https://github.com/duanegoodner/icu-deep-learning/blob/main/notebooks/icu_deep_learning.ipynb) directly on GitHUb
-  Open it in Google Colab for a more interactive reading experience with easier navigation:  
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/duanegoodner/lstm_adversarial_attack/blob/main/notebooks/icu_deep_learning.ipynb)  


### 🚀 Running the Project  
To run the project code, follow the instructions in [SETUP.md](SETUP.md) for setting up and running in a containerized environment.  

## Acknowledgement of Prior Studies  

This project builds on previous studies [[5](#ref_05), [6](#ref_06)] that were the first to apply LSTM-based predictive modeling and adversarial attacks to ICU patient data from the MIMIC-III database. While the initial goal was to reproduce and validate portions of the earlier studies, the project has since evolved into significant extensions and new contributions. However, none of this progress would have been possible without the invaluable foundation provided by the original research.  

## Highlights  

- **Extensive hyperparameter tuning** for predictive and attack models.  
- **Flexible attack objectives** allow targeting different types of adversarial perturbations.  
- **Fully containerized** for easy, reproducible environment setup.  
- **Single `config.toml` file** centralizes all parameters for streamlined modification and experimentation.  
- **Auto-generated data provenance** ensures reproducibility and prevents losing track of "what worked" during experiments.  
- **Modular data pipeline** eliminates the need for redundant upstream runs when testing multiple downstream settings.  
- **Flexible execution** — each pipeline component can run from the command line or inside the project's Jupyter notebook.  
- **Efficient adversarial attacks** — developed a custom PyTorch `AdversarialAttacker` module capable of attacking batches of samples.
- **Avoids security risks of .pkl files** — uses .json and .feather file formats for serialization.
- **60% Higher predictive performance (F1 score) and 10× faster data preprocessing** compared to prior studies.  


## Example Data: Input Elements' Perturbation Probability 

Each model input consists of a [19 × 48] array representing hourly values of 13 lab measurements and 6 vital signs collected over a 48-hour period. To analyze the adversarial behavior of a trained model under a specific attack objective function, we perform multiple attack iterations on each sample in a population. The attack objective function can favor small perturbation magnitude, sparse perturbations, or both.

For each sample, an adversarial example may be found after some number of attack iterations — or in some cases, not at all. Once the *first* adversarial example is discovered for a sample, we continue attacking the sample (up to a predefined iteration limit) to identify perturbations that further minimize the attack objective function and record the example with the lowest value of the attack objective function as that sample's *best* adversarial example.  The perturbation associated with a *best* example has lower magnitude and/or greater sparsity than its corresponding *first example*.

A "*zero-to-one*" attack refers to an adversarial perturbation that flips a model's predicted output from `0` (non-mortality) to `1` (mortality)**. Similarly, a *"one-to-zero"* attack flips the predicted output from `1` to `0`.

The "Perturbation Probability" figure below shows the fraction of adversarial examples in which each input array element is non-zero for the *first* and *best* discovered examples, with separate plots for *zero-to-one* and *one-to-zero* attacks.

![Perturbation Probability](docs/perturbation_probability_data.png)

Some key takeaways from the above data:
- For the *first* examples, most measurements' perturbation probability is fairly evenly distributed across the 48-hour observation period, though does increase for later times.
- SpO<sub>2</sub> perturbations are less common in first examples compared to other measurements. However, this difference disappears in best examples.
- The best examples strongly favor perturbations at the end of the observation period. These adversarial examples are not what we would call "anomalous." A human interpreter would also be more likely to misinterpret a late-time perturbation.
- Fine details in the probability distributions are well-matched between *zero-to-one* and *one-to-zero* best examples, suggesting that the model’s vulnerabilities are generally independent of the attack direction.

For additional exploration and analysis, refer to the [Getting Started](#getting-started) section.


## **Tools Used**  

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python) ![PyTorch](https://img.shields.io/badge/PyTorch-%23EE4C2C?logo=pytorch&logoColor=white) ![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?logo=postgresql&logoColor=white) ![Pandas](https://img.shields.io/badge/Pandas-150458?logo=pandas&logoColor=white) ![NumPy](https://img.shields.io/badge/NumPy-013243?logo=numpy&logoColor=white) ![Apache Arrow](https://img.shields.io/badge/Apache%20Arrow-0E77B3?logo=apache) ![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-F7931E?logo=scikit-learn&logoColor=white) ![TensorBoard](https://img.shields.io/badge/TensorBoard-FF6F00?logo=tensorflow&logoColor=white) ![Matplotlib](https://img.shields.io/badge/Matplotlib-11557C?logo=plotly&logoColor=white) ![Optuna](https://img.shields.io/badge/Optuna-7C3AED?logo=python&logoColor=white) ![msgspec](https://img.shields.io/badge/msgspec-blue) ![Jupyter](https://img.shields.io/badge/Jupyter-F37626.svg?&logo=Jupyter&logoColor=white)



# References


<a><a id="ref_01">1.</a> </a>[Johnson, A., Pollard, T., and Mark, R. (2016) 'MIMIC-III Clinical Database' (version 1.4), *PhysioNet*.](https://doi.org/10.13026/C2XW26) 

<a id="ref_02">2.</a> [Johnson, A. E. W., Pollard, T. J., Shen, L., Lehman, L. H., Feng, M., Ghassemi, M., Moody, B., Szolovits, P., Celi, L. A., & Mark, R. G. (2016). MIMIC-III, a freely accessible critical care database. Scientific Data, 3, 160035.](https://www.nature.com/articles/sdata201635)

<a id="ref_03">3.</a> [Goodfellow, I.J., Shlens, J. and Szegedy, C., 2014. Explaining and harnessing adversarial examples. arXiv preprint arXiv:1412.6572.](https://arxiv.org/abs/1412.6572)

<a id="ref_04">4.</a> [Akhtar, N., Mian, A., Kardan, N. and Shah, M., 2021. Advances in adversarial attacks and defenses in computer vision: A survey. IEEE Access, 9, pp.155161-155196.](https://arxiv.org/abs/2108.00401)

<a id="ref_05">5.</a> [Sun, M., Tang, F., Yi, J., Wang, F. and Zhou, J., 2018, July. Identify susceptible locations in medical records via adversarial attacks on deep predictive models. In *Proceedings of the 24th ACM SIGKDD international conference on knowledge discovery & data mining* (pp. 793-801).](https://dl.acm.org/doi/10.1145/3219819.3219909)

<a id="ref_06">6.</a> [Tang, F., Xiao, C., Wang, F. and Zhou, J., 2018. Predictive modeling in urgent care: a comparative study of machine learning approaches. *Jamia Open*, *1*(1), pp.87-98.](https://academic.oup.com/jamiaopen/article/1/1/87/5032901)

