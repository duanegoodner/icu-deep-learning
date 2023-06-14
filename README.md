# lstm_adversarial_attack
LSTM time series deep learning model and adversarial attacks



## Overview

## 1. Overview

### 1.1 Summary of Prior Work

This project builds on results originally published in:

[Sun, M., Tang, F., Yi, J., Wang, F. and Zhou, J., 2018, July. Identify susceptible locations in medical records via adversarial attacks on deep predictive models. In *Proceedings of the 24th ACM SIGKDD international conference on knowledge discovery & data mining* (pp. 793-801)](https://dl.acm.org/doi/10.1145/3219819.3219909)

The original paper trained a Long Short-Term Memory (LSTM) time series model sing data from the Medical Information Mart for Intensive Care (MIMIC-III) database to predict patient outcomes. The input features consisted of data from 13 lab measurements (Blood Urea Nitrogen, HCO<sub>3</sub>, Na, PaCO2, Glucose, Creatinine, Albumin, Mg, K, Ca, Platelets, and Lactate), and 6 vital signs (Heart Rate, Respiration Rate, Systolic Blood Pressure, Diastolic Blood Pressure, Oxygen Saturation, and Temperature). The prediction target was a binary variable representing in-hospital mortality. Input data for each patient were collected over time spans ranging from 6 to 48 hours. The dataset used for model training and evaluation contained 37,559 samples. Each sample consisted of  a single ICU stay by a patient and was represented by a 48 (hour) x 19 (measurements) input feature matrix. Samples with less than 48 hours of data were padded to 48 hours  the global mean value of each measurement parameter. 

The full LSTM model consisted of:

- A single-layer, bi-directional LSTM with an input size of 19, and 128 hidden states per direction. Tanh activation was applied to the outputs.
- A dropout layer with dropout probability = 50%
- A fully-connected layer with an input size of 256 (for the 2 x 128 LSTM outputs), 32 output nodes, and ReLU activation.
- A final 2-node layer with soft-max activation.

This model was trained using a Binary Cross Entropy loss, and an Adam optimizer (learning rate = 1e-4, momentum decay rate = 0.999, and moving average decay rate = 0.5). An adversarial attack algorithm was then used to identify small perturbations which, when applied to a real, correctly-classified input features, caused the trained model to misclassify the perturbed input. The attack algorithm used L1 regularization to favor adversarial examples with sparse perturbations that resemble the structure of data entry errors most likely to occur in real medical data. Attacks were run serially (one sample at a time), and the attack on a given sample was halted upon finding a single adversarial example.

### 1.2 Focus and Key Findings of Current Poject

The current project follows the general approach of Sun et al, and adds the modifications / extensions

- Implementation in PyTorch (instead of Tensorflow).

- A larger dataset (41,951 patient ICU stays vs 37,559 in the original study). For patients with multiple ICU stays, the original study's code filtered all all stays after the initial stay. This removal appears to have been indadvertent.

- A streamlined `preprocess` sub-package is used to convert database SQL query outputs to the tensor form used for model input. This package reduces RAM consumption by saving large intermediate data structures to disk (primarily Pandas dataframes saved as .pickle files) instead of returning them to global scope of an executing program. It also performs the query output to tensor conversion 90% faster than the original code, primarily through the use of vectorized operations.

- The feature matrices of samples with data collection time ranges less than the maximum observation window (typically 48 hours) are padded with zero values. The padded data are input to the LSTM as Pytorch PackedSequence objects, allowing the padding values to be ignored by the model.

- A GPU-compatible adversarial attack algorithm is implemented to enable running attacks on batches of samples. This enabled a 20X reduction in the the amount of time needed to perform attacks on the full dataset. 

- LSTM predictive performance is improved hyperparameter tuning with the the Optuna Tree-structued Parzen Estimator (TPE) algorithm

- Hyperparameter tuning of the attack algorithm (also using TPE) to find adversarial perturbations with higher sparsity and lower magnitude.

- The attack algorithm was allowed to continue running after the first adversarial example was found for a given input. In most cases, these additional search iterations led to new adversarial examples that exhibited greater sparsity and smaller perturbations than the initially discovered examples.

  



## How to run this project

This section contains instructions on how to set up a development environment to run the project code. (These steps are not necessary if you just want to review the results in the completed Jupyter notebook [link])

### 1. Requirements

* CUDA-enabled GPU
* git
* Docker
* [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/overview.html#installation-guide)



### 2. Build a  PostgreSQL MIMIC-III database inside a Docker container

> **Note**  ~ 60 GB storage is needed to build the database, and the entire process may take 1.5 - 2.0 hours.

Go to https://github.com/duanegoodner/docker_postgres_mimiciii, and follow that repository's Getting Started steps 1 through 6 to build a PostgreSQL MIMIC-III database in a named Docker volume, and a Docker image with a PostgreSQL database that can access the named volume.



### 3. Clone the lstm_adversarial_attack repository to your machine:

```
$ git clone https://github.com/duanegoodner/lstm_adversarial_attack
```



### 4. Set the `LOCAL_PROJECT_ROOT` environment variable (to be used by Docker)

> **Note** The size of the `lstm_aa_app` image will be ~10 GB.

In file `lstm_adversarial_attack/docker/app/.env`, set the value of `LOCAL_PROJECT_ROOT` to the absolute path of the `lstm_adversarial_attack` root directory. Leave the values of `PROJECT_NAME`, `CONTAINER_DEVSPACE`, and `CONTAINER_PROJECT_ROOT` unchanged. For example, if in you ran the command in step 3 from directory `/home/my_user/projects` causing the cloned repo root to be `/home/my_user/projects/lstm_adversarial_attack`  your `lstm_adversarial_attack/docker/app/.env` file would look like this:

```
LOCAL_PROJECT_ROOT=/home/my_user/projects/lstm_adversarial_attack

PROJECT_NAME=lstm_adversarial_attack
CONTAINER_DEVSPACE=/home/devspace
CONTAINER_PROJECT_ROOT=${CONTAINER_DEVSPACE}/project
```



### 5. Build the `lstm_aa_app` Docker image

`cd` into directory `lstm_adversarial_attack/docker`, and run:

```
$ docker compose build
```





## Instructions for running code and viewing results in this repository

### Step 1. Download data

This work uses a subset of the MIMIC-III database. The queries used to extract the necessary views and tables from MIMIC-III are saved in `src/docker_db/mimiciii_queries` . The outputs from running these queries are saved as `.targ.gz` files in in`data/mimiciii_query_results` . (So it is not necessary to download the MIMIC-III database. Just clone this repository.) After cloning the ehr_adversarial_attack repository, run the following command from the project root to extract the query results into .csv format:

```
$ find data/mimiciii_query_results -type f -name '*.tar.gz' -execdir tar -xzvf {} \;
```

Output:

```
pivoted_bg.csv
d_icd_diagnoses.csv
icustay_detail.csv
pivoted_vital.csv
admissions.csv
diagnoses_icd.csv
pivoted_gc.csv
pivoted_uo.csv
pivoted_lab.csv
```

### Step 2. Obtain pre-processed data

There are two options for obtaining data that have been converted from the SQL query output format to the feature and label tensors required for LSTM model input. Option A is faster.

#### Option A: Extract the existing preprocessed archive files

From the repository root directory, run the command:

```
$ find data/output_feature_finalizer -type f -name '*.tar.gz' -execdir tar -xzvf {} \;
```

Output:

```
in_hospital_mortality_list.pickle
measurement_data_list.pickle
measurement_col_names.pickle
```

#### Option B: Run the preprocessing code

From the repository root directory, run the following command to preprocess the SQL query outputs into the LSTM model input format:

```
$ python src/preprocess/main.py
```

Output:

```shell
Starting Prefilter
Done with Prefilter

Starting ICUStatyMeasurementCombiner
Done with ICUStatyMeasurementCombiner

Starting FullAdmissionListBuilder
Done with FullAdmissionListBuilder

Starting FeatureBuilder
Done processing sample 0/41960
Done processing sample 5000/41960
Done processing sample 10000/41960
Done processing sample 15000/41960
Done processing sample 20000/41960
Done processing sample 25000/41960
Done processing sample 30000/41960
Done processing sample 35000/41960
Done processing sample 40000/41960
Done with FeatureBuilder

Starting FeatureFinalizer
Done with FeatureFinalizer

All Done!
Total preprocessing time = 555.2803893089294 seconds

```



### Step 3. Obtain a trained LSTM model

This step also has a fast option (A), and a slow option (B).

#### Option A: Do nothing, except note the filename that will be needed for Step 4

Parameters of a pre-trained LSTM model are saved in `data/cross_validate_sun2018_full48m19_01/2023-05-07_23:32:09.938445.tar`. Take note of the filename `2023-05-07_23:32:09.938445.tar` (just the filename, not the full path), so you can use it as input when running adversarial attacks in Step 4.

#### Option B: Run the cross-validation script

From the repository root directory, run:

```
$ python src/LSTMSun2018_cross_validate.py
```

This will train LSTM model using cross-validation and and evaluate the predictive performance periodically throughout the training process. Note that this method (used in the original paper) has drawbacks due to the fact that it never evaluates the model on unseen data, so there is significant risk of overfitting.

Output:

```ll
# Many realtime updates on training loss and evaluation metrics
Model parameters saved in file: 2023-05-07_23:40:59.241609.tar
# your filename will be different, but will have the same format
```

Take note of the .tar filename. for use in Step 4.



### Step 4. Run adversarial attacks on the model

Now we are ready to run an adversarial attack on an the trained LSTM model. From the repository root, run:

```
$ python src/adv_attack_full48_m19.py -f <file_name_obained_from_step_3.tar>
```

For example, if you used Option A in Step 3, you would run `$ python src/adv_attack_full48_m19.py -f 2023-05-07_23:32:09.938445.tar`

Output:

```
# Updates on elapsed time and index of sample under attack
Attack summary data saved in k0.0-l10.15-lr0.1-ma100-ms1-2023-05-07_23:47:51.261865.pickle
# Your .tar filename will be different, but will have the same format.
```

Once again, only the filename (not full path), is printed, but that's all you need for the next step.



### Step 5. Plot results of the adversarial attacks

From the repo root directory, run:

```
$ python src/attack_results_analyzer.py -f <filename_from_step4_output.tar>
```

For example, if your output from Step 4 said: `Attack summary data saved in k0.0-l10.15-lr0.1-ma100-ms1-2023-05-07_23:47:51.261865.pickle`, you would run `$ python src/attack_results_analyzer.py -f k0.0-l10.15-lr0.1-ma100-ms1-2023-05-07_23:47:51.261865.pickle `

This will produce plots of attack susceptibilities of various measurements vs. time for 0-to-1 and 1-to-0 attacks.  (The plot for 1-to-0 should appear first. Depending on your environment, you may need to close this plot window before the 0-to-1 plot appears.)



## Key Results

#### LSTM predictive metrics

Here are the LSTM predictive evaluation metrics from the original paper and our work. The performance metric scores from our study are actually higher than those in the original work.

<img src="https://github.com/duanegoodner/ehr_adversarial_attack/blob/main/data/images/LStM_predictive_metrics.png"  width="40%" height="30%">



#### Adversarial attack susceptibility vs. measurement parameter

The table below indicates that in our study, we were unable to reproduce the attack susceptibilities reported in the original paper.

![](https://github.com/duanegoodner/ehr_adversarial_attack/blob/main/data/images/Table.png)



#### Adversarial attack susceptibility vs measurement time

These below plots also do NOT show the increase in susceptibility at later measurement times that were reported in the original paper.

![](https://github.com/duanegoodner/ehr_adversarial_attack/blob/main/data/images/plots.png)



## Original Paper Code Repository

Although  the code repository for [[Sun, 2018](https://dl.acm.org/doi/10.1145/3219819.3219909)] was not published, some of the authors reported on predictive modeling (but not adversarial attack) with a similar LSTM in:

[Tang, F., Xiao, C., Wang, F. and Zhou, J., 2018. Predictive modeling in urgent care: a comparative study of machine learning approaches. *Jamia Open*, *1*(1), (pp.87-98)](https://academic.oup.com/jamiaopen/article/1/1/87/5032901)

The repository for this paper is available at: https://github.com/illidanlab/urgent-care-comparative



# References

1. [Sun, M., Tang, F., Yi, J., Wang, F. and Zhou, J., 2018, July. Identify susceptible locations in medical records via adversarial attacks on deep predictive models. In *Proceedings of the 24th ACM SIGKDD international conference on knowledge discovery & data mining* (pp. 793-801).](https://dl.acm.org/doi/10.1145/3219819.3219909)
2. [Johnson, A., Pollard, T., and Mark, R. (2016) 'MIMIC-III Clinical Database' (version 1.4), *PhysioNet*.](https://doi.org/10.13026/C2XW26) 
3. [Johnson, A. E. W., Pollard, T. J., Shen, L., Lehman, L. H., Feng, M., Ghassemi, M., Moody, B., Szolovits, P., Celi, L. A., & Mark, R. G. (2016). MIMIC-III, a freely accessible critical care database. Scientific Data, 3, 160035.](https://www.nature.com/articles/sdata201635)

4. [Tang, F., Xiao, C., Wang, F. and Zhou, J., 2018. Predictive modeling in urgent care: a comparative study of machine learning approaches. *Jamia Open*, *1*(1), pp.87-98.](https://academic.oup.com/jamiaopen/article/1/1/87/5032901)



