"""Unit tests for Local File Model Scanner and GGUF Header Parser (Milestone M1.9 Step 2)."""

import struct
from pathlib import Path
import pytest

from orbit.runtime.models.file_scanner import (
    LocalFileModelScanner,
    parse_gguf_header_safe,
)
from orbit.runtime.models.models import (
    ModelCapability,
    ModelFileFormat,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
)


def _create_synthetic_gguf_file(path: Path, version: int = 3, tensor_count: int = 290, kv_count: int = 18) -> None:
    """Helper to write a binary header with GGUF magic bytes."""
    header = struct.pack("<4sIII", b"GGUF", version, tensor_count, kv_count)
    path.write_bytes(header + b"\x00" * 100)


def test_parse_gguf_header_valid(tmp_path: Path):
    model_path = tmp_path / "qwen2.5-7b-instruct.Q4_K_M.gguf"
    _create_synthetic_gguf_file(model_path, version=3, tensor_count=350, kv_count=24)

    meta = parse_gguf_header_safe(model_path)
    assert meta["format"] == "GGUF"
    assert meta["gguf_version"] == 3
    assert meta["tensor_count"] == 350
    assert meta["kv_count"] == 24


def test_parse_gguf_header_invalid_magic(tmp_path: Path):
    corrupt_path = tmp_path / "corrupt.gguf"
    corrupt_path.write_bytes(b"NOT_GGUF_DATA_HERE_1234567890")

    meta = parse_gguf_header_safe(corrupt_path)
    assert meta == {}


def test_parse_gguf_header_truncated_file(tmp_path: Path):
    short_path = tmp_path / "short.gguf"
    short_path.write_bytes(b"GG")

    meta = parse_gguf_header_safe(short_path)
    assert meta == {}


def test_local_file_scanner_discovers_supported_formats(tmp_path: Path):
    # Setup test directory structure
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    gguf_file = models_dir / "llama-3-8b.Q4_K_M.gguf"
    _create_synthetic_gguf_file(gguf_file, 3, 290, 18)

    onnx_file = models_dir / "vision-encoder.onnx"
    onnx_file.write_bytes(b"ONNX_BINARY_MOCK" * 10)

    safetensors_file = models_dir / "model.safetensors"
    safetensors_file.write_bytes(b"SAFETENSORS_MOCK" * 10)

    bin_file = models_dir / "pytorch_model.bin"
    bin_file.write_bytes(b"BIN_WEIGHTS_MOCK" * 10)

    # Ignored files
    (models_dir / "readme.md").write_text("Documentation")
    (models_dir / "config.json").write_text("{}")
    (models_dir / "script.py").write_text("print('hello')")

    scanner = LocalFileModelScanner(model_directories=[models_dir])
    descriptors = scanner.scan_all()

    assert len(descriptors) == 4
    formats = {d.format for d in descriptors}
    assert formats == {
        ModelFileFormat.GGUF,
        ModelFileFormat.ONNX,
        ModelFileFormat.SAFETENSORS,
        ModelFileFormat.BIN,
    }

    # Verify GGUF metadata populated
    gguf_desc = next(d for d in descriptors if d.format == ModelFileFormat.GGUF)
    assert gguf_desc.format_metadata.get("gguf_version") == 3
    assert gguf_desc.format_metadata.get("tensor_count") == 290
    assert gguf_desc.file_name == "llama-3-8b.Q4_K_M.gguf"


def test_scanner_unsupported_files_safely_ignored(tmp_path: Path):
    scanner = LocalFileModelScanner(model_directories=[tmp_path])
    (tmp_path / "text.txt").write_text("sample")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "archive.zip").write_bytes(b"PK")

    descriptors = scanner.scan_all()
    assert len(descriptors) == 0


def test_scanner_handles_nonexistent_directory():
    scanner = LocalFileModelScanner(model_directories=[Path("Z:/NonExistent/Directory/Models")])
    descriptors = scanner.scan_all()
    assert descriptors == []


def test_scanner_to_model_descriptors_conversion(tmp_path: Path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    gguf_file = models_dir / "qwen2.5-coder-7b-instruct.gguf"
    _create_synthetic_gguf_file(gguf_file, 3, 350, 24)

    scanner = LocalFileModelScanner(model_directories=[models_dir])
    files = scanner.scan_all()
    models = scanner.to_model_descriptors(files)

    assert len(models) == 1
    m = models[0]
    assert m.model_id == "local_file:qwen2.5-coder-7b-instruct.gguf"
    assert m.provider == ModelProviderKind.LOCAL_FILE
    assert m.source_type == ModelSourceType.LOCAL_FILE
    assert m.status == ModelStatus.DISCOVERED
    assert ModelCapability.CODE_GENERATION in m.capabilities
    assert m.size_bytes > 0
