"""Focused Unit Tests for ORBIT UIA Tree & Cache Subsystem (Objective P1-A).

Validates:
1. CacheRequestFactory creation.
2. Cache request property configuration (only supported/required perception properties).
3. CachedControlHelper.build_cached_control construction and fallback.
4. CachedControlHelper.get_cached_children retrieval and fallback to GetChildren.
5. Cached tree traversal with pre-cached properties.
6. Depth limiting in tree traversal.
7. Duplicate element prevention (deduplication).
8. Dead HWND handling in TreeService.
9. Destroyed/stale element handling (UIADeadElementError skip).
10. Unsupported cache fallback.
11. Focused element extraction.
12. Window/root resolution.
13. Existing CurrentStateObserver integration.
14. Existing DesktopPerceptionEngine / DesktopObserver integration.
15. Single authoritative production observation pipeline (no duplicates).
16. Canonical UIElementObservation contract preservation.
17. Sensory-only invariant (no physical actuation or planner imports in tree modules).
"""

from __future__ import annotations

import ast
import inspect
import sys
from typing import Optional
import unittest
from unittest.mock import MagicMock, patch

from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import DesktopObservation, UIElementObservation
from orbit.adapters.uia.core import Rect
from orbit.adapters.uia.controls import Control
from orbit.adapters.uia.enums import ControlType, PatternId, PropertyId, TreeScope
from orbit.adapters.uia.exceptions import (
    UIADeadElementError,
    UIANotEnabledError,
    UIANotSupportedError,
    UIAException,
)
from orbit.adapters.uia.tree import (
    CacheRequestFactory,
    CachedControlHelper,
    TreeService,
    create_tree_traversal_cache,
    traverse_tree,
)
from orbit.adapters.uia.tree.traversal import (
    INTERACTIVE_CONTROL_TYPES,
    extract_observation_from_control,
)
from orbit.adapters.uia.tree_extractor import UIAElementTreeExtractor
from orbit.runtime.perception.uia import UIAElementObserver
from orbit.runtime.perception.observer import DesktopObserver
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.cognitive.observer import CurrentStateObserver


class FakeElement:
    """Mock COM element simulating IUIAutomationElement."""

    def __init__(
        self,
        name: str = "TestButton",
        control_type: int = ControlType.ButtonControl,
        automation_id: str = "btn_1",
        class_name: str = "Button",
        rect: tuple = (10, 20, 110, 60),  # left, top, right, bottom
        is_enabled: bool = True,
        is_offscreen: bool = False,
        has_focus: bool = False,
    ):
        self.CurrentName = name
        self.CurrentControlType = control_type
        self.CurrentAutomationId = automation_id
        self.CurrentClassName = class_name
        self.CurrentBoundingRectangle = Rect(*rect)
        self.CurrentIsEnabled = is_enabled
        self.CurrentIsOffscreen = is_offscreen
        self.CurrentHasKeyboardFocus = has_focus
        self.CurrentNativeWindowHandle = 1001

        # Cached variants
        self.CachedName = name
        self.CachedControlType = control_type
        self.CachedAutomationId = automation_id
        self.CachedClassName = class_name
        self.CachedBoundingRectangle = Rect(*rect)
        self.CachedIsEnabled = is_enabled
        self.CachedIsOffscreen = is_offscreen
        self.CachedHasKeyboardFocus = has_focus
        self.CachedNativeWindowHandle = 1001


class FakeControl:
    """Mock Control wrapper implementing required properties for testing."""

    def __init__(
        self,
        name: str = "Button_OK",
        control_type: int = ControlType.ButtonControl,
        control_type_name: str = "ButtonControl",
        automation_id: str = "btn_ok",
        class_name: str = "Button",
        rect: tuple = (10, 20, 110, 60),
        is_enabled: bool = True,
        is_offscreen: bool = False,
        has_focus: bool = False,
        children: Optional[list] = None,
        is_cached: bool = False,
        runtime_id: Optional[list] = None,
        native_window_handle: int = 1001,
    ):
        self._is_cached = is_cached
        self._runtime_id = runtime_id
        self._name = name
        self.ControlType = control_type
        self.ControlTypeName = control_type_name
        self.AutomationId = automation_id
        self.ClassName = class_name
        self.BoundingRectangle = Rect(*rect) if rect else None
        self.IsEnabled = is_enabled
        self.IsOffscreen = is_offscreen
        self.HasKeyboardFocus = has_focus
        self.NativeWindowHandle = native_window_handle

        # Cached mirror properties
        self._cached_name = name
        self.CachedControlType = control_type
        self.CachedControlTypeName = control_type_name
        self.CachedAutomationId = automation_id
        self.CachedClassName = class_name
        self.CachedBoundingRectangle = Rect(*rect) if rect else None
        self.CachedIsEnabled = is_enabled
        self.CachedIsOffscreen = is_offscreen
        self.CachedHasKeyboardFocus = has_focus
        self.CachedNativeWindowHandle = native_window_handle

        self._children = children or []
        self.Element = MagicMock()

    @property
    def Name(self) -> str:
        return self._name

    @Name.setter
    def Name(self, value: str) -> None:
        self._name = value

    @property
    def CachedName(self) -> str:
        return self._cached_name

    @CachedName.setter
    def CachedName(self, value: str) -> None:
        self._cached_name = value

    def GetRuntimeId(self):
        return self._runtime_id

    def GetChildren(self):
        return list(self._children)

    def BuildUpdatedCache(self, cache_request):
        cached = FakeControl(
            name=self.Name,
            control_type=self.ControlType,
            control_type_name=self.ControlTypeName,
            automation_id=self.AutomationId,
            class_name=self.ClassName,
            rect=(
                self.BoundingRectangle.left,
                self.BoundingRectangle.top,
                self.BoundingRectangle.right,
                self.BoundingRectangle.bottom,
            ) if self.BoundingRectangle else (0, 0, 0, 0),
            is_enabled=self.IsEnabled,
            is_offscreen=self.IsOffscreen,
            has_focus=self.HasKeyboardFocus,
            children=self._children,
            is_cached=True,
            runtime_id=self._runtime_id,
        )
        return cached


class DyingControl(FakeControl):
    """Mock Control that raises UIADeadElementError when accessed."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def Name(self) -> str:
        raise UIADeadElementError(0x800401FD)

    @property
    def CachedName(self) -> str:
        raise UIADeadElementError(0x800401FD)


class TestUIATreeAndCacheSubsystem(unittest.TestCase):
    """Automated unit assertions for UIA Tree & Cache subsystem."""

    # 1. CacheRequestFactory creation
    def test_01_cache_request_factory_creation(self):
        """Verify CacheRequestFactory successfully creates or handles CacheRequest."""
        with patch("orbit.adapters.uia.tree.cache_utils.CacheRequest") as mock_cache_cls:
            mock_inst = MagicMock()
            mock_cache_cls.return_value = mock_inst

            cache = CacheRequestFactory.create_tree_traversal_cache()
            self.assertIsNotNone(cache)
            self.assertEqual(mock_inst.TreeScope, TreeScope.TreeScope_Element | TreeScope.TreeScope_Children)
            self.assertTrue(mock_inst.AddProperty.called)
            self.assertTrue(mock_inst.AddPattern.called)

    # 2. Cache request contains only supported/required properties
    def test_02_cache_request_properties_configured(self):
        """Verify that core perception properties are registered in cache request."""
        with patch("orbit.adapters.uia.tree.cache_utils.CacheRequest") as mock_cache_cls:
            mock_inst = MagicMock()
            mock_cache_cls.return_value = mock_inst

            CacheRequestFactory.create_tree_traversal_cache()
            registered_props = [call_args[0][0] for call_args in mock_inst.AddProperty.call_args_list]

            self.assertIn(PropertyId.BoundingRectangleProperty, registered_props)
            self.assertIn(PropertyId.NameProperty, registered_props)
            self.assertIn(PropertyId.ControlTypeProperty, registered_props)
            self.assertIn(PropertyId.AutomationIdProperty, registered_props)
            self.assertIn(PropertyId.IsEnabledProperty, registered_props)

    # 3. Cached control construction
    def test_03_cached_control_construction(self):
        """Verify CachedControlHelper.build_cached_control marks control as cached."""
        ctrl = FakeControl(name="SubmitButton")
        self.assertFalse(getattr(ctrl, "_is_cached", False))

        mock_cache_req = MagicMock()
        cached_ctrl = CachedControlHelper.build_cached_control(ctrl, cache_request=mock_cache_req)

        self.assertTrue(getattr(cached_ctrl, "_is_cached", False))
        self.assertEqual(cached_ctrl.Name, "SubmitButton")

    # 4. Cached child retrieval
    def test_04_cached_child_retrieval(self):
        """Verify get_cached_children extracts children with _is_cached=True."""
        parent = FakeControl(name="ParentPanel")
        mock_child_elem = MagicMock()

        mock_elem_array = MagicMock()
        mock_elem_array.Length = 1
        mock_elem_array.GetElement.return_value = mock_child_elem

        mock_updated = MagicMock()
        mock_updated.GetCachedChildren.return_value = mock_elem_array
        parent.Element.BuildUpdatedCache.return_value = mock_updated

        mock_cache_req = MagicMock()
        mock_cache_req.Clone.return_value = MagicMock()

        child_ctrl = FakeControl(name="ChildButton")
        with patch("orbit.adapters.uia.tree.cache_utils.Control.CreateControlFromElement", return_value=child_ctrl):
            children = CachedControlHelper.get_cached_children(parent, cache_request=mock_cache_req)

        self.assertEqual(len(children), 1)
        self.assertTrue(getattr(children[0], "_is_cached", False))

    # 5. Cached tree traversal
    def test_05_cached_tree_traversal(self):
        """Verify traverse_tree collects elements from cached hierarchy."""
        child1 = FakeControl(name="SaveButton", rect=(10, 10, 60, 40), is_cached=True)
        child2 = FakeControl(name="CancelButton", rect=(70, 10, 120, 40), is_cached=True)
        root = FakeControl(name="MainDialog", children=[child1, child2])

        with patch("orbit.adapters.uia.tree.traversal.CachedControlHelper.get_cached_children", side_effect=[[child1, child2], [], []]):
            results = traverse_tree(root, max_depth=3, max_elements=10)

        self.assertEqual(len(results), 2)
        names = [r.name for r in results]
        self.assertIn("SaveButton", names)
        self.assertIn("CancelButton", names)

    # 6. Depth limiting
    def test_06_tree_traversal_depth_limiting(self):
        """Verify traverse_tree strictly obeys max_depth."""
        level3 = FakeControl(name="DeepNode", rect=(10, 10, 50, 50))
        level2 = FakeControl(name="MidNode", rect=(10, 10, 60, 60), children=[level3])
        level1 = FakeControl(name="TopNode", rect=(10, 10, 70, 70), children=[level2])
        root = FakeControl(name="RootNode", children=[level1])

        def fake_get_children(node, cache_req=None):
            return node.GetChildren()

        with patch("orbit.adapters.uia.tree.traversal.CachedControlHelper.get_cached_children", side_effect=fake_get_children):
            # max_depth=1 should only visit level1 (depth 1)
            results = traverse_tree(root, max_depth=1, max_elements=10)

        names = [r.name for r in results]
        self.assertIn("TopNode", names)
        self.assertNotIn("MidNode", names)
        self.assertNotIn("DeepNode", names)

    # 7. Duplicate element prevention
    def test_07_duplicate_element_deduplication(self):
        """Verify duplicate observations with identical signature are deduplicated."""
        dup1 = FakeControl(name="SameButton", automation_id="btn_1", rect=(10, 10, 50, 50))
        dup2 = FakeControl(name="SameButton", automation_id="btn_1", rect=(10, 10, 50, 50))
        root = FakeControl(name="Root", children=[dup1, dup2])

        with patch("orbit.adapters.uia.tree.traversal.CachedControlHelper.get_cached_children", side_effect=[[dup1, dup2], [], []]):
            results = traverse_tree(root, max_depth=2, max_elements=10)

        self.assertEqual(len(results), 1)

    def test_07b_distinct_runtime_ids_preserve_same_name_and_bounds(self):
        """Verify controls with same name, type, and bounds but distinct UIA RuntimeIds are NOT merged."""
        ctrl1 = FakeControl(name="Item", automation_id="", rect=(10, 10, 50, 50), runtime_id=[42, 101])
        ctrl2 = FakeControl(name="Item", automation_id="", rect=(10, 10, 50, 50), runtime_id=[42, 102])
        root = FakeControl(name="Root", children=[ctrl1, ctrl2])

        with patch("orbit.adapters.uia.tree.traversal.CachedControlHelper.get_cached_children", side_effect=[[ctrl1, ctrl2], [], []]):
            results = traverse_tree(root, max_depth=2, max_elements=10)

        self.assertEqual(len(results), 2)

    def test_07c_distinct_locations_preserve_same_name_and_type(self):
        """Verify controls with identical name and type at different locations are preserved."""
        btn_top = FakeControl(name="Close", automation_id="", rect=(10, 10, 30, 30))
        btn_bot = FakeControl(name="Close", automation_id="", rect=(10, 100, 30, 120))
        root = FakeControl(name="Dialog", children=[btn_top, btn_bot])

        with patch("orbit.adapters.uia.tree.traversal.CachedControlHelper.get_cached_children", side_effect=[[btn_top, btn_bot], [], []]):
            results = traverse_tree(root, max_depth=2, max_elements=10)

        self.assertEqual(len(results), 2)

    def test_07d_repeated_controls_in_separate_containers(self):
        """Verify identical controls in different container nodes are preserved."""
        card1_btn = FakeControl(name="Select", automation_id="", rect=(20, 20, 80, 50))
        card2_btn = FakeControl(name="Select", automation_id="", rect=(20, 120, 80, 150))
        card1 = FakeControl(name="Card1", control_type=ControlType.GroupControl, rect=(10, 10, 100, 100), children=[card1_btn])
        card2 = FakeControl(name="Card2", control_type=ControlType.GroupControl, rect=(10, 110, 100, 200), children=[card2_btn])
        root = FakeControl(name="Root", children=[card1, card2])

        def fake_children(node, cache_req=None):
            return node.GetChildren()

        with patch("orbit.adapters.uia.tree.traversal.CachedControlHelper.get_cached_children", side_effect=fake_children):
            results = traverse_tree(root, max_depth=3, max_elements=10)

        select_buttons = [r for r in results if r.name == "Select"]
        self.assertEqual(len(select_buttons), 2)

    # 8. Dead HWND handling
    def test_08_dead_hwnd_handling(self):
        """Verify TreeService recovers gracefully from invalid or dead HWND without raising."""
        service = TreeService()
        with patch.object(service, "_is_win32", True):
            with patch("orbit.adapters.uia.tree.service.ControlFromHandle", side_effect=UIADeadElementError(0x800401FD)):
                with patch("orbit.adapters.uia.tree.service.GetRootControl", return_value=None):
                    focused, elements = service.observe_window_elements(target_hwnd=99999)
                    self.assertIsNone(focused)
                    self.assertEqual(elements, [])

    # 9. Destroyed/stale element handling
    def test_09_stale_element_handling_during_traversal(self):
        """Verify destroyed elements during traversal are skipped cleanly."""
        dying_ctrl = DyingControl(name="DyingElement")
        healthy_ctrl = FakeControl(name="HealthyElement", rect=(10, 10, 50, 50))
        root = FakeControl(name="Root", children=[dying_ctrl, healthy_ctrl])

        with patch("orbit.adapters.uia.tree.traversal.CachedControlHelper.get_cached_children", side_effect=[[dying_ctrl, healthy_ctrl], [], []]):
            results = traverse_tree(root, max_depth=2, max_elements=10)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "HealthyElement")

    # 10. Unsupported cache fallback
    def test_10_unsupported_cache_fallback(self):
        """Verify fallback to live GetChildren when cache request creation or Clone fails."""
        child = FakeControl(name="FallbackChild", rect=(10, 10, 50, 50))
        parent = FakeControl(name="Parent", children=[child])

        # Force CacheRequest creation to fail
        with patch("orbit.adapters.uia.tree.cache_utils.CacheRequestFactory.create_tree_traversal_cache", return_value=None):
            children = CachedControlHelper.get_cached_children(parent, cache_request=None)

        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].Name, "FallbackChild")

    # 11. Focused element extraction
    def test_11_focused_element_extraction(self):
        """Verify TreeService extracts focused control and tags is_focused=True."""
        focused_ctrl = FakeControl(name="SearchBox", control_type=ControlType.EditControl, rect=(10, 10, 100, 30), has_focus=True, native_window_handle=123)
        service = TreeService()

        with patch("orbit.adapters.uia.tree.service.GetFocusedControl", return_value=focused_ctrl):
            focused_obs = service.get_focused_element(parent_context="TestApp", target_hwnd=123)

        self.assertIsNotNone(focused_obs)
        self.assertEqual(focused_obs.name, "SearchBox")
        self.assertTrue(focused_obs.has_keyboard_focus)
        self.assertEqual(focused_obs.parent_context, "TestApp")
        self.assertEqual(focused_obs.hwnd, 123)

    # 12. Window/root resolution
    def test_12_window_root_resolution(self):
        """Verify resolve_root_control uses HWND if valid, desktop root for None, and fails closed for dead HWND."""
        service = TreeService()
        win_ctrl = FakeControl(name="Notepad Window")
        root_ctrl = FakeControl(name="Desktop")

        with patch("orbit.adapters.uia.tree.service.ControlFromHandle", return_value=win_ctrl):
            ctrl, title = service.resolve_root_control(target_hwnd=1234)
            self.assertIsNotNone(ctrl)
            assert ctrl is not None
            self.assertEqual(ctrl.Name, "Notepad Window")
            self.assertEqual(title, "Notepad Window")

        with patch("orbit.adapters.uia.tree.service.GetRootControl", return_value=root_ctrl):
            ctrl, title = service.resolve_root_control(target_hwnd=None)
            self.assertIsNotNone(ctrl)
            assert ctrl is not None
            self.assertEqual(ctrl.Name, "Desktop")
            self.assertEqual(title, "Desktop")

        with patch("orbit.adapters.uia.tree.service.ControlFromHandle", side_effect=Exception("HWND not found")):
            ctrl, title = service.resolve_root_control(target_hwnd=9999)
            self.assertIsNone(ctrl)
            self.assertEqual(title, "")

    # 13. CurrentStateObserver integration
    def test_13_current_state_observer_integration(self):
        """Verify CurrentStateObserver successfully coordinates through DesktopPerceptionEngine to UIA observer."""
        obs = CurrentStateObserver()
        self.assertIsNotNone(obs.perception_engine)
        self.assertIsNotNone(obs.perception_engine.observer)
        self.assertIsNotNone(obs.perception_engine.observer._uia_observer)

    # 14. DesktopPerceptionEngine / DesktopObserver integration
    def test_14_desktop_observer_tree_extractor_wiring(self):
        """Verify DesktopObserver delegates UIA interrogation to UIAElementObserver backed by TreeService."""
        desktop_obs = DesktopObserver()
        uia_obs = desktop_obs._uia_observer
        self.assertIsInstance(uia_obs._tree_extractor, UIAElementTreeExtractor)
        self.assertIsInstance(uia_obs._tree_extractor.tree_service, TreeService)

    # 15. Single authoritative production observation pipeline
    def test_15_single_authoritative_pipeline(self):
        """Prove there are NOT two independent production UIA paths.

        UIAElementObserver must delegate exclusively to UIAElementTreeExtractor,
        which wraps TreeService as its execution substrate.
        """
        uia_observer = UIAElementObserver()
        mock_service = MagicMock(spec=TreeService)
        mock_service.observe_window_elements.return_value = (None, [])

        extractor = UIAElementTreeExtractor(tree_service=mock_service)
        uia_observer._tree_extractor = extractor

        focused, elements = uia_observer.observe_elements(target_hwnd=555, max_elements=25)
        mock_service.observe_window_elements.assert_called_once_with(
            target_hwnd=555,
            max_elements=25,
        )

    # 16. Canonical UIElementObservation contract preservation
    def test_16_canonical_observation_contract_preservation(self):
        """Verify that tree traversal produces canonical UIElementObservation with BoundingBox."""
        btn = FakeControl(name="Submit", rect=(10, 20, 110, 60))
        root = FakeControl(name="Form", children=[btn])

        with patch("orbit.adapters.uia.tree.traversal.CachedControlHelper.get_cached_children", side_effect=[[btn], []]):
            elements = traverse_tree(root, max_depth=2, max_elements=5)

        self.assertEqual(len(elements), 1)
        obs = elements[0]
        self.assertIsInstance(obs, UIElementObservation)
        self.assertEqual(obs.name, "Submit")
        self.assertIsInstance(obs.bounding_box, BoundingBox)
        self.assertEqual(obs.bounding_box.left, 10)
        self.assertEqual(obs.bounding_box.top, 20)
        self.assertEqual(obs.bounding_box.width, 100)
        self.assertEqual(obs.bounding_box.height, 40)

    # 17. Sensory-only invariant check
    def test_17_sensory_only_invariant(self):
        """Static verification: Tree subsystem does not import planner, controller, or action dispatchers."""
        import orbit.adapters.uia.tree.cache_utils as cu
        import orbit.adapters.uia.tree.traversal as tr
        import orbit.adapters.uia.tree.service as sv

        forbidden_imported_names = {
            "AgentPlanner",
            "PrimitiveExecutionController",
            "PrimitiveComposer",
            "PrimitiveValidator",
            "execute_primitive",
            "SendInput",
            "mouse_event",
            "keybd_event",
        }

        for mod in (cu, tr, sv):
            source = inspect.getsource(mod)
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name, forbidden_imported_names, f"Forbidden import {alias.name} in {mod.__name__}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for alias in node.names:
                            self.assertNotIn(alias.name, forbidden_imported_names, f"Forbidden import {alias.name} in {mod.__name__}")


if __name__ == "__main__":
    unittest.main()
