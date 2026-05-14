# ============================================================================
# File   : scripts/03_build_models.R
# Purpose: Entry-point R production pipeline that mirrors
#          scripts/step3_models.py. Builds m1..m7 ablation with
#          {tidymodels} when available, otherwise falls back to glm/glmnet/
#          xgboost/ranger directly.
#
# 用法 (Colab / RStudio):
#   source("R/load_rebas_data.R")     # builds data/processed/raw_games.csv
#   source("R/compute_features.R")    # builds data/processed/model_ready_data.csv
#   source("scripts/03_build_models.R")
# ============================================================================

suppressPackageStartupMessages({
  library(dplyr); library(readr); library(here); library(lubridate)
  library(glmnet); library(ranger)
  if (requireNamespace("xgboost", quietly = TRUE)) library(xgboost)
  if (requireNamespace("yardstick", quietly = TRUE)) library(yardstick)
})

if (!requireNamespace("tidymodels", quietly = TRUE)) {
  message("tidymodels not installed — using direct-engine fallback.")
}

# ---- load ------------------------------------------------------------------
df <- readr::read_csv(here::here("data/processed/model_ready_data.csv"),
                      show_col_types = FALSE) |>
  dplyr::filter(features_complete == 1) |>
  dplyr::mutate(
    is_home_win = factor(is_home_win, levels = c(0, 1)),
    stadium     = factor(stadium)
  )

# ---- time-aware split ------------------------------------------------------
train <- df |> dplyr::filter(date <  as.Date("2024-08-01"))
valid <- df |> dplyr::filter(date >= as.Date("2024-08-01") &
                              date <  as.Date("2024-09-16"))
test  <- df |> dplyr::filter(date >= as.Date("2024-09-16"))
message(sprintf("train=%d  valid=%d  test=%d",
                nrow(train), nrow(valid), nrow(test)))

TARGET <- "is_home_win"
FEATURES_M7 <- c(
  "stadium",
  "diff_elo", "diff_pythag", "diff_rest", "pf_pre",
  "diff_OPS_30g", "diff_HR_per_g_30g", "diff_K_pct_30g",
  "diff_BB_pct_30g", "diff_runs_per_g_30g", "diff_at_stadium_OPS"
)
# weather: append c("temperature", "humidity", "wind_speed") if available
weather_avail <- all(c("temperature", "humidity", "wind_speed") %in% names(df))
if (weather_avail) {
  FEATURES_M7 <- c(FEATURES_M7, "temperature", "humidity", "wind_speed")
}

# ---- helper: prepare X matrix ---------------------------------------------
make_matrix <- function(d, feats) {
  d <- d[, c(feats, TARGET), drop = FALSE]
  num <- feats[!sapply(d[feats], is.factor)]
  cat <- feats[ sapply(d[feats], is.factor)]
  # one-hot encode cats
  if (length(cat)) {
    mm <- model.matrix(~ . - 1, data = d[, cat, drop = FALSE])
    X <- cbind(as.matrix(d[, num, drop = FALSE]), mm)
  } else {
    X <- as.matrix(d[, num, drop = FALSE])
  }
  list(X = X, y = as.integer(as.character(d[[TARGET]])))
}

# ---- ablation m1..m7 with glm/glmnet --------------------------------------
groups <- list(
  m1 = character(),
  m2 = c("stadium"),
  m3 = if (weather_avail) c("temperature", "humidity", "wind_speed") else character(),
  m4 = c("stadium", if (weather_avail) c("temperature","humidity","wind_speed")),
  m5 = c("stadium", "diff_elo", "diff_pythag", "diff_rest", "pf_pre"),
  m6 = c("stadium", "diff_elo", "diff_pythag", "diff_rest", "pf_pre",
         "diff_OPS_30g", "diff_HR_per_g_30g", "diff_K_pct_30g",
         "diff_BB_pct_30g", "diff_runs_per_g_30g", "diff_at_stadium_OPS"),
  m7 = FEATURES_M7
)

evaluate <- function(y, p) {
  pred <- as.integer(p >= 0.5)
  list(
    accuracy = mean(pred == y),
    auc      = if (length(unique(y)) > 1)
      yardstick::roc_auc_vec(factor(y, levels = c(0,1)), p, event_level = "second")
      else NA_real_,
    brier    = mean((p - y) ^ 2),
    n        = length(y)
  )
}

trainval <- bind_rows(train, valid)
ablation <- list()
for (mname in names(groups)) {
  feats <- groups[[mname]]
  if (length(feats) == 0) {
    p_const <- mean(as.integer(as.character(trainval[[TARGET]])))
    res <- evaluate(as.integer(as.character(test[[TARGET]])),
                    rep(p_const, nrow(test)))
  } else {
    fm <- as.formula(paste(TARGET, "~", paste(feats, collapse = " + ")))
    fit <- glm(fm, family = binomial(), data = trainval)
    p <- predict(fit, newdata = test, type = "response")
    res <- evaluate(as.integer(as.character(test[[TARGET]])), p)
  }
  ablation[[mname]] <- c(model = mname, res)
  message(sprintf("  %-3s  n_feats=%2d  AUC=%.3f  acc=%.3f  brier=%.3f",
                  mname, length(feats), res$auc, res$accuracy, res$brier))
}
ablation_df <- bind_rows(lapply(ablation, as_tibble))
readr::write_csv(ablation_df, here::here("Results/eval/results_ablation_R.csv"))

# ---- algorithm comparison on m7 -------------------------------------------
xy_train <- make_matrix(trainval, FEATURES_M7)
xy_test  <- make_matrix(test, FEATURES_M7)

# 1. glmnet (elastic-net)
cvg <- glmnet::cv.glmnet(xy_train$X, xy_train$y, family = "binomial", alpha = 0.5)
p_glm <- as.numeric(predict(cvg, newx = xy_test$X, s = "lambda.min", type = "response"))
e_glm <- evaluate(xy_test$y, p_glm)

# 2. random forest
rf <- ranger::ranger(
  dependent.variable.name = TARGET,
  data = trainval[, c(TARGET, FEATURES_M7)] |>
    dplyr::mutate(dplyr::across(dplyr::where(is.character), as.factor)),
  num.trees = 400, max.depth = 6, min.node.size = 5,
  probability = TRUE, seed = 42
)
p_rf <- predict(rf, data = test[, c(TARGET, FEATURES_M7)] |>
                  mutate(across(where(is.character), as.factor)))$predictions[, "1"]
e_rf <- evaluate(as.integer(as.character(test[[TARGET]])), p_rf)

# 3. xgboost (if available)
e_xgb <- list(auc = NA_real_)
if (requireNamespace("xgboost", quietly = TRUE)) {
  dtr <- xgboost::xgb.DMatrix(xy_train$X, label = xy_train$y)
  dte <- xgboost::xgb.DMatrix(xy_test$X, label = xy_test$y)
  xb <- xgboost::xgb.train(
    params = list(objective = "binary:logistic",
                  eval_metric = "logloss",
                  max_depth = 3, eta = 0.05,
                  subsample = 0.8, colsample_bytree = 0.8,
                  reg_alpha = 0.1, reg_lambda = 1),
    data = dtr, nrounds = 400, verbose = 0
  )
  p_xb <- predict(xb, dte)
  e_xgb <- evaluate(xy_test$y, p_xb)
}

algo_df <- tibble::tibble(
  model = c("glmnet_elastic", "ranger_rf", "xgboost"),
  auc   = c(e_glm$auc, e_rf$auc, e_xgb$auc),
  acc   = c(e_glm$accuracy, e_rf$accuracy, e_xgb$accuracy %||% NA),
  brier = c(e_glm$brier, e_rf$brier, e_xgb$brier %||% NA)
)
print(algo_df)
readr::write_csv(algo_df, here::here("Results/eval/results_algos_R.csv"))

# ---- session info ----------------------------------------------------------
source(here::here("scripts/00_session_info.R"))
message("DONE — see Results/eval/results_ablation_R.csv & results_algos_R.csv")
