# ORBIT — MILESTONE M1.7 STEP 2: FORENSIC VISUAL RECOGNITION AUDIT
# VISUAL TEMPLATE, ICON & NON-TEXT UI TARGET RECOGNITION AUDIT

**Milestone**: M1.7 Step 2  
**Author**: Antigravity Autonomous Agent (Pair Programming with User)  
**Date**: 2026-09-06  
**Operating System**: Windows 11 AMD64 (Build 26200)  
**Python Runtime**: Python 3.13.7  
**Status**: AUDIT COMPLETE — IMPLEMENTATION READY  

---

## 1. EXECUTIVE SUMMARY & FORENSIC PROBLEM STATEMENT

ORBIT's Milestone M1.7 Step 1 successfully added a local, truthful Windows Native OCR perception capability (`Windows.Media.Ocr.OcrEngine` via WinRT C ABI). This enabled ORBIT to truthfully localize on-screen text when accessibility controls are missing.

However, desktop operating systems and modern application frameworks feature significant non-text graphical elements that cannot be localized by OCR:
- **Toolbar & Navigation Icons** (Search magnifying glass, Gear/Settings cog, Refresh arrow, Hamburger menu, Back/Forward arrows).
- **Application Logos & Branding Glyphs** (System tray icons, window dock icons).
- **Custom Canvas & Flutter/Qt Controls** (Vector/bitmap toggle switches, color pickers, graphical sliders, canvas nodes).
- **Graphical Buttons** (Icon-only close/minimize controls without text labels).

Milestone M1.7 Step 2's objective is to implement a **deterministic, evidence-based visual target recognition subsystem** using high-performance template and icon matching, strictly grounded in coordinate geometry, confidence scoring, provenance tracking, and fail-closed safety.

---

## 2. FORENSIC AUDIT OF EXISTING PERCEPTION & TARGETING PIPELINE

### A. What Visual Evidence is Available?
1. **Raw Screen Pixels**: Captured via Win32 GDI `BitBlt` / `GetDIBits` in `ProductionObservationAdapter` (`src/orbit/adapters/observation/adapter.py`) into PIL `Image.Image` (RGB format).
2. **Snapshot Metadata**: `ObservationSnapshot` carries `snapshot_id`, monotonic `timestamp_ns`, `generation_id`, and `desktop_geometry`.
3. **Telemetry Buffer**: `snapshot.telemetry` and `intent.metadata` can transport visual evidence and templates across the runtime boundary.

### B. Which Coordinate Spaces Exist?
1. **`SCREENSHOT_PIXEL_SPACE`**: Relative to the $(0, 0)$ top-left of the captured screenshot image bitmap.
2. **`WINDOW_CLIENT_SPACE`**: Relative to the client area origin of a specific HWND (`ClientToScreen` conversion).
3. **`VIRTUAL_DESKTOP_SPACE`**: Global virtual desktop pixel coordinates encompassing all monitors (supports negative origins e.g. $x < 0, y < 0$).
4. **`LOGICAL_DPI_SPACE`**: Device-Independent Pixels scaled by the display DPI factor ($96\text{ DPI} = 1.0\times, 192\text{ DPI} = 2.0\times$).

### C. How Templates Will Be Represented
Templates are strongly typed via `VisualTemplate`:
- `template_id`: Unique deterministic identifier (e.g. `tpl_settings_gear_01`).
- `name` / `semantic_intent`: Intended human-readable meaning (e.g. "Settings Gear Icon").
- `image`: PIL RGB/Grayscale `Image.Image` or raw pixel buffer.
- `dimensions`: $(W, H)$ in physical template pixels.
- `source`: `VisualTemplateSource` (`TRUSTED_REGISTERED_TEMPLATE` vs `UNTRUSTED_RUNTIME_IMAGE`).
- `checksum`: SHA-256 hash of the template bitmap bytes for cryptographic integrity.
- `mask`: Optional alpha/binary mask for non-rectangular icons.

### D. How Template Provenance Will Be Tracked
Visual templates are categorized under strict trust boundaries:
- `TRUSTED_REGISTERED_TEMPLATE`: Pre-registered application templates with known dimensions and verified SHA-256 hashes.
- `UNTRUSTED_RUNTIME_IMAGE`: Dynamic runtime templates; subject to stricter confidence thresholds and explicit policy gating.

### E. How Confidence Will Be Calculated
Visual matching utilizes deterministic **Normalized Cross-Correlation (NCC)**:
$$\gamma(x, y) = \frac{\sum_{x', y'} (T(x', y') - \bar{T})(I(x + x', y + y') - \bar{I}_{x, y})}{\sqrt{\sum_{x', y'} (T(x', y') - \bar{T})^2 \sum_{x', y'} (I(x + x', y + y') - \bar{I}_{x, y})^2}}$$
where $\gamma(x, y) \in [-1.0, 1.0]$.
- Peak correlation values above $0.85$ indicate strong visual similarity.
- Confidence is calculated directly from the mathematical peak correlation score:
  $$\text{Confidence} = \max(0.0, \gamma_{\text{max}})$$
- Confidence is **never fabricated or hardcoded to 1.0**.

### F. How False Positives Will Fail Closed
- `minimum_confidence` threshold (default: $0.85$ for registered templates, $0.90$ for runtime templates). Matches below threshold return `VisualMatchStatus.LOW_CONFIDENCE` and produce **ZERO pointer events**.

### G. How Duplicate Visual Matches Will Be Handled (Ambiguity Gate)
- If multiple local correlation peaks exceed the threshold:
  - Calculate the peak separation margin: $\Delta = \gamma_{\text{best}} - \gamma_{\text{second\_best}}$.
  - If $\Delta < \text{ambiguity\_margin}$ (default: $0.05$) or multiple identical correlation peaks exist:
    $\to$ Return `VisualMatchStatus.AMBIGUOUS` with candidate list and fail closed (zero pointer dispatch).

### H. How DPI Scaling Affects Matching
- Screenshots captured via GDI `BitBlt` under Per-Monitor DPI V2 are at physical pixel resolution.
- Templates captured at standard DPI ($96\text{ DPI}$) on a $2.0\times$ display ($192\text{ DPI}$) differ in pixel scale.
- Multi-scale matching evaluates candidate scales in a bounded set (e.g. $[0.75, 1.0, 1.25, 1.5, 2.0]\times$) or exact DPI scale factor derived from `DisplayMetrics`.
- Coordinates are mapped to `VIRTUAL_DESKTOP_SPACE` using `OCRCoordinateMapper` / `VisualCoordinateMapper`.

### I. How Stale Screenshots Will Be Rejected
- Before visual matching: `snapshot.is_stale` or `snapshot.generation_id != current_generation_id` immediately halts matching with `VisualMatchStatus.STALE_OBSERVATION`.
- Derived target coordinates carry `desktop_generation_id` and cannot survive layout changes or AppBar dock resizing.

### J. How Visual Coordinates Enter the Existing Safety Pipeline
$$\text{Visual Bounding Box} \to \text{VisualCoordinateMapper} \to \text{calculate\_safe\_action\_point()} \to \text{WorkspaceAdapter.validate\_coordinate()} \to \text{AutonomousDispatchGate} \to \text{Pointer Action}$$
No direct pointer injection is permitted without passing all existing M1.6 safety gates.

### K. Which Capabilities Can Genuinely Be LIVE_OS_VALIDATED?
- Live screen capture of a real Windows application window.
- Real-time template matching of a known UI button / graphical icon from the live capture.
- Derivation and validation of physical virtual desktop coordinates against `ProductionWorkspaceAdapter`.
- Live pointer movement to the validated safe action point.

### L. Which Capabilities Remain TEST_PROVEN Only?
- Multi-monitor negative virtual desktop topologies (tested synthetically on single-monitor test host).
- Extreme scale-factor degradation and corrupted template recovery paths.

---

## 3. PROPOSED IMPLEMENTATION BLUEPRINT

```text
src/orbit/runtime/perception/
├── __init__.py               # Perception subsystem exports
├── models.py                 # OCR models & shared coordinate spaces
├── visual_models.py          # VisualTemplate, VisualMatch, VisualMatchResult, VisualMatchStatus, VisualMatchPolicy
├── visual_matcher.py         # Deterministic TemplateVisualMatcher (NumPy NCC engine) & MockVisualMatcher
├── visual_engine.py          # VisualPerceptionEngine coordinating templates, multi-scale matching & freshness
├── coordinate_mapper.py      # Extended coordinate transformation engine
├── normalization.py          # Deterministic text normalization
├── ocr.py                    # Windows Native WinRT OCR
└── engine.py                 # SemanticPerceptionEngine integrating OCR + Visual Perception
```

---

**AUDIT VERDICT**: The architecture is fully sound, uses existing approved dependencies (`numpy`, `pillow`), and is completely fail-closed. Proceeding directly to implementation.
