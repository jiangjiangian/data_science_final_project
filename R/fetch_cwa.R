# ============================================================================
# File   : R/fetch_cwa.R
# Purpose: Fetch CWA Open Data hourly station observations for CPBL 2024
#          game-times, join to data/processed/raw_games.csv, emit
#          data/processed/games_with_weather.csv.
#
# 用法 (本機, RStudio / Colab):
#   1. 取得 CWA Open Data API key (https://opendata.cwa.gov.tw/),
#      寫入 .Renviron:  CWA_API_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXX
#   2. 安裝 deps:
#      renv::install(c("httr2", "jsonlite", "dplyr", "tidyr", "readr",
#                      "lubridate", "memoise", "cachem", "logger", "here"))
#   3. 跑這個 script: Rscript R/fetch_cwa.R
#
# 端點:
#   1. CODiS (歷史觀測, 推薦)
#      https://e-service.cwa.gov.tw/HistoryDataQuery/MonthDataController.do
#      但需要 station_id + year_month 一筆一筆抓, 沒 API key 限制較鬆
#   2. Open Data API O-A0003-001 (僅供即時, 不適合歷史)
#   3. Open Data API C-B0024-002 (氣候統計, 月均值)
#
# 我們用 CODiS 的 monthly CSV 端點抓 station-month-day-hour, 然後 join 賽事
# game-time (rounded to nearest hour >= scheduled start).
# ============================================================================

suppressPackageStartupMessages({
  library(httr2)
  library(jsonlite)
  library(dplyr)
  library(tidyr)
  library(readr)
  library(lubridate)
  library(memoise)
  library(cachem)
  library(logger)
  library(here)
})

# ---- config ----------------------------------------------------------------
CONFIG <- list(
  api_key    = Sys.getenv("CWA_API_KEY", unset = ""),
  raw_games  = here::here("data", "processed", "raw_games.csv"),
  lookup     = here::here("data", "raw", "_lookup", "stadium_to_station.csv"),
  out_path   = here::here("data", "processed", "games_with_weather.csv"),
  cache_dir  = here::here("data", "raw", ".cache_cwa"),
  log_path   = here::here("logs", "fetch_cwa.log"),
  base_url   = "https://opendata.cwa.gov.tw/api/v1/rest/datastore",
  codis_url  = "https://e-service.cwa.gov.tw/HistoryDataQuery/downloads/MonthDataDownload.do",
  retry_n    = 3,
  jitter_sec = c(1, 3)
)

dir.create(CONFIG$cache_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(dirname(CONFIG$log_path), recursive = TRUE, showWarnings = FALSE)
logger::log_appender(logger::appender_tee(CONFIG$log_path))
logger::log_layout(logger::layout_glue_colors)

if (CONFIG$api_key == "") {
  logger::log_warn(
    "CWA_API_KEY not set. CODiS bulk-CSV path still works without an API key, ",
    "but the JSON-API path needs it. Set in .Renviron and restart R."
  )
}

stadium_lookup <- readr::read_csv(CONFIG$lookup, show_col_types = FALSE)
games <- readr::read_csv(CONFIG$raw_games, show_col_types = FALSE) |>
  dplyr::mutate(
    game_dt = lubridate::ymd_hms(datetime, tz = "Asia/Taipei", quiet = TRUE),
    game_date = lubridate::as_date(game_dt),
    game_hour = lubridate::hour(game_dt),
    year_month = format(game_date, "%Y-%m")
  )

logger::log_info("games loaded: {nrow(games)}, date range {min(games$game_date)} .. {max(games$game_date)}")

# ---- step 1: pick station per game (using stadium_norm) --------------------
games <- games |>
  dplyr::left_join(
    stadium_lookup |>
      dplyr::group_by(stadium_norm) |>
      dplyr::slice(1) |>
      dplyr::ungroup() |>
      dplyr::select(stadium_norm, station_id, station_name),
    by = c("stadium" = "stadium_norm")
  )

needed_pairs <- games |>
  dplyr::distinct(station_id, year_month) |>
  dplyr::filter(!is.na(station_id))

logger::log_info("distinct station-month pairs to fetch: {nrow(needed_pairs)}")

# ---- step 2: fetcher (with cache + retry) ----------------------------------
disk_cache <- cachem::cache_disk(CONFIG$cache_dir, max_size = 5e8)

# fetch_codis_month: pull a month's hourly CSV for one station from CWA CODiS
# return tibble(station_id, datetime, temperature, humidity, wind_speed, wind_dir)
fetch_codis_month_raw <- function(station_id, year_month) {
  # CODiS year/month format = 2024-04 -> ?stname=...&datepicker=2024-04
  # actual endpoint accepts param "stname" and "datepicker" and returns a CSV.
  # NB: this URL pattern may change. If CWA shuts it down, fall back to
  # opendata.cwa.gov.tw JSON API with CONFIG$api_key.
  url <- CONFIG$codis_url
  Sys.sleep(runif(1, CONFIG$jitter_sec[1], CONFIG$jitter_sec[2]))   # 禮貌
  req <- httr2::request(url) |>
    httr2::req_url_query(
      `command` = "viewMain",
      `station` = station_id,
      `stname`  = station_id,
      `datepicker` = year_month
    ) |>
    httr2::req_retry(max_tries = CONFIG$retry_n, backoff = ~ 2 ^ .x) |>
    httr2::req_timeout(60)
  resp <- tryCatch(httr2::req_perform(req), error = function(e) NULL)
  if (is.null(resp) || httr2::resp_status(resp) != 200) {
    logger::log_warn("CODiS fetch failed: station={station_id}, ym={year_month}")
    return(tibble::tibble())
  }
  body <- httr2::resp_body_string(resp, encoding = "UTF-8")
  # CODiS CSV starts with several preamble lines, then a header row.
  # Use suppressWarnings because skip count varies. If parse fails, give up.
  tryCatch({
    txt <- readr::read_lines(body)
    # find header line that contains "ObsTime"
    hdr_idx <- which(grepl("ObsTime|觀測時間", txt))[1]
    if (is.na(hdr_idx)) return(tibble::tibble())
    df <- readr::read_csv(
      I(paste(txt[hdr_idx:length(txt)], collapse = "\n")),
      show_col_types = FALSE, na = c("X", "...", "-", "")
    )
    df
  }, error = function(e) tibble::tibble())
}

fetch_codis_month <- memoise::memoise(fetch_codis_month_raw, cache = disk_cache)

# ---- step 3: walk every needed (station, ym) pair --------------------------
weather_long <- purrr::pmap_dfr(
  needed_pairs,
  function(station_id, year_month) {
    logger::log_info("fetching {station_id} / {year_month}")
    d <- fetch_codis_month(station_id, year_month)
    if (nrow(d) == 0) return(tibble::tibble())
    # rename to canonical names
    d |>
      dplyr::mutate(
        station_id = station_id,
        year_month = year_month
      )
  }
)

logger::log_info("weather rows collected: {nrow(weather_long)}")

# ---- step 4: join game-time hourly to each game ----------------------------
# canonical column normalization (CODiS Chinese header -> our names)
rename_map <- c(
  "ObsTime"     = "obs_dt",
  "觀測時間(LST)" = "obs_dt",
  "Temperature" = "temperature",
  "氣溫(℃)"     = "temperature",
  "RH"          = "humidity",
  "相對溼度(%)" = "humidity",
  "WS"          = "wind_speed",
  "風速(m/s)"   = "wind_speed",
  "WD"          = "wind_dir",
  "風向(360degree)" = "wind_dir",
  "Precp"       = "precip",
  "降水量(mm)"  = "precip"
)
if (nrow(weather_long) > 0) {
  weather_long <- weather_long |>
    dplyr::rename_with(.fn = ~ ifelse(.x %in% names(rename_map), rename_map[.x], .x))

  if (!"obs_dt" %in% names(weather_long)) {
    stop("Weather schema unexpected: no obs_dt column. Check CODiS endpoint.")
  }

  weather_long <- weather_long |>
    dplyr::mutate(
      obs_dt = lubridate::ymd_h(paste0(year_month, "-", obs_dt), tz = "Asia/Taipei",
                                truncated = 1, quiet = TRUE)
    )
}

# join via (station_id, hour bucket >= game start)
games_w <- games |>
  dplyr::mutate(join_hour = lubridate::floor_date(game_dt, "hour")) |>
  dplyr::left_join(
    weather_long |>
      dplyr::select(station_id, obs_dt, temperature, humidity, wind_speed, wind_dir),
    by = c("station_id" = "station_id", "join_hour" = "obs_dt")
  )

# ---- step 5: indoor games: keep weather as climate context, mark flag -----
games_w <- games_w |>
  dplyr::mutate(
    is_indoor = ifelse(stadium == "大巨蛋", 1L, 0L),
    # wind dir to 8-point compass
    wind_dir_cat = cut(
      wind_dir,
      breaks = c(-1, 22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5, 361),
      labels = c("N","NE","E","SE","S","SW","W","NW","N")
    )
  )

# ---- step 6: write out + report --------------------------------------------
miss_rate <- mean(is.na(games_w$temperature))
logger::log_info("weather join missing rate: {round(miss_rate, 3)}")
if (miss_rate > 0.20) {
  logger::log_warn(
    "More than 20% of games lack weather. ",
    "Either the CODiS endpoint failed, or stadium-station mapping is wrong. ",
    "Check logs/fetch_cwa.log and data/raw/.cache_cwa/."
  )
}

readr::write_csv(games_w, CONFIG$out_path)
logger::log_info("wrote {CONFIG$out_path}  ({nrow(games_w)} rows, {ncol(games_w)} cols)")

# ---- session info ----------------------------------------------------------
sink(here::here("Results", "session_info_fetch_cwa.txt"))
print(sessionInfo())
sink()
cat("DONE — see ", CONFIG$out_path, "\n")
