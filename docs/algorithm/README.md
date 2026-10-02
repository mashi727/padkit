# padkit のアルゴリズム（SPD）

padkit 自身の処理を SPD で書いたもの。1 ファイル 1 図。`:call` の名前は呼び出し先の図の
1 行目と一致する（`tests/test_docs_algorithm.py` が検査する）。入口は `00-main.spd`。

| 番号 | 対象 |
|---|---|
| 00–01 | CLI（`cli.py`） |
| 10–15 | 解析（`spd.py`） |
| 20–21 | lint と講評観点（`lint.py`） |
| 30–31 | padtools_ts との突き合わせ（`engine.py`） |
| 40–44 | スタイル・書体・描画・深さ揃え・接続線（`presets.py`, `engine.py`, `patches/`） |
| 50 | PDF の用紙配置（`pdf.py`） |

```bash
padkit pdf --align-depth docs/algorithm/*.spd -o docs/algorithm/padkit-algorithm.pdf
```

コードを変えたら対応する図も直す。図はコードから生成していないので、自動では追従しない。
