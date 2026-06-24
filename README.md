# coderouter-plugin-compress

[![CI](https://github.com/zephel01/coderouter-plugin-compress/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zephel01/coderouter-plugin-compress/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![runtime deps](https://img.shields.io/badge/runtime%20deps-0-brightgreen)
![license](https://img.shields.io/badge/license-MIT-yellow)

**日本語** · [English](./README.en.md) · [CodeRouter 本体](https://github.com/zephel01/CodeRouter) · 姉妹プラグイン: [coderouter-plugin-memory](https://github.com/zephel01/coderouter-plugin-memory) · 着想元: [headroom](https://github.com/chopratejas/headroom)

CodeRouter 向けの **コンテキスト圧縮** プラグイン（[headroom](https://github.com/chopratejas/headroom) に着想）。`tool_result` ブロック（JSON / ログ）を LLM に届く前に圧縮する、pure-stdlib の `InputFilter` プラグインです。狙いは「答えは同じ、トークンは少なく」。

- **opt-in。** `plugins.enabled` に `compress` を明示したときだけ作動します。
- **コア依存ゼロ。** MVP の crusher は pure Python。精密なトークン計測（`accuracy`）と AST コード圧縮（`code`）は任意の extras です。
- **既定で安全。** crusher がエラーになってもブロックは無加工のまま。`mode: off` は完全なパススルーです。
- **可逆（CCR）。** 原文はコンテンツハッシュをキーにローカル保持されます。

**ドキュメント:** [Architecture](docs/architecture.md) · [CCR（可逆圧縮）](docs/CCR.md) · [CacheAligner](docs/CACHE_ALIGNER.md)

## インストール

```bash
pip install -e .              # コア（pure stdlib）
pip install -e ".[accuracy]"  # + ローカルトークナイザ計測（CJK 正確）
```

## CodeRouter で有効化（`providers.yaml`）

```yaml
plugins:
  enabled: [compress, compress-stats]
  config:
    compress:
      mode: safe                # off | safe | aggressive
      min_block_tokens: 200
      targets: [tool_result]
      crushers: [json, log, text]
      ccr: true
      metering:
        tokenizer_path: ~/.coderouter/tokenizers/sonnet.json  # 任意
```

## 何を圧縮するか

| Crusher | 対象 | 手法 |
|---|---|---|
| `json` | JSON のツール出力 | オブジェクト配列 → 列指向テーブル（キー重複排除）+ 空白の最小化 |
| `log`  | ログ / スタックトレース | 完全一致ラン + テンプレートランの畳み込み。**マーカー行は逐語で保持** |
| `text` | その他の長いブロック | 保守的な中間省略、マーカーは保持 |

## テスト & ベンチマーク

```bash
python -m pytest -q                 # ユニットテスト（47 件）
python scripts/bench.py             # 圧縮前後のトークン削減量
python scripts/integration_test.py  # 実 CodeRouter に対して（要: pip install coderouter-cli）
python scripts/live/run_live.py     # 実 `coderouter serve` + スタブ upstream
```

## CCR 再展開（Phase 2）

圧縮されたブロックには、コンテンツハッシュ ID `ccr_<hex>` とヒント
`reply "expand ccr_<hex>" to restore` が付与されます。後続のターンでその ID が
エコーされると、そのターンはブロックを **非圧縮** のまま通します。決定論的で
誤検出がなく、ローカルモデルでも動作します（ツールコール不要）。
`ccr_restore: explicit | off`（既定 `explicit`）で切り替えます。

## CacheAligner（Phase 3）

2 つ目の独立した InputFilter（`cache-align`、**opt-in**）。Anthropic の
プロンプトキャッシュのブレークポイントを付与し、必要に応じてプレフィックスを
安定化します。プラグインフィルタとして実装されているため、CodeRouter コアは
一切変更されません。Anthropic ネイティブの有料ルートでは `cache_control`
マーカーがそのまま転送され、大きく安定した system+tools プレフィックスが
キャッシュされます。OpenAI / ローカルルートでは変換時に無害に破棄されます。

```yaml
plugins:
  enabled: [compress, compress-stats, cache-align]
  config:
    cache-align:
      inject_cache_control: true    # system + tools 末尾に ephemeral ブレークポイント
      cache_system: true
      cache_tools: true
      stabilize_tools_order: false  # リスク高め。既定 off
      max_breakpoints: 4            # Anthropic のハード上限
```

ステータス: Phase 0–3 完了。すべてプラグインとして実装され、CodeRouter コアは
未変更です。Phase 4（任意の ML/AST 圧縮）は未着手です。

## CodeRouter との関係

これは [CodeRouter](https://github.com/zephel01/CodeRouter) のための、独立して
バージョン管理されるスタンドアロンプラグインです。実行時に CodeRouter を
import することはありません。`coderouter.input_filter` / `coderouter.observer`
のエントリポイント経由でアタッチし、`plugins.enabled` に列挙されたときだけ
作動します。統合テストとライブテストは、実エンジンを動かすために
`coderouter-cli` をインストールします。

## 関連プロジェクト

| プロジェクト | 役割 |
|---|---|
| [CodeRouter](https://github.com/zephel01/CodeRouter) | このプラグインをホストする wire 層ルーター（必須）。 |
| [coderouter-plugin-memory](https://github.com/zephel01/coderouter-plugin-memory) | 姉妹プラグイン — wire 層で注入されるセッション横断メモリ。`compress` ときれいに併用できます。 |
| [headroom](https://github.com/chopratejas/headroom) | 圧縮 / CCR / キャッシュ整列のアイデアの着想元。 |

MIT License.
