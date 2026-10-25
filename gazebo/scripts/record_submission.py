"""Record a fresh real-AI navigation run without editing the verified controller.
Host: --run (optional --output-root PATH for an extra export). Container: --capture DIR.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap
import time
import uuid


def save_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def overlay(folder, instruction, model, phase, detail=""):
    # textfile+expansion=none: user input never becomes a filter expression.
    lines = [
        "日本語指示 → 実AIの目的地選択 → Gazeboで移動・停止",
        "入力: " + instruction,
        "モデル: " + model,
        "状態: " + phase,
        detail,
    ]
    content = "\n".join("\n".join(textwrap.wrap(s, 42)) for s in lines if s)
    temp = folder / "overlay.tmp"
    temp.write_text(content + "\n", encoding="utf-8")
    os.replace(temp, folder / "overlay.txt")
    with (folder / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {"unix_time": time.time(), "phase": phase, "detail": detail},
                ensure_ascii=False,
            )
            + "\n"
        )


def capture_command(folder, width, height, font):
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-f",
        "x11grab",
        "-framerate",
        "15",
        "-video_size",
        f"{width}x{height}",
        "-i",
        os.environ.get("DISPLAY", ":99"),
        "-t",
        "900",
        "-vf",
        f"pad=ceil(iw/2)*2:ceil(ih/2)*2+240:0:240:black,drawtext=fontfile={font}:textfile=overlay.txt:reload=1:expansion=none:fontcolor=white:fontsize=23:x=16:y=12:line_spacing=4",
        "-an",
        "-c:v",
        "libx264",
        "-threads",
        "2",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-progress",
        "progress.txt",
        "-n",
        "submission.mp4",
    ]


def capture_worker(folder):
    """Container-only X11 recorder. Host controls stop through the mounted folder."""
    folder = folder.resolve()
    font = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if not font.exists():
        raise RuntimeError(
            "Japanese font missing; rebuild the existing simulator image."
        )
    display = subprocess.run(
        ["xdpyinfo"], capture_output=True, text=True, check=True
    ).stdout
    match = re.search(r"dimensions:\s+(\d+)x(\d+)", display)
    if not match:
        raise RuntimeError("Cannot read the X11 desktop dimensions")
    width, height = map(int, match.groups())
    command = capture_command(folder, width, height, font)
    save_json(
        folder / "capture-command.json",
        {"argv": command, "desktop_size": [width, height]},
    )
    with (folder / "ffmpeg.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command, cwd=folder, stdin=subprocess.PIPE, stdout=log, stderr=log
        )
        started = time.monotonic()
        ready = False
        try:
            while process.poll() is None:
                progress = folder / "progress.txt"
                text = progress.read_text(errors="replace") if progress.exists() else ""
                if not ready and any(
                    int(n) > 0 for n in re.findall(r"^frame=(\d+)", text, re.M)
                ):
                    save_json(
                        folder / "capture-ready.json",
                        {"status": "RECORDING", "unix_time": time.time()},
                    )
                    ready = True
                if (folder / "stop-recording").exists():
                    process.stdin.write(b"q\n")
                    process.stdin.flush()
                    break
                if not ready and time.monotonic() - started > 25:
                    raise RuntimeError("No captured video frames within 25 seconds")
                time.sleep(0.15)
        finally:
            if process.poll() is None:
                try:
                    process.stdin.write(b"q\n")
                    process.stdin.flush()
                    process.wait(timeout=20)
                except (OSError, subprocess.TimeoutExpired):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    if process.returncode != 0 or not ready:
        raise RuntimeError("Recording failed; inspect ffmpeg.log")
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(folder / "submission.mp4"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    metadata = json.loads(probe.stdout)
    videos = [s for s in metadata.get("streams", []) if s.get("codec_type") == "video"]
    if not videos or float(metadata["format"]["duration"]) <= 0:
        raise RuntimeError("Recorded file has no playable video stream")
    save_json(folder / "capture-finished.json", {"status": "PASS", "probe": metadata})
    return 0


class Recorder:
    def __init__(self, dc, folder):
        self.dc, self.folder = dc, folder
        self.process = None
        self.log = None

    def start(self):
        relative = self.folder.relative_to(self.dc.ROOT).as_posix()
        self.log = (self.folder / "capture-worker.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            self.dc.compose_command(
                "exec",
                "-T",
                "simulator",
                "python3",
                "/workspace/" + relative + "/record_submission.py",
                "--capture",
                "/workspace/" + relative,
            ),
            cwd=self.dc.ROOT,
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        until = time.monotonic() + 35
        while time.monotonic() < until:
            if self.process.poll() is not None:
                raise RuntimeError(
                    "Recorder exited before first frame; inspect capture-worker.log and ffmpeg.log"
                )
            if (self.folder / "capture-ready.json").exists():
                return
            time.sleep(0.2)
        raise RuntimeError(
            "Recorder did not report a captured frame; navigation was not started"
        )

    def finish(self):
        (self.folder / "stop-recording").touch()
        try:
            if self.process:
                try:
                    self.process.wait(timeout=35)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                    raise RuntimeError(
                        "Recorder did not finish; video is not certified complete"
                    )
                if self.process.returncode != 0:
                    raise RuntimeError("Recorder failed; inspect capture-worker.log")
            if not (self.folder / "capture-finished.json").exists():
                raise RuntimeError("Video validation report missing")
        finally:
            if self.log:
                self.log.close()


def export_recording(folder, output_root=None):
    """Use one canonical run directory; export a copy only when requested."""
    folder = folder.resolve()
    if output_root is None:
        return folder
    destination = output_root.resolve() / folder.name
    if destination == folder:
        return folder
    if destination.is_relative_to(folder):
        raise ValueError("Export directory cannot be inside the recording")
    destination.mkdir(parents=True, exist_ok=False)
    for name in (
        "submission.mp4", "manifest.json", "real-ai-selection.json",
        "capture-finished.json", "events.jsonl",
    ):
        if (folder / name).exists():
            shutil.copyfile(folder / name, destination / name)
    if (folder / "audit").exists():
        shutil.copytree(folder / "audit", destination / "audit")
    return destination


def run_host(args):
    repository = args.repository.resolve()
    if repository != Path(__file__).resolve().parents[2]:
        raise ValueError("Run the recorder located inside the requested repository")
    gazebo = repository / "gazebo"
    source = gazebo / "scripts/destination_control.py"
    if not source.is_file():
        raise RuntimeError(f"Missing controller: {source}")
    import destination_control as dc
    from task_results import navigation_succeeded

    args.model = args.model or dc.default_model()
    args.port = args.port if args.port is not None else dc.default_port()
    if not args.run:
        print(
            "PREVIEW: no services, inference, resets, recording or movement were started."
        )
        print(
            "Will reset simulator; wait for sensors; start X11 recording; run real AI and evidence-gated navigation; stop and save MP4/audit."
        )
        print(
            f"Repository: {repository}\nModel: {args.model}\nInstruction: {args.instruction}"
        )
        return 0
    registry = dc.load_registry()
    # Confirm certificates before restarting anything. Real inference still happens on camera.
    installed = dc.local_request(args.port, "/api/tags", timeout=5)
    found = next(
        (
            m
            for m in installed.get("models", [])
            if m.get("name") == args.model
            and not m.get("remote_host")
            and not m.get("remote_model")
        ),
        None,
    )
    if not found or not dc.language_validated(
        registry, {"model": args.model, "model_digest": found.get("digest")}
    ):
        raise RuntimeError(
            "Current real local-AI certificate unavailable. Run project.ps1 SubmissionCheck first."
        )
    if not any(dc.qualified(d) for d in registry["destinations"]):
        raise RuntimeError(
            "No currently qualified destination. Run the submission check first."
        )
    session = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    folder = gazebo / "outputs/recordings" / session
    folder.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(Path(__file__), folder / "record_submission.py")
    manifest = {
        "status": "INCOMPLETE",
        "run_id": session,
        "instruction": args.instruction,
        "model": args.model,
        "recording": "Gazebo X11 desktop with live audit labels; no cuts; no audio",
        "started_unix": time.time(),
        "controller_sha256": dc.digest(source),
        "fingerprint": dc.fingerprint(),
        "audit": None,
    }
    recorder = Recorder(dc, folder)
    audit = None
    with dc.navigation_lock():
        try:
            log = folder / "setup.log"
            dc.prepare_simulator(log)
            # Read-only checks do not install software or change the simulator image.
            dc.docker_run(["exec", "-T", "simulator", "ffmpeg", "-version"], log, 15)
            overlay(
                folder, args.instruction, args.model, "準備完了・これから実AIで推論"
            )
            recorder.start()
            time.sleep(3)

            def display_event(phase, data):
                if phase == "inference_started":
                    overlay(
                        folder, args.instruction, args.model, "実ローカルAIで推論中"
                    )
                elif phase == "selection":
                    save_json(folder / "real-ai-selection.json", data)
                    overlay(
                        folder,
                        args.instruction,
                        args.model,
                        "実AIの応答",
                        f"decision={data['decision']} / destination={data.get('destination_id')}",
                    )
                    time.sleep(3)
                elif phase == "navigation_started":
                    overlay(
                        folder,
                        args.instruction,
                        args.model,
                        "移動中",
                        f"AIが選んだ目標座標: {data['goal']}",
                    )

            audit = dc.run_instruction(
                args.instruction,
                dc.load_registry(),
                folder / "audit",
                execute=True,
                model=args.model,
                port=args.port,
                reset=False,
                on_event=display_event,
            )
            manifest["audit"] = audit
            passed = navigation_succeeded(audit)
            report = audit.get("world_evaluation", {})
            error = report.get("world_goal_error_m")
            details = (
                f"到達誤差: {error * 100:.2f} cm / 衝突記録: {len(report.get('obstacle_collisions', []))}"
                if isinstance(error, (float, int))
                else str(audit.get("reason", "No world evaluation"))
            )
            overlay(
                folder,
                args.instruction,
                args.model,
                "PASS・到着と停止を確認"
                if passed
                else "未達・提出成功動画として扱わない",
                details + " / 最終停止: " + str(audit.get("final_stop", "UNCONFIRMED")),
            )
            time.sleep(5)
            manifest["navigation_passed"] = passed
        except (Exception, KeyboardInterrupt) as error:
            manifest["error"] = str(error) or "Interrupted"
        finally:
            # If an exception occurred outside run_instruction, still confirm a stop.
            if audit is None:
                manifest["emergency_final_stop"] = dc.stop_robot(folder / "stop.log")
            try:
                recorder.finish()
                manifest["video_validated"] = True
            except Exception as error:
                manifest["recording_error"] = str(error)
                manifest["video_validated"] = False
            manifest["finished_unix"] = time.time()
            manifest["status"] = (
                "PASS"
                if manifest.get("navigation_passed") and manifest.get("video_validated")
                else "INCOMPLETE"
            )
            video = folder / "submission.mp4"
            if video.exists():
                manifest["video_sha256"] = hashlib.sha256(
                    video.read_bytes()
                ).hexdigest()
            save_json(folder / "manifest.json", manifest)
    destination = export_recording(folder, args.output_root)
    print(
        f"Status: {manifest['status']}\nRecording and evidence: {destination}\nFull diagnostic logs: {folder}"
    )
    print(
        "Review the video visually: Gazebo camera, legible labels, full path and final stop. Runtime PASS does not certify camera framing."
    )
    return 0 if manifest["status"] == "PASS" else 1


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--repository", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional additional export directory; default keeps one copy in gazebo/outputs/recordings",
    )
    parser.add_argument(
        "--model", help="Defaults to OLLAMA_MODEL in .env or qwen3:1.7b"
    )
    parser.add_argument(
        "--port", type=int, help="Defaults to OLLAMA_PORT in .env or 11434"
    )
    parser.add_argument("--instruction", default="東側の資材受け渡し場所へ行って")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    return capture_worker(args.capture) if args.capture else run_host(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as error:
        print(f"RECORDING INCOMPLETE: {error}", file=sys.stderr)
        raise SystemExit(1)
