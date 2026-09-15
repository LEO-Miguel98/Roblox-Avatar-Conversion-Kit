from __future__ import annotations

from collections import Counter


def install(pmx):
    """Pin visible facial-skin borders to the reconstructed eye/mouth shapes.

    v0.3.19 made broad facial skin participate in expressions, but the actual hole/border vertices
    around an animated-head eye or mouth could still be driven only by a soft falloff.  Those border
    loops define what the viewer reads as the eyelid/socket and lip line, so v0.3.20 detects the
    boundary edges of the restored opaque face shell and gives nearby eye/lip borders the full local
    expression shape.  Interior cheek/forehead/chin vertices keep the softer v0.3.19 cage response.
    """

    base_reconstructed_face_morphs = pmx._reconstructed_face_morphs

    def boundary_face_morphs(
        mesh,
        group_to_bone,
        source_to_pmx,
        *,
        regions=None,
        mouth_hidden_at_neutral=False,
    ):
        regions = regions or pmx._analyze_face_regions(mesh, group_to_bone)
        morphs = base_reconstructed_face_morphs(
            mesh,
            group_to_bone,
            source_to_pmx,
            regions=regions,
            mouth_hidden_at_neutral=mouth_hidden_at_neutral,
        )
        if regions is None or not morphs:
            return morphs

        group = regions.group
        center = regions.center
        width, height, depth = regions.size
        by_name = {morph.name_en: morph for morph in morphs}

        edge_counts = Counter()
        skin_vertices = set()
        for face in mesh.faces:
            if face.group != group or not (face.material or "").endswith("__RACK_SKIN"):
                continue
            ids = [corner[0] for corner in face.corners]
            skin_vertices.update(ids)
            for index, first in enumerate(ids):
                second = ids[(index + 1) % len(ids)]
                edge_counts[tuple(sorted((first, second)))] += 1

        boundary = {
            vertex
            for edge, count in edge_counts.items()
            if count == 1
            for vertex in edge
        }
        front_boundary = frozenset(
            index
            for index in boundary
            if mesh.vertices[index][2] <= center[2] - 0.06 * depth
        )
        if not front_boundary:
            return morphs

        def clamp(value, limit):
            return max(-limit, min(limit, value))

        def nearest_distance2(point, points, radius_x, radius_y):
            rx = max(float(radius_x), 1e-6)
            ry = max(float(radius_y), 1e-6)
            return min(
                ((point[0] - other[0]) / rx) ** 2
                + ((point[1] - other[1]) / ry) ** 2
                for other in points
            )

        def replace_source_offsets(name, source_deltas):
            morph = by_name.get(name)
            if morph is None or not source_deltas:
                return
            replacement_pmx = {
                pmx_index
                for source_index in source_deltas
                for pmx_index in source_to_pmx.get((group, source_index), ())
            }
            if not replacement_pmx:
                return
            morph.offsets[:] = [
                (vertex_index, delta)
                for vertex_index, delta in morph.offsets
                if vertex_index not in replacement_pmx
            ]
            for source_index in sorted(source_deltas):
                delta = source_deltas[source_index]
                for pmx_index in source_to_pmx.get((group, source_index), ()):
                    morph.offsets.append((pmx_index, pmx._mmd_vec3(delta)))

        def eye_border(source, kind):
            if len(source) < 12:
                return {}
            points = [mesh.vertices[index] for index in source]
            xmid = sum(point[0] for point in points) / len(points)
            line = sum(point[1] for point in points) / len(points)
            xspan = max(max(point[0] for point in points) - min(point[0] for point in points), 1e-6)
            side = 1.0 if xmid >= center[0] else -1.0
            output = {}
            for index in front_boundary:
                point = mesh.vertices[index]
                if side * (point[0] - center[0]) < -0.02 * width:
                    continue
                distance2 = nearest_distance2(
                    point, points, 0.16 * width, 0.13 * height
                )
                if distance2 >= 1.0:
                    continue
                rel_y = point[1] - line
                rel_x = (point[0] - xmid) / xspan
                if kind == "blink":
                    dx = 0.0
                    # The visible socket border itself closes to the same line as the eye surface.
                    dy = line - point[1]
                    max_y = 0.16 * height
                elif kind == "wide":
                    dx = 0.0
                    dy = rel_y * 0.28
                    max_y = 0.055 * height
                elif kind == "half":
                    dx = 0.0
                    dy = (line - point[1]) * 0.78 if rel_y > 0.0 else 0.0
                    max_y = 0.090 * height
                elif kind == "happy":
                    arch = 0.022 * height * (1.0 - min(abs(rel_x) * 2.0, 1.0))
                    dx = 0.0
                    dy = (line + arch - point[1]) * 0.90
                    max_y = 0.105 * height
                else:
                    continue
                dy = clamp(dy, max_y)
                if max(abs(dx), abs(dy)) >= 1e-6:
                    output[index] = (dx, dy, 0.0)
            return output

        left_eye_driver = (
            regions.left_eye_surface
            if len(regions.left_eye_surface) >= 12 else regions.left_eye
        )
        right_eye_driver = (
            regions.right_eye_surface
            if len(regions.right_eye_surface) >= 12 else regions.right_eye
        )
        for name, source in (
            ("BlinkLeft", left_eye_driver),
            ("BlinkRight", right_eye_driver),
        ):
            replace_source_offsets(name, eye_border(source, "blink"))
        for source in (left_eye_driver, right_eye_driver):
            replace_source_offsets("Blink", eye_border(source, "blink"))
            replace_source_offsets("EyeWide", eye_border(source, "wide"))
            replace_source_offsets("HalfLid", eye_border(source, "half"))
            replace_source_offsets("HappyEyes", eye_border(source, "happy"))

        mouth_all = getattr(regions, "mouth_all", regions.mouth)
        mouth_surface = getattr(regions, "mouth_surface", frozenset())
        mouth_driver = mouth_surface if len(mouth_surface) >= 12 else mouth_all

        def mouth_border(kind):
            if len(mouth_driver) < 12:
                return {}
            points = [mesh.vertices[index] for index in mouth_driver]
            xmid = sum(point[0] for point in points) / len(points)
            line = sum(point[1] for point in points) / len(points)
            output = {}
            for index in front_boundary:
                point = mesh.vertices[index]
                if abs(point[0] - xmid) > 0.22 * width:
                    continue
                if abs(point[1] - line) > 0.12 * height:
                    continue
                distance2 = nearest_distance2(
                    point, points, 0.12 * width, 0.08 * height
                )
                if distance2 >= 1.0:
                    continue
                rel_x = point[0] - xmid
                sign_x = 1.0 if rel_x >= 0.0 else -1.0
                xnorm = min(abs(rel_x) / max(0.21 * width, 1e-6), 1.0)
                rel_y = point[1] - line
                if kind == "open":
                    dx = 0.0
                    dy = (
                        (-0.080 * height if rel_y <= 0.0 else 0.022 * height)
                        * (0.60 + 0.40 * min(abs(rel_y) / max(0.11 * height, 1e-6), 1.0))
                    )
                elif kind == "i":
                    dx = 0.028 * width * xnorm * sign_x
                    dy = -0.010 * height * (1.0 - xnorm)
                elif kind == "u":
                    dx = -0.038 * width * xnorm * sign_x
                    dy = -0.020 * height if rel_y <= 0.0 else 0.007 * height
                elif kind == "e":
                    dx = 0.021 * width * xnorm * sign_x
                    dy = -0.048 * height if rel_y <= 0.0 else 0.014 * height
                elif kind == "o":
                    dx = -0.025 * width * xnorm * sign_x
                    dy = -0.055 * height if rel_y <= 0.0 else 0.012 * height
                elif kind == "closed":
                    dx = 0.0
                    dy = (line - point[1]) * 0.90
                elif kind == "wide":
                    dx = 0.034 * width * xnorm * sign_x
                    dy = -0.006 * height
                elif kind == "smile":
                    # Lip-border corners spread and rise with the same visual motion as the mouth.
                    dx = 0.021 * width * xnorm * sign_x
                    dy = 0.060 * height * (xnorm ** 1.12)
                else:
                    continue
                dx = clamp(dx, 0.045 * width)
                dy = clamp(dy, 0.090 * height)
                if max(abs(dx), abs(dy)) >= 1e-6:
                    output[index] = (dx, dy, 0.0)
            return output

        for name, kind in (
            ("MouthOpen", "open"),
            ("MouthI", "i"),
            ("MouthU", "u"),
            ("MouthE", "e"),
            ("MouthO", "o"),
            ("MouthClosed", "closed"),
            ("MouthWide", "wide"),
            ("Smile", "smile"),
        ):
            replace_source_offsets(name, mouth_border(kind))

        return morphs

    pmx._reconstructed_face_morphs = boundary_face_morphs
