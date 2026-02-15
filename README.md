# note2X

note の「今日のあなたに」セクションに出てきた記事の作者プロフィールを巡回し、作者が公開している X（旧 Twitter）アカウントを抽出する CLI アプリです。

## できること

- `note.com` トップページから「今日のあなたに」の記事リンクを収集
- 各記事の作者ページを探索
- 作者ページにある `x.com` / `twitter.com` のリンクからフォロー対象を抽出
- `x.com/intent/follow` URL を生成

> 注意: note / X の UI 変更やログイン状態により、取得できない場合があります。

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## 使い方

```bash
python follow_note_today.py --limit 10
```

### ログインが必要な場合

「今日のあなたに」はユーザーごとの表示なので、Cookie が必要になることがあります。

1. ブラウザで note にログイン
2. Playwright 形式の cookie JSON を保存
3. 次のように実行

```bash
python follow_note_today.py --cookies cookies.json --headful
```

### X のフォローページを順に開く

```bash
python follow_note_today.py --open-intents --headful
```

`--open-intents` は自動でフォローボタンを押すのではなく、フォロー Intent ページを開くだけです（誤フォロー防止）。
