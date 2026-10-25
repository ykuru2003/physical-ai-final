# Physical AI：PushT教材を中心にしたロボット学習プロジェクト

PushTとLeRobot ACTの教材で、**データ取得 → 品質検証 → 学習 → 評価 → 自動テスト**を一通り実行するプロジェクトです。
ROS 2／Gazeboによる日本語ナビゲーションを、追加機能として含みます。
教材で学習したACTとGazeboの走行を接続する処理は、まだ実装されていません。

説明はこのREADME、操作は `project.ps1`、Git設定とCIはルートで一元管理します。

- [準備](#準備)
- [教材を起動する](#教材を起動する)
- [データ取得から評価まで](#データ取得から評価まで)
- [操作コマンド](#操作コマンド)
- [コードの構成](#コードの構成)
- [変更する場所とデータの流れ](#変更する場所とデータの流れ)
- [テストとCI](#テストとci)
- [Gazebo拡張](#gazebo拡張)
- [出力と一時ファイル](#出力と一時ファイル)
- [Gitと実行環境の設定](#gitと実行環境の設定)

## 準備

教材はDocker内のPython 3.12環境で実行します。GPUや有料APIキーは必要ありません。

- Windows・macOS：Linuxコンテナを使えるDocker Desktopを準備します。WindowsはWSL 2 backendを有効にします。
- Linux：Docker EngineとCompose pluginを準備します。
- GitHubでの管理・CIを行う場合はGitとGitHubアカウントも用意します。
- Dockerを使わないオフライン検査には、ローカルのPython 3.12とPowerShellが必要です。

インストール手順は [Windows](https://docs.docker.com/desktop/setup/install/windows-install/)、
[macOS](https://docs.docker.com/desktop/setup/install/mac-install/)、
[Linux](https://docs.docker.com/engine/install/) の公式説明を参照してください。

プロジェクトのフォルダで次を確認します。

```powershell
docker --version
docker compose version
docker run --rm hello-world
```

## 教材を起動する

Dockerを起動してから、プロジェクト直下のPowerShellで実行します。

```powershell
.\project.ps1 Start
```

初回は必要なライブラリを含むイメージをビルドします。
[JupyterLab](http://localhost:8888/lab?token=roboops-workshop)を開き、
`workshop.ipynb` を上から進めてください。
GazeboとOllamaは、教材の起動・学習・PushT評価には必要ありません。

ポートを変える場合は `.env.example` を `.env` にコピーして `JUPYTER_PORT` を変更します。
この設定ファイルは教材とGazeboで共用します。`.env` はGitに保存しません。

終了・状態確認・ログ表示は次のコマンドです。

```powershell
.\project.ps1 Status
.\project.ps1 Logs
.\project.ps1 Stop
```

`Stop` は教材を終了します。Gazeboは `SimulatorStop` で別に終了します。

## データ取得から評価まで

Notebookは手順を学ぶために各処理を明示しています。
同じ処理を繰り返す場合やCIでは、共通のPythonコマンド `python -m roboops` の4つのサブコマンドを使います。
すべてプロジェクト直下から実行します。

```powershell
# 固定revisionから20エピソード分を取得・前処理する
docker compose run --rm workshop python -m roboops download --max-episodes 20

# 必須項目、shape、値、エピソード長を確認する
docker compose run --rm workshop python -m roboops validate

# 教材・データ・モデルのテストを実行する
.\project.ps1 Test

# CI用の小さなACTを学習し、checkpointを保存する
docker compose run --rm workshop python -m roboops train --config configs/train_ci.yaml

# 保存したcheckpointを固定seedのPushT環境で評価する
docker compose run --rm workshop python -m roboops evaluate --config configs/eval_ci.yaml
```

- 取得元は `lerobot/pusht_keypoints`、revisionは `roboops/schema.py` で固定しています。
- 処理済みデータは `src/pusht_keypoints.npz` に保存します。
- 学習のweight・config・正規化統計・履歴は、設定されたcheckpointフォルダに保存します。
- 評価結果や動画は `evaluation/` に保存します。`--save-video` を付けると評価動画を保存できます。
- Notebookの30 epoch学習と、CI向けの短い学習は、用途に合わせて条件が異なります。

`Test` のデータ検査には、先に処理済みデータの作成が必要です。
学習条件と保存先は `configs/train_ci.yaml`、評価条件と合格基準は `configs/eval_ci.yaml` にあります。
コマンドの引数は `python -m roboops train --help` などで確認できます。
ヘルプだけならTorch・LeRobot・Gym・ROSは読み込みません。
ローカルPythonでもプロジェクト直下から `python -m roboops` で実行できます。

## 操作コマンド

PowerShellの操作入口は、ルートの `project.ps1` だけです。
別フォルダから呼んでも、実行先はこのプロジェクトを基準にします。

教材の操作：

- `Start`：教材をビルドして起動。`Workshop` は同じ操作の別名です。
- `Stop` / `Status` / `Logs`：教材の終了・状態・ログ。
- `Build` / `Shell`：教材イメージのビルド・コンテナ内のシェル。
- `Validate`：教材とGazeboのCompose設定を検査。
- `Test`：教材のpytest。

Gazeboの操作：

- `Simulator`：Gazeboをビルドして起動。
- `SimulatorStop` / `SimulatorStatus` / `SimulatorLogs` / `SimulatorShell`：終了・状態・ログ・シェル。
- `TestExtension`：オフラインのPython検査と統合されたPowerShell検査。
- `Verify`：実ローカルAIからシミュレータの走行・停止までを検証。
- `Evaluate`：単一ゴールの実位置評価。`-Driver navigation -GoalX 3 -GoalY 1` などを指定できます。
- `Cases`：障害物3配置のbaseline制御の比較試験。終了時に元のワールドと記録を復元します。
- `Check` / `Demo` / `RunReference`：通信確認・短いデモ・baseline制御の単独走行。
- `Clean`：古いGazeboログを復元用ZIPへ整理。

`Check`・`Demo`・`RunReference` はロボットを動かします。
`Verify`・`Evaluate` はシミュレータを再起動して原点へ戻します。
`Evaluate`・`Cases`・`Clean` は `-CheckOnly` で準備や対象だけを確認できます。
ほかの操作に `-CheckOnly` を付けた場合は実行前にエラーにします。

```powershell
.\project.ps1 Help
.\project.ps1 Evaluate -Driver navigation -GoalX 3 -GoalY 1 -CheckOnly
.\project.ps1 Cases -CheckOnly
.\project.ps1 Clean -CheckOnly
```

## コードの構成

```text
physical-ai-final/
  README.md                 準備・使い方・開発の説明
  project.ps1               教材とGazeboの操作をまとめた入口
  .github/workflows/ci.yml   教材とオフライン検査の2ジョブ
  .gitignore                保存しないファイルと証跡の例外
  .gitattributes            改行・検証対象ファイルのバイト列の扱い
  .dockerignore             両方のDockerビルドで使う除外設定
  .env.example              共通の環境設定例
  compose.yaml / Dockerfile 教材の実行環境
  pyproject.toml / uv.lock   教材の依存関係
  workshop.ipynb            講義本編（ここから始める）
  configs/                  学習・評価条件
  roboops/
    __main__.py             データ取得・検査・学習・評価の共通入口
    *.py                    用途別の実装
  tests/
    test_*.py               教材と構成の検査
    Test-Project.ps1        操作コマンドの統合検査
    run_powershell.py        検査用一時ディレクトリの管理
  gazebo/
    compose.yaml            Gazebo専用の実行環境
    Dockerfile / entrypoint.sh  ROS・Gazeboイメージと起動処理
    simulation/             ワールド・センサー・ROSブリッジ
    scripts/                AI選択・走行・実位置評価
    tests/                  Gazeboのオフライン検査
    outputs/                現在の検証記録と最新ログ（到達評価は world-evaluation/*.json）
  src/                      元データ・取得記録・学習用NPZ
  checkpoints/              学習済みモデル・設定・正規化統計
  evaluation/               評価結果・動画（すべてGit対象外）
  .cache/test-runs/          テスト中の一時データ
  work/             過去の作業記録の復元用ZIP
```

実行環境は教材とGazeboで異なるため、ComposeとDockerfileはそれぞれにあります。
ビルドの除外設定と環境変数は共用し、操作・テスト・説明・Git設定を重複して置きません。
GazeboのPython実装は `gazebo/scripts/` に直接置き、中継だけのファイルや細かな実装用サブフォルダは作りません。
baseline・preciseは `reference_navigation.py --profile baseline` / `--profile precise` で停止距離を選びます。navigationは現在の走行処理です。
全体検証は `verify_navigation.py`、ROSからの走行要求処理は `verify_navigation.py requested-drive` です。旧名の互換入口はありません。

## 変更する場所とデータの流れ

最初はNotebookで入出力を確認し、`roboops/__main__.py` から `training.py` または `evaluation.py` へ進むと追いやすくなります。
既存の責務に含まれる処理は、そのモジュールへ追加します。操作入口や設定ファイルを機能ごとに増やす必要はありません。

`roboops/` の役割：

- `__main__.py`：サブコマンドの引数と処理の呼び出し。
- `schema.py`：フィールド名・次元・固定データセット・既定の保存先。
- `download.py`：取得、キャッシュ確認、NPZへの変換。
- `validation.py`：順序付きの `Check(label, passed, detail)` を返すデータ検査。
- `data.py`：NPZ読込、エピソード分割、action chunk、正規化統計。
- `normalization.py`：正規化統計の保存・読込と座標の変換。
- `policy.py`：ACTの構築と、PushTの観測・actionへの接続。
- `training.py`：DataLoader、最適化、checkpointと履歴の保存。
- `rollout.py`：1エピソードの実行と集計。Torch・Gymのimportには依存しません。
- `evaluation.py`：checkpoint・環境の準備、固定seedの評価、動画とmetricsの保存。
- `config.py`：YAML設定の読込。

学習処理は `prepare_loaders()` → `train_policy()` → checkpoint・metrics保存の順です。
評価は `run_evaluation()` から各seedの `evaluate_episode()` を呼びます。

PushTの主な入力は、agent位置の2次元とT字ブロックのkeypointの16次元です。
actionは、agentが次に向かう目標座標の2次元です。
train/validationはエピソード単位で分け、正規化統計もtraining側だけで計算します。
行単位で混ぜると、隣接するchunkが共有する未来actionから評価用の情報が学習へ漏れるためです。
chunkの末尾は同じエピソードの最後のactionで埋め、`action_is_pad` で有効な範囲を区別します。

ACTは正規化済みのTorch Tensorを受け取ります。
`PushTPolicyRunner` はそれを、生の観測を受け取って生の目標座標を返す `reset()`・`select_action(observation)` のインターフェースへ変換します。
別のPolicyもこのインターフェースを実装すれば、評価処理を再利用できます。

評価結果の意味：

- `initial_reward`：実行前のgoal coverageから求めた初期報酬。
- `max_reward`：初期報酬も含めた最大報酬。
- `reward_gain`：`max_reward - initial_reward`。
- `success`：環境の `is_success` が一度でも成立したか。

集計は `rollout.py`、閾値との比較は `evaluation.py`、閾値は `configs/eval_ci.yaml` にあります。
CI用の小さな閾値は処理の動作確認用で、十分なタスク性能を保証するものではありません。

## テストとCI

教材の静的検査と、ダウンロード不要の回帰テスト：

```powershell
docker compose run --rm workshop ruff check .
docker compose run --rm workshop pytest -q tests/test_preparation.py tests/test_rollout.py tests/test_cli.py
```

処理済みデータとモデルを含む教材テストは `project.ps1 Test` で実行します。
Gazebo側のオフライン検査は `project.ps1 TestExtension` です。
操作コマンドの検査だけなら、次を実行できます。

```powershell
pwsh -NoProfile -File tests/Test-Project.ps1
```

操作コマンドの検査はDocker・Python・Ollamaの業務処理を模擬します。
一時ディレクトリの管理には実際のPythonを使い、正常終了・テスト失敗のどちらでもコピーを片付けます。
`work` はテストの実行場所に使いません。

CIは `.github/workflows/ci.yml` の1ファイルです。この階層はGitHub Actionsの固定配置です。
`workshop` ジョブはDockerビルド、Ruff、データ取得・検証、pytest、小規模学習、PushT評価を実行します。
`offline` ジョブはGazeboのPython検査、リポジトリ構成、統合PowerShell検査を実行します。
オフラインの合格は、実走行や実AIの再検証の合格を意味しません。

## Gazebo拡張

WindowsのDocker Desktop上でROS 2 JazzyとGazebo Harmonicを動かします。
ホスト側にROSをインストールする必要はありません。
日本語の目的地選択には、ローカルのOllamaと `qwen3:1.7b` を使います。
走行と障害物回避はLiDARを使うnavigation制御が担当します。

```powershell
.\project.ps1 Simulator
```

[Gazeboの画面](http://localhost:6080/vnc.html?autoconnect=true&resize=scale)を開きます。
Ollamaが動いていなければ別のPowerShellで `ollama serve` を起動します。
`ollama list` に `qwen3:1.7b` がない場合だけ、`ollama pull qwen3:1.7b` で取得します。

```powershell
.\project.ps1 Verify
```

この検証はモデルやDockerイメージを追加ダウンロードせず、有効な既存の証跡を再利用します。
すべての到達・実AI検証をやり直す場合は、次を拡張フォルダで実行します。

```powershell
Push-Location gazebo
try {
    python scripts/verify_navigation.py --model qwen3:1.7b --recheck-navigation --recheck-ai
} finally { Pop-Location }
```

自分の日本語で選択だけを確認する場合も、拡張フォルダで実行します。

```powershell
Push-Location gazebo
try {
    python scripts/destination_control.py "東側の資材受け渡し場所へ行って" --model qwen3:1.7b
} finally { Pop-Location }
```

実際に走行させる場合は `--execute` を付けます。走行ごとに原点へ戻ります。
実AIの合格は有限のテスト結果であり、任意の日本語入力で正しく判断する保証ではありません。
東 `(3, 1)` と南 `(1, -1)` の過去の実位置PASS記録は保持しています。
コマンド・ROSトピック・出力名を役割名に変更したため、現在の構成では到達資格とローカルAIの再検証が必要です。`project.ps1 Verify` で再検証します。古いハッシュを新しいコードに合わせて書き換えることはしません。旧トピック名・旧ハッシュを含む記録は `work/gazebo-history.zip` に原文のまま保管しています。
未登録・曖昧・停止指示、推論失敗、不正応答、未検証の目的地では走行を開始しません。
到達基準は実位置で目標の25cm以内です。実位置は評価に使い、経路の選択には使いません。
連続移動、専用入力画面、教材ACTとGazeboをつなぐadapterは未実装です。

目的地は `gazebo/scripts/destinations.json` で管理します。
追加・変更後は拡張フォルダで `python scripts/qualify_destinations.py` と `python scripts/validate_local_ai.py --model qwen3:1.7b` を実行します。
`destination_control.py`・`navigate_to_goal.py`・`evaluate_navigation.py`・`validate_local_ai.py` は検証記録とハッシュ照合するため、変更時は対応する実走行・実AIの再検証が必要です。
合格記録のハッシュを手で更新して通すことはしません。

## 出力と一時ファイル

- `src/`：元データを直下の `frames.parquet`（観測・action）、`episodes.parquet`（エピソード情報）、`tasks.parquet`、`info.json`、`stats.json` にまとめます。`source.json` にrevisionとSHA-256を記録します。
- `.cache/lerobot/`：LeRobotが必要とする `meta/`・`data/chunk-*` の配置を元データから自動生成します。削除しても再生成できます。
- 学習・検査用の `pusht_keypoints.npz` と取得条件も `src/` 直下に保存します。
- ダウンロードのキャッシュはHugging Face標準の場所（Dockerでは専用ボリューム）に保存し、`src/` へ混ぜません。
- `checkpoints/`：教材で学習したモデル・設定・正規化統計・学習履歴。
- `evaluation/`：評価結果と動画。
- `.cache/ci/checkpoint/`：CI向けの短い学習で作るモデル。教材の学習済みモデルと保存先を分けます。
- `gazebo/outputs/`：現在の検証記録と最新ログ。
- `.cache/test-runs/`：本体のテスト用一時データ。終了時に片付けます。
- `gazebo/.cache/`：拡張のテスト用一時データと、再生成できる検査結果（キャッシュ直下のJSON）。
- `work/gazebo-history.zip`：再生成できない過去の走行ログを残した1個のZIP。移動前のコピーやテスト用バックアップは削除済みです。
- `gazebo/work/`：今後 `Clean` で古いログを整理する場合に作成するZIPの保存先。

古いGazeboログは `project.ps1 Clean -CheckOnly` で候補を確認し、`project.ps1 Clean` で整理します。
検証に必要な証跡・最新ログを残し、ZIPの内容をSHA-256で照合してから元の場所を片付けます。
ZIP内の `__archive_manifest__.json` に元パスとハッシュがあります。
ZIPは `work/` 直下へ置き、保存済みZIPを再びログ整理の対象にはしません。
教材データと学習済みモデルはログ整理の対象にしません。
走行ロック・自動試験マーカーがある場合は整理を開始しません。

別途起動した走行プログラムと同時に操作しないでください。
強制終了で `outputs/navigation.lock` が残った場合は、実行中の処理がないことと停止を確認してから除去します。

## Gitと実行環境の設定

保存対象のルールは `.gitignore`、改行とバイト列のルールは `.gitattributes` にまとめています。
秘密情報、データ、モデル、通常ログ、キャッシュ、バックアップは保存しません。
Gazeboの現在の検証概要は、ルートの `.gitignore` に明示した例外で保存します。過去の合格記録はローカルの履歴ZIPに保持しています。
既にGit管理されたファイルは、`.gitignore` の追記だけでは対象から外れない点に注意してください。

両方のDockerビルドでルートの `.dockerignore` を使います。
ルートの `.env` はGazeboのCompose呼び出しにも明示的に渡します。
`pyproject.toml` は教材の依存関係、`uv.lock` は再現するバージョン、2つのComposeファイルはそれぞれの環境とポートを管理します。

新しく取得する場合は、このリポジトリへのアクセス権がある環境で実行します。

```powershell
git clone https://github.com/ykuru2003/physical-ai-final.git
Set-Location physical-ai-final
```

GitHubへ保存する際はデータ・モデル・ログ・認証情報が差分へ混ざっていないことを確認してください。
