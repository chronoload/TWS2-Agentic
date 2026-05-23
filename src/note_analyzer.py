
"""
Rmd笔记分析器 - 提取定义、定理、推论、例子、问题、解答等内容
支持知识分类和知识图谱三元组标注
"""
import re
import json
import csv
from pathlib import Path


class KnowledgeCategory:
    """知识分类常量"""
    PRACTICE = "practice"       # 🔧 练习 - 巩固基本技能
    HEURISTIC = "heuristic"     # 💡 启发 - 制造认知冲突
    GENERALIZATION = "generalization"  # 🌉 推广 - 从特殊到一般
    REASONING = "reasoning"     # 🔗 推理 - 训练逻辑链条
    KERNEL = "kernel"           # ⚡ 要诀 - 提炼核心思想
    APPLICATION = "application" # 🏭 应用 - 对接真实情境
    
    ALL = [PRACTICE, HEURISTIC, GENERALIZATION, REASONING, KERNEL, APPLICATION]
    
    @staticmethod
    def get_display_name(category):
        """获取显示名称"""
        names = {
            KnowledgeCategory.PRACTICE: "🔧 练习",
            KnowledgeCategory.HEURISTIC: "💡 启发",
            KnowledgeCategory.GENERALIZATION: "🌉 推广",
            KnowledgeCategory.REASONING: "🔗 推理",
            KnowledgeCategory.KERNEL: "⚡ 要诀",
            KnowledgeCategory.APPLICATION: "🏭 应用"
        }
        return names.get(category, category)
    
    @staticmethod
    def get_description(category):
        """获取分类描述"""
        descriptions = {
            KnowledgeCategory.PRACTICE: "巩固基本技能，提高准确性和速度",
            KnowledgeCategory.HEURISTIC: "制造认知冲突，引出新概念或新视角",
            KnowledgeCategory.GENERALIZATION: "从特殊到一般，发现更广泛的规律",
            KnowledgeCategory.REASONING: "训练逻辑链条，填补推导中的步骤",
            KnowledgeCategory.KERNEL: "提炼核心思想、关键步骤、易错点",
            KnowledgeCategory.APPLICATION: "对接真实工程/生活情境，建模与估算"
        }
        return descriptions.get(category, "")


class NoteElement:
    """笔记元素"""
    def __init__(self, elem_type, title="", content="", course_id="", lesson_num=0, raw_start=-1, raw_end=-1):
        self.elem_type = elem_type
        self.title = title
        self.content = content
        self.course_id = course_id
        self.lesson_num = lesson_num
        self.raw_start = raw_start  # 原始内容起始位置（包括 ::: env）
        self.raw_end = raw_end      # 原始内容结束位置（包括 :::）
        self.id = "%s_%s" % (elem_type, str(hash(title + content) % 1000000))
        self.categories = []  # 知识分类标签
        self.tags = []        # 自定义标签
        self.triples = []     # 关联的知识三元组

    def to_dict(self, include_raw_pos=False):
        result = {
            "id": self.id,
            "type": self.elem_type,
            "title": self.title,
            "content": self.content,
            "course_id": self.course_id,
            "lesson_num": self.lesson_num,
            "categories": self.categories,
            "tags": self.tags,
            "triples": [triple.to_dict() for triple in self.triples]
        }
        if include_raw_pos:
            result["raw_start"] = self.raw_start
            result["raw_end"] = self.raw_end
        return result

    @staticmethod
    def from_dict(data):
        elem = NoteElement(
            elem_type=data.get("type", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            course_id=data.get("course_id", ""),
            lesson_num=data.get("lesson_num", 0),
            raw_start=data.get("raw_start", -1),
            raw_end=data.get("raw_end", -1)
        )
        elem.id = data.get("id", elem.id)
        elem.categories = data.get("categories", [])
        elem.tags = data.get("tags", [])
        elem.triples = [KnowledgeTriple.from_dict(d) for d in data.get("triples", [])]
        return elem
    
    def add_category(self, category):
        """添加知识分类标签"""
        if category not in self.categories:
            self.categories.append(category)
    
    def add_tag(self, tag):
        """添加自定义标签"""
        if tag not in self.tags:
            self.tags.append(tag)
    
    def add_triple(self, triple):
        """添加知识三元组"""
        self.triples.append(triple)


class KnowledgeTriple:
    """知识图谱三元组 - (主语, 谓语, 宾语)"""
    def __init__(self, subject, predicate, obj):
        self.subject = subject
        self.predicate = predicate
        self.object = obj
    
    def to_dict(self):
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object
        }
    
    @staticmethod
    def from_dict(data):
        return KnowledgeTriple(data.get("subject"), data.get("predicate"), data.get("object"))
    
    def __str__(self):
        return f'({self.subject}, {self.predicate}, {self.object})'


class KnowledgeRelation:
    """知识关系类型"""
    IS_A = "是"
    DEPENDS_ON = "依赖"
    EXAMPLE_OF = "是...的例子"
    GENERALIZATION_OF = "是...的推广"
    PREREQUISITE_OF = "是...的前置条件"
    APPLICATION_OF = "是...的应用"
    LEADS_TO = "引出"
    PART_OF = "是...的一部分"
    PROVES = "证明"
    EXPLAINS = "解释"
    
    # 学科探索相关关系
    PROBLEM_MOTIVATES = "问题引出"          # 问题→理论
    HEURISTIC_LEADS_TO = "启发得出"         # 启发→新理论
    GENERALIZES_FROM = "推广自"             # 从特殊推广到一般
    COROLLARY_OF = "是...的推论"            # 推论→定理
    APPLICATION_TO = "应用到"               # 理论→应用
    KEY_TIP_FOR = "是...的要诀"            # 要诀→知识点
    PRACTICE_CONSOLIDATES = "练习巩固"     # 练习→知识点
    REASONING_PROVES = "推理证明"           # 推理→结论
    THROUGH_PROBLEM = "通过...问题"         # 通过问题的方式


class NoteAnalyzer:
    """Rmd笔记分析器"""

    # 定义哪些环境类型可以有标题（definition/theorem等有正式名称的环境）
    TYPES_WITH_TITLE = {'definition', 'theorem', 'corollary', 'lemma', 'proposition', 'axiom', 'postulate'}
    # 定义哪些环境类型不应该有标题（problem/example等以内容为主的环境）
    TYPES_WITHOUT_TITLE = {'problem', 'example', 'exercise', 'remark', 'note', 'solution', 'proof'}
    
    @staticmethod
    def parse_note(content, course_id="", lesson_num=0):
        """解析Rmd笔记内容，提取所有环境并按位置排序（支持任意环境名）"""
        elements = []
        
        # 寻找所有 ::: 开头的环境
        # 匹配 ::: envname
        start_pattern = re.compile(r':::\s*([a-zA-Z_][a-zA-Z0-9_]*)', re.IGNORECASE)
        
        i = 0
        n = len(content)
        while i < n - 3:
            match = start_pattern.search(content, i)
            if not match:
                break
            
            env_type = match.group(1).lower()
            start_idx = match.start()
            
            # 找到匹配的结束 :::
            end_idx = NoteAnalyzer._find_closing_triple_colon(content, start_idx)
            if end_idx > start_idx:
                # 提取内容
                content_start = match.end()
                if content_start < len(content) and content[content_start] == '\n':
                    content_start += 1
                
                elem_content = content[content_start:end_idx].strip()
                # 清理转义字符
                elem_content = elem_content.replace('\\*', '*')
                
                title = ""
                remaining_content = ""
                
                # 根据环境类型决定是否提取标题
                # 内容型元素：我们依然想要把内容作为标题（便于识别）
                content_types = ["remark", "problem", "exercise", "question", "example", "note", "solution", "proof"]
                if env_type in content_types:
                    # 内容型元素：使用我们的新逻辑，把内容作为标题
                    title, remaining_content = NoteAnalyzer._extract_title_and_content(elem_content, env_type=env_type)
                elif env_type in NoteAnalyzer.TYPES_WITHOUT_TITLE:
                    # 其他不要标题的类型：整个内容都是内容
                    remaining_content = NoteAnalyzer._clean_content(elem_content)
                elif env_type in NoteAnalyzer.TYPES_WITH_TITLE:
                    # 这些类型可以有标题，提取标题和内容
                    title, remaining_content = NoteAnalyzer._extract_title_and_content(elem_content, env_type=env_type)
                else:
                    # 其他类型：只有加粗的才提取标题
                    title, remaining_content = NoteAnalyzer._extract_title_and_content(elem_content, require_markdown=True)
                
                elem = NoteElement(env_type, title, remaining_content, course_id, lesson_num, 
                                   start_idx, end_idx + 3)
                elements.append(elem)
                
                i = end_idx + 3
            else:
                i = match.end()
        
        # 按开始位置排序
        elements.sort(key=lambda x: x.raw_start)
        return elements
    
    @staticmethod
    def _extract_title_and_content(elem_content, require_markdown=False, env_type=None):
        """提取标题和内容 - 优先用内容作为标题（便于识别）
        
        Args:
            elem_content: 环境内的原始内容
            require_markdown: 是否必须用markdown格式（**标题**）才算标题
            env_type: 环境类型，用于决定如何处理标题
            
        Returns:
            (title, content) 元组
        """
        if not elem_content:
            return "", ""
        
        # 清理转义字符
        elem_content = elem_content.replace('\\*', '*')
        
        lines = elem_content.split('\n', 1)
        first_line = lines[0].strip()
        
        # 内容型元素 - 把内容作为标题（前60个字符），便于识别
        content_types = ["remark", "problem", "exercise", "question", "example", "note", "solution", "proof"]
        if env_type in content_types:
            # 优先用内容作为标题（前60字符），完整内容保留
            title = first_line[:60] + ("..." if len(first_line) > 60 else "")
            content = NoteAnalyzer._clean_content(elem_content)
            return title, content
        
        # 识别加粗标题 **...**
        if first_line.startswith('**') and first_line.endswith('**'):
            title = first_line[2:-2].strip()
            remaining = lines[1].strip() if len(lines) > 1 else ""
            content = NoteAnalyzer._clean_content(remaining)
            return title, content
        
        # 如果要求markdown格式，或者不是明确可作为标题的情况
        if require_markdown:
            content = NoteAnalyzer._clean_content(elem_content)
            return "", content
        
        # 识别短标题（需要同时满足多个条件）
        # 1. 长度适中（3-50字符）- 太短或太长都不像标题
        # 2. 不以标点结尾 - 句子通常以标点结尾
        # 3. 不包含"？"、"如果"等疑问词开头 - 这些更像问题
        # 4. 不以"解："、"答案："、"证："等开头 - 这些是解答不是标题
        is_likely_title = (
            3 <= len(first_line) <= 50 and
            not first_line.endswith(('.', '，', '。', '?', '？', ';', '：', ':', '!', '！')) and
            not first_line.startswith(('如果', '假设', '求', '计算', '证明', '解：', '答案：', '证：', '为什么', '怎样', '如何'))
        )
        
        if is_likely_title:
            title = first_line
            remaining = lines[1].strip() if len(lines) > 1 else ""
            content = NoteAnalyzer._clean_content(remaining)
        else:
            title = ""
            content = NoteAnalyzer._clean_content(elem_content)
        
        return title, content
    
    @staticmethod
    def _clean_content(content):
        """清理内容中的多余空白和换行"""
        if not content:
            return ""
        
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # 移除行尾空白
            line = line.rstrip()
            # 跳过纯空白行
            if line.strip():
                cleaned_lines.append(line)
        
        # 移除开头的多余空行
        while cleaned_lines and not cleaned_lines[0].strip():
            cleaned_lines.pop(0)
        
        # 移除结尾的空行
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()
        
        return '\n'.join(cleaned_lines).strip()

    @staticmethod
    def _find_closing_triple_colon(content, start):
        """找到匹配的结束三冒号（支持任意环境）"""
        depth = 1
        i = start + 3  # 跳过开始的:::
        n = len(content)
        while i < n - 2:
            if content[i:i+3] == ':::':
                # 检查是不是另一个环境的开始
                next_part = content[i+3:i+30] if i+30 < n else content[i+3:]
                # 匹配 ::: envname 格式
                env_match = re.match(r'\s*([a-zA-Z_][a-zA-Z0-9_]*)', next_part)
                if env_match:
                    depth += 1
                else:
                    depth -= 1
                
                if depth == 0:
                    return i
                i += 3
            else:
                i += 1
        return n
    
    @staticmethod
    def _find_closing_triple_colon_simple(content, start, env_type):
        """简化版：找到紧随其后的结束三冒号（不深度嵌套）"""
        i = start + 3  # 跳过开始的:::
        n = len(content)
        while i < n - 2:
            if content[i:i+3] == ':::':
                # 检查是不是另一个环境的开始
                next_part = content[i+3:i+30] if i+30 < n else content[i+3:]
                # 匹配 ::: envname 格式
                env_match = re.match(r'\s*([a-zA-Z_][a-zA-Z0-9_]*)', next_part)
                if not env_match:
                    # 这是结束标记
                    return i
                i += 3
            else:
                i += 1
        return -1

    @staticmethod
    def find_problem_solution_pair(elements):
        """查找问题和对应的解答"""
        pairs = []
        i = 0
        n = len(elements)
        while i < n:
            if elements[i].elem_type == "problem":
                problem = elements[i]
                solution = None
                # 查找紧随问题后的解答
                j = i + 1
                while j < n:
                    if elements[j].elem_type == "solution":
                        # 检查解答标题是否包含问题标题
                        if problem.title and problem.title in elements[j].title:
                            solution = elements[j]
                            break
                        # 如果没有匹配标题，但位置紧随问题后，也视为对应的解答
                        if solution is None:
                            solution = elements[j]
                            break
                    elif elements[j].elem_type == "problem":
                        break
                    j += 1
                pairs.append((problem, solution))
            i += 1
        return pairs
    
    @staticmethod
    def find_theorem_proof_pair(elements):
        """查找定理、推论和对应的证明"""
        pairs = []
        i = 0
        n = len(elements)
        theorem_types = ["theorem", "corollary", "lemma", "proposition", "axiom", "postulate"]
        while i < n:
            if elements[i].elem_type in theorem_types:
                theorem = elements[i]
                proof = None
                # 查找紧随其后的证明
                j = i + 1
                while j < n:
                    if elements[j].elem_type == "proof":
                        # 检查证明标题是否包含定理标题
                        if theorem.title and theorem.title in elements[j].title:
                            proof = elements[j]
                            break
                        # 如果没有匹配标题，但位置紧随其后，也视为对应的证明
                        if proof is None:
                            proof = elements[j]
                            break
                    elif elements[j].elem_type in theorem_types:
                        break
                    j += 1
                pairs.append((theorem, proof))
            i += 1
        return pairs
    
    @staticmethod
    def generate_fill_in_blank(content):
        """
        智能生成填空题
        
        策略：
        1. 首先检查是否有显式标记的空白（如 {{...}} 或 [[...]]）
        2. 如果没有，则智能识别关键内容进行挖空
        3. 对于定义类内容，挖空被定义的术语
        4. 对于数学内容，挖空重要的公式或结论
        5. 对于一般内容，挖空关键词或关键短语
        
        返回：(masked_text, answers_list, full_text)
            masked_text: 挖空后的文本
            answers_list: 答案列表（每个被挖空的答案）
            full_text: 原始完整文本
        """
        if not content:
            return "", [], ""
        
        # === 策略1：查找显式标记的空白 ===
        # 支持 {{answer}} 或 [[answer]] 标记的填空题
        explicit_patterns = [
            (re.compile(r'\{\{([^}]+)\}\}'), r'{{', r'}}'),  # {{answer}}
            (re.compile(r'\[\[([^\]]+)\]\]'), r'[[', r']]')   # [[answer]]
        ]
        
        for pattern, start_tag, end_tag in explicit_patterns:
            if pattern.search(content):
                answers = []
                masked = content
                
                # 收集所有答案并替换为空白
                for match in pattern.finditer(content):
                    answer = match.group(1).strip()
                    if answer:
                        answers.append(answer)
                
                # 替换标记为 ___
                def replace_with_blank(match):
                    return "___"
                
                masked = pattern.sub(replace_with_blank, masked)
                
                if answers:
                    return masked, answers, content
        
        # === 策略2：智能识别关键内容进行挖空 ===
        answers = []
        
        # 首先清理文本，处理多余的换行
        cleaned_content = content.replace('\r\n', '\n').replace('\r', '\n').strip()
        
        # 尝试处理不同类型的内容
        lines = [line.strip() for line in cleaned_content.split('\n') if line.strip()]
        
        if not lines:
            return content, [], content
        
        # === 定义类内容：识别 "A是B" 或 "A定义为B" 结构 ===
        definition_patterns = [
            re.compile(r'(\S+)\s*[是指]?\s*定[义义为]\s*(.+)'),
            re.compile(r'^([^：。]+)[:：]\s*(.+)'),  # A：B 格式
            re.compile(r'^(\S+)\s*是\s*(.+)'),
        ]
        
        for line in lines[:3]:  # 只在前几行查找，避免挖空太多
            for pattern in definition_patterns:
                match = pattern.match(line)
                if match:
                    term = match.group(1).strip()
                    if len(term) >= 2:  # 确保是有意义的术语
                        answers.append(term)
                        masked = cleaned_content.replace(term, "___", 1)
                        return masked, answers, cleaned_content
        
        # === 数学类内容：识别公式和重要表达式 ===
        math_patterns = [
            re.compile(r'\$([^$]+)\$'),  # LaTeX行内公式
            re.compile(r'\\\[([^\\]+)\\\]'),  # LaTeX块级公式
        ]
        
        for pattern in math_patterns:
            matches = pattern.findall(cleaned_content)
            if matches:
                formula = matches[0].strip()
                if formula:
                    answers.append(formula)
                    masked = pattern.sub("___", cleaned_content, count=1)
                    return masked, answers, cleaned_content
        
        # === 通用策略：智能选择关键词挖空 ===
        # 1. 首先选择第一句或关键段落
        key_text = cleaned_content
        if len(lines) > 1:
            key_text = lines[0] if len(lines[0]) > 20 else '\n'.join(lines[:2])
        
        # 2. 选择有意义的部分挖空（避免太短的）
        sentences = re.split(r'[。！？.!?]', key_text)
        target_sentence = None
        
        for s in sentences:
            s = s.strip()
            if len(s) >= 15:  # 确保句子有一定长度
                target_sentence = s
                break
        
        if not target_sentence:
            target_sentence = key_text[:min(100, len(key_text))]
        
        # 3. 选择中间部分挖空
        words = re.split(r'(\s+)', target_sentence)
        if len(words) >= 5:
            # 选择中间1-3个有意义的词作为答案
            middle = len(words) // 2
            # 收集一些连续的词
            selected_words = []
            for i in range(max(0, middle - 1), min(len(words), middle + 2)):
                if words[i].strip():
                    selected_words.append(words[i])
            
            if selected_words:
                answer = ''.join(selected_words)
                if len(answer) >= 3:
                    # 构造挖空文本
                    # 在原文中找到这个短语并替换
                    answer_start = target_sentence.find(answer)
                    if answer_start >= 0:
                        masked_sentence = target_sentence[:answer_start] + "___" + target_sentence[answer_start + len(answer):]
                        masked = cleaned_content.replace(target_sentence, masked_sentence, 1)
                        answers.append(answer)
                        return masked, answers, cleaned_content
        
        # === 兜底策略：随机选择中间部分 ===
        if len(cleaned_content) > 20:
            mid = len(cleaned_content) // 2
            start = max(0, mid - 10)
            end = min(len(cleaned_content), mid + 10)
            
            # 尝试在单词边界处截取
            while start > 0 and cleaned_content[start].isalnum():
                start -= 1
            while end < len(cleaned_content) and cleaned_content[end - 1].isalnum():
                end += 1
            
            to_mask = cleaned_content[start:end].strip()
            if len(to_mask) >= 3:
                answers.append(to_mask)
                masked = cleaned_content[:start] + "___" + cleaned_content[end:]
                return masked, answers, cleaned_content
        
        # 如果所有策略都失败，返回原始内容
        return cleaned_content, [], cleaned_content
    
    @staticmethod
    def auto_classify_elements(elements):
        """自动对元素进行知识分类"""
        for elem in elements:
            NoteAnalyzer._classify_single_element(elem)
        return elements
    
    @staticmethod
    def _classify_single_element(elem):
        """对单个元素进行分类"""
        text = (elem.title + " " + elem.content).lower()
        elem_type = elem.elem_type
        
        # 根据元素类型初步分类
        # 理论类元素 - 主要标记为推理
        if elem_type in ["definition", "theorem", "corollary", "lemma", "proposition", "axiom", "postulate"]:
            # 定义和定理类默认标记为推理类
            elem.add_category(KnowledgeCategory.REASONING)
            
            # 如果是推论，标记为推广
            if elem_type == "corollary":
                elem.add_category(KnowledgeCategory.GENERALIZATION)
        
        # 问题/练习类元素 - 默认标记为练习
        elif elem_type in ["problem", "exercise", "question", "remark"]:
            elem.add_category(KnowledgeCategory.PRACTICE)
        
        # 例子类元素 - 应用
        elif elem_type in ["example", "note"]:
            elem.add_category(KnowledgeCategory.APPLICATION)
        
        # 解答/证明类元素 - 推理
        elif elem_type in ["solution", "proof"]:
            elem.add_category(KnowledgeCategory.REASONING)
        
        # 启发类 - 根据关键词判断
        heuristic_indicators = ["如果", "假设", "猜想", "会怎样", "猜一猜", "为什么", "有趣", "奇妙"]
        for indicator in heuristic_indicators:
            if indicator in text:
                elem.add_category(KnowledgeCategory.HEURISTIC)
                break
        
        # 推理类 - 根据关键词判断（理论类已默认添加）
        if elem_type not in ["definition", "theorem", "corollary", "lemma", "proposition", "axiom", "postulate", "solution", "proof"]:
            reasoning_indicators = ["证明", "推导", "验证", "补全", "推出", "因为", "所以", "从而", "因此"]
            for indicator in reasoning_indicators:
                if indicator in text:
                    elem.add_category(KnowledgeCategory.REASONING)
                    break
        
        # 推广类 - 根据关键词判断
        generalization_indicators = ["推广到", "一般化", "任意", "n维", "更一般", "从...到..."]
        for indicator in generalization_indicators:
            if indicator in text:
                elem.add_category(KnowledgeCategory.GENERALIZATION)
                break
        
        # 要诀类 - 根据关键词判断
        kernel_indicators = ["步骤", "关键", "要诀", "核心", "易错", "注意", "小结", "总结", "套路"]
        for indicator in kernel_indicators:
            if indicator in text:
                elem.add_category(KnowledgeCategory.KERNEL)
                break
        
        # 应用类 - 根据关键词判断（例子类已默认添加）
        if elem_type not in ["example", "note"]:
            application_indicators = ["应用", "估算", "设计", "真实", "实际", "情境", "工程", "生活"]
            for indicator in application_indicators:
                if indicator in text:
                    elem.add_category(KnowledgeCategory.APPLICATION)
                    break
        
        # 练习类 - 根据关键词判断（问题类已默认添加）
        if elem_type not in ["problem", "exercise", "question", "remark"]:
            # 练习类需要有明确的练习题指示词
            practice_indicators = ["练习题", "作业", "习题", "练习", "自测", "测验"]
            for indicator in practice_indicators:
                if indicator in text:
                    elem.add_category(KnowledgeCategory.PRACTICE)
                    break
    
    @staticmethod
    def auto_extract_triples(elements):
        """自动解析上下文关系：问题→例子→定义→推论→定理→应用→解决问题"""
        triples = []
        
        # 知识发现流程 - 自动建立相邻元素间的关系
        problem_types = ["problem", "exercise", "question", "remark"]
        example_types = ["example", "note"]
        theory_types = ["definition", "lemma", "proposition", "axiom", "postulate"]
        theorem_types = ["theorem"]
        corollary_types = ["corollary"]
        application_types = ["example"]
        solution_types = ["solution", "proof"]
        
        for i, elem in enumerate(elements):
            if i == 0:
                continue
            
            prev_elem = elements[i - 1]
            
            # 确保我们有标题（即使是简短的）
            subj_title = prev_elem.title or f"{prev_elem.elem_type} {prev_elem.id}"
            obj_title = elem.title or f"{elem.elem_type} {elem.id}"
            
            # 建立关系的核心逻辑
            
            # 1. 问题 → 例子：问题引出例子（启发）
            if prev_elem.elem_type in problem_types and elem.elem_type in example_types:
                triple = KnowledgeTriple(subj_title, "启发", obj_title)
                triples.append(triple)
                elem.add_triple(triple)
            
            # 2. 例子 → 问题：例子启发问题
            elif prev_elem.elem_type in example_types and elem.elem_type in problem_types:
                triple = KnowledgeTriple(subj_title, "启发", obj_title)
                triples.append(triple)
                elem.add_triple(triple)
            
            # 3. 问题/例子 → 定义/公理/引理：抽象到理论（推论）
            elif (prev_elem.elem_type in problem_types + example_types and 
                  elem.elem_type in theory_types):
                triple = KnowledgeTriple(subj_title, "推论", obj_title)
                triples.append(triple)
                elem.add_triple(triple)
            
            # 4. 定义 → 定理：从定义到定理
            elif prev_elem.elem_type in theory_types and elem.elem_type in theorem_types:
                triple = KnowledgeTriple(subj_title, "推论", obj_title)
                triples.append(triple)
                elem.add_triple(triple)
            
            # 5. 定理 → 推论：推论是定理的推广
            elif prev_elem.elem_type in theorem_types and elem.elem_type in corollary_types:
                triple = KnowledgeTriple(subj_title, "推广", obj_title)
                triples.append(triple)
                elem.add_triple(triple)
            
            # 6. 定理/推论 → 例子/问题：应用到例子
            elif (prev_elem.elem_type in theorem_types + corollary_types + theory_types and 
                  elem.elem_type in example_types + problem_types):
                triple = KnowledgeTriple(subj_title, "应用", obj_title)
                triples.append(triple)
                elem.add_triple(triple)
            
            # 7. 问题 → 解答：通过练习解决问题
            elif prev_elem.elem_type in problem_types and elem.elem_type in solution_types:
                triple = KnowledgeTriple(subj_title, "练习", obj_title)
                triples.append(triple)
                elem.add_triple(triple)
            
            # 8. 其他相邻关系：默认建立前提关系
            else:
                # 只有比较接近的元素才建立前提关系（避免太宽泛）
                if elem.lesson_num == prev_elem.lesson_num and elem.course_id == prev_elem.course_id:
                    triple = KnowledgeTriple(subj_title, "前提", obj_title)
                    triples.append(triple)
                    elem.add_triple(triple)
        
        return triples

    @staticmethod
    def extract_from_file(file_path, course_id="", lesson_num=0):
        """从文件中提取元素"""
        try:
            content = file_path.read_text(encoding="utf-8")
            return NoteAnalyzer.parse_note(content, course_id, lesson_num)
        except Exception as e:
            print("Error parsing note %s: %s" % (file_path, e))
            return []

    @staticmethod
    def to_json(elements, output_path):
        """导出为JSON - 包含所有字段（包括位置）"""
        data = {
            "note_elements": [elem.to_dict(include_raw_pos=True) for elem in elements],
            "total_count": len(elements),
            "type_counts": {}
        }
        for elem in elements:
            if elem.elem_type not in data["type_counts"]:
                data["type_counts"][elem.elem_type] = 0
            data["type_counts"][elem.elem_type] += 1
        
        output_path.parent.mkdir(exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def to_csv(elements, output_path):
        """导出为CSV - 不包含位置字段"""
        if not elements:
            return
        
        output_path.parent.mkdir(exist_ok=True)
        fieldnames = ["id", "type", "title", "content", "course_id", "lesson_num"]
        
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for elem in elements:
                writer.writerow(elem.to_dict(include_raw_pos=False))

    @staticmethod
    def to_xlsx(elements, output_path):
        """导出为XLSX - 不包含位置字段"""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("需要pandas库，运行: pip install pandas openpyxl")
        
        if not elements:
            return
        
        output_path.parent.mkdir(exist_ok=True)
        
        data = [elem.to_dict(include_raw_pos=False) for elem in elements]
        df = pd.DataFrame(data)
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='All_Elements', index=False)
            
            for elem_type in set(e.elem_type for e in elements):
                type_data = [e.to_dict(include_raw_pos=False) for e in elements if e.elem_type == elem_type]
                pd.DataFrame(type_data).to_excel(writer, sheet_name=elem_type.title(), index=False)

    @staticmethod
    def from_json(json_path):
        """从JSON导入"""
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [NoteElement.from_dict(d) for d in data.get("note_elements", [])]

    @staticmethod
    def from_csv(csv_path):
        """从CSV导入"""
        import csv
        elements = []
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                elements.append(NoteElement.from_dict(row))
        return elements


class SpacedRepetitionManager:
    """间隔重复复习管理器"""
    
    DEFAULT_INTERVALS = [0.1, 1, 6, 24, 72, 168, 336]
    
    def __init__(self, data_path):
        self.data_path = data_path
        self.review_data = self._load()

    def _load(self):
        if self.data_path.exists():
            try:
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"reviews": {}}

    def _save(self):
        self.data_path.parent.mkdir(exist_ok=True)
        with open(self.data_path, 'w', encoding='utf-8') as f:
            json.dump(self.review_data, f, ensure_ascii=False, indent=2)

    def add_element(self, elem):
        if elem.id not in self.review_data["reviews"]:
            self.review_data["reviews"][elem.id] = {
                "elem": elem.to_dict(include_raw_pos=True),
                "level": 0,
                "next_review": None,
                "history": []
            }
            self._save()

    def review(self, elem_id, quality):
        if elem_id not in self.review_data["reviews"]:
            return
        
        review = self.review_data["reviews"][elem_id]
        history_entry = {
            "timestamp": "",
            "quality": quality,
            "old_level": review["level"]
        }
        
        if quality >= 4:
            review["level"] = min(review["level"] + 1, len(self.DEFAULT_INTERVALS) - 1)
        elif quality <= 2:
            review["level"] = max(review["level"] - 1, 0)
        
        import datetime
        interval = self.DEFAULT_INTERVALS[review["level"]]
        next_time = datetime.datetime.now() + datetime.timedelta(hours=interval)
        review["next_review"] = next_time.isoformat()
        
        history_entry["new_level"] = review["level"]
        history_entry["timestamp"] = datetime.datetime.now().isoformat()
        review["history"].append(history_entry)
        
        self._save()

    def get_due_reviews(self):
        import datetime
        now = datetime.datetime.now()
        due = []
        for elem_id, review in self.review_data["reviews"].items():
            next_str = review.get("next_review")
            if next_str:
                try:
                    next_review = datetime.datetime.fromisoformat(next_str)
                    if next_review <= now:
                        elem_data = review.get("elem", {})
                        due.append(NoteElement.from_dict(elem_data))
                except:
                    pass
        return due

    def get_all_elements(self):
        return [NoteElement.from_dict(r.get("elem", {})) 
                for r in self.review_data["reviews"].values()]


class KnowledgeGraph:
    """知识图谱管理器"""
    def __init__(self):
        self.nodes = {}  # 节点 {id: {"label": ..., "type": ..., "categories": []}}
        self.edges = []  # 边 [(source, target, relation)]
        self.elem_nodes = {}  # 元素ID到节点ID的映射
    
    def add_element(self, elem):
        """添加笔记元素为节点"""
        node_id = elem.id
        label = elem.title or elem.elem_type
        node_type = elem.elem_type
        categories = elem.categories
        self.nodes[node_id] = {
            "label": label,
            "type": node_type,
            "categories": categories,
            "content": elem.content
        }
        self.elem_nodes[elem.id] = node_id
        
        # 添加元素的三元组作为边
        for triple in elem.triples:
            # 查找或创建主语和宾语节点
            subj_id = self._get_or_create_node(triple.subject, "concept")
            obj_id = self._get_or_create_node(triple.object, "concept")
            self.edges.append((subj_id, obj_id, triple.predicate))
        
        return node_id
    
    def _get_or_create_node(self, label, node_type):
        """获取或创建节点"""
        for node_id, node in self.nodes.items():
            if node["label"] == label:
                return node_id
        node_id = f"concept_{len(self.nodes)}"
        self.nodes[node_id] = {
            "label": label,
            "type": node_type,
            "categories": [],
            "content": ""
        }
        return node_id
    
    def build_from_elements(self, elements):
        """从元素列表构建知识图谱"""
        for elem in elements:
            self.add_element(elem)
        
        # 自动建立元素间的关系
        for i, elem in enumerate(elements):
            if i > 0:
                prev_elem = elements[i-1]
                # 同一课时内的元素建立时序关系
                if prev_elem.lesson_num == elem.lesson_num:
                    self.edges.append((
                        self.elem_nodes.get(prev_elem.id, prev_elem.id),
                        self.elem_nodes.get(elem.id, elem.id),
                        "随后出现"
                    ))
        return self
    
    def get_nodes_by_category(self, category):
        """按分类获取节点"""
        return [
            node_id for node_id, node in self.nodes.items()
            if category in node["categories"]
        ]
    
    def get_related_nodes(self, node_id):
        """获取与某节点相关的所有节点"""
        related = set()
        for source, target, relation in self.edges:
            if source == node_id:
                related.add(target)
            if target == node_id:
                related.add(source)
        return list(related)
    
    def to_cytoscape_json(self):
        """导出为Cytoscape.js格式的JSON（用于可视化）"""
        data = {"nodes": [], "edges": []}
        
        # 添加节点
        for node_id, node in self.nodes.items():
            data["nodes"].append({
                "data": {
                    "id": node_id,
                    "label": node["label"],
                    "type": node["type"],
                    "categories": node["categories"]
                }
            })
        
        # 添加边
        for idx, (source, target, relation) in enumerate(self.edges):
            data["edges"].append({
                "data": {
                    "id": f"edge_{idx}",
                    "source": source,
                    "target": target,
                    "label": relation
                }
            })
        
        return data
    
    def to_graphviz_dot(self):
        """导出为Graphviz DOT格式"""
        lines = ["digraph KnowledgeGraph {"]
        lines.append("    rankdir=LR;")
        lines.append("    node [fontname=\"Microsoft YaHei\"];")
        
        # 节点
        node_colors = {
            "definition": "#FFB3BA",
            "theorem": "#BAFFC9",
            "corollary": "#BAE1FF",
            "example": "#FFFFBA",
            "problem": "#FFE6CC",
            "remark": "#E8E8E8"
        }
        
        for node_id, node in self.nodes.items():
            color = node_colors.get(node["type"], "#FFFFFF")
            label = node["label"]
            lines.append(f'    "{node_id}" [label="{label}", style=filled, fillcolor="{color}"];')
        
        # 边
        for idx, (source, target, relation) in enumerate(self.edges):
            lines.append(f'    "{source}" -> "{target}" [label="{relation}"];')
        
        lines.append("}")
        return "\n".join(lines)
    
    def get_statistics(self):
        """获取统计信息"""
        stats = {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_types": {},
            "category_distribution": {}
        }
        
        for node in self.nodes.values():
            node_type = node["type"]
            if node_type not in stats["node_types"]:
                stats["node_types"][node_type] = 0
            stats["node_types"][node_type] += 1
            
            for category in node["categories"]:
                if category not in stats["category_distribution"]:
                    stats["category_distribution"][category] = 0
                stats["category_distribution"][category] += 1
        
        return stats
    
    @staticmethod
    def load_from_elements(elements):
        """从元素加载知识图谱"""
        graph = KnowledgeGraph()
        graph.build_from_elements(elements)
        return graph
    
    def get_graph_data_for_drawing(self):
        """获取用于绘制的图数据（节点位置和颜色）"""
        nodes = []
        colors = {
            "definition": "#FFB3BA",
            "theorem": "#BAFFC9",
            "corollary": "#BAE1FF",
            "example": "#FFFFBA",
            "problem": "#FFE6CC",
            "remark": "#E8E8E8"
        }
        for idx, (node_id, node) in enumerate(self.nodes.items()):
            x = 200 + (idx % 7) * 120
            y = 200 + (idx // 7) * 100
            nodes.append({
                "id": node_id,
                "label": node["label"],
                "type": node["type"],
                "categories": node["categories"],
                "x": x,
                "y": y,
                "color": colors.get(node["type"], "#FFFFFF"),
                "related": self.get_related_nodes(node_id)
            })
        
        edges = []
        for idx, (source, target, relation) in enumerate(self.edges):
            edges.append({
                "source": source,
                "target": target,
                "relation": relation,
                "id": f"edge_{idx}"
            })
        
        return {"nodes": nodes, "edges": edges}


