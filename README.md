# padkit — SPD/PAD ツールチェーン

SPD（Simple PAD Description）で書いた手順・計画を PAD（Problem Analysis Diagram,
問題分析図）として検査・描画するツール群。

- **`padkit`**（CLI）: lint / SVG / PDF / AST。描画は [padtools_ts](https://github.com/steelpipe75/padtools_ts) を固定版で呼ぶ
- **`skill/`**（Claude Skill `spd`）: SPD の文法と規則を読み込み、LLM に正しい SPD を書かせる。計画・設計なら構造の欠陥も講評する

主眼は作図の省力化ではなく、**構造の欠陥検出**にある。PAD にすると、散文の計画書では
見えない欠陥（本流の途中の終端、反復の欠如、片道の分岐）が形として現れる。

## なぜラッパーが要るのか

padtools_ts は次の入力を**エラーも警告も出さず、終了コード 0 で**誤った図にする
（固定コミットで実測）。

| 入力 | 描かれる図 |
|---|---|
| スペースで字下げ | 入れ子が全部消え、`:if` が文字列の箱になる |
| `:ifx 条件`（綴り違い） | `:if` として読み、子ブロックを捨てる |
| 処理ボックスの 2 文字目が `#`（`C# で書く`） | 次の行を同じ箱に取り込む |
| `:else  # コメント` | else 側を丸ごと捨てる |
| 最後の文が字下げされた 1 文字の箱 | その箱が消える |

`padkit lint` はこれらを個別の規則で error にし、さらに **padkit 自身のパーサで組んだ AST と
padtools_ts の AST を突き合わせて**、未知の黙殺も E900 として止める。`svg` / `pdf` / `ast` は
lint を通らない入力を描画しない。

## 導入

前提: Python ≥ 3.11、[uv](https://docs.astral.sh/uv/)、Node.js ≥ 22（npm）、cairo
（macOS: `brew install cairo` / Debian 系: `apt install libcairo2`）。

```bash
uv tool install .        # padkit コマンドを導入
padkit setup             # 固定版 padtools_ts の依存を npm ci で導入（初回のみ、約 94 MB）
padkit info              # 固定版・エンジンの場所・解決されたフォントを確認
```

開発時は `uv sync` のうえ `uv run padkit …`。エンジンの置き場所は既定で
`~/.cache/padkit/padtools_ts-<commit>`、`PADKIT_ENGINE_DIR` で変えられる。

## 使い方

```bash
padkit lint plan.spd                 # 構文・黙殺・講評観点。error があれば exit 1
padkit lint --strict plan.spd        # warning でも exit 1
padkit lint --format json plan.spd   # 統計と診断を JSON で（LLM への読み戻し用）
padkit fix-indent -w plan.spd        # スペース字下げをタブに直す（段の幅は自動推定）

padkit svg plan.spd -o plan.svg                  # house スタイル（navy, CJK ゴシック）
padkit svg plan.spd -o plan.svg --style mono     # padtools_ts の既定（monospace・黒）
padkit pdf plan.spd -o plan.pdf                  # 用紙と向きを自動選択
padkit pdf a.spd b.spd -o book.pdf --paper a3    # 複数の図を 1 冊に綴じる
padkit pdf plan.spd --align-depth                # 深さを列に揃える（下記）

padkit ast plan.spd -o plan.json                 # padtools_ts の AST
padkit svg --from-ast plan.json -o plan.svg      # AST から描画（往復）
padkit ast --oracle plan.spd                     # padkit 自身の解析結果
```

診断コードの一覧は [skill/reference/lint-codes.md](skill/reference/lint-codes.md)。

### スタイル

| 名前 | 書体 | 線・文字 | 線幅 |
|---|---|---|---|
| `house`（既定） | CJK ゴシック 13 | `#142850`（navy） | 1 |
| `mono` | monospace 14 | 黒 | 1 |
| `print` | CJK ゴシック 13 | 黒 | 1.6 |

CJK ゴシックは Noto Sans CJK JP → Noto Sans JP → Hiragino Sans → … の順に、
**インストール済みでかつ可変フォントでないもの**を選ぶ。cairo は可変フォントを既定インスタンス
で描くため、Noto Sans JP の可変版を選ぶと極細（Thin）になる。`--font-family` 等で個別に上書きできる。
余白・箱の内側余白は padtools_ts の CLI から変えられない。

### 深さの列揃え（`--align-depth`）

PAD の規格にはない拡張。標準の描画では子の位置が親の箱の幅で決まるため、同じ深さの箱が
左右にずれる。`--align-depth` を付けると、同じ深さの箱をすべてその深さの最大幅に伸ばし、
**1 列 = 1 段の抽象度**として並べる。粒度の混在（同じ列に戦略と作業が並ぶ）が見えやすくなる。
代わりに図の幅は各列の最大幅の和になる。`:comment` は枠が無いので伸ばさない。

`svg` / `pdf` の両方で使える。実装は padtools_ts の描画への小さなパッチ（下記）。

### PDF の用紙

- 向きは図の縦横比で決める。用紙は A4 で縮小率が 0.7 未満になるなら A3 にする
- 既定では拡大しない（`--max-scale 1.0`）。複数ページで文字の大きさが揃う。紙面いっぱいにするなら `--max-scale 10`
- 余白は 36 pt（0.5 in）、`--margin` で変更
- フォントは PDF に埋め込まれる。フォントの無い環境でも同じ見た目になることをテストで確認している

## Skill の導入

`skill/` を Claude Code のスキル置き場へリンクする。

```bash
ln -s "$PWD/skill" ~/.claude/skills/spd    # /spd で起動
```

`skill/scripts/spd_lint.py` は padkit 無しで動く単体の linter（標準ライブラリのみ）。
`src/padkit/spd.py` と `lint.py` から生成しており、手で編集しない。

```bash
uv run python scripts/build_skill_lint.py    # 再生成（テストが鮮度を検査する）
```

## 開発

```bash
uv sync
uv run padkit setup
uv run pytest                    # エンジン未導入なら該当テストは skip
UPDATE_GOLDEN=1 uv run pytest    # golden SVG の更新
```

### padtools_ts の固定版を上げる

```bash
./scripts/vendor_padtools.sh <commit-sha>
uv run padkit setup --force
uv run pytest
```

`src/padkit/_vendor/padtools_ts/` には `dist/`・`package.json`・`package-lock.json`・LICENSE・
文法（`spd.langium`）だけを置き、`node_modules` は置かない。`PIN.json` にコミット、tarball の
SHA-256、適用したパッチを記録する。

padtools_ts への変更は `patches/*.patch` として持ち、vendor のたびに番号順に当て直す。
vendor 済みのファイルを直接編集しない。パッチが当たらなくなったら、新しい版に合わせて作り直す。

| パッチ | 内容 | 既定の出力 |
|---|---|---|
| `0001-align-depth.patch` | `--align-depth`（深さの列揃え） | 変えない |
| `0002-sequence-line-stops-at-shape.patch` | 順次処理の縦線が、最後の要素の図形を越えて子の部分木の下端まで伸びる不具合を直す | 縦線の終点だけ変わる |
| `0003-connector-reaches-terminal.patch` | 終端（角丸）へつなぐ横線が、角丸の手前で宙に浮いて終わる不具合を直す | 終端へつながる横線の終点だけ変わる |

0002 は upstream の描画の不具合で、分岐（`:if`/`:switch`）や子を持つ箱が列の最後にあると
縦線がはみ出す。0003 も upstream の不具合で、`:terminal` が子や分岐先の先頭にあると、横線が
外接矩形の角で止まり角丸に届かない。それぞれ `test_sequence_line_stops_at_the_branch_shape`、
`test_connector_reaches_rounded_terminal`（`tests/test_engine.py`）で検査している。

エンジンの `dist` は実行時に vendor 側と照合され、違えば自動で写し直される。
`package-lock.json` が変わったときだけ `padkit setup --force` が要る。

固定先は v0.4.0 タグではなく main のコミット `de37d5d` にしている。v0.4.0 は langium 化以前の
手書きパーサで、仕様の基準にした `spd.langium` を含まないため。

## 構成

```
src/padkit/
  spd.py        SPD パーサ（padtools_ts から独立。AST 突き合わせの基準）
  lint.py       講評観点の検査と出力
  engine.py     padtools_ts の導入・呼び出し・AST 比較
  presets.py    スタイルとフォント解決
  pdf.py        SVG → PDF、用紙フィット
  cli.py
  _vendor/padtools_ts/
skill/
  SKILL.md
  reference/    文法・講評観点・診断コード
  examples/
  scripts/spd_lint.py   （生成物）
tests/
  fixtures/ok/       正常系
  fixtures/broken/   1 行目の `# expect: E…` が期待する診断
  golden/            golden SVG
```

## ライセンス

MIT。padtools_ts（MIT, © 2025 steelpipe）を同梱している。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 参照。
