import json
import pickle
from itertools import chain
from pathlib import Path

import pandas as pd
import yaml
from flask import Flask, render_template, request
from typing import List, Literal, Tuple, Dict

PKL_DIR = Path("pkl")
CONFIG_PATH = "config.yaml"
BALANCE_COLUMNS = ["収入", "支出", "収支"]
LARGE_ITEMS_KEY = "大型収支項目"

# 単位ごとの移動平均設定: (窓幅, ラベル)
MA_SETTINGS = {
    "month": (12, "12ヶ月移動平均"),
    "year": (3, "3年移動平均"),
}
MA_LABELS = {label for _, label in MA_SETTINGS.values()}

COLORS = [
    ('rgb(  0,   0, 255)', 'rgba(  0,   0, 255, 0.5)'),
    ('rgb(  0, 203, 255)', 'rgba(  0, 203, 255, 0.5)'),
    ('rgb(255, 255,   0)', 'rgba(255, 255,   0, 0.5)'),
    ('rgb(216, 255, 204)', 'rgba(216, 255, 204, 0.5)'),
    ('rgb(  0, 255,   0)', 'rgba(  0, 255,   0, 0.5)'),
    ('rgb(  0, 101,   0)', 'rgba(  0, 101,   0, 0.5)'),
    ('rgb(255,  63,   0)', 'rgba(255,  63,   0, 0.5)'),
    ('rgb( 203,  0, 203)', 'rgba( 203,  0, 203, 0.5)'),
    ('rgb(  0,   0,  50)', 'rgba(  0,   0,  50, 0.5)'),
    ('rgb(255, 153,   0)', 'rgba(255, 153,   0, 0.5)'),
    ('rgb(255, 105, 180)', 'rgba(255, 105, 180, 0.5)'),
    ('rgb(139,  69,  19)', 'rgba(139,  69,  19, 0.5)'),
    ('rgb(128, 128, 128)', 'rgba(128, 128, 128, 0.5)'),
    ('rgb(128,   0,   0)', 'rgba(128,   0,   0, 0.5)'),
    ('rgb(  0, 128, 128)', 'rgba(  0, 128, 128, 0.5)'),
    ('rgb(154, 205,  50)', 'rgba(154, 205,  50, 0.5)'),
    ('rgb(148,   0, 211)', 'rgba(148,   0, 211, 0.5)'),
]

app = Flask(__name__)


# ---------------------------------------------------------------------------
# データ読み込み
# ---------------------------------------------------------------------------
def _read_pickle(name: str):
    with open(PKL_DIR / name, mode='rb') as f:
        return pickle.load(f)


def read_monthly_data() -> Dict[str, pd.DataFrame]:
    """
    {
        "balance_and_cashflow": pd.DataFrame,
        "transaction": pd.DataFrame,
        "income": pd.DataFrame,
        "expense": pd.DataFrame
    }
    を返す
    """
    return _read_pickle('monthly_data.pkl')


def read_yearly_data() -> Dict[str, pd.DataFrame]:
    """
    {
        "balance_and_cashflow": pd.DataFrame,
        "transaction": pd.DataFrame,
        "income": pd.DataFrame,
        "expense": pd.DataFrame
    }
    を返す
    """
    return _read_pickle('yearly_data.pkl')


def read_forecast_data() -> pd.DataFrame:
    return _read_pickle('forecast_data.pkl')


def read_category_data() -> Dict[str, Dict[str, str]]:
    """
    {
        "major_expense_category_to_leaf_categories": Dict[str, str],
        "minor_expense_category_to_leaf_categories": Dict[str, str]
    }
    """
    return _read_pickle('category_data.pkl')


def read_config() -> Dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------
def _json(obj):
    return json.dumps(obj, ensure_ascii=False)


def _color(i: int, shade: int=0):
    """shade: 0 = 実線色, 1 = 半透明色"""
    return COLORS[i % len(COLORS)][shade]


def _split_param(value: str) -> List[str]:
    """'a,b,c' -> ['a', 'b', 'c'] (未指定・空なら [])。"""
    return value.split(",") if value else []


def _yen(value : str | int) -> str:
    """数字にカンマを入れて見やすくする
    1000000 -> 1,000,000
    """
    return "{:,}".format(int(value))


def _read_by_period(unit: Literal["year", "month"]) -> Tuple[Dict[str, pd.DataFrame], str]:
    """'year' / 'month' からデータと先頭列ラベルを返す (index.html 用)。"""
    if unit == 'year':
        return read_yearly_data(), '年度'
    elif unit == 'month':
        return read_monthly_data(), '月'
    raise ValueError(f"Invalid value for unit: {unit!r}.")


def _read_by_key(year_month: str):
    """キーの長さで月次/年次を判別する (month.html 用)。
    year_monthの例: 2026, 202601
    """
    if len(year_month) == 6:
        return read_monthly_data()
    elif len(year_month) == 4:
        return read_yearly_data()
    raise ValueError(f"Invalid value for year_month: {year_month!r}.")


# ---------------------------------------------------------------------------
# 除外項目の算出
# ---------------------------------------------------------------------------
def _unselected(candidates: List[str], selected: List[str]) -> List[str]:
    """candidateの中で、selectedに該当しないものを抽出"""
    return [item for item in candidates if item not in selected]


def _balance_exclude_items(params):
    """収支: 選択されていない大型項目を除外する。"""
    large_items: List = read_config()[LARGE_ITEMS_KEY]
    return _unselected(large_items, _split_param(params.get("large")))


def _expense_exclude_items(params):
    """支出カテゴリ: 支出側に存在する大型項目のうち、選択されていないものを除外する。"""
    large_items: List = read_config()[LARGE_ITEMS_KEY]  # 大型項目（収支問わず）
    mapping = read_category_data()["minor_expense_category_to_leaf_categories"]
    expense_items = chain.from_iterable(mapping.values())   # 支出項目
    large_expense_items = [item for item in expense_items if item in large_items]   # 大型支出項目
    return _unselected(large_expense_items, _split_param(params.get("largeExpense")))




# ---------------------------------------------------------------------------
# DataFrame 生成
# ---------------------------------------------------------------------------
def _asset_frame(data):
    return data["balance_and_cashflow"].drop(columns=BALANCE_COLUMNS)


def _major_expense_frame(data, category_data, exclude_items=()):
    mapping = category_data["major_expense_category_to_leaf_categories"]
    expense = data["expense"]
    return pd.DataFrame({
        name: expense[[col for col in cols if col not in exclude_items]].sum(axis=1)
        for name, cols in mapping.items()
    })


def _minor_expense_frame(data, category_data, option):
    mapping = category_data["minor_expense_category_to_leaf_categories"]
    return data["expense"][list(mapping.values())[int(option)]]


def _balance_frame(data, exclude_items, window=1):
    """収入・支出の集計 (index.html の balance 用)。"""
    df = data["transactions"].copy()
    df = df[~df.index.get_level_values(1).isin(exclude_items)]
    df = (
        df.groupby(level="yyyymm")[["入金", "出金"]]
        .sum()
        .rename(columns={"入金": "収入", "出金": "支出"})
    )
    df["収支"] = df["収入"] - df["支出"]
    return df.rolling(window).mean().fillna(0).astype(int)

def _with_moving_average(df, unit):
    """列が1本だけの df に、unit に応じた移動平均の列を追加して返す。"""
    if len(df.columns) != 1:
        return df
    window, label = MA_SETTINGS[unit]
    out = df.copy()
    out[label] = df.iloc[:, 0].rolling(window).mean().round().fillna(0).astype(int)
    return out


def _index_frame(data: Dict[str, pd.DataFrame], unit: str, target: str, params) -> pd.DataFrame:
    """index.html の表・グラフ共通の DataFrame を返す (balance を含む)。"""
    if target == "balance":
        exclude_items = _balance_exclude_items(params)
    elif target == "expense_category":
        exclude_items = _expense_exclude_items(params)
    else:
        exclude_items = []

    if target == "balance":
        if params.get("checkedMA") == "true":
            window = MA_SETTINGS[unit][0]
        else:
            window = 1
        return _balance_frame(data, exclude_items, window)
    if target == "asset":
        return _asset_frame(data)
    if target == "expense_category":
        return _major_expense_frame(data, read_category_data(), exclude_items)
    if target == "expense_subcategory":
        df = _minor_expense_frame(data, read_category_data(), params.get("num"))
        return _with_moving_average(df, unit)
    if target == "income":
        return data["income"]
    raise ValueError(f"Invalid value for target: {target!r}.")


# ---------------------------------------------------------------------------
# グラフ・表の整形
# ---------------------------------------------------------------------------
def _values(series):
    """NaN を None (JSON の null) にして list 化する。"""
    return [None if pd.isna(v) else v for v in series.tolist()]


def _stacked_line_chart(df, hidden_columns=()):
    """積み上げ折れ線グラフの Chart.js 設定を作る (index / forecast 共通)。"""
    datasets = []
    for i, column in enumerate(df.columns):
        if column in MA_LABELS:
            datasets.append({
                "label": column,
                "data": _values(df[column]),
                "fill": False,
                "borderColor": "rgb(0, 0, 0)",
                "borderDash": [6, 4],
            })
            continue

        dataset = {
            "fill": True if i == 0 else "-1",
            "backgroundColor": _color(i, 1),
            "borderColor": _color(i, 0),
            "label": column,
            "data": _values(df[column]),
        }
        if column in hidden_columns:
            dataset["hidden"] = True
        datasets.append(dataset)
    has_ma = any(c in MA_LABELS for c in df.columns)
    return {
        "type": "line",
        "options": {
            "elements": {"line": {"tension": 0.0001}},
            "scales": {"yAxes": [{"stacked": not has_ma, "ticks": {"beginAtZero": True}}]},
            "legend": {"display": True},
        },
        "data": {"labels": df.index.tolist(), "datasets": datasets},
    }



def _balance_chart(df):
    """収入・支出 (折れ線) + 収支 (棒) のグラフ設定を作る。"""
    datasets = []
    for i, column in enumerate(df.columns):
        if column == "収支":
            dataset = {"type": "bar", "backgroundColor": _color(i)}
        else:
            dataset = {"type": "line", "fill": False, "borderColor": _color(i)}
        dataset.update(label=column, data=df[column].tolist())
        datasets.append(dataset)

    return {
        "type": "bar",
        "data": {"labels": df.index.tolist(), "datasets": datasets},
        "options": {
            "responsive": True,
            "tooltips": {"mode": "index", "intersect": True},
            "elements": {"line": {"tension": 0.0001}},
            "scales": {"yAxes": [{"ticks": {"beginAtZero": True}}]},
        },
    }


def _pie_chart(df, row_key):
    values = df.loc[row_key, :].values.copy()
    values[values < 0] = 0
    return {
        "type": "pie",
        "options": {"responsive": True},
        "data": {
            "datasets": [{
                "data": values.tolist(),
                "backgroundColor": [_color(i) for i in range(len(df.columns))],
            }],
            "labels": df.columns.tolist(),
        },
    }


def _format_table(df, header):
    """DataFrame を [ヘッダ, 新しい行→古い行...] の表形式に変換する。"""
    out = [[header, *df.columns]]
    for index in reversed(df.index.tolist()):
        out.append([index, *("{:,}".format(df.loc[index, c]) for c in df.columns)])
    return out


# ---------------------------------------------------------------------------
# 共通用
# ---------------------------------------------------------------------------
@app.route('/getExpenseSubcategory')
def get_expense_subcategory():
    data = read_category_data()
    return _json(list(data["minor_expense_category_to_leaf_categories"].keys()))


@app.route('/getMonth')
def get_month():
    return _json(read_monthly_data()["balance_and_cashflow"].index.tolist())


@app.route('/getYear')
def get_year():
    return _json(read_yearly_data()["balance_and_cashflow"].index.tolist())


@app.route('/get_large_items')
def get_large_items():
    return _json(read_config()[LARGE_ITEMS_KEY])


@app.route('/get_large_expense_items')
def get_large_expense_items():
    large_items = read_config()[LARGE_ITEMS_KEY]
    mapping = read_category_data()["minor_expense_category_to_leaf_categories"]
    return _json([
        category
        for category in chain.from_iterable(mapping.values())
        if category in large_items
    ])


# ---------------------------------------------------------------------------
# index.html 用
# ---------------------------------------------------------------------------
@app.route('/getTable_index/<unit>/<target>/')
def get_table_index(unit, target):
    data, col = _read_by_period(unit)
    df = _index_frame(data, unit, target, request.args)
    return _json(_format_table(df, col))


@app.route('/getGraph_index/<unit>/<target>/')
def get_graph_index(unit, target):
    data, _ = _read_by_period(unit)
    df = _index_frame(data, unit, target, request.args)

    if target == "balance":
        return _json(_balance_chart(df))

    if target == "expense_category":
        large_items = set(read_config()[LARGE_ITEMS_KEY])
        mapping = read_category_data()["major_expense_category_to_leaf_categories"]
        hidden = [k for k, v in mapping.items() if large_items & set(v)]
    elif target in ("income", "expense_subcategory"):
        hidden = read_config()[LARGE_ITEMS_KEY]
    else:
        hidden = []
    return _json(_stacked_line_chart(df, hidden_columns=hidden))

# ---------------------------------------------------------------------------
# month.html 用
# ---------------------------------------------------------------------------
@app.route('/getGraph_snapMonth/<target>/<year_month>')
def get_graph_snap_month(target, year_month):
    data = _read_by_key(year_month)
    if target == "expense":
        df = _major_expense_frame(data, read_category_data())
    elif target == "income":
        df = data["income"]
    else:
        raise ValueError(f"Invalid value for target: {target!r}.")
    return _json(_pie_chart(df, year_month))


@app.route('/getTable_snapMonth/<slct>/<year_month>')
def get_table_snap_month(slct, year_month):
    data = _read_by_key(year_month)
    if slct == "income":
        df = data["income"]
    elif slct == "expense":
        df = data["expense"]
    elif slct == "balance":
        df = data["balance_and_cashflow"].loc[:, BALANCE_COLUMNS]
    else:
        raise ValueError(f"Invalid value for slct: {slct!r}.")

    out = [["項目", "金額"]]
    out.extend([col, _yen(df.loc[year_month, col])] for col in df.columns)
    return _json(out)


# ---------------------------------------------------------------------------
# forecast.html 用
# ---------------------------------------------------------------------------
@app.route('/getTable_forecast')
def get_table_forecast():
    df = read_forecast_data()
    out = [["月", "実績", "予測"]]
    out.extend(
        [month, _yen(df.loc[month, "実績"]), _yen(df.loc[month, "予測"])]
        for month in reversed(df.index)
    )
    return _json(out)


@app.route('/getGraph_forecast')
def get_graph_forecast():
    return _json(_stacked_line_chart(read_forecast_data()))


# ---------------------------------------------------------------------------
# render_template 用
# ---------------------------------------------------------------------------
@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')


@app.route('/forecast')
def forecast():
    return render_template('forecast.html')


@app.route('/month')
def month():
    return render_template('month.html')


@app.route('/menu')
def menu():
    return render_template('menu.html')


if __name__ == '__main__':
    app.debug = True
    app.run(port=5000)