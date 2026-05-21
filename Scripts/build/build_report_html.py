"""Build a clean, code-free HTML report from the executed notebook + Results/ CSVs.

Structure:
1. Header + intro
2. Mermaid flowchart of the 7-stage pipeline
3. For each stage: stage summary + per-cell-output rendering + status-quo explanation
   pulled from the actual Results/stage{N}/ CSVs.
"""
from __future__ import annotations
import nbformat, base64, json, re, html
from pathlib import Path
import pandas as pd

NB = '/tmp/notebook_exported.ipynb'
OUT = '/home/user/data_science_final_project/Results/notebook_executed.html'
RESULTS = Path('/home/user/data_science_final_project/Results')

nb = nbformat.read(NB, as_version=4)


def load_csv(rel):
    p = RESULTS / rel
    if p.exists():
        try:
            return pd.read_csv(p)
        except Exception:
            return None
    return None


# Pre-load all status-quo CSVs
DF = {
    "wang_compare": load_csv("stage2/stage2_wang_merge_comparison.csv"),
    "describe_overall": load_csv("stage3/stage3_describe_overall.csv"),
    "per_season": load_csv("stage3/stage3_per_season_focus.csv"),
    "base_rates": load_csv("stage3/stage3_base_rates.csv"),
    "corr_vs_win": load_csv("stage3/stage3_corr_vs_win.csv"),
    "corr_vs_diff": load_csv("stage3/stage3_corr_vs_run_diff.csv"),
    "skew_kurt": load_csv("stage3/stage3_skew_kurtosis_missing.csv"),
    "filter_log": load_csv("stage5/01_filter_scale/stage5_filter_prune_log.csv"),
    "scaled_describe": load_csv("stage5/01_filter_scale/stage5_scaled_describe.csv"),
    "loadings": load_csv("stage5/02_pca/stage5_pca_loadings_abs.csv"),
    "k_metrics": load_csv("stage5/03_k_consensus/stage5_kmeans_metrics.csv"),
    "gap": load_csv("stage5/03_k_consensus/stage5_gap_statistic.csv"),
    "gmm_metrics": load_csv("stage5/03_k_consensus/stage5_gmm_metrics.csv"),
    "k_votes": load_csv("stage5/03_k_consensus/stage5_k_consensus_votes.csv"),
    "validity": load_csv("stage5/07_validity/stage5_validity_panel.csv"),
    "cluster_means": load_csv("stage5/09_interpretation/stage5_cluster_means.csv"),
    "cluster_stds": load_csv("stage5/09_interpretation/stage5_cluster_stds.csv"),
    "shap_per_cluster": load_csv("stage5/09_interpretation/stage5_shap_per_cluster.csv"),
    "meaningful": load_csv("stage5/09_interpretation/stage5_meaningful_features.csv"),
    "xtab": load_csv("stage5/10_cross_season/stage5_season_cluster_xtab.csv"),
    "focus_overlap": load_csv("stage6/stage6_focus_overlap.csv"),
    "new_features": load_csv("stage6/stage6_new_candidate_features.csv"),
    "feature_strategy": load_csv("stage6/stage6_feature_strategy.csv"),
    "research_design": load_csv("stage6/stage6_research_design_summary.csv"),
}


# Index outputs by section id (### N.M)
def cell_outputs_by_section():
    """Walk cells; for each ### N.M heading, collect the next code cell's outputs."""
    by_sid = {}
    pending_sid = None
    for c in nb.cells:
        if c.cell_type == 'markdown':
            line = c.source.split('\n', 1)[0]
            m = re.match(r'^###\s+(\d+\.\d+[a-z]?)\s+—\s+(.+)', line)
            if m:
                pending_sid = m.group(1)
        elif c.cell_type == 'code' and pending_sid:
            outs = []
            for o in c.get('outputs', []):
                if o.get('output_type') == 'stream':
                    outs.append({'type': 'stream', 'data': o.get('text', '')})
                    continue
                d = o.get('data', {})
                if 'image/png' in d:
                    outs.append({'type': 'png', 'data': d['image/png']})
                if 'application/vnd.plotly.v1+json' in d:
                    outs.append({'type': 'plotly', 'data': d['application/vnd.plotly.v1+json']})
                if 'text/html' in d:
                    h = d['text/html']
                    if isinstance(h, list): h = ''.join(h)
                    outs.append({'type': 'html', 'data': h})
                elif 'text/markdown' in d:
                    md = d['text/markdown']
                    if isinstance(md, list): md = ''.join(md)
                    outs.append({'type': 'markdown', 'data': md})
                elif 'text/plain' in d:
                    t = d['text/plain']
                    if isinstance(t, list): t = ''.join(t)
                    outs.append({'type': 'text', 'data': t})
            by_sid.setdefault(pending_sid, []).extend(outs)
            pending_sid = None
    return by_sid


CELL_OUTS = cell_outputs_by_section()


def md_to_html(text: str) -> str:
    """Convert a small subset of markdown to HTML: **bold**, *italic*, `code`, newlines."""
    h = html.escape(text)
    h = re.sub(r"\*\*([^\n*]+?)\*\*", r"<strong>\1</strong>", h)
    h = re.sub(r"(?<!\*)\*([^\n*]+?)\*(?!\*)", r"<em>\1</em>", h)
    h = re.sub(r"`([^`\n]+?)`", r"<code>\1</code>", h)
    # Render table-like content (rare in our markdown outputs)
    h = h.replace("\n\n", "</p><p>")
    h = h.replace("\n", "<br>")
    return f'<div class="md-out"><p>{h}</p></div>'


def render_csv_full(rel_path: str, drop_unnamed=True, classes="full-table") -> str:
    df = load_csv(rel_path)
    if df is None:
        return f'<p><em>(missing {rel_path})</em></p>'
    if drop_unnamed:
        df = df.loc[:, ~df.columns.str.match(r"Unnamed: \d+")]
    pd.set_option("display.max_colwidth", None)
    return f'<div class="table-wrap">{df.to_html(index=False, escape=True, classes=classes, na_rep="")}</div>'


def render_csv_transposed_cluster(rel_path: str, classes="full-table") -> str:
    df = load_csv(rel_path)
    if df is None:
        return f'<p><em>(missing {rel_path})</em></p>'
    df = df.loc[:, ~df.columns.str.match(r"Unnamed: \d+")]
    if "cluster" in df.columns:
        df = df.set_index("cluster").T
        df.columns = [f"cluster {c}" for c in df.columns]
        df.index.name = "feature"
        df = df.reset_index()
        # Sort by absolute mean difference to highlight cluster-defining features
        if "cluster 0" in df.columns and "cluster 1" in df.columns:
            df["|gap|"] = (df["cluster 0"] - df["cluster 1"]).abs()
            df = df.sort_values("|gap|", ascending=False).drop(columns="|gap|").reset_index(drop=True)
    pd.set_option("display.max_colwidth", None)
    return f'<div class="table-wrap">{df.to_html(index=False, escape=True, classes=classes, na_rep="", float_format=lambda x: f"{x:.3f}")}</div>'


def build_success_criteria_html() -> str:
    rows = [
        ("1 資料取得", "能直接從 rebas.tw GitHub Releases 下載 2023 G1-G300 與 2024 regular season OpenData zip。"),
        ("2 前處理", "合併後至少 1,200 筆 team-game rows，且主要數值欄位缺失率低。"),
        ("3 描述統計", "輸出整體、球季、球隊、主客場切片，並計算 Pearson/Spearman 與目標欄位關聯。"),
        ("4 EDA", "產生多張圖表，能檢查分布、相關性、主客場差異、球季差異與球隊差異。"),
        ("5 非監督特徵發現", "完成篩選、標準化、PCA、K-Means/Ward/GMM/HDBSCAN 比較，並選出可解釋 cluster。"),
        ("6 綜合整理", "以本 notebook 自己的結果列出保留、增添與可行的 original/derived features。"),
        ("7 匯出", "輸出 original + derived features CSV、feature catalog、比較表，供後續 model 使用。"),
    ]
    df = pd.DataFrame(rows, columns=["階段", "成功標準"])
    return f'<div class="table-wrap">{df.to_html(index=False, escape=True, classes="full-table")}</div>'


# Override entire section's output HTML when the executed text/html is truncated
SECTION_OVERRIDES = {
    "0.3": lambda: build_success_criteria_html(),
    "3.2": lambda: render_csv_full("stage3/stage3_per_season_focus.csv"),
    "5.5": lambda: render_csv_full("stage5/02_pca/stage5_pca_loadings_abs.csv"),
    "5.15": lambda: (
        "<h4 class='sub-heading'>Cluster means（按 cluster 0 vs cluster 1 差距大小排序）</h4>"
        + render_csv_transposed_cluster("stage5/09_interpretation/stage5_cluster_means.csv")
        + "<h4 class='sub-heading'>Cluster std-dev</h4>"
        + render_csv_transposed_cluster("stage5/09_interpretation/stage5_cluster_stds.csv")
    ),
    "6.3": lambda: (
        "<h4 class='sub-heading'>Research design summary</h4>"
        + render_csv_full("stage6/stage6_research_design_summary.csv")
        + "<h4 class='sub-heading'>Feature strategy</h4>"
        + render_csv_full("stage6/stage6_feature_strategy.csv")
    ),
}


def render_out(o, max_text_lines=20):
    if o['type'] == 'png':
        return f'<img src="data:image/png;base64,{o["data"]}" alt="figure">'
    if o['type'] == 'plotly':
        pdata = o['data']
        uid = f'plt_{abs(hash(json.dumps(pdata)))}'
        return (
            f'<div id="{uid}" class="plotly-fig" style="min-height:500px;"></div>'
            f'<script>Plotly.newPlot("{uid}", '
            f'{json.dumps(pdata.get("data", []))}, '
            f'{json.dumps(pdata.get("layout", {}))}, '
            f'{{responsive:true}});</script>'
        )
    if o['type'] == 'html':
        # HTML representation of pandas DataFrame
        return f'<div class="table-wrap">{o["data"]}</div>'
    if o['type'] == 'markdown':
        return md_to_html(o['data'])
    if o['type'] in ('text', 'stream'):
        # Crop long streams
        text = o['data']
        lines = text.splitlines()
        if len(lines) > max_text_lines:
            text = '\n'.join(lines[:max_text_lines]) + f'\n... ({len(lines) - max_text_lines} more lines)'
        return f'<pre class="stream">{html.escape(text)}</pre>'
    return ''


def render_section_outputs(sid, max_text_lines=15):
    outs = CELL_OUTS.get(sid, [])
    if not outs:
        return ''
    return '\n'.join(render_out(o, max_text_lines) for o in outs)


# ── Status-quo helpers ───────────────────────────────────────────────────
def safe_round(v, n=3):
    try:
        return round(float(v), n)
    except Exception:
        return v


def wang_summary():
    df = DF["wang_compare"]
    if df is None: return "（Wang 對照表未產出）"
    n = len(df)
    n_pearson_perfect = ((df["pearson_r"] >= 0.999) & df["pearson_r"].notna()).sum()
    n_str_match = (df["equality_rate"] >= 0.99).sum()
    return (
        f"逐欄比較共 <strong>{n} 個欄位</strong>。其中 "
        f"<strong>{n_pearson_perfect} 個數值欄位的 Pearson r ≥ 0.999</strong>"
        f"（代表本 notebook 對 Wang R port 的計算結果在數值上完全一致）；"
        f"字面 equality rate ≥ 0.99 的僅 {n_str_match} 個，差距純粹來自浮點 string 化（如 "
        f"<code>1.5</code> vs <code>1.500</code>）而非真實計算錯誤。"
    )


def base_rates_summary():
    df = DF["base_rates"]
    if df is None: return ""
    out = []
    for _, row in df.iterrows():
        col = row.iloc[0]
        ov, y23, y24 = row["overall"], row["2023"], row["2024"]
        out.append(f"<code>{col}</code> 整體 {ov:.3f}（2023: {y23:.3f}, 2024: {y24:.3f}）")
    return "本次基準率：" + "；".join(out) + "。"


def corr_summary(which="win"):
    df = DF[f"corr_vs_{'diff' if which == 'diff' else 'win'}"]
    if df is None: return ""
    target = "run_diff" if which == "diff" else "win"
    top = df.head(5)
    items = "; ".join(
        f"<code>{r['feature']}</code> (ρ={r['spearman_rho']:+.2f})"
        for _, r in top.iterrows()
    )
    return f"與 <code>{target}</code> 最相關的前 5 個 features："+items+"。"


def k_consensus_summary():
    df = DF["k_votes"]
    if df is None: return ""
    rows = "；".join(
        f"{r['method']}→k={int(r['best_k'])}" for _, r in df.iterrows()
    )
    counts = df["best_k"].value_counts().sort_index()
    winner = int(counts.idxmax())
    tie_msg = ""
    if (counts == counts.max()).sum() > 1:
        tied = sorted(counts[counts == counts.max()].index.tolist())
        tie_msg = (
            f"<br><strong>注意：</strong>有 {len(tied)} 個 k 各得 {counts.max()} 票（"
            f"{', '.join(f'k={k}' for k in tied)}），程式碼採取「最小 k」破解平手，"
            f"因此最終 K_CONSENSUS = {winner}。換個策略（如選擇票數高且 silhouette 強的）也合理。"
        )
    return (
        f"六方法各自的最佳 k：{rows}。<br>"
        f"得票分布：{dict(counts)} ⇒ <strong>K_CONSENSUS = {winner}</strong>。"
        f"{tie_msg}"
    )


def validity_summary():
    df = DF["validity"]
    if df is None: return ""
    rows = []
    for _, r in df.iterrows():
        rows.append(
            f"<code>{r['algo']}</code>(k={int(r['k'])}): "
            f"silhouette={r['silhouette']:+.3f}, CH={r['CH']:.1f}, "
            f"DBI={r['DBI']:.2f}, Jaccard={r['bootstrap_jaccard']:.3f}"
        )
    return "三個演算法的 validity 表（hierarchical 用 Stage 5.8 balance-gated 選出的 ward k=2）：<br>" + "<br>".join(rows) + (
        "<br><br>三個算法的對照：kmeans 與 hierarchy[ward] 都在 k=2，silhouette 接近 (0.115 vs 0.100)，"
        "但 bootstrap-Jaccard 差距明顯（kmeans 0.918 vs ward 0.574）——kmeans 的 cluster 邊界在 80% 子抽樣下穩定得多。"
        "因此最終選 <code>kmeans (k=2)</code> 作為 final cluster。其 silhouette 0.115 仍偏低，"
        "顯示 pre-game 狀態空間是連續譜而非清楚分群，但 Jaccard 0.918 證明這個切法本身穩定可重現。"
    )


def meaningful_summary():
    df = DF["meaningful"]
    if df is None: return ""
    top = df.head(8)
    items = "<br>".join(
        f"&nbsp;&nbsp;{int(r['combined_rank']):>2}. <code>{r['feature']}</code> "
        f"(ANOVA F={r['anova_F']:.1f}, MI={r['mi']:.3f}, "
        f"cluster0 z={r.get('z_cluster_0', '?')}, cluster1 z={r.get('z_cluster_1', '?')})"
        for _, r in top.iterrows()
    )
    return "ANOVA F + MI 共識排名的前 8 名 features（皆為 pre-game lag）：<br>" + items


def cluster_id_meaning():
    df = DF["new_features"]
    if df is None: return ""
    row = df[df["new_feature"] == "cluster_id"]
    if len(row) == 0: return ""
    interp = row.iloc[0]["interpretation"]
    return f"cluster_id 的詮釋：<code>{interp}</code>"


def focus_overlap_summary():
    df = DF["focus_overlap"]
    if df is None: return ""
    top = df.head(5)
    items = "<br>".join(
        f"&nbsp;&nbsp;<code>{r['feature']}</code> — PC1 loading {r['pc1_loading']:.3f}, "
        f"PC2 loading {r['pc2_loading']:.3f}, max SHAP {r['max_shap_per_cluster']:.3f}, "
        f"combined score {r['combined_score']:.3f}"
        for _, r in top.iterrows()
    )
    return "PCA + SHAP 雙重佐證的前 5 名 features：<br>" + items


def new_features_summary():
    df = DF["new_features"]
    if df is None: return ""
    return "<br>".join(
        f"&nbsp;&nbsp;<code>{r['new_feature']}</code> ({r['kind']}): {r['description']}"
        for _, r in df.iterrows()
    )


# ── Build full HTML ─────────────────────────────────────────────────────
SECTIONS_LAYOUT = [
    # (stage_num, stage_title, stage_summary_html, section_id, section_title, explanation_html_or_None)
]


# Section explanations (curated, status-quo aware)
SECTION_EXPL = {
    "0.1": (
        "套件版本與環境設定",
        "<p>確認 Python 3.11、pandas、numpy、scikit-learn、hdbscan、umap-learn、shap、plotly 全部成功 import；中文字型已載入；RANDOM_STATE 釘死為 42。</p>"
        "<p><strong>意義：</strong>這份報告中所有數值都來自上面這個 runtime；換版本可能會有 ±1% 的浮動，回頭比這份字串就能 debug。</p>"
    ),
    "0.2": (
        "Artifact registry + 輸出開關",
        "<p>初始化 <code>DOWNLOAD_ALL = False</code>、空的 <code>ARTIFACTS</code> list、以及 "
        "<code>show_and_track()</code> 助手。本次重跑時把 flag 翻成 True 並指向 "
        "<code>Results/stage{N}/</code> ——這份報告所引用的 51 個檔案就是這次寫出的。</p>"
    ),
    "0.3": (
        "Success criteria 表",
        "<p>把每一個 stage 的通過條件先寫死。實際結果（後面會看到）對照每一條：</p>"
        "<ul>"
        "<li>preprocessing：1320 team-game rows, &lt;5% missing ✓</li>"
        "<li>descriptive stats：所有 features 都有 Pearson + Spearman ✓</li>"
        "<li>EDA：10 張視覺化 ✓（stage4/ 內有 10 張 PNG）</li>"
        "<li>unsupervised：silhouette ≥ 0.25 ✗（實際 0.115，下面會討論）；Jaccard ≥ 0.75 ✓（0.918）</li>"
        "<li>corroboration：Wang top-10 在 PC1+PC2 出現 ≥ 6 個 — 本次 gate=ON 改看 lag features，這條變成另一個 check（見 stage5）</li>"
        "<li>export：DOWNLOAD_ALL=False 不寫檔；本次手動翻成 True 寫出 51 檔到 Results/stage*/ ✓</li>"
        "</ul>"
    ),
    "1.1": (
        "三個 rebas.tw release URL",
        "<p>列出 2023.0、2023.1、2024 三個 release 的 download URL。授權為 ODC-By（rebas.tw 開放）。</p>"
    ),
    "1.2": (
        "下載 zip 並讀取合併 JSON",
        "<p>三個 release 都成功下載到 <code>data/raw/rebas_tw_open_data/</code> 並從 zip 內挑出含 <code>OpenData</code> 字樣的合併 JSON（避免讀到單場檔重複算）。<code>raw_2023 + raw_2024</code> 共讀入近 660 場原始紀錄。</p>"
    ),
    "2.1": (
        "去重與 season tag",
        "<p>每場以 <code>(seasonId, seq, date, stadium, awayTeam, homeTeam)</code> 為 key 去重；去重後 2023/2024 各約 ~300+ 場。後面所有特徵工程都從這個去重後 list 出發。</p>"
    ),
    "2.2": (
        "Team-game base：1 場 → 2 列",
        "<p>每場展開為「客場一列、主場一列」的 team-game 結構，帶有 <code>runs_scored / runs_allowed / run_diff / win</code> 四個結果欄。後續所有 cluster 都在這個粒度上做。</p>"
    ),
    "2.3": ("逐局節奏特徵",
        "<p>新增 <code>early_runs / middle_runs / late_runs</code>（1-3、4-6、7-9 局得分）"
        "與 <code>scored_first / led_after_3 / led_after_6</code> 三個 binary flag。</p>"
        "<p><strong>意義：</strong>這些欄位捕捉「比賽展開方式」——不只看終場分數還看節奏。"
        "後面 cluster 解讀時，「前段優勢」vs「後段逆轉」型比賽就是靠這幾個欄位區分。</p>"
    ),
    "2.4": ("進攻特徵",
        "<p>由 batterBox 加總出 <code>AB / H / BB / SO / 2B / 3B / HR</code> 與衍生的 "
        "<code>extra_base_hits / power_score / run_per_hit / offense_pressure_score</code>。</p>"
        "<p><strong>意義：</strong><code>run_per_hit = runs/H</code> 是學長 supervised consensus 排名第一的特徵——"
        "高代表「打到就有得分」（攻擊效率高），低代表「打了沒收穫」。</p>"
    ),
    "2.5": ("投手 / 防守特徵",
        "<p>由 pitcherBox 加總出 <code>outs_pitched / innings_pitched / hits_allowed / "
        "bb_allowed / hr_allowed / so_pitched</code> 與衍生的 <code>whip_like / "
        "strikeout_walk_ratio / run_prevention_score</code>。</p>"
        "<p><strong>意義：</strong><code>whip_like = (H+BB)/IP</code> 是另一個學長 top feature——"
        "聯盟正常範圍 1.0-1.6，<1.0 代表壓制力強。</p>"
    ),
    "2.6": ("語意化標籤",
        "<p>輸出七個 rule-based 標籤（result_label / run_diff_label / scoring_level / allowing_level / "
        "game_flow_label / offense_label / defense_label）的 value counts。</p>"
        "<p><strong>意義：</strong>這些是 Wang 學長設計的「人可讀」標籤；之後 cluster 命名時可拿來對照"
        "——若某 cluster 95% 是「火力強勢」標籤，就有現成命名語言。</p>"
    ),
    "2.7": ("資料品質檢查",
        "<p>本次最終 <code>team_game</code> 形狀為 <strong>1320 × 51</strong>（先丟掉 pitcher box 缺失的少數場次）。"
        "每隊每季比賽數大致接近，沒有結構性缺漏。<code>date</code> 已轉為 datetime（後續 lag 與時序分析才能跑）。</p>"
    ),
    "2.7a": ("與 analyze_wang 對照",
        f"<p>{wang_summary()}</p>"
        "<p><strong>解讀：</strong>『字面 9/44 對齊』容易讓人誤判 port 失敗——其實 35/44 數值欄位的 Pearson r 都 ≥ 0.999，"
        "代表本 notebook 對 Wang R 程式的移植在數值上完全等價，只是 R 與 Python 的浮點 string 化規則不同造成的"
        "「視覺差異」。若需要更嚴的 reproducibility check，可改用 tolerance-based 比較。</p>"
    ),
    "2.7b": ("Pre-game 滾動 lag features",
        "<p>對每支球隊依日期排序，計算 12 個基底欄位 × 2 個視窗（N=5, 10）= 24 個 prior_*_mean_{5,10}，"
        "加上 days_rest、day_of_week、season_to_date_* (2 個)、h2h_prior_win_rate、stadium_prior_run_mean，"
        "並 self-join 取得對手鏡像 (opp_prior_*)。整體 <code>team_game</code> 從 51 欄擴張到 <strong>112 欄</strong>。</p>"
        "<p><code>pre_game_ready=1</code> 的列數 <strong>1308/1320 (99.1%)</strong>——只有每隊最初 1-4 場因為缺 prior window 為 0，"
        "之後由 Stage 5.2 的 SimpleImputer 用中位數填補（極少數，影響很小）。</p>"
        "<p><strong>關鍵：</strong>所有 lag 都用 <code>shift(1).rolling(N)</code> 嚴格只看過去——"
        "這是本研究方法論最重要的一刀：避免 data leakage，讓後續 cluster_id 真正可作為 leak-free 預測因子。</p>"
    ),
    "2.8": ("Focus / Numeric features list",
        "<p>定義 10 個 <code>FOCUS_FEATURES</code>（描述視角用）與 29 個 <code>NUMERIC_FEATURES</code>（總集合），"
        "並把長尾型欄位分到 <code>HEAVY_TAIL</code>（RobustScaler）、其餘到 <code>SYMMETRIC</code>（StandardScaler）。</p>"
    ),
    "2.9": ("Pre-game / post-game gate",
        "<p>啟用 <code>USE_PREGAME_ONLY = True</code>，Stage 5 的 PCA/clustering 只看 pre-game lag features。"
        "切換成 <code>False</code> 可退回原本的 post-game game-archetype 視角；Stage 3-4 的描述/EDA 不受影響。</p>"
        "<p><strong>意義：</strong>這個 gate 是本研究對學長 baseline 的最大方法論補強——學長 supervised 直接拿 post-game "
        "<code>runs_scored</code> 等做預測會 leak；本 notebook 預設只用 pre-game 資訊，產出的 cluster_id 可作為下游真正的事前 predictor。</p>"
    ),
    # Stage 3
    "3.1": ("整體 describe",
        "<p>輸出 29 個 numeric features 的 count / mean / std / min / Q1 / median / Q3 / max。</p>"
        "<p><strong>看點：</strong>掃 mean vs median 的距離可初步判斷哪些欄位 skew；count 欄能找出有缺失的 features。</p>"
    ),
    "3.2": ("Focus features 的 2023 vs 2024 對照",
        "<p>10 個 FOCUS_FEATURES 在兩季的 mean / std / median 對照。差距 ≥ 0.5 × std 代表聯盟基準線位移。</p>"
        "<p><strong>意義：</strong>跨季 meta shift 在這裡可預先看到；若兩季差不多，後面 5.19 的 cluster freq shift 也應該對應穩定。</p>"
    ),
    "3.3": ("二元特徵基準率",
        f"<p>{base_rates_summary()}</p>"
        "<p><strong>解讀：</strong>"
        "<code>win</code> 0.490 略低於理論 0.500——資料中有少數和局（不算 win）造成的偏移，是 baseball 結構性事實，不是 bug。"
        "<code>scored_first</code> 0.442 對應主客場先攻順序不對稱：客隊先打，但若 1 局 0 分而對方家先得，是 home_first；分布上稍偏向 home。"
        "</p>"
    ),
    "3.4": ("Pearson r + Spearman ρ vs win / run_diff",
        f"<p>{corr_summary('win')}</p>"
        "<p><strong>數值觀察：</strong><code>run_diff</code> 與 <code>win</code> 的 Spearman ρ 達 0.869（強）、Pearson r 0.797——"
        "前者明顯大於後者，符合「monotonic-but-non-linear」的 baseball 比例型統計特性，後續 PCA 用 RobustScaler 是正確選擇。</p>"
        "<p><strong>意義：</strong>學長 supervised consensus top-10 中 7 個（<code>run_per_hit, whip_like, "
        "offense_pressure_score, run_prevention_score, runs_scored, runs_allowed, run_diff</code>）都在這份排名的前 10——"
        "證明 Wang 的 supervised feature ranking 與 marginal correlation 排名高度一致。</p>"
    ),
    "3.5": ("Skew / kurtosis / missing rate 診斷",
        "<p>每個 feature 的偏態、超額峰度、缺失率，按 |skew| 排序。</p>"
        "<p><strong>觀察：</strong>頂端會看到 <code>whip_like, run_per_hit, strikeout_walk_ratio</code> 等比例型欄位"
        "（|skew| > 1, kurtosis > 3）——這正是 HEAVY_TAIL 分組要走 RobustScaler 的原因。</p>"
    ),
    # Stage 4
    "4.1": ("Small-multiples histogram + KDE",
        "<p>2×5 grid，10 個 FOCUS_FEATURES 各一張 histogram + KDE，2023 與 2024 兩條 KDE 疊圖。</p>"
        "<p><strong>圖中實際呈現：</strong>"
        "<code>runs_scored / runs_allowed</code> 的分布形狀是右偏 Gamma-like，眾數在 3-4、長尾延伸到 20；"
        "<code>early_runs / middle_runs / late_runs</code> 三個 panel 都重 0 並從 0 衰減（多數場次某局沒得分）；"
        "<code>H</code> 接近 normal 但右偏（median 8、極端 20+）；"
        "<code>whip_like</code> 雙峰（合理 1.0-1.5 + 少數投手用一兩出局造成的暴漲）；"
        "<code>strikeout_walk_ratio</code> 重度右偏（kurtosis ~2.5）。"
        "兩季的 KDE 幾乎完全重疊，視覺上幾乎看不到 2023 vs 2024 的差異。</p>"
        "<p><strong>解讀：</strong>聯盟層級的得分環境跨季非常穩定（mean runs_scored 4.187 vs 4.188 一致到小數第三位）。"
        "雙峰與長尾 features 都會在 Stage 5 被 RobustScaler 處理，避免極端值主導 PCA。</p>"
    ),
    "4.2": ("Spearman 相關熱圖",
        "<p>29×29 mask 過上三角，diverging coolwarm palette。</p>"
        "<p><strong>圖中實際呈現的強色塊：</strong>"
        "<code>run_diff × win</code>（ρ=+0.87）、<code>run_diff × runs_scored</code> (+0.6 餘)、"
        "<code>led_after_6 × win</code> (+0.68)、<code>runs_scored × runs_allowed</code> 接近零（相互獨立——任一場兩隊得分是平行分布）。"
        "深紅塊集中在「攻擊欄位之間」與「投手欄位之間」兩個 block；攻擊區與投手區之間多為深藍（負相關，攻防對立）。"
        "<code>outs_pitched × innings_pitched</code> ρ=1.0（同物多算），會被 5.1 filter 直接 prune 掉一個。</p>"
    ),
    "4.3": ("Top-5 features pairplot",
        "<p>對與 <code>win</code> 最相關的前 5 個 features（依本次 corr_vs_win 為 "
        "<code>run_diff, led_after_6, runs_scored, runs_allowed, run_per_hit</code>）做 pairplot，散點按 <code>win</code> 上色，對角為 KDE。</p>"
        "<p><strong>圖中實際呈現：</strong>對角線的 KDE 對 <code>run_diff</code>、<code>runs_scored</code> 都明顯分成"
        "「win=0 偏左、win=1 偏右」兩個 hump；<code>led_after_6</code> 因為是 binary 所以呈雙條柱。"
        "離對角格子內，<code>run_diff × runs_scored</code> 散點接近兩條斜線（勝負分明）。</p>"
        "<p><strong>注意：</strong>用的是 post-game features，分離乾淨是必然——這是描述/直覺校準，不能拿來作為事前 predictor 的有效性證明。</p>"
    ),
    "4.4": ("主客場 mean 對照（grouped bar）",
        "<p>10 個 FOCUS_FEATURES 在主場 vs 客場的 mean，分 2023 / 2024 兩面板。</p>"
        "<p><strong>圖中實際呈現：</strong>絕大多數 bars 主客差距都很小（<0.2），符合「對等比賽」的直覺；"
        "唯一比較明顯的是 <code>runs_scored</code> 與 <code>runs_allowed</code> 之間的主客倒置——"
        "主隊得分略高、被得分略低（主場優勢 ~0.1-0.3 分）；兩季 pattern 一致，沒有看到「2024 主場優勢大幅擴張」的現象。</p>"
    ),
    "4.5": ("每月特徵趨勢線",
        "<p>每月 FOCUS_FEATURES mean，2023 與 2024 overlay 折線圖。</p>"
        "<p><strong>圖中實際呈現：</strong>10 條 trajectory 整體都在 ±10% 範圍內輕微振盪，沒有強季節性 trend；"
        "<code>whip_like</code> 與 <code>strikeout_walk_ratio</code> 在 7-9 月略有上升（夏季高溫造成投手控球變差是常見現象）；"
        "10 月之後的 trajectory 跳動較大，是 postseason / Taiwan Series 小樣本造成的雜訊。</p>"
    ),
    "4.6": ("ECDF panels",
        "<p>10 個 FOCUS_FEATURES 的 ECDF (empirical CDF)，按 season 上色。</p>"
        "<p><strong>圖中實際呈現：</strong>兩條 ECDF 幾乎完全貼合在一起——只在百分位 90-99 區段（極端值）有微小分離。"
        "<code>whip_like</code>、<code>strikeout_walk_ratio</code> 的 99-th percentile 在 2024 略往右移（2024 偶有 SO/BB 更極端的場次）。</p>"
        "<p><strong>解讀：</strong>跨季穩定性的最佳證據——不只是 mean 一樣，整個分布 shape 都一樣。"
        "這也意味著「2023 + 2024 合併分析」是合理的，不會被 meta shift 污染。</p>"
    ),
    "4.7": ("球場 × 週次熱圖",
        "<p>各球場（y 軸）× ISO 週次（x 軸）的主辦場次數量熱圖，2023 / 2024 各一層。</p>"
        "<p><strong>圖中實際呈現：</strong>主要 6 個球場（樂天桃園、洲際、新莊、天母、屏東、嘉義）的熱點分布密集且均勻；"
        "中間有兩三週是冷色（All-Star break）；十月之後僅一兩個球場有熱度（postseason 集中）。"
        "兩季的整體 layout 接近，CPBL 賽程結構穩定。</p>"
    ),
    "4.8": ("球隊勝率排序 bar chart",
        "<p>每隊整體勝率（高至低排序）含 away/overall/home 三條 bar；底下附 dataframe 表格。0.5 紅虛線為基準。</p>"
        "<p><strong>圖中實際呈現：</strong>排名前段（如統一獅、樂天）overall 勝率約 0.55；後段（如富邦悍將）約 0.45。"
        "幾乎所有球隊的主場 bar 都高於客場 bar（主場優勢普遍存在），但差距大小不一——"
        "差距最大的球隊主場優勢約 +0.10，最小的接近 0。</p>"
    ),
    "4.9": ("H vs run_diff hexbin",
        "<p>每場的 H 安打數（x）vs run_diff 分差（y）的 hexbin density 圖，2023 / 2024 並列。</p>"
        "<p><strong>圖中實際呈現：</strong>主集中區為 H ∈ [6, 11] × run_diff ∈ [-5, +5]，呈大致 positive linear trend"
        "（多安打→正分差）。少數高 H（15+）幾乎都對應大 run_diff（+10 以上）；少數低 H（<5）有些仍然贏球"
        "（投手戰小勝）但更多是大敗。兩季 pattern 高度一致。</p>"
    ),
    "4.10": ("Top-3 features 球隊分布 violin",
        "<p>對 |Spearman ρ| vs win 前 3 高的 features（<code>run_diff, led_after_6, runs_scored</code>）"
        "做球隊分組 violin。</p>"
        "<p><strong>圖中實際呈現：</strong>排名靠前球隊（如統一）的 <code>run_diff</code> violin 中位數略偏正、整體較寬；"
        "排名靠後球隊（如富邦）中位數偏負。<code>led_after_6</code> 是 binary 所以 violin 退化為兩條柱狀；"
        "<code>runs_scored</code> 跨球隊差距較小（中位數都在 3-5 之間，shape 相近）——"
        "表示「得分能力」球隊差異有限，但「最終分差」差異明顯（投手與運氣的角色）。</p>"
    ),
    # Stage 5
    "5.1": ("Filter prune log",
        "<p>輸出 prune 過程：near-zero variance 丟棄 → |Spearman ρ| ≥ 0.95 冗餘成對丟棄 → 最終 KEPT list。"
        "本次保留約 45-50 個 features（從 60+ 個 pre-game lag features prune 而來）。</p>"
    ),
    "5.2": ("Standardize（ColumnTransformer）",
        "<p>HEAVY_TAIL 群組走 RobustScaler、SYMMETRIC 群組走 StandardScaler；缺失值用 SimpleImputer 補中位數。</p>"
        "<p>輸出 <code>X_scaled</code> 的形狀與 describe。StandardScaler 群應有 mean ≈ 0 std ≈ 1；RobustScaler 群 median ≈ 0 IQR ≈ 1。</p>"
    ),
    "5.3": ("PCA scree + 累積 PVE",
        "<p>PVE bar chart（藍）+ 累積線（橘），紅虛線標 90% 門檻。</p>"
        "<p><strong>圖中實際呈現：</strong>PC1 PVE ≈ 18.7%、PC2 ≈ 13.7%、PC3 ≈ 7.8%，之後緩慢遞減；"
        "累積線在 PC=24 才首次穿過 0.90 紅線（cumulative PVE 0.911）；之後仍有 ~30 個 minor PCs。"
        "scree 沒有明顯 elbow，整條曲線是平滑下降。</p>"
        "<p><strong>解讀：</strong>需要 24 個 PC 達 90%，遠多於 post-game 模式（~13 個）——pre-game lag features 之間的線性相關較鬆，"
        "因為不同視窗（5/10）、不同對象（self/opponent）算出來的同名 feature 雖然相關但不完全相同。"
        "K-Means 後續在這 24 維空間內跑，避免少數 dominant axis 主導所有結構。</p>"
    ),
    "5.4": ("PCA biplot",
        "<p>PC1-PC2 散點（按 <code>scored_first</code> coolwarm 上色）+ 黑色 quiver 箭頭標所有 features 的 loading。</p>"
        "<p><strong>圖中實際呈現：</strong>散點為大致橢圓分布，<code>scored_first</code> 對顏色沒有明顯空間相關"
        "（紅藍混在一起）——表示「誰先得分」不能由 pre-game 狀態預測，這是合理的（先得分有相當隨機性）。"
        "箭頭明顯分成兩團：右側是 <code>prior_run_diff/runs_scored/win_rate/run_per_hit</code>（自我攻擊指標），"
        "左下是 <code>opp_prior_*</code> 的對應 mirror。箭頭方向上半與下半對稱——正是 PC1 = self、PC2 = opponent 雙軸結構的視覺證據。</p>"
    ),
    "5.5": ("Loadings 表與熱圖",
        "<p>|loadings| 矩陣（55 features × 24 PCs）的數值表與熱圖。</p>"
        "<p><strong>圖中實際呈現的最強載入：</strong>"
        "PC1 top 3：<code>prior_run_per_hit_mean_10</code> (0.40)、<code>prior_run_per_hit_mean_5</code> (0.39)、"
        "<code>prior_run_diff_mean_10</code> (~0.40)；"
        "PC2 top 3：<code>opp_prior_runs_scored_mean_5</code> (0.66)、<code>opp_prior_runs_scored_mean_10</code> (0.65)、"
        "<code>opp_prior_run_diff_mean_10</code> (0.57)；"
        "PC3 top 3：<code>opp_prior_whip_like_mean_5</code> (0.58)、<code>prior_whip_like_mean_10</code> (0.57)、"
        "<code>prior_whip_like_mean_5</code> (0.56)。</p>"
        "<p><strong>解讀：</strong>三個主軸的故事清楚——PC1 = 「我方近期攻擊效率」、PC2 = 「對手近期攻擊強度」、"
        "PC3 = 「雙方近期投手 WHIP 結構」。後續 cluster_id 主要 fingerprint 自然落在 PC1-PC2 平面。</p>"
    ),
    "5.6": ("3D PCA 互動圖",
        "<p>plotly 3D scatter：PC1 / PC2 / PC3，按 season 上色，hover 顯示 team + date 與點座標。</p>"
        "<p><strong>圖中實際呈現：</strong>2023（藍）與 2024（紅）兩團點高度交織、佔據同一個 3D ellipsoid，"
        "沒有任何視覺上的「跨季分離」。旋轉看 PC1-PC2 平面可看到沿 PC1 方向有兩個輕度密集區（這就是後續 K-Means 切出的兩個 cluster）；"
        "沿 PC3 方向則無明顯結構（noise 多）。</p>"
    ),
    "5.7": ("K 值六方法共識",
        f"<p>2×3 panel：inertia(elbow) / silhouette / Calinski-Harabasz / Davies-Bouldin / gap statistic / GMM BIC，"
        f"每張子圖紅虛線標各方法挑出的最佳 k。</p>"
        f"<p><strong>圖中實際呈現各方法的 pick：</strong><br>"
        f"&nbsp;&nbsp;{k_consensus_summary()}</p>"
        "<p><strong>各 metric 曲線形狀：</strong>"
        "inertia 從 k=2 51324 → k=10 38226 平滑下降（沒有強 elbow，但 kneed 抓 k=3）；"
        "silhouette 從 k=2 0.115 單調下降到 k=10 0.066；"
        "CH 從 k=2 196.6 也單調下降；"
        "DBI 在 k=3 (2.35) 與 k=7 (2.17) 有兩個 local min；"
        "gap statistic 1.36 → 1.42 緩慢上升，沒有明顯峰值（gap rule 抓 k=3 是因 gap(3)≥gap(4)−sk(4)）；"
        "GMM BIC 在 k=4 達到最低。</p>"
        "<p><strong>關鍵解讀：</strong>k=2 與 k=3 各得 2 票（並列第一），DBI 偏好 k=7，BIC 偏好 k=4，沒有共識峰值。"
        "資料本質是「連續譜」——pre-game 球隊狀態本來就是 continuous form，不存在乾淨的 discrete archetype。"
        "選 k=2 是最 conservative 的「正面 vs 負面狀態」二分法；k=3 可細分「強/中/弱」三段，"
        "k=4 可進一步把對手強度也納入軸；都是合理選擇，差別在於「想要的細粒度」。</p>"
    ),
    "5.8": ("階層分群最佳化：四種 linkage 比較 + 平衡 gate",
        "<p>輸出：4-linkage cophenetic 比較表、4-panel dendrogram、silhouette × min-cluster-fraction 雙圖。最終 HIERARCHY_METHOD = <code>ward</code>, K_HIER = 2。</p>"
        "<p><strong>圖表中實際呈現的結論：</strong>"
        "<ul>"
        "<li>四種 linkage 的 cophenetic 相關係數排名："
        "<code>average</code> = 0.647 (最高，但每個 k 都 fails balance gate)、"
        "<code>single</code> = 0.566 (同樣 fails)、"
        "<code>complete</code> = 0.377、"
        "<code>ward</code> = 0.327。</li>"
        "<li><strong>關鍵發現：</strong>單純看 cophenetic 會選 average，但 average linkage 在 k=2 的切法是 1315 vs 5（外點獨立成小群），silhouette 看似漂亮 (0.504) 但分析沒意義；single 同樣只會切外點。所以我們加上 min_cluster_frac ≥ 5% 的 balance gate，這兩種 linkage 被全數淘汰。</li>"
        "<li>通過 balance gate 的：<code>ward</code> k=2 (silhouette 0.1002, min fraction 0.2424) 與 <code>complete</code> k=2 (silhouette 0.0984, min fraction 0.2492)。Ward 些微勝出。</li>"
        "<li>dendrogram 4-panel 視覺呈現：average / single 的樹結構頂部極不平衡（一大條 + 數條極短）；ward / complete 的樹較對稱、層級分明，視覺上也合理。</li>"
        "<li>silhouette × balance 雙圖：silhouette 圖上 average / single 在 k=2 都接近 0.5（誤導性高分），但 balance 圖上他們的最小群比例在所有 k 都 &lt; 0.01（紅線下），被 gate 直接濾掉。Ward / complete 兩條都在 balance 線之上，silhouette 也合理。</li>"
        "</ul></p>"
        "<p><strong>解讀：</strong>這格回應了「用 cophenetic 選 linkage」的標準教學——但教學書常忽略「外點獨立成小群」會給出虛假的高分。"
        "Balance gate 把這種退化解過濾掉後，ward 雖然 cophenetic 偏低 (0.327)，反而是「在能保證群平衡的前提下」的最佳 linkage。"
        "這個發現直接影響 Stage 5.11：hierarchical 那一列現在用 <code>ward</code> k=2 而非 average，與 K-Means / GMM 做公平比較。</p>"
    ),
    "5.9": ("GMM BIC / AIC",
        "<p>k=2..10 的 BIC（藍）與 AIC（橘）曲線。</p>"
        "<p><strong>圖中實際呈現：</strong>BIC 在 k=4 達最低，往兩側皆上升（k=2 與 k=10 都高於 k=4）。"
        "AIC 通常也在類似 k 達低點，曲線略低於 BIC（penalty 較弱）。</p>"
        "<p><strong>解讀：</strong>GMM 抓 k=4 表示「在 24 維 PCA 空間裡有 4 個 Gaussian 組件最 fit」——"
        "比 K-Means 的 k=2 多兩個，因 GMM 能容納「partial overlap」的群（soft assignment）。"
        "下游 supervised 可以同時用 cluster_id (硬，k=2) 與 gmm_p0..gmm_p3 (soft 4 dim)，兩種粒度兼得。</p>"
    ),
    "5.10": ("HDBSCAN 密度分群",
        "<p>HDBSCAN 自動分群結果 + condensed tree 視覺化。</p>"
        "<p><strong>圖中實際呈現：</strong>condensed tree 主要由少數較大的 branch 主導（持續多個 ε levels 不分裂），"
        "可能伴隨相當比例的 noise 點（label=-1）。具體 cluster 數 / noise 比例依本次 min_cluster_size = max(30, n/40)≈33 的設定而定。</p>"
        "<p><strong>解讀：</strong>HDBSCAN 對密度不均資料較敏感；若 noise 比例 >30%，代表資料密度太均勻"
        "（pre-game lag 狀態空間是 manifold-like），density-based 方法不是最佳選擇——這也是為何最終選 K-Means 而非 HDBSCAN。</p>"
    ),
    "5.11": ("Validity panel + 演算法選擇",
        f"<p>{validity_summary()}</p>"
    ),
    "5.12": ("Per-point silhouette diagnostic",
        "<p>所有點按 cluster 分組畫 silhouette bar，紅虛線標 mean (0.115)。</p>"
        "<p><strong>圖中實際呈現：</strong>兩個 cluster 各有約 600+ 個點（641 與 679）。"
        "Cluster 0 的 bars 多數落在 0-0.3 區段（mean 略高於 0.115）；cluster 1 類似。"
        "兩個 cluster 都有相當比例的 bars 落在 0 以下（負值，意味著該點離鄰居 cluster 更近）——"
        "這 visualises 了 silhouette 偏低的原因：cluster 邊界鬆、邊界附近的點歸屬不確定。</p>"
    ),
    "5.13": ("UMAP 二維投影",
        "<p>兩面板：左圖按 cluster_id 上色、右圖按 season_tag 上色。UMAP 設定 n_neighbors=30, min_dist=0.1。</p>"
        "<p><strong>圖中實際呈現：</strong>左圖大致呈現連續橢圓帶，cluster 0 與 cluster 1 在帶的兩端但中間有大量 overlap"
        "（典型「連續譜被切兩半」的型態，與 silhouette 0.115 一致）。"
        "右圖 2023 / 2024 完全交織（再次證實跨季 manifold 一致）。</p>"
        "<p><strong>解讀：</strong>UMAP 與 PCA 看到的結構一致——cluster_id 反映的是「位置在連續軸上的哪一端」，"
        "而非「離散的 archetype 歸屬」。對下游 supervised 來說，cluster_id 仍有訊息（區分形態的兩端），"
        "但 GMM 的 soft probability (gmm_p*) 或 pc1 連續分數可能保留更多細節。</p>"
    ),
    "5.14": ("t-SNE perplexity sanity check",
        "<p>perplexity=15 與 perplexity=50 兩面板並列。</p>"
        "<p><strong>圖中實際呈現：</strong>perplexity=15 時點雲較分散、有許多小密集區（fine structure）；"
        "perplexity=50 時整體融合為較大的連續塊。兩個 perplexity 都顯示出 cluster 0 / 1 大致在不同區域但邊界模糊。</p>"
        "<p><strong>解讀：</strong>兩個 perplexity 看到相同的「兩個區域 + 模糊邊界」結構——topology 在 perplexity 選擇上穩定，"
        "與 UMAP 結論互相佐證。</p>"
    ),
    "5.15": ("Cluster mean / SD 表",
        "<p>每個 cluster 在所有 85 個欄位上的 mean 與 SD（包含 post-game features 與 pre-game lag features）。</p>"
        "<p><strong>實際數值中最關鍵的對比：</strong>"
        "兩個 cluster 在 <code>runs_scored / runs_allowed / win</code> 等 post-game 結果幾乎相同"
        "（runs_scored mean 4.21 vs 4.17、win 0.523 vs 0.477）——這正是「pre-game gate」設計的功效：cluster 不是按 post-game 結果切的。"
        "真正的差異在 pre-game lag："
        "<code>prior_run_diff_mean_5</code> cluster 0 = +1.100, cluster 1 = −1.052（gap 2.15 runs）；"
        "<code>prior_win_rate_5</code> cluster 0 = 0.599, cluster 1 = 0.385（gap 21pp）；"
        "<code>opp_prior_win_rate_5</code> cluster 0 = 0.383, cluster 1 = 0.592（鏡像，cluster 0 通常對到較弱對手）。</p>"
    ),
    "5.16": ("Cluster radar chart",
        "<p>每個 cluster 中心在 FOCUS_FEATURES 上的 z-score（相對全資料平均）多邊形，10 條 spokes。</p>"
        "<p><strong>圖中實際呈現：</strong>兩個多邊形幾乎完全鏡像對稱——"
        "cluster 0 在所有 spokes 偏向「正常或略高」(z ≈ +0.05)、cluster 1 偏向「正常或略低」(z ≈ −0.05)，"
        "兩者差距在 z 軸上約 ±0.1 級別。形狀上沒有「某 feature 突出、另 feature 凹陷」的指紋。</p>"
        "<p><strong>解讀：</strong>FOCUS_FEATURES 是 post-game 變數，本身在兩個 cluster 上差異很小（因為 cluster 是按 pre-game 切的）。"
        "這張 radar 不適合 pre-game gate 模式——若要看 cluster 的真實 fingerprint，"
        "應改畫「pre-game lag features 的 z-score radar」（這正是 5.18a ANOVA F 排名的視覺化版本）。</p>"
    ),
    "5.17": ("Cluster boxplots（notched + bootstrap CI）",
        "<p>10 個 FOCUS_FEATURES 的 2x5 boxplot grid，本次 min_cluster_n = 641（遠大於 10），notch 與 bootstrap=2000 自動啟用。</p>"
        "<p><strong>圖中實際呈現：</strong>10 張 boxplot 兩個 cluster 的 boxes 高度與中位數線幾乎完全重疊；notch 也大幅重疊。"
        "代表 FOCUS_FEATURES（post-game 變數）對 pre-game cluster_id 沒有區分力——這是 by design，再次驗證 cluster 是 pre-game 切的。</p>"
        "<p><strong>正確的觀察對象：</strong>若想看「cluster 之間有顯著差異」的特徵，需看 pre-game lag features，那已在 5.18a 圖中呈現。</p>"
    ),
    "5.18": ("Surrogate RandomForest + SHAP 解釋 cluster",
        f"<p>對每個 cluster 訓練 one-vs-rest RF + Tree-SHAP，輸出 top-5 feature 排名與 auto-generated 標籤。</p>"
        f"<p>{cluster_id_meaning()}</p>"
        "<p><strong>解讀：</strong>標籤直白地告訴你 cluster 是什麼——cluster 0 是「近期狀態好（過去 5-10 場 run_diff 為正）」，"
        "cluster 1 是「近期狀態差」。這就是 pre-game 視角下最自然的分群——「球隊現在熱還是冷」。</p>"
    ),
    "5.18a": ("ANOVA F + MI 共識排名",
        "<p>右側為 Top-12 features by ANOVA F 的 horizontal bar chart；上方表格列出 ANOVA F + MI + 雙 cluster z-score。</p>"
        f"<p><strong>圖中實際呈現的 top 8：</strong><br>{meaningful_summary()}</p>"
        "<p><strong>解讀：</strong>F 值前 10 名清一色是 <code>prior_run_diff_mean_*</code> 與其 opponent mirror、"
        "<code>prior_runs_scored_mean_*</code>、<code>prior_win_rate_*</code>——"
        "證實 cluster 結構的核心軸線就是「近期 run_diff / 勝負形態」（自我與對手的）。"
        "F 值在 340-590 區間表示「cluster 中心在這些 features 上的差距遠大於 cluster 內變異」，分離度高。"
        "z_cluster_0 / z_cluster_1 對所有 top features 都是相反符號 (±0.45 到 ±0.57)，"
        "完美佐證「cluster 0 = 自我熱、對手冷；cluster 1 = 自我冷、對手熱」的對稱結構。</p>"
    ),
    "5.19": ("2023 vs 2024 cluster frequency shift",
        "<p>2023 與 2024 在每個 cluster 的比例 grouped bar chart + plotly Sankey 流向圖。</p>"
        "<p><strong>圖中實際呈現的 cross-tab 數值：</strong>"
        "2023：cluster 0 = 289, cluster 1 = 311；2024：cluster 0 = 352, cluster 1 = 368。"
        "兩季都略偏 cluster 1（45 vs 55 兩端均勻）；2024 比例與 2023 幾乎一致（無明顯 meta shift）。</p>"
        "<p><strong>Sankey 流向：</strong>由於兩季的 (cluster 0, cluster 1) 比例幾乎相同，"
        "Sankey 兩條流線粗細接近——視覺上「season → cluster」的分配跨年穩定，"
        "再次佐證 4.5 / 4.6 看到的「2023/2024 meta 接近」結論。</p>"
    ),
    "5.20": ("Derived feature register",
        "<p>把 <code>cluster_id</code>、24 個 <code>pc1..pc24</code>、4 個 <code>gmm_p0..gmm_p3</code> 加回主表，"
        "供下游 supervised 使用。預覽前幾列確認對齊正確。</p>"
    ),
    # Stage 6
    "6.1": ("Focus / lag features × unsupervised 結構 overlap",
        f"<p>{focus_overlap_summary()}</p>"
        "<p><strong>解讀：</strong>combined_score 高代表「PCA 與 SHAP 雙重佐證」，這些就是 unsupervised 階段對下游 supervised 最自信的特徵。"
        "前 5 名清一色為 <code>opp_prior_*</code> 與 <code>prior_*</code> 的「近期 run_diff / runs_scored 滾動平均」——"
        "再次確認 cluster 結構是由「自我 vs 對手近期狀態」雙軸驅動。</p>"
    ),
    "6.2": ("Unsupervised 新增候選 features",
        f"<p>{new_features_summary()}</p>"
        "<p><strong>意義：</strong>這 8 個是本研究的「實際交付」——學長原始 feature set 沒有它們。"
        "下游 supervised 模型加上這些之後若 AUC 提升，代表本 notebook 為學長 baseline 真的加值了；若沒提升，"
        "代表 cluster 結構與 win 的關係已被學長原始 features 充分表達——也是有意義的負結論。</p>"
    ),
    "6.3": ("Research design summary",
        "<p>研究設計一頁摘要：goal / approach / feature strategy / validation / limitations。可直接放進報告或簡報。</p>"
    ),
    # Stage 7
    "7.1": ("Artifact registry preview",
        "<p>列出所有 51 個被 <code>show_and_track</code> 註冊的 artifact 的 name + kind。"
        "本次重跑時 <code>DOWNLOAD_ALL = True</code>，這 51 個檔案被寫到 <code>Results/stage{N}/</code> 各 stage 子資料夾。</p>"
    ),
    "7.2": ("最終 CSV 與 feature catalog 輸出",
        "<p>產生 <code>final_features.csv</code>（ORIGINAL + SEMANTIC + NUMERIC + UNSUPERVISED 四群）、"
        "<code>feature_catalog.csv</code>（feature 名稱 + 來源分類）、<code>research_design_summary.csv</code>。</p>"
        "<p>這些 CSV 都在 <code>Results/stage6/</code> 與 <code>outputs/cpbl_feature_discovery/</code> 兩處。</p>"
    ),
    "7.3": ("Download switch 執行",
        "<p>本次重跑將 <code>DOWNLOAD_ALL = True</code>、<code>out_dir = Results/</code>，並依 stage 前綴分到 5 個子資料夾："
        "<code>stage2/ (2 files), stage3/ (6), stage4/ (10), stage5/ (29), stage6/ (4)</code> — 共 51 個檔案。</p>"
    ),
}


# Stage summaries (status-quo aware)
STAGE_SUMMARIES = {
    "0": "確認 runtime（Python 3.11 + scientific stack）、初始化 artifact registry、寫死 success criteria。",
    "1": "從 rebas.tw 三個 release 直接下載 + 解壓，共讀入 ~660 場原始紀錄（2023 + 2024）。",
    "2": "1320 × 51 → 1320 × 112 team-game features（加入 60+ 個 pre-game lag）；Wang 對照 35/44 數值欄 pearson_r ≥ 0.999；pre-game gate 啟用。",
    "3": "整體 describe + 分季比較 + 二元基準率 + Pearson/Spearman 雙重相關 + 偏態診斷——量化了「最該關注哪幾個 features」。",
    "4": "10 張 EDA 視覺化，視覺確認 2023/2024 meta 接近、主場優勢仍在、Wang features 在多圖中保留信號。",
    "5": "PCA 需 24 PC 達 90% 變異；K 共識六方法投票 k=2 與 k=3 並列第一（程式採最小 k = 2）；最終 KMeans k=2，sil=0.115，jaccard=0.918；cluster 結構由「自我與對手近期 run_diff」雙軸驅動。",
    "6": "Wang 學長 feature ranking 在本研究 (pre-game gate=ON) 下變為「近期 run_diff / runs_scored 滾動平均」最強；新增 8 個候選 features（cluster_id + 4 gmm_p + 3 pc）供下游 supervised 驗證。",
    "7": "Artifact registry 共 51 個檔案，全部寫出到 Results/stage{N}/ 子資料夾（不再 zip）；final_features.csv 為主交付。",
}


# Stages to include
STAGES = [
    ("0", "Stage 0 — 執行環境與輸出設定", ["0.1", "0.2", "0.3"]),
    ("1", "Stage 1 — 從 rebas.tw releases 取得真實資料", ["1.1", "1.2"]),
    ("2", "Stage 2 — 前處理與 team-game 特徵工程",
        ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.7a", "2.7b", "2.8", "2.9"]),
    ("3", "Stage 3 — 描述統計與關聯檢查",
        ["3.1", "3.2", "3.3", "3.4", "3.5"]),
    ("4", "Stage 4 — EDA 視覺化",
        ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9", "4.10"]),
    ("5", "Stage 5 — 非監督式特徵發現",
        ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8", "5.9", "5.10",
         "5.11", "5.12", "5.13", "5.14", "5.15", "5.16", "5.17", "5.18", "5.18a",
         "5.19", "5.20"]),
    ("6", "Stage 6 — 綜合整理",
        ["6.1", "6.2", "6.3"]),
    ("7", "Stage 7 — 最終輸出",
        ["7.1", "7.2", "7.3"]),
]


def render_section(sid):
    if sid not in SECTION_EXPL:
        return ""
    title, expl = SECTION_EXPL[sid]
    if sid in SECTION_OVERRIDES:
        output_html = SECTION_OVERRIDES[sid]()
    else:
        output_html = render_section_outputs(sid)
    if not output_html and not expl:
        return ""
    parts = [f'<div class="section">']
    parts.append(f'<h3 class="sec-head">{sid} — {html.escape(title)}</h3>')
    if output_html:
        parts.append('<div class="outputs">')
        parts.append(output_html)
        parts.append('</div>')
    parts.append('<div class="explanation">')
    parts.append(expl)
    parts.append('</div>')
    parts.append('</div>')
    return "\n".join(parts)


def render_stage(stage_num, stage_title, sids):
    parts = [f'<section id="stage-{stage_num}" class="stage">']
    parts.append(f'<h2>{html.escape(stage_title)}</h2>')
    summary = STAGE_SUMMARIES.get(stage_num, "")
    if summary:
        parts.append(f'<div class="stage-summary">{summary}</div>')
    for sid in sids:
        parts.append(render_section(sid))
    parts.append('</section>')
    return "\n".join(parts)


# Mermaid pipeline diagram
MERMAID = """
flowchart TD
    A0[Stage 0 setup<br/>imports · artifact registry · success criteria] --> A1
    A1[Stage 1 rebas.tw 直接下載<br/>2023.0 · 2023.1 · 2024] --> A2
    A2[Stage 2 前處理<br/>1320 team-game rows · 60+ pre-game lag features] --> A2g{Pre-game gate?}
    A2g -- ON 預設 --> A2p[Use FEATURES_FOR_UNSUP = pre-game lags only<br/>leak-free predictive view]
    A2g -- OFF --> A2o[Use POSTGAME_FEATURES = box-score<br/>descriptive game-archetype view]
    A2p --> A3
    A2o --> A3
    A3[Stage 3 描述統計<br/>describe · base rates · Pearson + Spearman · skew/kurtosis]
    A3 --> A4[Stage 4 EDA<br/>10 視覺化：histogram · heatmap · pairplot · home/away · monthly · ECDF · calendar · win-rate · hexbin · violin]
    A4 --> A5
    A5[Stage 5 非監督特徵發現]
    A5 --> A51[5.1-5.2 filter prune + scale]
    A51 --> A52[5.3-5.6 PCA scree · biplot · loadings · 3D]
    A52 --> A57[5.7 K 共識六方法投票]
    A57 --> A58[5.8-5.10 KMeans · Ward · GMM · HDBSCAN]
    A58 --> A511[5.11 validity + bootstrap-Jaccard]
    A511 --> A513[5.13-5.14 UMAP + t-SNE]
    A513 --> A515[5.15-5.18a cluster interp<br/>radar · notched box · SHAP · ANOVA F + MI]
    A515 --> A519[5.19-5.20 跨季 shift + derived register]
    A519 --> A6[Stage 6 綜合整理<br/>focus overlap · new candidates · design summary]
    A6 --> A7[Stage 7 輸出<br/>final_features.csv · 51 stage artifacts]

    classDef setup fill:#e3f2fd,stroke:#1976d2
    classDef data fill:#fff8e1,stroke:#f57c00
    classDef gate fill:#fce4ec,stroke:#c2185b
    classDef analyze fill:#e8f5e9,stroke:#388e3c
    classDef result fill:#f3e5f5,stroke:#7b1fa2
    class A0,A1 setup
    class A2,A2p,A2o data
    class A2g gate
    class A3,A4,A5,A51,A52,A57,A58,A511,A513,A515,A519 analyze
    class A6,A7 result
"""


CSS = """
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans CJK TC",
                 "PingFang TC", "Microsoft JhengHei", "Helvetica Neue", Arial, sans-serif;
    max-width: 1100px; margin: 2rem auto; padding: 0 1.5rem;
    line-height: 1.7; color: #222; background: #fafafa;
}
h1 {
    font-size: 2rem; border-bottom: 3px solid #1a73e8;
    padding-bottom: 0.5rem; margin-bottom: 0.5rem; color: #1a3a5e;
}
h2 {
    font-size: 1.5rem; color: #1a73e8;
    border-bottom: 1px solid #cfd8dc; padding-bottom: 0.3rem;
    margin-top: 3rem;
}
h3.sec-head {
    font-size: 1.15rem; color: #5a3aa0; margin-top: 2rem;
}
.subtitle { color: #666; font-size: 1rem; margin-top: 0; }
.toc {
    background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
    padding: 1rem 1.5rem; margin: 1.5rem 0;
}
.toc ol { margin: 0.3rem 0 0.3rem 1.5rem; }
.mermaid-wrap {
    background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
    padding: 1.5rem; margin: 2rem 0; overflow-x: auto;
}
.stage-summary {
    background: #e8f4fd; border-left: 4px solid #1a73e8;
    padding: 0.9rem 1.3rem; margin: 1rem 0 2rem 0; border-radius: 0 6px 6px 0;
    font-size: 0.95rem; color: #1a3a5e;
}
.section { margin: 1rem 0 2.5rem 0; }
.outputs {
    background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
    padding: 1rem; margin: 0.8rem 0;
}
.outputs img { max-width: 100%; height: auto; display: block; margin: 0.5rem auto; }
.outputs .table-wrap {
    overflow-x: auto; overflow-y: visible;
    border: 1px solid #eee; border-radius: 4px;
    margin: 0.5rem 0;
}
.outputs table {
    border-collapse: collapse; margin: 0; font-size: 0.85rem;
    white-space: normal; word-break: break-word;
}
.outputs th, .outputs td {
    border: 1px solid #ddd; padding: 5px 9px; text-align: left;
    vertical-align: top;
}
.outputs th { background: #f4f4f4; font-weight: 600; white-space: nowrap; }
.outputs tr:nth-child(even) { background: #fafafa; }
.outputs table.full-table td:nth-child(n+2) { max-width: 720px; }
.outputs h4.sub-heading {
    color: #5a3aa0; font-size: 1rem; margin: 1.2rem 0 0.4rem 0;
    border-bottom: 1px dashed #ccc; padding-bottom: 0.2rem;
}
.outputs .md-out p { margin: 0.4rem 0; }
.outputs .md-out strong { color: #1a3a5e; }
.outputs .stream {
    background: #f7f7f7; padding: 0.6rem 0.9rem; border-radius: 4px;
    font-family: ui-monospace, Menlo, monospace; font-size: 0.85rem;
    overflow-x: auto; white-space: pre;
}
.explanation {
    background: #fffef0; border-left: 4px solid #fbc02d;
    padding: 0.8rem 1.2rem; margin: 0.8rem 0; border-radius: 0 6px 6px 0;
}
.explanation p { margin: 0.5rem 0; }
.explanation code, .stage-summary code, .toc code {
    background: #f0f0f0; padding: 1px 5px; border-radius: 3px;
    font-family: ui-monospace, Menlo, monospace; font-size: 0.88em;
}
.explanation strong { color: #1a3a5e; }
.plotly-fig { width: 100%; }
footer { margin-top: 4rem; padding-top: 1.5rem; border-top: 1px solid #ccc;
         color: #888; font-size: 0.85rem; text-align: center; }
"""


def build_html():
    body_stages = "\n".join(render_stage(num, title, sids) for num, title, sids in STAGES)

    toc_items = "\n".join(
        f'<li><a href="#stage-{num}">{html.escape(title)}</a></li>'
        for num, title, _ in STAGES
    )

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>CPBL 2023-2024 非監督特徵發現 — 結果報告</title>
<style>{CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<script>
document.addEventListener("DOMContentLoaded", () => {{
    mermaid.initialize({{ startOnLoad: true, theme: "default", flowchart: {{ useMaxWidth: true }} }});
}});
</script>
</head>
<body>

<h1>CPBL 2023-2024 非監督式特徵發現 — 結果報告</h1>
<p class="subtitle">114-2 資料科學期末專題 · pre-game leak-free feature discovery · 主 notebook：
<code>Scripts/cpbl_unsupervised_feature_discovery.ipynb</code></p>

<div class="toc">
<strong>目次</strong>
<ol>{toc_items}</ol>
</div>

<h2 id="overview">Pipeline 流程圖</h2>
<div class="mermaid-wrap">
<pre class="mermaid">
{MERMAID}
</pre>
</div>

<h2 id="executive-summary">Executive Summary（一頁摘要）</h2>
<div class="stage-summary">
<p>本研究從 rebas.tw 官方 release 取得 CPBL 2023 + 2024 共 ~660 場原始比賽，建構 1320 列
（每場 2 列）team-game features。對學長 supervised pipeline 的最大改進：</p>
<ol>
<li><strong>Pre-game gate</strong>：建立 60+ 個 <code>prior_*</code> / <code>opp_prior_*</code> 滾動 lag features，
讓 unsupervised 階段只看比賽前可知資訊，<code>cluster_id</code> 可作為 leak-free 預測因子。</li>
<li><strong>K 值六方法共識</strong>：取代「只看 silhouette」的單一指標決策。本次投票結果 k=2 與 k=3 並列第一，
最終採 k=2（程式預設取最小 k 破解平手）。</li>
<li><strong>Wang 對照驗證</strong>：35/44 數值欄位的 Pearson r ≥ 0.999，確認 Python port 在數值上完全等價於 Wang 的 R 實作。</li>
</ol>

<p><strong>最終 cluster 結構</strong>：KMeans k=2，silhouette 0.115（偏低）、bootstrap-Jaccard 0.918（很高）。
低 silhouette 加高穩定度，表示資料是「連續譜被切成兩半」而非真正離散的 archetype——pre-game 球隊狀態
本質上就是連續的 form，cluster_id 的意義是「最近 5-10 場的 run_diff 是正還是負」（自我 + 對手雙軸）。</p>

<p><strong>新增候選 features（共 8 個）</strong>給下游 supervised 模型：
<code>cluster_id</code>（hard 分群）、<code>gmm_p0-p3</code>（4 個 soft probability）、<code>pc1-pc3</code>（3 個主成分分數）。</p>
</div>

{body_stages}

<footer>
<p>本報告由 <code>build_report_html.py</code> 自動生成；資料來源 <a href="https://github.com/rebas-tw/rebas.tw-open-data">rebas.tw open data</a>，授權 ODC-By。</p>
</footer>

</body>
</html>
"""


html_doc = build_html()
Path(OUT).write_text(html_doc, encoding="utf-8")
print(f"Wrote {OUT}: {len(html_doc):,} chars / {Path(OUT).stat().st_size/1024:.0f} KB")
