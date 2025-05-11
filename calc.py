import yaml
import pandas as pd
import numpy as np
from tqdm import tqdm
from pprint import pprint
import argparse
import pickle

def none2int(val):
    if val is None:
        output = 0
    else:
        output = int(val)
    return output

def calcMonthList(startMonth, finishMonth):
    y = startMonth[0]
    m = startMonth[1]
    yearList = []
    monthList = []
    while True:
        if len(yearList) == 0 or yearList[-1][0] != str(int(np.floor((100 * y + m - 4) / 100))):
            yearList.append([str(int(np.floor((100 * y + m - 4) / 100))), [str(100 * y + m)]])
        else:
            yearList[-1][1].append(str(100 * y + m))
        monthList.append(str(100 * y + m))
        if [y, m] == [finishMonth[0], finishMonth[1]]:
            break
        y, m = nextMonth(y, m)
    return {"月": monthList, "年度+月": yearList}

def nextMonth(y, m):
    m = m + 1
    if m == 13:
        m = 1
        y = y + 1
    return (y, m)


def main(args):
    # configファイルの読み込み
    print("--configファイルの読み込み中--")
    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert config["開始月"] <= config["締め月"] <= config["現在月"]

    out2List = [item for _, items in config["支出項目"] for item in items]
    out1List = [category for category, _ in config["支出項目"] if category != "NA"]

    # エクセルファイルの読み込み
    print('--エクセルファイルの読み込み中--')
    df_origin = pd.read_excel(args.data, sheet_name=None)
    sheetNameList = list(df_origin.keys())
    for i, sheetName in enumerate(sheetNameList):
        df_tmp = df_origin[sheetName]
        # "項目チェック"
        assert  "yyyymm" in df_tmp.columns and\
                "分類" in df_tmp.columns and\
                "入金" in df_tmp.columns and\
                "出金" in df_tmp.columns and\
                "残高" in df_tmp.columns, "{}シートのカラム名が不適切です".format(sheetName)
        for j, x in enumerate(df_tmp["分類"].values):
            if j == 0:
                assert np.isnan(x), "{}シートの１行目のデータには残高のみ記載してください".format(sheetName)
            else:
                assert x == "移動" or x in config["収入項目"] + out2List, "{}シートの{}行目のデータの分類「{}」が不適切です".format(sheetName, j, x)
        for j, x in enumerate(df_tmp["yyyymm"].values):
            assert not np.isnan(x), "{}シートの{}行目のデータのyyyymmが入力されていません。".format(sheetName, j)
        for j in range(len(df_tmp)):
            assert 190000 < df_tmp.loc[j, "yyyymm"] < 210000, f"{sheetName}のyyyymmが不正"
        for j in range(len(df_tmp) - 1):
            assert df_tmp.loc[j, "yyyymm"] <= df_tmp.loc[j + 1, "yyyymm"], f"{sheetName}のyyyymmが不正"

        prev_zandaka = df_tmp.loc[0, "残高"]       
        for month in calcMonthList(config["開始月"], config["現在月"])["月"]:
            if len(df_tmp.loc[df_tmp["yyyymm"] == month, :]) == 0:
                continue
            zandaka = df_tmp.loc[df_tmp["yyyymm"] == month, "残高"].iloc[-1]
            nyukin = sum(df_tmp.loc[df_tmp["yyyymm"] == month, "入金"])
            shukkin = sum(df_tmp.loc[df_tmp["yyyymm"] == month, "出金"])
            assert prev_zandaka + nyukin - shukkin == zandaka, f"{sheetName}の"
            prev_zandaka = zandaka


        df_tmp["sheet"] = sheetNameList[i]
        df_tmp = df_tmp.astype({'yyyymm': str})
        if i == 0:
            df_data = df_tmp
        else:
            df_data = pd.concat([df_data, df_tmp])

    df_item = pd.DataFrame([(y, x[0]) for x in config["支出項目"] for y in x[1]], columns=["分類", "大分類"])
    df_data = pd.merge(df_data, df_item, on="分類", how="left")   # 元のエクセルデータ
    # 移動のチェック
    for month in calcMonthList(config["開始月"], config["現在月"])["月"]:
        nyukin = int(df_data.query('yyyymm==@month & 分類=="移動"')["入金"].sum())
        shukkin = int(df_data.query('yyyymm==@month & 分類=="移動"')["出金"].sum())
        assert nyukin == shukkin, f"{month}の移動のデータが不整合です。入金が{nyukin}、出金が{shukkin}"

    # 計算
    print( "--計算中--")
    df_month = {}
    df_month["basic"] = pd.DataFrame(0, index=calcMonthList(config["開始月"], config["現在月"])["月"], columns=["資産", "収入", "支出", "収支"])
    df_month["in"] = pd.DataFrame(0, index=calcMonthList(config["開始月"], config["現在月"])["月"], columns=[x for x in config["収入項目"]])
    df_month["out2"] = pd.DataFrame(0, index=calcMonthList(config["開始月"], config["現在月"])["月"], columns=[x for x in out2List])
    df_month["out1"] = pd.DataFrame(0, index=calcMonthList(config["開始月"], config["現在月"])["月"], columns=[x for x in out1List if x != "NA"])
    for sheetName in sheetNameList:
        zandakaOld = 0
        for month in df_month["basic"].index:
            zan = df_data.query('yyyymm==@month and sheet==@sheetName')["残高"].values
            if len(zan) == 0:
                df_month["basic"].loc[month, "資産"] += zandakaOld
            else:
                df_month["basic"].loc[month, "資産"] += int(zan[-1])
                zandakaOld = int(zan[-1])
    for month in tqdm(df_month["basic"].index):
        nyukin = (df_data.query('yyyymm==@month & 分類!="移動"')["入金"].sum())
        shukkin = (df_data.query('yyyymm==@month & 分類!="移動"')["出金"].sum())
        df_month["basic"].loc[month, "収入"] = none2int(nyukin)
        df_month["basic"].loc[month, "支出"] = none2int(shukkin)
        df_month["basic"].loc[month, "収支"] = none2int(nyukin) - none2int(shukkin)
        for item in config["収入項目"]:
            nyukin = df_data.query('分類==@item and yyyymm==@month')['入金'].sum()
            df_month["in"].loc[month, item] = none2int(nyukin)
            assert df_data.query('分類==@item and yyyymm==@month')['出金'].sum() == 0.0, \
                   "エラー\n{}の{}について入金項目にもかかわらず出金の列に記入されています。".format(month, item)
        for item in out2List:
            shukkin = df_data.query('分類==@item and yyyymm==@month')['出金'].sum()
            df_month["out2"].loc[month, item] = none2int(shukkin)
            assert df_data.query('分類==@item and yyyymm==@month')['入金'].sum() == 0.0, \
                   "エラー\n{}の{}について出金項目にもかかわらず入金の列に記入されています。".format(month, item)
        for item in [x for x in out1List if x != "NA"]:
            if item != "NA":
                shukkin = df_data.query('大分類==@item and yyyymm==@month')["出金"].sum()
                df_month["out1"].loc[month, item] = none2int(shukkin)
    # 収支のチェック
    monthOld = None
    for month in calcMonthList(config["開始月"], config["現在月"])["月"]:
        if monthOld != None:
            assert df_month["basic"].loc[month, "資産"] - df_month["basic"].loc[monthOld, "資産"] == df_month["basic"].loc[month, "収支"], \
                  "エラー\n{}の資産は{}\n{}の資産は{}\n差額は{}\nしかし{}の収支が{}です。".format(\
                          monthOld, df_month["basic"].loc[monthOld, "資産"], month,  df_month["basic"].loc[month, "資産"],\
                          df_month["basic"].loc[month, "資産"] - df_month["basic"].loc[monthOld, "資産"],\
                          month,  df_month["basic"].loc[month, "収支"])
        monthOld = month

    # 年用
    yearList = calcMonthList(config["開始月"], config["現在月"])["年度+月"]
    df_year = {}
    for key in df_month.keys():
        df_year[key] = pd.DataFrame(0, index=[year[0] for year in yearList], columns=df_month[key].columns)
        for col in df_year[key].columns:
            for year in yearList:
                x = 0
                for month in year[1]:
                    if col == '資産':
                        x = int(df_month[key][col][month])
                    else:
                        x += int(df_month[key][col][month])
                df_year[key].loc[str(year[0]), col] = x

    # 予測
    futureMonth = config["現在月"]
    for _ in range(60):
        futureMonth = nextMonth(futureMonth[0], futureMonth[1])
    index = calcMonthList(config["開始月"], [futureMonth[0], futureMonth[1]])["月"]
    df_future = pd.DataFrame(0, index=index, columns=["実績", "予測"])
    shusiPredict = {}
    for month in calcMonthList(config["開始月"], config["締め月"])["月"]:
        shusiPredict[month[4:7]] = df_month["basic"].loc[month, "収支"]
    zandaka = df_month["basic"]['資産']
    money_old = 0
    for month in df_future.index:
        money = zandaka.get(month)
        if month in calcMonthList(config["開始月"], config["締め月"])["月"]:
            df_future.loc[month, "実績"] = money
            df_future.loc[month, "予測"] = 0
        else:
            money = money_old + shusiPredict[month[4:7]]
            df_future.loc[month, "実績"] = 0
            df_future.loc[month, "予測"] = money
        money_old = money
    print("--計算終了--")
    with open("df_month.pkl", mode='wb') as f:
      pickle.dump(df_month, f)
    with open("df_year.pkl", mode='wb') as f:
      pickle.dump(df_year, f)
    with open("df_future.pkl", mode='wb') as f:
      pickle.dump(df_future, f)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default="sample/config.yaml")
    parser.add_argument('--data', default="sample/kakeibo.xlsx")
    args = parser.parse_args()
    main(args)
