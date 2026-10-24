# Physical AI 最終課題用の作業環境

WindowsのDocker Desktop上で、ROS 2 Jazzy＋Gazebo Harmonicを動かします。
ブラウザからGazeboの画面を開けるため、Windows側にROSやXサーバーを入れる必要はありません。
描画にはCPUを使います。GPUの割り当ては不要ですが、PCの性能によって表示が遅くなります。

2026-10-23にDocker Desktop上のGazebo／ROS 2でSTEP 2を実走行し、GOAL REACHEDを確認しました。
前傾を防ぐ前側支え輪と姿勢・接触監視を追加しています。実行方法と検証結果は末尾のSTEP 2節を参照してください。

## 保存場所

このプロジェクトの保存先は `C:\Users\USER\Documents\Codex\physical-ai-final` です。
ダウンロードフォルダでも使えますが、継続して編集するものはドキュメント内が管理しやすく、
アプリのインストール先であるProgram Filesへ入れる必要はありません。
この作業ではGitHubへのアップロードや公開は行っていません。

## まず起動する

1. Docker Desktopを開き、Linux containersのEngineが起動するまで待ちます。
2. PowerShellで、次を実行します。

```powershell
cd C:\Users\USER\Documents\Codex\physical-ai-final
docker compose up -d --build simulator
```

初回はROS、Gazebo、画面表示用のソフトをダウンロードするため、時間がかかります。
この構成はブラウザ表示を使い、Docker Desktopのホストネットワーク機能やGPU設定は使いません。

3. 次をブラウザで開きます。

[Gazeboの画面を開く](http://localhost:6080/vnc.html?autoconnect=true&resize=scale)

青い二輪ロボット、橙色の障害物、緑色の目標マーカーが表示されます。
ロボット前面は黄色です。起動直後はロボットが停止している状態です。
ブラウザ側にConnectボタンが出た場合はクリックしてください。

4. ロボットを少し動かし、通信とセンサーを確認します。

```powershell
docker compose exec -T simulator /ros_entrypoint.sh python3 /workspace/scripts/check_environment.py
```

このチェックは、ROSから前進指令を送り、Gazeboから位置・距離センサー・シミュレーション時刻が返ることを確認します。
ロボットが約3秒間前進するため、他の操作を止めた状態で実行してください。
成功するとPASSが表示され、結果が `outputs/environment-check.json` に保存されます。
再確認する場合は、障害物の直前へ進みすぎないよう、コンテナを再起動してから行ってください。

## 操作方法

短い前進・旋回のデモです。AI制御ではありません。

```powershell
docker compose exec -T simulator /ros_entrypoint.sh python3 /workspace/scripts/demo_drive.py1404
```

キーボードで操作する場合は次を実行します。画面に表示されたキー割り当てに従ってください。

```powershell
docker compose exec simulator /ros_entrypoint.sh ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

ROSのターミナルを開く場合です。

```powershell
docker compose exec simulator /ros_entrypoint.sh bash
```

このターミナル内では `ros2 topic list`、`ros2 topic echo /odom --once`、
`ros2 topic echo /scan --once` などを利用できます。

停止、再起動、ログの確認は次のとおりです。

```powershell
docker compose --profile workshop down
docker compose up -d simulator
docker compose logs --tail 100 simulator
```

`down`で学習モデルや演習ファイルは消えません。再起動するとGazeboのロボット位置は初期位置へ戻ります。
シミュレーションの設定を変更した場合は `docker compose restart simulator` を実行してください。
Dockerfileを変更した場合は `docker compose up -d --build simulator` を実行してください。

## 元のPushT演習を使う

元の教材一式は `workshop` サブフォルダへコピーしています。
元フォルダは変更していません。ノートブック・学習済みモデル・データ・動画はコピーにも残しています。

```powershell
docker compose --profile workshop up -d --build workshop
```

[JupyterLabを開く](http://localhost:8888/lab?token=roboops-workshop)

JupyterLab内の `notebooks/01_roboops_workshop.ipynb` を開いて使います。
このサービスは元の教材のDockerfileと依存関係を使います。
Gazeboのコンテナと、演習のAI環境のコンテナは別です。
現在、演習のACTモデルからGazeboロボットへ指令を送る処理は追加していません。
ROSの探索はシミュレータコンテナ内に限定しているため、別コンテナのPythonからrclpyで操作するには
ROS依存関係と通信設定の追加が必要です。

元のCI用 `train.py` / `eval.py` は、短い動作確認を目的としています。
保存済みのノートブック用学習記録は、`eval.py`が参照する`model`項目を持たないため、
保存済みACTモデルの再評価には、まずノートブックの評価手順を使ってください。
スクリプト用の前処理済みNPZは未生成です。元のスクリプトは変更していません。

## ファイルの役割

- `compose.yaml`: シミュレータと演習用サービスの起動設定。
- `docker/ros-gazebo.Dockerfile`: ROS 2、Gazebo、ブラウザ表示用ソフトのインストール。
- `docker/entrypoint.sh`: 仮想画面、ブラウザ表示、ROSの起動と停止。
- `simulation/worlds/practice.sdf`: 二輪ロボット、LiDAR、障害物、目標マーカー。
- `simulation/config/bridge.yaml`: ROSとGazeboのメッセージ変換。
- `simulation/launch/simulation.launch.py`: Gazeboとブリッジの一括起動。
- `scripts/check_environment.py`: 通信、センサー、ロボット移動の確認。
- `scripts/demo_drive.py`: AIを使わない短い動作デモ。
- `workshop`: コピーした元のPushT演習。
- `outputs`: この環境で生成する検証結果や録画の保存先。
- `manage.ps1`: PowerShell用の操作補助。直接Dockerのコマンドを実行しても同じです。

## ROSの入出力

- `/cmd_vel`: `geometry_msgs/msg/Twist`。前後速度m/sと旋回速度rad/sをROSからGazeboへ送信。
- `/odom`: `nav_msgs/msg/Odometry`。Gazeboからロボットの位置と速度を受信。
- `/scan`: `sensor_msgs/msg/LaserScan`。Gazeboから周囲の距離mを受信。
- `/clock`: `rosgraph_msgs/msg/Clock`。Gazeboからシミュレーション時刻を受信。

ロボットのモデルとワールドはこのプロジェクトに含まれます。起動時の外部モデルの取得は不要です。
STEP 2のルールベース自律走行を追加しました。AIの学習・推論接続、
提出用録画は次の実装です。緑色のマーカー自体には成功判定の機能はありません。

## PowerShellの操作補助

プロジェクト内で次のように実行できます。

```powershell
.\manage.ps1 Start
.\manage.ps1 Check
.\manage.ps1 Demo
.\manage.ps1 Workshop
.\manage.ps1 Logs
.\manage.ps1 Stop
```

PowerShellのスクリプト実行が制限されているPCでは、設定を変更せず、上のDockerコマンドを直接使ってください。

## ポートとトラブル対応

6080または8888を別のアプリが使っている場合は、`.env.example`を`.env`へコピーし、
`GAZEBO_WEB_PORT`や`JUPYTER_PORT`を変更してください。変更後は`docker compose up -d simulator`等で再作成します。

- Dockerに接続できない: Docker Desktopを開き、Engineの起動を待つ。Linux containersか確認する。
- ビルド中に取得に失敗: インターネット接続とDocker Desktopのプロキシ設定を確認する。
- 画面が出ない: `docker compose ps` と `docker compose logs --tail 100 simulator` を確認する。
- 画面が重い: Jupyterを同時に使わず、Docker Desktopのメモリ割り当てを確認する。最初はメモリ6GB以上が目安。
- Checkが失敗: ログを確認し、`docker compose restart simulator`後、画面が出てから再実行する。

Web画面のヘルスチェックは表示サービスの応答確認です。ロボットが実際に動くことの確認にはCheckを使ってください。

## GitHubへ登録するとき

GitHubへのアップロードはまだ行っていません。
元の教材のサブフォルダではなく、このプロジェクトのルートを登録対象にしてください。
ルートの`.gitignore`により、データ、学習済みモデル、動画、キャッシュ、`.env`を除外します。
そのためGitHubから取得しただけでは元のモデルやデータは揃いません。
元のノートブックにはデータや配布モデルを取得する手順があります。
自身で学習したモデルを配布する場合は、その保存先と取得方法を別途READMEへ追記してください。

コピーした教材のGitHub Actionsは`workshop/.github`内にあり、この新規リポジトリのActionsとしては実行されません。
自動検証を使う場合は、プロジェクトのルートに合わせたワークフローを別途追加します。
公開前には教材の再配布条件を確認し、教材を使った部分と自分で実装した部分をREADMEやレポートに記載してください。

## バージョンと参考資料

ROS 2 Jazzy / Ubuntu 24.04 / Gazebo Harmonicを採用しています。
Dockerのベースは公式の `ros:jazzy-ros-base-noble`、Gazeboは`ros-jazzy-ros-gz`経由で取得します。
ROS側はタグとaptを使うため、将来の再ビルドではパッチ版が更新される場合があります。
演習側は元の教材のDockerfileと`uv.lock`をそのまま使います。

- [Gazebo公式: ROSとの対応とインストール](https://gazebosim.org/docs/harmonic/ros_installation/)
- [ros_gz_bridge公式: 通信と型の対応](https://github.com/gazebosim/ros_gz/tree/jazzy/ros_gz_bridge)
- [公式ROS Dockerイメージの定義](https://github.com/osrf/docker_images/tree/master/ros/jazzy/ubuntu/noble)

## STEP 2: LiDARによる障害物の自動回避

`scripts/drive_to_goal_v3.py` は `/odom` と360度の `/scan` を使い、
障害物の位置や中継点を事前指定せず `(3, 1)` を目指します。AIは使いません。
車体・車輪を囲む半径0.33 mに余裕を加えた0.48 mの領域で通過方向を選びます。
回避する側を保持して左右の反転を抑え、直進方向も空くまで前進しません。
速度は最大0.22 m/s、旋回は最大0.8 rad/sです。
オドメトリでゴールの0.25 m以内に入ると停止し `GOAL REACHED!` を表示します。
車輪のオドメトリとGazeboの実位置には滑りによる差があるため、実座標の誤差0.25 mを保証する判定ではありません。

### 実行

Docker Desktopを起動し、他の走行プログラム・キーボード操作を終了してから実行します。
ZIPのダウンロード・展開は不要です。

```powershell
cd C:\Users\USER\Documents\Codex\physical-ai-final
.\run-step2.ps1
```

シミュレータを再起動して初期位置へ戻し、型を明示した購読で `/odom`、`/scan`、
`/step2/imu` の受信を最大120秒待ち、走行します。
待機ログは `outputs/step2-topic-readiness.log`、走行ログは `outputs/step2-run.log`、
位置・指令・姿勢・LiDAR推定余裕・接触監視の結果は `outputs/step2-run.json` に保存します。
起動失敗時はコンテナのログも `outputs/step2-startup-diagnostics.log` に保存します。
走行失敗時のPowerShellエラーには、末尾の具体的な停止理由を表示します。

不正スキャン、センサーの1秒以上の受信途絶、0.20 radを超える前後・左右の傾き、
障害物との接触、通過方向なしで停止します。走行の上限は240秒です。

### 今回修正した原因

前側の支えがないモデルが加速時に前傾していました。失敗後のGazebo画面でPitch=0.41 rad
（約24度）を確認しました。その状態ではLiDARが床を拾うと考えられ、
位置がほぼ変わらないのに最短距離が約1.14 mから0.60 mへ急変し、回避やBLOCKED停止が続いていました。

前側に低摩擦の支え輪を追加し、最大前進加速度を1から0.3 m/s²へ下げました。
水平姿勢をIMUで監視し、障害物に接触センサーを追加しました。
支え輪と床の接触も別トピックで受信し、接触監視系の動作確認に使います。
接触監視の設定は [Gazeboの公式チュートリアル](https://gazebosim.org/docs/harmonic/sensors/) と
[HarmonicのContactシステム実装](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/contact/Contact.cc) を参照しています。

障害物は直線経路上の `(1.5, 0.5)` にあります。
変更前のSTEP 1ワールドは `simulation/worlds/practice.step1.sdf.bak`、
今回の安定化修正前は `simulation/worlds/practice.sdf.before-stability-fix.bak` に保存しています。
ブリッジ・起動設定の安定化修正前にも同名末尾のバックアップがあります。
v2・compose.yaml・workshop教材とOneDrive原本は変更していません。GitHub公開もしていません。

### 実走行結果（2026-10-23 21:21 JST）

Docker Engineの名前付きパイプへの直接接続は拒否されましたが、Docker Desktopの
再起動ボタンと、次回起動時に一度だけ実行するローカル検証処理を使って実走行しました。
修正後は2回の実走行でGOAL REACHEDを確認しています。最終結果は以下です。

- 実際のGazebo／ROS 2で `GOAL REACHED!`、プロセス終了コード0。
- 最終オドメトリ: `(2.7584, 1.0458)`、目標まで約0.246 m。
- LiDARから計算した車体外接円との最小余裕: 約0.150 m。
- IMUの最大傾き: 約1.05e-8 rad。前傾は解消。
- 支え輪と床の接触受信: 11,113件。障害物との接触検出: 0件。
- 最終GUI実位置は表示丸めで約 `(2.65, 1.17)`。目標マーカーの半径0.4 m内です。

接触センサーは接触時に通知する方式です。通知ゼロだけを証明にせず、
床との接触受信、姿勢、LiDARの余裕、Gazeboの画面も合わせて確認しました。
この結果は今回の静的ワールドに対する検証であり、任意の迷路・移動障害物に対する到達保証ではありません。

### 検証用ファイル

- `scripts/test_step2_offline.py`: 障害物なし／現配置／元の配置、100ms・300msのスキャン遅延での簡易到達、不正スキャン・近接時停止、構文・XMLを検査。
- `scripts/wait_step2_ready.py`: 型を明示してROSの実データを待機。
- `scripts/run_step2_once.py`: 一度だけ起動時検証を行い、結果を保存。
- `simulation/launch/simulation.launch.py`: `outputs/step2-autotest.request` がある起動時だけ上記検証を実行。通常起動では自動走行しません。
- `outputs/step2-autotest-status.json`: 自動検証の実行結果。
- `outputs/before-stability-fix-step2-run.log` と同名JSON: 修正前の失敗記録。

簡易検証はPython 3で `python scripts/test_step2_offline.py` を実行します。
この簡易モデルはGazeboの接触物理を再現せず、実走行ログとは別です。

配布ZIPも内容・パス・サイズを確認して、チャットの作業用フォルダへ比較用に展開済みです。
ZIP版の地図＋A*方式は上書き適用していません。

### PowerShellから3配置をまとめて検証する

現在の制御コードを変更せず、障害物を現在の配置 `(1.5,0.5)`、中央寄り `(1.5,0)`、
ゴール側 `(1.8,0.9)` の順に置いて、各回でシミュレータを再起動します。
他の走行プログラムを終了してから、次を実行します。

```powershell
.\test-step2-cases.ps1
```

実行前の構成だけ確認する場合は `.\test-step2-cases.ps1 -CheckOnly` です。
このモードではDockerの操作もファイル変更も行いません。

結果は `outputs/step2-cases/日時-ID/` の配置別フォルダと `summary.json` に保存します。
ゴール到達に加え、障害物接触がなく、床との接触受信により監視の動作を確認できた回だけPASSとします。
このゴール判定は引き続きオドメトリに基づきます。
失敗した回も理由とログを残し、次の配置を試します。
最後にワールドのファイルを実行前と同じバイト列へ戻し、元の配置でシミュレータを再起動します。
既存の単独走行ログも退避・復元するため、配置別の新しい結果は上記の専用フォルダで確認してください。
実行中にPowerShell自体を強制終了すると復元処理が動かないことがあるため、
その場合は結果フォルダの `practice.before-tests.sdf` が復旧用バックアップになります。

追加時の検査ではPowerShellの構文、3配置のXML生成、途中失敗を模擬した際のワールド・ログ復元を確認しました。
新しい3配置の一括走行は、追加時点では実際のGazeboで未実施です。

### 次の段階: Gazeboの実位置による独立評価

走行に使う `drive_to_goal_v3.py` はそのままに、Gazeboが配信するワールド座標を
評価専用の `/step2/ground_truth` で受信する機能を追加しました。
PosePublisherはモデルだけの親ワールドからの姿勢を配信し、ROSへTFMessageとして変換します。
設定の根拠は [PosePublisher公式仕様](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/pose_publisher/PosePublisher.hh) と
[ros_gz_bridgeのTF変換実装](https://github.com/gazebosim/ros_gz/blob/jazzy/ros_gz_bridge/src/convert/tf2_msgs.cpp) です。
追加前のワールドとブリッジは末尾 `.before-ground-truth.bak` にバックアップしています。

Docker Desktopを起動し、他の走行を終了して、PowerShellで実行します。

```powershell
.\evaluate-step2.ps1
```

再起動してトピックを待った後、独立評価プロセスが実位置とオドメトリの受信を確認してから
既存v3を起動します。測定が途絶した場合は停止します。
走行終了後、停止状態を1秒測定し、実位置のゴール誤差と計算位置とのずれを報告します。
実位置は操舵・経路選択には使いません。

- `PASS`: 既存走行が到達し、実位置も目標から0.25m以内。接触検出なしで監視の動作も確認。
- `FAIL`: 測定は完了したが、実位置の誤差などが基準外。計算位置でGOAL REACHEDでも、この評価ではFAILになり得ます。
- `INCOMPLETE`: 測定データ不足・途絶、走行プログラムの失敗、接触監視の動作未確認など。測れていない値を成功扱いしません。

結果は `outputs/step2-evaluation/日時-ID/` に保存します。
`evaluation.json` が最終判定、`world-odom-trace.json` が両方の位置の記録、
`driver-run.json` が今回の走行記録、`evaluation.log` が画面出力です。
既存の `outputs/step2-run.json` は検証後に元へ戻します。
実位置と計算位置を比較する際は、受信から1秒以内・両者のシミュレーション時刻差0.10秒以内のデータだけを使います。

準備だけの検査は `.\evaluate-step2.ps1 -CheckOnly`、
判定ロジックの検査は `python scripts/test_step2_evaluation.py` です。
追加時点で判定ロジック4テスト、既存の簡易走行5ケース、Python／PowerShell構文とXMLを検査済みです。
新しい実位置トピックの受信・Gazeboでの独立評価は、追加時点では未検証です。

### v4: 計算位置の停止余裕を厳しくする

2026-10-24の実位置評価では、v3の最終オドメトリ誤差は0.222 m、
実位置のゴール誤差は0.379 m、両者のずれは0.167 mでした。
走行中の最大ずれは0.178 mで、障害物接触はありませんでした。
測定結果は `outputs/step2-evaluation/20261024-115735-9cc71f/evaluation.json` に残しています。

v3は比較用に変更せず残し、`scripts/drive_to_goal_v4.py` を追加しました。
v4は同じLiDAR回避処理を使い、計算位置での停止条件だけを0.25 mから0.03 mへ厳しくしています。
観測済みの約0.18 mのずれに対して余裕を取る変更で、位置推定の偏りそのものを補正するものではありません。
実位置の評価基準は引き続き0.25 mです。実位置は走行制御には使いません。
このずれの上限が今後も一定であるという保証はなく、合格するかは実走行で確認します。

PowerShellでv4を独立評価するには次を実行します。

```powershell
.\evaluate-step2.ps1 -Driver v4
```

v3との比較は `.\evaluate-step2.ps1 -Driver v3` でできます。
パラメータ省略時は従来どおりv3です。結果フォルダ名とevaluation.jsonに版名を記録します。
v4の結果は `outputs/step2-evaluation/v4-日時-ID/` に保存します。

追加時点で、v4の簡易走行5ケース・不正センサー時の停止・Python構文・独立評価4テスト・
PowerShell構文と版指定の構成検査が成功しています。
v4のGazebo実走行および実位置25cm以内への改善は、追加時点では未検証です。
簡易検証は `python scripts/test_step2_v4_offline.py` で再実行できます。

### STEP 3: ローカル学習モデルで目的地を選ぶ（2026-10-24追加）

`python scripts/complete_step3.py` が残りの実行時検証をまとめて行います。
プロジェクトのフォルダで、Docker DesktopとOllamaが起動しており、他の走行プログラムが終了している状態で実行してください。
この処理はシミュレータを毎回原点へ再起動します。実機向けの制御ではありません。
保存済みの `gpt-oss:20b` だけを使用し、モデル取得・有料API・APIキー・GitHub送信は行いません。
Dockerイメージも自動取得せず、既存イメージがなければ停止します。

追加した目的地は `scripts/destinations.json` で管理します。
東ステーション `(3,1)` と、2つ目の候補として南ステーション `(1,-1)`、南側の手前の待機所 `(0.5,-1)`、西ステーション `(-1,0)` を登録しました。
名称は今回追加した仮の名称です。既存の `(3,1)` の実位置PASSログ3回は `historical_reports` に参照を保存しました。
変更後の構成では全目的地を実走行で再確認するまで走行対象にしません。
`state` の書き換えだけでは有効化されず、実位置PASSの証拠3回・証拠ファイルのハッシュ・ワールドと制御コードのハッシュを照合します。

一括処理は次の順に実行し、失敗した段階で終了します。

1. Ollamaの保存済みモデルとDockerへの接続確認。
2. 東ステーションを原点から3回走行し、実位置誤差25cm以内・障害物接触なし・接触監視動作を確認。
3. 南ステーションから候補を順に探索し、3回連続で同じ基準を満たした最初の候補を有効化。失敗した候補は有効化しません。
4. 本物の学習モデルで日本語の言い換え・停止・否定・曖昧・複数目的地・未知・指示上書きなど17件を検証。
5. 自然言語から東ステーションと2つ目の目的地を選び、v5接続後の実位置を再評価。
6. 未知の目的地の指示で、走行を起動せず、停止を確認。

個別に実行する場合は次の通りです。

```powershell
python scripts/test_destination_control.py
python scripts/qualify_destinations.py --check-only
python scripts/qualify_destinations.py --ids east_station
python scripts/qualify_destinations.py
python scripts/validate_local_ai.py
python scripts/destination_control.py "東側の資材受け渡し場所へ向かって"
python scripts/destination_control.py "東側の資材受け渡し場所へ向かって" --execute
```

`--execute` を付けない選択確認では走行しません。
推論はOllamaの `127.0.0.1:11434` に限定し、HTTPプロキシや外部へのリダイレクトは使いません。
別のローカルポートは `--port` で指定できます。
単語の含有判定による目的地の選択や、AI失敗時のキーワード方式への切替はありません。
モデルには目的地IDと説明だけを渡し、返されたIDを登録済み座標に変換します。
モデルが出した座標・シェル命令・追加フィールドは受け付けません。
未知・曖昧・停止・接続失敗・不正応答・未検証目的地では走行を開始しません。
実行モードは推論の前後にゼロ速度を送信し、受信したオドメトリ速度で停止を確認します。
停止確認に失敗した場合は `STOP_UNCONFIRMED` と記録し、停止成功とは報告しません。
実AIの17件検証が通っていない構成でも走行を拒否します。
有限のテスト合格は、あらゆる日本語での正解を保証するものではありません。

新しい走行・候補検証は `outputs/navigation.lock` により同時実行を拒否します。
既存の `evaluate-step2.ps1` もこのロック中の実行を拒否するようにしました。
別途手動で起動したROS走行ノードとの同時利用は対象外です。必ず他の走行プログラムを終了してください。
強制終了でロックが残った場合は、実行中の処理がないことと停止を確認してからロックを除去してください。
停止確認は計算位置側の速度に基づき、Gazeboの実位置評価とは別です。

ログの保存先は以下です。

- `outputs/destination-offline-tests.json`: 模擬AI・模擬Dockerの安全制御テストと簡易走行。実AI／Gazeboではありません。
- `outputs/local-ai-validation.json`: 実AIの17件検証。接続不能時もINCOMPLETEと理由を保存。
- `outputs/destination-qualification/日時-ID/summary.json`: 候補探索・複数回検証の結果。
- `outputs/step2-evaluation/qualify-.../evaluation.json`: 各回の実位置評価。
- `outputs/language-goals/日時-ID/selection.json`: 入力、モデル名とモデル識別値、選択結果、目的地、評価、停止確認。
- 同じフォルダの `stop.log` と `world-evaluation/`: 停止の出力と接続走行の実位置ログ。

v5に追加した `--output` は評価ごとに走行結果を分離するためのものです。
既存の単独走行結果を誤って今回の成功として採点することを防ぎます。
v5の回避・停止アルゴリズム自体は維持し、v4のソース、教材、ワールド配置は変更していません。
Ollamaの接続は [公式API仕様](https://github.com/ollama/ollama/blob/main/docs/openapi.yaml) と
[構造化出力の公式説明](https://ollama.com/blog/structured-outputs) を参照しています。

今回の環境ではオフライン安全制御21テスト、4目的地×3条件の簡易走行12件、既存実位置判定4テスト、Python構文、PowerShell構文・CheckOnlyを検証しました。
実AIはローカル接続拒否、Dockerは名前付きパイプへのアクセス拒否で実行できませんでした。
したがって2つ目の目的地の実位置PASS、実AIの意味理解、ROSの実停止、自然言語からの接続走行は未検証です。
候補やモデルを成功扱いで有効化していません。ローカルAIサーバーの起動も実行環境の自動承認審査に拒否されたため、自動起動はしていません。

追補: 一括検証は6段階の進捗を表示します。2目的地それぞれで意図したIDと実位置PASSが一致すること、未知指示で実AIの判断と停止確認が両方得られたことを確認します。モデルの接続失敗を未知指示の成功として扱いません。この最終判定を含むオフライン23テストと簡易走行12ケースが成功していますが、実環境の検証はサービス接続で停止しています。
通常のWindows PowerShellで `python -u scripts/complete_step3.py 2>&1 | Tee-Object outputs/step3-full-check.log` を実行すると、再開時の画面出力を共有フォルダ内に保存できます。最終行付近の `STEP 3 runtime checks PASS` が全検証成功の目印です。

### 2026-10-24 実検証の更新

通常のPowerShellで東 `(3,1)` と南 `(1,-1)` が各3回連続で実位置PASSとなりました。
東の実位置誤差は約19～20cm、南は約15cmで、全6回とも障害物接触なし、停止確認も成功しています。
3回ずつの証拠を現在のワールド・v5・評価器のハッシュと照合して再利用します。

保存済みgpt-oss:20bは推論が時間切れになり、待ち時間延長後も接続が切断されました。
ユーザーの明示許可により約1.4GBの無料ローカルモデル `qwen3:1.7b` を追加しました。
日本語の説明と例を用意し、学習モデルで移動意図を判定してから目的地を選ぶ2段階へ変更しました。
各段階は本物のモデル推論です。入力中の単語を検索して目的地に結びつける方式は使っていません。
モデルを各問題の直後に解放する設定をやめ、2分間保持して再ロードを減らしています。
実AIの元の17件と、プロンプトの例に含めていない別の13件、計30件が全てPASSしました。
停止・否定・質問・未知目的地・複数目的地・回答上書きの依頼では、目的地への移動を選択しませんでした。
これは30件の確認結果で、任意の入力に対する安全性の保証ではありません。
初期の失敗結果も `outputs/local-ai-validation-first-small-model.json`、
`outputs/local-ai-validation-japanese-first.json`、`outputs/local-ai-validation-before-intent-gate.json` に保持しています。
最終結果は `outputs/local-ai-validation.json` で、モデル識別値・選択器・検証器・目的地説明の一致を確認します。

残る実検証は、自然言語からv5へ接続した東・南への実走行と、未知指示に対するROS上の停止確認です。
Dockerへのアクセスがエージェントの実行環境では拒否されるため、ここだけは通常のPowerShellから実行します。
Docker Desktopを起動し、別のPowerShellで `ollama serve` を実行したまま、プロジェクトで次を実行してください。

```powershell
.\verify-step3.ps1
```

文字コード設定と小型モデル指定はこのスクリプト内で設定します。
一致する証拠がある実走行とAI検証は再利用し、接続走行と未知指示の実停止確認へ進みます。
モデルやDockerイメージの追加取得はしません。
最新の画面出力は `outputs/step3-full-check.log`、各回の出力は日時付きの同名ログへ保存します。
直接実行する場合は `python -u scripts/complete_step3.py --model qwen3:1.7b` です。
一括処理の既定モデルも小型モデルに変更しました。
全てを再確認したい場合のみ `--recheck-navigation --recheck-ai` を指定します。
今回のオフライン検査は27テスト・簡易走行12件、既存評価判定4テスト、Python構文と新PowerShell構文が成功しました。
`verify-step3.ps1` の通常Windows環境での完走と、最終ROS接続検証はまだ実施していません。

### 最終確認: STEP 3 全検証PASS（2026-10-24）

通常のPowerShellでverify-step3.ps1が最後まで完走し、保存された個別ログでも確認しました。
自然言語から学習モデルが東ステーションを選択してv5へ接続し、実位置誤差0.1959835983mでPASS。
南東の点検場所という自然言語から南ステーションを選択してv5へ接続し、実位置誤差0.1470367458mでPASS。
両方とも障害物接触なし、開始前と終了後の停止確認に成功しています。
「登録されていないコンビニに行って」は実AIがunknownと判定し、走行を起動せず、停止確認にも成功しました。
東・南各3回の実位置PASS証拠と、実AI30件の合格証拠も、現在の構成に対して有効であることを確認しました。
結果はoutputs/step3-final-verification.jsonに集約しました。今回依頼されたシミュレータでの検証は完了です。
実際の接続記録はoutputs/language-goals/20261024-165000-802f0bb2/、20261024-165112-d3a817ba/、20261024-165142-d8cb7e7a/にあります。
