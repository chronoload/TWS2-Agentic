/**
 * Vditor 编辑器自动补全数据模块
 * 支持：LaTeX 公式、代码片段、自定义关键词字典
 */

// ─── LaTeX 命令补全数据 ────────────────────────────────────────
export const LATEX_COMMANDS: Record<string, string> = {
  // 希腊字母
  'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ε',
  'varepsilon': 'ε', 'zeta': 'ζ', 'eta': 'η', 'theta': 'θ', 'vartheta': 'ϑ',
  'iota': 'ι', 'kappa': 'κ', 'lambda': 'λ', 'mu': 'μ', 'nu': 'ν',
  'xi': 'ξ', 'pi': 'π', 'varpi': 'ϖ', 'rho': 'ρ', 'varrho': 'ϱ',
  'sigma': 'σ', 'varsigma': 'ς', 'tau': 'τ', 'upsilon': 'υ', 'phi': 'φ',
  'varphi': 'ϕ', 'chi': 'χ', 'psi': 'ψ', 'omega': 'ω',
  'Gamma': 'Γ', 'Delta': 'Δ', 'Theta': 'Θ', 'Lambda': 'Λ', 'Xi': 'Ξ',
  'Pi': 'Π', 'Sigma': 'Σ', 'Upsilon': 'Υ', 'Phi': 'Φ', 'Psi': 'Ψ', 'Omega': 'Ω',
  // 运算符
  'frac': '\\frac{a}{b}', 'dfrac': '\\dfrac{a}{b}', 'sqrt': '\\sqrt{x}',
  'sum': '\\sum_{i=1}^{n}', 'prod': '\\prod_{i=1}^{n}', 'int': '\\int_{a}^{b}',
  'iint': '\\iint', 'iiint': '\\iiint', 'oint': '\\oint',
  'lim': '\\lim_{x \\to }', 'sup': '\\sup', 'inf': '\\inf',
  'max': '\\max', 'min': '\\min',
  // 关系
  'leq': '≤', 'geq': '≥', 'neq': '≠', 'approx': '≈', 'equiv': '≡',
  'sim': '∼', 'simeq': '≃', 'll': '≪', 'gg': '≫', 'propto': '∝',
  'perp': '⊥', 'parallel': '∥', 'in': '∈', 'notin': '∉',
  'subset': '⊂', 'supset': '⊃', 'subseteq': '⊆', 'supseteq': '⊇',
  'cup': '∪', 'cap': '∩', 'emptyset': '∅',
  // 箭头
  'rightarrow': '→', 'leftarrow': '←', 'leftrightarrow': '↔',
  'Rightarrow': '⇒', 'Leftarrow': '⇐', 'Leftrightarrow': '⇔',
  'uparrow': '↑', 'downarrow': '↓',
  'mapsto': '↦', 'implies': '⟹', 'iff': '⟺',
  // 函数
  'sin': '\\sin', 'cos': '\\cos', 'tan': '\\tan', 'cot': '\\cot',
  'sec': '\\sec', 'csc': '\\csc', 'arcsin': '\\arcsin', 'arccos': '\\arccos',
  'arctan': '\\arctan', 'sinh': '\\sinh', 'cosh': '\\cosh', 'tanh': '\\tanh',
  'ln': '\\ln', 'log': '\\log', 'exp': '\\exp', 'det': '\\det',
  'dim': '\\dim', 'ker': '\\ker', 'deg': '\\deg',
  // 格式
  'hat': '\\hat{x}', 'bar': '\\bar{x}', 'vec': '\\vec{x}',
  'dot': '\\dot{x}', 'ddot': '\\ddot{x}', 'tilde': '\\tilde{x}',
  'overline': '\\overline{x}', 'underline': '\\underline{x}',
  'overbrace': '\\overbrace{x}^{n}', 'underbrace': '\\underbrace{x}_{n}',
  'widehat': '\\widehat{x}', 'widetilde': '\\widetilde{x}',
  'mathbf': '\\mathbf{x}', 'mathbb': '\\mathbb{R}', 'mathcal': '\\mathcal{L}',
  'mathrm': '\\mathrm{x}', 'mathit': '\\mathit{x}', 'mathsf': '\\mathsf{x}',
  'mathtt': '\\mathtt{x}',
  // 矩阵/多行
  'begin': '\\begin{aligned}\n\n\\end{aligned}',
  'matrix': '\\begin{matrix}\na & b \\\\\nc & d\n\\end{matrix}',
  'pmatrix': '\\begin{pmatrix}\na & b \\\\\nc & d\n\\end{pmatrix}',
  'bmatrix': '\\begin{bmatrix}\na & b \\\\\nc & d\n\\end{bmatrix}',
  'vmatrix': '\\begin{vmatrix}\na & b \\\\\nc & d\n\\end{vmatrix}',
  'cases': '\\begin{cases}\na, & \\text{if } x > 0 \\\\\nb, & \\text{otherwise}\n\\end{cases}',
  'aligned': '\\begin{aligned}\na &= b + c \\\\\n  &= d + e\n\\end{aligned}',
  // 物理
  'nabla': '∇', 'partial': '∂', 'infty': '∞',
  'hbar': 'ℏ', 'ell': 'ℓ', 'Re': 'ℜ', 'Im': 'ℑ',
  'forall': '∀', 'exists': '∃',
  'text': '\\text{}', 'quad': '\\quad', 'qquad': '\\qquad',
  'cdots': '⋯', 'ldots': '…', 'vdots': '⋮', 'ddots': '⋱',
  // 装饰
  'boxed': '\\boxed{x}', 'cancel': '\\cancel{x}',
  'color': '\\color{red}{x}',
}

// ─── 代码片段补全数据 ──────────────────────────────────────────
export const SNIPPETS: Record<string, string> = {
  'table': '| 列1 | 列2 | 列3 |\n| --- | --- | --- |\n|  |  |  |\n|  |  |  |',
  'table4': '| 列1 | 列2 | 列3 | 列4 |\n| --- | --- | --- | --- |\n|  |  |  |  |',
  'math': '$$\n\n$$',
  'mathinline': '$ $',
  'code': '```\n\n```',
  'codepython': '```python\n\n```',
  'codejs': '```javascript\n\n```',
  'codejson': '```json\n\n```',
  'codecpp': '```cpp\n\n```',
  'codejava': '```java\n\n```',
  'quote': '> ',
  'task': '- [ ] ',
  'taskdone': '- [x] ',
  'h1': '# ',
  'h2': '## ',
  'h3': '### ',
  'h4': '#### ',
  'hr': '---',
  'img': '![描述](url)',
  'link': '[文本](url)',
  'bold': '**粗体**',
  'italic': '*斜体*',
  'strike': '~~删除线~~',
  'details': '<details>\n<summary>标题</summary>\n\n内容\n\n</details>',
  'mermaid': '```mermaid\ngraph TD\n    A --> B\n```',
  'flowchart': '```mermaid\nflowchart TD\n    Start --> Stop\n```',
}

// ─── 内置学科名词字典 ──────────────────────────────────────────
export interface DictEntry {
  keyword: string   // 触发关键词
  value: string     // 插入值
  desc?: string     // 描述/说明
}

export interface DictGroup {
  name: string      // 字典名（如"数学名词"）
  enabled: boolean  // 是否启用
  entries: DictEntry[]
}

// 数学名词（中文）
export const DICT_MATH_ZH: DictEntry[] = [
  { keyword: '极限', value: '极限', desc: 'lim' },
  { keyword: '导数', value: '导数', desc: "f'(x)" },
  { keyword: '偏导', value: '偏导数', desc: '∂f/∂x' },
  { keyword: '积分', value: '积分', desc: '∫' },
  { keyword: '定积分', value: '定积分', desc: '∫ₐᵇ' },
  { keyword: '级数', value: '级数', desc: 'Σ' },
  { keyword: '收敛', value: '收敛' },
  { keyword: '发散', value: '发散' },
  { keyword: '矩阵', value: '矩阵', desc: 'A ∈ ℝᵐˣⁿ' },
  { keyword: '行列式', value: '行列式', desc: 'det(A)' },
  { keyword: '特征值', value: '特征值', desc: 'λ' },
  { keyword: '特征向量', value: '特征向量' },
  { keyword: '线性变换', value: '线性变换' },
  { keyword: '向量空间', value: '向量空间' },
  { keyword: '正交', value: '正交' },
  { keyword: '对称', value: '对称' },
  { keyword: '概率', value: '概率', desc: 'P(A)' },
  { keyword: '期望', value: '期望', desc: 'E[X]' },
  { keyword: '方差', value: '方差', desc: 'Var(X)' },
  { keyword: '协方差', value: '协方差', desc: 'Cov(X,Y)' },
  { keyword: '正态分布', value: '正态分布', desc: 'N(μ,σ²)' },
  { keyword: '泊松分布', value: '泊松分布', desc: 'Poisson(λ)' },
  { keyword: '拓扑', value: '拓扑' },
  { keyword: '同构', value: '同构' },
  { keyword: '同态', value: '同态' },
  { keyword: '群', value: '群' },
  { keyword: '环', value: '环' },
  { keyword: '域', value: '域' },
  { keyword: '范数', value: '范数', desc: '‖x‖' },
  { keyword: '内积', value: '内积', desc: '⟨x,y⟩' },
  { keyword: '傅里叶变换', value: '傅里叶变换', desc: 'F(ω)' },
  { keyword: '拉普拉斯变换', value: '拉普拉斯变换', desc: 'L(s)' },
  { keyword: '泰勒展开', value: '泰勒展开' },
  { keyword: '微分方程', value: '微分方程' },
  { keyword: '偏微分方程', value: '偏微分方程' },
  { keyword: '常微分方程', value: '常微分方程' },
]

// 数学名词（英文）
export const DICT_MATH_EN: DictEntry[] = [
  { keyword: 'limit', value: 'limit', desc: 'lim' },
  { keyword: 'derivative', value: 'derivative', desc: "f'(x)" },
  { keyword: 'partial', value: 'partial derivative', desc: '∂f/∂x' },
  { keyword: 'integral', value: 'integral', desc: '∫' },
  { keyword: 'definite integral', value: 'definite integral', desc: '∫ₐᵇ' },
  { keyword: 'series', value: 'series', desc: 'Σ' },
  { keyword: 'convergent', value: 'convergent' },
  { keyword: 'divergent', value: 'divergent' },
  { keyword: 'matrix', value: 'matrix', desc: 'A ∈ ℝᵐˣⁿ' },
  { keyword: 'determinant', value: 'determinant', desc: 'det(A)' },
  { keyword: 'eigenvalue', value: 'eigenvalue', desc: 'λ' },
  { keyword: 'eigenvector', value: 'eigenvector' },
  { keyword: 'linear transformation', value: 'linear transformation' },
  { keyword: 'vector space', value: 'vector space' },
  { keyword: 'orthogonal', value: 'orthogonal' },
  { keyword: 'symmetric', value: 'symmetric' },
  { keyword: 'probability', value: 'probability', desc: 'P(A)' },
  { keyword: 'expectation', value: 'expectation', desc: 'E[X]' },
  { keyword: 'variance', value: 'variance', desc: 'Var(X)' },
  { keyword: 'covariance', value: 'covariance', desc: 'Cov(X,Y)' },
  { keyword: 'normal distribution', value: 'normal distribution', desc: 'N(μ,σ²)' },
  { keyword: 'Poisson distribution', value: 'Poisson distribution', desc: 'Poisson(λ)' },
  { keyword: 'topology', value: 'topology' },
  { keyword: 'isomorphism', value: 'isomorphism' },
  { keyword: 'homomorphism', value: 'homomorphism' },
  { keyword: 'group', value: 'group' },
  { keyword: 'ring', value: 'ring' },
  { keyword: 'field', value: 'field' },
  { keyword: 'norm', value: 'norm', desc: '‖x‖' },
  { keyword: 'inner product', value: 'inner product', desc: '⟨x,y⟩' },
  { keyword: 'Fourier transform', value: 'Fourier transform', desc: 'F(ω)' },
  { keyword: 'Laplace transform', value: 'Laplace transform', desc: 'L(s)' },
  { keyword: 'Taylor expansion', value: 'Taylor expansion' },
  { keyword: 'differential equation', value: 'differential equation' },
  { keyword: 'PDE', value: 'partial differential equation' },
  { keyword: 'ODE', value: 'ordinary differential equation' },
]

// 物理名词（中文）
export const DICT_PHYSICS_ZH: DictEntry[] = [
  { keyword: '牛顿定律', value: '牛顿定律' },
  { keyword: '动量', value: '动量', desc: 'p = mv' },
  { keyword: '角动量', value: '角动量', desc: 'L = r × p' },
  { keyword: '能量', value: '能量', desc: 'E' },
  { keyword: '动能', value: '动能', desc: 'Eₖ = ½mv²' },
  { keyword: '势能', value: '势能', desc: 'Eₚ' },
  { keyword: '守恒', value: '守恒' },
  { keyword: '力', value: '力', desc: 'F = ma' },
  { keyword: '引力', value: '万有引力', desc: 'F = GMm/r²' },
  { keyword: '电磁', value: '电磁' },
  { keyword: '电场', value: '电场', desc: 'E' },
  { keyword: '磁场', value: '磁场', desc: 'B' },
  { keyword: '电磁感应', value: '电磁感应', desc: 'ε = -dΦ/dt' },
  { keyword: '麦克斯韦方程', value: '麦克斯韦方程组' },
  { keyword: '波动', value: '波动' },
  { keyword: '干涉', value: '干涉' },
  { keyword: '衍射', value: '衍射' },
  { keyword: '偏振', value: '偏振' },
  { keyword: '热力学', value: '热力学' },
  { keyword: '熵', value: '熵', desc: 'S' },
  { keyword: '焓', value: '焓', desc: 'H' },
  { keyword: '自由能', value: '自由能', desc: 'G, F' },
  { keyword: '量子', value: '量子' },
  { keyword: '波函数', value: '波函数', desc: 'ψ' },
  { keyword: '薛定谔方程', value: '薛定谔方程', desc: 'iℏ∂ψ/∂t = Ĥψ' },
  { keyword: '不确定性原理', value: '不确定性原理', desc: 'ΔxΔp ≥ ℏ/2' },
  { keyword: '自旋', value: '自旋' },
  { keyword: '相对论', value: '相对论' },
  { keyword: '洛伦兹变换', value: '洛伦兹变换' },
  { keyword: '质能方程', value: '质能方程', desc: 'E = mc²' },
  { keyword: '黑洞', value: '黑洞' },
  { keyword: '哈密顿量', value: '哈密顿量', desc: 'Ĥ' },
  { keyword: '拉格朗日量', value: '拉格朗日量', desc: 'L' },
  { keyword: '张量', value: '张量' },
  { keyword: '散射', value: '散射' },
  { keyword: '衰变', value: '衰变' },
  { keyword: '光谱', value: '光谱' },
  { keyword: '能级', value: '能级' },
  { keyword: '费米子', value: '费米子' },
  { keyword: '玻色子', value: '玻色子' },
  { keyword: '规范场', value: '规范场' },
  { keyword: '对称性破缺', value: '对称性破缺' },
  { keyword: '超导', value: '超导' },
  { keyword: '声子', value: '声子' },
  { keyword: '等离子体', value: '等离子体' },
]

// 物理名词（英文）
export const DICT_PHYSICS_EN: DictEntry[] = [
  { keyword: "Newton's laws", value: "Newton's laws" },
  { keyword: 'momentum', value: 'momentum', desc: 'p = mv' },
  { keyword: 'angular momentum', value: 'angular momentum', desc: 'L = r × p' },
  { keyword: 'energy', value: 'energy', desc: 'E' },
  { keyword: 'kinetic energy', value: 'kinetic energy', desc: 'Eₖ = ½mv²' },
  { keyword: 'potential energy', value: 'potential energy', desc: 'Eₚ' },
  { keyword: 'conservation', value: 'conservation' },
  { keyword: 'force', value: 'force', desc: 'F = ma' },
  { keyword: 'gravitation', value: 'gravitation', desc: 'F = GMm/r²' },
  { keyword: 'electromagnetic', value: 'electromagnetic' },
  { keyword: 'electric field', value: 'electric field', desc: 'E' },
  { keyword: 'magnetic field', value: 'magnetic field', desc: 'B' },
  { keyword: 'electromagnetic induction', value: 'electromagnetic induction', desc: 'ε = -dΦ/dt' },
  { keyword: "Maxwell's equations", value: "Maxwell's equations" },
  { keyword: 'wave', value: 'wave' },
  { keyword: 'interference', value: 'interference' },
  { keyword: 'diffraction', value: 'diffraction' },
  { keyword: 'polarization', value: 'polarization' },
  { keyword: 'thermodynamics', value: 'thermodynamics' },
  { keyword: 'entropy', value: 'entropy', desc: 'S' },
  { keyword: 'enthalpy', value: 'enthalpy', desc: 'H' },
  { keyword: 'free energy', value: 'free energy', desc: 'G, F' },
  { keyword: 'quantum', value: 'quantum' },
  { keyword: 'wave function', value: 'wave function', desc: 'ψ' },
  { keyword: 'Schrödinger equation', value: 'Schrödinger equation', desc: 'iℏ∂ψ/∂t = Ĥψ' },
  { keyword: 'uncertainty principle', value: 'uncertainty principle', desc: 'ΔxΔp ≥ ℏ/2' },
  { keyword: 'spin', value: 'spin' },
  { keyword: 'relativity', value: 'relativity' },
  { keyword: 'Lorentz transformation', value: 'Lorentz transformation' },
  { keyword: 'mass-energy equivalence', value: 'mass-energy equivalence', desc: 'E = mc²' },
  { keyword: 'black hole', value: 'black hole' },
  { keyword: 'Hamiltonian', value: 'Hamiltonian', desc: 'Ĥ' },
  { keyword: 'Lagrangian', value: 'Lagrangian', desc: 'L' },
  { keyword: 'tensor', value: 'tensor' },
  { keyword: 'scattering', value: 'scattering' },
  { keyword: 'decay', value: 'decay' },
  { keyword: 'spectrum', value: 'spectrum' },
  { keyword: 'energy level', value: 'energy level' },
  { keyword: 'fermion', value: 'fermion' },
  { keyword: 'boson', value: 'boson' },
  { keyword: 'gauge field', value: 'gauge field' },
  { keyword: 'symmetry breaking', value: 'symmetry breaking' },
  { keyword: 'superconductivity', value: 'superconductivity' },
  { keyword: 'phonon', value: 'phonon' },
  { keyword: 'plasma', value: 'plasma' },
]

// 生物名词（中文）
export const DICT_BIOLOGY_ZH: DictEntry[] = [
  { keyword: '细胞', value: '细胞' },
  { keyword: '细胞核', value: '细胞核' },
  { keyword: '线粒体', value: '线粒体' },
  { keyword: '叶绿体', value: '叶绿体' },
  { keyword: '内质网', value: '内质网' },
  { keyword: '高尔基体', value: '高尔基体' },
  { keyword: '蛋白质', value: '蛋白质' },
  { keyword: '氨基酸', value: '氨基酸' },
  { keyword: '酶', value: '酶' },
  { keyword: '基因', value: '基因' },
  { keyword: '基因组', value: '基因组' },
  { keyword: '转录', value: '转录' },
  { keyword: '翻译', value: '翻译' },
  { keyword: '复制', value: '复制' },
  { keyword: '突变', value: '突变' },
  { keyword: '表达', value: '表达' },
  { keyword: '调控', value: '调控' },
  { keyword: '信号转导', value: '信号转导' },
  { keyword: '细胞分裂', value: '细胞分裂' },
  { keyword: '有丝分裂', value: '有丝分裂' },
  { keyword: '减数分裂', value: '减数分裂' },
  { keyword: '光合作用', value: '光合作用' },
  { keyword: '呼吸作用', value: '呼吸作用' },
  { keyword: '进化', value: '进化' },
  { keyword: '自然选择', value: '自然选择' },
  { keyword: '遗传', value: '遗传' },
  { keyword: '表观遗传', value: '表观遗传' },
  { keyword: '生态', value: '生态' },
  { keyword: '种群', value: '种群' },
  { keyword: '群落', value: '群落' },
  { keyword: '生态系统', value: '生态系统' },
  { keyword: '多样性', value: '多样性' },
  { keyword: '免疫', value: '免疫' },
  { keyword: '抗体', value: '抗体' },
  { keyword: '抗原', value: '抗原' },
  { keyword: '干细胞', value: '干细胞' },
  { keyword: '凋亡', value: '凋亡' },
  { keyword: '自噬', value: '自噬' },
]

// 生物名词（英文）
export const DICT_BIOLOGY_EN: DictEntry[] = [
  { keyword: 'cell', value: 'cell' },
  { keyword: 'nucleus', value: 'nucleus' },
  { keyword: 'mitochondrion', value: 'mitochondrion' },
  { keyword: 'chloroplast', value: 'chloroplast' },
  { keyword: 'endoplasmic reticulum', value: 'endoplasmic reticulum' },
  { keyword: 'Golgi apparatus', value: 'Golgi apparatus' },
  { keyword: 'protein', value: 'protein' },
  { keyword: 'amino acid', value: 'amino acid' },
  { keyword: 'enzyme', value: 'enzyme' },
  { keyword: 'gene', value: 'gene' },
  { keyword: 'genome', value: 'genome' },
  { keyword: 'transcription', value: 'transcription' },
  { keyword: 'translation', value: 'translation' },
  { keyword: 'replication', value: 'replication' },
  { keyword: 'mutation', value: 'mutation' },
  { keyword: 'expression', value: 'expression' },
  { keyword: 'regulation', value: 'regulation' },
  { keyword: 'signal transduction', value: 'signal transduction' },
  { keyword: 'cell division', value: 'cell division' },
  { keyword: 'mitosis', value: 'mitosis' },
  { keyword: 'meiosis', value: 'meiosis' },
  { keyword: 'photosynthesis', value: 'photosynthesis' },
  { keyword: 'respiration', value: 'respiration' },
  { keyword: 'evolution', value: 'evolution' },
  { keyword: 'natural selection', value: 'natural selection' },
  { keyword: 'heredity', value: 'heredity' },
  { keyword: 'epigenetics', value: 'epigenetics' },
  { keyword: 'ecology', value: 'ecology' },
  { keyword: 'population', value: 'population' },
  { keyword: 'community', value: 'community' },
  { keyword: 'ecosystem', value: 'ecosystem' },
  { keyword: 'diversity', value: 'diversity' },
  { keyword: 'immunity', value: 'immunity' },
  { keyword: 'antibody', value: 'antibody' },
  { keyword: 'antigen', value: 'antigen' },
  { keyword: 'stem cell', value: 'stem cell' },
  { keyword: 'apoptosis', value: 'apoptosis' },
  { keyword: 'autophagy', value: 'autophagy' },
]

// 化学名词（中文）
export const DICT_CHEMISTRY_ZH: DictEntry[] = [
  { keyword: '原子', value: '原子' },
  { keyword: '分子', value: '分子' },
  { keyword: '离子', value: '离子' },
  { keyword: '化学键', value: '化学键' },
  { keyword: '共价键', value: '共价键' },
  { keyword: '离子键', value: '离子键' },
  { keyword: '氢键', value: '氢键' },
  { keyword: '氧化', value: '氧化' },
  { keyword: '还原', value: '还原' },
  { keyword: '催化剂', value: '催化剂' },
  { keyword: '反应速率', value: '反应速率' },
  { keyword: '平衡', value: '化学平衡' },
  { keyword: '电离', value: '电离' },
  { keyword: '电解', value: '电解' },
  { keyword: '聚合', value: '聚合' },
  { keyword: '有机化学', value: '有机化学' },
  { keyword: '无机化学', value: '无机化学' },
  { keyword: '配位', value: '配位' },
  { keyword: '晶体', value: '晶体' },
  { keyword: '同位素', value: '同位素' },
]

// 化学名词（英文）
export const DICT_CHEMISTRY_EN: DictEntry[] = [
  { keyword: 'atom', value: 'atom' },
  { keyword: 'molecule', value: 'molecule' },
  { keyword: 'ion', value: 'ion' },
  { keyword: 'chemical bond', value: 'chemical bond' },
  { keyword: 'covalent bond', value: 'covalent bond' },
  { keyword: 'ionic bond', value: 'ionic bond' },
  { keyword: 'hydrogen bond', value: 'hydrogen bond' },
  { keyword: 'oxidation', value: 'oxidation' },
  { keyword: 'reduction', value: 'reduction' },
  { keyword: 'catalyst', value: 'catalyst' },
  { keyword: 'reaction rate', value: 'reaction rate' },
  { keyword: 'chemical equilibrium', value: 'chemical equilibrium' },
  { keyword: 'ionization', value: 'ionization' },
  { keyword: 'electrolysis', value: 'electrolysis' },
  { keyword: 'polymerization', value: 'polymerization' },
  { keyword: 'organic chemistry', value: 'organic chemistry' },
  { keyword: 'inorganic chemistry', value: 'inorganic chemistry' },
  { keyword: 'coordination', value: 'coordination' },
  { keyword: 'crystal', value: 'crystal' },
  { keyword: 'isotope', value: 'isotope' },
]

// 默认字典组：中文 @ 触发，英文 & 触发
export const DEFAULT_DICT_GROUPS: DictGroup[] = [
  { name: '数学名词（中文）', enabled: true, entries: DICT_MATH_ZH },
  { name: '物理名词（中文）', enabled: true, entries: DICT_PHYSICS_ZH },
  { name: '生物名词（中文）', enabled: false, entries: DICT_BIOLOGY_ZH },
  { name: '化学名词（中文）', enabled: false, entries: DICT_CHEMISTRY_ZH },
  { name: '数学名词（English）', enabled: true, entries: DICT_MATH_EN },
  { name: '物理名词（English）', enabled: true, entries: DICT_PHYSICS_EN },
  { name: '生物名词（English）', enabled: false, entries: DICT_BIOLOGY_EN },
  { name: '化学名词（English）', enabled: false, entries: DICT_CHEMISTRY_EN },
]

// ─── 自动补全配置管理 ──────────────────────────────────────────
export interface AutocompleteConfig {
  latex: boolean       // LaTeX 公式补全
  snippets: boolean    // 代码片段补全
  dicts: boolean       // 关键词字典补全
  dictGroups: DictGroup[]  // 字典组（含自定义）
}

const AUTOCOMPLETE_KEY = 'ts2_autocomplete_config'

export function loadAutocompleteConfig(): AutocompleteConfig {
  try {
    const raw = localStorage.getItem(AUTOCOMPLETE_KEY)
    if (raw) {
      const saved = JSON.parse(raw)
      return {
        latex: saved.latex ?? true,
        snippets: saved.snippets ?? true,
        dicts: saved.dicts ?? true,
        dictGroups: saved.dictGroups ?? DEFAULT_DICT_GROUPS,
      }
    }
  } catch { /* ignore */ }
  return {
    latex: true,
    snippets: true,
    dicts: true,
    dictGroups: DEFAULT_DICT_GROUPS,
  }
}

export function saveAutocompleteConfig(config: AutocompleteConfig): void {
  localStorage.setItem(AUTOCOMPLETE_KEY, JSON.stringify(config))
}

// ─── 构建 Vditor hint.extend 配置 ─────────────────────────────
export function buildHintExtends(config: AutocompleteConfig) {
  const extendsList: Array<{ key: string; hint: (key: string) => Promise<Array<{ html: string; value: string }>> }> = []

  // LaTeX 补全：\ 触发
  if (config.latex) {
    extendsList.push({
      key: '\\',
      hint: async (key: string) => {
        if (!key) {
          // 显示常用命令
          const common = ['frac', 'sqrt', 'sum', 'int', 'lim', 'begin', 'alpha', 'beta', 'gamma', 'delta', 'theta', 'lambda', 'omega', 'pi', 'phi', 'psi', 'nabla', 'partial', 'infty']
          return common.slice(0, 8).map(cmd => ({
            html: `<span style="color:#c678dd">\\${cmd}</span> <span style="color:#888;font-size:11px">${LATEX_COMMANDS[cmd] || ''}</span>`,
            value: LATEX_COMMANDS[cmd] || ('\\' + cmd),
          }))
        }
        const lowerKey = key.toLowerCase()
        const matches = Object.entries(LATEX_COMMANDS)
          .filter(([name]) => name.toLowerCase().startsWith(lowerKey))
          .slice(0, 8)
        return matches.map(([name, val]) => ({
          html: `<span style="color:#c678dd">\\${name}</span> <span style="color:#888;font-size:11px">${val.length > 30 ? val.substring(0, 30) + '…' : val}</span>`,
          value: val,
        }))
      },
    })
  }

  // 代码片段补全：! 触发
  if (config.snippets) {
    extendsList.push({
      key: '!',
      hint: async (key: string) => {
        const lowerKey = key.toLowerCase()
        const matches = Object.entries(SNIPPETS)
          .filter(([name]) => name.toLowerCase().startsWith(lowerKey))
          .slice(0, 8)
        if (!key) {
          return Object.entries(SNIPPETS).slice(0, 8).map(([name, val]) => ({
            html: `<span style="color:#e5c07b">!${name}</span> <span style="color:#888;font-size:11px">${val.split('\n')[0]}</span>`,
            value: val,
          }))
        }
        return matches.map(([name, val]) => ({
          html: `<span style="color:#e5c07b">!${name}</span> <span style="color:#888;font-size:11px">${val.split('\n')[0]}</span>`,
          value: val,
        }))
      },
    })
  }

  // 中文关键词字典补全：@ 触发
  if (config.dicts) {
    const zhEntries: DictEntry[] = []
    const enEntries: DictEntry[] = []
    for (const group of config.dictGroups) {
      if (group.enabled) {
        if (group.name.includes('中文')) {
          zhEntries.push(...group.entries)
        } else if (group.name.includes('English')) {
          enEntries.push(...group.entries)
        } else {
          // 自定义字典归入中文
          zhEntries.push(...group.entries)
        }
      }
    }

    if (zhEntries.length > 0) {
      extendsList.push({
        key: '@',
        hint: async (key: string) => {
          if (!key) {
            return zhEntries.slice(0, 8).map(entry => ({
              html: `<span style="color:#61afef">@${entry.keyword}</span>${entry.desc ? ` <span style="color:#888;font-size:11px">${entry.desc}</span>` : ''}`,
              value: entry.value,
            }))
          }
          const lowerKey = key.toLowerCase()
          const matches = zhEntries
            .filter(entry => entry.keyword.toLowerCase().includes(lowerKey) || entry.value.toLowerCase().includes(lowerKey))
            .slice(0, 8)
          return matches.map(entry => ({
            html: `<span style="color:#61afef">@${entry.keyword}</span>${entry.desc ? ` <span style="color:#888;font-size:11px">${entry.desc}</span>` : ''}`,
            value: entry.value,
          }))
        },
      })
    }

    if (enEntries.length > 0) {
      extendsList.push({
        key: '&',
        hint: async (key: string) => {
          if (!key) {
            return enEntries.slice(0, 8).map(entry => ({
              html: `<span style="color:#56b6c2">&${entry.keyword}</span>${entry.desc ? ` <span style="color:#888;font-size:11px">${entry.desc}</span>` : ''}`,
              value: entry.value,
            }))
          }
          const lowerKey = key.toLowerCase()
          const matches = enEntries
            .filter(entry => entry.keyword.toLowerCase().includes(lowerKey) || entry.value.toLowerCase().includes(lowerKey))
            .slice(0, 8)
          return matches.map(entry => ({
            html: `<span style="color:#56b6c2">&${entry.keyword}</span>${entry.desc ? ` <span style="color:#888;font-size:11px">${entry.desc}</span>` : ''}`,
            value: entry.value,
          }))
        },
      })
    }
  }

  return extendsList
}
