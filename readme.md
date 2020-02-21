# pandastim
<img align = "right" width = "120" src=".\images\omr_sin_example.png ">

Cross-platform Python package for generating visual stimuli using the [Panda3d](https://www.panda3d.org/) library.

### Installation
This assumes you are using Anaconda and Python 3:

    conda create --name pstim
    conda activate pstim
    conda install numpy scipy matplotlib zeromq
    pip install panda3d

To install pandastim, just to go the directory where you want it installed and run:    

    git clone https://github.com/EricThomson/pandastim.git

To test the installation, try running one of the examples in [examples/examples_readme.md](examples/examples_readme.md). For instance, `examples/drifting_fullfield_sin.py`. Note that panda3d doesn't always play nicely with IDEs, so I typically run scripts from the command line (e.g., `python -m examples.drifting_fullfield_sin`).

### Package structure
The three main modules:
- `stimuli.py`: defines classes used to show different textures. Can be as simple as showing a static grey sinusoidal grating, or showing a sequence of stimuli locked to an input signal from some external source.
- `textures.py`: texture classes used by the stimulus classes. They are all instances of the `TextureBase` abstract base class defined therein. If you run textures by itself, you can toggle different examples in `main` for fun and debugging.
- `utils.py`: helper code used across different classes: the interface classes for zmq sockets are here.

The `examples/` folder contains many examples. If you want to roll your own, I would use one of those as a starting point. For testing closed-loop experiment code, you can run `pub_class_toggle.py`, a zeromq publisher socket that emits random 0's and 1's that can be consumed by the ClosedLoop class.

### Profiling pandastim
Panda3d comes with a nice graphical code profiler for Windows users. The stimulus classes include a `profile_on` flag (which defaults to `False`). To activate it, you have to run `pstats` before starting your Python code, and set that flag to `True`r. This will also cause an FPS display to show on your stimulus window even if you aren't using the profiler.

On Windows, `pstats.exe` in your conda directory in `\envs\pstim\Scripts` (in Linux, `pstats` is in `\envs\pstim\bin` -- run it from the command line with `./pstats` -- you may need to install the module `libcanberra-gtk-module` first: `sudo apt-get install libcanberra-gtk-module`).

To learn more about optimizaing/profiling in panda3d: https://docs.panda3d.org/1.10/python/optimization/index


### To do (short term)
- Refactoring
    - Need a print or whatever for the Tex classes for insertion during Stim displays during filesaving.
    - Basic runthrough of code: documented, relatively clean, etc., including readme.
    - what is the deal with setColor versus setBackgroundColor? Also in 's' you are setting card color twice.
    - Also the ColorBlendAttrib.M_add, when is that needed?
    - why for transform do you use card.setR for 's' but card.setTexRotate? Are these different?
    - what are these different bg colors? sometimes 0 0 0 0 sometimes .5 .5  etc
    - Get names straight: stim_class or stim or texture for inputs to stim and calling it self.stim? didn't call it texture because that's largely taken. could do texture.texture or tex.texture. Maybe `tex`? Explicit is better than implcit, but maybe not for this.
    - profile_on is sometimes just profile. make sure it is consistent.
    - are the ndc2uv used/necessary and should they be in utils?
- Saving
    - Save mechanism check. E.g. for save mechanism, save stimulus types and params at top of file before saving which ones were delivered.
    - Have it save start/end time?
- Put x in ClosedLoop at position.
- Instead of examples folder, just do examples file? Probably not, but fewer. Port from examples_working.py (2 hours).
- Document how to run/test closed loop stuff (1 hour)



### To do (medium term)
- What is difference b/w card.detachNode() and card.removeNode(), and do we need to do clearTexture(stage) first? They both seem to work fine. Is detach safer?
- Create new updating stimulus classes
    - looming circle stimulus (static_fullfield_circle)
    - randomly updating stimulus (tex_random_working.py)
    - radial sine stimulus (use their code)
    - radial grating stimulus:
- Create open loop stim class.
- Find good example of weird rendiering differences with two angles, and ask about it @panda3d.
- Consider making monitor a process or use zmq iostream features.
- Make the 'Scaling' showbase? (this is for expanding/contracting circle)
    - Scaling card vs scaling texture?
- plot_timeline seems to not be used, or is used in lots of methods just make it a function?
- Independent color of middle band?
- Add drifting noise stimulus to drifting_fullfield examples.
- Add contrast to sines/gratings
- Have a stim code/previous stim or whatever, and only update task manager if it changes. Add better mechanism so if the stim type is same as previous, just return: don't change stimulus type, don't save anything.
- INstructions on how to integrate new stimulus class into closed loop.
- Document how to make a new texture class.
- How to close programatically? Would be useful for smoothness and also could add time/close signal code to save file.

### To do (long term)
- check with photodiode at different locations on window: is it identical?
- Ensure it works in real-time with inputs about fish location.
- Optimize
  - try compressing textures (https://www.panda3d.org/manual/?title=Texture_Compression) (note need 4x size for tex)?
- Consider porting to `pixel2d` (basics are in working/).
- Write up instructions on how to add new stimuli (basically make a numpy array, put it in stimuli.py, and then follow the examples whether you want a static, drifting stimulus, or experiment)
- To make plaids is pretty easy, just supereimpose two guys at two angles as in BinocularDrift fail 1am 3//9/19.
- Make a huge set of possible stimuli to show: the basis set (including plaids)

#### Notes
- If you are just learning panda3d, consider working through their tutorial (https://www.panda3d.org/manual/). Also you might consider installing their SDK, as it comes with useful examples (https://www.panda3d.org/download/).
- panda3d doesn't listen to your OS scale setting, so 800 pixel window is an 800 pixel window, it will not be scaled by your OS.
- It often looks like textures are drifting vertically/horizontally even when they are not. This is the well-known 'aperture problem'. To disambiguate, increase the window size until you can see their edges.
- `stimuli.KeyboardToggleStim` is largely a debugging class: it is really helpful for for testing out new stimulus classes you are thinking of pushing to `ClosedLoop`.


#### Conventions
PEP8, largely. UpperCamelCase for classes; lower_case_underscore for vars/functions/methods. Explicit is better than implicit.

#### Acknowledgments
Thanks to rdb (developer of panda3d) who provided lots of help figuring out how to efficiently do 2d things in a 3d game engine. Also the panda3d community in general has been very helpful.
