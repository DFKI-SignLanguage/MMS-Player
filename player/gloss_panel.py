#    MMS Player - procedural animation of Sign Language avatars
#    Copyright (C) 2024 German Research Center for Artificial Intelligence (DFKI)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

#
# Optional, procedurally-generated debug overlay showing which gloss (MMS row) is currently
# being played: "... (n-1) prevGLOSS --> (n) currentGLOSS --> (n+1) nextGLOSS ...", with the
# active gloss highlighted, or, during a transition between two glosses, with the arrow between
# them highlighted.
#
# The whole gloss sequence is set as a single, static line of text once, at setup time. On every
# frame, the panel only: i) moves which character span is highlighted, and ii) smoothly scrolls
# the text horizontally so the active gloss/arrow stays centered — holding still while a gloss is
# playing, and panning to the next one during a transition. This avoids swapping the displayed
# text at every gloss/transition boundary, which reads as an abrupt jump rather than a flow.
#
# The panel is parented to the render camera (so it always sits at the bottom of the camera view,
# regardless of the camera's own position/animation). Since Blender doesn't support keyframing a
# string property, both the highlight and the scroll position are driven by a `frame_change_pre`
# handler. This module doesn't touch the source .blend scene: every object it needs is created
# procedurally at runtime.
#

import bpy
from bpy.app.handlers import persistent

from typing import List, Optional, Tuple
from mathutils import Vector

from .merge import GlossSegment
from .logging import logger

GLOSS_PANEL_OBJECT_NAME = "GlossPanel_Text"
GLOSS_PANEL_BACKDROP_NAME = "GlossPanel_Backdrop"

# How far beyond the camera's near clip plane to push the panel (as a multiplier), to keep it
# safely inside the frustum without needing to know the scene's real-world scale.
_DEPTH_FACTOR = 3.0
# How far down from the top of the frame the panel's anchor point sits (0 = top, 1 = bottom).
_VERTICAL_ANCHOR_RATIO = 0.05
# The text is sized to fill the full frustum width, assuming a line of ~64 characters.
_REFERENCE_CHAR_COUNT = 64
_AVERAGE_CHAR_WIDTH_FACTOR = 0.55  # Rough average glyph width, relative to font size, for the default font.
_LINE_HEIGHT_FACTOR = 1.3  # Approximate line height, relative to font size, for the default font.

# The semi-transparent backing plate behind the text, for readability over busy footage.
_BACKDROP_COLOR = (0.0, 0.0, 0.0)
_BACKDROP_ALPHA = 0.55
_BACKDROP_WIDTH_PADDING = 1.08  # Extra width relative to the text's own margin, so it doesn't hug the glyphs.
_BACKDROP_HEIGHT_FACTOR = 1.6  # Backdrop height, relative to the text line height.
_BACKDROP_DEPTH_PUSH = 1.001  # Pushes the backdrop slightly further from the camera than the text, avoiding z-fighting.

_ARROW = ">>>>"
_SEPARATOR = f" {_ARROW} "

# Module-level state consumed by the frame handler (Blender's handler signature leaves no room
# for extra arguments, so setup_gloss_panel() stashes everything it needs here).
_timeline: List[GlossSegment] = []
_part_spans: List[Tuple[int, int]] = []  # Per-gloss [start, end) character span within the static full body text.
_arrow_spans: List[Tuple[int, int]] = []  # arrow_spans[i]: the arrow between gloss i and gloss i+1.
_scroll_control_points: List[Tuple[float, float]] = []  # (frame, local_x) waypoints; see _build_scroll_control_points().
_panel_anchor: Vector = Vector((0.0, 0.0, 0.0))  # Fixed camera-local placement of the panel's centerline.


def setup_gloss_panel(camera_obj: bpy.types.Object, gloss_timeline: List[GlossSegment]) -> bpy.types.Object:
    """Create the gloss subtitle panel, parent it to `camera_obj`, and register the per-frame
    handler that keeps its highlight and scroll position in sync with the current playback frame.

    :param camera_obj: The camera the panel should be attached to (bottom of its view).
    :param gloss_timeline: The realized (start_frame, end_frame) range of every gloss, as produced by `Glue.realize_mms()`.
    """
    global _timeline, _part_spans, _arrow_spans, _scroll_control_points, _panel_anchor

    _timeline = sorted(gloss_timeline, key=lambda seg: seg.start_frame)

    _remove_existing_panel()

    backdrop_obj = _create_backdrop_object(GLOSS_PANEL_BACKDROP_NAME)
    text_obj = _create_text_object(GLOSS_PANEL_OBJECT_NAME)
    _panel_anchor = _place_on_camera(text_obj, backdrop_obj, camera_obj)

    full_body, _part_spans, _arrow_spans = _join_with_arrows([_format_gloss(s) for s in _timeline])
    text_obj.data.body = full_body

    # A flat average-glyph-width estimate drifts badly over a long line (e.g. real fonts render
    # "I" several times narrower than "W"), so each gloss's actual on-screen center is measured
    # directly off the text object's own geometry instead.
    boundary_indices = [index for span in _part_spans for index in span]
    local_x_by_index = _measure_local_x_positions(text_obj, full_body, boundary_indices)
    _scroll_control_points = _build_scroll_control_points(_timeline, _part_spans, local_x_by_index)

    bpy.app.handlers.frame_change_pre.append(_gloss_panel_frame_handler)

    # Make sure the very first rendered/displayed frame already shows the correct status,
    # rather than waiting for the next frame change.
    _gloss_panel_frame_handler(bpy.context.scene, None)

    logger.info(f"Gloss panel enabled, tracking {len(_timeline)} gloss segments.")
    return text_obj


def _remove_existing_panel():
    """Remove any panel object/handler left over from a previous run in the same Blender session."""

    handlers = bpy.app.handlers.frame_change_pre
    for handler in list(handlers):
        if getattr(handler, "__name__", None) == _gloss_panel_frame_handler.__name__:
            handlers.remove(handler)

    for name in (GLOSS_PANEL_OBJECT_NAME, GLOSS_PANEL_BACKDROP_NAME):
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)


def _create_text_object(name: str) -> bpy.types.Object:
    """Create a FONT curve object with two materials (index 0 = normal, index 1 = highlighted),
    selectable per-character via `body_format[i].material_index`.
    """

    curve_data = bpy.data.curves.new(name=name, type="FONT")
    curve_data.body = ""
    # 'LEFT' puts the object's local origin at the start of the text, so a character's local x
    # position is simply proportional to its index — see _build_scroll_control_points().
    curve_data.align_x = "LEFT"
    curve_data.align_y = "BOTTOM"

    curve_data.materials.append(_make_flat_emissive_material(f"{name}_Normal", (1.0, 1.0, 1.0)))
    curve_data.materials.append(_make_flat_emissive_material(f"{name}_Highlight", (1.0, 0.85, 0.1)))

    text_obj = bpy.data.objects.new(name, curve_data)
    text_obj.visible_shadow = False
    bpy.context.scene.collection.objects.link(text_obj)
    return text_obj


def _make_flat_emissive_material(name: str, color: Tuple[float, float, float], alpha: float = 1.0) -> bpy.types.Material:
    """A simple emissive material, so the panel stays clearly legible regardless of scene lighting."""

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 1.0
        bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1.0:
        # 'BLENDED' gives smooth alpha compositing; the (deprecated) 'blend_method' equivalent
        # would be 'BLEND'. Without this the material renders opaque regardless of the Alpha input.
        mat.surface_render_method = "BLENDED"
        mat.show_transparent_back = False
    return mat


def _create_backdrop_object(name: str) -> bpy.types.Object:
    """Create the flat, semi-transparent plate that sits behind the text for readability."""

    mesh = bpy.data.meshes.new(name)
    # A unit quad in the local XY plane, facing +Z (matches the text's own facing, see
    # `_create_text_object`). It is rescaled to its final size in `_place_on_camera()`.
    mesh.from_pydata(
        [(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    mesh.materials.append(_make_flat_emissive_material(f"{name}_Material", _BACKDROP_COLOR, alpha=_BACKDROP_ALPHA))

    backdrop_obj = bpy.data.objects.new(name, mesh)
    backdrop_obj.visible_shadow = False
    bpy.context.scene.collection.objects.link(backdrop_obj)
    return backdrop_obj


def _place_on_camera(text_obj: bpy.types.Object, backdrop_obj: bpy.types.Object, camera_obj: bpy.types.Object) -> Vector:
    """Parent both objects to `camera_obj`, and position/scale them to sit near the bottom edge of
    the camera's view frustum, computed from the current scene's render resolution/aspect ratio.

    :returns: the fixed camera-local point the text scrolls around, see `_build_scroll_control_points()`.
    """

    scene = bpy.context.scene
    points = list(camera_obj.data.view_frame(scene=scene))
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    z = points[0].z

    left_x, right_x = min(xs), max(xs)
    bottom_y, top_y = min(ys), max(ys)
    center_x = (left_x + right_x) / 2.0
    frame_width = right_x - left_x

    # `view_frame()` returns the frustum corners at the near clip plane. For a perspective
    # camera the frustum is a cone from the local origin, so scaling every coordinate by the
    # same factor moves the point further away while staying on the same frustum edge.
    depth_factor = _DEPTH_FACTOR if camera_obj.data.type == "PERSP" else 1.0

    anchor_y = top_y + (bottom_y - top_y) * _VERTICAL_ANCHOR_RATIO
    position = Vector((center_x, anchor_y, z)) * depth_factor
    frame_width *= depth_factor

    text_obj.parent = camera_obj
    text_obj.location = position.copy()
    text_obj.rotation_euler = (0.0, 0.0, 0.0)

    font_size = frame_width / (_REFERENCE_CHAR_COUNT * _AVERAGE_CHAR_WIDTH_FACTOR)
    text_obj.data.size = font_size

    line_height = font_size * _LINE_HEIGHT_FACTOR
    backdrop_obj.parent = camera_obj
    # The text's origin is its bottom-left (align_x='LEFT', align_y='BOTTOM'), but the backdrop
    # stays centered on the panel's fixed anchor point, half a line above it; its z is pushed
    # slightly further from the camera than the text, so the (opaque) text renders on top of the
    # (semi-transparent) backdrop instead of z-fighting.
    backdrop_obj.location = Vector((position.x, position.y + line_height * 0.5, position.z * _BACKDROP_DEPTH_PUSH))
    backdrop_obj.rotation_euler = (0.0, 0.0, 0.0)
    backdrop_obj.scale = (
        frame_width * _BACKDROP_WIDTH_PADDING,
        line_height * _BACKDROP_HEIGHT_FACTOR,
        1.0,
    )

    return position


def _format_gloss(segment: GlossSegment) -> str:
    return f"({segment.index}) {segment.name}"


def _join_with_arrows(parts: List[str]) -> Tuple[str, List[Tuple[int, int]], List[Tuple[int, int]]]:
    """Join `parts` with " --> " separators.

    :returns: (body, part_spans, arrow_spans) — each span is a [start, end) character range within `body`.
        arrow_spans[i] is the arrow between parts[i] and parts[i + 1].
    """

    body = ""
    part_spans = []
    arrow_spans = []
    for i, part in enumerate(parts):
        if i > 0:
            arrow_start = len(body) + 1  # Skip the separator's leading space.
            body += _SEPARATOR
            arrow_spans.append((arrow_start, arrow_start + len(_ARROW)))
        start = len(body)
        body += part
        part_spans.append((start, start + len(part)))
    return body, part_spans, arrow_spans


def _measure_local_x_positions(text_obj: bpy.types.Object, full_body: str, char_indices: List[int]) -> dict:
    """Measure the actual local-space x offset of each of `char_indices` within `full_body`, using
    the real (assigned) font's glyph metrics rather than an average-width estimate.

    Since the text's origin is at its start (align_x='LEFT'), the on-screen width of the prefix
    `full_body[:index]` is exactly that character's local x offset. This temporarily truncates
    `text_obj.data.body` to measure each prefix's rendered `dimensions.x`, then restores it — done
    once at setup time, not per frame.
    """

    view_layer = bpy.context.view_layer
    positions = {}
    for index in sorted(set(char_indices)):
        text_obj.data.body = full_body[:index]
        view_layer.update()
        positions[index] = text_obj.dimensions.x
    text_obj.data.body = full_body
    view_layer.update()
    return positions


def _build_scroll_control_points(
        timeline: List[GlossSegment],
        part_spans: List[Tuple[int, int]],
        local_x_by_index: dict,
) -> List[Tuple[float, float]]:
    """Build the (frame, local_x) waypoints the panel's scroll position is interpolated over.

    Two points per gloss — one at its start frame, one at its end frame, both at the same local_x
    (its center, in the static full-body text, from `local_x_by_index`) — so linear interpolation
    between consecutive points naturally holds still while a gloss is playing (both points share
    the same x) and glides smoothly from one gloss's center to the next while transitioning (the
    gap between one gloss's end point and the next one's start point).
    """

    control_points = []
    for segment, span in zip(timeline, part_spans):
        center_x = (local_x_by_index[span[0]] + local_x_by_index[span[1]]) / 2.0
        control_points.append((segment.start_frame, center_x))
        control_points.append((segment.end_frame, center_x))
    return control_points


def _interpolate(control_points: List[Tuple[float, float]], frame: float) -> float:
    """Piecewise-linear interpolation of `control_points` (sorted by frame) at `frame`, clamped
    to the first/last value outside their range."""

    if not control_points:
        return 0.0
    if frame <= control_points[0][0]:
        return control_points[0][1]
    if frame >= control_points[-1][0]:
        return control_points[-1][1]

    for (frame_a, x_a), (frame_b, x_b) in zip(control_points, control_points[1:]):
        if frame_a <= frame <= frame_b:
            if frame_b == frame_a:
                return x_b
            t = (frame - frame_a) / (frame_b - frame_a)
            return x_a + (x_b - x_a) * t

    return control_points[-1][1]


def _resolve_status(frame: float, timeline: List[GlossSegment]) -> Tuple[str, Optional[int]]:
    """Resolve the playback status at `frame`.

    :returns: ("gloss", i) when `frame` falls inside `timeline[i]`; ("transition", i) when it
        falls between `timeline[i]` and `timeline[i + 1]`; ("before", None) / ("after", None) when
        it falls before the first / after the last gloss; ("empty", None) for an empty timeline.
    """

    if not timeline:
        return "empty", None

    for i, segment in enumerate(timeline):
        if segment.start_frame <= frame <= segment.end_frame:
            return "gloss", i

    if frame < timeline[0].start_frame:
        return "before", None
    if frame > timeline[-1].end_frame:
        return "after", None

    for i in range(len(timeline) - 1):
        if timeline[i].end_frame < frame < timeline[i + 1].start_frame:
            return "transition", i

    # Shouldn't happen (every gap between consecutive glosses is covered above), but fail safe.
    return "after", None


def _compute_highlight_span(
        frame: float,
        timeline: List[GlossSegment],
        part_spans: List[Tuple[int, int]],
        arrow_spans: List[Tuple[int, int]],
) -> Optional[Tuple[int, int]]:
    """The [start, end) character span (within the static full body text) to highlight/bold."""

    status, i = _resolve_status(frame, timeline)
    if status == "gloss":
        assert i is not None
        return part_spans[i]
    if status == "transition":
        assert i is not None
        return arrow_spans[i]
    if status == "before":
        return part_spans[0] if part_spans else None
    if status == "after":
        return part_spans[-1] if part_spans else None
    return None


def _apply_highlight(text_obj: bpy.types.Object, highlight_span: Optional[Tuple[int, int]]):
    for i, char_format in enumerate(text_obj.data.body_format):
        is_highlighted = highlight_span is not None and highlight_span[0] <= i < highlight_span[1]
        char_format.use_bold = is_highlighted
        char_format.material_index = 1 if is_highlighted else 0


@persistent
def _gloss_panel_frame_handler(scene, depsgraph):
    if GLOSS_PANEL_OBJECT_NAME not in bpy.data.objects:
        return
    text_obj = bpy.data.objects[GLOSS_PANEL_OBJECT_NAME]
    frame = scene.frame_current

    highlight_span = _compute_highlight_span(frame, _timeline, _part_spans, _arrow_spans)
    _apply_highlight(text_obj, highlight_span)

    target_local_x = _interpolate(_scroll_control_points, frame)
    text_obj.location.x = _panel_anchor.x - target_local_x
