# Phase 2G.3 — Dense Visual Grounding & Set-of-Marks (SOM) Audit

## 1. Overview & Objectives

Phase 2G.3 introduces native Set-of-Marks (SOM) visual overlay generation and dense visual region grounding into ORBIT's perception and targeting pipeline (`SetOfMarksGenerator` + `VisualRegionGrounder`).

In modern GUI automation (such as OpenAI Astra 6 / Operator), applications frequently present custom-drawn canvases, direct GPU/DirectX render surfaces, web elements lacking accessibility descriptors, or non-standard Win32/DirectUI widgets where native accessibility trees (UIA, MSAA) are incomplete or empty.

Phase 2G.3 establishes a native visual grounding capability that:
1. Harvests interactable elements from UIA, OCR tokens, and visual regions.
2. Deduplicates overlapping bounding boxes using Intersection-over-Union (IoU) Non-Maximum Suppression.
3. Renders high-contrast, numbered visual mark tags (`[1]`, `[2]`, `[3]`, ...) directly on screenshots.
4. Provides bidirectional mapping between numeric mark identifiers and verified physical screen coordinates (`SafeActionPoint`).
5. Directly supports normalized 2D bounding boxes `[u1, v1, u2, v2]` from Vision-Language Models.

---

## 2. Architecture & Components

### 2.1 Set-of-Marks Generator (`SetOfMarksGenerator`)
- **File**: `src/orbit/runtime/perception/set_of_marks.py`
- Generates annotated images with neon badges (`#FF0055`, `#00E5FF`, `#76FF03`, `#FFD600`, `#D500F9`, `#FF6D00`, `#00E676`, `#2979FF`).
- Enforces active window containment filtering to prevent clicking out-of-scope desktop chrome unless permitted.
- Deduplicates dense OCR and UIA bounding boxes with configurable IoU threshold ($\ge 0.70$).
- Emits formatted text descriptions for multi-modal reasoning contexts.

### 2.2 Dense Visual Region Grounder (`VisualRegionGrounder`)
- **File**: `src/orbit/runtime/targeting/visual_grounder.py`
- Resolves bracketed mark strings (`Click [5]`, `mark_id=5`, `Save #2`) into physical targets.
- Computes deterministic, inside-the-box `SafeActionPoint` coordinates.
- Validates 2D normalized bounding boxes, rejecting inverted, degenerate, or out-of-bounds coordinates ($< 0.0$ or $> 1.0$).
- Produces fully auditable `TargetEvidence` records with `source="VISUAL_SOM"` and `source="VISUAL_BBOX"`.

---

## 3. Verification & Gate Evidence

### 3.1 Unit Test Coverage
- `tests/unit/test_set_of_marks.py`:
  - `test_som_generator_with_uia_elements` (PASS)
  - `test_som_generator_with_ocr_tokens` (PASS)
  - `test_som_iou_deduplication` (PASS)
  - `test_som_active_window_filtering` (PASS)
  - `test_visual_region_grounder_resolves_numeric_mark` (PASS)
  - `test_visual_region_grounder_resolves_box_2d` (PASS)
  - `test_visual_region_grounder_rejects_invalid_boxes` (PASS)

### 3.2 Integration Test
- `tests/integration/test_visual_som_grounding.py`:
  - `test_som_visual_grounding_end_to_end` (PASS)
  - Validates full end-to-end flow: Canvas image $\to$ SOM annotation $\to$ Agent decision referencing mark `[2]` $\to$ `VisualRegionGrounder` safe action point $\to$ Pointer click dispatch.

---

## 4. Exit Gate Confirmation
- [x] Set-of-Marks overlay generator produces clean visual annotations.
- [x] IoU bounding box deduplication operational.
- [x] Multi-modal text summary generation implemented.
- [x] VisualRegionGrounder enforces safe action point calculation and window bounds.
- [x] Closed-loop integration test passing.
