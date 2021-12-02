import pandas as pd
import numpy as np
import openpyxl
import yaml

def calcMonthList(startMonth, finishMonth):
    y = startMonth[0]
    m = startMonth[1]
    yearList = []
    monthList = []
    while True:
        monthList.append(str(100 * y + m))
        if [y, m] == [finishMonth[0], finishMonth[1]]:
            break
        y, m = nextMonth(y, m)
    return monthList

def nextMonth(y, m):
    m = m + 1
    if m == 13:
        m = 1
        y = y + 1
    return (y, m)

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.load(f)

monthList = calcMonthList(config["開始月"], config["締め月"])
itemList = [
    ["電気", 4000, 20000],
    ["ガス", 4000, 20000],
    ["水道", 4000, 20000],
    ["通信", 4000, 20000],
    ["住居", 100000, 200000],
    ["保険", 10000, 20000],
    ["医療", 5000, 20000],
    ["食料品", 50000, 100000],
    ["日用雑貨", 10000, 20000],
    ["交通", 10000, 20000],
    ["娯楽", 10000, 500000],
    ["交際", 15000, 100000],
    ["その他", 10000, 20000],
    ["給与A", -600000, -500000],
    ["給与B", -200000, -100000]]

zandaka = 10000000
data = []
data.append([monthList[0], "*", "*", "", "", "", zandaka])
for month in monthList:
    for item in itemList:
        val = np.random.randint(item[1], item[2])
        zandaka = zandaka - val
        if val >= 0:
            data.append([month, "*", "*", item[0], "", val, zandaka])
        else:
            data.append([month, "*", "*", item[0], -val, "", zandaka])
    zandaka = zandaka - 50000
    data.append([month, "*", "*", "移動", "", 50000, zandaka])
df1 = pd.DataFrame(data, columns = ["yyyymm", "dd", "品名", "分類", "入金", "出金", "残高"])

zandaka = 1000000
data = []
data.append([monthList[0], "*", "*", "", "", "", zandaka])
for month in monthList:
    for item in [["娯楽", 10000, 20000], ["交際", 15000, 25000]]:
        val = np.random.randint(item[1], item[2])
        zandaka = zandaka - val
        if val >= 0:
            data.append([month, "*", "*", item[0], "", val, zandaka])
        else:
            data.append([month, "*", "*", item[0], -val, "", zandaka])
    zandaka = zandaka + 50000
    data.append([month, "*", "*", "移動", 50000, "", zandaka])
df2 = pd.DataFrame(data, columns = ["yyyymm", "dd", "品名", "分類", "入金", "出金", "残高"])


with pd.ExcelWriter('kakeibo.xlsx') as writer:
    df1.to_excel(writer, sheet_name='kouza1', index=False)
    df2.to_excel(writer, sheet_name='kouza2', index=False)
