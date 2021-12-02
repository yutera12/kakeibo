# 家計簿ビューア
## 概要
* エクセルで作成した家計簿を[サンプルページ](https://yutera12.github.io/kakeibo)のように見ることができます。
* 初心者が勉強用に作ったものです。

## ソースコード
* `calc.py`
  * エクセルデータ、設定ファイルをもとに、エクセルのデータを要約したデータ(pikle形式)を作成
  * 使用した主なライブラリは`pandas`
* `server.py`
  * 要約したデータを元に、各種APIを提供
  * 使用した主なライブラリは`flask`
  * APIの一覧は下表
  * APIへのアクセス結果は`curl`コマンドで確かめることができる。
    * `curl http://localhost:5000/getMonth`
    * `curl --noproxy localhost http://localhost:5000/getMonth`

    | URL | 機能 |
    | --- | --- |
    | `/index` | `index.html`の表示 | 
    | `/month` | `month.html`の表示 | 
    | `/future` | `future.html`の表示 | 
    | `/getOut2` | 支出小項目の項目一覧を返す |
    | `/getMonth` | 表示対象の月の一覧を返す |
    | `/getYear` | 表示対象の年の一覧を返す |
    | `/getTable_index/<item>` | `index.html`で使用するテーブルのデータを返す |
    | `/getGraph_index/<item>` | `index.html`で使用するテーブルのグラフを返す |
    | `/getGraph_snapMonth/<slct>/<my>` | `month.html`で使用するテーブルのデータを返す |
    | `/getTable_snapMonth/<slct>/<my>` | `month.html`で使用するテーブルのグラフを返す |
    | `/getTable_future` | `future.html`で使用するテーブルのデータを返す |
    | `/getGraph_future` | `future.html`で使用するテーブルのグラフを返す |

* `index.html`, `future.html`, `month.html`
  * それぞれ推移ページ、月毎・年毎ページ、予測ページ用のhtmlファイル
  * 使用した主なライブラリは、`boostrap4`、`vue`、`chartjs`

## 入力
#### エクセルで作成した家計簿
* エクセルのテーブルは以下のカラムを含む必要がある。
  * yyyymm
  * 分類
  * 入金
  * 残高

* イメージは以下の通り。

    |yyyymm|dd|品名|分類|入金|出金|残高|
    |---|---|---|---|---|---|---|
    |201704|1|||||6978|
    |201704|15|りんご|食料品||200|6778|
    |201704|18|専門書|教育教養||1500|5278|
    |201704|20|ATMで引き出し|移動|50000||55278|
    |...|...|...|...|...|...|...|

* 複数、口座、財布がある場合は複数のシートに記述する。
* サンプルは[こちら](https://github.com/yutera12/kakeibo/blob/master/sample/kakeibo.xlsx)。

#### 設定ファイル
* ビューアで表示する期間や、収入、支出の項目をyaml形式で記載する。
* サンプルは[こちら](https://github.com/yutera12/kakeibo/blob/master/sample/config.yaml)。
  
## ビューアの起動方法
1. `python calc.py`
1. `python server.py`
1. ブラウザの窓に`http://localhost:5000/index`と打ち込み実行
