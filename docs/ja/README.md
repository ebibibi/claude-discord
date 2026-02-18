> **Note:** This is an auto-translated version of the original English documentation.
> If there are any discrepancies, the [English version](../../README.md) takes precedence.
> **注意:** これは英語のオリジナルドキュメントを自動翻訳したものです。
> 内容に相違がある場合は、[英語版](../../README.md)が優先されます。

---

# claude-code-discord-bridge

[![CI](https://github.com/ebibibi/claude-code-discord-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/ebibibi/claude-code-discord-bridge/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

スマートフォンから [Claude Code](https://docs.anthropic.com/en/docs/claude-code) を使う。Discord の thread を通じて **Claude Code CLI へのフルアクセス**を提供する薄い Discord frontend です。ターミナルから離れたときのモバイル開発を想定して設計されています。

**[English](../../README.md)** | **[简体中文](../zh-CN/README.md)** | **[한국어](../ko/README.md)** | **[Español](../es/README.md)** | **[Português](../pt-BR/README.md)** | **[Français](../fr/README.md)**

> **免責事項:** このプロジェクトは Anthropic と提携・承認・公式接続されているものではありません。「Claude」および「Claude Code」は Anthropic, PBC の商標です。本プロジェクトは Claude Code CLI と連携する独立したオープンソースツールです。

> **全て Claude Code が構築しました。** 設計・実装・テスト・ドキュメントは Claude Code（Anthropic の AI コーディングエージェント）が行いました。人間の作者はソースコードを読んでいません。詳細は [このプロジェクトの構築方法](#このプロジェクトの構築方法) を参照してください。

## なぜ作ったか

Claude Code で 3〜4 プロジェクトを並行して動かしています。[Termux](https://termux.dev/) + tmux でスマートフォンから作業する際、複数の terminal session 管理が煩雑になっていました——どの tmux window がどのプロジェクトか？それぞれで何をしていたか？コンテキストスイッチのコストが生産性を下げていました。

**Discord はこれを完璧に解決します:**

- 各プロジェクトの会話が**名前付き thread** になり、一目でわかる
- Thread には全履歴が保持されるため、数時間後でも続きから始められる
- Emoji reaction でステータスが一目瞭然——terminal 出力をスクロールする必要なし
- Discord は無料で全スマートフォンに対応、通知も標準機能

## これは何か（そして何でないか）

**これは:** Discord と Claude Code CLI の架け橋です。`claude -p --output-format stream-json` を subprocess として起動し、出力をパースして Discord に返します。それだけです。

**これではない:** 高機能な Discord bot、AI chatbot framework、Claude Code ターミナル体験の代替。カスタム AI ロジック、plugin システム、管理ダッシュボードはありません。

**重い処理は Claude Code 環境が担います。** CLAUDE.md、skills、tools、memory、MCP server——これらはすべてターミナルと全く同じように動きます。このブリッジは UI 層を提供するだけです。

**セキュリティモデル:** 自分だけがアクセスできる channel を持つプライベート Discord サーバーで動かしてください。bot は意図的にシンプルに設計されています——機能が少ないほど攻撃面が少ない。コード全体を自分で読め、外部に情報を送ることもありません。

## 他ツールとの比較

| | claude-code-discord-bridge | [OpenClaw](https://github.com/openclaw/openclaw) など |
|---|---|---|
| **目的** | モバイルファーストな Claude Code アクセス | 高機能 Discord AI bot |
| **AI backend** | Claude Code CLI（subprocess） | Direct API 呼び出し |
| **機能** | 最小限：threads、status、chunking | 豊富：plugins、admin、multi-model |
| **設定** | 既存の Claude Code 環境をそのまま利用 | bot 固有の設定 |
| **Skills/tools** | Claude Code から継承 | bot config で定義 |
| **対象ユーザー** | すでに Claude Code を使っている開発者 | Discord AI bot を求める誰でも |
| **複雑さ** | Python 約 800 行 | 数千行 |

**Discord AI chatbot が欲しい場合**は OpenClaw などの方が遥かに高機能です。

**スマートフォンから Claude Code を使いたい場合**——既存のプロジェクトコンテキスト、skills、tools ごと——それがこのツールの目的です。

## 機能

- **Thread = Session** — 各タスクは専用の Discord thread に対応し、Claude Code session と 1:1 マッピング
- **リアルタイムステータス** — Emoji reaction で Claude の動作を表示（🧠 考え中、🛠️ ファイル読み込み、💻 編集中、🌐 Web 検索）
- **Session 持続** — `--resume` で会話をまたいでセッションを継続
- **Skill 実行** — slash command で Claude Code skills を実行（`/skill goodmorning`）、autocomplete 付き
- **Webhook トリガー** — CI/CD パイプラインから Discord webhook 経由で Claude Code タスクを起動
- **自動アップグレード** — upstream パッケージがリリースされたときに bot を自動更新
- **REST API** — 外部ツールから Discord に push 通知（オプション、aiohttp が必要）
- **Fence-aware 分割** — 長いレスポンスをコードブロックを壊さずに自然な区切りで分割
- **並列 session** — 複数 session を並行実行（上限設定可）
- **セキュリティ強化** — shell injection なし、subprocess 環境から secrets を除去、ユーザー認証

## 仕組み

```
あなた（Discord）  →  Bridge  →  Claude Code CLI
    ↑                                          ↓
    ←──────── stream-json output ──────────────←
```

1. 設定した Discord channel にメッセージを送る
2. Bot が thread を作成して Claude Code session を開始
3. stream-json output をリアルタイムにパースしてステータス更新
4. Claude のレスポンスを thread に返す
5. Thread で返信すると会話が続く

## クイックスタート

### 要件

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) のインストールと認証
- Message Content intent を有効化した Discord bot token
- [uv](https://docs.astral.sh/uv/)（推奨）または pip

### スタンドアロン起動

```bash
git clone https://github.com/ebibibi/claude-code-discord-bridge.git
cd claude-code-discord-bridge

cp .env.example .env
# .env に bot token と channel ID を記入

uv run python -m claude_discord.main
```

### パッケージとしてインストール

既存の discord.py bot に組み込む場合（Discord は token ごとに Gateway 接続 1 つのみ許可）:

```bash
uv add git+https://github.com/ebibibi/claude-code-discord-bridge.git
```

```python
from claude_discord import ClaudeChatCog, ClaudeRunner, SessionRepository
from claude_discord.database.models import init_db

# 初期化
await init_db("data/sessions.db")
repo = SessionRepository("data/sessions.db")
runner = ClaudeRunner(command="claude", model="sonnet")

# 既存 bot に追加
await bot.add_cog(ClaudeChatCog(bot, repo, runner))
```

最新バージョンへの更新:

```bash
uv lock --upgrade-package claude-code-discord-bridge && uv sync
```

## 設定

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `DISCORD_BOT_TOKEN` | Discord bot token | （必須） |
| `DISCORD_CHANNEL_ID` | Claude chat 用 channel ID | （必須） |
| `CLAUDE_COMMAND` | Claude Code CLI のパス | `claude` |
| `CLAUDE_MODEL` | 使用するモデル | `sonnet` |
| `CLAUDE_PERMISSION_MODE` | CLI の permission mode | `acceptEdits` |
| `CLAUDE_WORKING_DIR` | Claude の作業ディレクトリ | カレントディレクトリ |
| `MAX_CONCURRENT_SESSIONS` | 最大並列 session 数 | `3` |
| `SESSION_TIMEOUT_SECONDS` | Session の無操作タイムアウト | `300` |

## Discord Bot 設定

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリケーションを作成
2. Bot を作成してトークンをコピー
3. Privileged Gateway Intents で **Message Content Intent** を有効化
4. 以下の権限で bot をサーバーに招待:
   - Send Messages
   - Create Public Threads
   - Send Messages in Threads
   - Add Reactions
   - Manage Messages（reaction クリーンアップ用）
   - Read Message History

## Webhook 連携

CI/CD パイプライン（GitHub Actions など）から Discord webhook 経由で Claude Code タスクを起動できます。

```python
from claude_discord import WebhookTriggerCog, WebhookTrigger, ClaudeRunner

runner = ClaudeRunner(command="claude", model="sonnet")

triggers = {
    "🔄 docs-sync": WebhookTrigger(
        prompt="Update documentation based on latest code changes.",
        working_dir="/home/user/my-project",
        timeout=600,
    ),
    "🚀 deploy": WebhookTrigger(
        prompt="Deploy to staging environment.",
        timeout=300,
    ),
}

await bot.add_cog(WebhookTriggerCog(
    bot=bot,
    runner=runner,
    triggers=triggers,
    channel_ids={YOUR_CHANNEL_ID},
))
```

**仕組み:**
1. channel に Discord webhook を設定
2. トリガープレフィックスに一致するメッセージを送信（例: `🔄 docs-sync`）
3. Cog が thread を作成し、設定済みプロンプトで Claude Code を実行
4. 結果がリアルタイムで thread にストリーミングされる

**セキュリティ:** Webhook メッセージのみを処理します。より厳密な制御には `allowed_webhook_ids` が使えます。プロンプトはサーバーサイドに固定——webhook はどのトリガーを発火するかを選ぶだけです。

### GitHub Actions の例

```yaml
# .github/workflows/docs-sync.yml
on:
  push:
    branches: [main]
jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -X POST "${{ secrets.DISCORD_WEBHOOK_URL }}" \
            -H "Content-Type: application/json" \
            -d '{"content": "🔄 docs-sync"}'
```

## 自動アップグレード

upstream パッケージがリリースされたときに bot を自動的にアップグレードします。

```python
from claude_discord import AutoUpgradeCog, UpgradeConfig

config = UpgradeConfig(
    package_name="claude-code-discord-bridge",
    trigger_prefix="🔄 bot-upgrade",
    working_dir="/home/user/my-bot",
    restart_command=["sudo", "systemctl", "restart", "my-bot.service"],
)

await bot.add_cog(AutoUpgradeCog(bot, config))
```

**パイプライン:** upstream push → CI webhook → `🔄 bot-upgrade` → `uv lock --upgrade-package` → `uv sync` → サービス再起動。

`upgrade_command` および `sync_command` パラメータでカスタムコマンドも指定できます。

## REST API

外部ツールから Discord に push 通知を送るためのオプション REST API です。aiohttp が必要:

```bash
uv add "claude-code-discord-bridge[api]"
```

```python
from claude_discord import NotificationRepository
from claude_discord.ext.api_server import ApiServer

repo = NotificationRepository("data/notifications.db")
await repo.init_db()

api = ApiServer(
    repo=repo,
    bot=bot,
    default_channel_id=YOUR_CHANNEL_ID,
    host="127.0.0.1",
    port=8080,
    api_secret="your-secret-token",  # オプション Bearer 認証
)
await api.start()
```

### エンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/health` | ヘルスチェック |
| POST | `/api/notify` | 即時通知を送信 |
| POST | `/api/schedule` | 通知をスケジュール |
| GET | `/api/scheduled` | 保留中の通知一覧 |
| DELETE | `/api/scheduled/{id}` | スケジュール済み通知のキャンセル |

### 使用例

```bash
# ヘルスチェック
curl http://localhost:8080/api/health

# 通知を送信
curl -X POST http://localhost:8080/api/notify \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-token" \
  -d '{"message": "Build succeeded!", "title": "CI/CD"}'

# 通知をスケジュール
curl -X POST http://localhost:8080/api/schedule \
  -H "Content-Type: application/json" \
  -d '{"message": "Time to review PRs", "scheduled_at": "2026-01-01T09:00:00"}'
```

## アーキテクチャ

```
claude_discord/
  main.py                  # スタンドアロン起動エントリポイント
  bot.py                   # Discord Bot クラス
  cogs/
    claude_chat.py         # メイン chat Cog（thread 作成、メッセージ処理）
    skill_command.py       # /skill slash command（autocomplete 付き）
    webhook_trigger.py     # Webhook → Claude Code タスク実行
    auto_upgrade.py        # Webhook → パッケージアップグレード + 再起動
    _run_helper.py         # 共有 Claude CLI 実行ロジック
  claude/
    runner.py              # Claude CLI subprocess マネージャー
    parser.py              # stream-json イベントパーサー
    types.py               # SDK メッセージの型定義
  database/
    models.py              # SQLite スキーマ
    repository.py          # Session CRUD 操作
    notification_repo.py   # スケジュール通知 CRUD
  discord_ui/
    status.py              # Emoji reaction ステータスマネージャー（デバウンス済み）
    chunker.py             # Fence-aware メッセージ分割
    embeds.py              # Discord embed ビルダー
  ext/
    api_server.py          # REST API server（オプション、aiohttp 必要）
  utils/
    logger.py              # ロギング設定
```

### 設計思想

- **カスタム AI ロジックなし** — 推論・ツール使用・コンテキストはすべて Claude Code が処理
- **メモリシステムなし** — Claude Code 組み込みの session + CLAUDE.md がメモリを担当
- **ツール定義なし** — Claude Code が包括的なツールセットを持つ
- **Plugin システムなし** — 機能追加は Claude Code の設定で行い、このbot側では行わない
- **Framework の仕事は純粋に UI** — メッセージ受信、ステータス表示、レスポンス配信

### セキュリティ

- `asyncio.create_subprocess_exec`（shell 不使用）でコマンドインジェクションを防止
- session ID を使用前に厳格な regex で検証
- `--` セパレーターでフラグ解釈によるプロンプトインジェクションを防止
- subprocess 環境から bot token と secrets を除去
- `allowed_user_ids` で Claude を呼び出せるユーザーを制限
- シンプルなコードベース（約 800 行）——自分で監査しやすい

## テスト

```bash
uv run pytest tests/ -v --cov=claude_discord
```

parser、chunker、repository、runner、webhook trigger、auto-upgrade、REST API をカバーする 131 個のテスト。

## このプロジェクトの構築方法

**このコードベース全体は [Claude Code](https://docs.anthropic.com/en/docs/claude-code)**（Anthropic の AI コーディングエージェント）**によって書かれました。** 人間の作者（[@ebibibi](https://github.com/ebibibi)）は自然言語で要件と方向性を提供しましたが、ソースコードを手動で読んだり編集したりはしていません。

つまり:

- **すべてのコードが AI 生成** — アーキテクチャ、実装、テスト、ドキュメント
- **人間の作者はコードレベルでの正確性を保証できない** — 保証が必要な場合はソースを確認してください
- **バグレポートと PR を歓迎** — 対応にも Claude Code が使われる予定です
- **AI 作成オープンソースソフトウェアの実例** — Claude Code が構築できるものの参考にしてください

このプロジェクトは 2026-02-18 の 1 日で、Claude Code との反復的な会話を通じて構築されました。要件から始まり、動作するテスト済みのドキュメント付きパッケージで終わりました。

## 実際の使用例

**[EbiBot](https://github.com/ebibibi/discord-bot)** — claude-code-discord-bridge をパッケージ依存関係として使用する個人 Discord bot。push 通知、Todoist watchdog、自動ドキュメント同期のカスタム Cog を含みます。このフレームワーク上で自分の bot を構築する際の参考にしてください。

## インスパイア元

- [OpenClaw](https://github.com/openclaw/openclaw) — Emoji status reaction、メッセージデバウンス、fence-aware chunking
- [claude-code-discord-bot](https://github.com/timoconnellaus/claude-code-discord-bot) — CLI spawn + stream-json アプローチ
- [claude-code-discord](https://github.com/zebbern/claude-code-discord) — permission 制御パターン
- [claude-sandbox-bot](https://github.com/RhysSullivan/claude-sandbox-bot) — thread-per-conversation モデル

## ライセンス

MIT
