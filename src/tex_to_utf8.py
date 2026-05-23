

"""
TeX 公式到 UTF-8 字符翻译模块
用于在间隔复习和笔记分析中将 TeX 公式更友好地显示为 Unicode/UTF-8 字符
"""

import re


class TeXToUTF8:
    """TeX 公式到 UTF-8 字符翻译器"""

    # 希腊字母映射
    GREEK_LETTERS = {
        '\\alpha': 'α',
        '\\beta': 'β',
        '\\gamma': 'γ',
        '\\delta': 'δ',
        '\\epsilon': 'ε',
        '\\varepsilon': 'ε',
        '\\zeta': 'ζ',
        '\\eta': 'η',
        '\\theta': 'θ',
        '\\vartheta': 'θ',
        '\\iota': 'ι',
        '\\kappa': 'κ',
        '\\lambda': 'λ',
        '\\mu': 'μ',
        '\\nu': 'ν',
        '\\xi': 'ξ',
        '\\pi': 'π',
        '\\varpi': 'π',
        '\\rho': 'ρ',
        '\\varrho': 'ρ',
        '\\sigma': 'σ',
        '\\varsigma': 'ς',
        '\\tau': 'τ',
        '\\upsilon': 'υ',
        '\\phi': 'φ',
        '\\varphi': 'φ',
        '\\chi': 'χ',
        '\\psi': 'ψ',
        '\\omega': 'ω',
        '\\Alpha': 'Α',
        '\\Beta': 'Β',
        '\\Gamma': 'Γ',
        '\\Delta': 'Δ',
        '\\Epsilon': 'Ε',
        '\\Zeta': 'Ζ',
        '\\Eta': 'Η',
        '\\Theta': 'Θ',
        '\\Iota': 'Ι',
        '\\Kappa': 'Κ',
        '\\Lambda': 'Λ',
        '\\Mu': 'Μ',
        '\\Nu': 'Ν',
        '\\Xi': 'Ξ',
        '\\Pi': 'Π',
        '\\Rho': 'Ρ',
        '\\Sigma': 'Σ',
        '\\Tau': 'Τ',
        '\\Upsilon': 'Υ',
        '\\Phi': 'Φ',
        '\\Chi': 'Χ',
        '\\Psi': 'Ψ',
        '\\Omega': 'Ω',
    }

    # 数学符号映射
    MATH_SYMBOLS = {
        '\\le': '≤',
        '\\leq': '≤',
        '\\ge': '≥',
        '\\geq': '≥',
        '\\neq': '≠',
        '\\approx': '≈',
        '\\equiv': '≡',
        '\\sim': '~',
        '\\simeq': '≃',
        '\\cong': '≅',
        '\\prec': '≺',
        '\\succ': '≻',
        '\\preceq': '⪯',
        '\\succeq': '⪰',
        '\\subset': '⊂',
        '\\subseteq': '⊆',
        '\\supset': '⊃',
        '\\supseteq': '⊇',
        '\\in': '∈',
        '\\notin': '∉',
        '\\ni': '∋',
        '\\propto': '∝',
        '\\times': '×',
        '\\div': '÷',
        '\\pm': '±',
        '\\mp': '∓',
        '\\cdot': '·',
        '\\ast': '*',
        '\\star': '⋆',
        '\\circ': '∘',
        '\\bullet': '•',
        '\\oplus': '⊕',
        '\\ominus': '⊖',
        '\\otimes': '⊗',
        '\\oslash': '⊘',
        '\\odot': '⊙',
        '\\wedge': '∧',
        '\\vee': '∨',
        '\\cap': '∩',
        '\\cup': '∪',
        '\\setminus': '∖',
        '\\backslash': '∖',
        '\\leftarrow': '←',
        '\\rightarrow': '→',
        '\\to': '→',
        '\\leftrightarrow': '↔',
        '\\Leftarrow': '⇐',
        '\\Rightarrow': '⇒',
        '\\Leftrightarrow': '⇔',
        '\\mapsto': '↦',
        '\\hookrightarrow': '↪',
        '\\infty': '∞',
        '\\nabla': '∇',
        '\\partial': '∂',
        '\\forall': '∀',
        '\\exists': '∃',
        '\\nexists': '∄',
        '\\neg': '¬',
        '\\lnot': '¬',
        '\\land': '∧',
        '\\lor': '∨',
        '\\top': '⊤',
        '\\bot': '⊥',
        '\\vdash': '⊢',
        '\\models': '⊨',
        '\\angle': '∠',
        '\\measuredangle': '∡',
        '\\sphericalangle': '∢',
        '\\perp': '⊥',
        '\\parallel': '∥',
        '\\prime': '′',
        '\\hbar': 'ℏ',
        '\\ell': 'ℓ',
        '\\wp': '℘',
        '\\Re': 'ℜ',
        '\\Im': 'ℑ',
        '\\mho': '℧',
        '\\aleph': 'ℵ',
        '\\beth': 'ℶ',
        '\\gimel': 'ℷ',
        '\\daleth': 'ℸ',
        '\\emptyset': '∅',
        '\\varnothing': '∅',
        '\\dots': '…',
        '\\cdots': '⋯',
        '\\ldots': '…',
        '\\ddots': '⋱',
        '\\vdots': '⋮',
    }

    # 函数名映射
    FUNCTION_NAMES = {
        '\\sin': 'sin',
        '\\cos': 'cos',
        '\\tan': 'tan',
        '\\cot': 'cot',
        '\\sec': 'sec',
        '\\csc': 'csc',
        '\\arcsin': 'arcsin',
        '\\arccos': 'arccos',
        '\\arctan': 'arctan',
        '\\sinh': 'sinh',
        '\\cosh': 'cosh',
        '\\tanh': 'tanh',
        '\\coth': 'coth',
        '\\ln': 'ln',
        '\\log': 'log',
        '\\exp': 'exp',
        '\\lim': 'lim',
        '\\max': 'max',
        '\\min': 'min',
        '\\sup': 'sup',
        '\\inf': 'inf',
        '\\det': 'det',
        '\\dim': 'dim',
        '\\ker': 'ker',
        '\\rank': 'rank',
        '\\deg': 'deg',
        '\\gcd': 'gcd',
        '\\lcm': 'lcm',
        '\\hom': 'hom',
        '\\Hom': 'Hom',
        '\\id': 'id',
        '\\Id': 'Id',
        '\\mod': 'mod',
    }

    # 求和/积分等大运算符
    BIG_OPERATORS = {
        '\\sum': '∑',
        '\\prod': '∏',
        '\\coprod': '∐',
        '\\int': '∫',
        '\\oint': '∮',
        '\\iint': '∬',
        '\\iiint': '∭',
        '\\iiiint': '⨌',
        '\\bigcup': '⋃',
        '\\bigcap': '⋂',
        '\\bigsqcup': '⨆',
        '\\biguplus': '⨄',
        '\\bigvee': '⋁',
        '\\bigwedge': '⋀',
    }

    # 括号和分隔符
    DELIMITERS = {
        '\\{': '{',
        '\\}': '}',
        '\\|': '∥',
        '\\lfloor': '⌊',
        '\\rfloor': '⌋',
        '\\lceil': '⌈',
        '\\rceil': '⌉',
        '\\langle': '⟨',
        '\\rangle': '⟩',
        '\\vert': '|',
        '\\Vert': '∥',
    }

    # 数学字体映射
    MATH_FONTS = {
        '\\mathbb{R}': 'ℝ',
        '\\mathbb{C}': 'ℂ',
        '\\mathbb{Z}': 'ℤ',
        '\\mathbb{N}': 'ℕ',
        '\\mathbb{Q}': 'ℚ',
        '\\mathbb{P}': 'ℙ',
        '\\mathbb{E}': '𝔼',
        '\\mathbb{F}': '𝔽',
        '\\mathbb{B}': '𝔹',
        '\\mathbb{H}': 'ℍ',
        '\\mathbb{S}': '𝕊',
        '\\mathcal{L}': 'ℒ',
        '\\mathcal{O}': '𝒪',
        '\\mathcal{H}': 'ℋ',
        '\\mathcal{F}': 'ℱ',
        '\\mathcal{A}': '𝒜',
        '\\mathcal{B}': 'ℬ',
        '\\mathcal{C}': '𝒞',
        '\\mathcal{D}': '𝒟',
        '\\mathcal{E}': 'ℰ',
        '\\mathcal{G}': '𝒢',
        '\\mathcal{I}': 'ℐ',
        '\\mathcal{J}': '𝒥',
        '\\mathcal{K}': '𝒦',
        '\\mathcal{M}': 'ℳ',
        '\\mathcal{N}': '𝒩',
        '\\mathcal{P}': '𝒫',
        '\\mathcal{Q}': '𝒬',
        '\\mathcal{R}': 'ℛ',
        '\\mathcal{S}': '𝒮',
        '\\mathcal{T}': '𝒯',
        '\\mathcal{U}': '𝒰',
        '\\mathcal{V}': '𝒱',
        '\\mathcal{W}': '𝒲',
        '\\mathcal{X}': '𝒳',
        '\\mathcal{Y}': '𝒴',
        '\\mathcal{Z}': '𝒵',
    }

    # 粗体数学字母
    BOLD_LETTERS = {
        '\\mathbf{a}': '𝐚', '\\mathbf{b}': '𝐛', '\\mathbf{c}': '𝐜',
        '\\mathbf{d}': '𝐝', '\\mathbf{e}': '𝐞', '\\mathbf{f}': '𝐟',
        '\\mathbf{g}': '𝐠', '\\mathbf{h}': '𝐡', '\\mathbf{i}': '𝐢',
        '\\mathbf{j}': '𝐣', '\\mathbf{k}': '𝐤', '\\mathbf{l}': '𝐥',
        '\\mathbf{m}': '𝐦', '\\mathbf{n}': '𝐧', '\\mathbf{o}': '𝐨',
        '\\mathbf{p}': '𝐩', '\\mathbf{q}': '𝐪', '\\mathbf{r}': '𝐫',
        '\\mathbf{s}': '𝐬', '\\mathbf{t}': '𝐭', '\\mathbf{u}': '𝐮',
        '\\mathbf{v}': '𝐯', '\\mathbf{w}': '𝐰', '\\mathbf{x}': '𝐱',
        '\\mathbf{y}': '𝐲', '\\mathbf{z}': '𝐳',
        '\\mathbf{A}': '𝐀', '\\mathbf{B}': '𝐁', '\\mathbf{C}': '𝐂',
        '\\mathbf{D}': '𝐃', '\\mathbf{E}': '𝐄', '\\mathbf{F}': '𝐅',
        '\\mathbf{G}': '𝐆', '\\mathbf{H}': '𝐇', '\\mathbf{I}': '𝐈',
        '\\mathbf{J}': '𝐉', '\\mathbf{K}': '𝐊', '\\mathbf{L}': '𝐋',
        '\\mathbf{M}': '𝐌', '\\mathbf{N}': '𝐍', '\\mathbf{O}': '𝐎',
        '\\mathbf{P}': '𝐏', '\\mathbf{Q}': '𝐐', '\\mathbf{R}': '𝐑',
        '\\mathbf{S}': '𝐒', '\\mathbf{T}': '𝐓', '\\mathbf{U}': '𝐔',
        '\\mathbf{V}': '𝐕', '\\mathbf{W}': '𝐖', '\\mathbf{X}': '𝐗',
        '\\mathbf{Y}': '𝐘', '\\mathbf{Z}': '𝐙',
    }

    @staticmethod
    def translate_tex(text):
        """
        将文本中的 TeX 公式翻译为 UTF-8 字符
        
        Args:
            text: 包含 TeX 公式的文本
            
        Returns:
            翻译后的文本
        """
        if not text:
            return text
        
        # 保存换行符
        lines = text.split('\n')
        translated_lines = []
        
        for line in lines:
            result = line
            
            # 先处理 $$...$$ 显示公式
            def process_display_math(match):
                content = match.group(1)
                return ' ' + TeXToUTF8._translate_math(content) + ' '
            
            result = re.sub(r'\$\$([\s\S]*?)\$\$', lambda m: process_display_math(m), result)
            
            # 处理 $...$ 内联公式
            def process_inline_math(match):
                content = match.group(1)
                return ' ' + TeXToUTF8._translate_math(content) + ' '
            
            result = re.sub(r'\$([^$]+?)\$', lambda m: process_inline_math(m), result)
            
            # 处理 \(...\) 和 \[...\]
            result = re.sub(r'\\\(([\s\S]*?)\\\)', lambda m: ' ' + TeXToUTF8._translate_math(m.group(1)) + ' ', result)
            result = re.sub(r'\\\[([\s\S]*?)\\\]', lambda m: ' ' + TeXToUTF8._translate_math(m.group(1)) + ' ', result)
            
            # 最后处理不在公式环境中的独立命令
            result = TeXToUTF8._translate_general(result)
            
            # 清理多余的空格（但保持行内的单个空格）
            result = re.sub(r'[ \t]+', ' ', result).strip()
            
            translated_lines.append(result)
        
        # 重新组合换行符
        return '\n'.join(translated_lines)
    
    @staticmethod
    def _translate_math(content):
        """翻译数学环境内的内容"""
        if not content:
            return content
        
        result = content
        
        # 先处理各种复杂的嵌套结构，从内向外处理
        
        # 1. 处理 \left 和 \right 括号
        result = TeXToUTF8._handle_delimiters(result)
        
        # 2. 处理数学字体命令 (\mathcal, \mathbb, \mathbf等)
        result = TeXToUTF8._handle_math_fonts(result)
        
        # 3. 处理 operatorname 和其他函数
        result = TeXToUTF8._handle_operatorname(result)
        
        # 4. 收集所有替换，按长度降序排序避免短匹配先替换长匹配
        all_replacements = []
        all_replacements.extend(TeXToUTF8.MATH_FONTS.items())
        all_replacements.extend(TeXToUTF8.BOLD_LETTERS.items())
        all_replacements.extend(TeXToUTF8.GREEK_LETTERS.items())
        all_replacements.extend(TeXToUTF8.MATH_SYMBOLS.items())
        all_replacements.extend(TeXToUTF8.FUNCTION_NAMES.items())
        all_replacements.extend(TeXToUTF8.BIG_OPERATORS.items())
        all_replacements.extend(TeXToUTF8.DELIMITERS.items())
        
        # 按长度降序排序，确保长的模式先被替换
        all_replacements.sort(key=lambda x: -len(x[0]))
        
        # 执行替换
        for tex, utf8 in all_replacements:
            result = TeXToUTF8._safe_replace(result, tex, utf8)
        
        # 处理简单的上下标
        result = TeXToUTF8._simple_subsuperscript(result)
        
        # 处理分数
        result = TeXToUTF8._simple_fractions(result)
        
        # 处理平方根
        result = TeXToUTF8._simple_sqrt(result)
        
        # 清理大括号
        result = result.replace('{', '').replace('}', '')
        
        return result
    
    @staticmethod
    def _safe_replace(text, old, new):
        """安全地替换字符串，避免部分匹配"""
        result = text
        idx = 0
        while True:
            pos = result.find(old, idx)
            if pos == -1:
                break
            # 检查是否是完整单词（避免部分匹配）
            prev_ok = pos == 0 or not result[pos-1].isalnum() and result[pos-1] not in '\\'
            next_pos = pos + len(old)
            next_ok = next_pos >= len(result) or not result[next_pos].isalnum()
            
            if prev_ok and next_ok:
                result = result[:pos] + new + result[next_pos:]
                idx = pos + len(new)
            else:
                idx = pos + 1
        return result
    
    @staticmethod
    def _handle_delimiters(text):
        """处理 \left 和 \right 等分隔符"""
        result = text
        # 移除 \left 和 \right 前缀
        result = result.replace('\\left', '').replace('\\right', '')
        return result
    
    @staticmethod
    def _handle_math_fonts(text):
        """处理数学字体命令"""
        result = text
        
        # 处理 \mathrm{...} - 罗马字体，直接显示内容
        def replace_mathrm(match):
            content = match.group(1)
            return content
        
        result = re.sub(r'\\mathrm\{([^}]+)\}', replace_mathrm, result)
        
        # 处理 \mathcal{X}
        def replace_mathcal(match):
            char = match.group(1)
            mapping = {
                'A': '𝒜', 'B': 'ℬ', 'C': '𝒞', 'D': '𝒟', 'E': 'ℰ',
                'F': 'ℱ', 'G': '𝒢', 'H': 'ℋ', 'I': 'ℐ', 'J': '𝒥',
                'K': '𝒦', 'L': 'ℒ', 'M': 'ℳ', 'N': '𝒩', 'O': '𝒪',
                'P': '𝒫', 'Q': '𝒬', 'R': 'ℛ', 'S': '𝒮', 'T': '𝒯',
                'U': '𝒰', 'V': '𝒱', 'W': '𝒲', 'X': '𝒳', 'Y': '𝒴', 'Z': '𝒵',
                'l': 'ℓ', 'h': 'ℏ',
            }
            return mapping.get(char, char)
        
        result = re.sub(r'\\mathcal\{([A-Za-z])\}', replace_mathcal, result)
        
        # 处理 \mathbb{X}
        def replace_mathbb(match):
            char = match.group(1)
            mapping = {
                'R': 'ℝ', 'C': 'ℂ', 'Z': 'ℤ', 'N': 'ℕ',
                'Q': 'ℚ', 'P': 'ℙ', 'E': '𝔼', 'F': '𝔽',
                'B': '𝔹', 'H': 'ℍ', 'S': '𝕊',
            }
            return mapping.get(char, char)
        
        result = re.sub(r'\\mathbb\{([A-Za-z])\}', replace_mathbb, result)
        
        # 处理 \mathbf{X}
        def replace_mathbf(match):
            char = match.group(1)
            lowercase = {
                'a': '𝐚', 'b': '𝐛', 'c': '𝐜', 'd': '𝐝', 'e': '𝐞',
                'f': '𝐟', 'g': '𝐠', 'h': '𝐡', 'i': '𝐢', 'j': '𝐣',
                'k': '𝐤', 'l': '𝐥', 'm': '𝐦', 'n': '𝐧', 'o': '𝐨',
                'p': '𝐩', 'q': '𝐪', 'r': '𝐫', 's': '𝐬', 't': '𝐭',
                'u': '𝐮', 'v': '𝐯', 'w': '𝐰', 'x': '𝐱', 'y': '𝐲', 'z': '𝐳',
            }
            uppercase = {
                'A': '𝐀', 'B': '𝐁', 'C': '𝐂', 'D': '𝐃', 'E': '𝐄',
                'F': '𝐅', 'G': '𝐆', 'H': '𝐇', 'I': '𝐈', 'J': '𝐉',
                'K': '𝐊', 'L': '𝐋', 'M': '𝐌', 'N': '𝐍', 'O': '𝐎',
                'P': '𝐏', 'Q': '𝐐', 'R': '𝐑', 'S': '𝐒', 'T': '𝐓',
                'U': '𝐔', 'V': '𝐕', 'W': '𝐖', 'X': '𝐗', 'Y': '𝐘', 'Z': '𝐙',
            }
            if char in lowercase:
                return lowercase[char]
            elif char in uppercase:
                return uppercase[char]
            return char
        
        result = re.sub(r'\\mathbf\{([A-Za-z])\}', replace_mathbf, result)
        
        return result
    
    @staticmethod
    def _handle_operatorname(text):
        """处理 \operatorname{...} 命令"""
        result = text
        result = re.sub(r'\\operatorname\{([^}]+)\}', r'\1', result)
        result = re.sub(r'\\text\{([^}]+)\}', r'\1', result)
        return result
    
    @staticmethod
    def _simple_subsuperscript(text):
        """简单的上下标处理，更好的嵌套支持"""
        superscripts = {
            '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', 
            '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
            '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
            'i': 'ⁱ', 'n': 'ⁿ', 'm': 'ᵐ', 't': 'ᵗ', 's': 'ˢ',
            'T': 'ᵀ', '*': '⋆',
        }
        subscripts = {
            '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄', 
            '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
            '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
            'i': 'ᵢ', 'n': 'ₙ', 'm': 'ₘ', 't': 'ₜ', 's': 'ₛ',
        }
        
        result = text
        
        # 先处理简单的 ^{...}
        def replace_superscript(match):
            inside = match.group(1)
            output = ''
            for c in inside:
                if c in superscripts:
                    output += superscripts[c]
                else:
                    output += c
            return '^' + output
        
        result = re.sub(r'\^\{([^}]+)\}', replace_superscript, result)
        
        # 处理简单的 ^x
        def replace_simple_sup(match):
            c = match.group(1)
            if c in superscripts:
                return superscripts[c]
            return '^' + c
        
        result = re.sub(r'\^([a-zA-Z0-9+\-*])', replace_simple_sup, result)
        
        # 处理简单的 _{...}
        def replace_subscript(match):
            inside = match.group(1)
            output = ''
            for c in inside:
                if c in subscripts:
                    output += subscripts[c]
                else:
                    output += c
            return '_' + output
        
        result = re.sub(r'_\{([^}]+)\}', replace_subscript, result)
        
        # 处理简单的 _x
        def replace_simple_sub(match):
            c = match.group(1)
            if c in subscripts:
                return subscripts[c]
            return '_' + c
        
        result = re.sub(r'_([a-zA-Z0-9+\-*])', replace_simple_sub, result)
        
        return result
    
    @staticmethod
    def _simple_fractions(text):
        """简单的分数处理"""
        def replace_fraction(match):
            num = match.group(1)
            den = match.group(2)
            simple = {
                ('1','2'): '½', ('1','3'): '⅓', ('2','3'): '⅔',
                ('1','4'): '¼', ('3','4'): '¾', ('1','5'): '⅕',
                ('2','5'): '⅖', ('3','5'): '⅗', ('4','5'): '⅘',
                ('1','6'): '⅙', ('5','6'): '⅚', ('1','8'): '⅛',
                ('3','8'): '⅜', ('5','8'): '⅝', ('7','8'): '⅞',
            }
            if (num, den) in simple:
                return simple[(num, den)]
            return f'{num}/{den}'
        
        return re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', replace_fraction, text)
    
    @staticmethod
    def _simple_sqrt(text):
        """简单的平方根处理"""
        result = re.sub(r'\\sqrt\{([^}]+)\}', r'√\1', text)
        result = result.replace(r'\sqrt', '√')
        return result
    
    @staticmethod
    def _translate_general(text):
        """翻译不在公式环境中的内容"""
        result = text
        
        # 先处理数学字体
        result = TeXToUTF8._handle_math_fonts(result)
        result = TeXToUTF8._handle_operatorname(result)
        
        # 和之前一样，替换各种命令
        all_replacements = []
        all_replacements.extend(TeXToUTF8.MATH_FONTS.items())
        all_replacements.extend(TeXToUTF8.BOLD_LETTERS.items())
        all_replacements.extend(TeXToUTF8.GREEK_LETTERS.items())
        all_replacements.extend(TeXToUTF8.MATH_SYMBOLS.items())
        all_replacements.extend(TeXToUTF8.FUNCTION_NAMES.items())
        all_replacements.extend(TeXToUTF8.BIG_OPERATORS.items())
        all_replacements.extend(TeXToUTF8.DELIMITERS.items())
        all_replacements.sort(key=lambda x: -len(x[0]))
        
        for tex, utf8 in all_replacements:
            result = TeXToUTF8._safe_replace(result, tex, utf8)
        
        return result
    
    @staticmethod
    def translate_for_display(text, enable_translation=True):
        """
        为显示目的翻译 TeX 公式的便捷函数
        
        Args:
            text: 原始文本
            enable_translation: 是否启用翻译
            
        Returns:
            翻译后的文本
        """
        if not enable_translation:
            return text
        return TeXToUTF8.translate_tex(text)

