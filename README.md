# 日本語指示によるAI目的地選択とGazebo移動ロボット

日本語の指示からローカルAIが目的地を選び、Gazebo内のロボットが移動・到着・停止する最終課題です。

**日本語入力 → Ollamaの実推論 → 登録目的地の選択 → ROS 2経由の走行 → 到着・停止確認**

AIは目的地を選択し、LiDARとオドメトリを使う制御処理が走行・障害物回避を担当します。
AIが直接モーター指令を生成する構成ではありません。本リポジトリには移動タスクの実装・検証・録画を含みます。

## 必要な環境

- Docker DesktopのLinuxコンテナ、またはDocker EngineとCompose plugin。
- ホストのPython 3.12以上とPowerShell 7。ホストの課題コードはPython標準ライブラリのみを使用します。
- ホストのOllamaと、インストール済みのローカルモデルqwen3:1.7b。
- ROS 2 JazzyとGazebo Harmonicはコンテナ内にあります。ホストへのROS導入は不要です。

必要なら.env.exampleを.envへコピーします。モデル名とポートはOLLAMA_MODEL・OLLAMA_PORTで設定します。
環境変数が.envより優先されます。Pythonの場所は-Python引数かPHYSICAL_AI_PYTHON環境変数で指定できます。
Ollamaが未起動なら別ターミナルでollama serve、モデルがない初回だけollama pull qwen3:1.7bを実行してください。
検証・録画コマンドはモデルをダウンロードしません。

## 最短の実行手順：起動から録画まで

以下はリポジトリ直下から実行します。内部パスはリポジトリを基準に解決します。

```powershell
./project.ps1 Start
./project.ps1 SubmissionCheck
./project.ps1 Record
```

Startは初回ビルドと起動、SubmissionCheckは提出前検証、Recordは今回の実行の録画を行います。

Gazeboの画面は起動時のURLで開きます。既定は[Gazeboデスクトップ](http://localhost:6080/vnc.html?autoconnect=true&resize=scale)です。

- SubmissionCheck：東側目的地の到達資格、実AIの30入力検証、日本語入力からの走行3回を実施。
- Select：目的地の選択だけを確認し、走行しない。
- Run：今回の実推論に基づいて到着・停止まで実行。
- Record -CheckOnly：推論・走行・録画・サービス操作をせずプレビュー。
- Record：初期化後に録画を開始し、今回の推論、走行、結果を連続収録。

録画は `gazebo/outputs/recordings/<run-id>/submission.mp4` に保存されます。
同じフォルダの `manifest.json` に走行と録画の判定、`audit/selection.json` にAIの選択・最終停止の記録があります。
最後の表示がPASSであることを確認し、動画を再生して入力・AIの判断・移動・停止が読める画面で収録されていることを確認してください。
録画対象はGazeboコンテナのデスクトップです。ロボットと経路が見える画角にし、ほかのウィンドウを重ねないでください。

到達資格は現在の指紋と一致する3回の記録がある場合だけ再利用します。証跡のない新しいcloneでは再検証します。
初期状態へ戻すためシミュレータを再起動する処理があります。他の走行処理と同時に実行しないでください。

```powershell
./project.ps1 Status
./project.ps1 Logs
./project.ps1 Stop
./project.ps1 Help
```

Start・Stop・Status等はGazeboを対象にします。操作はHelpに記載された現在のコマンドに統一しています。

## 個別操作

次のコマンドは必要に応じて使用します。最短手順に毎回追加する必要はありません。

```powershell
# AIによる選択だけを確認（走行しない）
./project.ps1 Select -Instruction "東側の資材受け渡し場所へ行って"
# 録画せずに今回の指示を実行
./project.ps1 Run -Instruction "東側の資材受け渡し場所へ行って"
# サービスを操作せず録画設定を確認
./project.ps1 Record -CheckOnly
# AIを使わず、現在の走行制御を指定座標で評価
./project.ps1 Evaluate -GoalX 3 -GoalY 1
# 古いログの整理候補を確認
./project.ps1 Clean -CheckOnly
```

Evaluateは走行制御の診断で、日本語指示からのタスク検証とは別です。
Buildはイメージのビルドだけ、Shellは起動中コンテナのシェルを開きます。
Cleanはログを照合付きZIPへまとめる操作です。過去の作業記録は保持し、提出用録画・提出前検証・historicalは整理対象から除外します。

## 評価と制限

目的地のID・説明・座標はgazebo/scripts/destinations.jsonに登録します。
AIは登録IDだけを返し、座標は登録値を使用します。未登録・曖昧・停止指示、推論失敗、不正応答、未検証目的地では移動を開始しません。
拒否テストのPASSは「移動先を選択しなかった」という意味で、拒否理由の分類精度とは区別します。

本実装の評価基準は、実位置で目標から25cm以内、障害物の衝突記録なし、最終停止確認です。
25cmは独自の基準で、講座の公式合格基準ではありません。実位置は評価だけに使用し、経路の選択には使いません。
固定環境と有限の入力による検証であり、任意の日本語・障害物配置での成功を保証しません。

## ファイル構成

```text
project.ps1                 引数・ヘルプ・コマンド振り分け
.env.example                共通設定例
.github/workflows/ci.yml     オフライン検査のCI
gazebo/
  compose.yaml / Dockerfile ROS・Gazebo・録画の環境
  entrypoint.sh            コンテナ起動
  simulation/              ワールド・ブリッジ・launch
  scripts/                 AI選択・走行・評価・録画・検証・ホスト操作
  tests/                   課題のオフライン検査
  outputs/                 実行記録・検証状態（生成物はGit対象外）
    recordings/<run-id>/   提出MP4・監査記録・録画ログを一括保存
tests/                     全体構成と操作入口の検査
docs/verification.md       過去の結果と再検証の扱い
work/gazebo-history/       整理済みの過去検証記録（Git対象外）
```

DockerfileはROS・Gazebo・録画ツールを含むイメージを定義し、compose.yamlはポート・マウント・起動設定、entrypoint.shはコンテナ内の起動処理を担当します。3ファイルとも使用中です。
実行環境はgazebo/内のDockerfileとComposeの1組です。Composeプロジェクト名はphysical-ai-finalです。
ビルドはリポジトリをコンテキストとし、ルートの.dockerignoreを使います。

## コードを読む順序

- project.ps1 → gazebo/scripts/project_commands.ps1：操作入口と、Docker管理・診断・検証コマンドの実装。
- destination_control.py：実推論、登録地照合、資格確認、停止を含むタスク実行。
- settings.py：相対パス、モデル・ポート、Composeの構築。
- navigate_to_goal.py：LiDARとオドメトリによる移動。
- evaluate_navigation.py：実位置と接触による独立した評価。
- task_results.py：提出前検証と録画で共通に使う成功判定。目的地・実位置・衝突・停止を照合。
- submission_check.py：東側目的地の提出前検証。
- record_submission.py：実行イベントの表示、録画、監査記録。

通常実行と録画は同じrun_instruction()・evaluate()を使います。
prepare_simulator()で初期化を分離し、録画はその後に開始します。
on_eventで実推論・走行の通知を受け、実行時の関数置き換えは行いません。
提出前検証と録画は共通の成功判定を使い、要求と異なる目的地や停止未確認を成功と扱いません。

## 検査

```powershell
./project.ps1 Test
./project.ps1 Validate
./project.ps1 Verify
```

TestはDocker・Ollama不要の構文、現行走行制御の安全停止・合成走行、録画異常系、操作入口の検査です。
ValidateはシミュレータのCompose設定を検査します。サービスは起動しません。
Verifyは任意の拡張検証で、2目的地と拒否指示の実行を含みます。
オフラインPASSは実Gazebo・実AIでの成功を意味しません。コード変更後は必要な実行検証を行います。
過去の証明書のハッシュを書き換えて合格扱いにすることはしません。

## 困ったとき

- Dockerへ接続できない：Docker Desktopが起動し、Linuxコンテナを使えることを確認してStatusを実行します。
- Ollamaへ接続できない：Ollamaが起動しているか、モデル名とポートが設定と一致するかを確認します。
- 到達資格・実AI検証が無効：SubmissionCheckを実行します。古いハッシュは手で更新しません。
- センサー準備や走行が失敗：表示された実行フォルダのログとLogsコマンドを確認します。
- 録画が失敗：録画フォルダのcapture-worker.log、ffmpeg.log、manifest.jsonを確認します。
- navigation.lockが残った：別の走行が実行中でないことと停止を先に確認します。実行中のロックを消さないでください。

## 出力と履歴

- gazebo/outputs/submission-check/：3回の実行監査と概要。
- gazebo/outputs/language-goals/：単独の指示実行。
- gazebo/outputs/recordings/<run-id>/：提出MP4・manifest・AI応答・監査記録・FFmpegログをまとめて保存。
- gazebo/outputs/historical/：変更前の証跡。現在のコードの保証には使いません。

録画は標準では1か所だけに保存します。別の場所に提出用コピーが必要な場合のみ、record_submission.pyの--output-rootで指定できます。
オフライン検査のキャッシュはルートの.cache/tests/gazebo/にまとめます。

データ、モデル、ログ、動画、キャッシュ、秘密情報はGitに含めません。
検証状態の概要2ファイルは保存しますが、生の証跡は各環境で生成します。
Cleanは提出用録画・提出前検証・historicalを整理対象から除外します。

## 過去の記録を読む

ローカルのwork/gazebo-history/README.mdを入口に、過去の検証記録と当時のコード・設定を確認できます。
旧作業スクリプト・重複バックアップ・キャッシュは展開対象から外しています。
閲覧用の個人パスはマスクし、原本ZIPはリポジトリ外に保持しています。現在の検証証跡とは区別してください。
テストコードはtests/とgazebo/tests/に保持しています。
