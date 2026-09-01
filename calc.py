"""
家計簿（kakeibo）集計スクリプト

エクセルの取引明細と config.yaml の項目定義を読み込み、
月次・年次の収支サマリーと将来予測を計算して pickle に保存する。

元スクリプトのロジック（各種整合性チェック含む）は変更していない。
可読性・保守性・実行効率の向上のために関数分割とベクトル化を行った。
"""

from __future__ import annotations

import argparse
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

YearMonth = Tuple[int, int]  # (year, month)


class ValidationError(Exception):
    """入力データや計算結果の整合性チェックに失敗したときの例外。"""


# --------------------------------------------------------------------------- #
# 月・年度まわりのユーティリティ
# --------------------------------------------------------------------------- #

def next_month(y: int, m: int) -> YearMonth:
    """翌月の (年, 月) を返す。"""
    if m == 12:
        return y + 1, 1
    return y, m + 1


def fiscal_year(y: int, m: int) -> str:
    """4月始まりの年度を文字列で返す（例: 2023年4月〜2024年3月 -> "2023"）。"""
    return str(int(np.floor((100 * y + m - 4) / 100)))


def build_month_index(start: YearMonth, finish: YearMonth) -> List[str]:
    """start から finish までの "YYYYMM" 文字列のリストを返す（両端含む）。"""
    y, m = start
    months = []
    while True:
        months.append(f"{100 * y + m}")
        if (y, m) == tuple(finish):
            break
        y, m = next_month(y, m)
    return months


def build_fiscal_year_groups(months: List[str]) -> List[Tuple[str, List[str]]]:
    """月リストを年度ごとにグルーピングする。[(年度, [月, 月, ...]), ...] を返す。"""
    groups: Dict[str, List[str]] = {}
    for month in months:
        y, m = int(month[:4]), int(month[4:6])
        fy = fiscal_year(y, m)
        groups.setdefault(fy, []).append(month)
    return list(groups.items())


def none2int(val) -> int:
    return 0 if val is None or (isinstance(val, float) and np.isnan(val)) else int(val)


# --------------------------------------------------------------------------- #
# 設定・エクセルの読み込みと検証
# --------------------------------------------------------------------------- #

def load_config(path: str) -> dict:
    logger.info("configファイルの読み込み中: %s", path)
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not (config["開始月"] <= config["締め月"] <= config["現在月"]):
        raise ValidationError("config.yaml の 開始月 <= 締め月 <= 現在月 を満たしていません")
    return config


def category_lists(config: dict) -> Tuple[List[str], List[str]]:
    """(出金の細目リスト, 出金の大分類リスト[NAを除く]) を返す。"""
    expense_subcategories = [item for _, items in config["支出項目"] for item in items]
    expense_categories = [category for category, _ in config["支出項目"] if category != "NA"]
    return expense_subcategories, expense_categories


def validate_sheet(df: pd.DataFrame, sheet_name: str, config: dict, expense_subcategories: List[str]) -> None:
    """1シート分の取引明細に対する形式・整合性チェック。"""
    required_cols = {"yyyymm", "分類", "入金", "出金", "残高"}
    if not required_cols.issubset(df.columns):
        raise ValidationError(f"{sheet_name}シートのカラム名が不適切です")

    valid_categories = set(config["収入項目"] + expense_subcategories) | {"移動"}
    for j, x in enumerate(df["分類"].values):
        if j == 0:
            if not pd.isna(x):
                raise ValidationError(f"{sheet_name}シートの１行目のデータには残高のみ記載してください")
        elif x not in valid_categories:
            raise ValidationError(f"{sheet_name}シートの{j}行目のデータの分類「{x}」が不適切です")

    if df["yyyymm"].isna().any():
        bad = df.index[df["yyyymm"].isna()][0]
        raise ValidationError(f"{sheet_name}シートの{bad}行目のデータのyyyymmが入力されていません。")

    if not df["yyyymm"].between(190000, 210000, inclusive="neither").all():
        raise ValidationError(f"{sheet_name}のyyyymmが不正")

    if not df["yyyymm"].is_monotonic_increasing:
        raise ValidationError(f"{sheet_name}のyyyymmが不正")

    # 残高 = 前残高 + 入金 - 出金 の月次整合性チェック
    prev_zandaka = df.loc[0, "残高"]
    for month, group in df.iloc[1:].groupby(df.iloc[1:]["yyyymm"]):
        zandaka = group["残高"].iloc[-1]
        nyukin = group["入金"].sum()
        shukkin = group["出金"].sum()
        if prev_zandaka + nyukin - shukkin != zandaka:
            raise ValidationError(f"{sheet_name}の{month}の残高整合性チェックに失敗しました")
        prev_zandaka = zandaka


def load_excel_data(path: str, config: dict, expense_subcategories: List[str]) -> pd.DataFrame:
    """全シートを読み込み・検証し、1つの DataFrame に結合する。"""
    logger.info("エクセルファイルの読み込み中: %s", path)
    sheets = pd.read_excel(path, sheet_name=None)

    frames = []
    for sheet_name, df in sheets.items():
        validate_sheet(df, sheet_name, config, expense_subcategories)
        df = df.copy()
        df["sheet"] = sheet_name
        df["yyyymm"] = df["yyyymm"].astype(int).astype(str)
        frames.append(df)

    df_transactions = pd.concat(frames, ignore_index=True)

    df_item = pd.DataFrame(
        [(sub_item, category) for category, items in config["支出項目"] for sub_item in items],
        columns=["分類", "大分類"],
    )
    df_transactions = pd.merge(df_transactions, df_item, on="分類", how="left")

    validate_transfers(df_transactions, config)
    return df_transactions


def validate_transfers(df_transactions: pd.DataFrame, config: dict) -> None:
    """「移動」区分の入金・出金が月ごとに一致することを確認する。"""
    transfer_transactions = df_transactions[df_transactions["分類"] == "移動"]
    monthly_totals = transfer_transactions.groupby("yyyymm")[["入金", "出金"]].sum()
    mismatched_months = monthly_totals[monthly_totals["入金"].astype(int) != monthly_totals["出金"].astype(int)]
    if not mismatched_months.empty:
        month, row = next(iter(mismatched_months.iterrows()))
        raise ValidationError(
            f"{month}の移動のデータが不整合です。入金が{int(row['入金'])}、出金が{int(row['出金'])}"
        )


# --------------------------------------------------------------------------- #
# 月次集計
# --------------------------------------------------------------------------- #

def compute_asset_balances(df_transactions: pd.DataFrame, months: List[str], asset_groups: Dict[str, List[str]]) -> pd.DataFrame:
    """資産項目（複数シートの合算）ごとの月末残高を計算する。データの無い月は前月値を維持。"""
    monthly_balances = df_transactions.groupby(["sheet", "yyyymm"])["残高"].last().unstack("sheet")
    monthly_balances = monthly_balances.reindex(months).ffill().fillna(0).astype(int)

    result = pd.DataFrame(0, index=months, columns=list(asset_groups.keys()))
    for asset_name, sheet_names in asset_groups.items():
        available_sheets = [s for s in sheet_names if s in monthly_balances.columns]
        if available_sheets:
            result[asset_name] = monthly_balances[available_sheets].sum(axis=1)
    return result


def compute_category_pivot(
    df_transactions: pd.DataFrame,
    months: List[str],
    columns: List[str],
    category_col: str,
    amount_col: str,
    other_amount_col: str,
) -> pd.DataFrame:
    """分類（または大分類）ごとに amount_col を月次集計したピボットを返す。
    other_amount_col 側に値が入っている行があればエラーにする。"""
    subset = df_transactions[df_transactions[category_col].isin(columns)]

    bad = subset[subset[other_amount_col].fillna(0) != 0]
    if not bad.empty:
        row = bad.iloc[0]
        raise ValidationError(
            f"エラー\n{row['yyyymm']}の{row[category_col]}について"
            f"{amount_col}項目にもかかわらず{other_amount_col}の列に記入されています。"
        )

    pivot = subset.pivot_table(index="yyyymm", columns=category_col, values=amount_col, aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(index=months, columns=columns, fill_value=0)
    return pivot.fillna(0).astype(int)


def compute_month_frames(df_transactions: pd.DataFrame, months: List[str], config: dict,
                          expense_categories: List[str], expense_subcategories: List[str]) -> Dict[str, pd.DataFrame]:
    logger.info("月次集計を計算中")
    monthly_data: Dict[str, pd.DataFrame] = {}

    asset_groups = config["資産項目"]
    monthly_data["basic"] = compute_asset_balances(df_transactions, months, asset_groups)
    monthly_data["basic"]["収入"] = 0
    monthly_data["basic"]["支出"] = 0
    monthly_data["basic"]["収支"] = 0

    non_transfer_transactions = df_transactions[df_transactions["分類"] != "移動"]
    monthly_totals = non_transfer_transactions.groupby("yyyymm")[["入金", "出金"]].sum()
    monthly_totals = monthly_totals.reindex(months, fill_value=0)
    monthly_data["basic"]["収入"] = monthly_totals["入金"].astype(int)
    monthly_data["basic"]["支出"] = monthly_totals["出金"].astype(int)
    monthly_data["basic"]["収支"] = monthly_data["basic"]["収入"] - monthly_data["basic"]["支出"]

    monthly_data["income"] = compute_category_pivot(
        df_transactions, months, config["収入項目"], "分類", "入金", "出金"
    )
    monthly_data["expense_subcategory"] = compute_category_pivot(
        df_transactions, months, expense_subcategories, "分類", "出金", "入金"
    )
    monthly_data["expense_category"] = compute_category_pivot(
        df_transactions, months, [x for x in expense_categories if x != "NA"], "大分類", "出金", "入金"
    )

    validate_balance_consistency(monthly_data["basic"], months, asset_groups)
    return monthly_data


def validate_balance_consistency(monthly_summary: pd.DataFrame, months: List[str], asset_groups: Dict[str, List[str]]) -> None:
    """資産合計の月差分が収支と一致することを確認する。"""
    asset_cols = list(asset_groups.keys())
    totals = monthly_summary[asset_cols].sum(axis=1)
    for prev_month, month in zip(months, months[1:]):
        diff = totals[month] - totals[prev_month]
        if diff != monthly_summary.loc[month, "収支"]:
            raise ValidationError(
                "エラー\n{}の資産は{}\n{}の資産は{}\n差額は{}\nしかし{}の収支が{}です。".format(
                    prev_month, totals[prev_month], month, totals[month],
                    diff, month, monthly_summary.loc[month, "収支"],
                )
            )


# --------------------------------------------------------------------------- #
# 年次集計
# --------------------------------------------------------------------------- #

def compute_year_frames(monthly_data: Dict[str, pd.DataFrame], year_groups: List[Tuple[str, List[str]]],
                         asset_groups: Dict[str, List[str]]) -> Dict[str, pd.DataFrame]:
    logger.info("年次集計を計算中")
    asset_keys = set(asset_groups.keys())
    year_labels = [fy for fy, _ in year_groups]

    yearly_data: Dict[str, pd.DataFrame] = {}
    for key, df in monthly_data.items():
        out = pd.DataFrame(0, index=year_labels, columns=df.columns)
        for fy, months in year_groups:
            for col in df.columns:
                if col in asset_keys:
                    out.loc[fy, col] = int(df.loc[months[-1], col])
                else:
                    out.loc[fy, col] = int(df.loc[months, col].sum())
        yearly_data[key] = out
    return yearly_data


# --------------------------------------------------------------------------- #
# 将来予測
# --------------------------------------------------------------------------- #

def compute_forecast(monthly_data_basic: pd.DataFrame, config: dict, months_ahead: int = 60) -> pd.DataFrame:
    logger.info("将来予測を計算中")
    future_month = config["現在月"]
    for _ in range(months_ahead):
        future_month = next_month(*future_month)

    index = build_month_index(config["開始月"], future_month)
    actual_months = set(build_month_index(config["開始月"], config["締め月"]))

    asset_cols = list(config["資産項目"].keys())
    zandaka = monthly_data_basic[asset_cols].sum(axis=1)

    monthly_balance_change = {
        month[4:6]: monthly_data_basic.loc[month, "収支"]
        for month in build_month_index(config["開始月"], config["締め月"])
    }

    forecast_data = pd.DataFrame(0, index=index, columns=["実績", "予測"])
    previous_balance = 0
    for month in index:
        if month in actual_months:
            current_balance = zandaka.get(month, previous_balance)
            forecast_data.loc[month, "実績"] = current_balance
            forecast_data.loc[month, "予測"] = 0
        else:
            current_balance = previous_balance + monthly_balance_change[month[4:6]]
            forecast_data.loc[month, "実績"] = 0
            forecast_data.loc[month, "予測"] = current_balance
        previous_balance = current_balance
    return forecast_data


# --------------------------------------------------------------------------- #
# 保存
# --------------------------------------------------------------------------- #

def save_outputs(output_dir: Path, monthly_data: dict, yearly_data: dict, forecast_data: pd.DataFrame) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in (("monthly_data", monthly_data), ("yearly_data", yearly_data), ("forecast_data", forecast_data)):
        path = output_dir / f"{name}.pkl"
        with open(path, "wb") as f:
            pickle.dump(obj, f)
        logger.info("保存しました: %s", path)


# --------------------------------------------------------------------------- #
# メイン
# --------------------------------------------------------------------------- #

def run(config_path: str, data_path: str, output_dir: str = ".") -> None:
    config = load_config(config_path)
    expense_subcategories, expense_categories = category_lists(config)

    df_transactions = load_excel_data(data_path, config, expense_subcategories)

    months = build_month_index(config["開始月"], config["現在月"])
    monthly_data = compute_month_frames(df_transactions, months, config, expense_categories, expense_subcategories)

    year_groups = build_fiscal_year_groups(months)
    yearly_data = compute_year_frames(monthly_data, year_groups, config["資産項目"])

    forecast_data = compute_forecast(monthly_data["basic"], config)

    save_outputs(Path(output_dir), monthly_data, yearly_data, forecast_data)
    logger.info("計算終了")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="家計簿の月次・年次集計と将来予測を計算する")
    parser.add_argument("--config", default="sample/config.yaml", help="config.yaml のパス")
    parser.add_argument("--data", default="sample/kakeibo.xlsx", help="取引明細エクセルのパス")
    parser.add_argument("--output", default=".", help="pickle 出力先ディレクトリ")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.config, args.data, args.output)