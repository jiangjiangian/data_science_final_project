# ============================================================================
# File   : R/load_rebas_data.R
# Purpose: R mirror of scripts/step1_build_raw_games.py. Loads rebas
#          v0.1.0-2024 OpenData/Challenge/TaiwanSeries JSONs, re-aggregates
#          batterBox SEPARATELY for home and away, normalises stadium 11->8,
#          outputs data/processed/raw_games.csv.
#
# 用法 (RStudio / Colab 本機):
#   1. 把三個 zip 解到 data/raw/rebas_v0.1.0-2024/ 底下
#   2. source("R/load_rebas_data.R")
# ============================================================================

suppressPackageStartupMessages({
  library(jsonlite)
  library(dplyr)
  library(tidyr)
  library(purrr)
  library(readr)
  library(lubridate)
  library(here)
  library(digest)
})

# ---- config ----------------------------------------------------------------
SOURCES <- list(
  regular   = here::here("data/raw/rebas_v0.1.0-2024/CPBL-2024-OpenData/CPBL-2024-OpenData.json"),
  challenge = here::here("data/raw/rebas_v0.1.0-2024/CPBL-2024-Challenge-OpenData/CPBL-2024-Challenge-OpenData.json"),
  series    = here::here("data/raw/rebas_v0.1.0-2024/CPBL-2024-TaiwanSeries-OpenData/CPBL-2024-TaiwanSeries-OpenData.json")
)

STADIUM_MAP <- c(
  "樂天桃園棒球場"     = "樂天桃園",
  "臺中市洲際棒球場"   = "洲際",
  "臺北市立天母棒球場" = "天母",
  "新北市立新莊棒球場" = "新莊",
  "澄清湖棒球場"       = "澄清湖",
  "臺南市立棒球場"     = "臺南",
  "臺北大巨蛋"         = "大巨蛋",
  "嘉義市立棒球場"     = "其他",
  "花蓮縣立德興棒球場" = "其他",
  "臺東棒球村第一棒球場" = "其他",
  "斗六棒球場"         = "其他"
)
INDOOR_STADIUMS <- c("大巨蛋")
BATTER_KEYS <- c("PA","AB","R","H","RBI","2B","3B","HR","BB","IBB","HBP","SO","SH","SF","GIDP","SB","CS","E")

sum_innings <- function(arr) {
  if (length(arr) == 0) return(0L)
  vals <- suppressWarnings(as.integer(arr))
  sum(vals[!is.na(vals)])
}

aggregate_box <- function(box, prefix) {
  out <- setNames(rep(0L, length(BATTER_KEYS)), paste0(prefix, "_", BATTER_KEYS))
  if (length(box) == 0) return(out)
  for (b in box) {
    for (k in BATTER_KEYS) {
      v <- b[[k]]
      if (!is.null(v) && !is.na(suppressWarnings(as.integer(v)))) {
        out[paste0(prefix, "_", k)] <- out[paste0(prefix, "_", k)] +
          suppressWarnings(as.integer(v))
      }
    }
  }
  out
}

make_game_id <- function(game, game_type, seq_in_source) {
  d <- substr(game$date %||% "", 1, 10)
  d <- gsub("-", "", d)
  sprintf("%s-%s-%03d", d, toupper(substr(game_type, 1, 3)), seq_in_source)
}

`%||%` <- function(a, b) if (is.null(a) || length(a) == 0) b else a

# ---- main loop -------------------------------------------------------------
rows <- list()
for (gt in names(SOURCES)) {
  path <- SOURCES[[gt]]
  if (!file.exists(path)) {
    warning(sprintf("missing file: %s", path)); next
  }
  data <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  message(sprintf("%s: %d games", gt, length(data)))
  for (i in seq_along(data)) {
    g <- data[[i]]
    home_scores <- g$homeScores %||% list()
    away_scores <- g$awayScores %||% list()
    h_tot <- sum_innings(unlist(home_scores))
    a_tot <- sum_innings(unlist(away_scores))
    home_box <- g$homeBatterBox %||% list()
    away_box <- g$awayBatterBox %||% list()

    stadium_norm <- STADIUM_MAP[g$stadium %||% ""]
    if (is.na(stadium_norm)) stadium_norm <- "其他"

    row <- list(
      game_id        = make_game_id(g, gt, i),
      game_type      = gt,
      season         = g$season %||% NA,
      seasonId       = g$seasonId %||% NA,
      seq            = g$seq %||% NA,
      datetime       = g$date %||% NA,
      stadium_raw    = g$stadium %||% NA,
      stadium        = unname(stadium_norm),
      is_indoor      = as.integer(stadium_norm %in% INDOOR_STADIUMS),
      home_team      = g$homeTeam %||% NA,
      away_team      = g$awayTeam %||% NA,
      home_team_id   = g$homeTeamId %||% NA,
      away_team_id   = g$awayTeamId %||% NA,
      home_innings_played = length(home_scores),
      away_innings_played = length(away_scores),
      home_score = h_tot,
      away_score = a_tot,
      total_score = h_tot + a_tot,
      is_home_win = as.integer(h_tot > a_tot),
      is_tie      = as.integer(h_tot == a_tot),
      n_home_batters = length(home_box),
      n_away_batters = length(away_box)
    )
    row <- c(row, as.list(aggregate_box(home_box, "home")))
    row <- c(row, as.list(aggregate_box(away_box, "away")))
    rows[[length(rows) + 1]] <- row
  }
}

df <- dplyr::bind_rows(rows) |>
  dplyr::mutate(date = lubridate::ymd_hms(datetime, tz = "Asia/Taipei", quiet = TRUE)) |>
  dplyr::arrange(date, game_id)

# drop ties
ties <- sum(df$is_tie)
df <- df |> dplyr::filter(is_tie == 0) |> dplyr::select(-is_tie)
message(sprintf("ties dropped: %d  -> remaining %d games", ties, nrow(df)))
message(sprintf("home_win rate: %.3f", mean(df$is_home_win)))
print(table(df$stadium))

out_path <- here::here("data/processed/raw_games.csv")
dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)
readr::write_csv(df, out_path)
message(sprintf("written: %s", out_path))
