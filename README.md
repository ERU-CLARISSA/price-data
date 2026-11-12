# price-data

価格記録アプリ（09_price_app）が読む、公的な価格データの配信用リポジトリ（GitHub Actions ＋ GitHub Pages）。
アプリはここの JSON を読むだけ。取り込み元は公的データだけ。

配信先（予定）：https://eru-clarissa.github.io/price-data/v1/index.json

## ファイル（`v1/`）
| ファイル | 中身 | 元 | 更新 |
|---|---|---|---|
| `index.json` | 各ファイルの sha256・大きさ・データの日付。アプリはハッシュが変わったファイルだけ取る | — | 毎回 |
| `maff_weekly.json` | 野菜の全国平均の店頭価格（円/kg、週の月曜の日付）2017-11〜 | 農林水産省 食品価格動向調査（野菜）の Excel | 週 |
| `outlook.json` | 今月の価格見通し（-2〜2 の 5 段階、前半・後半）と理由・主産地 | 農林水産省 野菜の生育状況及び価格見通し（PDF の表） | 月 |
| `otoku.json` | 今週のお手頃野菜（best＝大変お買い得、good＝お買い得・平年を下回る） | 農林水産省 今週のお手頃野菜（ページの文） | 週 |
| `estat/items.json`・`estat/cities.json`・`estat/city/<市のコード>.json` | 主要品目の都市別小売価格（月次、2000-01〜、`values` は月ごと、抜けは null） | 総務省 小売物価統計調査（e-Stat API） | 月 |
| `seasonal.json` | 季節の指数（12 か月）と安くなりやすい月 | 上の 2 つから計算 | 毎回 |

ビルド日時は入れない。中身が同じならハッシュも同じ。

## 動かし方（ローカル）
```
python -m venv .venv
.venv\Scripts\python -m pip install -r pipeline\requirements.txt
cd pipeline
..\.venv\Scripts\python -X utf8 -m unittest discover -s tests -t .
..\.venv\Scripts\python -X utf8 build.py --out ..\site [--previous ..\site_old]
```
e-Stat は環境変数 `ESTAT_APP_ID` があるときだけ取る（ローカルではなければスキップ。Actions では `--require-estat` でなければ失敗）。
appId はチャットやコードに書かない。

## 失敗したとき
- 取り込み元ごとに独立。失敗した元・件数が前回の 8 割未満に減った元は、前回の配信のファイルをそのまま使い、終了コード 2 → 配信のあと notify ジョブが赤になる（GitHub からメール）。
- 原因は Actions の build ジョブの Summary（report.md）。

## 出典
- 農林水産省「食品価格動向調査（野菜）」「野菜の生育状況及び価格見通し」「今週のお手頃野菜」（政府標準利用規約に準拠。加工して作成）
- 総務省統計局「小売物価統計調査」。このサービスは、政府統計総合窓口(e-Stat)のAPI機能を使用していますが、サービスの内容は国によって保証されたものではありません。
