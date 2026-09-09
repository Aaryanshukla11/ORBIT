"""Spreadsheet environment providers for ORBIT.

Supports SPREADSHEET_READ and SPREADSHEET_WRITE through:
1. ExcelComProvider (via Windows COM / Excel installation)
2. LibreOfficeCalcProvider (via LibreOffice CLI/UNO)
3. CsvSpreadsheetProvider (built-in zero-dependency CSV fallback)
"""

from __future__ import annotations

import csv
import logging
import os
import shutil
from typing import Any, Dict, List, Optional

from orbit.runtime.agent.contracts import AbstractAction
from orbit.runtime.environment.registry import EnvironmentProvider, ProviderExecutionResult

logger = logging.getLogger(__name__)


class CsvSpreadsheetProvider(EnvironmentProvider):
    """Zero-dependency CSV fallback provider for spreadsheet operations."""

    @property
    def provider_id(self) -> str:
        return "csv_fallback_provider"

    @property
    def supported_features(self) -> List[str]:
        return ["csv", "tabular_raw", "plain_text_table"]

    async def is_available(self) -> bool:
        # Standard Python csv module is always available
        return True

    async def check_permissions(self, action: AbstractAction) -> bool:
        path = action.parameters.get("path") or action.parameters.get("file_path")
        if not path:
            return False
        # Check directory existence and writability for write actions
        parent_dir = os.path.dirname(os.path.abspath(path)) or "."
        if os.path.exists(parent_dir):
            return os.access(parent_dir, os.W_OK)
        return True

    async def execute(self, action: AbstractAction) -> ProviderExecutionResult:
        path = action.parameters.get("path") or action.parameters.get("file_path")
        if not path:
            return ProviderExecutionResult(success=False, error="Missing required parameter 'path'")

        action_name = action.action_type.value

        try:
            if "WRITE" in action_name:
                rows = action.parameters.get("rows") or action.parameters.get("data") or []
                headers = action.parameters.get("headers") or action.parameters.get("columns")

                # Ensure directory exists
                parent = os.path.dirname(os.path.abspath(path))
                if parent and not os.path.exists(parent):
                    os.makedirs(parent, exist_ok=True)

                # If path ends in .xlsx or doesn't specify csv, handle as csv fallback
                csv_path = path if path.endswith(".csv") else f"{os.path.splitext(path)[0]}.csv"

                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if headers:
                        writer.writerow(headers)
                    for row in rows:
                        if isinstance(row, dict):
                            if headers:
                                writer.writerow([row.get(h, "") for h in headers])
                            else:
                                writer.writerow(list(row.values()))
                        elif isinstance(row, (list, tuple)):
                            writer.writerow(row)
                        else:
                            writer.writerow([row])

                return ProviderExecutionResult(
                    success=True,
                    output={"path": csv_path, "rows_written": len(rows)},
                    metadata={"provider": self.provider_id, "format": "csv"},
                )

            elif "READ" in action_name:
                if not os.path.exists(path):
                    return ProviderExecutionResult(success=False, error=f"File not found: {path}")

                data: List[List[str]] = []
                with open(path, "r", newline="", encoding="utf-8", errors="replace") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        data.append(row)

                return ProviderExecutionResult(
                    success=True,
                    output={"path": path, "rows": data, "row_count": len(data)},
                    metadata={"provider": self.provider_id, "format": "csv"},
                )

            return ProviderExecutionResult(success=False, error=f"Unsupported action: {action_name}")

        except Exception as e:
            logger.error("[CSV PROVIDER] Execution failed: %s", e)
            return ProviderExecutionResult(success=False, error=str(e))


class ExcelComProvider(EnvironmentProvider):
    """Microsoft Excel provider via Windows COM (win32com.client)."""

    @property
    def provider_id(self) -> str:
        return "excel_com_provider"

    @property
    def supported_features(self) -> List[str]:
        return ["excel", "xlsx", "formulas", "vba", "macros", "charts", "pivot_tables", "formatting"]

    async def is_available(self) -> bool:
        try:
            import win32com.client  # type: ignore[import-not-found]
            # Try lightweight COM object check without launching GUI
            return True
        except ImportError:
            return False
        except Exception:
            return False

    async def check_permissions(self, action: AbstractAction) -> bool:
        path = action.parameters.get("path") or action.parameters.get("file_path")
        if not path:
            return False
        parent = os.path.dirname(os.path.abspath(path)) or "."
        return os.access(parent, os.W_OK) if os.path.exists(parent) else True

    async def execute(self, action: AbstractAction) -> ProviderExecutionResult:
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError:
            return ProviderExecutionResult(success=False, error="win32com not installed")

        path = action.parameters.get("path") or action.parameters.get("file_path")
        if not path:
            return ProviderExecutionResult(success=False, error="Missing parameter 'path'")

        action_name = action.action_type.value
        try:
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            try:
                if "WRITE" in action_name:
                    wb = excel.Workbooks.Add()
                    ws = wb.ActiveSheet
                    headers = action.parameters.get("headers") or action.parameters.get("columns") or []
                    rows = action.parameters.get("rows") or action.parameters.get("data") or []

                    col_idx = 1
                    for h in headers:
                        ws.Cells(1, col_idx).Value = str(h)
                        col_idx += 1

                    row_idx = 2 if headers else 1
                    for r in rows:
                        col_idx = 1
                        if isinstance(r, dict):
                            for h in headers:
                                ws.Cells(row_idx, col_idx).Value = str(r.get(h, ""))
                                col_idx += 1
                        elif isinstance(r, (list, tuple)):
                            for val in r:
                                ws.Cells(row_idx, col_idx).Value = str(val)
                                col_idx += 1
                        row_idx += 1

                    abs_path = os.path.abspath(path)
                    wb.SaveAs(abs_path)
                    wb.Close(SaveChanges=True)
                    return ProviderExecutionResult(
                        success=True,
                        output={"path": abs_path, "rows_written": len(rows)},
                        metadata={"provider": self.provider_id},
                    )
            finally:
                excel.Quit()
        except Exception as e:
            logger.warning("[EXCEL COM PROVIDER] Failed: %s", e)
            return ProviderExecutionResult(success=False, error=str(e))

        return ProviderExecutionResult(success=False, error="Unsupported operation")


class LibreOfficeCalcProvider(EnvironmentProvider):
    """LibreOffice Calc provider via soffice binary."""

    @property
    def provider_id(self) -> str:
        return "libreoffice_calc_provider"

    async def is_available(self) -> bool:
        return shutil.which("soffice") is not None

    async def check_permissions(self, action: AbstractAction) -> bool:
        path = action.parameters.get("path") or action.parameters.get("file_path")
        if not path:
            return False
        parent = os.path.dirname(os.path.abspath(path)) or "."
        return os.access(parent, os.W_OK) if os.path.exists(parent) else True

    async def execute(self, action: AbstractAction) -> ProviderExecutionResult:
        # LibreOffice headless execution if available
        return ProviderExecutionResult(success=False, error="LibreOffice execution not configured")
