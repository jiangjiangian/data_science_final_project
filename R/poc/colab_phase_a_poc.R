# ============================================================================
# File   : R/poc/colab_phase_a_poc.R
# Purpose: Self-contained, Colab-runnable Phase A POC for the CPBL Home-Team
#          Win Prediction project (m1 - m7 ablation). Single file. No
#          here() / source() / logger dependencies. Writes outputs to the
#          current working directory (on Colab that is /content/ by default).
# Author : Sub-Agent 4 (model-builder), Colab port
# Date   : 2026-05-13
# ============================================================================
#
# ---------------------------------------------------------------------------
# Colab 使用步驟:
#   1. https://colab.research.google.com -> File -> New notebook
#   2. Runtime -> Change runtime type -> Runtime type = R
#   3. 把這整份 script 貼進一個 cell, 按執行 (Shift+Enter)
#      或上傳本檔後在 cell 跑:  source("colab_phase_a_poc.R")
#   4. 跑完後在左側檔案窗格下載:
#          poc_model_comparison.csv
#          poc_model_comparison.png
#
# ---------------------------------------------------------------------------
# 警告: 本 POC 使用 *合成* 資料 (synthetic). 任何分數均無實質意義,
#       只用來驗證 m1-m7 pipeline wiring. 真實 CPBL / CWA 資料接入是
#       Sub-Agent 2 (data-collector) 的工作.
# ============================================================================


# ---- 0. install + load packages -------------------------------------------
pkgs <- c(
  "dplyr", "tidyr", "tibble", "readr", "lubridate", "ggplot2",
  "rsample", "recipes", "parsnip", "workflows", "yardstick", "glmnet"
)

new_pkgs <- setdiff(pkgs, rownames(installed.packages()))
if (length(new_pkgs) > 0L) {
  message("Installing missing packages: ", paste(new_pkgs, collapse = ", "))
  install.packages(new_pkgs, repos = "https://cloud.r-project.org")
}

invisible(lapply(pkgs, function(p) {
  suppressPackageStartupMessages(library(p, character.only = TRUE))
}))

set.seed(42)


# ---- 1. config -------------------------------------------------------------
config <- list(
  n_games          = 400L,
  start_date       = as.Date("2023-04-01"),
  end_date         = as.Date("2023-09-30"),
  stadiums         = c("臺北大巨蛋", "樂天桃園",
                       "洲際", "台南", "新莊",
                       "澄清湖", "嘉義"),
  teams            = c("中信兄弟", "統一獅",
                       "樂天桃猿", "富邦悍將",
                       "味全龍", "台鋼雄鷹"),
  dome_stadiums    = c("臺北大巨蛋"),
  hfa_logit        = 0.16,
  elo_init         = 1500,
  elo_sigma        = 60,
  pythag_window    = 30L,
  pythag_exponent  = 1.83,
  rest_cap         = 5L,
  train_prop       = 0.8,
  glmnet_penalty   = 0.01,
  glmnet_mixture   = 0.5,
  out_csv          = file.path(getwd(), "poc_model_comparison.csv"),
  out_png          = file.path(getwd(), "poc_model_comparison.png")
)


# ---- 2. synthetic data generator ------------------------------------------
generate_synth <- function(n_games    = config$n_games,
                           start_date = config$start_date,
                           end_date   = config$end_date,
                           stadiums   = config$stadiums,
                           teams      = config$teams,
                           dome_set   = config$dome_stadiums) {

  all_dates <- seq.Date(start_date, end_date, by = "day")

  games <- tibble(
    game_idx = seq_len(n_games),
    date     = sort(sample(all_dates, n_games, replace = TRUE))
  ) |>
    mutate(
      stadium   = sample(stadiums, n(), replace = TRUE),
      home_team = sample(teams,    n(), replace = TRUE),
      away_team = sample(teams,    n(), replace = TRUE)
    ) |>
    filter(home_team != away_team) |>
    mutate(
      game_id = sprintf("%s-G%03d", format(date, "%Y%m%d"), seq_len(n())),
      season  = lubridate::year(date),
      is_dome = stadium %in% dome_set,
      temperature = round(rnorm(n(), 28, 3), 1),
      humidity    = pmin(100, pmax(30, round(rnorm(n(), 75, 10)))),
      wind_speed  = pmax(0, round(rnorm(n(), 2.5, 1.2), 2))
    )

  true_skill <- tibble(
    team = teams,
    true_rating = rnorm(length(teams), mean = config$elo_init,
                       sd = config$elo_sigma)
  )

  games |>
    left_join(true_skill, by = c("home_team" = "team")) |>
    rename(home_true = true_rating) |>
    left_join(true_skill, by = c("away_team" = "team")) |>
    rename(away_true = true_rating) |>
    mutate(
      rating_diff    = (home_true - away_true) / 400,
      weather_effect = -0.02 * (wind_speed - 2.5),
      logit_p_home   = config$hfa_logit + rating_diff + weather_effect,
      p_home         = 1 / (1 + exp(-logit_p_home)),
      home_score     = rpois(n(), lambda = 4 + 1.5 * p_home),
      away_score     = rpois(n(), lambda = 4 + 1.5 * (1 - p_home))
    ) |>
    filter(home_score != away_score) |>
    mutate(
      is_home_win = factor(
        if_else(home_score > away_score, "1", "0"),
        levels = c("0", "1")
      )
    ) |>
    select(
      game_id, date, season,
      stadium, home_team, away_team,
      home_score, away_score, is_home_win,
      is_dome, temperature, humidity, wind_speed
    )
}


# ---- 3. Elo / Pythag / rest_days ------------------------------------------
# 3a. Elo --------------------------------------------------------------------
compute_elo <- function(games,
                        k_factor    = 4,
                        hfa_elo     = 24,
                        mov_alpha   = 0.6,
                        mov_beta    = 2.2,
                        init_rating = 1500) {

  stopifnot(all(c("game_id", "date", "home_team", "away_team",
                  "home_score", "away_score") %in% names(games)))

  games <- games |> arrange(date, game_id)

  # 必須強制轉成 character. factor 拿來做 list[[]] 會被 R 內部強轉
  # integer (factor level), 在空 list 上就拋 "subscript out of bounds".
  home_chr <- as.character(games$home_team)
  away_chr <- as.character(games$away_team)

  ratings <- list()
  get_rating <- function(team) {
    team <- as.character(team)
    if (is.null(ratings[[team]])) init_rating else ratings[[team]]
  }

  n_rows    <- nrow(games)
  home_pre  <- numeric(n_rows)
  away_pre  <- numeric(n_rows)
  home_post <- numeric(n_rows)
  away_post <- numeric(n_rows)

  for (i in seq_len(n_rows)) {
    h_team <- home_chr[i]
    a_team <- away_chr[i]
    h_pre  <- get_rating(h_team)
    a_pre  <- get_rating(a_team)

    home_pre[i] <- h_pre
    away_pre[i] <- a_pre

    expected_home <- 1 / (1 + 10 ^ ((a_pre - (h_pre + hfa_elo)) / 400))
    h_score <- games$home_score[i]
    a_score <- games$away_score[i]

    if (is.na(h_score) || is.na(a_score) || h_score == a_score) {
      home_post[i] <- h_pre
      away_post[i] <- a_pre
      next
    }

    actual_home <- as.integer(h_score > a_score)
    diff_abs    <- abs(h_score - a_score)
    rating_diff_winner <- if (actual_home == 1L) {
      (h_pre + hfa_elo) - a_pre
    } else {
      a_pre - (h_pre + hfa_elo)
    }

    mov_mult <- log(diff_abs + 1) *
      (mov_beta / (rating_diff_winner * mov_alpha + mov_beta))
    mov_mult <- max(0.5, min(4, mov_mult))

    delta <- k_factor * mov_mult * (actual_home - expected_home)

    h_post <- h_pre + delta
    a_post <- a_pre - delta
    home_post[i] <- h_post
    away_post[i] <- a_post

    ratings[[h_team]] <- h_post
    ratings[[a_team]] <- a_post
  }

  games |>
    mutate(
      home_elo_pre  = home_pre,
      away_elo_pre  = away_pre,
      home_elo_post = home_post,
      away_elo_post = away_post
    )
}

# 3b. Pythagenpat rolling ---------------------------------------------------
compute_pythagenpat <- function(games,
                                window   = config$pythag_window,
                                exponent = config$pythag_exponent) {

  stopifnot(all(c("game_id", "date", "home_team", "away_team",
                  "home_score", "away_score") %in% names(games)))

  long <- games |>
    select(game_id, date, home_team, away_team, home_score, away_score) |>
    mutate(
      home_team = as.character(home_team),
      away_team = as.character(away_team)
    ) |>
    pivot_longer(
      cols      = c(home_team, away_team),
      names_to  = "side",
      values_to = "team"
    ) |>
    mutate(
      runs_scored  = if_else(side == "home_team", home_score, away_score),
      runs_allowed = if_else(side == "home_team", away_score, home_score),
      side         = if_else(side == "home_team", "home", "away")
    ) |>
    arrange(team, date, game_id) |>
    group_by(team) |>
    mutate(
      rs_lag = dplyr::lag(cumsum(runs_scored),  default = 0),
      ra_lag = dplyr::lag(cumsum(runs_allowed), default = 0),
      n_lag  = dplyr::lag(dplyr::row_number() - 1L, default = 0L),
      rs_win = rs_lag - dplyr::lag(cumsum(runs_scored),
                                   n = window, default = 0),
      ra_win = ra_lag - dplyr::lag(cumsum(runs_allowed),
                                   n = window, default = 0),
      pythag_pre = if_else(
        n_lag < 5L,
        NA_real_,
        (rs_win ^ exponent) / (rs_win ^ exponent + ra_win ^ exponent)
      )
    ) |>
    ungroup() |>
    select(game_id, side, pythag_pre)

  wide <- long |>
    pivot_wider(
      names_from  = side,
      values_from = pythag_pre,
      names_glue  = "{side}_pythag_30g"
    )

  games |> left_join(wide, by = "game_id")
}

# 3c. rest days -------------------------------------------------------------
compute_rest_days <- function(games, cap = config$rest_cap) {

  stopifnot(all(c("game_id", "date", "home_team", "away_team")
                %in% names(games)))

  long <- games |>
    select(game_id, date, home_team, away_team) |>
    mutate(
      home_team = as.character(home_team),
      away_team = as.character(away_team)
    ) |>
    pivot_longer(
      cols      = c(home_team, away_team),
      names_to  = "side",
      values_to = "team"
    ) |>
    mutate(side = if_else(side == "home_team", "home", "away")) |>
    arrange(team, date, game_id) |>
    group_by(team) |>
    mutate(
      rest_days = as.integer(date - dplyr::lag(date)),
      rest_days = pmin(rest_days, cap)
    ) |>
    ungroup() |>
    select(game_id, side, rest_days)

  wide <- long |>
    pivot_wider(
      names_from  = side,
      values_from = rest_days,
      names_glue  = "{side}_rest_days"
    )

  games |> left_join(wide, by = "game_id")
}

# 3d. one-shot wrapper ------------------------------------------------------
augment_team_strength <- function(games) {
  games |>
    compute_elo() |>
    compute_pythagenpat() |>
    compute_rest_days() |>
    mutate(
      elo_diff    = home_elo_pre    - away_elo_pre,
      pythag_diff = home_pythag_30g - away_pythag_30g,
      rest_diff   = home_rest_days  - away_rest_days
    )
}


# ---- 4. recipes (m2 ... m7) -----------------------------------------------
# 註: m1 (intercept-only) 在 Phase A 用「手動 constant prediction」實作,
#     避免 step_rm(all_predictors()) 在 glm 上 design matrix 為空的坑.

build_recipe_m2 <- function(train_df) {
  recipe(is_home_win ~ elo_diff + pythag_diff + rest_diff, data = train_df) |>
    step_impute_median(all_numeric_predictors()) |>
    step_zv(all_predictors()) |>
    step_normalize(all_numeric_predictors())
}

build_recipe_m3 <- function(train_df) {
  recipe(is_home_win ~ stadium, data = train_df) |>
    step_dummy(stadium, one_hot = FALSE) |>
    step_zv(all_predictors())
}

build_recipe_m4 <- function(train_df) {
  recipe(is_home_win ~ temperature + humidity + wind_speed,
         data = train_df) |>
    step_impute_median(all_numeric_predictors()) |>
    step_zv(all_predictors()) |>
    step_normalize(all_numeric_predictors())
}

build_recipe_m5 <- function(train_df) {
  recipe(is_home_win ~ elo_diff + pythag_diff + rest_diff + stadium,
         data = train_df) |>
    step_impute_median(all_numeric_predictors()) |>
    step_dummy(stadium, one_hot = FALSE) |>
    step_zv(all_predictors()) |>
    step_normalize(all_numeric_predictors())
}

build_recipe_m6 <- function(train_df) {
  recipe(
    is_home_win ~ elo_diff + pythag_diff + rest_diff +
      temperature + humidity + wind_speed,
    data = train_df
  ) |>
    step_impute_median(all_numeric_predictors()) |>
    step_zv(all_predictors()) |>
    step_normalize(all_numeric_predictors())
}

build_recipe_m7 <- function(train_df) {
  recipe(
    is_home_win ~ elo_diff + pythag_diff + rest_diff +
      stadium + temperature + humidity + wind_speed,
    data = train_df
  ) |>
    step_impute_median(all_numeric_predictors()) |>
    step_dummy(stadium, one_hot = FALSE) |>
    step_interact(terms = ~ wind_speed:starts_with("stadium_")) |>
    step_zv(all_predictors()) |>
    step_normalize(all_numeric_predictors())
}

build_recipes_m2_m7 <- function(train_df) {
  list(
    m2 = build_recipe_m2(train_df),
    m3 = build_recipe_m3(train_df),
    m4 = build_recipe_m4(train_df),
    m5 = build_recipe_m5(train_df),
    m6 = build_recipe_m6(train_df),
    m7 = build_recipe_m7(train_df)
  )
}


# ---- 5. scoring helper ----------------------------------------------------
# 給定一個 (truth, .pred_0, .pred_1, .pred_class) 的 tibble, 算 5 個 metric.
# event_level = "second" 因為 factor levels = c("0","1"),
# 第二個 level "1" 是 positive class.
score_preds <- function(model_id, engine_id, preds) {
  metric_multi <- metric_set(
    roc_auc, pr_auc, brier_class, accuracy, f_meas
  )

  metric_multi(
    preds,
    truth     = is_home_win,
    estimate  = .pred_class,
    .pred_1,
    event_level = "second"
  ) |>
    mutate(model = model_id, engine = engine_id) |>
    select(model, engine, .metric, .estimate)
}


# ---- 6. pipeline ----------------------------------------------------------
cat("\n=== Phase A POC (Colab) start ===\n")

# 6.1 generate + enrich -----------------------------------------------------
games <- generate_synth()
cat(sprintf("Generated %d synthetic games (after dropping ties)\n",
            nrow(games)))

enriched <- games |>
  augment_team_strength() |>
  mutate(
    stadium     = factor(stadium, levels = config$stadiums),
    home_team   = as.character(home_team),
    away_team   = as.character(away_team),
    is_home_win = factor(as.character(is_home_win), levels = c("0", "1"))
  ) |>
  filter(!is.na(is_home_win)) |>
  arrange(date, game_id)

model_frame <- enriched |>
  select(
    is_home_win, date,
    elo_diff, pythag_diff, rest_diff,
    stadium, temperature, humidity, wind_speed, is_dome
  )

cat(sprintf("Model frame: %d rows x %d cols\n",
            nrow(model_frame), ncol(model_frame)))
cat("Class balance:\n")
print(table(model_frame$is_home_win, useNA = "ifany"))

# 6.2 time-aware split -----------------------------------------------------
split    <- initial_time_split(model_frame, prop = config$train_prop)
train_df <- training(split)
test_df  <- testing(split)
cat(sprintf("Train: %d | Test: %d\n", nrow(train_df), nrow(test_df)))

# 6.3 m1: intercept-only baseline (手動實作) ------------------------------
p_home_train <- mean(as.character(train_df$is_home_win) == "1")
cat(sprintf("m1 baseline P(home_win) on train = %.4f\n", p_home_train))

preds_m1 <- tibble(
  is_home_win = test_df$is_home_win,
  .pred_0     = 1 - p_home_train,
  .pred_1     = p_home_train,
  .pred_class = factor(
    if_else(p_home_train >= 0.5, "1", "0"),
    levels = c("0", "1")
  )
)
scores_m1 <- score_preds("m1", "constant", preds_m1)

# 6.4 m2 ... m7 via workflows + glm ---------------------------------------
recipes_list <- build_recipes_m2_m7(train_df)
spec_glm <- logistic_reg() |>
  set_engine("glm") |>
  set_mode("classification")

fit_and_score <- function(m_id, rec, spec, engine_id) {
  wf <- workflow() |>
    add_recipe(rec) |>
    add_model(spec)

  fit_obj <- tryCatch(
    fit(wf, data = train_df),
    error = function(e) {
      message(sprintf("[%s/%s] fit failed: %s",
                      m_id, engine_id, conditionMessage(e)))
      NULL
    }
  )
  if (is.null(fit_obj)) return(NULL)

  preds <- bind_cols(
    test_df |> select(is_home_win),
    predict(fit_obj, new_data = test_df, type = "prob"),
    predict(fit_obj, new_data = test_df, type = "class")
  )
  scores <- score_preds(m_id, engine_id, preds)
  list(fit = fit_obj, scores = scores)
}

results <- list(m1_constant = list(fit = NULL, scores = scores_m1))

for (m_id in names(recipes_list)) {
  cat(sprintf("Fitting %s (glm)... ", m_id))
  res <- fit_and_score(m_id, recipes_list[[m_id]], spec_glm, "glm")
  if (!is.null(res)) {
    results[[paste0(m_id, "_glm")]] <- res
    cat("OK\n")
  } else {
    cat("SKIP\n")
  }
}

# 6.5 m7 加跑 glmnet ------------------------------------------------------
spec_glmnet <- logistic_reg(
  penalty = config$glmnet_penalty,
  mixture = config$glmnet_mixture
) |>
  set_engine("glmnet") |>
  set_mode("classification")

cat("Fitting m7 (glmnet)... ")
res_m7_net <- fit_and_score("m7", recipes_list[["m7"]], spec_glmnet, "glmnet")
if (!is.null(res_m7_net)) {
  results[["m7_glmnet"]] <- res_m7_net
  cat("OK\n")
} else {
  cat("SKIP\n")
}


# ---- 7. aggregate + output -----------------------------------------------
scores_long <- bind_rows(lapply(results, function(x) x$scores))

scores_wide <- scores_long |>
  pivot_wider(names_from = .metric, values_from = .estimate) |>
  arrange(desc(roc_auc))

cat("\n=== POC ranking (sorted by ROC-AUC desc) ===\n")
print(scores_wide)

write_csv(scores_wide, config$out_csv)
cat(sprintf("\nWrote %s\n", config$out_csv))


# ---- 8. plot --------------------------------------------------------------
plot_df <- scores_wide |>
  mutate(label = paste(model, engine, sep = "/"))

p <- ggplot(plot_df, aes(x = reorder(label, roc_auc), y = roc_auc)) +
  geom_col(fill = "#3a6ea5") +
  geom_text(aes(label = sprintf("%.3f", roc_auc)),
            hjust = -0.1, size = 3.4) +
  coord_flip() +
  ylim(0, max(plot_df$roc_auc) + 0.08) +
  labs(
    title    = "CPBL Phase A POC: ROC-AUC by model",
    subtitle = "Synthetic data; values are sanity-check only",
    x = NULL, y = "ROC-AUC (test fold)"
  ) +
  theme_minimal(base_size = 11)

ggsave(config$out_png, p, width = 7, height = 4.2, dpi = 150)
cat(sprintf("Wrote %s\n", config$out_png))

cat("\n=== Phase A POC (Colab) done ===\n")
invisible(scores_wide)
