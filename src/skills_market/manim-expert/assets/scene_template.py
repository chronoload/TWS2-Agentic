"""
ManimCE Scene Template - Copy this to create new animations
"""
from manim import *


class MyScene(Scene):
    def construct(self):
        # === Configuration ===
        self.camera.background_color = BLACK

        # === Title ===
        title = Tex("My Title", font_size=48, color=WHITE)
        self.play(Write(title))
        self.wait(0.5)
        self.play(title.animate.scale(0.7).to_corner(UL))
        self.wait(0.5)

        # === Your content here ===

        # === Cleanup ===
        self.wait(2)


class My3DScene(ThreeDScene):
    def construct(self):
        self.camera.background_color = "#000000"
        self.set_camera_orientation(phi=70*DEGREES, theta=-45*DEGREES)

        # 3D content here
        axes = ThreeDAxes()
        self.play(Create(axes))
        self.begin_ambient_camera_rotation(rate=0.1)
        self.wait(2)
        self.stop_ambient_camera_rotation()
        self.wait(1)
