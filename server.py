from flask import Flask, render_template, request, redirect, url_for, make_response, jsonify
import werkzeug
import json
import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime
import yaml

def read_df_month():
    with open('df_month.pkl', mode='rb') as f:
        df = pickle.load(f)
    return df

def read_df_year():
    with open('df_year.pkl', mode='rb') as f:
        df = pickle.load(f)
    return df

def read_df_future():
    with open('df_future.pkl', mode='rb') as f:
        df = pickle.load(f)
    return df

colors = [
    ['rgb(  0,   0, 255)', 'rgba(  0,   0, 255, 0.5)'],
    ['rgb(  0, 203, 255)', 'rgba(  0, 203, 255, 0.5)'],
    ['rgb(255, 255,   0)', 'rgba(255, 255,   0, 0.5)'],
    ['rgb(216, 255, 204)', 'rgba(216, 255, 204, 0.5)'],
    ['rgb(  0, 255,   0)', 'rgba(  0, 255,   0, 0.5)'],
    ['rgb(  0, 101,   0)', 'rgba(  0, 101,   0, 0.5)'],
    ['rgb(255,  63,   0)', 'rgba(255,  63,   0, 0.5)'],
    ['rgb( 203,  0, 203)', 'rgba( 203,  0, 203, 0.5)'],
    ['rgb(  0,   0,  50)', 'rgba(  0,   0,  50, 0.5)']
]

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False 

#########
# 共通用 #
#########
@app.route('/getOut2')
def getOut2():
    df = read_df_month()
    return json.dumps(df["out2"].columns.tolist(), ensure_ascii=False)

@app.route('/getMonth')
def getMonth():
    df = read_df_month()
    return json.dumps(df["basic"].index.tolist(), ensure_ascii=False)

@app.route('/getYear')
def getYear():
    df = read_df_year()
    return json.dumps(df["basic"].index.tolist(), ensure_ascii=False)

################
# index.html用 #
################
@app.route('/getTable_index/<my>/<item>/')
def getTable_index(my, item):
    slct, out2Num = item.split(",")
    if my == 'year':
        df = read_df_year()
        col = '年度'
    elif my == 'month':
        df = read_df_month()
        col = '月'
    if slct == "asset":
        df = df["basic"].drop(columns=["収入", "支出", "収支"])
    elif slct == "inout":
        df = df["basic"].drop(columns="資産")
    elif slct == "out1":
        df = df["out1"]
    elif slct == "out2":
        df = df["out2"].loc[:, [df["out2"].columns[int(out2Num)]]]
    elif slct == "in":
        df = df["in"]
    out = []
    out.append([])
    out[-1].append(col)
    for column in df.columns:
        out[-1].append(column)
    for index in reversed(df.index.tolist()):
        out.append([])
        out[-1].append(index)
        for column in df.columns:
            out[-1].append("{:,}".format(df.loc[index, column]))
    return json.dumps(out, ensure_ascii=False)

@app.route('/getGraph_index/<my>/<item>/')
def getGraph_index(my, item):
    slct, out2Num = item.split(",")
    if my == 'year':
        df = read_df_year()
    elif my == 'month':
        df = read_df_month()
    if slct == "inout":
        df = df["basic"].drop(columns="資産")
        chartData = {}
        chartData["labels"] = df.index.tolist()
        chartData["datasets"] = []
        for i, column in enumerate(df.columns):
            chartData["datasets"].append({})
            if i == 2:
                chartData["datasets"][-1]["type"] = "bar"
                chartData["datasets"][-1]["backgroundColor"] = colors[i % len(colors)][0]
            else:
                chartData["datasets"][-1]["type"] = "line"
                chartData["datasets"][-1]["fill"] = False
                chartData["datasets"][-1]["borderColor"] = colors[i % len(colors)][0]
            chartData["datasets"][-1]["label"] = column
            chartData["datasets"][-1]["data"] = df.loc[:, column].tolist()
        out = {}
        out["type"] = "bar"
        out["data"] = chartData
        out["options"] = {"responsive": True, "tooltips": {"mode": "index", "intersect": True},
                          "elements": {"line": {"tension": 0.0001}},
                          "scales"  : {"yAxes": [{"ticks": {"beginAtZero": True}}]}
                         }
    else:
        if slct == "out1":
            df = df["out1"]
        elif slct == "out2":
            df = df["out2"].loc[:, [df["out2"].columns[int(out2Num)]]]
        elif slct == "in":
            df = df["in"]
        elif slct == "asset":
            df = df["basic"].drop(columns=["収入", "支出", "収支"])
        out = {}
        out["type"] = "line"
        out["options"] = {"elements": {"line": {"tension": 0.0001}},
                          "scales"  : {"yAxes":[{"stacked": True, "ticks": {"beginAtZero": True}}]},
                          "legend": {"display": True}
                         }
        out["data"] = {}
        out["data"]["labels"] = df.index.tolist()
        out["data"]["datasets"] = []
        for i, column in enumerate(df.columns):
            out["data"]["datasets"].append({})
            if i == 0:
                out["data"]["datasets"][-1]["fill"] = True
            else:
                out["data"]["datasets"][-1]["fill"] = "-1"
            out["data"]["datasets"][-1]["backgroundColor"] = colors[i % len(colors)][1]
            out["data"]["datasets"][-1]["borderColor"] = colors[i % len(colors)][0]
            out["data"]["datasets"][-1]["label"] = column
            out["data"]["datasets"][-1]["data"] = df.loc[:, column].tolist()
    return json.dumps(out, ensure_ascii=False)

################
# month.html用 #
################
@app.route('/getGraph_snapMonth/<slct>/<my>')
def getGraph_snapMonth(slct, my):
    if len(my) == 6:
        df = read_df_month()
    elif len(my) == 4:
        df = read_df_year()
    else:
        df = df_month
    if slct == "out":
        df = df["out1"]
    elif slct == "in":
        df = df["in"]
    if my == "undefined":
        my = df.index[-1]
    con = {}
    con["type"] = "pie"
    con["options"] = {"responsive": True}
    con["data"] = {}
    con["data"]["datasets"] = [{}]
    tmp = df.copy().loc[my, :].values
    tmp[tmp < 0] = 0
    con["data"]["datasets"][0]["data"] = tmp.tolist()
    con["data"]["datasets"][0]["backgroundColor"] = [colors[i % len(colors)][0] for i in range(len(df.columns))]
    con["data"]["labels"] = df.columns.tolist()
    return json.dumps(con, ensure_ascii=False)

@app.route('/getTable_snapMonth/<slct>/<my>')
def getTable_snapMonth(slct, my):
    if len(my) == 6:
        df = read_df_month()
    elif len(my) == 4:
        df = read_df_year()
    else:
        df = df_month
    if slct == "in":
        df = df["in"]
    elif slct == "out":
        df = df["out2"]
    elif slct == "inout":
        df = df["basic"].drop(columns="資産")
    if my == "undefined":
        my = df.index[-1]
    out = []
    out.append([])
    out[-1].append("項目")
    out[-1].append("金額")
    for col in df.columns:
        out.append([])
        out[-1].append(col)
        out[-1].append("{:,}".format(int(df.loc[my, col])))
    return json.dumps(out, ensure_ascii=False)

#################
# future.html用 #
#################
@app.route('/getTable_future')
def getTable_future():
    df_future = read_df_future()
    out = []
    out.append([])
    out[-1].append("月")
    out[-1].append("実績")
    out[-1].append("予測")
    for month in reversed(df_future.index):
        out.append([])
        out[-1].append(month)
        out[-1].append("{:,}".format(int(df_future.loc[month, "実績"])))
        out[-1].append("{:,}".format(int(df_future.loc[month, "予測"])))
    return json.dumps(out, ensure_ascii=False)

@app.route('/getGraph_future')
def getGraph_future():
    df_future = read_df_future()
    out = {}
    out["type"] = "line"
    out["options"] = {"elements": {"line": {"tension": 0.0001}},
                      "scales"  : {"yAxes":[{"stacked": True, "ticks": {"beginAtZero": True}}]},
                      "legend": {"display": True}
                      }
    out["data"] = {}
    out["data"]["labels"] = df_future.index.tolist()
    out["data"]["datasets"] = []
    for i, column in enumerate(df_future.columns):
        out["data"]["datasets"].append({})
        if i == 0:
            out["data"]["datasets"][-1]["fill"] = True
        else:
            out["data"]["datasets"][-1]["fill"] = "-1"
        out["data"]["datasets"][-1]["backgroundColor"] = colors[i % len(colors)][1]
        out["data"]["datasets"][-1]["borderColor"] = colors[i % len(colors)][0]
        out["data"]["datasets"][-1]["label"] = column
        out["data"]["datasets"][-1]["data"] = df_future.loc[:, column].tolist()
    return json.dumps(out, ensure_ascii=False)

###############
# menu.html用 #
###############
@app.route('/get_config', methods=['GET'])
def read_config():
    with open('config.yaml', "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return json.dumps(config, ensure_ascii=False)

@app.route('/post_config', methods=['POST'])
def upload_config():
    conf = yaml.safe_load(request.data.decode('utf-8'))
    sishutu = yaml.safe_load(conf['sishutu'])
    print(conf)
    shunyu = yaml.safe_load(conf['shunyu'])
    start = conf['start']
    finish = conf['finish']
    current = conf['current']
    with open('config.yaml', 'w', encoding='utf-8') as f:
        yaml.dump({'開始月': start,
                   '締め月': finish,
                   '現在月': current,
                   '収入項目': shunyu,
                   '支出項目': sishutu}, f, encoding='utf8', allow_unicode=True)
    return 'OK'

app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024
@app.route('/data/upload', methods=['POST'])
def upload_multipart():
    if not 'yourFileKey' in request.files.keys():
        return make_response(jsonify({'result':'アップロードが失敗しました'}))
    file = request.files['yourFileKey']
    fileName = file.filename
    dir = 'upload'
    os.makedirs(dir, exist_ok=True)
    file.save(os.path.join(dir, 'data'))
    return make_response(jsonify({'result':'アップロードが完了しました'}))

@app.route('/execute', methods=['POST'])
def execute():
    import calc
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default="config.yaml")
    parser.add_argument('--data', default="upload/data")
    args = parser.parse_args()
    calc.main(args)
    return "OK"

#####################
# render_template用 #
#####################
@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/future')
def future():
    return render_template('future.html')

@app.route('/month')
def month():
    return render_template('month.html')

@app.route('/menu')
def menu():
    return render_template('menu.html')

if __name__ == '__main__':
    app.debug = True
    app.run(port=5000)