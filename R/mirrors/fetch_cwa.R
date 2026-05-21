# ============================================================================
# File   : R/mirrors/fetch_cwa.R
# Purpose: Fetch hourly historical weather observations for each CPBL game and
#          join to data/processed/raw_games.csv -> games_with_weather.csv.
#
#          Primary source = Open-Meteo Archive API
#                           (https://open-meteo.com/en/docs/historical-weather-api)
#          - Free, NO API key, historical hourly back to 1940
#          - ERA5 reanalysis, ~10 km grid
#          - Returns temperature_2m, relative_humidity_2m, wind_speed_10m,
#            wind_direction_10m, precipitation
#
#          Why not direct CWA: opendata.cwa.gov.tw API is current-only,
#          CODiS historical CSV needs interactive session / CAPTCHA. Open-Meteo
#          uses ERA5 reanalysis which incorporates CWA station data anyway.
#
# 用法 (Colab / 本機 RStudio):
#   install.packages(c("httr2","jsonlite","dplyr","tidyr","readr",
#                      "lubridate","memoise","cachem","logger","here"))
#   source("R/mirrors/load_rebas_data.R")  # 先生成 data/processed/raw_games.csv
#   source("R/mirrors/fetch_cwa.R")         # 再跑這個
# ============================================================================

suppressPackageStartupMessages({
  library(httr2); library(jsonlite); library(dplyr); library(tidyr)
  library(readr); library(lubridate); library(memoise); library(cachem)
  library(logger); library(here); library(purrr); library(tibble)
})

CONFIG <- list(
  raw_games  = here::here("data/processed/raw_games.csv"),
  lookup     = here::here("data/raw/_lookup/stadium_to_station.csv"),
  out_path   = here::here("data/processed/games_with_weather.csv"),
  cache_dir  = here::here("data/raw/.cache_weather"),
  log_path   = here::here("logs/fetch_cwa.log"),
  api_url    = "https://archive-api.open-meteo.com/v1/archive",
  retry_n    = 3
)
dir.create(CONFIG$cache_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(dirname(CONFIG$log_path), recursive = TRUE, showWarnings = FALSE)
logger::log_appender(logger::appender_tee(CONFIG$log_path))

# ---- load games + lookup ---------------------------------------------------
games <- readr::read_csv(CONFIG$raw_games, show_col_types = FALSE) |>
  dplyr::mutate(
    game_dt = lubridate::ymd_hms(datetime, tz = "Asia/Taipei", quiet = TRUE),
    game_date = lubridate::as_date(game_dt)
  )

stadium_lookup <- readr::read_csv(CONFIG$lookup, show_col_types = FALSE)

# 1 row per (stadium_norm) — pick the FIRST mapping when multiple raw stadia
# share the same norm (e.g. 其他 has 4 sub-venues; we go with their own coords)
# So we actually want stadium_raw level for accurate lat/lon, then collapse later.
games <- games |>
  dplyr::left_join(
    stadium_lookup |>
      dplyr::select(stadium_raw, latitude, longitude),
    by = c("stadium_raw" = "stadium_raw")
  )

n_missing_geo <- sum(is.na(games$latitude))
if (n_missing_geo > 0) {
  warning(sprintf("%d games have no lat/lon — check stadium_to_station.csv",
                  n_missing_geo))
}

logger::log_info("games: {nrow(games)}, missing lat/lon: {n_missing_geo}")

# ---- distinct (lat, lon, date_range) we need fetching ----------------------
date_lo <- format(min(games$game_date, na.rm = TRUE), "%Y-%m-%d")
date_hi <- format(max(games$game_date, na.rm = TRUE), "%Y-%m-%d")
logger::log_info("date range: {date_lo} .. {date_hi}")

distinct_sites <- games |>
  dplyr::filter(!is.na(latitude)) |>
  dplyr::distinct(stadium_raw, latitude, longitude)
logger::log_info("distinct sites to query: {nrow(distinct_sites)}")

# ---- Open-Meteo fetcher with disk cache + retry ---------------------------
disk_cache <- cachem::cache_disk(CONFIG$cache_dir, max_size = 5e8)

fetch_openmeteo_raw <- function(lat, lon, start_date, end_date) {
  resp <- httr2::request(CONFIG$api_url) |>
    httr2::req_url_query(
      latitude  = lat,
      longitude = lon,
      start_date = start_date,
      end_date   = end_date,
      hourly = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation",
      timezone = "Asia/Taipei",
      wind_speed_unit = "ms"
    ) |>
    httr2::req_retry(max_tries = CONFIG$retry_n, backoff = ~ 2 ^ .x) |>
    httr2::req_timeout(60) |>
    httr2::req_perform()

  if (httr2::resp_status(resp) != 200) {
    stop(sprintf("Open-Meteo HTTP %d", httr2::resp_status(resp)))
  }
  body <- httr2::resp_body_json(resp)
  if (is.null(body$hourly)) return(tibble::tibble())
  h <- body$hourly
  tibble::tibble(
    obs_dt = lubridate::ymd_hm(unlist(h$time), tz = "Asia/Taipei"),
    temperature = unlist(h$temperature_2m),
    humidity    = unlist(h$relative_humidity_2m),
    wind_speed  = unlist(h$wind_speed_10m),
    wind_dir    = unlist(h$wind_direction_10m),
    precip      = unlist(h$precipitation)
  )
}
fetch_openmeteo <- memoise::memoise(fetch_openmeteo_raw, cache = disk_cache)

# ---- pull every site's full window ----------------------------------------
weather_long <- purrr::pmap_dfr(
  distinct_sites,
  function(stadium_raw, latitude, longitude) {
    logger::log_info("fetching {stadium_raw}  lat={latitude} lon={longitude}")
    df <- tryCatch(
      fetch_openmeteo(latitude, longitude, date_lo, date_hi),
      error = function(e) {
        logger::log_warn("fetch failed for {stadium_raw}: {conditionMessage(e)}")
        tibble::tibble()
      }
    )
    if (nrow(df) == 0) return(tibble::tibble())
    df |> dplyr::mutate(stadium_raw = stadium_raw,
                        latitude = latitude, longitude = longitude)
  }
)
logger::log_info("weather rows pulled: {nrow(weather_long)}")

# ---- join game-time hourly to each game -----------------------------------
games <- games |>
  dplyr::mutate(join_hour = lubridate::floor_date(game_dt, "hour"))

if (nrow(weather_long) == 0) {
  warning("Open-Meteo returned no data. Writing games with NA weather cols.")
  games_w <- games |>
    dplyr::mutate(
      temperature = NA_real_, humidity = NA_real_,
      wind_speed = NA_real_, wind_dir = NA_real_, precip = NA_real_
    )
} else {
  games_w <- games |>
    dplyr::left_join(
      weather_long |>
        dplyr::select(stadium_raw, obs_dt, temperature, humidity,
                      wind_speed, wind_dir, precip),
      by = c("stadium_raw" = "stadium_raw", "join_hour" = "obs_dt")
    )
}

# ---- compass binning + indoor flag ----------------------------------------
games_w <- games_w |>
  dplyr::mutate(
    is_indoor = ifelse(stadium == "大巨蛋", 1L, 0L),
    wind_dir_cat = cut(
      wind_dir,
      breaks = c(-1, 22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5, 361),
      labels = c("N","NE","E","SE","S","SW","W","NW","N")
    )
  )

miss_rate <- mean(is.na(games_w$temperature))
logger::log_info("weather join missing rate: {round(miss_rate, 4)}")
if (miss_rate > 0.10) {
  logger::log_warn(
    "More than 10% of games lack weather. Check timezone or coord lookup."
  )
}

readr::write_csv(games_w, CONFIG$out_path)
logger::log_info("wrote {CONFIG$out_path}  rows={nrow(games_w)} cols={ncol(games_w)}")

# ---- session info ----------------------------------------------------------
si_path <- here::here("Results/session_info_fetch_cwa.txt")
dir.create(dirname(si_path), showWarnings = FALSE, recursive = TRUE)
sink(si_path); print(sessionInfo()); sink()
cat("DONE — see ", CONFIG$out_path, "\n")
cat(sprintf("weather missing rate = %.3f\n", miss_rate))
cat(sprintf("first 3 rows of weather cols:\n"))
print(games_w[1:3, c("game_id", "stadium_raw", "join_hour",
                      "temperature", "humidity", "wind_speed", "wind_dir")])
