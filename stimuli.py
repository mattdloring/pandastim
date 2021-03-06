"""
pandastim/stimuli.py
Classes to present visual stimuli in pandastim (subclasses of ShowBase, which 
implements the main event loop in panda3d).

Part of pandastim package: https://github.com/EricThomson/pandastim
"""
from pandastim import utils

import sys
import numpy as np
import logging
import threading as tr
import time

from direct.showbase.ShowBase import ShowBase
from direct.showbase import ShowBaseGlobal  # global vars defined by p3d
from direct.task import Task
from direct.gui.OnscreenText import OnscreenText  # for binocular stim

from panda3d.core import Texture, CardMaker, TextureStage, WindowProperties, ColorBlendAttrib, TransformState, \
    ClockObject, PerspectiveLens, AntialiasAttrib, PStatClient, Shader

from datetime import datetime

# Set up a logger
log_level = logging.INFO
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # because annoying reasons
if not logger.hasHandlers():
    log_handler = logging.StreamHandler(sys.stdout)
    log_handler.setLevel(log_level)
    logger.addHandler(log_handler)


class TexMoving(ShowBase):
    """
    Shows single texture drifting across the window at specified velocity and angle.
    
    Usage:
        tex = SinGreyTex()
        stim_show = ShowTexMoving(tex, angle = 30, velocity = 0.1, fps = 40, profile_on = True)
        stim_show.run()
        
    Note(s):
        Positive angles are clockwise, negative ccw.
        Velocity is normalized to window size, so 1.0 is the entire window width (i.e., super-fast).
    """

    def __init__(self, tex, angle=0, velocity=0.1, fps=30,
                 window_name="ShowTexMoving", window_size=None, profile_on=False):
        super().__init__()
        self.tex = tex
        if window_size is None:
            self.window_size = self.tex.texture_size
        else:
            self.window_size = window_size
        self.angle = angle
        self.velocity = velocity
        self.texture_stage = TextureStage("texture_stage")
        self.window_name = window_name

        # Set frame rate (fps)
        ShowBaseGlobal.globalClock.setMode(ClockObject.MLimited)
        ShowBaseGlobal.globalClock.setFrameRate(fps)

        # Set up profiling if desired
        if profile_on:
            PStatClient.connect()  # this will only work if pstats is running: see readme
            ShowBaseGlobal.base.setFrameRateMeter(True)  # Show frame rate
            self.center_indicator = None

        # Window properties set up
        self.window_properties = WindowProperties()
        self.window_properties.setSize(self.window_size, self.window_size)
        self.window_properties.setTitle(window_name)
        ShowBaseGlobal.base.win.requestProperties(self.window_properties)

        # Create scenegraph, attach stimulus to card.
        cm = CardMaker('card')
        cm.setFrameFullscreenQuad()
        self.card = self.aspect2d.attachNewNode(cm.generate())
        # Scale is so it can handle arbitrary rotations and shifts in binocular case
        self.card.setScale(np.sqrt(8))
        self.card.setColor((1, 1, 1, 1))  # makes it bright when bright (default combination with card is add)
        self.card.setTexture(self.texture_stage, self.tex.texture)
        self.card.setTexRotate(self.texture_stage, self.angle)

        if self.velocity != 0:
            # Add task to taskmgr to translate texture
            self.taskMgr.add(self.moveTextureTask, "moveTextureTask")

    # Task for moving the texture
    def moveTextureTask(self, task):
        new_position = -task.time * self.velocity
        self.card.setTexPos(self.texture_stage, new_position, 0, 0)  # u, v, w
        return Task.cont


class TexFixed(TexMoving):
    """
    Presents single texture without any motion. Useful for debugging: no need to set fps high.
    
    Usage:
        tex = SinGreyTex()
        stim_show = ShowTexStatic(tex, fps = 10, profile_on = True)
        stim_show.run()
    """

    def __init__(self, tex, angle=0, fps=30, window_size=None,
                 window_name="ShowTexStatic", profile_on=False):
        super().__init__(tex, angle=angle, velocity=0,
                         fps=fps, window_size=window_size,
                         profile_on=profile_on, window_name=window_name)
        self.window_properties.setTitle(self.window_name)
        ShowBaseGlobal.base.win.requestProperties(self.window_properties)


class InputControlParams(ShowBase):
    """
    Input signal sends in x, y, theta values for binocular stimuli to control
    those parameters of the stim in real time. Need to expand to single texture.

    Usage:
        InputControlParams(texture_object,
                        stim_angles = (0, 0),
                        strip_angle = 0,
                        position = (0,0),
                        velocities = (0,0),
                        strip_width = 2,
                        window_size = 512,
                        window_name = 'FunStim',
                        profile_on  = False)

    Note(s):
        - angles are relative to strip angle
        - position is x,y in card-based coordinates (from [-1 1]), so (.5, .5) will be in middle of top right quadrant
        - Velocity is in same direction as angle, and units of window size (so 1 is super-fast)
        - strip_width is just the width of the strip down the middle. Can be 0.
    """

    def __init__(self, tex, stim_angles=(0, 0), initial_angle=0, initial_position=(0, 0),
                 velocities=(0, 0), strip_width=4, fps=30, window_size=None,
                 window_name='position control', profile_on=False, save_path=None):
        super().__init__()
        self.render.setAntialias(AntialiasAttrib.MMultisample)
        self.aspect2d.prepareScene(ShowBaseGlobal.base.win.getGsg())  # pre-loads world
        self.tex = tex
        if window_size == None:
            self.window_size = tex.texture_size
        else:
            self.window_size = window_size
        self.mask_position_card = initial_position
        self.strip_width = strip_width
        self.scale = np.sqrt(8)  # so it can handle arbitrary rotations and shifts
        self.strip_angle = initial_angle  # this will change fairly frequently
        self.stim_angles = stim_angles
        self.left_texture_angle = self.stim_angles[0] + self.strip_angle  # make this a property
        self.right_texture_angle = self.stim_angles[1] + self.strip_angle
        self.left_velocity = velocities[0]
        self.right_velocity = velocities[1]
        self.fps = fps
        self.window_name = window_name
        self.profile_on = profile_on
        print(save_path)
        self.save_path = save_path
        if self.save_path:
            initial_params = {'angles': stim_angles, 'initial_angle': self.strip_angle,
                              'velocities': velocities, 'strip_width': self.strip_width,
                              'initial_position': initial_position}
            print(tex, initial_params)
            self.filestream = utils.save_initialize(self.save_path, [tex], [initial_params])
            print(self.filestream)
        else:
            self.filestream = None

            # Set window title and size
        self.window_properties = WindowProperties()
        self.window_properties.setSize(self.window_size, self.window_size)
        self.window_properties.setTitle(self.window_name)
        ShowBaseGlobal.base.win.requestProperties(self.window_properties)  # base is a panda3d global

        # Set frame rate
        ShowBaseGlobal.globalClock.setMode(ClockObject.MLimited)
        ShowBaseGlobal.globalClock.setFrameRate(self.fps)  # can lock this at whatever

        # CREATE MASK ARRAYS
        self.left_mask_array = 255 * np.ones((self.tex.texture_size, self.tex.texture_size), dtype=np.uint8)
        self.left_mask_array[:, self.tex.texture_size // 2 - self.strip_width // 2:] = 0
        self.right_mask_array = 255 * np.ones((self.tex.texture_size, self.tex.texture_size), dtype=np.uint8)
        self.right_mask_array[:, : self.tex.texture_size // 2 + self.strip_width // 2] = 0

        # TEXTURE STAGES FOR LEFT CARD
        self.left_texture_stage = TextureStage('left_texture_stage')
        # Mask
        self.left_mask = Texture("left_mask_texture")
        self.left_mask.setup2dTexture(self.tex.texture_size, self.tex.texture_size,
                                      Texture.T_unsigned_byte, Texture.F_luminance)
        self.left_mask.setRamImage(self.left_mask_array)
        self.left_mask_stage = TextureStage('left_mask_array')
        # Multiply the texture stages together
        self.left_mask_stage.setCombineRgb(TextureStage.CMModulate,
                                           TextureStage.CSTexture,
                                           TextureStage.COSrcColor,
                                           TextureStage.CSPrevious,
                                           TextureStage.COSrcColor)

        # TEXTURE STAGES FOR RIGHT CARD
        self.right_texture_stage = TextureStage('right_texture_stage')
        # Mask
        self.right_mask = Texture("right_mask_texture")
        self.right_mask.setup2dTexture(self.tex.texture_size, self.tex.texture_size,
                                       Texture.T_unsigned_byte, Texture.F_luminance)
        self.right_mask.setRamImage(self.right_mask_array)
        self.right_mask_stage = TextureStage('right_mask_stage')
        # Multiply the texture stages together
        self.right_mask_stage.setCombineRgb(TextureStage.CMModulate,
                                            TextureStage.CSTexture,
                                            TextureStage.COSrcColor,
                                            TextureStage.CSPrevious,
                                            TextureStage.COSrcColor)

        # CREATE CARDS/SCENEGRAPH
        cm = CardMaker('stimcard')
        cm.setFrameFullscreenQuad()
        # self.setBackgroundColor((0,0,0,1))
        self.left_card = self.aspect2d.attachNewNode(cm.generate())
        self.right_card = self.aspect2d.attachNewNode(cm.generate())
        self.left_card.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))
        self.right_card.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))

        # ADD TEXTURE STAGES TO CARDS
        self.left_card.setTexture(self.left_texture_stage, self.tex.texture)
        self.left_card.setTexture(self.left_mask_stage, self.left_mask)
        self.right_card.setTexture(self.right_texture_stage, self.tex.texture)
        self.right_card.setTexture(self.right_mask_stage, self.right_mask)
        self.setBackgroundColor((0, 0, 0, 1))  # without this the cards will appear washed out
        # self.left_card.setAntialias(AntialiasAttrib.MMultisample)
        # self.right_card.setAntialias(AntialiasAttrib.MMultisample)
        # TRANSFORMS
        # Masks
        self.mask_transform = self.trs_transform()
        self.left_card.setTexTransform(self.left_mask_stage, self.mask_transform)
        self.right_card.setTexTransform(self.right_mask_stage, self.mask_transform)

        # Textures
        # Left
        self.left_card.setTexScale(self.left_texture_stage, 1 / self.scale)
        self.left_card.setTexRotate(self.left_texture_stage, self.left_texture_angle)
        # Right 
        self.right_card.setTexScale(self.right_texture_stage, 1 / self.scale)
        self.right_card.setTexRotate(self.right_texture_stage, self.right_texture_angle)

        # Set task manager(s) for textures
        if self.left_velocity != 0 and self.right_velocity != 0:
            self.taskMgr.add(self.textures_update, "move_both")
        elif self.left_velocity != 0 and self.right_velocity == 0:
            self.taskMgr.add(self.left_texture_update, "move_left")
        elif self.left_velocity == 0 and self.right_velocity != 0:
            self.taskMgr.add(self.right_texture_update, "move_right")

        # Event handler to process the messages
        self.accept("stim", self.process_stim, [])

        # Set up profiling if desired
        if profile_on:
            PStatClient.connect()  # this will only work if pstats is running
            ShowBaseGlobal.base.setFrameRateMeter(True)  # Show frame rate

    @property
    def mask_position_uv(self):
        return (utils.card2uv(self.mask_position_card[0]),
                utils.card2uv(self.mask_position_card[1]))

    def process_stim(self, x, y, theta):
        """
        Event handler method for processing message about current x,y, theta
        """
        # If new values are same as previous, return to caller. Otherwise, reset
        if (self.strip_angle, self.mask_position_card) == (theta, (x, y)):
            return
        else:
            self.strip_angle = theta
            self.right_texture_angle = self.stim_angles[1] + self.strip_angle
            self.left_texture_angle = self.stim_angles[0] + self.strip_angle
            # print(self.strip_angle, self.left_texture_angle, self.right_texture_angle)
            self.mask_position_card = (x, y)
            self.mask_transform = self.trs_transform()
            self.left_card.setTexTransform(self.left_mask_stage, self.mask_transform)
            self.right_card.setTexTransform(self.right_mask_stage, self.mask_transform)
            self.left_card.setTexRotate(self.left_texture_stage, self.left_texture_angle)
            self.right_card.setTexRotate(self.right_texture_stage, self.right_texture_angle)

        if self.filestream:
            self.filestream.write(f"{str(datetime.now())}\t{x}\t{y}\t{theta}\n")
            self.filestream.flush()
            return

    # Move both textures
    def textures_update(self, task):
        left_tex_position = -task.time * self.left_velocity  # negative b/c texture stage
        right_tex_position = -task.time * self.right_velocity
        self.left_card.setTexPos(self.left_texture_stage, left_tex_position, 0, 0)
        self.right_card.setTexPos(self.right_texture_stage, right_tex_position, 0, 0)
        return task.cont

    def left_texture_update(self, task):
        left_tex_position = -task.time * self.left_velocity  # negative b/c texture stage
        self.left_card.setTexPos(self.left_texture_stage, left_tex_position, 0, 0)
        return task.cont

    def right_texture_update(self, task):
        right_tex_position = -task.time * self.right_velocity
        self.right_card.setTexPos(self.right_texture_stage, right_tex_position, 0, 0)
        return task.cont

    def trs_transform(self):
        """ 
        trs = translate rotate scale transform for mask stage
        rdb contributed to this code
        """
        # print(self.strip_angle)
        pos = 0.5 + self.mask_position_uv[0], 0.5 + self.mask_position_uv[1]
        center_shift = TransformState.make_pos2d((-pos[0], -pos[1]))
        scale = TransformState.make_scale2d(1 / self.scale)
        rotate = TransformState.make_rotate2d(self.strip_angle)
        translate = TransformState.make_pos2d((0.5, 0.5))
        return translate.compose(rotate.compose(scale.compose(center_shift)))


class BinocularMoving(ShowBase):
    """
    Show binocular drifting textures forever.
    Takes in texture object and other parameters, and shows texture drifting indefinitely.

    Usage:
        BinocularDrift(texture_object,
                        stim_angles = (0, 0),
                        strip_angle = 0,
                        position = (0,0),
                        velocities = (0,0),
                        strip_width = 2,
                        window_size = 512,
                        window_name = 'FunStim',
                        profile_on  = False)

    Note(s):
        - angles are (left_texture_angle, right_texture_angle): >0 is cw, <0 ccw
        - Make texture_size a power of 2: this makes the GPU happier.
        - position is x,y in card-based coordinates (from [-1 1]), so (.5, .5) will be in middle of top right quadrant
        - Velocity is in card-based units, so 1.0 is the entire window width (i.e., super-fast).
        - strip_width is just the width of the strip down the middle. It can be 0. Even is better.
        - The texture array can be 2d (gray) or NxNx3 (rgb) with unit8 or uint16 elements.
    """

    def __init__(self, tex, stim_angles=(0, 0), strip_angle=0, position=(0, 0),
                 velocities=(0, 0), strip_width=4, fps=30, window_size=None,
                 window_name='BinocularDrift', profile_on=False):
        super().__init__()
        self.tex = tex
        if window_size == None:
            self.window_size = tex.texture_size
        else:
            self.window_size = window_size
        self.mask_position_card = position
        self.mask_position_uv = (utils.card2uv(self.mask_position_card[0]),
                                 utils.card2uv(self.mask_position_card[1]))
        self.scale = np.sqrt(8)  # so it can handle arbitrary rotations and shifts
        self.left_texture_angle = stim_angles[0]
        self.right_texture_angle = stim_angles[1]
        self.left_velocity = velocities[0]
        self.right_velocity = velocities[1]
        self.strip_angle = strip_angle  # this will change fairly frequently
        self.fps = fps
        self.window_name = window_name
        self.profile_on = profile_on

        # Set window title and size
        self.window_properties = WindowProperties()
        self.window_properties.setSize(self.window_size, self.window_size)
        self.window_properties.setTitle(self.window_name)
        ShowBaseGlobal.base.win.requestProperties(self.window_properties)  # base is a panda3d global

        # CREATE MASK ARRAYS
        self.left_mask_array = 255 * np.ones((self.tex.texture_size, self.tex.texture_size), dtype=np.uint8)
        self.left_mask_array[:, self.tex.texture_size // 2 - strip_width // 2:] = 0
        self.right_mask_array = 255 * np.ones((self.tex.texture_size, self.tex.texture_size), dtype=np.uint8)
        self.right_mask_array[:, : self.tex.texture_size // 2 + strip_width // 2] = 0

        # TEXTURE STAGES FOR LEFT CARD
        self.left_texture_stage = TextureStage('left_texture_stage')
        # Mask
        self.left_mask = Texture("left_mask_texture")
        self.left_mask.setup2dTexture(self.tex.texture_size, self.tex.texture_size,
                                      Texture.T_unsigned_byte, Texture.F_luminance)
        self.left_mask.setRamImage(self.left_mask_array)
        self.left_mask_stage = TextureStage('left_mask_array')
        # Multiply the texture stages together
        self.left_mask_stage.setCombineRgb(TextureStage.CMModulate,
                                           TextureStage.CSTexture,
                                           TextureStage.COSrcColor,
                                           TextureStage.CSPrevious,
                                           TextureStage.COSrcColor)

        # TEXTURE STAGES FOR RIGHT CARD
        self.right_texture_stage = TextureStage('right_texture_stage')
        # Mask
        self.right_mask = Texture("right_mask_texture")
        self.right_mask.setup2dTexture(self.tex.texture_size, self.tex.texture_size,
                                       Texture.T_unsigned_byte, Texture.F_luminance)
        self.right_mask.setRamImage(self.right_mask_array)
        self.right_mask_stage = TextureStage('right_mask_stage')
        # Multiply the texture stages together
        self.right_mask_stage.setCombineRgb(TextureStage.CMModulate,
                                            TextureStage.CSTexture,
                                            TextureStage.COSrcColor,
                                            TextureStage.CSPrevious,
                                            TextureStage.COSrcColor)

        # CREATE CARDS/SCENEGRAPH
        cm = CardMaker('stimcard')
        cm.setFrameFullscreenQuad()
        # self.setBackgroundColor((0,0,0,1))
        self.left_card = self.aspect2d.attachNewNode(cm.generate())
        self.right_card = self.aspect2d.attachNewNode(cm.generate())
        self.left_card.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))
        self.right_card.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))

        # ADD TEXTURE STAGES TO CARDS
        self.left_card.setTexture(self.left_texture_stage, self.tex.texture)
        self.left_card.setTexture(self.left_mask_stage, self.left_mask)
        self.right_card.setTexture(self.right_texture_stage, self.tex.texture)
        self.right_card.setTexture(self.right_mask_stage, self.right_mask)
        self.setBackgroundColor((0, 0, 0, 1))  # without this the cards will appear washed out

        # TRANSFORMS
        # Masks
        self.mask_transform = self.trs_transform()
        self.left_card.setTexTransform(self.left_mask_stage, self.mask_transform)
        self.right_card.setTexTransform(self.right_mask_stage, self.mask_transform)
        # Left texture
        self.left_card.setTexScale(self.left_texture_stage, 1 / self.scale)
        self.left_card.setTexRotate(self.left_texture_stage, self.left_texture_angle)
        # Right texture
        self.right_card.setTexScale(self.right_texture_stage, 1 / self.scale)
        self.right_card.setTexRotate(self.right_texture_stage, self.right_texture_angle)

        # Set dynamic transforms
        if self.left_velocity != 0 and self.right_velocity != 0:
            self.taskMgr.add(self.textures_update, "move_both")
        elif self.left_velocity != 0 and self.right_velocity == 0:
            self.taskMgr.add(self.left_texture_update, "move_left")
        elif self.left_velocity == 0 and self.right_velocity != 0:
            self.taskMgr.add(self.right_texture_update, "move_right")

        # Set frame rate
        ShowBaseGlobal.globalClock.setMode(ClockObject.MLimited)
        ShowBaseGlobal.globalClock.setFrameRate(self.fps)  # can lock this at whatever

        # Set up profiling if desired
        if profile_on:
            PStatClient.connect()  # this will only work if pstats is running
            ShowBaseGlobal.base.setFrameRateMeter(True)  # Show frame rate
            # Following will show a small x at the center
            self.title = OnscreenText("x",
                                      style=1,
                                      fg=(1, 1, 1, 1),
                                      bg=(0, 0, 0, .8),
                                      pos=self.mask_position_card,
                                      scale=0.05)

    # Move both textures
    def textures_update(self, task):
        left_tex_position = -task.time * self.left_velocity  # negative b/c texture stage
        right_tex_position = -task.time * self.right_velocity
        self.left_card.setTexPos(self.left_texture_stage, left_tex_position, 0, 0)
        self.right_card.setTexPos(self.right_texture_stage, right_tex_position, 0, 0)
        return task.cont

    def left_texture_update(self, task):
        left_tex_position = -task.time * self.left_velocity  # negative b/c texture stage
        self.left_card.setTexPos(self.left_texture_stage, left_tex_position, 0, 0)
        return task.cont

    def right_texture_update(self, task):
        right_tex_position = -task.time * self.right_velocity
        self.right_card.setTexPos(self.right_texture_stage, right_tex_position, 0, 0)
        return task.cont

    def trs_transform(self):
        """ 
        trs = translate rotate scale transform for mask stage
        rdb contributed to this code
        """
        pos = 0.5 + self.mask_position_uv[0], 0.5 + self.mask_position_uv[1]
        center_shift = TransformState.make_pos2d((-pos[0], -pos[1]))
        scale = TransformState.make_scale2d(1 / self.scale)
        rotate = TransformState.make_rotate2d(self.strip_angle)
        translate = TransformState.make_pos2d((0.5, 0.5))
        return translate.compose(rotate.compose(scale.compose(center_shift)))


class BinocularFixed(BinocularMoving):
    """
    Presents binocular stim class without any motion.
    Most useful for testing stimuli. Obviously no need to set fps high.
    """

    def __init__(self, stim, stim_angles=(0, 0), strip_angle=0,
                 position=(0, 0), strip_width=4, fps=30,
                 window_size=None, window_name=None, profile_on=False):
        super().__init__(stim, stim_angles=stim_angles, velocities=(0, 0),
                         strip_angle=strip_angle, strip_width=strip_width,
                         position=position, fps=fps, window_size=window_size,
                         profile_on=profile_on, window_name=window_name)
        self.window_properties.setTitle("BinocularStatic")
        ShowBaseGlobal.base.win.requestProperties(self.window_properties)


class OpenLoopStim(ShowBase):
    """
    Takes in stimuli dataframe, as well as list of values/durations to show
    different stimuli. 
    
    Stimulation class for open-loop experiments, such as under the microscope
    Runs entirely autonomously -- could optionally be hooked to a go stimulus (from zmq or other)

    Stimulus as DataFrame formatted:

    stim_type:
            'b' - binocular textures
            's' - whole field textures
            'rdk' - random dot motion

    angle: singular for whole field and random dot, (left, right) for binocular
    velocity: singular for whole field and random dot, (left, right) for binocular
    texture: singular for whole field, ignored for random dot, (left, right) for binocular

    duration: total length of stimuli (seconds)
    stationary_time: length of time before motion begins
        (e.g., duration:10, stationary_time:6 = 6 seconds static, 4 seconds motion before advancing stimulus)



    """
    pass


class ClosedLoopStimChoice(ShowBase):
    """
    closed loop stimuli

    this version only updates when told to do so

    stimuli contains possible stim choices
    """

    def __init__(self, textures, def_freq=32, def_center_width=16, scale=8, fps=75, save_path=None,
                 window_size=None, win_pos=(0, 0), window_name='Pandastim',
                 fish_id=None, fish_age=None, profile_on=False, gui=False):

        super().__init__()

        self.textures = textures

        self.scale = np.sqrt(scale)
        self.fps = fps
        ShowBaseGlobal.globalClock.setMode(ClockObject.MLimited)
        ShowBaseGlobal.globalClock.setFrameRate(self.fps)

        self.profileOn = profile_on
        if self.profileOn:
            PStatClient.connect()  # this will only work if pstats is running
            ShowBaseGlobal.base.setFrameRateMeter(True)

        # set up saving
        if save_path:
            self.filestream = utils.updated_saving(save_path, fish_id, fish_age)
        else:
            self.filestream = None

        if window_size is None:
            self.windowSize = (1024, 1024)
        else:
            self.windowSize = window_size

        self.windowProps = WindowProperties()
        self.windowName = window_name
        self.windowProps.setTitle(self.windowName)
        self.windowProps.setSize(self.windowSize)
        if not gui:
            self.windowProps.set_undecorated(True)
            self.disable_mouse()
            self.windowProps.set_foreground(True)
            self.windowProps.set_origin(self.window_position)
            self.window_position = win_pos
        if gui:
            self.windowProps.set_origin((600, 600))

        ShowBaseGlobal.base.win.requestProperties(self.windowProps)  # base is panda3d

        self.default_freq = def_freq
        self.default_center_width = def_center_width

        self.rotation_offset = 0
        self.strip_angle = 0
        self.center_x = 0
        self.center_y = 0

        self.curr_id = 0

        self.set_stimulus(None)
        self.taskMgr.add(self.move_textures, "move textures")

        self.accept("stimulus", self.set_stimulus, [])

    def set_stimulus(self, stimulus):
        self.clear_cards()

        print(stimulus)
        self._stat_finish = True
        self._max_finish = True

        if stimulus is None or not 'stim_type' in stimulus:
            self.current_stimulus = {'stim_type': 's', 'velocity': 0, 'angle': 0, 'texture': self.textures['blank']}
            print('defaulting to blank')
        elif stimulus['stim_type'] == 'blank':
            self.current_stimulus = {'stim_type': 's', 'velocity': 0, 'angle': 0, 'texture': self.textures['blank']}
        elif stimulus['stim_type'] == 's':
            self.current_stimulus = stimulus
            try:
                self.current_stimulus['texture'] = self.textures['freq'][stimulus['freq']]
            except:
                self.current_stimulus['texture'] = self.textures['freq'][self.default_freq]

        elif stimulus['stim_type'] == 'b':
            self.current_stimulus = stimulus

            try:
                if isinstance(stimulus['freq'], int):
                    self.current_stimulus['texture'] = [self.textures['freq'][stimulus['freq']],
                                                        self.textures['freq'][stimulus['freq']]]
                else:
                    self.current_stimulus['texture'] = [
                    self.textures['freq'][stimulus['freq'][0]], self.textures['freq'][stimulus['freq'][1]]]
            except:
                self.current_stimulus['texture'] = [
                self.textures['freq'][self.default_freq], self.textures['freq'][self.default_freq]]
            try:
                test_1 = self.current_stimulus['center_width']
            except KeyError:
                self.current_stimulus['center_width'] = self.default_center_width
            if stimulus['center_x'] or stimulus['center_y'] != 0:
                self.center_x = stimulus['center_x']
                self.center_y = stimulus['center_y']
            else:
                self.center_x = 0
                self.center_y = 0

            if stimulus['strip_angle'] != 0:
                self.strip_angle = stimulus['strip_angle']
            else:
                self.strip_angle = 0

        if stimulus is not None:
            if 'stationary_time' in stimulus:
                self._stat_finish = False
                self._stimulus_stationary = tr.Thread(target=self.stimulus_stationary)
                self._stimulus_stationary.start()

            if 'stim_time' in stimulus:
                if stimulus['stim_time'] != 0:
                    self._max_finish = False
                    self.max_time = tr.Thread(target=self.stimulus_max_duration)
                    self.max_time.start()

        self.curr_id += 1

        self.create_texture_stages()
        self.create_cards()
        self.set_texture_stages()
        self.set_transforms()

        self.save()

    def save(self):
        if self.filestream:
            saved_stim = dict(self.current_stimulus.copy())
            saved_stim.pop('texture')
            self.filestream.write("\n")
            self.filestream.write(f"{str(datetime.now())}: {self.curr_id} {saved_stim}")
            self.filestream.flush()

    def stimulus_max_duration(self):

        if self.current_stimulus['stim_type'] != 'b':
            if self.current_stimulus['stim_time'] > 0:
                t_0 = time.time()
                while time.time() - t_0 <= self.current_stimulus['stim_time']:
                    if self._max_finish:
                        break
                    pass

            if not self._max_finish:
                self.set_stimulus({'stim_type': 'blank', 'velocity': 0, 'angle': 0, 'texture': self.textures['blank']})
                return
            else:
                return
        elif self.current_stimulus['stim_type'] == 'b':
            t0, t1 = self.current_stimulus['stim_time']
            still_running = True

            if t0 == 0:
                a_done = True
            else:
                a_done = False
            if t1 == 0:
                b_done = True
            else:
                b_done = False

            if t0 or t1 > 0:
                _t0 = time.time()
                while still_running:
                    elapsed = time.time() - _t0
                    if elapsed >= t0 and not a_done:
                        self.left_card.detachNode()
                        self.current_stimulus['texture'][0] = self.textures['blank']
                        self.save()
                        a_done = True
                    if elapsed >= t1 and not b_done:
                        self.right_card.detachNode()
                        self.current_stimulus['texture'][1] = self.textures['blank']
                        self.save()
                        b_done = True
                    if a_done and b_done:
                        still_running = False
                        break

            else:
                return

    def stimulus_stationary(self):
        if self.current_stimulus['stim_type'] != 'b':
            if self.current_stimulus['stationary_time'] >= 0:
                t_0 = time.time()
                prev_vel = self.current_stimulus['velocity']
                self.current_stimulus['velocity'] = 0
                self.save()
                while time.time() - t_0 <= self.current_stimulus['stationary_time']:
                    if self._stat_finish:
                        break
                    pass

                self.current_stimulus['velocity'] = prev_vel
                self.save()
                return
            else:
                return
        if self.current_stimulus['stim_type'] == 'b':
            stat_time_0, stat_time_1 = self.current_stimulus['stationary_time']
            a0 = False
            a1 = False

            if stat_time_0 or stat_time_1 >= 0:

                v0, v1 = self.current_stimulus['velocity']
                t_0 = time.time()

                if stat_time_0 > 0:
                    self.current_stimulus['velocity'][0] = 0
                    a0 = True
                if stat_time_1 > 0:
                    self.current_stimulus['velocity'][1] = 0
                    a1 = True

                self.save()
                while True:
                    if self._stat_finish:
                        break
                    if not a0 and not a1:
                        break

                    if time.time() - t_0 >= stat_time_0 and a0 :
                        self.current_stimulus['velocity'][0] = v0
                        a0 = False
                        self.save()

                    if time.time() - t_0 >= stat_time_1 and a1:
                        self.current_stimulus['velocity'][1] = v1
                        a1 = False
                        self.save()

            else:
                return

    def move_textures(self, task):
        # moving the stimuli
        # print(self.current_stim)
        if self.current_stimulus['stim_type'] == 'b':
            left_tex_position = -task.time * self.current_stimulus['velocity'][0]  # negative b/c texture stage
            right_tex_position = -task.time * self.current_stimulus['velocity'][1]
            try:
                self.left_card.setTexPos(self.left_texture_stage, left_tex_position, 0, 0)
                self.right_card.setTexPos(self.right_texture_stage, right_tex_position, 0, 0)
            except Exception as e:
                print('error on move_texture_b')

        elif self.current_stimulus['stim_type'] == 's':
            if self.current_stimulus['velocity'] == 0:
                pass
            else:
                new_position = -task.time * self.current_stimulus['velocity']
                # Sometimes setting position fails when the texture stage isn't fully set
                try:
                    self.card.setTexPos(self.texture_stage, new_position, 0, 0)  # u, v, w
                except Exception as e:
                    print('error on move_texture_s')

        elif self.current_stimulus['stim_type'] == 'rdk' and self.dots_made:
            dt = task.time - self.last_time
            self.last_time = task.time

            # because this isnt the 2D card, lets set up a lens to see it
            self.lens = PerspectiveLens()
            self.lens.setFov(90, 90)
            self.lens.setNearFar(0.001, 1000)
            self.lens.setAspectRatio(1)
            self.cam.node().setLens(self.lens)

            # ???
            random_vector = np.random.randint(100, size=10000)
            self.coherent_change_vector_ind = np.where(random_vector < self.current_stimulus['coherence'])

            #######
            # Continously update the dot stimulus
            #####
            self.dots_position[0, :, 0][self.coherent_change_vector_ind] += \
                np.cos(self.current_stimulus['angle'] * np.pi / 180) * self.current_stimulus['velocity'] * dt

            self.dots_position[0, :, 1][self.coherent_change_vector_ind] += \
                np.sin(self.current_stimulus['angle'] * np.pi / 180) * self.current_stimulus['velocity'] * dt

            # Randomly redraw dot with a short lifetime
            k = np.random.random(10000)
            if self.current_stimulus['lifetime'] == 0:
                ind = np.where(k >= 0)[0]
            else:
                ind = np.where(k < dt / self.current_stimulus['lifetime'])[0]

            self.dots_position[0, :, 0][ind] = 2 * np.random.random(len(ind)).astype(np.float32) - 1  # x
            self.dots_position[0, :, 1][ind] = 2 * np.random.random(len(ind)).astype(np.float32) - 1  # y
            self.dots_position[0, :, 2] = np.ones(10000) * self.current_stimulus['brightness']

            # Wrap them
            self.dots_position[0, :, 0] = (self.dots_position[0, :, 0] + 1) % 2 - 1
            self.dots_position[0, :, 1] = (self.dots_position[0, :, 1] + 1) % 2 - 1

            memoryview(self.dummytex.modify_ram_image())[:] = self.dots_position.tobytes()

        return task.cont

    def create_texture_stages(self):
        """
        Create the texture stages: these are basically textures that you can apply
        to cards (sometimes mulitple textures at the same time -- is useful with
        masks).

        For more on texture stages:
        https://docs.panda3d.org/1.10/python/programming/texturing/multitexture-introduction
        """
        # Binocular cards
        if self.current_stimulus['stim_type'] == 'b':
            # TEXTURE STAGES FOR LEFT CARD
            # Texture itself
            self.left_texture_stage = TextureStage('left_texture_stage')
            # Mask
            self.left_mask = Texture("left_mask_texture")
            self.left_mask.setup2dTexture(self.current_stimulus['texture'][0].texture_size[0],
                                          self.current_stimulus['texture'][0].texture_size[1],
                                          Texture.T_unsigned_byte, Texture.F_luminance)
            self.left_mask_stage = TextureStage('left_mask_array')

            # TEXTURE STAGES FOR RIGHT CARD
            self.right_texture_stage = TextureStage('right_texture_stage')
            # Mask
            self.right_mask = Texture("right_mask_texture")
            self.right_mask.setup2dTexture(self.current_stimulus['texture'][1].texture_size[0],
                                           self.current_stimulus['texture'][1].texture_size[1],
                                           Texture.T_unsigned_byte, Texture.F_luminance)
            self.right_mask_stage = TextureStage('right_mask_stage')

        # monocular cards
        elif self.current_stimulus['stim_type'] == 's':
            self.texture_stage = TextureStage("texture_stage")

        # random dots are special cards because they are actually full panda3d models with a special lens  to appear 2D
        # NOT the 2D card based textures the others are based on cr: Armin Bahl
        elif self.current_stimulus['stim_type'] == 'rdk':
            self.dot_motion_coherence_shader = [
                """ #version 140
                    uniform sampler2D p3d_Texture0;
                    uniform mat4 p3d_ModelViewProjectionMatrix;
                    in vec4 p3d_Vertex;
                    in vec2 p3d_MultiTexCoord0;
                    uniform int number_of_dots;
                    uniform float size_of_dots;
                    uniform float radius;

                    out float dot_color;
                    void main(void) {
                        vec4 newvertex;
                        float dot_i;
                        float dot_x, dot_y;
                        float maxi = 10000.0;
                        vec4 dot_properties;
                        dot_i = float(p3d_Vertex[1]);
                        dot_properties = texture2D(p3d_Texture0, vec2(dot_i/maxi, 0.0));
                        dot_x = dot_properties[2];
                        dot_y = dot_properties[1];
                        dot_color = dot_properties[0];
                        newvertex = p3d_Vertex;
                        if (dot_x*dot_x + dot_y*dot_y > radius*radius || dot_i > number_of_dots) { // only plot a certain number of dots in a circle
                            newvertex[0] = 0.0;
                            newvertex[1] = 0.0;
                            newvertex[2] = 0.0;
                        } else {
                            newvertex[0] = p3d_Vertex[0]*size_of_dots+dot_x;
                            newvertex[1] = 0.75;
                            newvertex[2] = p3d_Vertex[2]*size_of_dots+dot_y;
                        }
                        gl_Position = p3d_ModelViewProjectionMatrix * newvertex;
                    }
                """,

                """ #version 140
                    in float dot_color;
                    //out vec4 gl_FragColor;
                    void main() {
                        gl_FragColor = vec4(dot_color, dot_color, dot_color, 1);
                    }
                """
            ]
            self.compiled_dot_motion_shader = Shader.make(Shader.SLGLSL, self.dot_motion_coherence_shader[0],
                                                          self.dot_motion_coherence_shader[1])

            self.circles = self.loader.loadModel('resources/circles.bam')

            self.dummytex = Texture("dummy texture")  # this doesn't have an associated texture (as above)
            self.dummytex.setup2dTexture(10000, 1, Texture.T_float, Texture.FRgb32)
            self.dummytex.setMagfilter(Texture.FTNearest)

            tex = TextureStage("dummy followup")
            tex.setSort(-100)  # ???

            self.circles.setTexture(tex, self.dummytex)
            self.circles.setShader(self.compiled_dot_motion_shader)

    def create_cards(self):
        """
        Create cards: these are panda3d objects that are required for displaying textures.
        You can't just have a disembodied texture. In pandastim (at least for now) we are
        only showing 2d projections of textures, so we use cards.
        """
        cardmaker = CardMaker("stimcard")
        cardmaker.setFrameFullscreenQuad()

        # Binocular cards
        if self.current_stimulus['stim_type'] == 'b':
            self.setBackgroundColor((0, 0, 0, 1))  # without this the cards will appear washed out
            self.left_card = self.aspect2d.attachNewNode(cardmaker.generate())
            self.left_card.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))  # otherwise only right card shows

            self.right_card = self.aspect2d.attachNewNode(cardmaker.generate())
            self.right_card.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))

        # Tex card
        elif self.current_stimulus['stim_type'] == 's':
            self.card = self.aspect2d.attachNewNode(cardmaker.generate())
            self.card.setColor((1, 1, 1, 1))
            self.card.setScale(self.scale)

        # attach model to card w/ the rdk stimulus
        elif self.current_stimulus['stim_type'] == 'rdk':
            self.card = self.render.attachNewNode('dumb node')
            self.circles.reparentTo(self.card)
            self.circles.setShaderInput("number_of_dots", int(self.current_stimulus['number']))
            self.circles.setShaderInput("size_of_dots", self.current_stimulus['size'])
            self.circles.setShaderInput("radius", self.current_stimulus['window'])
            self.setBackgroundColor(0, 0, 0, 1)

    def set_texture_stages(self):
        """
        Add texture stages to cards
        """
        if self.current_stimulus['stim_type'] == 'b':

            # self.mask_position_uv = (self.bin_center_x, self.bin_center_y)

            # CREATE MASK ARRAYS
            self.left_mask_array = 255 * np.ones((self.current_stimulus['texture'][0].texture_size[0],
                                                  self.current_stimulus['texture'][0].texture_size[1]), dtype=np.uint8)
            self.left_mask_array[:, (self.current_stimulus['texture'][0].texture_size[1] // 2)
                                    - self.current_stimulus['center_width'] // 2:] = 0

            self.right_mask_array = 255 * np.ones((self.current_stimulus['texture'][1].texture_size[0],
                                                   self.current_stimulus['texture'][1].texture_size[1]), dtype=np.uint8)
            self.right_mask_array[:,
            : (self.current_stimulus['texture'][0].texture_size[1] // 2) + self.current_stimulus[
                'center_width'] // 2] = 0

            # ADD TEXTURE STAGES TO CARDS
            self.left_mask.setRamImage(self.left_mask_array)
            self.left_card.setTexture(self.left_texture_stage, self.current_stimulus['texture'][0].texture)
            self.left_card.setTexture(self.left_mask_stage, self.left_mask)

            # Multiply the texture stages together
            self.left_mask_stage.setCombineRgb(TextureStage.CMModulate,
                                               TextureStage.CSTexture,
                                               TextureStage.COSrcColor,
                                               TextureStage.CSPrevious,
                                               TextureStage.COSrcColor)
            self.right_mask.setRamImage(self.right_mask_array)
            self.right_card.setTexture(self.right_texture_stage, self.current_stimulus['texture'][1].texture)
            self.right_card.setTexture(self.right_mask_stage, self.right_mask)

            # Multiply the texture stages together
            self.right_mask_stage.setCombineRgb(TextureStage.CMModulate,
                                                TextureStage.CSTexture,
                                                TextureStage.COSrcColor,
                                                TextureStage.CSPrevious,
                                                TextureStage.COSrcColor)

        elif self.current_stimulus['stim_type'] == 's':
            self.card.setTexture(self.texture_stage, self.current_stimulus['texture'].texture)

    def set_transforms(self):
        """
        Set up the transforms to apply to textures/cards (e.g., rotations/scales)
        This is different from the framewise movement handled by the task manager
        """
        if self.current_stimulus['stim_type'] == 'b':
            self.mask_transform = self.trs_transform()

            # self.left_angle = self.reduce_to_pi(self.fish_angle+self.current_stim['angle'][0])
            # self.right_angle = self.reduce_to_pi(self.fish_angle+self.current_stim['angle'][1])
            self.left_angle = self.strip_angle + self.current_stimulus['angle'][0] + self.rotation_offset
            self.right_angle = self.strip_angle + self.current_stimulus['angle'][1] + self.rotation_offset

            self.left_card.setTexTransform(self.left_mask_stage, self.mask_transform)
            self.right_card.setTexTransform(self.right_mask_stage, self.mask_transform)
            # Left texture
            self.left_card.setTexScale(self.left_texture_stage, 1 / self.scale)
            self.left_card.setTexRotate(self.left_texture_stage, self.left_angle)

            # Right texture
            self.right_card.setTexScale(self.right_texture_stage, 1 / self.scale)
            self.right_card.setTexRotate(self.right_texture_stage, self.right_angle)

        elif self.current_stimulus['stim_type'] == 's':
            self.card.setTexRotate(self.texture_stage, self.current_stimulus['angle'] + self.rotation_offset)
            self.card.setTexPos(self.texture_stage, self.center_x, self.center_y, 0)

        elif self.current_stimulus['stim_type'] == 'rdk':
            self.dots_position = np.empty((1, 10000, 3)).astype(np.float32)
            self.dots_position[0, :, 0] = 2 * np.random.random(10000).astype(np.float32) - 1  # x
            self.dots_position[0, :, 1] = 2 * np.random.random(10000).astype(np.float32) - 1  # y
            self.dots_position[0, :, 2] = np.ones(10000) * self.current_stimulus['brightness']
            self.dots_made = True
            self.card.setTexPos(self.texture_stage, self.center_x, self.center_y, 0)

    def clear_cards(self):
        """
        Clear cards when new stimulus: stim-class sensitive
        """
        try:
            if self.current_stimulus['stim_type'] == 'b':
                self.left_card.detachNode()
                self.right_card.detachNode()
                # if self.profile_on:
                # self.center_indicator.detachNode()

            elif self.current_stimulus['stim_type'] == 's':
                self.card.detachNode()

            elif self.current_stimulus['stim_type'] == 'rdk':
                self.card.detachNode()

        except AttributeError:
            pass

    def trs_transform(self):
        """
        trs = translate-rotate-scale transform for mask stage
        panda3d developer rdb contributed to this code
        """
        # self.mask_position_uv = (self.center_x, self.center_y)

        # # pos = 0.5 + self.mask_position_uv[0], 0.5 + self.mask_position_uv[1]
        # center_shift = TransformState.make_pos2d((self.mask_position_uv[0], self.mask_position_uv[1]))
        # scale = TransformState.make_scale2d(1 / self.scale)
        # rotate = TransformState.make_rotate2d(self.strip_angle)s
        # translate = TransformState.make_pos2d((0.5, 0.5))
        # return translate.compose(scale.compose(center_shift))
        self.mask_position_uv = (self.center_x, self.center_y)

        # print(self.curr_params)

        pos = 0.5 + self.mask_position_uv[0], 0.5 + self.mask_position_uv[1]
        center_shift = TransformState.make_pos2d((-pos[0], -pos[1]))
        scale = TransformState.make_scale2d(1 / self.scale)
        rotate = TransformState.make_rotate2d(self.strip_angle)
        translate = TransformState.make_pos2d((0.5, 0.5))
        return translate.compose(rotate.compose(scale.compose(center_shift)))


class KeyboardToggleTex(ShowBase):
    """
    toggles between two textures based on keyboard inputs (0 and 1). Not set up
    for binocular stim. Similar call to InputControlStim
    """

    def __init__(self, tex_classes, stim_params, window_size=512,
                 profile_on=False, fps=30, save_path=None):
        super().__init__()

        self.tex_classes = tex_classes
        self.current_tex_num = 0
        self.stim_params = stim_params
        self.window_size = window_size
        self.stimulus_initialized = False  # to handle case from -1 (uninitalize) to 0 (first stim)
        self.fps = fps
        self.save_path = save_path
        if self.save_path:
            self.filestream = utils.save_initialize(save_path, tex_classes, stim_params)
        else:
            self.filestream = None

        # Window properties
        self.windowProps = WindowProperties()
        self.windowProps.setSize(self.window_size, self.window_size)
        self.set_title("Initializing")

        # Create scenegraph
        cm = CardMaker('card')
        cm.setFrameFullscreenQuad()
        self.card = self.aspect2d.attachNewNode(cm.generate())
        self.card.setScale(np.sqrt(8))
        self.texture_stage = TextureStage("texture_stage")

        # Set frame rate
        ShowBaseGlobal.globalClock.setMode(ClockObject.MLimited)
        ShowBaseGlobal.globalClock.setFrameRate(self.fps)  # can lock this at whatever

        if profile_on:
            PStatClient.connect()
            ShowBaseGlobal.base.setFrameRateMeter(True)

            # Set initial texture
        self.set_stimulus(str(self.current_tex_num))

        # Set up event handlers and tasks
        self.accept('0', self.set_stimulus, ['0'])  # event handler
        self.accept('1', self.set_stimulus, ['1'])
        self.taskMgr.add(self.move_texture_task, "move_texture")  # task

    @property
    def current_stim_params(self):
        """ 
        returns parameters of current stimulus
        """
        return self.stim_params[self.current_tex_num]

    def set_stimulus(self, data):
        """ 
        Called with relevant keyboard events
        """
        if not self.stimulus_initialized:
            """
            If the first texture has not yet been shown, then toggle initialization
            and do not clear previous texture (there is no previous texture). 
            Otherwise clear previous texture so they do not overlap."""
            self.self_initialized = True
        else:
            self.card.detachNode()

        if data == '0':
            self.current_tex_num = 0
        elif data == '1':
            self.current_tex_num = 1

        if self.filestream:
            current_datetime = str(datetime.now())
            self.filestream.write(f"{current_datetime}\t{data}\n")
            self.filestream.flush()
        logger.info(self.current_tex_num, self.current_stim_params)
        self.tex = self.tex_classes[self.current_tex_num]

        self.card.setColor((1, 1, 1, 1))
        self.card.setTexture(self.texture_stage, self.tex.texture)
        self.card.setTexRotate(self.texture_stage, self.current_stim_params['angle'])
        other_stim = 1 if self.current_tex_num == 0 else 0
        self.set_title(f"Press {other_stim} to switch")

        return

    def move_texture_task(self, task):
        """
        The stimulus (texture) is set: now move it if needed.
        """
        if self.current_stim_params['velocity'] == 0:
            pass
        else:
            new_position = -task.time * self.current_stim_params['velocity']
            self.card.setTexPos(self.texture_stage, new_position, 0, 0)  # u, v, w
        return task.cont

    def set_title(self, title):
        self.windowProps.setTitle(title)
        ShowBaseGlobal.base.win.requestProperties(self.windowProps)  # base is a panda3d global


class InputControlStim(ShowBase):
    """
    Generic input-controll stimulus class: takes in list of texture classes, and stimulus parameters.
    Stimulus shown, in real-time, depends on events produced by utils.Monitor() class.
    
    Inputs:
        Positional
            tex_classes: m-element list of texture classes
            stim_params: m-element list of dictionaries: each contains parameters (e.g., velocity)
        
        Keyword 
            initial_tex_ind (0): index for first stim to show
            window_size (512): size of the panda3d window (pixels)
            window_name ('InputControlStim'): title of window in gui
            profile_on (False): will show actual fps, profiler, and little x at center if True
            fps (30): controls frame rate of display
            save_path (None): if set to a file path, will save data about stimuli, and time they are delivered
    """

    def __init__(self, tex_classes, stim_params, initial_tex_ind=0, window_size=512,
                 window_name="InputControlStim", profile_on=False, fps=30, save_path=None):
        super().__init__()

        self.current_tex_num = initial_tex_ind
        self.previous_tex_num = None
        self.tex_classes = tex_classes
        self.stim_params = stim_params
        self.window_size = window_size
        self.stimulus_initialized = False  # for setting up first stim (don't clear cards they don't exist)
        self.fps = fps
        self.profile_on = profile_on
        self.save_path = save_path
        if self.save_path:
            self.filestream = utils.save_initialize(save_path, tex_classes, stim_params)
        else:
            self.filestream = None
        self.scale = np.sqrt(8)  # so it can handle arbitrary rotations and shifts
        self.window_name = window_name

        # Window properties
        self.window_props = WindowProperties()
        self.window_props.setSize(self.window_size, self.window_size)
        self.set_title(self.window_name)

        # Set frame rate
        ShowBaseGlobal.globalClock.setMode(ClockObject.MLimited)
        ShowBaseGlobal.globalClock.setFrameRate(self.fps)

        # Set up profiling if desired
        if self.profile_on:
            PStatClient.connect()  # this will only work if pstats is running
            ShowBaseGlobal.base.setFrameRateMeter(True)  # Show frame rate

        # Set initial texture(s)
        self.set_stimulus(str(self.current_tex_num))

        # Set up event handlers (accept) and tasks (taskMgr) for dynamics
        self.accept('stim0', self.set_stimulus, ['0'])
        self.accept('stim1', self.set_stimulus, ['1'])
        self.accept('stim2', self.set_stimulus, ['2'])
        # Wrinkle: should we set this here or there?
        self.taskMgr.add(self.move_textures, "move textures")

    def set_tasks(self):
        if self.current_stim_params['stim_type'] == 'b':
            self.taskMgr.add(self.textures_update, "move_both")

    # Move textures
    def move_textures(self, task):
        if self.current_stim_params['stim_type'] == 'b':
            left_tex_position = -task.time * self.current_stim_params['velocities'][0]  # negative b/c texture stage
            right_tex_position = -task.time * self.current_stim_params['velocities'][1]
            try:
                self.left_card.setTexPos(self.left_texture_stage, left_tex_position, 0, 0)
                self.right_card.setTexPos(self.right_texture_stage, right_tex_position, 0, 0)
            except Exception as e:
                logger.error(e)
        elif self.current_stim_params['stim_type'] == 's':
            if self.current_stim_params['velocity'] == 0:
                pass
            else:
                new_position = -task.time * self.current_stim_params['velocity']
                # Sometimes setting position fails when the texture stage isn't fully set
                try:
                    self.card.setTexPos(self.texture_stage, new_position, 0, 0)  # u, v, w
                except Exception as e:
                    logger.error(e)
        return task.cont

    @property
    def texture_size(self):
        return self.tex_classes[self.current_tex_num].texture_size

    @property
    def current_stim_params(self):
        """ 
        Parameters of current texture (e.g., velocity, stim_type) 
        """
        return self.stim_params[self.current_tex_num]

    def create_cards(self):
        """ 
        Create cards: these are panda3d objects that are required for displaying textures.
        You can't just have a disembodied texture. In pandastim (at least for now) we are
        only showing 2d projections of textures, so we use cards.       
        """
        cardmaker = CardMaker("stimcard")
        cardmaker.setFrameFullscreenQuad()
        # Binocular cards
        if self.current_stim_params['stim_type'] == 'b':
            self.setBackgroundColor((0, 0, 0, 1))  # without this the cards will appear washed out
            self.left_card = self.aspect2d.attachNewNode(cardmaker.generate())
            self.left_card.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))  # otherwise only right card shows

            self.right_card = self.aspect2d.attachNewNode(cardmaker.generate())
            self.right_card.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))
            if self.profile_on:
                self.center_indicator = OnscreenText("x",
                                                     style=1,
                                                     fg=(1, 1, 1, 1),
                                                     bg=(0, 0, 0, .8),
                                                     pos=self.current_stim_params['position'],
                                                     scale=0.05)
        # Tex card
        elif self.current_stim_params['stim_type'] == 's':
            self.card = self.aspect2d.attachNewNode(cardmaker.generate())
            self.card.setColor((1, 1, 1, 1))  # ?
            self.card.setScale(self.scale)
        return

    def create_texture_stages(self):
        """
        Create the texture stages: these are basically textures that you can apply
        to cards (sometimes mulitple textures at the same time -- is useful with
        masks).
        
        For more on texture stages:
        https://docs.panda3d.org/1.10/python/programming/texturing/multitexture-introduction
        """
        # Binocular cards
        if self.current_stim_params['stim_type'] == 'b':
            # TEXTURE STAGES FOR LEFT CARD
            # Texture itself
            self.left_texture_stage = TextureStage('left_texture_stage')
            # Mask
            self.left_mask = Texture("left_mask_texture")
            self.left_mask.setup2dTexture(self.texture_size, self.texture_size,
                                          Texture.T_unsigned_byte, Texture.F_luminance)
            self.left_mask_stage = TextureStage('left_mask_array')

            # TEXTURE STAGES FOR RIGHT CARD
            self.right_texture_stage = TextureStage('right_texture_stage')
            # Mask
            self.right_mask = Texture("right_mask_texture")
            self.right_mask.setup2dTexture(self.texture_size, self.texture_size,
                                           Texture.T_unsigned_byte, Texture.F_luminance)
            self.right_mask_stage = TextureStage('right_mask_stage')
        # Tex card
        elif self.current_stim_params['stim_type'] == 's':
            self.texture_stage = TextureStage("texture_stage")
        return

    def set_stimulus(self, data):
        """ 
        Uses events from zmq to set the stimulus value. 
        """
        logger.debug("\tset_stimulus(%s)", data)
        if not self.stimulus_initialized:
            # If this is first stim, then toggle initialization to on, and
            # do not clear previous texture (there is no previous texture).
            self.stimulus_initialized = True
            self.data_previous = data
        elif data == self.data_previous:
            return
        else:
            self.data_previous = data
            self.clear_cards()  # clear the textures before adding new ones

        # This assumes data streaming is string numbers 0, 1, etc.
        self.current_tex_num = int(data)

        # Set new texture stages/cards etc
        self.tex = self.tex_classes[self.current_tex_num]

        logger.debug("\t%d: %s", self.current_tex_num, self.tex)
        self.create_texture_stages()
        self.create_cards()
        self.set_texture_stages()
        self.set_transforms()
        # Save stim to file (put this last as you want to set transforms quickly)
        if self.filestream:
            self.filestream.write(f"{str(datetime.now())}\t{data}\n")
            self.filestream.flush()
        return

    def clear_cards(self):
        """ 
        Clear cards when new stimulus: stim-class sensitive
        """
        if self.current_stim_params['stim_type'] == 'b':
            self.left_card.detachNode()
            self.right_card.detachNode()
            if self.profile_on:
                self.center_indicator.detachNode()
        elif self.current_stim_params['stim_type'] == 's':
            self.card.detachNode()
        return

    def set_transforms(self):
        """ 
        Set up the transforms to apply to textures/cards (e.g., rotations/scales)
        This is different from the framewise movement handled by the task manager
        """
        if self.current_stim_params['stim_type'] == 'b':
            # masks
            self.mask_transform = self.trs_transform()
            self.left_card.setTexTransform(self.left_mask_stage, self.mask_transform)
            self.right_card.setTexTransform(self.right_mask_stage, self.mask_transform)
            # Left texture
            self.left_card.setTexScale(self.left_texture_stage, 1 / self.scale)
            self.left_card.setTexRotate(self.left_texture_stage, self.current_stim_params['angles'][0])

            # Right texture
            self.right_card.setTexScale(self.right_texture_stage, 1 / self.scale)
            self.right_card.setTexRotate(self.right_texture_stage, self.current_stim_params['angles'][1])

        if self.current_stim_params['stim_type'] == 's':
            self.card.setTexRotate(self.texture_stage, self.current_stim_params['angle'])
        return

    def set_texture_stages(self):
        """ 
        Add texture stages to cards
        """
        if self.current_stim_params['stim_type'] == 'b':
            self.mask_position_uv = (utils.card2uv(self.current_stim_params['position'][0]),
                                     utils.card2uv(self.current_stim_params['position'][1]))

            # CREATE MASK ARRAYS
            self.left_mask_array = 255 * np.ones((self.texture_size,
                                                  self.texture_size), dtype=np.uint8)
            self.left_mask_array[:, self.texture_size // 2 - self.current_stim_params['strip_width'] // 2:] = 0
            self.right_mask_array = 255 * np.ones((self.texture_size,
                                                   self.texture_size), dtype=np.uint8)
            self.right_mask_array[:, : self.texture_size // 2 + self.current_stim_params['strip_width'] // 2] = 0

            # ADD TEXTURE STAGES TO CARDS
            self.left_mask.setRamImage(self.left_mask_array)
            self.left_card.setTexture(self.left_texture_stage, self.tex.texture)
            self.left_card.setTexture(self.left_mask_stage, self.left_mask)
            # Multiply the texture stages together
            self.left_mask_stage.setCombineRgb(TextureStage.CMModulate,
                                               TextureStage.CSTexture,
                                               TextureStage.COSrcColor,
                                               TextureStage.CSPrevious,
                                               TextureStage.COSrcColor)
            self.right_mask.setRamImage(self.right_mask_array)
            self.right_card.setTexture(self.right_texture_stage, self.tex.texture)
            self.right_card.setTexture(self.right_mask_stage, self.right_mask)
            # Multiply the texture stages together
            self.right_mask_stage.setCombineRgb(TextureStage.CMModulate,
                                                TextureStage.CSTexture,
                                                TextureStage.COSrcColor,
                                                TextureStage.CSPrevious,
                                                TextureStage.COSrcColor)

        elif self.current_stim_params['stim_type'] == 's':
            self.card.setTexture(self.texture_stage, self.tex.texture)
        return

    def trs_transform(self):
        """ 
        trs = translate-rotate-scale transform for mask stage
        panda3d developer rdb contributed to this code
        """
        pos = 0.5 + self.mask_position_uv[0], 0.5 + self.mask_position_uv[1]
        center_shift = TransformState.make_pos2d((-pos[0], -pos[1]))
        scale = TransformState.make_scale2d(1 / self.scale)
        rotate = TransformState.make_rotate2d(self.current_stim_params['strip_angle'])
        translate = TransformState.make_pos2d((0.5, 0.5))
        return translate.compose(rotate.compose(scale.compose(center_shift)))

    def set_title(self, title):
        self.window_props.setTitle(title)
        ShowBaseGlobal.base.win.requestProperties(self.window_props)  # base is a panda3d global


# %%  below stuff has NOT been refactors and probably will not work
class Scaling(ShowBase):
    """
    Show a single full-field texture that scales up or down in time, repeating.
    
    Matt: this has not been rewritten for the refactor it will not work.
    """

    def __init__(self, texture_array, scale=0.2, window_size=512, texture_size=512):
        super().__init__()
        self.scale = scale
        self.texture_array = texture_array
        self.texture_dtype = type(self.texture_array.flat[0])
        self.ndims = self.texture_array.ndim

        # Set window title
        self.window_properties = WindowProperties()
        self.window_properties.setSize(window_size, window_size)
        self.window_properties.setTitle("FullFieldDrift")
        ShowBaseGlobal.base.win.requestProperties(self.window_properties)

        # Create texture stage
        self.texture = Texture("Stimulus")

        # Select Texture ComponentType (e.g., uint8 or whatever)
        if self.texture_dtype == np.uint8:
            self.texture_component_type = Texture.T_unsigned_byte
        elif self.texture_dtype == np.uint16:
            self.texture_component_type = Texture.T_unsigned_short

        # Select Texture Format (color or b/w etc)
        if self.ndims == 2:
            self.texture_format = Texture.F_luminance  # grayscale
            self.texture.setup2dTexture(texture_size, texture_size,
                                        self.texture_component_type, self.texture_format)
            self.texture.setRamImageAs(self.texture_array, "L")
        elif self.ndims == 3:
            self.texture_format = Texture.F_rgb8
            self.texture.setup2dTexture(texture_size, texture_size,
                                        self.texture_component_type, self.texture_format)
            self.texture.setRamImageAs(self.texture_array, "RGB")
        else:
            raise ValueError("Texture needs to be 2d or 3d")

        self.textureStage = TextureStage("Stimulus")

        # Create scenegraph
        cm = CardMaker('card')
        cm.setFrameFullscreenQuad()
        self.card = self.aspect2d.attachNewNode(cm.generate())
        self.card.setTexture(self.textureStage, self.texture)  # ts, tx

        # Set the scale on the card (note this is different from scaling the texture)
        self.card.setScale(np.sqrt(2))

        if self.scale != 0:
            # Add task to taskmgr to translate texture
            self.taskMgr.add(self.scaleTextureTask, "scaleTextureTask")

    # Move the texture
    def scaleTextureTask(self, task):
        if task.time > 1:
            new_scale = task.time * (self.scale)
            self.card.setTexScale(self.textureStage, new_scale, new_scale)  # u_scale, v
            # Set conditional so when it reaches 0 or some max it resets to 1

        return Task.cont


# %%
if __name__ == '__main__':
    import textures

    sin_red_tex = textures.SinRgbTex(texture_size=512,
                                     spatial_frequency=20,
                                     rgb=(255, 0, 0))
    sin_red_stim = TexMoving(sin_red_tex,
                             angle=25,
                             velocity=-0.05,
                             window_name='red sin test stim',
                             profile_on=False)
    sin_red_stim.run()
