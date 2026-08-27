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
# being played, e.g.: "(n-1) prevGLOSS --> (n) currentGLOSS --> (n+1) nextGLOSS", or, during a
# transition between two glosses: "(n) lastGLOSS --> (n+1) nextGLOSS".
#
# The panel is a Text object parented to the render camera (so it always sits at the bottom of
# the camera view, regardless of the camera's own position/animation) and its content is updated
# on every frame via a `frame_change_pre` handler, since Blender doesn't support keyframing a
# string property directly. This module doesn't touch the source .blend scene: every object it
# needs is created procedurally at runtime.
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
# Fraction of the frustum width the text is sized to fill, assuming a line of ~64 characters.
_WIDTH_MARGIN_RATIO = 0.9
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
# for extra arguments, so the timeline is stashed here by setup_gloss_panel()).
_timeline: List[GlossSegment] = []


def setup_gloss_panel(camera_obj: bpy.types.Object, gloss_timeline: List[GlossSegment]) -> bpy.types.Object:
    """Create the gloss subtitle panel, parent it to `camera_obj`, and register the per-frame
    handler that keeps its text in sync with the current playback frame.

    :param camera_obj: The camera the panel should be attached to (bottom of its view).
    :param gloss_timeline: The realized (start_frame, end_frame) range of every gloss, as produced by `Glue.realize_mms()`.
    """
    global _timeline
    _timeline = sorted(gloss_timeline, key=lambda seg: seg.start_frame)

    _remove_existing_panel()

    backdrop_obj = _create_backdrop_object(GLOSS_PANEL_BACKDROP_NAME)
    text_obj = _create_text_object(GLOSS_PANEL_OBJECT_NAME)
    _place_on_camera(text_obj, backdrop_obj, camera_obj)

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
    curve_data.align_x = "CENTER"
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


def _place_on_camera(text_obj: bpy.types.Object, backdrop_obj: bpy.types.Object, camera_obj: bpy.types.Object):
    """Parent both objects to `camera_obj` and position/scale them to sit near the bottom edge of
    the camera's view frustum, computed from the current scene's render resolution/aspect ratio.
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
    text_obj.location = position
    text_obj.rotation_euler = (0.0, 0.0, 0.0)

    font_size = (frame_width * _WIDTH_MARGIN_RATIO) / (_REFERENCE_CHAR_COUNT * _AVERAGE_CHAR_WIDTH_FACTOR)
    text_obj.data.size = font_size

    line_height = font_size * _LINE_HEIGHT_FACTOR
    backdrop_obj.parent = camera_obj
    # The text's origin is its bottom-center (align_y='BOTTOM'), so the backdrop is centered
    # half a line above it; its z is pushed slightly further from the camera than the text, so
    # the (opaque) text renders on top of the (semi-transparent) backdrop instead of z-fighting.
    backdrop_obj.location = Vector((position.x, position.y + line_height * 0.5, position.z * _BACKDROP_DEPTH_PUSH))
    backdrop_obj.rotation_euler = (0.0, 0.0, 0.0)
    backdrop_obj.scale = (
        frame_width * _WIDTH_MARGIN_RATIO * _BACKDROP_WIDTH_PADDING,
        line_height * _BACKDROP_HEIGHT_FACTOR,
        1.0,
    )


def _format_gloss(segment: GlossSegment) -> str:
    return f"({segment.index}) {segment.name}"


def _join_with_arrows(parts: List[str]) -> Tuple[str, List[Tuple[int, int]], List[Tuple[int, int]]]:
    """Join `parts` with " --> " separators.

    :returns: (body, part_spans, arrow_spans) — each span is a [start, end) character range within `body`.
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


def _resolve_status(frame: float, timeline: List[GlossSegment]):
    """Resolve the playback status at `frame`.

    :returns: ("gloss", prev_or_None, current, next_or_None) when `frame` falls inside a gloss,
        or ("transition", last_or_None, next_or_None) otherwise (including before the first gloss
        or after the last one, where one of the two may be None).
    """

    for i, segment in enumerate(timeline):
        if segment.start_frame <= frame <= segment.end_frame:
            prev_segment = timeline[i - 1] if i > 0 else None
            next_segment = timeline[i + 1] if i + 1 < len(timeline) else None
            return "gloss", prev_segment, segment, next_segment

    last_segment = None
    next_segment = None
    for segment in timeline:
        if segment.end_frame < frame:
            last_segment = segment
        elif segment.start_frame > frame:
            next_segment = segment
            break

    return "transition", last_segment, next_segment


def _compute_body_and_highlight(frame: float, timeline: List[GlossSegment]) -> Tuple[str, Optional[Tuple[int, int]]]:
    """Compute the panel text and the [start, end) character span to highlight/bold, if any."""

    if not timeline:
        return "", None

    status, *rest = _resolve_status(frame, timeline)

    if status == "gloss":
        prev_segment, current_segment, next_segment = rest
        parts = [_format_gloss(s) for s in (prev_segment, current_segment, next_segment) if s is not None]
        current_part_index = 1 if prev_segment is not None else 0
        body, part_spans, _ = _join_with_arrows(parts)
        return body, part_spans[current_part_index]

    # "transition"
    last_segment, next_segment = rest
    if last_segment is not None and next_segment is not None:
        body, _, arrow_spans = _join_with_arrows([_format_gloss(last_segment), _format_gloss(next_segment)])
        return body, arrow_spans[0]
    if last_segment is not None:
        return _format_gloss(last_segment), None
    if next_segment is not None:
        return _format_gloss(next_segment), None
    return "", None


def _apply_body(text_obj: bpy.types.Object, body: str, highlight_span: Optional[Tuple[int, int]]):
    curve_data = text_obj.data
    curve_data.body = body
    for i, char_format in enumerate(curve_data.body_format):
        is_highlighted = highlight_span is not None and highlight_span[0] <= i < highlight_span[1]
        char_format.use_bold = is_highlighted
        char_format.material_index = 1 if is_highlighted else 0


@persistent
def _gloss_panel_frame_handler(scene, depsgraph):
    if GLOSS_PANEL_OBJECT_NAME not in bpy.data.objects:
        return
    text_obj = bpy.data.objects[GLOSS_PANEL_OBJECT_NAME]
    body, highlight_span = _compute_body_and_highlight(scene.frame_current, _timeline)
    _apply_body(text_obj, body, highlight_span)
