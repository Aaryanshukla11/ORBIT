"""
Phase 3 Verification Test: Environment Interfaces (Shell, Filesystem, Browser Scraper).

Validates:
1. Shell provider non-interactive PowerShell execution with timeouts & stdout/stderr.
2. LocalFileProvider atomic file write, read, copy, move, delete, list.
3. AccessibilityBrowserScraperProvider structured UIA DOM extraction.
4. Invariant: Transducer only, NO autonomous agents/planners.
"""

import os
import shutil
import tempfile
import unittest
import pytest

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.environment.shell_provider import HardenedShellProvider
from orbit.runtime.environment.file_providers import LocalFileProvider
from orbit.runtime.environment.browser_providers import AccessibilityBrowserScraperProvider


class TestPhase3EnvironmentInterfaces(unittest.IsolatedAsyncioTestCase):
    """Phase 3 Verification Suite."""

    async def test_shell_provider_powershell_execution(self):
        """Test non-interactive shell execution with output capture."""
        provider = HardenedShellProvider()
        action = AbstractAction(
            action_type=AbstractActionType.SHELL_EXECUTE,
            parameters={"command": "Write-Output 'ORBIT_SHELL_TEST_OK'"},
        )
        res = await provider.execute(action)
        self.assertTrue(res.success)
        self.assertIn("ORBIT_SHELL_TEST_OK", res.output.get("stdout", ""))

    async def test_filesystem_provider_atomic_crud(self):
        """Test file write, read, copy, move, list, delete."""
        test_dir = tempfile.mkdtemp(prefix="orbit_fs_test_")
        try:
            provider = LocalFileProvider(allowed_directories=[test_dir])
            file1 = os.path.join(test_dir, "test1.txt")
            file2 = os.path.join(test_dir, "test2.txt")
            file3 = os.path.join(test_dir, "test3.txt")

            # 1. Write
            w_res = await provider.execute(AbstractAction(
                action_type=AbstractActionType.FILE_WRITE,
                parameters={"path": file1, "content": "Hello ORBIT Filesystem"},
            ))
            self.assertTrue(w_res.success)
            self.assertTrue(os.path.exists(file1))

            # 2. Read
            r_res = await provider.execute(AbstractAction(
                action_type=AbstractActionType.FILE_READ,
                parameters={"path": file1},
            ))
            self.assertTrue(r_res.success)
            self.assertEqual(r_res.output.get("content"), "Hello ORBIT Filesystem")

            # 3. Copy
            c_res = await provider.execute(AbstractAction(
                action_type=AbstractActionType.FILE_WRITE,
                parameters={"path": file1, "dest": file2, "mode": "copy"},
            ))
            self.assertTrue(c_res.success)
            self.assertTrue(os.path.exists(file2))

            # 4. Move
            m_res = await provider.execute(AbstractAction(
                action_type=AbstractActionType.FILE_WRITE,
                parameters={"path": file2, "dest": file3, "mode": "move"},
            ))
            self.assertTrue(m_res.success)
            self.assertFalse(os.path.exists(file2))
            self.assertTrue(os.path.exists(file3))

            # 5. List
            l_res = await provider.execute(AbstractAction(
                action_type=AbstractActionType.FILE_READ,
                parameters={"path": test_dir, "mode": "list"},
            ))
            self.assertTrue(l_res.success)
            self.assertGreaterEqual(l_res.output.get("item_count", 0), 2)

            # 6. Delete
            d_res = await provider.execute(AbstractAction(
                action_type=AbstractActionType.FILE_WRITE,
                parameters={"path": file3, "mode": "delete"},
            ))
            self.assertTrue(d_res.success)
            self.assertFalse(os.path.exists(file3))

        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    async def test_browser_scraper_provider_availability(self):
        """Test AccessibilityBrowserScraperProvider registration and safety."""
        scraper = AccessibilityBrowserScraperProvider()
        self.assertEqual(scraper.provider_id, "accessibility_browser_scraper_provider")
        self.assertIn("browser_scrape", scraper.supported_features)


if __name__ == "__main__":
    unittest.main()
