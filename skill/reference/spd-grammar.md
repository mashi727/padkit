# SPD 文法リファレンス

規範は padtools_ts の `src/spd/langium/spd.langium`。本リポジトリでは
`steelpipe75/padtools_ts@de37d5dc3253` に固定し、全文を末尾に転載している。
ただし**文法ファイルと実装（`parser.ts` の後処理）は一致しない点がある**。
本書の記述は、固定コミットで実際に動かして確かめた挙動を優先する。

## 行と深さ

- 1 行 = 1 文。行頭が `:` なら命令、それ以外は処理ボックス
- 行頭の**タブの個数**が深さ。前の行より 1 段深い行は、その行の子になる
- 2 段以上一度に深くするとエラー。先頭行を字下げしてもエラー
- **行頭のスペースは字下げとして数えられない。** 文法上 `WS` は hidden token なので
  捨てられ、入れ子が消えたまま終了コード 0 で描画される

## 命令

| 命令 | 引数 | 子ブロック | 備考 |
|---|---|---|---|
| `:if` | 必須 | 真の処理 | |
| `:else` | **不可** | 偽の処理 | 直前の兄弟が `:if` でなければエラー。1 つの `:if` に 1 つまで |
| `:switch` | 必須 | **不可** | |
| `:case` | 必須 | その肢の処理 | 直前の兄弟が `:switch` か `:case`。同じ値の重複はエラー |
| `:while` | 必須 | 本体 | 前判定 |
| `:dowhile` | 必須 | 本体 | 後判定 |
| `:call` | 必須 | 可 | 二重線のボックス |
| `:terminal` | 必須 | **不可** | 角丸のボックス |
| `:comment` | 必須 | **不可** | 枠なしの注記 |

文法ファイル上はすべての引数が省略可能（`(arg=Argument)?`）だが、実装は `:else` 以外で
引数を必須とし、無ければ「このコマンドは引数が必要です」で止まる。

## ボックス内の文字

- `@` は改行。`A@B` は 2 行のボックス
- 行末の `@` は次の物理行へ続く。続きの行の字下げは無視される
- `\@` は文字の `@`
- `#` で始まる行（字下げ後）は無視される
- **行の途中の `#` はコメントにならない。** `処理 # メモ` はそのまま描かれる
  （文法の `LINE_COMMENT` から予想される挙動と異なる）

## 最小例

```spd
処理の名前
	:comment 構造に影響しない注記
	通常の処理ボックス
	:if 条件か
		真の場合の処理
	:else
		偽の場合の処理
	:switch 条件
	:case ケース1
		ケース1の処理
	:case ケース2
		ケース2の処理
	:while 繰り返し条件か
		本体を実行する
	:dowhile 繰り返し条件か
		本体を実行する
	:call 別図へ
	:terminal 終端
```

## 黙って壊れる入力

固定コミットで確認したもの。E002 の一部を除き、padtools_ts は終了コード 0 を返す。

| 入力 | 実際の描画 | lint |
|---|---|---|
| スペースの字下げ | 全行が深さ 0 の箱になる | E001 |
| タブとスペースの混在 | スペースが先なら深さ 0 の箱に化ける。タブが先なら別の行で見当違いのエラー | E002 |
| `:ifx 条件`（綴り違い） | `:if` 「x 条件」と読み、子ブロックを捨てる | E103 |
| `:whilex 条件` | `:while` 「x 条件」になる | E103 |
| 処理ボックスの 2 文字目が `#`（`C# で書く`） | 次の行を同じ箱に取り込む | E106 |
| `:else  # コメント` | else 側の処理を丸ごと捨てる | E109 |
| 最後の文が、字下げされた 1 文字の処理ボックス | その箱が消える | E115 |

E106 はコマンドの引数（`:if c#x`）では起きない。E115 は 2 文字以上、深さ 0、
命令の引数（`:terminal x`）では起きず、末尾の改行・CRLF・後続のコメント行の有無は関係しない。
これらは個別の規則で検出するが、`padkit lint` はさらに padtools_ts の AST と
padkit 自身の解析結果を突き合わせ、未知の黙殺も E900 として検出する。

## 文法全文（de37d5dc3253）

```langium
grammar Spd

entry Model:
    (statements+=Statement)*;

Statement:
    CommandStatement | ProcessStatement;

CommandStatement:
    IfStatement | WhileStatement | DoWhileStatement | CallStatement | SwitchStatement | CaseStatement | ElseStatement | TerminalStatement | CommentStatement;

Block:
    INDENT (statements+=Statement)+ DEDENT;

IfStatement: ':if' (arg=Argument)? (block=Block)?;
WhileStatement: ':while' (arg=Argument)? (block=Block)?;
DoWhileStatement: ':dowhile' (arg=Argument)? (block=Block)?;
CallStatement: ':call' (arg=Argument)? (block=Block)?;
SwitchStatement: ':switch' (arg=Argument)? (block=Block)?;
CaseStatement: ':case' (arg=Argument)? (block=Block)?;
ElseStatement: ':else' (block=Block)?;
TerminalStatement: ':terminal' (arg=Argument)? (block=Block)?;
CommentStatement: ':comment' (arg=Argument)? (block=Block)?;

ProcessStatement:
    (content=Content) (block=Block)?;

Argument returns string:
    Content;

terminal INDENT: 'synthetic:indent';
terminal DEDENT: 'synthetic:dedent';

hidden terminal LINE_COMMENT: /#[^\n\r]*/;
terminal Content: /[^\t:\n\r](?:[^\n\r]*(?<!\\)@[ \t]*\r?\n[ \t]*|#[^\n\r]*\r?\n[ \t]*)*[^\n\r]*/;

hidden terminal WS: /[ \t]+/;
hidden terminal NEWLINE: /\r?\n/;
```
