"""
3b1b Manim Scene Template - For use with manimgl
"""
from manim_imports_ext import *


class MyVideoScene(InteractiveScene):
    def construct(self):
        # === Content ===
        formula = Tex(R"E = mc^2", font_size=72)
        formula.to_edge(UP)

        self.play(Write(formula))
        self.wait(2)

        # === Camera operations ===
        frame = self.frame
        frame.save_state()
        self.play(frame.animate.scale(0.5))
        self.wait(1)
        self.play(Restore(frame))
        self.wait(2)
