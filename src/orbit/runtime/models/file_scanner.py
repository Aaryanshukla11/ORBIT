"""Local Model File Scanner and Metadata Extractor (Milestone M1.9 Step 2).

Safely discovers and extracts metadata from local model weights files (.gguf, .onnx, .safetensors, .bin)
in configured directories without loading weights into RAM or executing side effects.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import struct
from typing import Any, Dict, List, Optional, Set, Tuple

from orbit.runtime.models.capabilities import infer_capabilities
from orbit.runtime.models.models import (
    LocalModelFileDescriptor,
    ModelCapability,
    ModelDescriptor,
    ModelFileFormat,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
)

logger = logging.getLogger(__name__)

# Supported model file extensions
SUPPORTED_EXTENSIONS: Dict[str, ModelFileFormat] = {
    ".gguf": ModelFileFormat.GGUF,
    ".onnx": ModelFileFormat.ONNX,
    ".safetensors": ModelFileFormat.SAFETENSORS,
    ".bin": ModelFileFormat.BIN,
}


def parse_gguf_header_safe(file_path: Path | str, max_header_bytes: int = 65536) -> Dict[str, Any]:
    """Safely inspect the initial header of a GGUF file without loading tensor data."""
    p = Path(file_path)
    try:
        if not p.exists() or p.stat().st_size < 16:
            return {}

        with open(p, "rb") as f:
            header_data = f.read(min(max_header_bytes, p.stat().st_size))

        if len(header_data) < 16:
            return {}

        # Check magic bytes: b"GGUF"
        magic = header_data[:4]
        if magic != b"GGUF":
            return {}

        version = struct.unpack("<I", header_data[4:8])[0]

        # Check if 32-bit or 64-bit integer counts
        tensor_count_32 = struct.unpack("<I", header_data[8:12])[0]
        kv_count_32 = struct.unpack("<I", header_data[12:16])[0]

        if len(header_data) >= 24:
            tensor_count_64 = struct.unpack("<Q", header_data[8:16])[0]
            kv_count_64 = struct.unpack("<Q", header_data[16:24])[0]
            # Standard GGUF v2/v3 uses 64-bit integers. If realistic, prefer 64-bit:
            if tensor_count_64 > 0 and tensor_count_64 < 1000000 and kv_count_64 < 1000000:
                tensor_count = tensor_count_64
                kv_count = kv_count_64
            else:
                tensor_count = tensor_count_32
                kv_count = kv_count_32
        else:
            tensor_count = tensor_count_32
            kv_count = kv_count_32

        architecture: Optional[str] = None
        quantization: Optional[str] = None

        fn_lower = p.stem.lower()
        for fam in ("qwen", "llama", "deepseek", "phi", "mistral", "gemma", "nomic"):
            if fam in fn_lower:
                architecture = fam
                break

        for q in ("q4_k_m", "q4_k_s", "q5_k_m", "q8_0", "q4_0", "q4_1", "f16", "f32"):
            if q in fn_lower:
                quantization = q.upper()
                break

        return {
            "format": "GGUF",
            "gguf_version": version,
            "tensor_count": tensor_count,
            "kv_count": kv_count,
            "architecture": architecture,
            "quantization": quantization,
        }

    except Exception as ex:
        logger.debug("Non-fatal error reading GGUF header for %s: %s", p, ex)
        return {}


class LocalFileModelScanner:
    """Scans configured filesystem directories for local AI model files."""

    def __init__(self, model_directories: Optional[List[Path | str]] = None) -> None:
        self._directories: List[Path] = []
        if model_directories:
            for d in model_directories:
                self.add_directory(d)

    @property
    def configured_directories(self) -> List[Path]:
        return list(self._directories)

    def add_directory(self, directory_path: Path | str) -> None:
        """Register a directory to scan for model files."""
        p = Path(directory_path).resolve()
        if p not in self._directories:
            self._directories.append(p)
            logger.debug("Configured model directory for scanning: %s", p)

    def remove_directory(self, directory_path: Path | str) -> None:
        p = Path(directory_path).resolve()
        if p in self._directories:
            self._directories.remove(p)

    def scan_file(self, file_path: Path) -> Optional[LocalModelFileDescriptor]:
        """Inspect an individual candidate file and return a LocalModelFileDescriptor."""
        try:
            if not file_path.is_file():
                return None

            ext = file_path.suffix.lower()
            file_format = SUPPORTED_EXTENSIONS.get(ext, ModelFileFormat.UNKNOWN)
            if file_format == ModelFileFormat.UNKNOWN:
                return None  # Ignore non-model files safely

            stat = file_path.stat()
            size_bytes = stat.st_size
            last_modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc)

            model_family: Optional[str] = None
            quantization: Optional[str] = None
            is_compatible = True
            incomp_reason: Optional[str] = None
            format_metadata: Dict[str, Any] = {}

            if file_format == ModelFileFormat.GGUF:
                meta = parse_gguf_header_safe(file_path)
                if not meta:
                    is_compatible = False
                    incomp_reason = "Corrupt or invalid GGUF header"
                else:
                    format_metadata = meta
                    model_family = meta.get("architecture")
                    quantization = meta.get("quantization")
            elif file_format == ModelFileFormat.ONNX:
                format_metadata = {"format": "ONNX"}
                if size_bytes < 10:
                    is_compatible = False
                    incomp_reason = "File too small to be valid ONNX model"
            elif file_format == ModelFileFormat.SAFETENSORS:
                format_metadata = {"format": "SAFETENSORS"}
                if size_bytes < 10:
                    is_compatible = False
                    incomp_reason = "File too small to be valid SafeTensors model"
            elif file_format == ModelFileFormat.BIN:
                format_metadata = {"format": "BIN"}

            return LocalModelFileDescriptor(
                path=str(file_path),
                filename=file_path.name,
                file_name=file_path.name,
                format=file_format,
                format_metadata=format_metadata,
                size_bytes=size_bytes,
                last_modified_utc=last_modified,
                model_family=model_family,
                quantization=quantization,
                is_compatible=is_compatible,
                incompatibility_reason=incomp_reason,
            )

        except Exception as ex:
            logger.warning("Failed to scan candidate model file %s: %s", file_path, ex)
            return None

    def scan_directory(self, directory_path: Path, recursive: bool = False) -> List[LocalModelFileDescriptor]:
        """Scan a specific directory for supported model files."""
        if not directory_path.exists() or not directory_path.is_dir():
            logger.debug("Model directory does not exist or is not a directory: %s", directory_path)
            return []

        descriptors: List[LocalModelFileDescriptor] = []
        try:
            iterator = directory_path.rglob("*") if recursive else directory_path.iterdir()
            for entry in iterator:
                if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
                    desc = self.scan_file(entry)
                    if desc:
                        descriptors.append(desc)
        except Exception as ex:
            logger.warning("Error traversing directory %s: %s", directory_path, ex)

        return descriptors

    def scan_all(self, recursive: bool = False) -> List[LocalModelFileDescriptor]:
        """Scan all configured directories and collect model file descriptors."""
        all_files: List[LocalModelFileDescriptor] = []
        for d in self._directories:
            files = self.scan_directory(d, recursive=recursive)
            all_files.extend(files)
        return all_files

    def to_model_descriptors(self, file_descriptors: List[LocalModelFileDescriptor]) -> List[ModelDescriptor]:
        """Convert discovered local model file metadata into standard ModelDescriptors."""
        model_descriptors: List[ModelDescriptor] = []

        for fd in file_descriptors:
            clean_name = fd.filename.replace(" ", "_").lower()
            stable_id = f"local_file:{clean_name}"

            display_name = Path(fd.path).name
            capabilities = infer_capabilities(fd.filename)

            status = ModelStatus.DISCOVERED if fd.is_compatible else ModelStatus.INCOMPATIBLE

            desc = ModelDescriptor(
                model_id=stable_id,
                provider=ModelProviderKind.LOCAL_FILE,
                provider_model_name=fd.filename,
                display_name=display_name,
                source_type=ModelSourceType.LOCAL_FILE,
                source_path=fd.path,
                file_format=fd.format,
                status=status,
                capabilities=capabilities,
                family=fd.model_family,
                quantization_level=fd.quantization,
                size_bytes=fd.size_bytes,
                local_or_remote="local",
                discovered_at_utc=datetime.now(timezone.utc),
                metadata={
                    "is_compatible": fd.is_compatible,
                    "incompatibility_reason": fd.incompatibility_reason,
                    "last_modified_utc": fd.last_modified_utc.isoformat(),
                    "format_metadata": fd.format_metadata,
                },
            )
            model_descriptors.append(desc)

        return model_descriptors
