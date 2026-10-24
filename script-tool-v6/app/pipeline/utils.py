import json
import re


def _close_brackets(frag: str) -> str:
    """补全片段中未闭合的括号与字符串引号，使其成为合法 JSON 候选。"""
    stack = []
    in_str = False
    esc = False
    for ch in frag:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()
    if in_str:
        frag += '"'
    for op in reversed(stack):
        frag += "}" if op == "{" else "]"
    return frag


def _repair_truncated(text: str):
    """抢救被 max_tokens 截断的 JSON：从后往前在元素边界截断并补全括号。

    长输出（如分镜列表）被截断时，尾部会停在某个对象中间。
    这里回退到最近若干个 } / ] 边界，丢掉不完整的尾元素，
    补全外层括号后重试解析，能救回前面完整的部分。
    """
    bounds = [m.end() for m in re.finditer(r'[}\]]', text)]
    for end in reversed(bounds[-30:]):
        frag = text[:end].rstrip()
        if frag.endswith(","):
            frag = frag[:-1]
        try:
            return json.loads(_close_brackets(frag))
        except json.JSONDecodeError:
            continue
    return None


def extract_json(response: str) -> dict:
    """从 AI 响应中稳健提取 JSON 对象。

    支持以下格式：
    1. ```json{...}```  / ```{...}``` 代码块
    2. 纯 JSON 文本
    3. 文本中嵌入的首个 {...} 对象

    解析失败时打印诊断信息并返回空 dict。
    """
    if not response or not response.strip():
        print("[extract_json] WARNING: AI 返回了空响应")
        return {}

    text = response.strip()

    # 策略 1：提取 ```json ... ``` 或 ``` ... ``` 代码块
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
        print("[extract_json] 策略1（代码块）匹配成功")

    # 策略 2：提取首个完整的 {...} JSON 对象（处理嵌套）
    if not text.startswith('{'):
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            text = m.group(0)
            print("[extract_json] 策略2（花括号提取）匹配成功")
        else:
            print("[extract_json] WARNING: 策略1和2均未匹配到 JSON 结构，将尝试直接解析原始文本")
            print(f"[extract_json] 原始响应前 500 字符：\n{response[:500]}")

    # 策略 3：直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[extract_json] ERROR: JSON 解析失败 — {e}")
        # 策略 4：截断抢救（max_tokens 截断是长输出的常见失败模式）
        repaired = _repair_truncated(text)
        if repaired is not None:
            print("[extract_json] 策略4（截断抢救）成功，已救回部分完整元素")
            return repaired
        print(f"[extract_json] 待解析文本前 500 字符：\n{text[:500]}")
        print(f"[extract_json] 原始响应前 500 字符：\n{response[:500]}")
        return {}
