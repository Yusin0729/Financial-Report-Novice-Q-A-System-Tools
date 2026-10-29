"""驗證錯誤 Python 的入口切換；不載入或執行模型。"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from config.settings import SETTINGS


class PythonEntryTests(unittest.TestCase):
    def test_project_python_311_runs_without_restart(self):
        with patch("main.subprocess.run") as child:
            main.ensure_project_python()
        child.assert_not_called()

    def test_global_python_314_redirects_and_preserves_arguments_and_exit_code(self):
        with patch.object(sys, "prefix", str(Path(sys.prefix).parent)), patch.object(
                sys, "version_info", (3, 14)), patch.object(
                sys, "argv", ["Code/main.py", "--check-env"]), patch(
                "main.subprocess.run", return_value=SimpleNamespace(returncode=7)) as child:
            with self.assertRaises(SystemExit) as error:
                main.ensure_project_python()
        self.assertEqual(error.exception.code, 7)
        command = child.call_args.args[0]
        self.assertEqual(Path(command[0]).resolve(), Path(sys.executable).resolve())
        self.assertEqual(command[-1], "--check-env")

    def test_wrong_project_python_version_stops_without_restart_loop(self):
        with patch.object(sys, "version_info", (3, 14)), patch("main.subprocess.run") as child:
            with self.assertRaisesRegex(SystemExit, "Python 3.11"):
                main.ensure_project_python()
        child.assert_not_called()


class OcrSwitchTests(unittest.TestCase):
    def test_pipeline_switch_and_manifest_agree(self):
        from functions.ingestion.pdf_to_markdown import create_converter
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                settings = replace(SETTINGS, ocr_enabled=enabled)
                _, options = create_converter(settings)
                self.assertEqual(options["do_ocr"], enabled)
                from docling.models.factories import get_ocr_factory
                from functions.integrations.docling_mineru_ocr import MineruOcrOptions, MineruOcrModel
                factory=get_ocr_factory(allow_external_plugins=False)
                self.assertIs(factory.classes[MineruOcrOptions],MineruOcrModel)
                self.assertEqual(options["ocr_options"]["lang"], ["ch_lite"])
                self.assertEqual(options["ocr_options"]["mode"], "pdf_aware_layout_regions")
                self.assertFalse(options["ocr_options"]["force_full_page_ocr"])
                self.assertEqual(settings.pdf_manifest()["ocr_enabled"], enabled)

    def test_disabled_ocr_does_not_import_easyocr_or_construct_reader(self):
        import builtins
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from functions.integrations.docling_mineru_ocr import MineruOcrOptions, MineruOcrModel
        from dataclasses import asdict
        original_import = builtins.__import__

        def forbid_easyocr(name, *args, **kwargs):
            if name == "easyocr" or 'mineru_paddle' in name or name.startswith("mineru."):
                raise AssertionError("OCR 關閉時不得匯入辨識引擎")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=forbid_easyocr):
            model = MineruOcrModel(enabled=False, artifacts_path=None,
                                 options=MineruOcrOptions(cache_dir='unused', parameters=asdict(SETTINGS.ocr)),
                                 accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU))
        self.assertFalse(model.enabled)
        self.assertFalse(hasattr(model, "reader"))

    def test_menu_toggle_applies_to_selected_batch(self):
        source = SETTINGS.source_dir / "example.pdf"
        with patch.object(sys, "argv", ["Code/main.py"]), patch(
                "builtins.input", side_effect=["2", "1", "0"]), patch(
                "main.choose_pdf", return_value=[source]), patch(
                "functions.experiments.export_output.create_markdown_batch", return_value=Path('unused_batch')), patch(
                "main.run_markdown", return_value={"status": "converted_needs_review"}) as run:
            self.assertEqual(main.main(), 0)
        self.assertTrue(run.call_args.args[1].ocr_enabled)


if __name__ == "__main__":
    unittest.main()
