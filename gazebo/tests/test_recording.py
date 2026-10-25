"""Recorder/event regression tests: Docker, model and video encoder are mocked."""

from tests import CACHE_ROOT
from contextlib import nullcontext
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import destination_control as dc
import record_submission as recording
from task_results import navigation_succeeded
from tests.test_destination_control import valid_report


class RecordingTests(unittest.TestCase):
    def setUp(self):
        cache = CACHE_ROOT / 'test-runs'
        cache.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=cache)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.registry = {"destinations": [{"id": "east_station", "goal": [3.0, 1.0]}]}
        self.selection = {
            "decision": "select",
            "destination_id": "east_station",
            "model": "qwen3:1.7b",
            "model_digest": "test",
        }

    def run_instruction(self, **kwargs):
        return dc.run_instruction(
            "東側へ移動して",
            self.registry,
            self.folder / "audit",
            execute=True,
            **kwargs,
        )

    def test_progress_observes_real_selection_and_uses_prepared_evaluator(self):
        events = []
        with (
            patch.object(dc, "select_destination", return_value=self.selection),
            patch.object(dc, "qualified", return_value=True),
            patch.object(dc, "language_validated", return_value=True),
            patch.object(dc, "stop_robot", return_value="CONFIRMED_STATIONARY") as stop,
            patch.object(dc, "evaluate", return_value=valid_report()) as evaluate,
        ):
            audit = self.run_instruction(
                reset=False, on_event=lambda phase, data: events.append((phase, data))
            )
        self.assertTrue(navigation_succeeded(audit))
        evaluate.assert_called_once_with(
            [3.0, 1.0], self.folder / "audit/world-evaluation", reset=False
        )
        self.assertEqual(
            [x[0] for x in events],
            ["inference_started", "selection", "navigation_started"],
        )
        self.assertEqual(events[1][1], self.selection)
        self.assertEqual(stop.call_count, 2)

    def test_observer_failure_stops_before_navigation(self):
        def fail(phase, data):
            if phase == "selection":
                raise OSError("overlay unavailable")

        with (
            patch.object(dc, "select_destination", return_value=self.selection),
            patch.object(dc, "stop_robot", return_value="CONFIRMED_STATIONARY") as stop,
            patch.object(dc, "evaluate") as evaluate,
        ):
            audit = self.run_instruction(on_event=fail)
        self.assertFalse(navigation_succeeded(audit))
        self.assertEqual(stop.call_count, 2)
        evaluate.assert_not_called()
        self.assertIn("overlay unavailable", audit["reason"])

    def test_reset_false_does_not_restart_simulator(self):
        output = self.folder / "evaluation"

        def docker(args, log, timeout):
            report = valid_report()
            (output / "evaluation.json").write_text(
                json.dumps(report), encoding="utf-8"
            )

        with (
            patch.object(dc, "ROOT", self.folder),
            patch.object(dc, "prepare_simulator") as prepare,
            patch.object(dc, "docker_run", side_effect=docker),
        ):
            result = dc.evaluate([3.0, 1.0], output, reset=False)
        self.assertEqual(result["status"], "PASS")
        prepare.assert_not_called()

    def test_text_is_not_interpreted_as_filter_or_shell(self):
        text = "$(touch bad) ' : %{pts} 日本語"
        recording.overlay(self.folder, text, "qwen3:1.7b", "推論中")
        self.assertIn(text, (self.folder / "overlay.txt").read_text(encoding="utf-8"))
        cmd = recording.capture_command(self.folder, 1280, 800, "/font.ttc")
        self.assertNotIn(text, " ".join(cmd))
        self.assertIn("expansion=none", cmd[cmd.index("-vf") + 1])
        self.assertNotIn("-nostdin", cmd)
        self.assertIn("-n", cmd)

    def test_unconfirmed_stop_cannot_pass(self):
        audit = {
            "status": "PASS",
            "movement_started": True,
            "qualified": True,
            "language_validated": True,
            "destination": "east_station",
            "selection": self.selection,
            "goal": [3.0, 1.0],
            "world_evaluation": valid_report(),
            "final_stop": "UNCONFIRMED",
        }
        self.assertFalse(navigation_succeeded(audit))

    def test_default_storage_has_no_export_copy(self):
        folder = self.folder / "recordings/run-one"
        folder.mkdir(parents=True)
        (folder / "submission.mp4").write_bytes(b"test video bytes")
        before = sorted(self.folder.rglob("*"))
        self.assertEqual(recording.export_recording(folder), folder.resolve())
        self.assertEqual(sorted(self.folder.rglob("*")), before)
        self.assertEqual(recording.export_recording(folder, folder.parent), folder.resolve())

    def test_explicit_export_preserves_video_and_audit(self):
        folder = self.folder / "recordings/run-one"
        (folder / "audit").mkdir(parents=True)
        (folder / "submission.mp4").write_bytes(b"test video bytes")
        (folder / "audit/selection.json").write_text('{"status":"PASS"}', encoding="utf-8")
        destination = recording.export_recording(folder, self.folder / "explicit-export")
        self.assertEqual((destination / "submission.mp4").read_bytes(), b"test video bytes")
        self.assertEqual((destination / "audit/selection.json").read_bytes(), (folder / "audit/selection.json").read_bytes())

    def test_export_cannot_nest_inside_the_original_run(self):
        folder = self.folder / "recordings/run-one"
        folder.mkdir(parents=True)
        with self.assertRaises(ValueError):
            recording.export_recording(folder, folder / "nested")

    def test_capture_readiness_failure_cleans_up_and_never_calls_ai(self):
        import argparse

        args = argparse.Namespace(
            repository=dc.ROOT.parent,
            model="qwen3:1.7b",
            port=11434,
            run=True,
            instruction="東へ移動して",
            output_root=self.folder / "export",
        )
        old_root = dc.ROOT
        fake_root = self.folder / "gazebo"
        fake_root.mkdir()
        # run_host derives the source from the real repository; only output is redirected.
        with (
            patch.object(
                dc,
                "local_request",
                return_value={"models": [{"name": args.model, "digest": "test"}]},
            ),
            patch.object(dc, "language_validated", return_value=True),
            patch.object(dc, "load_registry", return_value=self.registry),
            patch.object(dc, "qualified", return_value=True),
            patch.object(dc, "prepare_simulator"),
            patch.object(dc, "docker_run"),
            patch.object(dc, "fingerprint", return_value={}),
            patch.object(dc, "navigation_lock", return_value=nullcontext()),
            patch.object(dc, "ROOT", fake_root),
            patch.object(dc, "stop_robot", return_value="CONFIRMED_STATIONARY") as stop,
            patch.object(dc, "run_instruction") as run,
            patch.object(
                recording.Recorder, "start", side_effect=RuntimeError("no frames")
            ),
            patch.object(
                recording.Recorder,
                "finish",
                side_effect=RuntimeError("recording incomplete"),
            ),
            patch("sys.stdout", new=io.StringIO()),
        ):
            result = recording.run_host(args)
        self.assertEqual(result, 1)
        run.assert_not_called()
        stop.assert_called_once()
        manifest = next((self.folder / "export").glob("*/manifest.json"))
        self.assertEqual(
            json.loads(manifest.read_text(encoding="utf-8"))["status"], "INCOMPLETE"
        )
        self.assertEqual(dc.ROOT, old_root)


if __name__ == "__main__":
    unittest.main()
