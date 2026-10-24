# Physical AI：日本語で目的地を選ぶロボットシミュレータ

日本語の指示をローカルAIが読み取り、登録された目的地へ仮想ロボットを動かすプロジェクトです。
WindowsのDocker Desktop上でROS 2 JazzyとGazebo Harmonicを動かし、画面はブラウザで表示します。

AIは「移動の依頼か」「どの目的地か」を選びます。障害物の回避と走行はLiDARを使うv5プログラムが担当します。
有料APIやAPIキーは使いません。実機ではなくシミュレータで動作を確認しています。

## 現在できること

- 日本語から東ステーション `(3, 1)` または南ステーション `(1, -1)` を選び、障害物を避けて移動する。
- 未登録の場所、移動を否定する指示、曖昧な指示を受けた場合に走行を開始しない。
- 到着をGazeboの実際の位置で評価し、障害物との接触と停止状態を確認する。
- 入力、AIの判断、走行結果、停止確認をログに保存する。

現在は走行のたびにシミュレータを再起動して原点へ戻します。
到着した場所から次の場所へ連続して移動する機能と、専用の日本語入力画面は未実装です。

## 必要なもの

- Windowsと、Linuxコンテナが動くDocker Desktop。
- Python 3.12（自動テストと同じバージョンを推奨）。
- Ollamaと、ローカルモデル `qwen3:1.7b`。
- リポジトリのファイル一式。GPUは必須ではありません。

モデルや教材データ、実行環境そのものはGitHubに含めていません。
新しいPCでは、必要なソフトとモデルを別途用意してください。

## 起動する

既にあるプロジェクトのフォルダでPowerShellを開いて実行します。
新しく取得する場合は、GitHubへログインした環境で次を実行します。

```powershell
git clone https://github.com/ykuru2003/physical-ai-final.git
cd physical-ai-final
```

### 1. シミュレータを起動する

Docker Desktopを起動し、Engineが動くまで待ってから、プロジェクトのPowerShellで実行します。

```powershell
docker compose up -d --build simulator
```

初回のビルドにはROS・Gazeboなどのダウンロードが必要です。
[Gazeboの画面](http://localhost:6080/vnc.html?autoconnect=true&resize=scale)を開き、接続ボタンが出た場合はConnectを押します。
青いロボット、橙色の障害物、緑色の目標マーカーが表示されます。

### 2. AIを起動する

**別のPowerShell**を開き、次を実行します。

```powershell
ollama serve
```

`Listening on 127.0.0.1:11434` と出たら、その画面は開いたままにします。
この画面はサーバーが使用するため、次の操作は元のPowerShellで行います。
既にOllamaが同じポートで動いていれば、起動し直す必要はありません。

元のPowerShellで `ollama list` を実行し、`qwen3:1.7b` がない場合だけ取得します。
初回の取得量は約1.4GBです。

```powershell
ollama pull qwen3:1.7b
```

保存済みの `gpt-oss:20b` は、このPCでは推論中にタイムアウト・接続切断が発生したため、現在の既定モデルにはしていません。

### 3. 全体を確認する

他の走行プログラムを終了した状態で、プロジェクトのPowerShellから実行します。

```powershell
.\verify-step3.ps1
```

この処理はモデル名と文字コードを設定し、現在の構成と一致する過去の合格記録を再利用します。
その後、日本語から東・南へ実際に走行し、未知の目的地の指示で走行しないことと停止を確認します。
モデルやDockerイメージの追加ダウンロードは行いません。

最後に `STEP 3 runtime checks PASS` が出れば全体の確認に成功しています。
画面出力は `outputs/step3-full-check.log` と、日時付きのログへ保存します。

すべての到達検証と実AI検証をやり直す場合だけ、次を使います。

```powershell
python -u scripts/complete_step3.py --model qwen3:1.7b --recheck-navigation --recheck-ai
```

## 自分の日本語で指示する

AIの選択結果だけを確認する場合です。ロボットは動きません。

```powershell
python scripts/destination_control.py "東側の資材受け渡し場所へ行って" --model qwen3:1.7b
```

実際に走行する場合は `--execute` を付けます。走行前に原点へ戻ります。

```powershell
python scripts/destination_control.py "南東の点検場所へ行って" --model qwen3:1.7b --execute
```

モデルは登録済みの目的地IDだけを選びます。座標や実行する命令をAIに作らせません。
停止・未知・曖昧な指示、推論失敗、不正な応答、未検証の目的地では走行を開始しません。
停止を確認できなかった場合は `STOP_UNCONFIRMED` と記録します。
判定の合格は有限のテスト結果であり、任意の日本語入力に対する正解を保証するものではありません。

## 目的地とAIのルールを変更する

- `scripts/destinations.json`：目的地ID、AIへ伝える説明、座標、到達検証の記録。
- `scripts/destination_control.py`：移動意図の判断と目的地選択に使うAIへの説明。
- `scripts/validate_local_ai.py`：日本語の言い換え・停止・未知指示など、実AIの30件の検証。
- `scripts/drive_to_goal_v5.py`：LiDARを使う障害物回避と走行・停止の処理。

登録済みでも、南側手前の待機所と西ステーションは実位置の到達検証待ちです。
目的地を追加しただけ、または `state` を書き換えただけでは走行可能になりません。
座標・ワールド・制御コード・AIへの説明などを変えた場合は、対応する検証をやり直してください。
合格記録のハッシュは手で書き換えません。

```powershell
python scripts/qualify_destinations.py --ids east_station
python scripts/qualify_destinations.py
python scripts/validate_local_ai.py --model qwen3:1.7b
```

## 確認済みの結果

2026-10-24に、ローカルのDocker／Gazebo／Ollamaで次を確認しました。

- 東 `(3, 1)` と南 `(1, -1)`：原点からそれぞれ3回連続で実位置PASS。障害物接触なし、停止確認も成功。
- 学習済みローカルAI `qwen3:1.7b`：日本語30件がPASS。移動意図の判定と目的地選択は実際のモデル推論です。
- 日本語からv5へ接続した追加走行：東の実位置誤差19.6cm、南14.7cm。両方ともPASS、障害物接触なし。
- 未知の「コンビニへ行って」：AIがunknownと判断し、走行を起動せず、ROS上の停止確認も成功。
- オフライン：安全制御27テスト、簡易走行12ケース、実位置評価の判定4テストがPASS。

到達の基準は実位置で目標の25cm以内です。実位置は評価に使い、経路の選択には使いません。
各回の結果と最終確認は、次の保存済みファイルにあります。

- `outputs/step2-evaluation/qualify-*/evaluation.json`：東・南それぞれ3回の実位置評価。
- `outputs/local-ai-validation.json`：実AI30件の結果。
- `outputs/step3-final-verification.json`：日本語からの接続走行と未知指示の停止確認の集約。

## 自動テスト（GitHub Actions）

`main` へのpush、pull request、Actions画面からの手動実行で、軽量なオフライン検査を実行します。
設定は `.github/workflows/offline-tests.yml` にあります。
Python 3.12のUbuntu環境を1つ使い、ジョブの上限は5分、同じブランチの古い実行は取り消します。
外部Pythonパッケージ、Docker、Ollama、学習モデル、有料API、追加の認証キーは不要です。
GitHub Actionsの利用枠はアカウントの契約・使用状況に従います。

検査する内容は、Python構文、ワールドXML、安全制御、実位置の評価判定、v3・v4の簡易走行です。
**GitHub上のPASSは、Gazeboの実走行や実AIの再検証が成功したという意味ではありません。**
実走行と実AIは、上記のローカルでの全体確認で検証します。

同じオフライン検査をPCで実行するには、次を使います。

```powershell
python scripts/run_offline_checks.py
```

GitHubのリポジトリでActionsを開き、`Offline tests` の実行結果を確認できます。

## 主なファイルとログ

- `compose.yaml`、`docker/`：Docker環境の起動と構築。
- `simulation/worlds/practice.sdf`：ロボット、センサー、障害物の配置。
- `simulation/config/bridge.yaml`：ROSとGazebo間の通信設定。
- `evaluate-step2.ps1`、`scripts/evaluate_step2.py`：実位置による独立評価。
- `verify-step3.ps1`、`scripts/complete_step3.py`：日本語からの走行までの一括検証。
- `scripts/stop_step2.py`：ゼロ速度の送信と、受信した速度による停止確認。
- `scripts/test_*.py`、`scripts/run_offline_checks.py`：オフライン検査。
- `outputs/language-goals/`：入力、AIの判断、走行結果、停止確認。
- `outputs/destination-qualification/`：目的地の複数回検証の集約。
- `workshop/`：元のPushT教材。教材の学習済みACTモデルからGazeboへ走行指令を出す接続は未実装です。

別途手動で起動したROSの走行ノードとは同時に操作しないでください。
強制終了で `outputs/navigation.lock` が残った場合は、実行中の処理がないことと停止を確認してから除去します。

## 終了・再起動

```powershell
docker compose stop simulator
docker compose restart simulator
docker compose logs --tail 100 simulator
```

`restart` でロボットは原点へ戻ります。Ollamaを手動で起動したPowerShellでは、Ctrl+Cで終了できます。

## GitHubに保存するもの

コード、設定、READMEと、内容を確認した合格記録だけを非公開リポジトリへ保存しています。
`.env` 本体、秘密鍵・認証情報、バックアップ、通常の実行ログ、作業用ファイル、モデルや教材データは保存対象から除外します。
`.env.example` はポート番号などの設定例で、秘密情報は含みません。
ハッシュ照合に使うファイルは `.gitattributes` で元のバイト列を保つ設定にしています。

保存対象からファイルを外す場合、既にGit管理に入っているものは `.gitignore` の追記だけでは外れません。
送信前にGitの対象ファイルと差分を確認してください。
