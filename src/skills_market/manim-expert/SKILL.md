---
name: manim-expert
description: >-
  This skill provides comprehensive expertise in Manim (both 3b1b and Manim Community Edition)
  for creating mathematical animations and visualizations. It should be used when the user
  requests help with Manim code generation, animation creation, mathematical visualization,
  or questions about the Manim animation library. Covers scene construction, camera control,
  LaTeX rendering, 3D scenes, animation patterns, and the Math-To-Manim AI pipeline.
  Also includes 55+ example animations from the Math-To-Manim project and 3Blue1Brown's
  video creation patterns.
---

# Manim Expert Skill

Comprehensive guide for creating mathematical animations using Manim (3b1b edition and Manim Community Edition).

## Critical: Two Manim Versions

There are **two distinct Manim libraries** with different APIs. Always confirm which version the user is working with before generating code.

### Manim Community Edition (`manim`)

- **Install**: `pip install manim`
- **Run**: `manim -pql file.py SceneName`
- **Import**: `from manim import *`
- **LaTeX**: Use `MathTex()` for equations, `Tex()` for LaTeX text
- **Raw strings**: `MathTex(r"\frac{a}{b}")`
- **Used by**: Math-To-Manim examples, general public projects

### 3b1b Manim (`manimgl`)

- **Install**: `pip install manimgl` (from source)
- **Run**: `manimgl file.py SceneName`
- **Import**: `from manimlib import *`
- **LaTeX**: Use `Tex()` (NOT `MathTex()` which is ManimCE only)
- **Raw strings**: `Tex(R"\frac{a}{b}")`
- **Used by**: 3Blue1Brown videos, `videos/` directory in this project
- **Key difference**: Uses `InteractiveScene`, `checkpoint_paste()`, no `MathTex`

## Quick Reference Commands

| Task | ManimCE | 3b1b |
|------|---------|------|
| Run scene | `manim -pql file.py Scene` | `manimgl file.py Scene` |
| High quality | `manim -qh file.py Scene` | `manimgl -w file.py Scene` |
| 4K render | `manim -qk file.py Scene` | N/A |
| Interactive | N/A | `manimgl file.py Scene -se <line>` |
| GIF output | `manim -pql --format gif file.py Scene` | N/A |
| List scenes | `manim file.py` | `manimgl file.py` |

Quality flags (ManimCE): `l`=low, `m`=medium, `h`=high, `k`=4K

## ManimCE Code Patterns

### Scene Skeleton

```python
from manim import *

class MyScene(Scene):
    def construct(self):
        # 1. Create mobjects
        title = Text("Title", font_size=48)
        equation = MathTex(r"\frac{a}{b}")

        # 2. Animate
        self.play(Write(title))
        self.play(FadeIn(equation))
        self.wait(1)
```

### 3D Scene

```python
class My3DScene(ThreeDScene):
    def construct(self):
        self.set_camera_orientation(phi=70*DEGREES, theta=-45*DEGREES)
        axes = ThreeDAxes()
        sphere = Sphere(radius=2, resolution=(30, 30))
        self.play(Create(axes), FadeIn(sphere))
        self.begin_ambient_camera_rotation(rate=0.1)
        self.wait(2)
        self.stop_ambient_camera_rotation()
```

### Essential Animation Methods

```python
self.play(Write(text))                    # Typewriter effect
self.play(FadeIn(obj))                    # Fade in
self.play(FadeOut(obj))                   # Fade out
self.play(Transform(a, b))               # Transform a into b
self.play(ReplacementTransform(a, b))    # Strict mapping transform
self.play(Create(obj))                    # Draw stroke
self.play(obj.animate.move_to(ORIGIN))   # Animate method
self.play(obj.animate.set_color(RED))    # Animate property
self.play(LaggedStart(*anims, lag_ratio=0.1))  # Staggered
self.play(AnimationGroup(*anims))         # Simultaneous
```

### Math Typesetting

```python
# ManimCE
MathTex(r"\frac{a}{b}", r"=", r"\sqrt{c}")  # Returns submobjects for each
Tex(r"E = mc^2")                             # Single LaTeX expression
MathTex("x^2 + y^2 = z^2", substrings_to_isolate=["x", "y", "z"])

# Color specific parts
eq = MathTex(r"x^2", "+", r"y^2", "=", r"z^2")
eq[0].set_color(BLUE)
eq[2].set_color(RED)

# Or use set_color_by_tex
eq = MathTex(r"x^2 + y^2 = z^2")
eq.set_color_by_tex("x^2", BLUE)
```

### Common Mobjects

```python
# Text
Text("Hello"), Tex(r"\alpha"), MathTex(r"\frac{1}{2}")
Integer(42), DecimalNumber(3.14)

# Shapes
Circle(), Square(), Rectangle(), Polygon([-1,0,0], [1,0,0], [0,2,0])
Line(LEFT, RIGHT), Arrow(LEFT, RIGHT), DashedLine(LEFT, RIGHT)
RoundedRectangle(), SurroundingRectangle(obj)

# Math
NumberPlane(), ComplexPlane(), Axes(), CoordinateSystem()
NumberLine(), NumberLine(x_range=[0, 10])
Dot(ORIGIN), VGroup(*items), Group(*items)

# Graphs
Graph(lambda x: np.sin(x), x_range=[-PI, PI])
ParametricCurve(lambda t: [np.cos(t), np.sin(t), 0], t_range=[0, 2*PI])

# 3D
Sphere(), Cube(), Torus(), Cone(), Cylinder()
ThreeDAxes(), Surface(), ParametricSurface()

# Tables & Charts
Table([["A","B"],["C","D"]]), BarChart(values=[1,2,3])
```

### Positioning & Layout

```python
obj.to_edge(UP)                    # Move to edge
obj.to_corner(UL)                  # Move to corner (UL, UR, DL, DR)
obj.next_to(other, RIGHT, buff=0.5)  # Place beside
obj.move_to(ORIGIN)                # Move to position
obj.shift(LEFT*2 + UP)             # Relative shift
VGroup(a, b, c).arrange(RIGHT, buff=1)  # Arrange in line
VGroup(a, b, c).arrange(DOWN, buff=0.5) # Arrange vertically
```

### Updaters

```python
# Simple updater
dot.add_updater(lambda m: m.move_to(point.get_center()))
obj.add_updater(lambda m: m.set_opacity(frame.time))

# f_always (3b1b)
obj.f_always.move_to(reference.get_center)

# Remove updater
dot.clear_updaters()
```

### Color Constants

`WHITE`, `BLACK`, `GREY`, `GREY_A/B/C/D`, `BLUE`, `BLUE_A/E/D/C`, `RED`, `RED_A/B/C/D/E`, `GREEN`, `GREEN_A/B/C/D/E`, `YELLOW`, `YELLOW_A/B/C/D/E`, `ORANGE`, `PURPLE`, `PURPLE_A/B/C/D/E`, `TEAL`, `MAROON`, `GOLD`, `PINK`, `LIGHT_GREY`, `DARK_GREY`

### Background Colors

```python
self.camera.background_color = "#000000"  # Black (default)
self.camera.background_color = "#1a0a2e"  # Deep purple
self.camera.background_color = WHITE      # White
```

### Custom Backgrounds & Starfields

```python
class StarField(VGroup):
    def __init__(self, is_3D=False, num_stars=200, **kwargs):
        super().__init__(**kwargs)
        for _ in range(num_stars):
            x = np.random.uniform(-7, 7)
            y = np.random.uniform(-4, 4)
            z = np.random.uniform(-3, 3) if is_3D else 0
            self.add(Dot(point=[x, y, z], color=WHITE, radius=0.02))
```

## 3b1b-Specific Patterns

### Scene Base Classes

```python
InteractiveScene    # Base for most 3b1b scenes (interactive dev)
PiCreatureScene    # Scenes with Pi creature
TeacherStudentsScene  # Pi creature classroom interactions
```

### Interactive Development Workflow

1. `manimgl file.py SceneName -se <line>` - Drop into interactive mode
2. In terminal: `checkpoint_paste()` - Run clipboard code
3. `checkpoint_paste(skip=True)` - Run without animation
4. `checkpoint_paste(record=True)` - Record to file
5. Use `self.frame` for camera operations

### 3b1b Code Style

```python
from manim_imports_ext import *  # Universal import for 3b1b videos

# Use Tex() for math, NOT MathTex()
formula = Tex(R"\frac{a}{b}")
formula = Tex(R"\pi")

# Text-to-color mapping
Tex(formula, t2c={"x": BLUE, "y": RED})

# Camera
frame = self.frame
frame.save_state()
self.play(frame.animate.scale(0.5))
self.play(Restore(frame))
```

## Math-To-Manim AI Pipeline

The Math-To-Manim project (in `manim/Math-To-Manim/`) provides an AI-driven pipeline that transforms natural language prompts into Manim animations using a six-agent **reverse knowledge tree** approach.

### Pipeline Architecture

```
User Prompt -> ConceptAnalyzer -> PrerequisiteExplorer (recursive)
    -> MathematicalEnricher -> VisualDesigner -> NarrativeComposer
    -> CodeGenerator -> Manim Python Code
```

### Key Concept: Reverse Knowledge Tree

Instead of training on examples, recursively ask "What must I understand BEFORE X?" to build pedagogically sound animations from foundations up.

### Three AI Pipelines Available

| Pipeline | Framework | Best For |
|----------|-----------|----------|
| Claude Sonnet 4.5 | Anthropic SDK | General purpose, reliable code |
| Gemini 3 | Google ADK | Complex topology, physics |
| Kimi K2.5 | OpenAI-compatible | LaTeX-heavy, structured reasoning |

### Running the Pipeline

```bash
# Claude UI
python src/app_claude.py

# Gemini pipeline
python Gemini3/run_pipeline.py "Explain the Hopf Fibration"

# Run example animations
manim -pql examples/physics/quantum/QED.py QEDJourney
manim -pql examples/mathematics/geometry/pythagorean.py PythagoreanScene
manim -pql examples/computer_science/machine_learning/AlexNet.py AlexNetIntro
```

## Example Animations Catalog

55+ examples organized by domain in `manim/Math-To-Manim/examples/`. For complete catalog with difficulty levels, read `references/examples_catalog.md`.

### Beginner Examples (Learn Manim Basics)

| File | Scene | Topic |
|------|-------|-------|
| `mathematics/geometry/pythagorean.py` | `EnhancedPythagorean` | Pythagorean theorem visual proof |
| `mathematics/geometry/bouncing_balls.py` | | Physics simulation |
| `misc/stickman.py` | `StickmanScene` | Basic character animation |
| `mathematics/trigonometry/TrigInference.py` | | Trig identities |

### Intermediate Examples

| File | Scene | Topic |
|------|-------|-------|
| `mathematics/fractals/fractal_scene.py` | `FractalScene` | Fractal patterns |
| `computer_science/algorithms/gale_shaply.py` | `GaleShapleyScene` | Stable matching |
| `computer_science/machine_learning/AlexNet.py` | `AlexNetIntro` | CNN architecture |
| `finance/optionskew.py` | `OptionSkewScene` | Option pricing |

### Advanced Examples

| File | Scene | Topic |
|------|-------|-------|
| `physics/quantum/QED.py` | `QEDJourney` | Quantum Electrodynamics (3D) |
| `physics/quantum/quantum_field_theory.py` | | QFT fundamentals |
| `mathematics/analysis/lorenz_attractor_symphony.py` | `LorenzAttractorSymphony` | Chaos theory (3D) |
| `mathematics/analysis/diffusion_optimal_transport.py` | | Optimal transport |
| `mathematics/statistics/information_geometry.py` | `InformationGeometryScene` | Information geometry |
| `physics/particle_physics/ElectroweakSymmetryScene.py` | | Electroweak symmetry |
| `misc/epic_hopf.py` | `HopfFibrationEpic` | Hopf fibration (3D topology) |

### 3D Scene Showcase

| File | Scene | Feature |
|------|-------|---------|
| `misc/visual_styles_showcase.py` | `All3DStyles` | Custom backgrounds, gradients, starfields |
| `physics/quantum/QED.py` | `QEDJourney` | Spacetime grid, light cones, EM waves |
| `mathematics/analysis/lorenz_attractor_symphony.py` | `LorenzAttractorSymphony` | 15k+ trajectory points, velocity coloring |
| `mathematics/geometry/rhombicosidodecahedron_flythrough.py` | | 3D polyhedron fly-through |

## Common Pitfalls

1. **Wrong Manim version API**: Using `MathTex()` with 3b1b or `Tex(R"...")` with ManimCE
2. **LaTeX without raw strings**: `MathTex("\frac{a}{b}")` fails - use `MathTex(r"\frac{a}{b}")`
3. **Missing `np` import**: `import numpy as np` needed for math functions
4. **3D in 2D scene**: Use `ThreeDScene` not `Scene` for 3D content
5. **Camera not reset**: Always `self.stop_ambient_camera_rotation()` before other camera moves
6. **Missing FFmpeg**: Manim requires FFmpeg for video output
7. **Missing LaTeX**: Manim requires LaTeX installation for equation rendering

## System Dependencies

- **Python**: 3.10+
- **FFmpeg**: `choco install ffmpeg` (Windows), `brew install ffmpeg` (macOS), `apt install ffmpeg` (Linux)
- **LaTeX**: MiKTeX (Windows), MacTeX (macOS), `apt install texlive-full` (Linux)
- **ManimCE**: `pip install manim`
- **3b1b**: `pip install manimgl` (from source)

## Reference Files

- `references/examples_catalog.md` - Complete catalog of all 55+ examples with descriptions, difficulty levels, and render commands
- `references/manim_tutorial_CN.md` - Chinese manim tutorial covering core concepts
- `references/3b1b_patterns.md` - 3Blue1Brown video creation patterns and code conventions
