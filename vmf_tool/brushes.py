import itertools

from . import vector


def triangle_of(side):
    "extract triangle from string (returns 3 vec3)"
    triangle = [[float(i) for i in xyz.split()] for xyz in side.plane[1:-1].split(') (')]
    return tuple(map(vector.vec3, triangle))

def plane_of(A, B, C):
    """returns plane the triangle defined by A, B & C lies on"""
    normal = ((A - B) * (C - B)).normalise()
    return (normal, vector.dot(normal, A)) # normal (vec3), distance (float)

def clip(points, plane):
    """points is assumed to be a sorted loop of vertices"""
    normal, distance = plane
    split_verts = {"back": [], "front": []}
    for i, A in enumerate(points):
        B = poly[(i + 1) % len(points)]
        A_distance = vector.dot(normal, A) - distance
        B_distance = vector.dot(normal, B) - distance
        A_behind = round(A_distance, 6) < 0
        B_behind = round(B_distance, 6) < 0
        if A_behind:
            split_verts["back"].append(A)
        else: # A is in front of the clipping plane
            split_verts["front"].append(A)
        # does the edge AB intersect the clipping plane?
        if (A_behind and not B_behind) or (B_behind and not A_behind):
            t = A_distance / (A_distance - B_distance)
            cut_point = vector.lerp(A, B, t)
            cut_point = [round(a, 2) for a in cut_point]
            # .vmf floating-point accuracy sucks
            split_verts["back"].append(cut_point)
            split_verts["front"].append(cut_point)
    return split_verts

def loop_fan(vertices):
    "ploygon to triangle fan"
    out = vertices[:3]
    for vertex in vertices[3:]:
        out += [out[0], out[-1], vertex]
    return out

def loop_fan_indices(vertices):
    "polygon to triangle fan (indices only) by Exactol"
    indices = []
    for i in range(len(vertices) - 2):
        indices += [0, i + 1, i + 2]
    return indices


def disp_tris(verts, power): # copied from snake-biscuits/bsp_tool/bsp_tool.py
    """takes flat array of verts and arranges them in a patterned triangle grid
    expects verts to be an array of length ((2 ** power) + 1) ** 2"""
    power2 = 2 ** power
    power2A = power2 + 1
    power2B = power2 + 2
    power2C = power2 + 3
    tris = []
    for line in range(power2):
        line_offset = power2A * line
        for block in range(2 ** (power - 1)):
            offset = line_offset + 2 * block
            if line % 2 == 0: # |\|/|
                tris.append(verts[offset + 0])
                tris.append(verts[offset + power2A])
                tris.append(verts[offset + 1])

                tris.append(verts[offset + power2A])
                tris.append(verts[offset + power2B])
                tris.append(verts[offset + 1])

                tris.append(verts[offset + power2B])
                tris.append(verts[offset + power2C])
                tris.append(verts[offset + 1])

                tris.append(verts[offset + power2C])
                tris.append(verts[offset + 2])
                tris.append(verts[offset + 1])
            else: # |/|\|
                tris.append(verts[offset + 0])
                tris.append(verts[offset + power2A])
                tris.append(verts[offset + power2B])

                tris.append(verts[offset + 1])
                tris.append(verts[offset + 0])
                tris.append(verts[offset + power2B])

                tris.append(verts[offset + 2])
                tris.append(verts[offset + 1])
                tris.append(verts[offset + power2B])

                tris.append(verts[offset + power2C])
                tris.append(verts[offset + 2])
                tris.append(verts[offset + power2B])
    return tris


def square_neighbours(x, y, edge_length): # edge_length = (2^power) + 1
    """yields the indicies of neighbouring points in a displacement"""
    for i in range(x - 1, x + 2):
        if i >= 0 and i < edge_length:
            for j in range(y - 1, y + 2):
                if j >= 0 and j < edge_length:
                    if not (i != x and j != y):
                        yield i * edge_length + j



class solid:
    __slots__ = ('aabb', 'center', 'colour', 'displacement_vertices', 'faces',
                 'id', 'index_map', 'indices', 'is_displacement', 'planes',
                 'planes', 'source', 'string_triangles', 'vertices')

    def __init__(self, solid_namespace): # THIS IS FOR IMPORTING FROM VMF
        """Initialise from namespace"""
        self.source = solid_namespace # preserve (for debug & accuracy)
        self.id = int(self.source.id)
        self.colour = tuple(int(x) / 255 for x in solid_namespace.editor.color.split())
        string_tris = [triangle_of(s) for s in solid_namespace.sides]
        self.planes = [plane_of(*t) for t in string_tris]
        self.is_displacement = False

        self.faces = []
        for i, plane in enumerate(self.planes):
            normal, distance = plane
            non_parallel = vector.vec3(z=-1) if abs(normal.z) != 1 else vector.vec3(y=-1)
            local_y = (non_parallel * normal).normalise()
            local_x = (local_y * normal).normalise()
            base = normal * distance
            center = sum(string_tris[i], vector.vec3()) / 3
            # ^ centered on string triangle, but rounding errors abound ^
            radius = 10 ** 4 # larger than any reasonable brush
            ngon = [center + ((-local_x + local_y) * radius),
                             center + ((local_x + local_y) * radius),
                             center + ((local_x + -local_y) * radius),
                             center + ((-local_x + -local_y) * radius)]
            for other_plane in self.planes:
                if other_plane == plane or plane[0] == -other_plane[0]:
                    continue
                ngon, offcut = clip(ngon, other_plane).values() # back, front
            self.faces.append(ngon)

        # OpenGL VERTEX_BUFFER & INDEX_BUFFER
        self.indices = []
        self.vertices = [] # [((position), (normal), (uv), (colour)), ...]
        # ^ except it's flat thanks to itertools.chain
        self.index_map = []
        uvs = {} # side: [(u, v), ...]
        side_index = 0
        start_index = 0
        for face, side, plane in zip(self.faces, self.source.sides, self.planes):
            face_indices = []
            normal = plane[0]
            u_axis = side.uaxis.rpartition(' ')[0::2]
            u_vector = [float(x) for x in u_axis[0][1:-1].split()]
            u_scale = float(u_axis[1])
            v_axis = side.vaxis.rpartition(' ')[0::2]
            v_vector = [float(x) for x in v_axis[0][1:-1].split()]
            v_scale = float(v_axis[1])
            uvs[side_index] = []
            for i, vertex in enumerate(face): # regex might help here
                uv = [vector.dot(vertex, u_vector[:3]) + u_vector[-1],
                      vector.dot(vertex, v_vector[:3]) + v_vector[-1]]
                uv[0] /= u_scale
                uv[1] /= v_scale
                uvs[side_index].append(uv)

                assembled_vertex = tuple(itertools.chain(vertex, normal, uv, self.colour))
                if assembled_vertex not in self.vertices:
                    self.vertices.append(assembled_vertex)
                    face_indices.append(len(self.vertices) - 1)
                else:
                    face_indices.append(self.vertices.index(assembled_vertex))

            side_index += 1
            face_indices = loop_fan(face_indices)
            self.index_map.append((start_index, len(face_indices)))
            self.indices += face_indices
            start_index += len(face_indices)

        # DISPLACEMENTS
        global square_neighbours
        self.displacement_vertices = {} # {side_index: vertices}
        for i, side in enumerate(self.source.sides):
            if hasattr(side, "dispinfo"):
                self.source.sides[i].blend_colour = [1 - i for i in self.colour]
                self.is_displacement = True
                power = int(side.dispinfo.power)
                power2 = 2 ** power
                quad = tuple(vector.vec3(x) for x in self.faces[i])
                if len(quad) != 4:
                    raise RuntimeError("displacement brush id {} side id {} has {} sides!".format(self.id, side.id, len(quad)))
                quad_uvs = tuple(vector.vec2(x) for x in uvs[i])
                disp_uvs = [] # barymetric uvs for each baryvert
                start = vector.vec3(*map(float, side.dispinfo.startposition[1:-1].split()))
                if start not in quad:
                    start = sorted(quad, key=lambda P: (start - P).magnitude())[0]
                index = quad.index(start) - 1
                quad = quad[index:] + quad[:index]
                quad_uvs = quad_uvs[index:] + quad_uvs[:index]
                side_dispverts = []
                A, B, C, D = quad
                DA = D - A
                CB = C - B
                Auv, Buv, Cuv, Duv = quad_uvs
                DAuv = Duv - Auv
                CBuv = Cuv - Buv
                distance_rows = [v for k, v in side.dispinfo.distances.__dict__.items() if k != "_line"] # skip line number
                normal_rows = [v for k, v in side.dispinfo.normals.__dict__.items() if k != "_line"]
                for y, distance_row, normals_row in zip(itertools.count(), distance_rows, normal_rows):
                    distance_row = [float(x) for x in distance_row.split()]
                    normals_row = [*map(float, normals_row.split())]
                    left_vert = A + (DA * y / power2)
                    left_uv = Auv + (DAuv * y / power2)
                    right_vert = B + (CB * y / power2)
                    right_uv = Buv + (CBuv * y / power2)
                    for x, distance in enumerate(distance_row):
                        k = x * 3 # index
                        normal = vector.vec3(normals_row[k], normals_row[k + 1], normals_row[k + 2])
                        baryvert = vector.lerp(right_vert, left_vert, x / power2)
                        disp_uvs.append(vector.lerp(right_uv, left_uv, x / power2))
                        side_dispverts.append(vector.vec3(baryvert) + (distance * normal))

                # calculate displacement normals
                normals = []
                for x in range(power2 + 1):
                    for y in range(power2 + 1):
                        dispvert = side_dispverts[x * (power2 + 1) + y]
                        neighbour_indices = square_neighbours(x, y, power2 + 1)
                        try:
                            neighbours = [side_dispverts[i] for i in neighbour_indices]
                        except Exception as exc:
                            # f"({x}, {y}) {list(square_neighbours(x, y, power2 + 1))=}") # python 3.8
                            print("({}, {}) {}".format(x, y, list(square_neighbours(x, y, power2 + 1))))
                            print(exc) # raise traceback instead
                        normal = vector.vec3(0, 0, 1)
                        if len(neighbours) != 0:
                            normal -= dispvert - sum(neighbours, vector.vec3()) / len(neighbours)
                            normal = normal.normalise()
                        normals.append(normal)

                self.displacement_vertices[i] = []
                alpha_rows = [v for k, v in side.dispinfo.alphas.__dict__.items() if k != "_line"]
                alphas = [float(a) for row in alpha_rows for a in row.split()]
                for pos, alpha, uv in zip(side_dispverts, alphas, disp_uvs):
                    assembled_vertex = tuple(itertools.chain(pos, [alpha, 0.0, 0.0], uv, self.colour))
                    self.displacement_vertices[i].append(assembled_vertex)

        if not self.is_displacement:
            del self.displacement_vertices
            

    def __repr__(self):
        return f"<solid {len(self.vertices)} vertices>"