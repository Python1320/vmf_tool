#TODO: !!! render each plane of a solid within it's bounding box !!!
#TODO: custom format with .vmf export
#TODO: auto-saves & auto-version numbering (Alpha, Beta, sub-version & RC buttons)
#TODO: compilepal button
#TODO: preview cubemaps (load from .bsp copy in /maps)
#TODO: export to obj (one object per solid)
#TODO: obj import (each object is a solid)
#TODO: multiple 2D viewports
#------- totally customisable:
#------- position, size, ortho/perspective etc. (like blender)
#TODO: less hassle overlay copy & paste
#TODO: materials
#TODO: LIVE skybox & sun preview
#TODO: lighting preview
#TODO: displacement face copying (fusing brushes)
#TODO: render effects preview
#TODO: forest fill (prop family, density, falloff side, sort by tricount)
#TODO: blend modulate preview
#TODO: transparency & alpha sorting
#TODO: render modes (wireframe, flat, textured etc)
#TODO: settings that can be changed without restarting & SETTINGS FILES
#TODO: vpk browser
#TODO: script I/O (MvM Previews, including BOSS & TANK sizes)
#TODO: .nav viewer & editor, auto-generated I/O tracking
#TODO: output to addoutput and vice-versa (show AddOutputs in entity Outputs)
#TODO: brush group to .smd/.dmx (live model editing with Save-as)
#------- fast .vmt translation & .qc generation
#------- compile .mdl on next map compile
#TODO: motion previews (animation tools for brush objects)
#TODO: rulers (jump curves, rocket tracks)
#TODO: material proxy previews (animated .vmts)
#TODO: Twister-esque quick displacements / arches
#------- quick sattelite dish
#------- quick spiral staircase
#TODO: stairs with slope & step fields, like a blender modifier
#TODO: mirror team (flip or rotate)
#TODO: sightline spotter
#------- point out the longest and narrowest sightlines to a given point
#------- hardest to spot (lighting or size) should be prioritised
#TODO: quick gamemode (Ctrl+N Menu)
#TODO: better I/O autocomplete, copy & addoutput tools
#------- typed activator (check flags etc. to know what will/may trigger)
#TODO: displacement rounding with preserve edges optional
#TODO: lightmode (blender-like colour scheming with presets)
#TODO: displacement sculpt curve tools
#------- guide frames for displacements (NURBS OR point cloud)
#TODO: inner angle longer cone when adjusting light_spot (the area covered by the sharp edge should be obvious in the editor)
#TODO: better framerate
#TODO: load data from compiled .bsp (lightmaps etc.)
#TODO: ragdoll preview
import camera
import ctypes
import enum
import itertools
import numpy as np # for vertex buffers Numpy is needed (available through pip)
from OpenGL.GL import * # Installed via pip (PyOpenGl 3.1.0)
from OpenGL.GL.shaders import compileShader, compileProgram
from OpenGL.GLU import * # PyOpenGL-accelerate 3.1.0 requires MSVC 2015
# get precompiled binaries if you can, it's much less work
import physics
from sdl2 import * #Installed via pip (PySDL2 0.9.5)
# requires SDL2.dll (steam has a copy in it's main directory)
# and an Environment Variable (PYSDL2_DLL_PATH)
import time

import sys
sys.path.insert(0, '../../')
import vmf_tool
sys.path.insert(0, '../')
import vector
import solid_tool # must be loaded AFTER vmf_tool

class pivot(enum.Enum): # for selections of more than one brush / entity
    """like blender pivot point"""
    median = 0
    active = 1
    cursor = 2
    individual = 3


def draw_aabb(aabb):
    """"Precede with "glBegin(GL_QUADS)"\nExpects glPolygonMode to be GL_LINE"""
    glVertex(aabb.min.x, aabb.max.y, aabb.max.z)
    glVertex(aabb.max.x, aabb.max.y, aabb.max.z)
    glVertex(aabb.max.x, aabb.min.y, aabb.max.z)
    glVertex(aabb.min.x, aabb.min.y, aabb.max.z)

    glVertex(aabb.min.x, aabb.max.y, aabb.max.z)
    glVertex(aabb.max.x, aabb.max.y, aabb.max.z)
    glVertex(aabb.max.x, aabb.max.y, aabb.min.z)
    glVertex(aabb.min.x, aabb.max.y, aabb.min.z)

    glVertex(aabb.min.x, aabb.min.y, aabb.max.z)
    glVertex(aabb.max.x, aabb.min.y, aabb.max.z)
    glVertex(aabb.max.x, aabb.min.y, aabb.min.z)
    glVertex(aabb.min.x, aabb.min.y, aabb.min.z)

    glVertex(aabb.min.x, aabb.max.y, aabb.min.z)
    glVertex(aabb.max.x, aabb.max.y, aabb.min.z)
    glVertex(aabb.max.x, aabb.min.y, aabb.min.z)
    glVertex(aabb.min.x, aabb.min.y, aabb.min.z)


def loop_fan(vertices):
    out = vertices[:3]
    for vertex in vertices[3:]:
        out += [out[0], out[-1], vertex]
    return out


def loop_fan_indices(vertices, start_index):
    "polygon to triangle fan (indices only) by Exactol"
    indices = []
    for i in range(1, len(vertices) - 1):
        indices += [startIndex, startIndex + i, startIndex + i + 1]
    return indices


def main(vmf_path, width=1024, height=576):
    SDL_Init(SDL_INIT_VIDEO)
    window = SDL_CreateWindow(b'SDL2 OpenGL', SDL_WINDOWPOS_CENTERED,  SDL_WINDOWPOS_CENTERED, width, height, SDL_WINDOW_OPENGL | SDL_WINDOW_BORDERLESS)
    glContext = SDL_GL_CreateContext(window)
    SDL_GL_SetSwapInterval(0)
    glClearColor(0.1, 0.1, 0.1, 0.0)
    glColor(1, 1, 1)
    gluPerspective(90, width / height, 0.1, 4096 * 4)
##    glOrtho(-width / 4, width / 4, -height / 4, height / 4, 0.1, 8096)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_CULL_FACE)
    glFrontFace(GL_CW)
    glPointSize(4)

    start_import = time.time()
    imported_vmf = vmf_tool.namespace_from(open(vmf_path))
    if hasattr(imported_vmf.world, 'solid'):
        imported_vmf.world.solids = [imported_vmf.world.solid]
        del imported_vmf.world.solid
    if not hasattr(imported_vmf.world, 'solids'):
        imported_vmf.world['solids'] = []
    if hasattr(imported_vmf, 'entity'):
        imported_vmf.entities = [imported_vmf.entity]
        del imported_vmf.entity
    if not hasattr(imported_vmf, 'entities'):
        imported_vmf['entities'] = []

    global solid
    string_solids = []
    for brush in imported_vmf.world.solids:
        # bootleg auto-visgroup
        if not any([face.material == 'TOOLS/SKIP' or face.material == 'TOOLS/HINT' or 'CLIP' in face.material.upper() for face in brush.sides]):
##        if any([hasattr(face, 'dispinfo') for face in brush.sides]):
            string_solids.append(brush)
    for entity in imported_vmf.entities:
        if hasattr(entity, 'solid'):
            if isinstance(entity.solid, vmf_tool.namespace):
                string_solids.append(entity.solid)
        if hasattr(entity, 'solids'):
            if isinstance(entity.solids[0], vmf_tool.namespace):
                string_solids += entity.solids
                
    solids = []
    for brush in string_solids:
        try:
            solids.append(solid_tool.solid(brush))
        except Exception as exc:
            print(f"Invalid solid! (id {brush.id})")
            print(exc, '\n')
            raise exc

    brush_triangles = list(itertools.chain(*[s.triangles for s in solids]))

    offset_index_map = lambda B, O: [(S + O, L) for S, L in B.index_map]
    
    brush_index_map = [s.index_map for s in solids]

    # vertices, indices & draw_call map ((brush (faces, ...)), ...)
    # [brush[sides], ... ] TO:
    # vertices bytes,
    # indices bytes &
    # [(brush (start, len), side (start, len), ...), ...]
    # use compress sequence to assemble draw calls

##    # Vertex Shaders
##    shader_brush = compileShader(open('shaders/verts_brush.v', 'rb'), GL_VERTEX_SHADER)
##    ## shader_vert_displacement = compileShader(open('shaders/verts_displacement.v', 'rb'), GL_VERTEX_SHADER)
##    # Fragment Shaders
##    shader_flat_brush = compileShader(open('shaders/brush_flat.f', 'rb'), GL_FRAGMENT_SHADER)
##    ## shader_flat_displacement = compileShader(open('shaders/displacement_flat.f', 'rb'), GL_FRAGMENT_SHADER)
##    # Programs
##    program_flat_brush = compileProgram(shader_brush, shader_flat_brush)
##    ## program_flat_displacement = compileProgram(shader_displacement, shader_flat_displacement)
##    glLinkProgram(program_flat_brush)
##
##    # Vertex Buffer
##    VERTEX_BUFFER, INDEX_BUFFER = glGenBuffers(2)
##    glBindBuffer(GL_ARRAY_BUFFER, VERTEX_BUFFER)
##    glBufferData(GL_ARRAY_BUFFER, len(vertices) * 4, np.array(vertices, dtype=np.float32), GL_STATIC_DRAW)
##    # Index Buffer
##    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, INDEX_BUFFER)
##    glBufferData(GL_ELEMENT_ARRAY_BUFFER, len(indices) * 4, np.array(indices, dtype=np.uint32), GL_STATIC_DRAW)
##    # Vertex Format
##    glEnableVertexAttribArray(0) # vertex_position
##    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 40, GLvoidp(0))
##    glEnableVertexAttribArray(1) # vertex_normal
##    glVertexAttribPointer(1, 3, GL_FLOAT, GL_TRUE, 40, GLvoidp(12))
##    glEnableVertexAttribArray(2) # vertex_uv
##    glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, 40, GLvoidp(24))
##    glEnableVertexAttribArray(4) # editor_colour
##    glVertexAttribPointer(4, 3, GL_FLOAT, GL_FALSE, 40, GLvoidp(32))
##    # blend_alpha (displacement)
##    glVertexAttribPointer(5, 1, GL_FLOAT, GL_FALSE, 40, GLvoidp(12)) # replace vertex_normal
    
    print(f'{len(solids)} brushes loaded succesfully!')   
    print('import took {:.2f} seconds'.format(time.time() - start_import))

    CAMERA = camera.freecam(None, None, 128)
    render_solids = [s for s in solids if (s.center - CAMERA.position).sqrmagnitude() < 5120]
    rendered_ray = []

    SDL_SetRelativeMouseMode(SDL_TRUE)
    SDL_CaptureMouse(SDL_TRUE)

    mousepos = vector.vec2()
    keys = []

    tickrate = 1 / 0.015
    old_time = time.time()
    event = SDL_Event()
    while True:
        while SDL_PollEvent(ctypes.byref(event)) != 0:
            if event.type == SDL_QUIT or event.key.keysym.sym == SDLK_ESCAPE and event.type == SDL_KEYDOWN:
                SDL_GL_DeleteContext(glContext)
                SDL_DestroyWindow(window)
                SDL_Quit()
                return False
            if event.type == SDL_KEYDOWN:
                if event.key.keysym.sym not in keys:
                    keys.append(event.key.keysym.sym)
            if event.type == SDL_KEYUP:
                while event.key.keysym.sym in keys:
                    keys.remove(event.key.keysym.sym)
            if event.type == SDL_MOUSEBUTTONDOWN:
                keys.append(event.button.button)
            if event.type == SDL_MOUSEBUTTONUP:
                while event.button.button in keys:
                    keys.remove(event.button.button)
            if event.type == SDL_MOUSEMOTION:
                mousepos += vector.vec2(event.motion.xrel, event.motion.yrel)
                SDL_WarpMouseInWindow(window, width // 2, height // 2)
            if event.type == SDL_MOUSEWHEEL:
                CAMERA.speed += event.wheel.y * 32

        dt = time.time() - old_time
        while dt >= 1 / tickrate:
            CAMERA.update(mousepos, keys, 1 / tickrate)
            render_solids = [s for s in solids if (s.center - CAMERA.position).magnitude() < 2048]
            if SDLK_r in keys:
                CAMERA = camera.freecam(None, None, 128)
            if SDLK_BACKQUOTE in keys:
                print(CAMERA.position)
                print(len(render_solids))
            if SDL_BUTTON_LEFT in keys:
                ray_start = CAMERA.position
                ray_dir = vector.vec3(0, 1, 0).rotate(*-CAMERA.rotation)
                rendered_ray = [ray_start, ray_start + (ray_dir * 4096)]
                #calculate collisions
            dt -= 1 / tickrate
            old_time = time.time()

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glPushMatrix()
        CAMERA.set()

        # CENTER MARKER
        glLineWidth(1)
        glBegin(GL_LINES)
        glColor(1, 0, 0)
        glVertex(0, 0, 0)
        glVertex(128, 0, 0)
        glColor(0, 1, 0)
        glVertex(0, 0, 0)
        glVertex(0, 128, 0)
        glColor(0, 0, 1)
        glVertex(0, 0, 0)
        glVertex(0, 0, 128)
        glEnd()

        # RAYCAST
        glColor(1, .5, 0)
        glBegin(GL_LINES)
        for point in rendered_ray:
            glVertex(*point)
        glEnd()

        # GRID
##        glLineWidth(2)
##        glBegin(GL_LINES)
##        for x in range(-16, 17):
##            x = x * 64
##            glColor(1, 0 , 0)
##            glVertex(x, -1024, 0)
##            glColor(.25, .25, .25)
##            glVertex(x, 0, 0)
##            glVertex(x, 0, 0)
##            glColor(1, 0 , 0)
##            glVertex(x, 1024, 0)
##        for y in range(-16, 17):
##            y = y * 64
##            glColor(0, 1 , 0)
##            glVertex(-1024, y, 0)
##            glColor(.25, .25, .25)
##            glVertex(0, y, 0)
##            glVertex(0, y, 0)
##            glColor(0, 1 , 0)
##            glVertex(1024, y, 0)
##        glEnd()

        # SOLIDS
##        glColor(1, 1, 1)
##        glBegin(GL_TRIANGLES)
##        for vertex in brush_triangles:
##            glVertex(*vertex)
##        glEnd()
        
        glBegin(GL_TRIANGLES)
        for solid in render_solids:
            glColor(*solid.colour)
            for vertex in solid.triangles:
                glVertex(*vertex)
        glEnd()

        # BRUSH BOUNDING BOXES
        # be sure to turn off backface culling
##        glColor(1, 0, 0)
##        glPolygonMode(GL_FRONT, GL_LINE)
##        glBegin(GL_QUADS)
##        for solid in solids:
##            draw_aabb(solid.aabb)
##        glEnd()
##        glPolygonMode(GL_FRONT, GL_FILL)

        glPopMatrix()
        SDL_GL_SwapWindow(window)

if __name__ == '__main__':
    try:
##        main('../../mapsrc/test2.vmf')
        main('../../mapsrc/sdk_pl_goldrush.vmf')
##        main('../vmfs/hemisphere.vmf')
    except Exception as exc:
        SDL_Quit()
        raise exc
##    import sys
##    for file in sys.argv[1:]:
##        main(file)
