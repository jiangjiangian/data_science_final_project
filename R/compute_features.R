# ============================================================================
# File   : R/compute_features.R
# Purpose: R mirror of scripts/step2_features.py. Takes
#          data/processed/raw_games.csv (output of R/load_rebas_data.R), adds
#          - Elo (uses R/elo_pythag.R)
#          - Pythagenpat 30g (uses R/elo_pythag.R)
#          - rest_days (uses R/elo_pythag.R)
#          - team_OPS_30g + 8 other batter-state rolling features
#          - team_at_stadium_OPS_30g
#          - Park Factor (time-aware leave-one-out)
#          - diff features (home - away)
#          - day-of-week, month, is_weekend
#          and writes data/processed/model_ready_data.csv.
#
# 用法 (RStudio / Colab):
#   source("R/load_rebas_data.R")   # 先建 raw_games.csv
#   source("R/compute_features.R")  # 然後跑特徵工程
# ============================================================================

suppressPackageStartupMessages({
  library(dplyr); library(tidyr); library(purrr); library(readr); library(here)
  library(lubridate); library(slider)
})

source(here::here("R/elo_pythag.R"))

ROLL_WINDOW <- 30L

# ---- load ------------------------------------------------------------------
raw <- readr::read_csv(here::here("data/processed/raw_games.csv"),
                       show_col_types = FALSE) |>
  dplyr::mutate(date = lubridate::as_datetime(date, tz = "Asia/Taipei"))

# ---- 1. team-strength bundle (Elo / Pythag / rest) -------------------------
df <- augment_team_strength(raw)
df <- df |>
  dplyr::mutate(
    diff_elo = home_elo_pre - away_elo_pre,
    diff_pythag = home_pythag_30g - away_pythag_30g
  ) |>
  dplyr::mutate(
    home_rest_days = ifelse(is.na(home_rest_days),
                            median(home_rest_days, na.rm = TRUE), home_rest_days),
    away_rest_days = ifelse(is.na(away_rest_days),
                            median(away_rest_days, na.rm = TRUE), away_rest_days),
    diff_rest = home_rest_days - away_rest_days
  )

# ---- 2. helper: per-team rolling batter-state ------------------------------
make_long_team_game <- function(df) {
  bind_rows(
    df |> transmute(game_id, date, side = "home", team = home_team, stadium,
                    PA = home_PA, AB = home_AB, H = home_H, HR = home_HR,
                    `2B` = home_2B, `3B` = home_3B, BB = home_BB,
                    HBP = home_HBP, SF = home_SF, SO = home_SO,
                    rs = home_score, ra = away_score),
    df |> transmute(game_id, date, side = "away", team = away_team, stadium,
                    PA = away_PA, AB = away_AB, H = away_H, HR = away_HR,
                    `2B` = away_2B, `3B` = away_3B, BB = away_BB,
                    HBP = away_HBP, SF = away_SF, SO = away_SO,
                    rs = away_score, ra = home_score)
  )
}

L <- make_long_team_game(df) |>
  arrange(team, date, game_id)

compute_team_ops <- function(prev) {
  S <- colSums(prev[, c("PA","AB","H","HR","2B","3B","BB","HBP","SF","SO","rs")],
               na.rm = TRUE)
  S1B <- S["H"] - S["2B"] - S["3B"] - S["HR"]
  if (S["AB"] == 0 || S["PA"] == 0) {
    return(c(AVG = NA, OBP = NA, SLG = NA, OPS = NA, ISO = NA,
             K_pct = NA, BB_pct = NA, HR_per_g = NA, runs_per_g = NA))
  }
  obp_den <- S["AB"] + S["BB"] + S["HBP"] + S["SF"]
  avg <- S["H"] / S["AB"]
  obp <- (S["H"] + S["BB"] + S["HBP"]) / obp_den
  slg <- (S1B + 2 * S["2B"] + 3 * S["3B"] + 4 * S["HR"]) / S["AB"]
  c(AVG = avg, OBP = obp, SLG = slg, OPS = obp + slg, ISO = slg - avg,
    K_pct = S["SO"] / S["PA"], BB_pct = S["BB"] / S["PA"],
    HR_per_g = S["HR"] / nrow(prev), runs_per_g = S["rs"] / nrow(prev))
}

# slider's slide_index_dbl is per-row, slide whole prev window
roll_feats <- L |>
  group_by(team) |>
  arrange(date, game_id, .by_group = TRUE) |>
  mutate(
    AVG_30g = slider::slide_index_dbl(
      .x = row_number(), .i = date, .f = function(i_window) {
        idx <- i_window; this_i <- max(idx); prev_i <- idx[idx < this_i]
        if (length(prev_i) < 5) NA_real_ else
          compute_team_ops(cur_data()[prev_i, ])[["AVG"]]
      }, .before = Inf, .complete = FALSE)
  )

# NB: slider per-call building is slow on 366 rows. For simplicity in
# production keep using R/elo_pythag.R approach with lag(cumsum), here we
# fall back to a manual loop which is more readable + within bench budget.

# manual: walk through, for each row compute rolling 30 games of THIS team
feat_cols <- c("AVG","OBP","SLG","OPS","ISO","K_pct","BB_pct","HR_per_g","runs_per_g")

L$gi <- seq_len(nrow(L))
team_groups <- split(L, L$team)
all_rows <- list()
for (team in names(team_groups)) {
  g <- team_groups[[team]]
  g <- g[order(g$date, g$game_id), ]
  for (i in seq_len(nrow(g))) {
    s <- max(1L, i - ROLL_WINDOW)
    prev <- g[s:(i - 1), , drop = FALSE]
    if (i == 1 || nrow(prev) < 5) {
      feats <- rep(NA_real_, length(feat_cols)); names(feats) <- feat_cols
    } else {
      feats <- compute_team_ops(prev)
    }
    all_rows[[length(all_rows) + 1]] <- c(
      list(game_id = g$game_id[i], side = g$side[i]),
      as.list(feats)
    )
  }
}
F <- bind_rows(all_rows)
home_F <- F |> filter(side == "home") |> select(-side) |>
  rename_with(.cols = -game_id, .fn = ~ paste0("home_", .x, "_30g"))
away_F <- F |> filter(side == "away") |> select(-side) |>
  rename_with(.cols = -game_id, .fn = ~ paste0("away_", .x, "_30g"))

df <- df |> left_join(home_F, by = "game_id") |> left_join(away_F, by = "game_id")
for (c in feat_cols) {
  df[[paste0("diff_", c, "_30g")]] <- df[[paste0("home_", c, "_30g")]] -
                                       df[[paste0("away_", c, "_30g")]]
}

# ---- 3. team_at_stadium_OPS_30g --------------------------------------------
L2 <- L |> select(game_id, date, side, team, stadium,
                  PA, AB, H, HR, `2B`, `3B`, BB, HBP, SF) |>
  arrange(team, stadium, date, game_id)

stadium_rows <- list()
ts_groups <- split(L2, list(L2$team, L2$stadium), drop = TRUE)
for (key in names(ts_groups)) {
  g <- ts_groups[[key]]
  g <- g[order(g$date, g$game_id), ]
  for (i in seq_len(nrow(g))) {
    s <- max(1L, i - ROLL_WINDOW)
    prev <- g[s:(i - 1), , drop = FALSE]
    if (i == 1 || nrow(prev) < 3) { ops <- NA_real_ } else {
      S <- colSums(prev[, c("AB","H","2B","3B","HR","BB","HBP","SF")], na.rm = TRUE)
      S1B <- S["H"] - S["2B"] - S["3B"] - S["HR"]
      obp_den <- S["AB"] + S["BB"] + S["HBP"] + S["SF"]
      if (S["AB"] == 0 || obp_den == 0) ops <- NA_real_ else
        ops <- (S["H"] + S["BB"] + S["HBP"]) / obp_den +
               (S1B + 2 * S["2B"] + 3 * S["3B"] + 4 * S["HR"]) / S["AB"]
    }
    stadium_rows[[length(stadium_rows) + 1]] <- list(
      game_id = g$game_id[i], side = g$side[i], ops_at_stad = ops
    )
  }
}
ST <- bind_rows(stadium_rows)
df <- df |>
  left_join(ST |> filter(side == "home") |> select(-side) |>
              rename(home_at_stadium_OPS_30g = ops_at_stad), by = "game_id") |>
  left_join(ST |> filter(side == "away") |> select(-side) |>
              rename(away_at_stadium_OPS_30g = ops_at_stad), by = "game_id") |>
  mutate(diff_at_stadium_OPS = home_at_stadium_OPS_30g - away_at_stadium_OPS_30g)

# ---- 4. Park Factor (time-aware leave-one-out) -----------------------------
df <- df |> arrange(date, game_id) |> mutate(pf_pre = NA_real_)
for (i in seq_len(nrow(df))) {
  prev <- df[seq_len(i - 1), ]
  s <- df$stadium[i]
  same <- prev[prev$stadium == s, ]
  other <- prev[prev$stadium != s, ]
  if (nrow(same) < 5 || nrow(other) < 5) {
    df$pf_pre[i] <- 1.0
  } else {
    df$pf_pre[i] <- mean(same$total_score) / mean(other$total_score)
  }
}

# ---- 5. day-of-week / month -----------------------------------------------
df <- df |>
  mutate(dow = weekdays(as.Date(date)),
         month = lubridate::month(date),
         is_weekend = as.integer(dow %in% c("Saturday", "Sunday")))

# ---- 6. complete-features flag --------------------------------------------
roll_cols <- grep("_30g$", names(df), value = TRUE)
df$features_complete <- as.integer(
  rowSums(is.na(df[, roll_cols, drop = FALSE])) == 0L
)

# ---- write -----------------------------------------------------------------
out_path <- here::here("data/processed/model_ready_data.csv")
readr::write_csv(df, out_path)
message(sprintf("written: %s  rows=%d  cols=%d", out_path, nrow(df), ncol(df)))
message(sprintf("features_complete: %d / %d", sum(df$features_complete), nrow(df)))
